"""Leader — unified task orchestration with smart routing."""

import json
import uuid
import asyncio
import time
from typing import Optional
from hive.llm import QwenClient
from hive.runtime import AgentRuntime
from hive.creator import CreatorAgent
from hive.tools import TOOLS, execute_tool
from hive.permissions import get_tool_tier, should_auto_allow
from hive.core.economy import economy, COSTS
from hive.core.message_bus import get_bus
from hive.core.audit_logger import audit_logger

SYSTEM_PROMPT = """You are HIVE, an AI operating system. You have access to tools.

When the user gives you a task:
1. Think about what needs to be done
2. Use tools to accomplish it
3. Report results clearly

If a task is complex, break it into steps and execute them one by one.
If you need a specialized agent that doesn't exist, describe what agent you need.

Be concise. Don't explain what you're about to do — just do it.
Only explain when the task is complete."""

ROUTING_PROMPT = """You are a task router. Analyze the user's message and decide the best execution mode.

Modes:
- "single": Simple tasks, questions, small edits, reading files, quick lookups
- "swarm": Complex tasks requiring multiple specialists, research + analysis + coding, security reviews, data analysis, multi-step workflows

Consider:
- Does this need multiple specialists working together?
- Is this a multi-step task with research, analysis, AND implementation?
- Would parallel execution save time?
- Is this a security review, threat model, or comprehensive analysis?

Reply with ONLY one word: "single" or "swarm" """


class Leader:
    """Unified orchestrator — routes tasks to single-agent or swarm mode."""

    def __init__(self, llm: QwenClient):
        self.llm = llm
        self.runtime = AgentRuntime(llm)
        self.creator = CreatorAgent(llm)
        self.bus = get_bus()
        self.bus.register_agent("leader", "orchestrator")
        self._active_agents: dict[str, dict] = {}
        self._task_history: list[dict] = []

    async def _route_task(self, message: str) -> str:
        """Use LLM to decide routing mode."""
        try:
            result = await self.llm.chat([
                {"role": "system", "content": ROUTING_PROMPT},
                {"role": "user", "content": message},
            ])
            content = self.llm.extract_response(result).strip().lower()
            if "swarm" in content:
                return "swarm"
            return "single"
        except Exception:
            return "single"

    async def _run_swarm_task(self, message: str, on_tool_call=None,
                               on_permission=None, on_text=None) -> str:
        """Run a task through the HIVE swarm pipeline."""
        try:
            from hive.agents.leader import run_swarm
            result = await run_swarm(message)
            synthesis = result.get("synthesis", "Task completed.")
            subtask_count = len(result.get("subtasks", []))
            worker_count = len(result.get("results", []))

            worker_details = []
            for r in result.get("results", []):
                worker_details.append(f"  - {r['worker']}: {r['status']}")

            status_lines = "\n".join(worker_details) if worker_details else "  (no workers dispatched)"

            return (
                f"**Swarm completed** — {subtask_count} subtasks, {worker_count} workers\n\n"
                f"{status_lines}\n\n"
                f"{synthesis}"
            )
        except Exception as e:
            return f"Swarm error: {e}. Falling back to single-agent mode."

    async def handle_message(self, user_message: str,
                             session_id: str,
                             memory,
                             db,
                             on_tool_call=None,
                             on_permission=None,
                             on_text=None,
                             force_swarm: bool = False) -> str:
        """Process a user message end-to-end."""
        memory.add_message("user", user_message)

        # Smart routing via LLM (or forced swarm)
        if force_swarm:
            mode = "swarm"
        else:
            mode = await self._route_task(user_message)

        if mode == "swarm":
            response = await self._run_swarm_task(
                user_message, on_tool_call, on_permission, on_text
            )
        else:
            response = await self._run_single_agent(
                user_message, session_id, memory, db,
                on_tool_call, on_permission, on_text
            )

        memory.add_message("assistant", response)
        return response

    async def _run_single_agent(self, user_message: str,
                                 session_id: str, memory, db,
                                 on_tool_call=None, on_permission=None,
                                 on_text=None) -> str:
        """Standard single-agent path with tool loop."""
        system = {"role": "system", "content": SYSTEM_PROMPT}
        context_messages = [system] + memory.get_context_window()

        response = await self.runtime.run_loop(
            session_id=session_id,
            messages=context_messages,
            on_tool_call=on_tool_call,
            on_permission=on_permission,
            on_text=on_text,
        )
        return response

    async def spawn_agent(self, agent_name: str, task: str,
                          context: dict = None) -> dict:
        """Spawn a worker agent."""
        code = await self.creator.load_agent(agent_name)
        if not code:
            return {"error": f"Agent not found: {agent_name}"}

        result = await self.runtime.run_agent(
            agent_code=code,
            task=task,
            context=context or {},
        )
        return result

    async def create_and_spawn(self, name: str, description: str,
                               task: str, tools: list[str] = None) -> dict:
        """Create a new agent and run it."""
        result = await self.creator.create_agent(
            name=name,
            description=description,
            task_description=task,
            tools=tools,
        )
        if "error" in result:
            return result

        spawn_result = await self.spawn_agent(name, task)
        return {
            "created": result,
            "execution": spawn_result,
        }

    def get_status(self) -> dict:
        """Get orchestrator status."""
        return {
            "active_agents": len(self._active_agents),
            "tasks_completed": len(self._task_history),
            "bus_messages": self.bus.message_count(),
            "registered_agents": list(self.bus.list_agents().keys()),
        }

    def shutdown(self):
        """Cleanup resources."""
        self.runtime.shutdown()
