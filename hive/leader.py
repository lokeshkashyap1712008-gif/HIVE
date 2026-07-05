"""Leader — task orchestration, agent spawning, coordination."""

import json
import uuid
import asyncio
from hive.llm import QwenClient
from hive.runtime import AgentRuntime
from hive.creator import CreatorAgent
from hive.tools import TOOLS, execute_tool
from hive.permissions import get_tool_tier, should_auto_allow

SYSTEM_PROMPT = """You are HIVE, an AI operating system. You have access to tools.

When the user gives you a task:
1. Think about what needs to be done
2. Use tools to accomplish it
3. Report results clearly

If a task is complex, break it into steps and execute them one by one.
If you need a specialized agent that doesn't exist, describe what agent you need.

Be concise. Don't explain what you're about to do — just do it.
Only explain when the task is complete."""

SWARM_KEYWORDS = [
    "swarm", "agents", "decompose", "orchestrat", "multi-agent",
    "security scan", "code review", "threat model", "red team",
    "gpu tune", "data analy", "report gen",
]


class Leader:
    """Orchestrates tasks, spawns agents, manages execution."""

    def __init__(self, llm: QwenClient):
        self.llm = llm
        self.runtime = AgentRuntime(llm)
        self.creator = CreatorAgent(llm)

    def _should_use_swarm(self, message: str) -> bool:
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in SWARM_KEYWORDS)

    async def _run_swarm_task(self, message: str) -> str:
        """Run a task through the HIVE swarm pipeline."""
        try:
            from hive.agents.leader import run_swarm
            result = await run_swarm(message)
            synthesis = result.get("synthesis", "Task completed.")
            subtask_count = len(result.get("subtasks", []))
            worker_count = len(result.get("results", []))
            return (
                f"Swarm completed: {subtask_count} subtasks dispatched to {worker_count} workers.\n\n"
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
                             on_text=None) -> str:
        """Process a user message end-to-end."""
        memory.add_message("user", user_message)

        # Check if swarm should handle this
        if self._should_use_swarm(user_message):
            response = await self._run_swarm_task(user_message)
            memory.add_message("assistant", response)
            return response

        # Standard single-agent path
        system = {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
        context_messages = [system] + memory.get_context_window()

        response = await self.runtime.run_loop(
            session_id=session_id,
            messages=context_messages,
            on_tool_call=on_tool_call,
            on_permission=on_permission,
            on_text=on_text,
        )

        memory.add_message("assistant", response)
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

    def shutdown(self):
        """Cleanup resources."""
        self.runtime.shutdown()
