"""
HIVE — Dashboard Events (SSE Live Stream)
Live event stream for the dashboard visualization.

Emits events as Server-Sent Events (SSE) so the dashboard can show:
- Live agent status updates
- Message flow between agents
- Task progress
- Budget changes
- Creation/deletion events
- Debate progress
- Emotional state changes

This is what makes the dashboard CINEMA — judges watch the hive work in real time.
"""

import asyncio
import json
import logging
import time
from typing import Optional
from dataclasses import asdict
from collections import defaultdict

from core.message_bus import MessageBus, get_bus
from core.agent_state import get_all_states
from core.economy import economy
from core.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class DashboardEvent:
    """A single dashboard event."""

    def __init__(self, event_type: str, data: dict, agent_id: str = "system"):
        self.event_type = event_type
        self.data = data
        self.agent_id = agent_id
        self.timestamp = time.time()
        self.event_id = f"{int(self.timestamp * 1000)}"

    def to_sse(self) -> str:
        """Convert to SSE format for /events endpoint."""
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "data": self.data,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }


class DashboardEventStream:
    """
    Manages the live event stream for the dashboard.
    Agents publish events here. The dashboard subscribes via SSE.

    Event types:
    - agent_state_update: Agent emotional/basic state changed
    - message_sent: Agent sent a message
    - task_started: Task began execution
    - task_completed: Task finished
    - task_blocked: Task blocked by safety/debate
    - agent_created: New agent spawned
    - agent_deleted: Agent removed
    - debate_started: 4-round debate started
    - debate_round: Debate round completed
    - debate_completed: Debate finished with verdict
    - budget_changed: Credits spent/refunded
    - hive_status: Full hive status snapshot
    - alert: Important event requiring attention
    - artifact_created: New artifact (chart, report, etc.)
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []
        self._event_history: list[DashboardEvent] = []  # Last 500 events
        self._max_history = 500
        self._alert_queue: list[DashboardEvent] = []  # Unread alerts

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to the event stream. Returns a queue."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        """Unsubscribe a queue."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event_type: str, data: dict, agent_id: str = "system"):
        """Publish an event to all subscribers."""
        event = DashboardEvent(event_type, data, agent_id)

        # Add to history
        if len(self._event_history) >= self._max_history:
            self._event_history.pop(0)
        self._event_history.append(event)

        # Push to all subscribers
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

        # Alert queue for important events
        if event_type in ("alert", "debate_completed", "agent_created", "task_blocked"):
            self._alert_queue.append(event)

    def get_recent(self, count: int = 50) -> list[dict]:
        """Get the N most recent events."""
        return [e.to_dict() for e in self._event_history[-count:]]

    def get_alerts(self) -> list[dict]:
        """Get unread alerts."""
        alerts = self._alert_queue.copy()
        self._alert_queue.clear()
        return [a.to_dict() for a in alerts]

    def message_count(self) -> int:
        return len(self._event_history)


# Singleton
_event_stream: Optional[DashboardEventStream] = None


def get_event_stream() -> DashboardEventStream:
    global _event_stream
    if _event_stream is None:
        _event_stream = DashboardEventStream()
    return _event_stream


# ─── Event helpers ───────────────────────────────────────────────────────────

def emit_agent_state(agent_id: str, state_data: dict):
    """Emit an agent state update."""
    get_event_stream().publish("agent_state_update", {
        "agent_id": agent_id,
        "state": state_data,
    })


def emit_task_started(task_id: str, task: str, agents: list[str]):
    """Emit task started."""
    get_event_stream().publish("task_started", {
        "task_id": task_id,
        "task": task,
        "agents_assigned": agents,
        "budget_before": economy.budget.available,
    })


