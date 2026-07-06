"""
HIVE OS - Swarm Leader (Queen Bee)
Orchestrates task decomposition, parallel worker dispatch, result synthesis.
"""

import asyncio
import time
import uuid
import json
import importlib
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from hive.core.llm_router import chat, QWEN_MAX
from hive.core.economy import economy, COSTS
from hive.core.message_bus import get_bus, MessageType
from hive.core.agent_state import get_or_create_state

VALID_WORKERS = {
    "web_scout", "security_scout", "code_architect", "data_analyst",
    "gpu_tuner", "communicator", "scheduler", "account_manager",
    "payment_agent", "cloud_tester", "code_runner", "diagnostician",
    "red_team", "report_agent", "desktop_controller",
}

WORKER_ALIASES = {
    "worker": "code_runner", "scout": "web_scout", "security": "security_scout",
    "code": "code_runner", "git": "code_runner", "docker": "code_runner",
    "analysis": "data_analyst", "data": "data_analyst", "gpu": "gpu_tuner",
    "message": "communicator", "email": "communicator", "schedule": "scheduler",
    "cron": "scheduler", "diagnose": "diagnostician", "diagnostic": "diagnostician",
    "report": "report_agent", "red": "red_team", "threat": "red_team",
    "test": "cloud_tester", "cloud": "cloud_tester", "account": "account_manager",
    "auth": "account_manager", "payment": "payment_agent", "desktop": "desktop_controller",
    "mouse": "desktop_controller", "keyboard": "desktop_controller",
    "click": "desktop_controller", "screenshot": "desktop_controller",
    "whatsapp": "desktop_controller", "browser": "desktop_controller", "chrome": "desktop_controller",
}


def _normalize_worker_type(worker_type: str) -> str:
    worker_type = worker_type.lower().strip()
    if worker_type in VALID_WORKERS:
        return worker_type
    if worker_type in WORKER_ALIASES:
        return WORKER_ALIASES[worker_type]
    for valid in VALID_WORKERS:
        if worker_type in valid or valid in worker_type:
            return valid
    return "code_runner"


class HiveLeader:
    """Queen Bee - Main orchestrator for the HIVE swarm"""

    def __init__(self, agent_id: str = "queen_bee"):
        self.agent_id = agent_id
        self.active_tasks: Dict[str, dict] = {}
        self.worker_registry: Dict[str, dict] = {}
        self.bus = get_bus()
        self.bus.register_agent(agent_id, "leader")

    async def decompose_task(self, description: str) -> List[dict]:
        messages = [
            {"role": "system", "content": """You are a task decomposition expert.
Decompose the given task into specific subtasks that can be assigned to specialized workers.
Available workers: web_scout, security_scout, code_architect, data_analyst, gpu_tuner, communicator, code_runner, diagnostician, scheduler, report_agent, red_team.
Return ONLY a JSON array (no markdown, no explanation). Each item needs 'description', 'worker_type', 'priority' fields.
For tasks that can run in parallel, use the same 'group' field value."""},
            {"role": "user", "content": f"Decompose this task: {description}"}
        ]

        response = await chat(messages, model=QWEN_MAX, quality=True)
        raw = response["content"]

        import re
        cleaned = re.sub(r'```(?:json)?\s*', '', raw)
        cleaned = re.sub(r'```\s*$', '', cleaned.strip())
        json_match = re.search(r'\[.*\]', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        try:
            subtasks = json.loads(cleaned)
            if isinstance(subtasks, list) and subtasks:
                for st in subtasks:
                    wt = st.get("worker_type", "code_runner")
                    st["worker_type"] = _normalize_worker_type(wt)
                    if "group" not in st:
                        st["group"] = "default"
                return subtasks
        except (json.JSONDecodeError, ValueError):
            pass

        return [{"description": description, "worker_type": "code_runner", "priority": "medium", "group": "default"}]

    async def _run_worker(self, subtask: dict) -> dict:
        worker_id = subtask.get("worker_type", "code_runner")
        description = subtask.get("description", "")
        group = subtask.get("group", "default")

        self.bus.send_message(
            self.agent_id, worker_id,
            f"TASK: {description}",
            MessageType.TASK
        )

        state = get_or_create_state(worker_id)
        state.task_started()

        try:
            mod = importlib.import_module(f"hive.agents.workers.{worker_id}")
            result = await mod.run(description)
            state.task_completed(success=True)

            self.bus.send_message(
                worker_id, self.agent_id,
                f"RESULT: {json.dumps(result)[:200]}",
                MessageType.RESPONSE
            )

            return {
                "worker": worker_id,
                "task": description,
                "group": group,
                "result": result,
                "status": "completed"
            }
        except Exception as e:
            state.task_completed(success=False)
            return {
                "worker": worker_id,
                "task": description,
                "group": group,
                "status": "error",
                "error": str(e)
            }

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
            "active_tasks": len(self.active_tasks),
            "registered_workers": len(self.worker_registry),
            "bus_messages": self.bus.message_count(),
        }


leader = HiveLeader()


async def run_swarm(task_description: str) -> dict:
    """Main entry point - run a task through the HIVE swarm with parallel execution"""
    task_id = str(uuid.uuid4())[:8]
    start_time = time.time()

    # Check if this is a high-stakes task that needs debate/judge
    high_stakes_keywords = ["delete", "payment", "transfer", "sudo", "drop", "destroy", "irreversible"]
    is_high_stakes = any(kw in task_description.lower() for kw in high_stakes_keywords)

    if is_high_stakes:
        try:
            from hive.agents.debate_protocol import run_debate
            debate_result = await run_debate(task_description)
            if debate_result.get("verdict") == "reject":
                return {
                    "task_id": task_id,
                    "description": task_description,
                    "subtasks": [],
                    "results": [],
                    "synthesis": f"Task rejected by debate protocol: {debate_result.get('final_position', 'Unresolved concerns')}",
                    "status": "rejected",
                    "debate": debate_result,
                }
        except Exception:
            pass  # Continue with swarm if debate fails

    subtasks = await leader.decompose_task(task_description)

    groups = {}
    for st in subtasks:
        group = st.get("group", "default")
        if group not in groups:
            groups[group] = []
        groups[group].append(st)

    results = []
    for group_name, group_tasks in groups.items():
        group_results = await asyncio.gather(
            *[leader._run_worker(st) for st in group_tasks],
            return_exceptions=True
        )
        for r in group_results:
            if isinstance(r, Exception):
                results.append({
                    "worker": "unknown",
                    "task": "unknown",
                    "status": "error",
                    "error": str(r)
                })
            else:
                results.append(r)

    if results:
        synthesis = await leader.synthesize_results(results)
    else:
        synthesis = "Task completed by swarm."

    elapsed_ms = (time.time() - start_time) * 1000

    return {
        "task_id": task_id,
        "description": task_description,
        "subtasks": subtasks,
        "results": results,
        "synthesis": synthesis,
        "status": "completed",
        "elapsed_ms": round(elapsed_ms, 1),
    }


def get_hive_status() -> dict:
    return leader.get_status()
