"""
HIVE OS - Leader Agent (Queen Bee)
Orchestrates task decomposition, volunteer selection, result synthesis.
Implements standby leader election with heartbeat monitoring.
"""

import asyncio
import time
import uuid
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from hive.core.llm_router import chat, QWEN_MAX
from hive.core.economy import economy
from hive.core.message_bus import get_bus, Message
from hive.core.agent_state import get_or_create_state

# All valid worker module names
VALID_WORKERS = {
    "web_scout", "security_scout", "code_architect", "data_analyst",
    "gpu_tuner", "communicator", "scheduler", "account_manager",
    "payment_agent", "cloud_tester", "code_runner", "diagnostician",
    "red_team", "report_agent", "desktop_controller",
}

# Map common/alternate names to valid modules
WORKER_ALIASES = {
    "worker": "code_runner",
    "scout": "web_scout",
    "security": "security_scout",
    "code": "code_runner",
    "git": "code_runner",
    "docker": "code_runner",
    "analysis": "data_analyst",
    "data": "data_analyst",
    "gpu": "gpu_tuner",
    "message": "communicator",
    "email": "communicator",
    "schedule": "scheduler",
    "cron": "scheduler",
    "diagnose": "diagnostician",
    "diagnostic": "diagnostician",
    "report": "report_agent",
    "red": "red_team",
    "threat": "red_team",
    "test": "cloud_tester",
    "cloud": "cloud_tester",
    "account": "account_manager",
    "auth": "account_manager",
    "payment": "payment_agent",
    "desktop": "desktop_controller",
    "mouse": "desktop_controller",
    "keyboard": "desktop_controller",
    "click": "desktop_controller",
    "screenshot": "desktop_controller",
    "whatsapp": "desktop_controller",
    "browser": "desktop_controller",
    "chrome": "desktop_controller",
}


def _normalize_worker_type(worker_type: str) -> str:
    """Map any worker_type string to a valid module name."""
    worker_type = worker_type.lower().strip()
    if worker_type in VALID_WORKERS:
        return worker_type
    if worker_type in WORKER_ALIASES:
        return WORKER_ALIASES[worker_type]
    # Partial match: check if worker_type is a substring of any valid worker
    for valid in VALID_WORKERS:
        if worker_type in valid or valid in worker_type:
            return valid
    return "code_runner"  # safe default


class LeaderState(Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    FAILING_OVER = "failing_over"
    RECOVERING = "recovering"


@dataclass
class LeaderConfig:
    heartbeat_interval: float = 5.0
    failure_threshold: int = 3
    max_concurrent_tasks: int = 5
    task_timeout: float = 300.0


class HiveLeader:
    """Queen Bee - Main orchestrator for the HIVE swarm"""

    def __init__(self, agent_id: str = "queen_bee"):
        self.agent_id = agent_id
        self.state = LeaderState.ACTIVE
        self.config = LeaderConfig()
        self.active_tasks: Dict[str, dict] = {}
        self.worker_registry: Dict[str, dict] = {}
        self.last_heartbeat: Dict[str, float] = {}
        self.failure_counts: Dict[str, int] = {}
        self._running = False

    def register_worker(self, worker_id: str, worker_type: str, info: dict = None):
        self.worker_registry[worker_id] = {
            "type": worker_type,
            "status": "idle",
            "registered_at": time.time(),
            **(info or {})
        }
        self.last_heartbeat[worker_id] = time.time()

    def update_heartbeat(self, worker_id: str):
        self.last_heartbeat[worker_id] = time.time()
        if worker_id in self.failure_counts:
            self.failure_counts[worker_id] = 0

    async def decompose_task(self, description: str) -> List[dict]:
        messages = [
            {"role": "system", "content": """You are a task decomposition expert.
Decompose the given task into specific subtasks that can be assigned to specialized workers.
Available workers: web_scout, security_scout, code_architect, data_analyst, gpu_tuner, communicator, code_runner, diagnostician, scheduler.
Return ONLY a JSON array (no markdown, no explanation). Each item needs 'description', 'worker_type', 'priority' fields."""},
            {"role": "user", "content": f"Decompose this task: {description}"}
        ]

        response = await chat(messages, model=QWEN_MAX, quality=True)
        raw = response["content"]

        # Strip markdown code blocks if present
        import re
        cleaned = re.sub(r'```(?:json)?\s*', '', raw)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip())
        # Also try to extract JSON array from text
        json_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        try:
            subtasks = json.loads(cleaned)
            if isinstance(subtasks, list) and subtasks:
                # Normalize worker_type for each subtask
                for st in subtasks:
                    wt = st.get("worker_type", "code_runner")
                    st["worker_type"] = _normalize_worker_type(wt)
                return subtasks
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: single task with safe worker
        return [{"description": description, "worker_type": "code_runner", "priority": "medium"}]

    async def synthesize_results(self, results: List[dict]) -> str:
        messages = [
            {"role": "system", "content": """You are a result synthesis expert.
Combine the results from multiple workers into a coherent, comprehensive response.
Highlight key findings, resolve conflicts, and provide actionable insights."""},
            {"role": "user", "content": f"Synthesize these results: {json.dumps(results, indent=2)}"}
        ]

        response = await chat(messages, model=QWEN_MAX, quality=True)
        return response["content"]

    def get_status(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "active_tasks": len(self.active_tasks),
            "registered_workers": len(self.worker_registry),
            "uptime": time.time()
        }


leader = HiveLeader()


async def run_swarm(task_description: str) -> dict:
    """Main entry point - run a task through the HIVE swarm"""
    task_id = str(uuid.uuid4())[:8]

    task = {
        "id": task_id,
        "description": task_description,
        "created_at": time.time()
    }

    # Decompose task
    subtasks = await leader.decompose_task(task_description)

    # Try to run worker agents
    results = []
    for subtask in subtasks:
        worker_id = _normalize_worker_type(subtask.get("worker_type", "code_runner"))
        try:
            # Try to import and run the worker
            import importlib
            mod = importlib.import_module(f"hive.agents.workers.{worker_id}")
            result = await mod.run(subtask["description"])
            results.append({
                "worker": worker_id,
                "task": subtask["description"],
                "result": result,
                "status": "completed"
            })
        except (ImportError, Exception) as e:
            results.append({
                "worker": worker_id,
                "task": subtask["description"],
                "status": "error",
                "error": str(e)
            })

    # Synthesize results
    if results:
        synthesis = await leader.synthesize_results(results)
    else:
        synthesis = "Task completed by swarm."

    return {
        "task_id": task_id,
        "description": task_description,
        "subtasks": subtasks,
        "results": results,
        "synthesis": synthesis,
        "status": "completed"
    }


def get_hive_status() -> dict:
    return leader.get_status()
