"""
HIVE — Hive Core (Leader Agent)
Task intake, decomposition, role assignment, result collection.
Orchestrates the entire swarm. All agents report to this one.
"""

import asyncio
import logging
import time
import uuid
from typing import Optional

from core.llm_router import chat, QUALITY_MODELS
from core.memory_manager import memory_manager
from core.task_queue import task_queue, Task, SubTask, TaskStatus, Priority
from core.audit_logger import audit_logger
from agents.safety_agent import SafetyAgent
from agents.agent_forge import agent_forge

logger = logging.getLogger(__name__)

# ─── Task decomposition prompt ────────────────────────────────────────────────

DECOMPOSE_PROMPT = """You are HIVE's Leader. The user has submitted this task:

"{task}"

Decompose this into sub-tasks. For each sub-task:
1. Identify the BEST worker type from this list:
   - web_scout        (HTTP requests, API calls, scraping, form fills)
   - account_manager  (create accounts, login, 2FA, OAuth)
   - payment_agent    (Stripe/PayPal, invoices, refunds, subscriptions)
   - cloud_tester     (Alibaba Cloud ECS/FC, Docker, health checks)
   - code_runner      (execute code, run tests, git ops, Docker)
   - report_agent     (generate PDF, send email, Slack/Discord webhooks)
   - diagnostician    (parse logs, error analysis, suggest fixes)
   - security_scout  (OWASP Top 10, CVE scan, pen test)
   - code_architect  (clone repo, write feature, PR via GitHub API)
   - red_team        (simulate attacker, generate threat model)
   - data_analyst    (stats on CSV/JSON/Excel, SQL queries, charts)
   - gpu_tuner       (nvidia-smi, GPU optimization, thermal management)
   - scheduler_agent  (cron, retry, timeout, queuing)
   - communicator    (send email, Slack, Discord, Telegram, SMS)

2. Give a clear description of what this sub-task asks the agent to do.

Respond ONLY with a JSON array like this (no markdown, no code block):
[
  {{"agent_type": "web_scout", "description": "Crawl example.com and find all API endpoints"}},
  {{"agent_type": "diagnostician", "description": "Analyze nginx logs and find errors"}}
]

If the task is SIMPLE (can be done by one agent), still return a single-element array.
Do NOT include code_runner, gpu_tuner, security_scout, code_architect, red_team unless explicitly needed.
Keep it to 2-6 sub-tasks maximum. Prefer fewer, parallelizable agents.
"""


# ─── Worker task execution ───────────────────────────────────────────────────

async def _run_worker(agent_type: str, subtask: SubTask, task_id: str) -> dict:
    """Run a single worker agent and return its result."""
    start = time.time()
    agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"

    await memory_manager.register(agent_id, agent_type, task_id)

    try:
        # Dynamically import and run the worker
        worker_module = _get_worker_module(agent_type)
        result = await worker_module.run(subtask.description, context={"task_id": task_id})
        elapsed = time.time() - start

        await memory_manager.unregister(agent_id)

        return {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "subtask_id": subtask.id,
            "status": "success",
            "result": result,
            "time_taken": elapsed,
        }

    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"[HiveCore] Worker {agent_type} failed: {e}")
        await memory_manager.mark_stalled(agent_id)
        return {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "subtask_id": subtask.id,
            "status": "error",
            "error": str(e),
            "time_taken": elapsed,
        }


def _get_worker_module(agent_type: str):
    """Dynamically load the worker module."""
    module_map = {
        "web_scout": "agents.workers.web_scout",
        "account_manager": "agents.workers.account_manager",
        "payment_agent": "agents.workers.payment_agent",
        "cloud_tester": "agents.workers.cloud_tester",
        "code_runner": "agents.workers.code_runner",
        "report_agent": "agents.workers.report_agent",
        "diagnostician": "agents.workers.diagnostician",
        "security_scout": "agents.workers.security_scout",
        "code_architect": "agents.workers.code_architect",
        "red_team": "agents.workers.red_team",
        "data_analyst": "agents.workers.data_analyst",
        "gpu_tuner": "agents.workers.gpu_tuner",
        "scheduler_agent": "agents.workers.scheduler",
        "communicator": "agents.workers.communicator",
    }

    if agent_type not in module_map:
        raise ValueError(f"Unknown agent type: {agent_type}")

    import importlib
    return importlib.import_module(module_map[agent_type])


# ─── Hive Core Leader ─────────────────────────────────────────────────────────

class HiveCore:
    """
    The leader of the HIVE swarm.
    Receives task, decomposes, spawns workers, collects results.
    Contains Safety Agent (one-way ratchet).
    """

    def __init__(self, task: Task):
        self.task = task
        self.safety = SafetyAgent(task_context=task.description)
        self.total_tokens = 0
        self.standby_leader_id: Optional[str] = None

    # ── SINGLE AGENT MODE ───────────────────────────────────────────────────

    async def execute_single(self) -> dict:
        """
        Run the entire task through Leader only (no workers).
        Used for the single-agent baseline comparison.
        """
        logger.info(f"[HiveCore] Task {self.task.id}: SINGLE mode (no workers)")
        audit_logger.log("EXECUTE_SINGLE", f"Task {self.task.id} in single mode", metadata={"task": self.task.description})

        messages = [
            {
                "role": "system",
                "content": (
                    "You are HIVE, an autonomous agent swarm leader. "
                    "Answer the user's task thoroughly and accurately. "
                    "You have access to extensive real-world capabilities."
                ),
            },
            {
                "role": "user",
                "content": self.task.description,
            },
        ]

        result = await chat(messages, quality_mode=True)
        self.total_tokens += result.get("tokens", 0)

        return {
            "mode": "single",
            "response": result["content"],
            "tokens_used": self.total_tokens,
            "sub_tasks": [],
            "agents_used": 0,
        }

    # ── SWARM MODE ──────────────────────────────────────────────────────────

    async def execute_swarm(self) -> dict:
        """
        Full swarm execution: decompose → safety-check → spawn workers → collect.
        """
        logger.info(f"[HiveCore] Task {self.task.id}: SWARM mode")
        audit_logger.log("EXECUTE_SWARM_START", f"Task {self.task.id} swarm execution started", metadata={"task": self.task.description})

        # Step 1: Safety check the overall task
        safety_result = await self.safety.check(self.task.description)
        if not safety_result["approved"]:
            return {
                "mode": "swarm",
                "error": f"Safety blocked: {safety_result['reason']}",
                "requires_human": safety_result.get("requires_human", False),
            }

        # Step 2: Decompose into sub-tasks
        sub_tasks = await self._decompose()
        if not sub_tasks:
            return {"mode": "swarm", "error": "Failed to decompose task"}

        # Step 3: Update task with sub-tasks
        for st in sub_tasks:
            task_queue.add_subtask(self.task.id, st)

        # Step 4: Safety-check each sub-task
        approved_tasks = []
        for st in sub_tasks:
            safety = await self.safety.check(st.description)
            if safety["approved"]:
                approved_tasks.append(st)
            else:
                logger.warning(f"[HiveCore] Sub-task blocked by Safety: {st.description[:60]}")

        if not approved_tasks:
            return {
                "mode": "swarm",
                "error": "All sub-tasks blocked by Safety Agent",
            }

        # Step 5: Spawn workers in parallel
        tasks_to_spawn = [
            {"agent_type": st.agent_type, "subtask": st}
            for st in approved_tasks
        ]

        spawned = await agent_forge.spawn_batch(
            tasks=tasks_to_spawn,
            task_id=self.task.id,
        )

        logger.info(f"[HiveCore] Spawned {len(spawned)} agents for task {self.task.id}")

        # Step 6: Run workers in parallel
        async def run_one(agent_info: dict) -> dict:
            subtask = next(st for st in approved_tasks if st.id == agent_info["subtask_id"])
            return await _run_worker(agent_info["agent_type"], subtask, self.task.id)

        results = await asyncio.gather(
            *[run_one(s) for s in spawned],
            return_exceptions=True,
        )

        # Collect results
        worker_results = []
        tokens_used = 0
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[HiveCore] Worker error: {r}")
            else:
                worker_results.append(r)
                tokens_used += r.get("time_taken", 0)

        self.total_tokens = tokens_used

        # Step 7: Compile final result
        final_result = await self._compile_results(worker_results)

        audit_logger.log(
            "EXECUTE_SWARM_COMPLETE",
            f"Task {self.task.id} swarm completed",
            metadata={
                "agents_used": len(worker_results),
                "successful": len([r for r in worker_results if r.get("status") == "success"]),
                "tokens": self.total_tokens,
            },
        )

        return {
            "mode": "swarm",
            "response": final_result,
            "sub_tasks": [
                {
                    "agent_type": r.get("agent_type"),
                    "status": r.get("status"),
                    "result": r.get("result"),
                    "error": r.get("error"),
                }
                for r in worker_results
            ],
            "agents_used": len(worker_results),
            "successful_agents": len([r for r in worker_results if r.get("status") == "success"]),
            "tokens_used": self.total_tokens,
        }

    # ── Task decomposition ───────────────────────────────────────────────────

    async def _decompose(self) -> list[SubTask]:
        """Ask LLM to break the task into sub-tasks."""
        messages = [
            {"role": "user", "content": DECOMPOSE_PROMPT.format(task=self.task.description)},
        ]

        try:
            result = await chat(messages, quality_mode=True)
            self.total_tokens += result.get("tokens", 0)

            import json
            data = json.loads(result["content"])

            sub_tasks = []
            for item in data:
                st = SubTask(
                    id=str(uuid.uuid4())[:8],
                    description=item["description"],
                    agent_type=item["agent_type"],
                )
                sub_tasks.append(st)

            logger.info(f"[HiveCore] Decomposed into {len(sub_tasks)} sub-tasks")
            audit_logger.log(
                "TASK_DECOMPOSED",
                f"Task {self.task.id} → {[st.agent_type for st in sub_tasks]}",
                metadata={"sub_tasks": [{"id": st.id, "type": st.agent_type, "desc": st.description} for st in sub_tasks]},
            )
            return sub_tasks

        except Exception as e:
            logger.error(f"[HiveCore] Decomposition failed: {e}")
            # Fallback: treat as single task for one agent
            return [
                SubTask(
                    id=str(uuid.uuid4())[:8],
                    description=self.task.description,
                    agent_type="diagnostician",  # most general-purpose
                )
            ]

    # ── Result compilation ─────────────────────────────────────────────────

    async def _compile_results(self, worker_results: list[dict]) -> str:
        """Use LLM to compile worker outputs into a final natural language response."""

        if not worker_results:
            return "No results generated."

        # Build summary for LLM
        worker_summary = "\n".join([
            f"## {r.get('agent_type', '?')} Agent (subtask {r.get('subtask_id', '?')}):\n"
            f"Status: {r.get('status', '?')}\n"
            f"Result: {str(r.get('result', r.get('error', 'No result')))[:500]}"
            for r in worker_results
        ])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are HIVE's Report Agent. Given the outputs from multiple specialized agents, "
                    "compile a clear, well-structured final response for the user. "
                    "Do not mention agents by name unless relevant. Just summarize the findings clearly."
                ),
            },
            {
                "role": "user",
                "content": f"Original user request: {self.task.description}\n\nAgent results:\n{worker_summary}\n\nCompile this into a final response:",
            },
        ]

        try:
            result = await chat(messages, quality_mode=True, max_tokens=2048)
            self.total_tokens += result.get("tokens", 0)
            return result["content"]
        except Exception as e:
            logger.error(f"[HiveCore] Compilation failed: {e}")
            return f"Swarm completed {len(worker_results)} sub-tasks."