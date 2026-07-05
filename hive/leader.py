"""Leader — task orchestration, agent spawning, coordination."""

import json
import uuid
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


class Leader:
    """Orchestrates tasks, spawns agents, manages execution."""

    def __init__(self, llm: QwenClient):
        self.llm = llm
        self.runtime = AgentRuntime(llm)
        self.creator = CreatorAgent(llm)

    async def handle_message(self, user_message: str,
                             session_id: str,
                             memory,
                             db,
                             on_tool_call=None,
                             on_permission=None,
                             on_text=None) -> str:
        """Process a user message end-to-end."""
        # Add user message to memory
        memory.add_message("user", user_message)

        # Build context
        system = {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
        context_messages = [system] + memory.get_context_window()

        # Run agent loop
        response = await self.runtime.run_loop(
            session_id=session_id,
            messages=context_messages,
            on_tool_call=on_tool_call,
            on_permission=on_permission,
            on_text=on_text,
        )

        # Add response to memory
        memory.add_message("assistant", response)

        return response

    async def spawn_agent(self, agent_name: str, task: str,
                          context: dict = None) -> dict:
        """Spawn a worker agent."""
        # Load agent code
        code = await self.creator.load_agent(agent_name)
        if not code:
            return {"error": f"Agent not found: {agent_name}"}

        # Run in separate process
        result = await self.runtime.run_agent(
            agent_code=code,
            task=task,
            context=context or {},
        )
        return result

    async def create_and_spawn(self, name: str, description: str,
                               task: str, tools: list[str] = None) -> dict:
        """Create a new agent and run it."""
        # Generate agent
        result = await self.creator.create_agent(
            name=name,
            description=description,
            task_description=task,
            tools=tools,
        )
        if "error" in result:
            return result

        # Spawn it
        spawn_result = await self.spawn_agent(name, task)
        return {
            "created": result,
            "execution": spawn_result,
        }

    def shutdown(self):
        """Cleanup resources."""
        self.runtime.shutdown()
