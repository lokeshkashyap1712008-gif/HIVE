"""
HIVE — Inter-Agent Message Bus
Async communication layer for agent-to-agent messaging.
Every agent can send, receive, broadcast messages.
Messages are typed: task | response | debate | challenge | heartbeat
"""

import time
import uuid
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
    to_agent: str = ""       # "" means broadcast
    msg_type: MessageType = MessageType.TASK
    content: str = ""
    thread_id: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    references: list[str] = field(default_factory=list)  # referenced message ids

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
    """
    Inter-agent message bus.
    Agents register, then send/receive messages through the bus.
    """

    def __init__(self, max_history: int = 1000):
        self._agents: dict[str, str] = {}  # agent_id -> role
        self._inbox: dict[str, list[Message]] = defaultdict(list)
        self._history: list[Message] = []
        self._max_history = max_history
        self._lock = None  # We'll use simple list ops since Python GIL handles it

    def register_agent(self, agent_id: str, role: str = ""):
        """Register an agent with the bus."""
        self._agents[agent_id] = role
        logger.debug(f"[MessageBus] Registered: {agent_id} ({role})")

    def unregister_agent(self, agent_id: str):
        """Remove an agent from the bus."""
        self._agents.pop(agent_id, None)
        self._inbox.pop(agent_id, None)
        logger.debug(f"[MessageBus] Unregistered: {agent_id}")

    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: MessageType = MessageType.TASK,
        thread_id: Optional[str] = None,
        references: Optional[list[str]] = None,
    ) -> str:
        """
        Send a message from one agent to another (or broadcast if to_agent="").
        Returns the message id.
        """
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
            # Direct message
            self._inbox[to_agent].append(msg)
        else:
            # Broadcast to all registered agents
            for agent_id in self._agents:
                if agent_id != from_agent:
                    self._inbox[agent_id].append(msg)

        logger.debug(f"[MessageBus] {from_agent} → {to_agent or 'ALL'}: [{msg_type.value}] {content[:60]}")
        return msg.id

    def get_messages(self, agent_id: str, clear: bool = False) -> list[Message]:
        """
        Get all messages for an agent.
        If clear=True, messages are removed from inbox after reading.
        """
        messages = list(self._inbox.get(agent_id, []))
        if clear:
            self._inbox[agent_id] = []
        return messages

    def get_thread(self, thread_id: str) -> list[Message]:
        """Get all messages in a thread."""
        return [m for m in self._history if m.thread_id == thread_id]

    def broadcast(self, from_agent: str, content: str, msg_type: MessageType = MessageType.TASK) -> str:
        """Broadcast to all agents except sender."""
        return self.send_message(from_agent, "", content, msg_type)

    def challenge(self, from_agent: str, to_agent: str, claim: str, evidence: str) -> str:
        """Send a formal challenge to another agent's claim."""
        content = f"CHALLENGE\nClaim: {claim}\nEvidence: {evidence}"
        return self.send_message(from_agent, to_agent, content, MessageType.CHALLENGE)

    def respond_to_challenge(self, from_agent: str, to_agent: str, rebuttal: str, original_msg_id: str) -> str:
        """Respond to a challenge."""
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.RESPONSE,
            content=f"REBUTTAL: {rebuttal}",
            references=[original_msg_id],
        )
        self._inbox[to_agent].append(msg)
        self._history.append(msg)
        return msg.id

    def heartbeat(self, agent_id: str) -> str:
        """Send a heartbeat to show agent is alive."""
        return self.send_message(agent_id, "leader", "alive", MessageType.HEARTBEAT)

    def list_agents(self) -> dict[str, str]:
        """List all registered agents and their roles."""
        return dict(self._agents)

    def history_size(self) -> int:
        return len(self._history)

    def pending_count(self, agent_id: str) -> int:
        """Number of pending messages for an agent."""
        return len(self._inbox.get(agent_id, []))

    def message_count(self) -> int:
        return len(self._history)

    def type_counts(self) -> dict:
        counts = defaultdict(int)
        for msg in self._history:
            counts[msg.msg_type.value] += 1
        return dict(counts)


# Singleton instance
_bus: MessageBus = None


def get_bus() -> MessageBus:
    """Get the singleton MessageBus instance."""
    global _bus
    if _bus is None:
        _bus = MessageBus()
    return _bus


# Singleton instance
message_bus = MessageBus()