"""CLI — main loop, input handling, output formatting."""

import sys
import uuid
import asyncio
import time
from hive import __version__
from hive.config import QWEN_MODEL, DASHSCOPE_API_KEY, ensure_dirs
from hive.storage import (
    init_db, get_db, create_session, end_session,
    add_message, list_sessions, list_agents, list_skills, audit_log,
)
from hive.memory import ShortTermMemory
from hive.llm import QwenClient
from hive.leader import Leader
from hive.theme import get_console

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Confirm
from rich.text import Text

console = get_console()

SLASH_COMMANDS = [
    "/help", "/quit", "/exit", "/sessions", "/resume",
    "/agents", "/skills", "/model", "/clear", "/status", "/swarm",
    "/cleanup", "/create-agent",
]

TEST_MODE = False
PROMPT = "│ > "
BANNER = [
    "██╗  ██╗██╗██╗   ██╗███████╗",
    "██║  ██║██║██║   ██║██╔════╝",
    "███████║██║██║   ██║█████╗  ",
    "██╔══██║██║╚██╗ ██╔╝██╔══╝  ",
    "██║  ██║██║ ╚████╔╝ ███████╗",
    "╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝",
]


def _render_response(response: str) -> None:
    try:
        console.print(Markdown(response))
    except Exception:
        console.print(response)


def _print_banner():
    mode = " · test mode" if TEST_MODE else ""
    console.print()
    for line in BANNER:
        console.print(f"  [banner]{line}[/banner]")
    console.print(f"  [header]HIVE Code[/header] [muted]v{__version__} · {QWEN_MODEL}{mode}[/muted]")
    console.print("  [muted]Type[/muted] [prompt]/help[/prompt] [muted]for commands[/muted]\n")


