"""
HIVE — Agent Forge (Creator)
Dynamically spawns workers on demand.
Memory-aware: checks RAM before spawning, reduces agents if low.
"""

import asyncio
import uuid
import logging
from typing import Optional

from core.memory_manager import memory_manager
from core.task_queue import task_queue, SubTask, TaskStatus
from core.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class AgentForge:
    """
    The CREATOR in the HIVE hierarchy.
    Spawns worker agents dynamically based on task requirements.
    Respects memory constraints — won't spawn if RAM is critically low.
    """

    def __init__(self):
        self._spawn_lock = asyncio.Lock()
        self._active_forges: dict[str, asyncio.Task] = {}

    async def spawn(
        self,
        agent_type: str,
        task_id: str,
        subtask: SubTask,
        max_concurrent: int = 8,
    ) -> Optional[dict]:
        """
        Spawn a single worker agent.
        Returns agent info dict or None if memory is too low.
        """
        agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"

        # Memory check
        max_agents = memory_manager.recommended_max_agents()
        if memory_manager.active_agent_count() >= min(max_agents, max_concurrent):
            logger.warning(
                f"[AgentForge] Memory pressure: {memory_manager.active_agent_count()} active, "
                f"recommended max {max_agents}. Will queue task."
            )
            return None

        # Register in memory manager
        await memory_manager.register(agent_id, agent_type, task_id)
        task_queue.register_agent(task_id, agent_id)
        audit_logger.log("AGENT_SPAWNED", f"Spawned {agent_type} ({agent_id}) for task {task_id}")

        return {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "task_id": task_id,
            "subtask_id": subtask.id,
        }

    async def spawn_batch(
        self,
        tasks: list[dict],
        task_id: str,
        max_concurrent: int = 8,
    ) -> list[dict]:
        """
        Spawn multiple agents in parallel.
        Each task dict: { "agent_type": str, "subtask": SubTask }
        Returns list of spawned agent info dicts.
        """
        spawned = []

        # Check memory and cap concurrent spawns
        max_agents = min(
            memory_manager.recommended_max_agents(),
            max_concurrent,
        )
        current = memory_manager.active_agent_count()
        available = max(agents := max_agents - current, 0)

        if available <= 0:
            logger.warning(f"[AgentForge] No available agent slots. {current} active, max {max_agents}")
            return []

        # Limit to available slots
        tasks_to_spawn = tasks[:available]

        # Spawn in parallel (up to available slots)
        async def spawn_one(t: dict):
            return await self.spawn(
                agent_type=t["agent_type"],
                task_id=task_id,
                subtask=t["subtask"],
                max_concurrent=max_concurrent,
            )

        results = await asyncio.gather(*[spawn_one(t) for t in tasks_to_spawn], return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[AgentForge] Spawn error: {r}")
            elif r:
                spawned.append(r)

        logger.info(f"[AgentForge] Spawned {len(spawned)}/{len(tasks)} agents (memory-constrained: {available})")
        return spawned

    async def terminate(self, agent_id: str):
        """Terminate a specific agent."""
        await memory_manager.unregister(agent_id)
        audit_logger.log("AGENT_TERMINATED", f"Terminated agent {agent_id}")

    def get_active_count(self) -> int:
        return memory_manager.active_agent_count()


agent_forge = AgentForge()