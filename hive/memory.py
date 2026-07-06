"""Memory system — short-term (in-memory) + long-term (SQLite)."""

import json
import time
from collections import deque, OrderedDict
from hive.config import MAX_MESSAGES, MAX_TOOL_CACHE, MAX_TOKENS


def estimate_tokens(text: str) -> int:
    """Better token estimate: average of word count and char/4."""
    if not text:
        return 0
    word_count = len(text.split())
    char_count = len(text) // 4
    return (word_count + char_count) // 2


class ShortTermMemory:
    """In-memory session context. Dies when session ends."""

    def __init__(self, max_messages: int = MAX_MESSAGES,
                 max_tool_cache: int = MAX_TOOL_CACHE):
        self.messages = deque(maxlen=max_messages)
        self.tool_cache = OrderedDict()
        self.agents = {}
        self.max_tool_cache = max_tool_cache

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })

    def cache_tool_result(self, tool_name: str, args: dict, result: str) -> None:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        self.tool_cache[key] = {
            "result": result,
            "timestamp": time.time(),
        }
        if len(self.tool_cache) > self.max_tool_cache:
            self.tool_cache.popitem(last=False)

    def get_cached_tool(self, tool_name: str, args: dict) -> str | None:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        entry = self.tool_cache.get(key)
        if entry:
            return entry["result"]
        return None

    def get_context_window(self, max_tokens: int = MAX_TOKENS) -> list[dict]:
        """Build message list fitting within token limit.
        Always includes the last 4 messages for continuity."""
        if not self.messages:
            return []

        # Always keep last 4 messages
        recent = list(self.messages)[-4:]
        older = list(self.messages)[:-4]

        messages = [{"role": m["role"], "content": m["content"]} for m in recent]
        total = sum(estimate_tokens(m["content"]) for m in recent)

        # Add older messages that fit
        for msg in reversed(older):
            msg_tokens = estimate_tokens(msg["content"])
            if total + msg_tokens > max_tokens:
                break
            messages.insert(0, {"role": msg["role"], "content": msg["content"]})
            total += msg_tokens

        return messages

    def update_agent_state(self, agent_name: str, state: dict) -> None:
        self.agents[agent_name] = state

    def remove_agent(self, agent_name: str) -> None:
        self.agents.pop(agent_name, None)

    def clear(self) -> None:
        self.messages.clear()
        self.tool_cache.clear()
        self.agents.clear()
