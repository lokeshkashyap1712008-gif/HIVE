"""
HIVE — Agent State & Emotions
Every agent has emotional state: confidence, stress, load, trust.
This is what makes the society feel ALIVE.

Key insight: Agents don't just return "Done."
They return confidence levels, emotional state, and next-step suggestions.
The Leader reasons about ALL of this, not just the output.

Emotions aren't human — they're operational states:
- High stress → agent requests help
- Low confidence → agent requests verification
- High load → agent declines new tasks
- Low trust in another agent → seeks independent confirmation
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class EmotionalState(str, Enum):
    CONFIDENT = "confident"
    CAUTIOUS = "cautious"
    UNCERTAIN = "uncertain"
    STRESSED = "stressed"
    OVERLOADED = "overloaded"
    CALM = "calm"
    ALARMED = "alarmed"


@dataclass
class AgentState:
    """Complete emotional/operational state for one agent."""

    agent_id: str

    # Core metrics (all 0.0-1.0)
    confidence: float = 0.75        # How sure is this agent in current work?
    trust_in_leader: float = 0.9   # Does this agent trust the Queen's decisions?
    trust_in_society: float = 0.8  # General trust in other agents
    stress_level: float = 0.1     # How stressed is this agent? (0=none, 1=max)
    workload: float = 0.0          # How busy is this agent? (0=idle, 1=maxed)
    reputation: float = 0.7        # Historical accuracy rate (0-1)

    # Derived
    emotional_state: EmotionalState = EmotionalState.CALM
    last_update: float = field(default_factory=time.time)

    # History for tracking trends
    confidence_history: list[float] = field(default_factory=list)
    stress_history: list[float] = field(default_factory=list)
    tasks_completed: int = 0
    tasks_failed: int = 0

    # Emotional signals
    expressed_doubt: bool = False   # Did this agent express uncertainty last result?
    requested_help: bool = False    # Did this agent ask for help?
    flagged_concern: bool = False   # Did this agent raise a safety concern?

    # Response formatting
    def update(self, confidence: Optional[float] = None, stress_delta: float = 0.0,
               workload_delta: float = 0.0):
        """Update state based on new information."""
        now = time.time()

        if confidence is not None:
            self.confidence = confidence
            self.confidence_history.append(confidence)
            if len(self.confidence_history) > 50:
                self.confidence_history.pop(0)

        self.stress_level = max(0.0, min(1.0, self.stress_level + stress_delta))
        self.stress_history.append(self.stress_level)
        if len(self.stress_history) > 50:
            self.stress_history.pop(0)

        self.workload = max(0.0, min(1.0, self.workload + workload_delta))
        self.last_update = now
        self._derive_emotional_state()

    def _derive_emotional_state(self):
        """Derive emotional state from core metrics."""
        if self.stress_level > 0.8:
            self.emotional_state = EmotionalState.STRESSED
        elif self.stress_level > 0.5:
            self.emotional_state = EmotionalState.CAUTIOUS
        elif self.confidence < 0.4:
            self.emotional_state = EmotionalState.UNCERTAIN
        elif self.workload > 0.9:
            self.emotional_state = EmotionalState.OVERLOADED
        elif self.confidence > 0.8 and self.stress_level < 0.3:
            self.emotional_state = EmotionalState.CONFIDENT
        else:
            self.emotional_state = EmotionalState.CALM

    def task_started(self):
        """Agent picked up a new task."""
        self.workload = min(1.0, self.workload + 0.1)

    def task_completed(self, success: bool = True):
        """Agent finished a task."""
        self.workload = max(0.0, self.workload - 0.1)
        if success:
            self.tasks_completed += 1
            self.stress_level = max(0.0, self.stress_level - 0.05)
            self.confidence = min(1.0, self.confidence + 0.02)
        else:
            self.tasks_failed += 1
            self.stress_level = min(1.0, self.stress_level + 0.1)
            self.confidence = max(0.0, self.confidence - 0.05)
        self._derive_emotional_state()

    def needs_help(self) -> bool:
        """Does this agent need help? High stress or low confidence."""
        return (self.stress_level > 0.7 or
                self.confidence < 0.4 or
                self.workload > 0.95)

    def should_verify(self) -> bool:
        """Should this agent's work be verified by another?"""
        return self.confidence < 0.7 or self.reputation < 0.6

    def trust_level(self, other_agent_id: str) -> float:
        """How much does this agent trust another specific agent?"""
        # Baseline trust in society, adjusted by their reputation
        base = self.trust_in_society
        if other_agent_id in agent_registry:
            other_rep = agent_registry[other_agent_id].reputation
            base = (base + other_rep) / 2
        return base

    def accuracy_rate(self) -> float:
        """Historical accuracy based on completed tasks."""
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 0.7  # Default for new agents
        return self.tasks_completed / total

    def update_reputation(self, was_correct: bool):
        """Update reputation based on whether this agent was right."""
        # Exponential moving average
        alpha = 0.2  # How much to weight new evidence
        new_acc = 1.0 if was_correct else 0.0
        self.reputation = (1 - alpha) * self.reputation + alpha * new_acc
        self.tasks_completed += 1 if was_correct else 0
        self.tasks_failed += 0 if was_correct else 1

    def to_result_dict(self, task_id: str = "") -> dict:
        """Convert state to a result dict with confidence + emotional signals."""
        return {
            "agent_id": self.agent_id,
            "confidence": round(self.confidence, 2),
            "confidence_label": self._confidence_label(),
            "emotional_state": self.emotional_state.value,
            "stress_level": round(self.stress_level, 2),
            "workload": round(self.workload, 2),
            "reputation": round(self.reputation, 2),
            "accuracy_rate": round(self.accuracy_rate(), 3),
            "needs_help": self.needs_help(),
            "should_verify": self.should_verify(),
            "expressed_doubt": self.expressed_doubt,
            "requested_help": self.requested_help,
            "flagged_concern": self.flagged_concern,
            "suggested_helper": self._suggested_helper(),
            "reason": self._reason_string(),
            "mood": self._mood_string(),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
        }

    def _confidence_label(self) -> str:
        if self.confidence >= 0.9:
            return "certain"
        elif self.confidence >= 0.75:
            return "confident"
        elif self.confidence >= 0.5:
            return "moderate"
        elif self.confidence >= 0.3:
            return "uncertain"
        else:
            return "doubtful"

    def _reason_string(self) -> str:
        """Why does this agent feel this way?"""
        if self.emotional_state == EmotionalState.CONFIDENT:
            return f"Based on {self.tasks_completed} successful tasks. Accuracy: {self.accuracy_rate():.0%}."
        elif self.emotional_state == EmotionalState.UNCERTAIN:
            return "Evidence is mixed or insufficient. Need more information."
        elif self.emotional_state == EmotionalState.STRESSED:
            return f"Under pressure. {self.workload:.0%} load. May be missing something."
        elif self.emotional_state == EmotionalState.OVERLOADED:
            return f"Workload at {self.workload:.0%}. Cannot take more tasks right now."
        elif self.emotional_state == EmotionalState.CAUTIOUS:
            return "Something doesn't add up. Proceeding carefully."
        else:
            return "Normal operation. Proceeding as planned."

    def _suggested_helper(self) -> Optional[str]:
        """Who should this agent suggest for verification/help?"""
        if self.should_verify():
            # High-rep agents for verification
            candidates = [
                (aid, state)
                for aid, state in agent_registry.items()
                if aid != self.agent_id and state.reputation > 0.75
            ]
            if candidates:
                best = max(candidates, key=lambda x: x[1].reputation)
                return best[0]
        if self.needs_help():
            return "leader"
        return None

    def _mood_string(self) -> str:
        """One-word mood indicator for dashboard."""
        mood_map = {
            EmotionalState.CONFIDENT: "confident",
            EmotionalState.CAUTIOUS: "cautious",
            EmotionalState.UNCERTAIN: "unsure",
            EmotionalState.STRESSED: "stressed",
            EmotionalState.OVERLOADED: "swamped",
            EmotionalState.CALM: "calm",
            EmotionalState.ALARMED: "alarmed",
        }
        return mood_map.get(self.emotional_state, "calm")

    def reset_flags(self):
        """Reset per-task flags after result is delivered."""
        self.expressed_doubt = False
        self.requested_help = False
        self.flagged_concern = False


