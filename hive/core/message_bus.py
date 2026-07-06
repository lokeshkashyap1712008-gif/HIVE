"""
HIVE — Inter-Agent Message Bus
Async communication layer for agent-to-agent messaging.
"""

import time
import uuid
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    TASK = "task"
    RESPONSE = "response"
    DEBATE = "debate"
    CHALLENGE = "challenge"
    HEARTBEAT = "heartbeat"
    ESCALATE = "escalate"
    APPROVE = "approve"
    REJECT = "reject"


@dataclass
class Message:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    from_agent: str = ""
    to_agent: str = ""
    msg_type: MessageType = MessageType.TASK
    content: str = ""
    thread_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    references: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.msg_type.value,
            "content": self.content,
            "thread_id": self.thread_id,
            "timestamp": self.timestamp,
            "references": self.references,
        }


class MessageBus:
    def __init__(self, max_history: int = 1000):
        self._agents: dict = {}
        self._inbox: dict = defaultdict(list)
        self._history: list = []
        self._max_history = max_history

    def register_agent(self, agent_id: str, role: str = ""):
        self._agents[agent_id] = role

    def unregister_agent(self, agent_id: str):
        self._agents.pop(agent_id, None)
        self._inbox.pop(agent_id, None)

    def send_message(self, from_agent: str, to_agent: str, content: str,
                     msg_type: MessageType = MessageType.TASK,
                     thread_id: Optional[str] = None,
                     references: Optional[list] = None) -> str:
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=msg_type,
            content=content,
            thread_id=thread_id or str(uuid.uuid4())[:8],
            references=references or [],
        )

        self._history.append(msg)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        if to_agent:
            self._inbox[to_agent].append(msg)
        else:
            for agent_id in self._agents:
                if agent_id != from_agent:
                    self._inbox[agent_id].append(msg)

        return msg.id

    def get_messages(self, agent_id: str, clear: bool = False) -> list:
        messages = list(self._inbox.get(agent_id, []))
        if clear:
            self._inbox[agent_id] = []
        return messages

    def get_thread(self, thread_id: str) -> list:
        return [m for m in self._history if m.thread_id == thread_id]

    def broadcast(self, from_agent: str, content: str, msg_type: MessageType = MessageType.TASK) -> str:
        return self.send_message(from_agent, "", content, msg_type)

    def publish(self, topic: str, event_type: str, data: dict) -> str:
        content = f"{event_type}: {json.dumps(data)}" if isinstance(data, dict) else f"{event_type}: {data}"
        return self.send_message(topic, "", content, MessageType.TASK)

    def challenge(self, from_agent: str, to_agent: str, claim: str, evidence: str) -> str:
        content = f"CHALLENGE\nClaim: {claim}\nEvidence: {evidence}"
        return self.send_message(from_agent, to_agent, content, MessageType.CHALLENGE)

    def heartbeat(self, agent_id: str) -> str:
        return self.send_message(agent_id, "leader", "alive", MessageType.HEARTBEAT)

    def list_agents(self) -> dict:
        return dict(self._agents)

    def message_count(self) -> int:
        return len(self._history)

    def type_counts(self) -> dict:
        counts = defaultdict(int)
        for msg in self._history:
            counts[msg.msg_type.value] += 1
        return dict(counts)


_bus: Optional[MessageBus] = None


def get_bus() -> MessageBus:
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus
