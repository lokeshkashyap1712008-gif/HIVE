"""
HIVE OS - Swarm Leader (Queen Bee)
Orchestrates task decomposition, parallel worker dispatch, result synthesis.
"""

import asyncio
import time
import uuid
import json
import importlib
import logging
from typing import Dict, List, Optional

from hive.core.llm_router import chat, QWEN_MAX
from hive.core.economy import economy, COSTS, TransactionType
from hive.core.message_bus import get_bus, MessageType
from hive.core.agent_state import get_or_create_state
from hive.agents.safety_agent import SafetyAgent
from hive.dashboard import get_dashboard, Event

logger = logging.getLogger(__name__)

VALID_WORKERS = {
    "web_scout", "security_scout", "code_architect", "data_analyst",
    "gpu_tuner", "scheduler", "account_manager",
    "payment_agent", "cloud_tester", "code_runner", "diagnostician",
    "red_team", "report_agent", "desktop_controller", "cleanup_crew",
}

# Only include communicator if SMTP is configured
import os
if os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"):
    VALID_WORKERS.add("communicator")

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
    "cleanup": "cleanup_crew", "clean": "cleanup_crew", "garbage": "cleanup_crew",
    "gc": "cleanup_crew", "prune": "cleanup_crew",
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
Available workers: web_scout, security_scout, code_architect, data_analyst, gpu_tuner, communicator, code_runner, diagnostician, scheduler, report_agent, red_team, cleanup_crew.

CRITICAL RULES:
1. Each subtask MUST include ALL relevant context from the original task (URLs, file paths, specific details)
2. If the original task mentions a URL, EVERY subtask that needs it must include the full URL
3. Do NOT summarize or truncate important details when creating subtasks
4. Each subtask description should be self-contained and actionable
5. Do NOT add communication/notification subtasks (email, slack, etc.) unless the user EXPLICITLY asks for them
6. Focus on the core task: analysis, scanning, generation — not delivery methods

Return ONLY a JSON array (no markdown, no explanation). Each item needs 'description', 'worker_type', 'priority' fields.
For tasks that can run in parallel, use the same 'group' field value."""},
            {"role": "user", "content": f"Decompose this task (include ALL details like URLs in each subtask):\n\n{description}"}
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
        required_skills = subtask.get("skills", [])
        dash = get_dashboard()

        # Dashboard: spawn agent
        agent_label = f"{worker_id}_{str(uuid.uuid4())[:4]}"
        dash.agent_spawn(agent_label, worker_id)

        safety = SafetyAgent(task_context=description)
        safety_result = await safety.check(description)
        if not safety_result.get("approved", True):
            logger.warning(f"[Swarm] SafetyAgent blocked task: {safety_result.get('reason')}")
            dash.agent_fail(agent_label, "blocked by safety")
            return {
                "worker": worker_id,
                "task": description,
                "group": group,
                "status": "blocked",
                "error": f"Blocked by SafetyAgent: {safety_result.get('reason')}",
                "requires_human": safety_result.get("requires_human", False),
            }

        task_cost = economy.task_cost(worker_id, "medium")
        if not economy.spend(worker_id, task_cost, f"worker task: {description[:50]}",
                             tx_type=TransactionType.TASK):
            logger.warning(f"[Swarm] Insufficient budget for worker {worker_id}")
            dash.agent_fail(agent_label, "insufficient budget")
            return {
                "worker": worker_id,
                "task": description,
                "group": group,
                "status": "error",
                "error": f"Insufficient budget. Need {task_cost} credits, have {economy.budget.available}.",
            }

        # Dashboard: spend credits
        dash.spend(task_cost, f"task:{worker_id}")
        dash.agent_work(agent_label, description[:50])

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

            # Dashboard: completed
            dash.agent_done(agent_label)
            dash.earn(task_cost // 2, f"refund:{worker_id}")  # partial refund on success

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
        except ImportError:
            # Worker module not found — try AgentForge to create a specialist
            logger.info(f"[Swarm] Worker '{worker_id}' not found, attempting to forge specialist agent")
            dash.set_status("forging specialist agent")
            try:
                from hive.agents.agent_forge import forge_task
                forge_result = await forge_task(description, required_skills or [worker_id])
                if forge_result.get("created"):
                    agent_id = forge_result["agent_id"]
                    dash.agent_spawn(agent_id, "forge")
                    dash.spend(COSTS["creation_event"], f"forge:{agent_id}")
                    from hive.agents.agent_forge import run_designed_agent
                    dash.agent_work(agent_id, description[:50])
                    run_result = await run_designed_agent(agent_id, description)
                    dash.agent_done(agent_id)
                    state.task_completed(success=True)

                    self.bus.send_message(
                        agent_id, self.agent_id,
                        f"RESULT: {json.dumps(run_result)[:200]}",
                        MessageType.RESPONSE
                    )
                    return {
                        "worker": f"forge:{agent_id}",
                        "task": description,
                        "group": group,
                        "result": run_result,
                        "status": "completed",
                        "forged": True,
                    }
                else:
                    raise Exception(f"No worker '{worker_id}' and forge failed: {forge_result.get('reason')}")
            except Exception as forge_err:
                dash.agent_fail(agent_label, str(forge_err)[:50])
                state.task_completed(success=False)
                return {
                    "worker": worker_id,
                    "task": description,
                    "group": group,
                    "status": "error",
                    "error": f"Worker not found and forge failed: {forge_err}"
                }
        except Exception as e:
            dash.agent_fail(agent_label, str(e)[:50])
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
    dash = get_dashboard()

    # Dashboard: task start
    dash.set_task(task_description)
    dash.set_status("routing")

    # Check if this is a high-stakes task that needs debate/judge
    high_stakes_keywords = ["delete", "payment", "transfer", "sudo", "drop", "destroy", "irreversible"]
    is_high_stakes = any(kw in task_description.lower() for kw in high_stakes_keywords)

    if is_high_stakes:
        dash.set_status("debating")
        try:
            from hive.agents.debate_protocol import run_debate
            dash.events.append(Event(time.time(), "msg", "leader", "Running debate protocol", "yellow"))
            debate_result = await run_debate(task_description)
            if debate_result.get("verdict") == "reject":
                dash.set_status("rejected")
                return {
                    "task_id": task_id,
                    "description": task_description,
                    "subtasks": [],
                    "results": [],
                    "synthesis": f"Task rejected by debate protocol: {debate_result.get('final_position', 'Unresolved concerns')}",
                    "status": "rejected",
                    "debate": debate_result,
                }

            from hive.agents.judge import judge_action
            agent_positions = {}
            for agent_id, finding in debate_result.get("rounds", {}).get("round_3_refinement", {}).items():
                agent_positions[agent_id] = finding
            if not agent_positions:
                agent_positions = {"debate_moderator": debate_result.get("final_position", "")}

            dash.events.append(Event(time.time(), "msg", "judge", "Verdict phase", "yellow"))
            judge_result = await judge_action(task_description, agent_positions)
            if judge_result.get("verdict") == "reject":
                dash.set_status("rejected")
                return {
                    "task_id": task_id,
                    "description": task_description,
                    "subtasks": [],
                    "results": [],
                    "synthesis": f"Task rejected by Judge: {judge_result.get('reasoning', 'Failed legitimacy check')}",
                    "status": "rejected",
                    "debate": debate_result,
                    "judge": judge_result,
                }
        except Exception as e:
            logger.warning(f"[Swarm] Debate/Judge protocol failed: {e}")

    # Dashboard: decomposing
    dash.set_status("decomposing")
    dash.events.append(Event(time.time(), "task", "leader", "Breaking into subtasks", "cyan"))

    subtasks = await leader.decompose_task(task_description)
    dash.subtask_progress(0, len(subtasks))
    dash.events.append(Event(time.time(), "msg", "leader", f"Created {len(subtasks)} subtasks", "green"))

    groups = {}
    for st in subtasks:
        group = st.get("group", "default")
        if group not in groups:
            groups[group] = []
        groups[group].append(st)

    # Dashboard: spawning workers
    dash.set_status("spawning")

    results = []
    for group_name, group_tasks in groups.items():
        dash.events.append(Event(time.time(), "msg", "leader", f"Running group '{group_name}' ({len(group_tasks)} tasks)", "cyan"))
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
        dash.subtask_progress(len(results), len(subtasks))

    # Dashboard: synthesizing
    dash.set_status("synthesizing")
    dash.events.append(Event(time.time(), "msg", "leader", "Synthesizing results", "cyan"))

    if results:
        synthesis = await leader.synthesize_results(results)
    else:
        synthesis = "Task completed by swarm."

    # Auto-trigger cleanup after swarm execution
    dash.set_status("cleanup")
    try:
        from hive.agents.cleanup_crew import cleanup_crew
        cleanup_result = cleanup_crew.run_full_cleanup()
        deleted = cleanup_result.get("agents_deleted", 0)
        if deleted > 0:
            dash.events.append(Event(time.time(), "delete", "cleanup", f"Removed {deleted} expired agents", "red"))
            logger.info(f"[Swarm] Auto-cleanup: {deleted} agents cleaned")
    except Exception as e:
        logger.warning(f"[Swarm] Auto-cleanup failed: {e}")

    elapsed_ms = (time.time() - start_time) * 1000

    # Dashboard: done
    dash.set_status("done")
    dash.clear_done_agents()

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
