"""
HIVE — Cleanup Crew (Deletor)
Runs every 30 seconds, kills zombie agents, frees memory.
Cannot delete: Leader, Agent Forge, or itself.
"""

import asyncio
import logging

from core.memory_manager import memory_manager
from core.audit_logger import audit_logger
from core.task_queue import TaskStatus

logger = logging.getLogger(__name__)


class CleanupCrew:
    """
    The DELETOR in the HIVE hierarchy.
    Periodically scans for zombie/stalled agents and removes them.
    Enforces the 3-failure kill rule.
    """

    def __init__(self):
        self._protected = {"hive_core", "agent_forge", "cleanup_crew"}

    async def run(self) -> int:
        """
        Run one cleanup cycle.
        Returns number of agents cleaned up.
        """
        cleaned = 0

        # Find stalled agents (3+ failures)
        for agent_id in memory_manager.get_stalled_agents(max_failures=3):
            if self._can_delete(agent_id):
                await self._kill(agent_id, reason="3 failures")
                cleaned += 1

        # Find non-responsive agents (no ping in 60s)
        for agent_id in await memory_manager.get_stale_agents(max_age_seconds=60):
            if self._can_delete(agent_id):
                await self._kill(agent_id, reason="no heartbeat")
                cleaned += 1

        if cleaned > 0:
            logger.info(f"[CleanupCrew] Removed {cleaned} zombie agents")

        return cleaned

    def _can_delete(self, agent_id: str) -> bool:
        """Agents that cannot be deleted by Cleanup Crew."""
        # Can't delete protected agents
        for protected in self._protected:
            if protected in agent_id.lower():
                return False
        return True

    async def _kill(self, agent_id: str, reason: str):
        """Kill an agent and log it."""
        await memory_manager.unregister(agent_id)
        audit_logger.log("AGENT_KILLED", f"Cleanup Crew killed {agent_id}: {reason}", agents_affected=[agent_id])
        logger.info(f"[CleanupCrew] Killed {agent_id} ({reason})")