"""
HIVE — Memory Manager
Tracks active agents, monitors RAM/VRAM, auto-adjusts spawn counts
"""

import asyncio
import logging
import time
import psutil
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    agent_id: str
    agent_type: str
    task_id: str
    spawned_at: float
    status: str = "running"  # running | stalled | finished
    memory_mb: float = 0.0
    failures: int = 0
    last_ping: float = 0.0


class MemoryManager:
    """
    Tracks all active agents.
    Provides RAM/VRAM monitoring and auto-spawn adjustment.
    """

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._lock = asyncio.Lock()
        self._nvidia_smi_cache = None
        self._nvidia_cache_time = 0

    # ── Agent registry ───────────────────────────────────────────────────────

    async def register(self, agent_id: str, agent_type: str, task_id: str) -> AgentInfo:
        async with self._lock:
            info = AgentInfo(
                agent_id=agent_id,
                agent_type=agent_type,
                task_id=task_id,
                spawned_at=time.time(),
                last_ping=time.time(),
            )
            self._agents[agent_id] = info
            logger.info(f"[MemoryManager] Registered agent {agent_id} ({agent_type})")
            return info

    async def unregister(self, agent_id: str):
        async with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                logger.info(f"[MemoryManager] Unregistered agent {agent_id}")

    async def ping(self, agent_id: str):
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].last_ping = time.time()

    async def mark_stalled(self, agent_id: str):
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].status = "stalled"
                self._agents[agent_id].failures += 1
                logger.warning(f"[MemoryManager] Agent {agent_id} marked STALLED (failures={self._agents[agent_id].failures})")

    async def get_stale_agents(self, max_age_seconds: int = 60) -> list[str]:
        """Return agent_ids that haven't pinged in max_age_seconds."""
        now = time.time()
        async with self._lock:
            return [
                aid for aid, info in self._agents.items()
                if (now - info.last_ping) > max_age_seconds and info.status == "running"
            ]

    def get_stalled_agents(self, max_failures: int = 3) -> list[str]:
        return [
            aid for aid, info in self._agents.items()
            if info.failures >= max_failures
        ]

    def list_agents(self) -> list[dict]:
        return [
            {
                "agent_id": info.agent_id,
                "agent_type": info.agent_type,
                "task_id": info.task_id,
                "status": info.status,
                "uptime_seconds": time.time() - info.spawned_at,
                "failures": info.failures,
            }
            for info in self._agents.values()
        ]

    def get_agent(self, agent_id: str) -> Optional[dict]:
        info = self._agents.get(agent_id)
        if not info:
            return None
        return {
            "agent_id": info.agent_id,
            "agent_type": info.agent_type,
            "task_id": info.task_id,
            "status": info.status,
            "uptime_seconds": time.time() - info.spawned_at,
            "failures": info.failures,
        }

    def active_agent_count(self) -> int:
        return len([a for a in self._agents.values() if a.status == "running"])

    async def kill_agent(self, agent_id: str) -> bool:
        async with self._lock:
            if agent_id in self._agents:
                self._agents[agent_id].status = "stalled"
                return True
        return False

    # ── Memory checks ────────────────────────────────────────────────────────

    def available_memory_mb(self) -> float:
        mem = psutil.virtual_memory()
        return mem.available / (1024 * 1024)

    def memory_percent(self) -> float:
        mem = psutil.virtual_memory()
        return mem.percent

    def total_memory_mb(self) -> float:
        mem = psutil.virtual_memory()
        return mem.total / (1024 * 1024)

    def recommended_max_agents(self) -> int:
        """Based on available RAM, return safe max concurrent agents."""
        free = self.available_memory_mb()
        if free < 500:
            return 1
        elif free < 1024:
            return 3
        elif free < 2048:
            return 5
        return 8

    # ── GPU monitoring ───────────────────────────────────────────────────────

    def gpu_utilization(self) -> Optional[float]:
        """Returns GPU utilization % or None if no GPU."""
        try:
            result = psutil.Process().cpu_percent(interval=0.1)
            # Fallback: try nvidia-smi directly
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    def gpu_temperature(self) -> Optional[float]:
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    def gpu_memory_mb(self) -> Optional[float]:
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True,
                timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    # ── Swarm health ─────────────────────────────────────────────────────────

    def swarm_health_score(self) -> int:
        """Composite health score 0-100."""
        score = 100
        free_mb = self.available_memory_mb()

        # Deduct for low memory
        if free_mb < 500:
            score -= 50
        elif free_mb < 1024:
            score -= 25
        elif free_mb < 2048:
            score -= 10

        # Deduct for stalled agents
        stalled = len(self.get_stalled_agents())
        score -= stalled * 15

        # Deduct for low GPU memory (if available)
        gpu_mem = self.gpu_memory_mb()
        if gpu_mem is not None and gpu_mem > 5000:
            score -= 20  # high VRAM usage

        return max(0, min(100, score))


# Singleton
memory_manager = MemoryManager()