def _print_help():
    help_text = (
        "[prompt]/help[/prompt]           Show this help\n"
        "[prompt]/quit[/prompt]           Exit hive\n"
        "[prompt]/sessions[/prompt]       List past sessions\n"
        "[prompt]/resume \\[id][/prompt]    Resume a session\n"
        "[prompt]/agents[/prompt]         List active agents\n"
        "[prompt]/skills[/prompt]         List learned skills\n"
        "[prompt]/model[/prompt]          Show current model\n"
        "[prompt]/status[/prompt]         Show swarm & bus status\n"
        "[prompt]/swarm[/prompt]          Force swarm mode for next task\n"
        "[prompt]/cleanup[/prompt]        Run agent garbage collection\n"
        "[prompt]/create-agent \\[task][/prompt]  Create a specialist agent\n"
        "[prompt]/clear[/prompt]          Clear screen"
    )
    console.print(Panel(
        help_text,
        title="[header]Commands[/header]",
        border_style="border",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


def _table(title: str) -> Table:
    return Table(
        title=title,
        show_header=True,
        header_style="header",
        border_style="border",
        box=box.SIMPLE_HEAD,
        expand=False,
    )


async def _prompt_async() -> str:
    console.print("[muted]╭─[/muted] [prompt]hive[/prompt] [muted]code[/muted]")
    return await asyncio.to_thread(input, PROMPT)


async def agent_action(tool_name: str, args: dict):
    detail = args.get("path", args.get("url", args.get("command", "")))
    if detail:
        console.print(f"  [tool]⏺[/tool] [bold]{tool_name}[/bold] [muted]{detail}[/muted]")
    else:
        console.print(f"  [tool]⏺[/tool] [bold]{tool_name}[/bold]")


async def permission_prompt(tool_name: str, target: str, tier: str) -> str:
    label = (target[:60] + "...") if target and len(target) > 60 else target
    panel = Panel(
        f"[bold]Tool:[/bold] {tool_name}\n"
        f"[bold]Target:[/bold] {label}\n"
        f"[bold]Risk:[/bold] {tier}",
        title="[permission]Permission Required[/permission]",
        border_style="warning",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)
    try:
        approved = Confirm.ask("  Approve tool use?", default=True)
    except (EOFError, KeyboardInterrupt):
        return "denied"
    return "approved" if approved else "denied"


class HiveCLI:
    """Main CLI application."""

    def __init__(self):
        ensure_dirs()
        self.session_id = str(uuid.uuid4())[:8]
        self.memory = ShortTermMemory()
        self.leader = None
        self.db = None
        self.running = True
        self._force_swarm = False

    async def start(self):
        global TEST_MODE
        TEST_MODE = "--test" in sys.argv

        await init_db()
        self.db = await get_db()
        await create_session(self.db, self.session_id, QWEN_MODEL)

        if TEST_MODE:
            _print_banner()
            console.print("[dim]Running in test mode. API calls are mocked.[/dim]\n")
            await self._run_test_mode()
            await self.db.close()
            return

        if not DASHSCOPE_API_KEY:
            console.print("[bold red]Error:[/bold red] No API key found.")
            console.print("Set [bold]DASHSCOPE_API_KEY[/bold] in [dim].env[/dim] file")
            console.print("Or run with [prompt]--test[/prompt] flag to test without API\n")
            await self.db.close()
            return

        llm = QwenClient(api_key=DASHSCOPE_API_KEY, model=QWEN_MODEL)
        self.leader = Leader(llm)

        try:
            await llm.chat([{"role": "user", "content": "ping"}])
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] API key invalid — {e}")
            console.print("To fix: go to [link]https://dashscope.console.aliyuncs.com/[/link]")
            console.print("[dim]Click 'API Keys' in left sidebar → Create Key[/dim]")
            await self.db.close()
            return

        _print_banner()

        while self.running:
            try:
                user_input = await _prompt_async()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye.[/dim]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            await self._handle_message(user_input)

        await end_session(self.db, self.session_id)
        self.leader.shutdown()
        await self.db.close()

    async def _handle_message(self, text: str):
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                started = time.perf_counter()
                force_swarm = self._force_swarm
                self._force_swarm = False
                with console.status("[thinking]✢ Thinking...[/thinking]", spinner="dots"):
                    response = await self.leader.handle_message(
                        user_message=text,
                        session_id=self.session_id,
                        memory=self.memory,
                        db=self.db,
                        on_tool_call=agent_action,
                        on_permission=permission_prompt,
                        force_swarm=force_swarm,
                    )
                elapsed = time.perf_counter() - started
                await add_message(self.db, self.session_id, "user", text)
                await add_message(self.db, self.session_id, "assistant", response)
                console.print()
                console.print(f"[thinking]✢ Thought:[/thinking] [muted]{elapsed:.1f}s[/muted]\n")
                _render_response(response)
                console.print(f"\n[status]▣ HIVE[/status] [muted]· {QWEN_MODEL} · {elapsed:.1f}s[/muted]")
                console.print()
                return
            except Exception as e:
                if attempt < max_retries:
                    console.print(f"[yellow]⚠ Retrying... ({attempt + 1}/{max_retries})[/yellow]")
                    await asyncio.sleep(1)
                else:
                    console.print(f"\n[bold red]Error:[/bold red] {e}\n")
                    console.print("[dim]Tip: Try rephrasing your message or use /swarm for complex tasks.[/dim]\n")

    async def _handle_command(self, cmd: str):
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/help":
            _print_help()

        elif command in ("/quit", "/exit"):
            console.print("[dim]Bye.[/dim]")
            self.running = False

        elif command == "/clear":
            console.clear()

        elif command == "/sessions":
            sessions = await list_sessions(self.db)
            if not sessions:
                console.print("[dim]No sessions yet.[/dim]\n")
                return
            table = _table("Recent Sessions")
            table.add_column("ID", style="code", width=10)
            table.add_column("Title", style="white")
            table.add_column("Model", style="dim")
            for s in sessions:
                sid = s["id"][:8]
                title = s["title"] or "(untitled)"
                table.add_row(sid, title, s["model"] or "")
            console.print(table)
            console.print()

        elif command == "/agents":
            try:
                from hive.agents.agent_forge import AGENT_REGISTRY, temporary_agents

                core_agents = [
                    agent_id for agent_id, info in AGENT_REGISTRY.items()
                    if info.get("type") == "core"
                ]
                worker_agents = [
                    agent_id for agent_id, info in AGENT_REGISTRY.items()
                    if info.get("type") == "worker"
                ]
                temp_agents = [
                    (agent_id, temporary_agents[agent_id])
                    for agent_id in temporary_agents
                ]

                if not core_agents and not worker_agents and not temp_agents:
                    console.print("[dim]No swarm agents registered.[/dim]\n")
                    return

                table = _table("Agent Swarm")
                table.add_column("Group", style="agent")
                table.add_column("Name", style="white")
                table.add_column("Details", style="dim")

                for agent_id in core_agents:
                    table.add_row("Core", agent_id, "permanent")
                for agent_id in worker_agents:
                    table.add_row("Worker", agent_id, "permanent")
                for agent_id, info in temp_agents:
                    name = info.get("name", agent_id)
                    details = info.get("purpose", "temporary agent")
                    table.add_row("Dynamic", name, details)

                console.print(table)
                console.print()
            except Exception:
                agents = await list_agents(self.db)
                if not agents:
                    console.print("[dim]No agents registered.[/dim]\n")
                    return
                table = _table("Registered Agents")
                table.add_column("Name", style="agent")
                table.add_column("Tier", style="yellow")
                table.add_column("Uses", style="dim", justify="right")
                for agent in agents:
                    table.add_row(agent["name"], agent["risk_tier"], str(agent["use_count"]))
                console.print(table)
                console.print()

        elif command == "/skills":
            skills = await list_skills(self.db)
            if not skills:
                console.print("[dim]No skills learned yet.[/dim]\n")
                return
            table = _table("Learned Skills")
            table.add_column("Name", style="agent")
            table.add_column("Confidence", style="green", justify="right")
            for s in skills:
                table.add_row(s["name"], f"{s['confidence']:.0%}")
            console.print(table)
            console.print()

        elif command == "/model":
            console.print(f"[bold]Current model:[/bold] [code]{QWEN_MODEL}[/code]\n")

        elif command == "/resume":
            if arg:
                self.session_id = arg
                self.memory.clear()
                try:
                    from hive.storage import create_session
                    await create_session(self.db, self.session_id, QWEN_MODEL)
                except Exception:
                    pass
                console.print(f"[success]Done.[/success] Resumed session: [code]{arg}[/code]\n")
            else:
                console.print("[bold yellow]Usage:[/bold yellow] /resume <session_id>\n")

        elif command == "/status":
            try:
                from hive.agents.leader import get_hive_status
                from hive.core.message_bus import get_bus
                from hive.core.economy import economy

                hive_status = get_hive_status()
                bus = get_bus()

                table = _table("System Status")
                table.add_column("Component", style="header")
                table.add_column("Value", style="white")

                table.add_row("Bus Messages", str(bus.message_count()))
                table.add_row("Registered Agents", ", ".join(bus.list_agents().keys()))
                table.add_row("Active Tasks", str(hive_status.get("active_tasks", 0)))
                table.add_row("Budget Remaining", f"{economy.balance} credits")

                type_counts = bus.type_counts()
                if type_counts:
                    for msg_type, count in type_counts.items():
                        table.add_row(f"Messages ({msg_type})", str(count))

                console.print(table)
                console.print()
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif command == "/swarm":
            self._force_swarm = True
            console.print("[success]Done.[/success] Next task will use swarm mode.\n")

        elif command == "/cleanup":
            try:
                from hive.agents.cleanup_crew import cleanup_crew
                with console.status("[thinking]✢ Scanning agents...[/thinking]", spinner="dots"):
                    result = cleanup_crew.run_full_cleanup()

                table = _table("Cleanup Results")
                table.add_column("Metric", style="header")
                table.add_column("Value", style="white")

                table.add_row("Agents Scanned", str(result.get("decisions_total", 0)))
                table.add_row("Agents Archived", str(result.get("agents_archived", 0)))
                table.add_row("Agents Deleted", str(result.get("agents_deleted", 0)))
                table.add_row("Memory Freed", f"{result.get('total_memory_freed_mb', 0)} MB")
                table.add_row("Credits Saved", str(result.get("total_cost_saved", 0)))

                console.print(table)
                console.print()
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif command == "/create-agent":
            if not arg:
                console.print("[bold yellow]Usage:[/bold yellow] /create-agent <task description>\n")
                console.print("[dim]Example: /create-agent Analyze Kubernetes security best practices[/dim]\n")
                return
            try:
                from hive.agents.agent_forge import forge_task
                with console.status("[thinking]✢ Forging specialist agent...[/thinking]", spinner="dots"):
                    result = await forge_task(arg, ["specialist"])

                if result.get("created"):
                    designed = result.get("designed", {})
                    console.print(f"\n[success]Agent created![/success]")
                    console.print(f"  Name: [bold]{designed.get('name', 'Unknown')}[/bold]")
                    console.print(f"  Purpose: {designed.get('purpose', 'N/A')}")
                    console.print(f"  Skills: {', '.join(designed.get('skills', []))}")
                    console.print(f"  ID: [code]{result.get('agent_id', 'N/A')}[/code]\n")
                else:
                    console.print(f"[yellow]Agent not created:[/yellow] {result.get('reason', 'Unknown')}\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown command: [cyan]{command}[/cyan]\n")

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
                user_input = await _prompt_async()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye.[/dim]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input)
                continue

            console.print()
            console.print("[thinking]✢ Thought:[/thinking] [muted]0.0s[/muted]\n")
            console.print(f"[white]{user_input}[/white]")
            console.print(f"\n[status]▣ HIVE[/status] [muted]· test mode · 0.0s[/muted]")
            console.print("[dim]Set DASHSCOPE_API_KEY in .env for real responses.[/dim]\n")

            await add_message(self.db, self.session_id, "user", user_input)
            await add_message(self.db, self.session_id, "assistant", f"[TEST] {user_input}")

        await end_session(self.db, self.session_id)
