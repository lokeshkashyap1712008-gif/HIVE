"""
HIVE — Memory Manager
Tracks active agents, monitors RAM, auto-adjusts spawn counts
"""

import logging
import time
import psutil
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    agent_id: str
    agent_type: str
    task_id: str
    spawned_at: float
    status: str = "running"
    memory_mb: float = 0.0
    failures: int = 0
    last_ping: float = 0.0


class MemoryManager:
    def __init__(self):
        self._agents: dict = {}

    async def register(self, agent_id: str, agent_type: str, task_id: str) -> AgentInfo:
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
        if agent_id in self._agents:
            del self._agents[agent_id]

    async def ping(self, agent_id: str):
        if agent_id in self._agents:
            self._agents[agent_id].last_ping = time.time()

    def get_stale_agents(self, max_age_seconds: int = 60) -> list:
        now = time.time()
        return [
            aid for aid, info in self._agents.items()
            if (now - info.last_ping) > max_age_seconds and info.status == "running"
        ]

    def get_stalled_agents(self, max_failures: int = 3) -> list:
        return [
            aid for aid, info in self._agents.items()
            if info.failures >= max_failures
        ]

    def list_agents(self) -> list:
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
        if agent_id in self._agents:
            self._agents[agent_id].status = "stalled"
            return True
        return False

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
        free = self.available_memory_mb()
        if free < 500:
            return 1
        elif free < 1024:
            return 3
        elif free < 2048:
            return 5
        return 8

    def gpu_utilization(self) -> Optional[float]:
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                text=True, timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    def gpu_temperature(self) -> Optional[float]:
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                text=True, timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    def gpu_memory_mb(self) -> Optional[float]:
        try:
            import subprocess
            output = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True, timeout=5,
            )
            return float(output.strip().split("\n")[0])
        except Exception:
            return None

    def swarm_health_score(self) -> int:
        score = 100
        free_mb = self.available_memory_mb()
        if free_mb < 500:
            score -= 50
        elif free_mb < 1024:
            score -= 25
        elif free_mb < 2048:
            score -= 10

        stalled = len(self.get_stalled_agents())
        score -= stalled * 15

        gpu_mem = self.gpu_memory_mb()
        if gpu_mem is not None and gpu_mem > 5000:
            score -= 20

        return max(0, min(100, score))


memory_manager = MemoryManager()