# Global registry of all agent states
agent_registry: dict[str, AgentState] = {}


def get_or_create_state(agent_id: str) -> AgentState:
    """Get or create state for an agent."""
    if agent_id not in agent_registry:
        agent_registry[agent_id] = AgentState(agent_id=agent_id)
    return agent_registry[agent_id]


def get_all_states() -> dict[str, dict]:
    """Get all agent states for dashboard."""
    return {aid: state.to_result_dict() for aid, state in agent_registry.items()}


def update_state(agent_id: str, **kwargs) -> AgentState:
    """Update an agent's state."""
    state = get_or_create_state(agent_id)
    state.update(**kwargs)
    return state


def task_result_to_state(result: dict) -> dict:
    """
    Convert any agent result dict into a state-inclusive result.
    Call this BEFORE returning any agent result to add emotional context.
    """
    agent_id = result.get("agent_id", "unknown")
    state = get_or_create_state(agent_id)

    # Update from result
    conf = result.get("confidence")
    if conf is not None:
        state.confidence = conf

    if result.get("status") == "error":
        state.stress_level = min(1.0, state.stress_level + 0.1)
        state.expressed_doubt = True

    state.task_completed(success=(result.get("status") != "error"))

    # Add state info to result
    result.update(state.to_result_dict())
    result["state_snapshot"] = state.to_result_dict()

    return result