"""CLI — main loop, input handling, output formatting."""

import sys
import uuid
import asyncio
from hive import __version__
from hive.config import QWEN_MODEL, DASHSCOPE_API_KEY, ensure_dirs
from hive.storage import (
    init_db, get_db, create_session, end_session,
    add_message, list_sessions, list_agents, list_skills, audit_log,
)
from hive.memory import ShortTermMemory
from hive.llm import QwenClient
from hive.leader import Leader
from hive.permissions import get_tool_tier


TEST_MODE = False


def print_banner():
    mode = " [test mode]" if TEST_MODE else ""
    print(f"hive v{__version__} | {QWEN_MODEL}{mode} | type /help for commands\n")


def print_help():
    print("""
  Commands:
    /help           Show this help
    /quit           Exit hive
    /sessions       List past sessions
    /resume <id>    Resume a session
    /agents         List active agents
    /skills         List learned skills
    /model          Show current model
    /clear          Clear screen
""")


async def agent_action(tool_name: str, args: dict):
    """Print tool call action."""
    detail = args.get("path", args.get("url", args.get("command", "")))
    if detail:
        print(f"  * {tool_name} ({detail})")
    else:
        print(f"  * {tool_name}")


async def permission_prompt(tool_name: str, target: str, tier: str) -> str:
    """Ask user for permission. Returns 'approved' or 'denied'."""
    label = target[:60] if target else ""
    try:
        answer = input(f"  ? Allow {tool_name} on {label}? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return "denied"
    if answer in ("", "y", "yes"):
        return "approved"
    return "denied"


class HiveCLI:
    """Main CLI application."""

    def __init__(self):
        ensure_dirs()
        self.session_id = str(uuid.uuid4())[:8]
        self.memory = ShortTermMemory()
        self.leader = None
        self.db = None
        self.running = True

    async def start(self):
        """Initialize and run the CLI."""
        global TEST_MODE
        TEST_MODE = "--test" in sys.argv

        # Init DB
        await init_db()
        self.db = await get_db()

        # Create session
        await create_session(self.db, self.session_id, QWEN_MODEL)

        if TEST_MODE:
            # Test mode: no API key needed, mock responses
            print_banner()
            print("  Running in test mode. API calls are mocked.\n")
            await self._run_test_mode()
            await self.db.close()
            return

        # Validate API key
        if not DASHSCOPE_API_KEY:
            print("  No API key found.")
            print("  Set DASHSCOPE_API_KEY in .env file")
            print("  Or run with --test flag to test without API\n")
            await self.db.close()
            return

        # Init LLM and leader
        llm = QwenClient(api_key=DASHSCOPE_API_KEY, model=QWEN_MODEL)
        self.leader = Leader(llm)

        # Test API key on startup
        try:
            await llm.chat([{"role": "user", "content": "ping"}])
        except Exception as e:
            print(f"  API key invalid. DashScope returned: {e}")
            print("  To fix: go to https://dashscope.console.aliyun.com/")
            print("  Click 'API Keys' in left sidebar -> Create Key")
            print("  Copy the key (format: sk-abc123...) and update .env\n")
            await self.db.close()
            return

        print_banner()

        # Main loop
        while self.running:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            await self._handle_message(user_input)

        # Cleanup
        await end_session(self.db, self.session_id)
        self.leader.shutdown()
        await self.db.close()

    async def _handle_message(self, text: str):
        """Process a user message."""
        try:
            response = await self.leader.handle_message(
                user_message=text,
                session_id=self.session_id,
                memory=self.memory,
                db=self.db,
                on_tool_call=agent_action,
                on_permission=permission_prompt,
            )
            # Save messages to DB
            await add_message(self.db, self.session_id, "user", text)
            await add_message(self.db, self.session_id, "assistant", response)

            print(f"\n  {response}\n")

        except Exception as e:
            print(f"\n  ! Error: {e}\n")

    async def _handle_command(self, cmd: str):
        """Handle slash commands."""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            print_help()

        elif command == "/quit" or command == "/exit":
            print("Bye.")
            self.running = False

        elif command == "/clear":
            print("\033[2J\033[H", end="")

        elif command == "/sessions":
            sessions = await list_sessions(self.db)
            if not sessions:
                print("  No sessions yet.\n")
                return
            print("  Recent sessions:")
            for s in sessions:
                sid = s["id"][:8]
                title = s["title"] or "(untitled)"
                print(f"    {sid}  {title}")
            print()

        elif command == "/agents":
            agents = await list_agents(self.db)
            if not agents:
                print("  No agents registered.\n")
                return
            print("  Registered agents:")
            for a in agents:
                print(f"    {a['name']}  (tier: {a['risk_tier']}, uses: {a['use_count']})")
            print()

        elif command == "/skills":
            skills = await list_skills(self.db)
            if not skills:
                print("  No skills learned yet.\n")
                return
            print("  Learned skills:")
            for s in skills:
                conf = f"{s['confidence']:.0%}"
                print(f"    {s['name']}  (confidence: {conf})")
            print()

        elif command == "/model":
            print(f"  Current model: {QWEN_MODEL}\n")

        elif command == "/resume":
            if arg:
                self.session_id = arg
                self.memory.clear()
                print(f"  Resumed session: {arg}\n")
            else:
                print("  Usage: /resume <session_id>\n")

        else:
            print(f"  Unknown command: {command}\n")

    async def _run_test_mode(self):
        """Run in test mode with mock responses."""
        from hive.tools import TOOLS
        from hive.runtime import AgentRuntime

        # Mock LLM
        class MockLLM:
            def build_tools_schema(self, tools):
                schema = []
                for name, spec in tools.items():
                    schema.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": spec["description"],
                            "parameters": {
                                "type": "object",
                                "properties": spec["parameters"],
                                "required": list(spec["parameters"].keys()),
                            },
                        },
                    })
                return schema

            async def chat(self, messages, tools=None):
                # Mock response - just echo back
                return {
                    "choices": [{
                        "message": {
                            "content": "[TEST] Received your message. "
                                       "This is a mock response. "
                                       "Set a valid DASHSCOPE_API_KEY to get real responses.",
                            "role": "assistant",
                        }
                    }]
                }

        llm = MockLLM()
        self.leader = Leader(llm)

        while self.running:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            # Mock response
            print(f"\n  [TEST] Echo: {user_input}")
            print("  Set DASHSCOPE_API_KEY in .env for real responses.\n")

            await add_message(self.db, self.session_id, "user", user_input)
            await add_message(self.db, self.session_id, "assistant", f"[TEST] {user_input}")

        await end_session(self.db, self.session_id)
