"""
HIVE — Cleanup Crew (Undertaker Bees)
NOT just "delete agents." An intelligent garbage collection system.
"""

import time
import logging
import os
import json
from dataclasses import dataclass
from typing import Optional

from hive.core.agent_state import agent_registry, get_or_create_state
from hive.core.economy import economy, COSTS
from hive.core.message_bus import get_bus
from hive.core.audit_logger import audit_logger

logger = logging.getLogger(__name__)

ARCHIVE_DIR = os.path.join(os.path.expanduser("~"), ".hive", "archives")
os.makedirs(ARCHIVE_DIR, exist_ok=True)

IDLE_THRESHOLD_SECONDS = 300
MEMORY_PRESSURE_THRESHOLD = 0.80
ORPHAN_THRESHOLD_SECONDS = 600
TEMP_AGENT_LIFETIME_SECONDS = 1800


@dataclass
class CleanupDecision:
    agent_id: str
    action: str
    reason: str
    memory_freed_mb: int = 0
    cost_saved: int = 0
    data_archived: bool = False


class CleanupCrew:
    def __init__(self):
        self.cleanup_history: list[CleanupDecision] = []
        self.last_full_scan = 0

    def scan_idle_agents(self) -> list[CleanupDecision]:
        decisions = []
        now = time.time()
        memory_usage = self._get_memory_usage()

        for agent_id, state in list(agent_registry.items()):
            if agent_id in ("leader", "agent_forge", "cleanup_crew", "judge", "safety_agent"):
                continue

            is_idle = (
                state.workload < 0.05 and
                (now - state.last_update) > IDLE_THRESHOLD_SECONDS
            )
            is_orphan = (
                state.tasks_completed > 0 and
                (now - state.last_update) > ORPHAN_THRESHOLD_SECONDS
            )
            memory_critical = memory_usage > MEMORY_PRESSURE_THRESHOLD

            if is_idle or is_orphan or memory_critical:
                if memory_critical and state.workload > 0.1:
                    continue
                decision = self._evaluate_cleanup(agent_id, state, is_idle, is_orphan, memory_critical)
                decisions.append(decision)

        self.cleanup_history.extend(decisions)
        return decisions

    def _evaluate_cleanup(self, agent_id: str, state, is_idle: bool, is_orphan: bool, memory_critical: bool) -> CleanupDecision:
        has_useful_results = state.tasks_completed > 0 and state.reputation > 0.5

        from hive.agents.agent_forge import temporary_agents
        is_temp = agent_id in temporary_agents
        is_old_temp = is_temp and (time.time() - state.last_update) > TEMP_AGENT_LIFETIME_SECONDS

        if is_old_temp:
            action = "archive_and_delete"
            reason = f"Temporary agent {agent_id} exceeded lifetime"
            cost_saved = COSTS["deletion_event"]
        elif is_orphan and is_idle and not has_useful_results:
            action = "delete"
            reason = f"Agent {agent_id} is orphan with no useful results"
            cost_saved = COSTS["deletion_event"]
        elif is_orphan and is_idle and has_useful_results:
            action = "archive_and_keep"
            reason = f"Agent {agent_id} is orphan but has useful results — archiving"
            cost_saved = 0
        elif memory_critical:
            action = "archive_and_delete"
            reason = f"Memory pressure: forcing cleanup of {agent_id}"
            cost_saved = COSTS["deletion_event"]
        else:
            action = "keep"
            reason = f"Agent {agent_id} has active context, keeping"
            cost_saved = 0

        memory_freed = self._estimate_memory_freed(agent_id, state)
        return CleanupDecision(
            agent_id=agent_id,
            action=action,
            reason=reason,
            memory_freed_mb=memory_freed,
            cost_saved=cost_saved,
            data_archived=(action in ("archive_and_keep", "archive_and_delete")),
        )

    def _get_memory_usage(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().percent / 100.0
        except ImportError:
            return 0.5

    def _estimate_memory_freed(self, agent_id: str, state) -> int:
        return 50 + state.tasks_completed * 10

    def archive_agent(self, agent_id: str, state) -> Optional[str]:
        archive_id = f"{agent_id}_{int(time.time())}"
        archive_path = os.path.join(ARCHIVE_DIR, f"{archive_id}.json")

        emo_val = state.emotional_state.value if hasattr(state.emotional_state, 'value') else str(state.emotional_state)

        archive_data = {
            "agent_id": agent_id,
            "archived_at": time.time(),
            "tasks_completed": state.tasks_completed,
            "tasks_failed": state.tasks_failed,
            "reputation": state.reputation,
            "accuracy_rate": state.accuracy_rate(),
            "emotional_state": emo_val,
            "last_update": state.last_update,
        }

        try:
            with open(archive_path, "w") as f:
                json.dump(archive_data, f, indent=2)
            return archive_path
        except Exception as e:
            logger.warning(f"[Cleanup] Archive failed: {e}")
            return None

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id in agent_registry:
            del agent_registry[agent_id]

        from hive.agents.agent_forge import temporary_agents, AGENT_REGISTRY
        if agent_id in temporary_agents:
            del temporary_agents[agent_id]
        if agent_id in AGENT_REGISTRY:
            del AGENT_REGISTRY[agent_id]

        bus = get_bus()
        bus.publish("hive", "deletion_event", {"agent_id": agent_id, "at": time.time()})

        audit_logger.log(
            decision_type="AGENT_DELETED",
            reason=f"Cleanup: deleted agent {agent_id}",
            metadata={"agent_id": agent_id},
        )
        logger.info(f"[Cleanup] Deleted agent: {agent_id}")
        return True

    def execute_decisions(self, decisions: list[CleanupDecision]) -> dict:
        results = []
        total_memory_freed = 0
        total_cost_saved = 0
        archived_count = 0
        deleted_count = 0

        for decision in decisions:
            if decision.action == "keep":
                continue

            state = get_or_create_state(decision.agent_id)

            if decision.data_archived:
                path = self.archive_agent(decision.agent_id, state)
                if path:
                    archived_count += 1

            if decision.action in ("archive_and_delete", "delete"):
                self.delete_agent(decision.agent_id)
                deleted_count += 1

            total_memory_freed += decision.memory_freed_mb
            total_cost_saved += decision.cost_saved
            results.append({
                "agent_id": decision.agent_id,
                "action": decision.action,
                "reason": decision.reason,
                "memory_freed_mb": decision.memory_freed_mb,
            })

        return {
            "decisions_executed": len(results),
            "agents_archived": archived_count,
            "agents_deleted": deleted_count,
            "total_memory_freed_mb": total_memory_freed,
            "total_cost_saved": total_cost_saved,
            "details": results,
        }

    def run_full_cleanup(self) -> dict:
        decisions = self.scan_idle_agents()
        result = self.execute_decisions(decisions)
        result["decisions_total"] = len(decisions)
        self.last_full_scan = time.time()
        return result

    def get_cleanup_status(self) -> dict:
        memory_usage = self._get_memory_usage()
        total_agents = len(agent_registry)
        idle_count = sum(
            1 for s in agent_registry.values()
            if s.workload < 0.05 and (time.time() - s.last_update) > IDLE_THRESHOLD_SECONDS
        )
        return {
            "memory_pressure": round(memory_usage * 100, 1),
            "total_agents": total_agents,
            "idle_agents": idle_count,
            "cleanup_history_count": len(self.cleanup_history),
            "cleanup_aggressive": memory_usage > MEMORY_PRESSURE_THRESHOLD,
            "last_full_scan": self.last_full_scan,
        }

    def _get_archive_size(self) -> float:
        try:
            total = 0
            for f in os.listdir(ARCHIVE_DIR):
                fp = os.path.join(ARCHIVE_DIR, f)
                if os.path.isfile(fp):
                    total += os.path.getsize(fp)
            return round(total / (1024 * 1024), 2)
        except Exception:
            return 0.0


cleanup_crew = CleanupCrew()


async def run(task: str = "cleanup_scan") -> dict:
    if "status" in task.lower() or "scan" in task.lower():
        return cleanup_crew.run_full_cleanup()
    else:
        return cleanup_crew.get_cleanup_status()