def emit_task_completed(
    task_id: str,
    agents: list[str],
    synthesis: str,
    total_cost: int,
    debate_verdict: str = None,
    concerns: list[str] = None,
    leader_mood: str = None,
):
    """Emit task completed."""
    get_event_stream().publish("task_completed", {
        "task_id": task_id,
        "agents_used": agents,
        "synthesis_preview": synthesis[:200] if synthesis else "",
        "total_cost": total_cost,
        "budget_remaining": economy.budget.available,
        "debate_verdict": debate_verdict,
        "concerns_raised": concerns or [],
        "leader_mood": leader_mood or "calm",
    })


def emit_debate_started(task: str):
    """Emit debate started."""
    get_event_stream().publish("debate_started", {
        "task_preview": task[:100],
        "timestamp": time.time(),
    })


def emit_debate_round(round_num: int, findings: dict):
    """Emit debate round completed."""
    get_event_stream().publish(f"debate_round_{round_num}", {
        "round": round_num,
        "findings_count": len(findings),
    })


def emit_debate_completed(verdict: str, confidence: float, reasoning: str, duration_ms: float):
    """Emit debate completed with verdict."""
    get_event_stream().publish("debate_completed", {
        "verdict": verdict,
        "confidence": confidence,
        "reasoning_preview": reasoning[:200] if reasoning else "",
        "duration_ms": duration_ms,
        "timestamp": time.time(),
    })

    if verdict == "reject":
        get_event_stream().publish("alert", {
            "type": "danger",
            "message": f"Debate rejected action (confidence: {confidence:.0%})",
            "reason": reasoning[:200],
        }, "judge")


def emit_budget_change(agent_id: str, amount: int, reason: str, new_balance: int):
    """Emit budget change."""
    get_event_stream().publish("budget_changed", {
        "agent_id": agent_id,
        "amount": amount,
        "reason": reason,
        "new_balance": new_balance,
        "timestamp": time.time(),
    })


def emit_agent_created(agent_id: str, name: str, purpose: str):
    """Emit agent created."""
    get_event_stream().publish("agent_created", {
        "agent_id": agent_id,
        "name": name,
        "purpose": purpose,
        "timestamp": time.time(),
    })

    get_event_stream().publish("alert", {
        "type": "success",
        "message": f"New agent spawned: {name}",
    }, "agent_forge")


def emit_agent_deleted(agent_id: str, reason: str):
    """Emit agent deleted."""
    get_event_stream().publish("agent_deleted", {
        "agent_id": agent_id,
        "reason": reason,
        "timestamp": time.time(),
    })


def emit_task_blocked(task_id: str, blocked_by: str, reason: str):
    """Emit task blocked."""
    get_event_stream().publish("task_blocked", {
        "task_id": task_id,
        "blocked_by": blocked_by,
        "reason": reason,
        "timestamp": time.time(),
    })

    get_event_stream().publish("alert", {
        "type": "warning",
        "message": f"Task blocked by {blocked_by}",
        "reason": reason,
    }, "safety_agent")


def emit_hive_status_snapshot():
    """Emit full hive status for dashboard polling."""
    states = get_all_states()
    econ = economy.summary()

    emotion_counts = defaultdict(int)
    for s in states.values():
        emotion_counts[s.get("emotional_state", "unknown")] += 1

    get_event_stream().publish("hive_status", {
        "total_agents": len(states),
        "emotion_breakdown": dict(emotion_counts),
        "budget_total": econ["budget_total"],
        "budget_spent": econ["budget_spent"],
        "budget_available": econ["budget_available"],
        "timestamp": time.time(),
    })


def emit_artifact(artifact_type: str, path: str, description: str):
    """Emit artifact created (chart, report, etc.)."""
    get_event_stream().publish("artifact_created", {
        "type": artifact_type,
        "path": path,
        "description": description,
        "timestamp": time.time(),
    })


# ─── FastAPI SSE endpoint ──────────────────────────────────────────────────

async def sse_events():
    """
    Generator for SSE stream. Use with FastAPI:

    @app.get("/events")
    async def events():
        return EventSourceResponse(sse_events())

    """
    queue = get_event_stream().subscribe()
    try:
        while True:
            event = await queue.get()
            yield event.to_sse()
    except GeneratorExit:
        get_event_stream().unsubscribe(queue)