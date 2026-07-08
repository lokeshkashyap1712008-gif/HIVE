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

SYSTEM_PROMPT = """You are HIVE, an AI operating system. You MUST use tools to do work.

RULE: Call exactly ONE tool per response. Then wait for the result before calling the next tool.

YOUR TOOLS:
- web_search(query): Search the web. Use this FIRST when asked to find/search/look up anything.
- exa_search(query, num_results): Advanced web search with more results.
- create_excel(data, title, filename): Create Excel file. data must be a JSON array of objects.

BROWSER TOOLS (Playwright — headless, step-by-step):
- browser_open(url): Open a website in the browser.
- browser_inspect(): List all interactive elements with index numbers.
- browser_click(index=N): Click element by its index from browser_inspect.
- browser_type(index=N, text="...", sensitive_data={...}): Type into input field. Use ${key} placeholders for sensitive data.
- browser_read(): Read the page text content.
- browser_screenshot(): Take a screenshot.
- browser_back(): Go back in browser history.
- browser_close(): Close the browser.

BROWSER USE (Chrome Profile — best for login & complex flows):
- browser_use_task(task): Automate using Chrome profile with saved logins. Use for login, multi-step workflows.

SESSION TOOLS (save login sessions for reuse):
- browser_session_save(name): Save current session to disk (cookies, localStorage).
- browser_session_load(name): Load a saved session (skips login on future runs).
- browser_list_sessions(): List all saved sessions.
- browser_delete_session(name): Delete a saved session.

EMAIL VERIFICATION:
- browser_create_inbox(): Create a disposable email inbox.
- browser_wait_for_code(timeout=30): Wait for verification code to arrive.

VAULT (encrypted credential & card storage):
- vault_store_credential(site, username, password): Store login in encrypted vault.
- vault_list_credentials(): List stored credentials (no passwords shown).
- vault_store_card(label, number, expiry, cvv, name, billing_zip): Store payment card.
- vault_list_cards(): List stored cards (last 4 digits only).

SIGNUP & CHECKOUT:
- browser_signup(task, url, email, password): Create account, handle email verification, save to vault.
- browser_checkout(task, url, amount, card_id, confirm): Fill checkout form with vault card. CLI prompts before final purchase.
- browser_google_login(email): Open visible browser for manual Google sign-in; saves session as google_com.
- browser_oauth(platform): OAuth for github or google.

CLI COMMANDS:
- /google-login [email] — manual Google sign-in with session save
- /oauth github|google — OAuth authorization flow

CREDENTIAL MANAGEMENT:
- Use sensitive_data parameter to inject credentials safely. LLM never sees actual values.
- Example: browser_type(index=2, text="${email}", sensitive_data={"email": "user@example.com"})

SWARM MODE - BROWSER AUTOMATION:
When a task requires browser automation (login, signup, checkout, navigate):
1. Use swarm mode — the leader picks browser_agent or browser_use_worker automatically
2. Login/complex tasks → browser_use_worker (Chrome profile)
3. Simple headless tasks → browser_agent (Playwright)
4. Checkout/payment → payment_agent (stops for human confirmation)

BROWSER WORKFLOW (step by step, one tool per turn):
  Step 1: browser_open("https://example.com")
  Step 2: browser_inspect()  →  see elements with index numbers
  Step 3: browser_type(index=0, text="my search", press_enter=true)
  Step 4: browser_screenshot()  →  verify what happened

CRITICAL:
- ALWAYS use browser_inspect() after browser_open to see what elements exist
- Use the index number from browser_inspect for browser_click/browser_type
- Only ONE tool call per response — then wait for the result
- NEVER create placeholder data
- For sensitive data (passwords, cards), use ${key} placeholders with sensitive_data
- For checkout: never set confirm=true without explicit user approval

Just do the work. Don't explain what you'll do."""

ROUTING_PROMPT = """You are a task router. Analyze the user's message and decide the best execution mode.

Modes:
- "single": Simple tasks, questions, small edits, reading files, quick lookups, web searches, data collection, creating files
- "swarm": Complex tasks requiring multiple specialists working in parallel, security reviews, threat models, browser automation tasks

IMPORTANT: Most tasks should use "single" mode. Only use "swarm" for truly complex multi-agent tasks.

ALWAYS use "swarm" for:
- Login to websites, sign in, authentication
- Click buttons, fill forms, navigate websites
- Star/unstar repos, follow/unfollow users
- Any task that requires interacting with a website
- Tasks mentioning credentials (email, password)

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
