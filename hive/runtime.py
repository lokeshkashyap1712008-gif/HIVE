"""Runtime — agent execution loop with process isolation."""

import asyncio
import json
import time
import types
from concurrent.futures import ProcessPoolExecutor
from hive.config import MAX_AGENTS, AGENT_TIMEOUT
from hive.llm import QwenClient
from hive.tools import TOOLS, execute_tool
from hive.permissions import get_tool_tier, check_dangerous_command, should_auto_allow


def _run_agent_process(agent_code: str, task: str, context: dict) -> dict:
    """Runs in a separate process. Agent's own memory space."""
    module = types.ModuleType("agent_module")
    module.__dict__["__name__"] = "agent_module"
    try:
        exec(agent_code, module.__dict__)
    except Exception as e:
        return {"error": f"Agent code execution failed: {e}"}

    # Find agent class
    agent_class = None
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and hasattr(obj, "execute"):
            agent_class = obj
            break

    if not agent_class:
        return {"error": "No agent class with execute() method found"}

    try:
        agent = agent_class()
        result = agent.execute(task, context)
        return {"result": result}
    except Exception as e:
        return {"error": f"Agent execution failed: {e}"}


class AgentRuntime:
    """Manages agent execution with process isolation."""

    def __init__(self, llm: QwenClient):
        self.llm = llm
        self.executor = ProcessPoolExecutor(max_workers=MAX_AGENTS)
        self.active = {}

    async def run_agent(self, agent_code: str, task: str,
                        context: dict) -> dict:
        """Run agent in separate process."""
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            self.executor,
            _run_agent_process,
            agent_code,
            task,
            json.dumps(context),
        )
        try:
            result = await asyncio.wait_for(future, timeout=AGENT_TIMEOUT)
            return result
        except asyncio.TimeoutError:
            return {"error": f"Agent timed out after {AGENT_TIMEOUT}s"}

    async def run_loop(self, session_id: str, messages: list[dict],
                       on_tool_call=None, on_permission=None) -> str:
        """Main agent loop: send to LLM, execute tools, repeat."""
        tools_schema = self.llm.build_tools_schema(TOOLS)
        conversation = list(messages)

        while True:
            # Call LLM
            result = await self.llm.chat(conversation, tools=tools_schema)
            choice = result.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # If no tool calls, return final answer
            if not tool_calls:
                return content

            # Add assistant message to conversation
            conversation.append(message)

            # Execute each tool call
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                args_str = func.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {}

                # Permission check
                tier = get_tool_tier(tool_name)
                target = args.get("path", args.get("url", args.get("command", "")))

                if tier == "dangerous":
                    decision = "denied"
                    if on_permission:
                        decision = await on_permission(tool_name, target, tier)
                    if decision != "approved":
                        tool_result = {"error": f"Denied: {tool_name}"}
                        conversation.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": json.dumps(tool_result),
                        })
                        continue

                if tier in ("moderate", "sensitive"):
                    if not should_auto_allow(tool_name, target):
                        decision = "denied"
                        if on_permission:
                            decision = await on_permission(tool_name, target, tier)
                        if decision != "approved":
                            tool_result = {"error": f"Denied: {tool_name}"}
                            conversation.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", ""),
                                "content": json.dumps(tool_result),
                            })
                            continue

                # Execute tool
                if on_tool_call:
                    await on_tool_call(tool_name, args)

                result = await execute_tool(tool_name, **args)

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result),
                })

    def shutdown(self):
        """Shutdown process pool."""
        self.executor.shutdown(wait=False)
