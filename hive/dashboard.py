"""
HIVE OS - Split Dashboard
70% normal CLI output + 30% pixel art swarm animation.
"""

import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from rich import box

from hive.swarm_viz import get_swarm_viz, AgentSprite

console = Console(force_terminal=True)


@dataclass
class Event:
    ts: float
    kind: str      # create, work, done, fail, delete, spend, earn, task, msg
    agent: str
    detail: str
    color: str = "white"


class Dashboard:
    def __init__(self):
        # Economy
        self.budget = 1000
        self.spent = 0
        
        # Agents
        self.agents: dict[str, dict] = {}
        self.total_created = 0
        self.total_deleted = 0
        
        # Events (kept for leader reference, not displayed)
        self.events: list[Event] = []
        
        # State
        self.task = ""
        self.status = "idle"
        self.task_start = 0.0
        self.subtasks_done = 0
        self.subtasks_total = 0
        self.leader_mode = ""
        
        # Viz reference
        self.viz = get_swarm_viz()

    # ── Economy ──────────────────────────────────────────────────
    def spend(self, amount: int, reason: str):
        self.spent += amount
        self.viz.show_credit_flash(f"-{amount}cr {reason[:15]}")
    
    def earn(self, amount: int, reason: str):
        self.spent -= amount
        self.viz.show_credit_flash(f"+{amount}cr {reason[:15]}")
    
    @property
    def remaining(self):
        return self.budget - self.spent

    # ── Agent Lifecycle ──────────────────────────────────────────
    def agent_spawn(self, agent_id: str, kind: str = "worker"):
        self.agents[agent_id] = {"kind": kind, "status": "spawning", "started": time.time()}
        self.total_created += 1
        self.viz.agent_spawn(agent_id, kind)
    
    def agent_work(self, agent_id: str, task: str = ""):
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = "working"
        self.viz.agent_work(agent_id, task)
    
    def agent_done(self, agent_id: str):
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = "done"
        self.viz.agent_done(agent_id)
    
    def agent_fail(self, agent_id: str, reason: str = ""):
        if agent_id in self.agents:
            self.agents[agent_id]["status"] = "failed"
        self.viz.agent_fail(agent_id, reason)
    
    def agent_delete(self, agent_id: str, reason: str = "cleanup"):
        self.agents.pop(agent_id, None)
        self.total_deleted += 1
        self.viz.remove_agent(agent_id)
    
    def clear_done_agents(self):
        to_remove = [aid for aid, a in self.agents.items() if a["status"] in ("done", "failed")]
        for aid in to_remove:
            self.agent_delete(aid, "task complete")

    # ── Task State ───────────────────────────────────────────────
    def set_task(self, task: str):
        self.task = task
        self.task_start = time.time()
        self.subtasks_done = 0
        self.subtasks_total = 0
    
    def set_status(self, status: str):
        self.status = status
    
    def subtask_progress(self, done: int, total: int):
        self.subtasks_done = done
        self.subtasks_total = total

    # ── Rendering ────────────────────────────────────────────────
    def _elapsed(self) -> str:
        if not self.task_start:
            return "0.0s"
        s = time.time() - self.task_start
        if s < 60:
            return f"{s:.1f}s"
        return f"{s/60:.1f}m"
    
    def render_cli_area(self) -> Panel:
        """Render the left 70% - status + task info."""
        t = Text()
        t.append(" HIVE OS ", style="bold white on bright_blue")
        t.append("  ")
        t.append(f" {self.status.upper()} ", style="bold black on bright_yellow" if self.status in ("spawning","running","synthesizing","decomposing") else "dim")
        t.append("  ")
        t.append(f" Mode: {self.leader_mode or 'auto'} ", style="cyan")
        t.append("  ")
        t.append(f" Time: {self._elapsed()} ", style="dim")
        t.append("  ")
        
        remaining = self.remaining
        rem_color = "green" if remaining > 500 else "yellow" if remaining > 200 else "red"
        t.append(f" Budget: {remaining:,} ", style=rem_color)
        
        return Panel(t, box=box.SIMPLE, style="blue", padding=(0, 0))
    
    def render_task_area(self) -> Panel:
        """Render current task info."""
        if not self.task:
            return Panel("[dim]Waiting for task...[/dim]", title="Task", box=box.ROUNDED)
        
        task_text = self.task[:60] + ("..." if len(self.task) > 60 else "")
        
        t = Text()
        t.append(f" {task_text}", style="bold cyan")
        if self.subtasks_total > 0:
            t.append(f"\n   {self.subtasks_done}/{self.subtasks_total} subtasks complete", style="dim")
        
        return Panel(t, title="[bold]Task[/bold]", border_style="cyan", box=box.ROUNDED)
    
    def render(self) -> Layout:
        """Build the 70/30 split layout."""
        layout = Layout()
        
        layout.split_row(
            Layout(name="left", ratio=7),
            Layout(name="right", ratio=3),
        )
        
        # Left side: status + task
        left = Layout()
        left.split_column(
            Layout(self.render_cli_area(), size=3, name="status"),
            Layout(self.render_task_area(), name="task"),
        )
        
        layout["left"].update(left)
        layout["right"].update(self.viz.render())
        
        return layout


# Singleton
_dashboard: Optional[Dashboard] = None

def get_dashboard() -> Dashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = Dashboard()
    return _dashboard
