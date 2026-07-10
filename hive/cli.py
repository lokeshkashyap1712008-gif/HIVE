"""CLI — main loop, input handling, output formatting."""

import sys
import uuid
import asyncio
import time
import json
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
from hive.dashboard import get_dashboard, Dashboard
from hive.tools import TOOLS

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Confirm, Prompt
from rich.text import Text
from rich.live import Live
from rich.layout import Layout

console = get_console()

SLASH_COMMANDS = [
    "/help", "/quit", "/exit", "/sessions", "/resume",
    "/agents", "/skills", "/model", "/clear", "/status", "/swarm",
    "/cleanup", "/create-agent", "/google-login", "/oauth",
    "/mcp", "/ppt",
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
        "[prompt]/ppt <topic>[/prompt]      Generate a polished PowerPoint deck\n"
        "[prompt]/mcp[/prompt]            Manage MCP servers (add, auth, tools)\n"
        "[prompt]/mcp auth \\[name][/prompt]    Authenticate OAuth MCP server\n"
        "[prompt]/google-login[/prompt]     Open browser for manual Google sign-in\n"
        "[prompt]/oauth \\[github|google][/prompt]  OAuth login flow\n"
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


async def cli_prompt_2fa(site: str, message: str) -> str | None:
    panel = Panel(
        f"[bold]Site:[/bold] {site}\n{message or 'Enter your verification code.'}",
        title="[permission]Verification Code Required[/permission]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)
    try:
        code = await asyncio.to_thread(
            Prompt.ask, "  Enter 6-digit code", password=True
        )
        return code.strip() if code else None
    except (EOFError, KeyboardInterrupt):
        return None


async def cli_prompt_checkout_confirm(amount: float, merchant: str, url: str) -> bool:
    amt = f"${amount:.2f}" if amount else "unknown amount"
    panel = Panel(
        f"[bold]Merchant:[/bold] {merchant}\n"
        f"[bold]Amount:[/bold] {amt}\n"
        f"[bold]URL:[/bold] {url or 'see browser'}",
        title="[permission]Confirm Purchase[/permission]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)
    try:
        return await asyncio.to_thread(
            Confirm.ask, f"  Place order for {amt}?", default=False
        )
    except (EOFError, KeyboardInterrupt):
        return False


async def cli_prompt_captcha_handoff(site: str, url: str) -> bool:
    panel = Panel(
        f"[bold]Site:[/bold] {site}\n"
        f"[bold]URL:[/bold] {url}\n\n"
        "Solve the CAPTCHA in the browser window, then press Enter here.",
        title="[permission]CAPTCHA — Human Required[/permission]",
        border_style="magenta",
        box=box.ROUNDED,
        padding=(1, 2),
    )
    console.print(panel)
    try:
        await asyncio.to_thread(input, "  Press Enter when CAPTCHA is solved... ")
        return True
    except (EOFError, KeyboardInterrupt):
        return False


def _register_interactive_handlers():
    from hive.interactive import register_handlers
    register_handlers(
        prompt_2fa=cli_prompt_2fa,
        prompt_checkout_confirm=cli_prompt_checkout_confirm,
        prompt_captcha_handoff=cli_prompt_captcha_handoff,
    )


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
        _register_interactive_handlers()

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

        # Close browser pool to kill any open Chrome windows
        try:
            from hive.browser.pool import get_pool
            pool = get_pool()
            await pool.close_all()
        except Exception:
            pass

    async def _handle_message(self, text: str):
        max_retries = 2
        dash = get_dashboard()
        viz = dash.viz
        
        for attempt in range(max_retries + 1):
            try:
                started = time.perf_counter()
                force_swarm = self._force_swarm
                self._force_swarm = False

                # Setup dashboard state
                dash.set_task(text)
                dash.leader_mode = "swarm" if force_swarm else "auto"
                dash.set_status("routing")
                
                # Create the 70/30 split layout
                layout = Layout()
                layout.split_row(
                    Layout(name="left", ratio=7),
                    Layout(name="right", ratio=3),
                )
                
                left_layout = Layout()
                left_layout.split_column(
                    Layout(dash.render_cli_area(), size=3, name="status"),
                    Layout(dash.render_task_area(), name="task"),
                )
                layout["left"].update(left_layout)
                layout["right"].update(viz.render())
                
                # Show live split layout during processing
                live = Live(layout, console=console, refresh_per_second=4, transient=False)
                live.start()
                
                try:
                    # Get streaming response
                    response = await self._handle_message_streaming(
                        text, session_id=self.session_id, memory=self.memory,
                        db=self.db, force_swarm=force_swarm, live=live, dash=dash, layout=layout
                    )
                finally:
                    live.stop()

                elapsed = time.perf_counter() - started
                await add_message(self.db, self.session_id, "user", text)
                await add_message(self.db, self.session_id, "assistant", response)
                
                console.print(f"\n[status]▣ HIVE[/status] [muted]· {QWEN_MODEL} · {elapsed:.1f}s[/muted]")
                console.print()
                return
            except Exception as e:
                if attempt < max_retries:
                    console.print(f"[yellow]Retrying... ({attempt + 1}/{max_retries})[/yellow]")
                    await asyncio.sleep(1)
                else:
                    console.print(f"\n[bold red]Error:[/bold red] {e}\n")
                    console.print("[dim]Tip: Try rephrasing your message or use /swarm for complex tasks.[/dim]\n")

    async def _handle_message_streaming(self, text: str, session_id: str, memory, db,
                                         force_swarm: bool, live: Live, dash, layout: Layout) -> str:
        """Handle message with streaming output."""
        viz = dash.viz
        
        # Always use swarm mode for visualization
        mode = "swarm"
        dash.leader_mode = mode
        dash.set_status("spawning")
        
        # Update layout initially
        layout["right"].update(viz.render())
        live.update(layout)
        
        # Run swarm task - dashboard updates via events in leader.py
        # The leader.py will call dash.agent_spawn, dash.agent_work, etc.
        # which update the viz. We need to refresh the Live display.
        
        # Create a background task to refresh the display
        async def refresh_loop():
            while True:
                await asyncio.sleep(0.3)  # Refresh every 300ms
                layout["right"].update(viz.render())
                live.update(layout)
        
        refresh_task = asyncio.create_task(refresh_loop())
        
        try:
            response = await self.leader._run_swarm_task(text)
        finally:
            refresh_task.cancel()
            try:
                await refresh_task
            except asyncio.CancelledError:
                pass
        
        # Final update
        layout["right"].update(viz.render())
        live.update(layout)
        
        return response

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
                table.add_row("Budget Remaining", f"{economy.budget.available} credits")

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

        elif command == "/oauth":
            platform = (arg or "github").lower().strip()
            if platform not in ("github", "google"):
                console.print("[bold yellow]Usage:[/bold yellow] /oauth github  or  /oauth google\n")
                return
            console.print(f"[cyan]Starting OAuth for {platform}...[/cyan]")
            console.print("[dim]A browser window will open. Authorize HIVE, then return here.[/dim]\n")
            try:
                from hive.browser.oauth import start_oauth
                result = await start_oauth(platform)
                if result.get("status") == "completed":
                    console.print(f"[success]OAuth complete![/success] User: {result.get('user_id')}")
                    console.print(f"  Session ID: [code]{result.get('session_id')}[/code]\n")
                else:
                    msg = result.get("reason") or result.get("instruction") or str(result)
                    console.print(f"[yellow]{msg}[/yellow]\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif command == "/google-login":
            email = arg.strip() if arg else None
            console.print("[cyan]Opening Google sign-in in a visible browser...[/cyan]")
            console.print("[dim]Log in manually (CAPTCHA, 2FA OK). HIVE saves your session when done.[/dim]\n")
            try:
                from hive.browser.google_login import run_google_login
                result = await run_google_login(email=email)
                if result.get("status") == "completed":
                    console.print(f"[success]{result['message']}[/success]")
                    console.print(f"  Email: {result.get('email', 'unknown')}")
                    console.print(f"  Session: [code]{result.get('session_name')}[/code]\n")
                else:
                    console.print(f"[yellow]{result.get('message', result)}[/yellow]\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif command == "/mcp":
            await self._handle_mcp_command(arg)

        elif command == "/ppt":
            topic = arg.strip()
            if not topic:
                console.print("[bold yellow]Usage:[/bold yellow] /ppt <topic> [output.pptx]\n")
                return
            output_path = None
            if " " in topic:
                parts = topic.split(None, 1)
                topic = parts[0]
                output_path = parts[1]
            else:
                output_path = None
            try:
                from hive.presentation import build_presentation
                with console.status("[thinking]✢ Crafting presentation...[/thinking]", spinner="dots"):
                    result = build_presentation(topic, output_path=output_path, slide_count=6, use_llm=False)
                console.print(f"[success]Presentation created![/success] {result}\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        else:
            console.print(f"[bold red]Error:[/bold red] Unknown command: [cyan]{command}[/cyan]\n")

    async def _handle_mcp_command(self, arg: str):
        """Handle /mcp commands for MCP server management."""
        from hive.mcp.config import mcp_config, MCPServerConfig, has_stored_token, delete_mcp_token
        from hive.mcp.client import mcp_client
        from hive.mcp.bridge import mcp_bridge
        from hive.tools import register_mcp_tools, unregister_mcp_tools

        parts = arg.split(maxsplit=2) if arg else []
        subcommand = parts[0] if parts else ""

        if not subcommand or subcommand == "status":
            # /mcp or /mcp status — show all servers
            servers = mcp_config.list_servers()
            if not servers:
                console.print("[dim]No MCP servers configured.[/dim]\n")
                console.print("[muted]Add a server with:[/muted] [prompt]/mcp add <name> <url>[/prompt]\n")
                return

            table = _table("MCP Servers")
            table.add_column("Name", style="agent")
            table.add_column("URL", style="dim", max_width=35)
            table.add_column("Auth", style="white")
            table.add_column("Status", style="white")
            table.add_column("Tools", style="green", justify="right")

            for server in servers:
                is_connected = mcp_client.is_connected(server.name)
                if server.auth_type == "oauth":
                    auth = "[yellow]OAuth[/yellow]" if has_stored_token(server.name) else "[red]OAuth (not authed)[/red]"
                elif server.headers.get("Authorization"):
                    auth = "[green]Token[/green]"
                else:
                    auth = "[dim]none[/dim]"

                if is_connected:
                    status = "[green]● connected[/green]"
                elif not server.enabled:
                    status = "[yellow]○ disabled[/yellow]"
                else:
                    status = "[red]○ offline[/red]"

                tool_count = len(mcp_bridge.get_tools_for_server(server.name)) if is_connected else "—"
                table.add_row(server.name, server.url, auth, status, str(tool_count))

            console.print(table)
            console.print()

        elif subcommand == "add":
            # /mcp add <name> <url> [auth_token]
            if len(parts) < 3:
                console.print("[bold yellow]Usage:[/bold yellow] /mcp add <name> <url> [auth_token]\n")
                console.print("[dim]Examples:[/dim]")
                console.print("  [prompt]/mcp add myserver https://my-mcp-server.com/mcp my-api-key[/prompt]")
                console.print("  [prompt]/mcp add gmail https://gmailmcp.googleapis.com/mcp[/prompt] [dim](OAuth)[/dim]\n")
                return

            name = parts[1]
            url = parts[2]
            auth_token = parts[3] if len(parts) > 3 else None

            # Detect Google MCP servers — auto-enable OAuth
            is_google = "googleapis.com" in url
            if is_google:
                console.print(f"[cyan]Detected Google MCP server[/cyan]")
                console.print("[dim]This server requires OAuth authentication.[/dim]\n")

                # Prompt for OAuth credentials
                from rich.prompt import Prompt
                client_id = Prompt.ask("  Enter your Google OAuth Client ID")
                client_secret = Prompt.ask("  Enter your Google OAuth Client Secret", password=True)

                if not client_id or not client_secret:
                    console.print("[bold red]Error:[/bold red] Client ID and secret are required for Google MCP servers.\n")
                    return

                config = MCPServerConfig(
                    name=name,
                    url=url,
                    auth_type="oauth",
                    oauth_client_id=client_id,
                    oauth_client_secret=client_secret,
                )
            else:
                headers = {}
                if auth_token:
                    headers["Authorization"] = f"Bearer {auth_token}"
                config = MCPServerConfig(name=name, url=url, headers=headers)

            success, msg = mcp_config.add_server(config)
            if not success:
                console.print(f"[bold red]Error:[/bold red] {msg}\n")
                return

            if is_google:
                # Run OAuth flow
                console.print(f"[cyan]Starting OAuth authentication...[/cyan]")
                console.print("[dim]A browser window will open. Log in and grant permissions.[/dim]\n")
                try:
                    auth_ok, auth_msg = await mcp_client.authenticate_oauth(config)
                    if not auth_ok:
                        console.print(f"[bold red]Authentication failed:[/bold red] {auth_msg}\n")
                        return
                    console.print(f"[success]Authentication successful![/success]\n")
                except Exception as e:
                    console.print(f"[bold red]Auth error:[/bold red] {e}\n")
                    return

            # Connect
            console.print(f"[cyan]Connecting to {name}...[/cyan]")
            try:
                success, connect_msg = await mcp_client.connect(config)
                if not success:
                    console.print(f"[yellow]Config saved but connection failed:[/yellow] {connect_msg}\n")
                    return

                # Discover tools
                ok, tools = await mcp_client.list_tools(name)
                if ok and tools:
                    from hive.mcp.bridge import convert_mcp_tool_to_hive
                    mcp_tools = {}
                    for tool in tools:
                        hive_name, hive_tool = convert_mcp_tool_to_hive(name, tool)
                        mcp_tools[hive_name] = hive_tool
                    register_mcp_tools(mcp_tools)
                    mcp_bridge._server_tools[name] = list(mcp_tools.keys())
                    for hn in mcp_tools:
                        mcp_bridge._tool_map[hn] = (name, tool["name"])

                    console.print(f"[success]Connected![/success] {len(tools)} tools available\n")
                    for tool in tools:
                        console.print(f"  [dim]•[/dim] {tool['name']}: {tool.get('description', '')[:60]}")
                    console.print()
                else:
                    console.print(f"[success]Connected![/success] No tools found\n")

            except Exception as e:
                console.print(f"[yellow]Connection error:[/yellow] {e}\n")

        elif subcommand == "auth":
            # /mcp auth <name> [--logout]
            if len(parts) < 2:
                console.print("[bold yellow]Usage:[/bold yellow] /mcp auth <name> [--logout]\n")
                console.print("[dim]Authenticate an OAuth-protected MCP server.[/dim]\n")
                return

            name = parts[1]
            logout = "--logout" in arg

            config = mcp_config.get_server(name)
            if not config:
                console.print(f"[bold red]Error:[/bold red] Server '{name}' not found. Use /mcp add first.\n")
                return

            if logout:
                delete_mcp_token(name)
                if mcp_client.is_connected(name):
                    await mcp_client.disconnect(name)
                    unregister_mcp_tools(name)
                console.print(f"[success]Logged out from {name}.[/success] Tokens removed.\n")
                return

            if config.auth_type != "oauth":
                console.print(f"[dim]Server '{name}' does not use OAuth.[/dim]\n")
                return

            # Disconnect if currently connected
            if mcp_client.is_connected(name):
                await mcp_client.disconnect(name)
                unregister_mcp_tools(name)

            console.print(f"[cyan]Starting OAuth authentication for {name}...[/cyan]")
            console.print("[dim]A browser window will open. Log in and grant permissions.[/dim]\n")
            try:
                auth_ok, auth_msg = await mcp_client.authenticate_oauth(config)
                if not auth_ok:
                    console.print(f"[bold red]Authentication failed:[/bold red] {auth_msg}\n")
                    return
                console.print(f"[success]Authentication successful![/success]\n")
            except Exception as e:
                console.print(f"[bold red]Auth error:[/bold red] {e}\n")
                return

            # Reconnect
            console.print(f"[cyan]Connecting to {name}...[/cyan]")
            try:
                success, connect_msg = await mcp_client.connect(config)
                if success:
                    ok, tools = await mcp_client.list_tools(name)
                    if ok and tools:
                        from hive.mcp.bridge import convert_mcp_tool_to_hive
                        mcp_tools = {}
                        for tool in tools:
                            hive_name, hive_tool = convert_mcp_tool_to_hive(name, tool)
                            mcp_tools[hive_name] = hive_tool
                        register_mcp_tools(mcp_tools)
                        mcp_bridge._server_tools[name] = list(mcp_tools.keys())
                        for hn in mcp_tools:
                            mcp_bridge._tool_map[hn] = (name, tool["name"])
                        console.print(f"[success]Connected![/success] {len(tools)} tools available\n")
                    else:
                        console.print(f"[success]Connected![/success]\n")
                else:
                    console.print(f"[bold red]Error:[/bold red] {connect_msg}\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif subcommand == "remove":
            # /mcp remove <name>
            if len(parts) < 2:
                console.print("[bold yellow]Usage:[/bold yellow] /mcp remove <name>\n")
                return

            name = parts[1]
            if mcp_client.is_connected(name):
                await mcp_client.disconnect(name)
                unregister_mcp_tools(name)

            # Also remove tokens
            delete_mcp_token(name)

            success, msg = mcp_config.remove_server(name)
            if success:
                console.print(f"[success]{msg}[/success]\n")
            else:
                console.print(f"[bold red]Error:[/bold red] {msg}\n")

        elif subcommand == "connect":
            # /mcp connect <name>
            if len(parts) < 2:
                console.print("[bold yellow]Usage:[/bold yellow] /mcp connect <name>\n")
                return

            name = parts[1]
            config = mcp_config.get_server(name)
            if not config:
                console.print(f"[bold red]Error:[/bold red] Server '{name}' not found. Use /mcp add first.\n")
                return

            if mcp_client.is_connected(name):
                console.print(f"[dim]Already connected to {name}.[/dim]\n")
                return

            console.print(f"[cyan]Connecting to {name}...[/cyan]")
            try:
                success, msg = await mcp_client.connect(config)
                if success:
                    # Discover tools
                    ok, tools = await mcp_client.list_tools(name)
                    if ok and tools:
                        from hive.mcp.bridge import convert_mcp_tool_to_hive
                        mcp_tools = {}
                        for tool in tools:
                            hive_name, hive_tool = convert_mcp_tool_to_hive(name, tool)
                            mcp_tools[hive_name] = hive_tool
                        register_mcp_tools(mcp_tools)
                        mcp_bridge._server_tools[name] = list(mcp_tools.keys())
                        for hn in mcp_tools:
                            mcp_bridge._tool_map[hn] = (name, tool["name"])
                        console.print(f"[success]Connected![/success] {len(tools)} tools available\n")
                    else:
                        console.print(f"[success]Connected![/success]\n")
                else:
                    console.print(f"[bold red]Error:[/bold red] {msg}\n")
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}\n")

        elif subcommand == "disconnect":
            # /mcp disconnect <name>
            if len(parts) < 2:
                console.print("[bold yellow]Usage:[/bold yellow] /mcp disconnect <name>\n")
                return

            name = parts[1]
            success, msg = await mcp_client.disconnect(name)
            if success:
                unregister_mcp_tools(name)
                console.print(f"[success]{msg}[/success]\n")
            else:
                console.print(f"[bold red]Error:[/bold red] {msg}\n")

        elif subcommand == "tools":
            # /mcp tools [server_name]
            server_name = parts[1] if len(parts) > 1 else None

            if server_name:
                # Show tools for specific server
                tool_names = mcp_bridge.get_tools_for_server(server_name)
                if not tool_names:
                    console.print(f"[dim]No tools found for '{server_name}'.[/dim]\n")
                    return

                table = _table(f"MCP Tools: {server_name}")
                table.add_column("Tool", style="code")
                table.add_column("Description", style="white", max_width=50)

                for hn in tool_names:
                    _, original = mcp_bridge._tool_map.get(hn, ("", hn))
                    spec = TOOLS.get(hn, {})
                    desc = spec.get("description", "")
                    # Remove the [MCP: ...] suffix for cleaner display
                    if " [MCP:" in desc:
                        desc = desc[:desc.index(" [MCP:")]
                    table.add_row(original, desc)

                console.print(table)
                console.print()
            else:
                # Show all MCP tools
                all_tools = mcp_bridge.get_hive_tools()
                if not all_tools:
                    console.print("[dim]No MCP tools available.[/dim]\n")
                    console.print("[muted]Connect to an MCP server with:[/muted] /mcp connect <name>\n")
                    return

                table = _table("All MCP Tools")
                table.add_column("Server", style="agent")
                table.add_column("Tool", style="code")
                table.add_column("Description", style="white", max_width=45)

                for hn, spec in sorted(all_tools.items()):
                    server = mcp_bridge.get_server_for_tool(hn) or "?"
                    _, original = mcp_bridge._tool_map.get(hn, ("", hn))
                    desc = spec.get("description", "")
                    if " [MCP:" in desc:
                        desc = desc[:desc.index(" [MCP:")]
                    table.add_row(server, original, desc[:60])

                console.print(table)
                console.print(f"  [dim]{len(all_tools)} tools from {len(mcp_bridge._server_tools)} servers[/dim]\n")

        elif subcommand == "resources":
            # /mcp resources [server_name]
            server_name = parts[1] if len(parts) > 1 else None
            servers = [server_name] if server_name else list(mcp_bridge._server_tools.keys())

            if not servers:
                console.print("[dim]No connected MCP servers.[/dim]\n")
                return

            for srv in servers:
                ok, resources = await mcp_client.list_resources(srv)
                if not ok:
                    console.print(f"[dim]{srv}: {resources}[/dim]")
                    continue

                if resources:
                    console.print(f"\n[bold]{srv}[/bold] resources:")
                    for r in resources:
                        console.print(f"  [dim]•[/dim] {r.get('uri', '?')} — {r.get('name', '')}")

            console.print()

        else:
            console.print("[bold yellow]MCP Commands:[/bold yellow]\n")
            console.print("  [prompt]/mcp[/prompt]                          Show all MCP servers\n")
            console.print("  [prompt]/mcp add[/prompt] <name> <url> [token]  Add and connect to a server\n")
            console.print("  [prompt]/mcp auth[/prompt] <name>               Authenticate an OAuth server\n")
            console.print("  [prompt]/mcp auth[/prompt] <name> --logout      Clear stored tokens\n")
            console.print("  [prompt]/mcp remove[/prompt] <name>              Remove an MCP server\n")
            console.print("  [prompt]/mcp connect[/prompt] <name>             Connect to a server\n")
            console.print("  [prompt]/mcp disconnect[/prompt] <name>          Disconnect from a server\n")
            console.print("  [prompt]/mcp tools[/prompt] [server]             List MCP tools\n")
            console.print("  [prompt]/mcp resources[/prompt] [server]         List MCP resources\n")
            console.print("  [prompt]/mcp status[/prompt]                     Show connection status\n")
            console.print()

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


class HiveServer:
    """JSON-lines server mode for Ink frontend.

    Uses non-blocking stdin via asyncio to avoid blocking the event loop.
    Permission responses are routed via a pending queue.
    """

    def __init__(self):
        ensure_dirs()
        self.session_id = str(uuid.uuid4())[:8]
        self.memory = ShortTermMemory()
        self.leader = None
        self.db = None
        self.running = True
        self._pending_permissions: dict[str, asyncio.Future] = {}
        self._pending_interactive: dict[str, asyncio.Future] = {}
        self._task_start = 0.0

    def _send(self, msg: dict):
        """Send a JSON message to stdout (to Ink frontend)."""
        import json
        try:
            sys.stdout.write(json.dumps(msg) + "\n")
            sys.stdout.flush()
        except (BrokenPipeError, OSError):
            self.running = False

    def _format_elapsed(self) -> str:
        """Format elapsed time since task started."""
        if not self._task_start:
            return "0.0s"
        s = time.time() - self._task_start
        if s < 60:
            return f"{s:.1f}s"
        return f"{s / 60:.1f}m"

    async def _recv_async(self) -> dict | None:
        """Non-blocking read from stdin using asyncio."""
        loop = asyncio.get_event_loop()
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                return None
            return json.loads(line.strip())
        except (json.JSONDecodeError, EOFError, ValueError):
            return None
        except Exception:
            return None

    async def start(self):
        await init_db()
        self.db = await get_db()
        await create_session(self.db, self.session_id, QWEN_MODEL)

        llm = QwenClient(api_key=DASHSCOPE_API_KEY, model=QWEN_MODEL)
        self.leader = Leader(llm)

        # Register interactive handlers for the Ink frontend.
        self._register_interactive_handlers()

        # Validate API key on first use (lazy) — skip upfront ping to avoid timeout
        self._api_key_validated = False

        # Patch dashboard to forward messages to frontend
        self._patch_dashboard()

        # Signal ready immediately
        self._send({"type": "ready"})

        # Start message reader task
        reader_task = asyncio.create_task(self._read_loop())

        try:
            await reader_task
        except asyncio.CancelledError:
            pass
        finally:
            await end_session(self.db, self.session_id)
            self.leader.shutdown()
            await self.db.close()

    def _register_interactive_handlers(self) -> None:
        """Register human-in-the-loop prompt handlers for Ink frontend."""
        import asyncio as _asyncio
        import uuid as _uuid
        from hive.interactive import register_handlers

        async def prompt_2fa_code(site: str, message: str):
            req_id = str(_uuid.uuid4())[:8]
            loop = _asyncio.get_event_loop()
            fut = loop.create_future()
            self._pending_interactive[req_id] = fut
            self._send(
                {
                    "type": "interactive_prompt",
                    "kind": "2fa",
                    "request_id": req_id,
                    "site": site,
                    "message": message or "",
                }
            )
            try:
                return await _asyncio.wait_for(fut, timeout=600.0)
            except _asyncio.TimeoutError:
                self._pending_interactive.pop(req_id, None)
                return None

        async def prompt_checkout_confirm(amount: float, merchant: str, url: str = ""):
            req_id = str(_uuid.uuid4())[:8]
            loop = _asyncio.get_event_loop()
            fut = loop.create_future()
            self._pending_interactive[req_id] = fut
            self._send(
                {
                    "type": "interactive_prompt",
                    "kind": "checkout_confirm",
                    "request_id": req_id,
                    "amount": amount,
                    "merchant": merchant,
                    "url": url or "",
                }
            )
            try:
                return bool(await _asyncio.wait_for(fut, timeout=600.0))
            except _asyncio.TimeoutError:
                self._pending_interactive.pop(req_id, None)
                return False

        async def prompt_captcha_handoff(site: str, url: str = ""):
            req_id = str(_uuid.uuid4())[:8]
            loop = _asyncio.get_event_loop()
            fut = loop.create_future()
            self._pending_interactive[req_id] = fut
            self._send(
                {
                    "type": "interactive_prompt",
                    "kind": "captcha_handoff",
                    "request_id": req_id,
                    "site": site,
                    "url": url or "",
                }
            )
            try:
                return bool(await _asyncio.wait_for(fut, timeout=600.0))
            except _asyncio.TimeoutError:
                self._pending_interactive.pop(req_id, None)
                return False

        register_handlers(
            prompt_2fa=prompt_2fa_code,
            prompt_checkout_confirm=prompt_checkout_confirm,
            prompt_captcha_handoff=prompt_captcha_handoff,
        )

    def _patch_dashboard(self):
        """Patch dashboard methods to forward messages to frontend."""
        from hive.dashboard import get_dashboard
        
        dash = get_dashboard()
        
        # Store original methods
        orig_agent_spawn = dash.agent_spawn
        orig_agent_work = dash.agent_work
        orig_agent_done = dash.agent_done
        orig_agent_fail = dash.agent_fail
        orig_spend = dash.spend
        orig_earn = dash.earn
        orig_set_status = dash.set_status
        orig_subtask_progress = dash.subtask_progress
        
        def patched_agent_spawn(agent_id, kind="worker"):
            orig_agent_spawn(agent_id, kind)
            self._send({"type": "agent_spawn", "agent_id": agent_id, "kind": kind})
        
        def patched_agent_work(agent_id, task=""):
            orig_agent_work(agent_id, task)
            self._send({"type": "agent_work", "agent_id": agent_id, "task": task})
        
        def patched_agent_done(agent_id):
            orig_agent_done(agent_id)
            self._send({"type": "agent_done", "agent_id": agent_id})
        
        def patched_agent_fail(agent_id, reason=""):
            orig_agent_fail(agent_id, reason)
            self._send({"type": "agent_fail", "agent_id": agent_id, "reason": reason})
        
        def patched_spend(amount, reason):
            orig_spend(amount, reason)
            self._send({"type": "spend", "amount": amount, "reason": reason})
        
        def patched_earn(amount, reason):
            orig_earn(amount, reason)
            self._send({"type": "earn", "amount": amount, "reason": reason})
        
        def patched_set_status(status):
            orig_set_status(status)
            self._send({"type": "status", "status": status})
        
        def patched_subtask_progress(done, total):
            orig_subtask_progress(done, total)
            self._send({"type": "subtask_progress", "done": done, "total": total})
        
        # Apply patches
        dash.agent_spawn = patched_agent_spawn
        dash.agent_work = patched_agent_work
        dash.agent_done = patched_agent_done
        dash.agent_fail = patched_agent_fail
        dash.spend = patched_spend
        dash.earn = patched_earn
        dash.set_status = patched_set_status
        dash.subtask_progress = patched_subtask_progress

    async def _read_loop(self):
        """Main message reading loop."""
        while self.running:
            msg = await self._recv_async()
            if msg is None:
                break

            msg_type = msg.get("type")

            if msg_type == "quit":
                break

            elif msg_type == "user_message":
                content = msg.get("content", "")
                if content.strip():
                    # Handle in background so we can keep reading messages
                    asyncio.create_task(self._handle_user_message(content))

            elif msg_type == "permission_response":
                # Route to waiting permission handler
                request_id = msg.get("request_id", "")
                decision = msg.get("decision", "denied")
                future = self._pending_permissions.pop(request_id, None)
                if future and not future.done():
                    future.set_result(decision)

            elif msg_type == "interactive_response":
                request_id = msg.get("request_id", "")
                result = msg.get("result")
                future = self._pending_interactive.pop(request_id, None)
                if future and not future.done():
                    future.set_result(result)

    async def _handle_user_message(self, text: str):
        """Process a user message and stream results back."""
        self._task_start = time.time()

        # Send initial status
        self._send({"type": "status", "status": "routing"})
        self._send({"type": "elapsed", "elapsed": "0.0s"})

        # Start elapsed timer
        elapsed_running = True

        async def update_elapsed():
            while elapsed_running:
                self._send({"type": "elapsed", "elapsed": self._format_elapsed()})
                await asyncio.sleep(0.5)

        elapsed_task = asyncio.create_task(update_elapsed())

        try:
            # Use the leader with streaming callbacks
            response = await self.leader.handle_message(
                user_message=text,
                session_id=self.session_id,
                memory=self.memory,
                db=self.db,
                on_tool_call=self._on_tool_call,
                on_permission=self._on_permission,
                on_text=self._on_text,
                force_swarm=False,
            )

            try:
                await add_message(self.db, self.session_id, "user", text)
                await add_message(self.db, self.session_id, "assistant", response)
            except Exception:
                pass  # DB errors should not crash the response

            self._send({"type": "response", "content": response})

        except Exception as e:
            self._send({"type": "error", "message": str(e)})
        finally:
            # Stop elapsed timer
            elapsed_running = False
            elapsed_task.cancel()
            try:
                await elapsed_task
            except asyncio.CancelledError:
                pass
            self._task_start = 0.0

    async def _on_tool_call(self, tool_name: str, args: dict):
        """Callback when agent calls a tool."""
        self._send({"type": "tool_call", "tool": tool_name, "args": args})
        self._send({"type": "status", "status": f"running {tool_name}"})

    async def _on_permission(self, tool_name: str, target: str, tier: str) -> str:
        """Callback when agent needs permission. Sends request and waits for response."""
        request_id = str(uuid.uuid4())[:8]

        # Create a future that the read loop will resolve
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_permissions[request_id] = future

        self._send({
            "type": "permission_request",
            "tool": tool_name,
            "target": target,
            "tier": tier,
            "request_id": request_id,
        })

        try:
            # Wait up to 120 seconds for user decision
            decision = await asyncio.wait_for(future, timeout=120.0)
            return decision
        except asyncio.TimeoutError:
            self._pending_permissions.pop(request_id, None)
            return "denied"

    async def _on_text(self, text: str):
        """Callback for streaming text output."""
        self._send({"type": "stream", "content": text})


if __name__ == "__main__":
    if "--server" in sys.argv:
        server = HiveServer()
        asyncio.run(server.start())
    else:
        cli = HiveCLI()
        asyncio.run(cli.start())
