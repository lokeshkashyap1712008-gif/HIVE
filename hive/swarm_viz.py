"""
HIVE OS - Swarm Visualizer
Pixel art ASCII animation of the agent swarm running in the terminal.
Renders a 30% panel showing bees spawning from a hive, working, and dying.
"""

import time
import math
from dataclasses import dataclass, field
from typing import Optional

from rich.text import Text
from rich.panel import Panel
from rich import box


# ── ASCII Sprites ────────────────────────────────────────────────

HIVE_FRAMES = [
    # Frame 0 - idle
    [
        "   /\\   ",
        "  /  \\  ",
        " /    \\ ",
        "/------\\",
        "| HIVE |",
        "+------+",
    ],
    # Frame 1 - pulse
    [
        "   /\\   ",
        "  /  \\  ",
        " / ** \\ ",
        "/------\\",
        "| HIVE |",
        "+------+",
    ],
]

BEE_IDLE = [
    " (\\ /) ",
    " (o.o) ",
    "  >v<  ",
]

BEE_SPAWN = [
    # Frame 0 - appears
    [
        "       ",
        "       ",
        " (o.o) ",
    ],
    # Frame 1 - moving down
    [
        "       ",
        " (o.o) ",
        "  / \\  ",
    ],
    # Frame 2 - landed
    [
        " (\\ /) ",
        " (o.o) ",
        "  >v<  ",
    ],
]

BEE_WORK = [
    # Frame 0 - working left
    [
        " (\\ /) ",
        " (O.O) ",
        " <<   ",
    ],
    # Frame 1 - working right
    [
        " (\\ /) ",
        " (O.O) ",
        "   >> ",
    ],
    # Frame 2 - thinking
    [
        " (\\ /) ",
        " (o.o) ",
        "  ... ",
    ],
]

BEE_DONE = [
    # Frame 0 - success flash
    [
        " (\\ /) ",
        " (^_^) ",
        "  + +  ",
    ],
    # Frame 1 - fading
    [
        "       ",
        " (^_^) ",
        "  + +  ",
    ],
    # Frame 2 - gone
    [
        "       ",
        "       ",
        "       ",
    ],
]

BEE_FAIL = [
    # Frame 0 - hurt
    [
        " (\\ /) ",
        " (x.x) ",
        "  ~ ~  ",
    ],
    # Frame 1 - dissolving
    [
        "       ",
        " (x.x) ",
        "  ~~   ",
    ],
    # Frame 2 - gone
    [
        "       ",
        "       ",
        "       ",
    ],
]

FORGE_SPRITE = [
    # Frame 0 - glow
    [
        " [=] ",
        " {F} ",
        " [=] ",
    ],
    # Frame 1 - create
    [
        " {*} ",
        " {F} ",
        " {*} ",
    ],
]

PARTICLES = [".", "*", "+", "~", "^", "`"]
PARTICLE_COLORS = ["dim", "yellow", "green", "cyan", "white", "red"]


@dataclass
class AgentSprite:
    """An animated agent in the swarm visualization."""
    agent_id: str
    kind: str  # worker, forge, cleanup, judge, safety
    status: str  # spawning, working, done, failed
    x: int = 0
    y: int = 0
    frame: int = 0
    started: float = 0.0
    task: str = ""
    particles: list = field(default_factory=list)


class SwarmVisualizer:
    """Pixel art visualization of the HIVE swarm."""
    
    def __init__(self, width: int = 28, height: int = 38):
        self.width = width
        self.height = height
        self.agents: list[AgentSprite] = []
        self.frame_count = 0
        self.last_frame_time = 0  # Initialize to 0 so first render always works
        self.hive_frame = 0
        self.particles: list[dict] = []  # floating particles
        self.credit_flash: Optional[str] = None
        self.credit_flash_time = 0
        self.status_text = "idle"
        self._last_render = None  # Initialize cache
        
        # Layout positions
        self.hive_x = width // 2 - 4
        self.hive_y = 1
        self.work_start_y = 10
        self.max_agents = 6  # max visible agents
    
    def _get_work_position(self, index: int) -> tuple[int, int]:
        """Get grid position for an agent at given index."""
        col = index % 3
        row = index // 3
        x = 2 + col * 9
        y = self.work_start_y + row * 6
        return x, y
    
    def agent_spawn(self, agent_id: str, kind: str = "worker"):
        """Add a new agent to the visualization."""
        if len(self.agents) >= self.max_agents:
            return
        
        # Find open slot
        used_slots = set()
        for a in self.agents:
            idx = self.agents.index(a)
            used_slots.add(idx)
        
        slot = 0
        while slot in used_slots and slot < self.max_agents:
            slot += 1
        
        x, y = self._get_work_position(slot)
        
        agent = AgentSprite(
            agent_id=agent_id,
            kind=kind,
            status="spawning",
            x=x,
            y=y,
            started=time.time(),
        )
        self.agents.append(agent)
        self.status_text = f"spawning {kind}"
    
    def agent_work(self, agent_id: str, task: str = ""):
        """Set agent to working state."""
        for a in self.agents:
            if a.agent_id == agent_id:
                a.status = "working"
                a.task = task[:20]
                a.frame = 0
                break
    
    def agent_done(self, agent_id: str):
        """Set agent to done state."""
        for a in self.agents:
            if a.agent_id == agent_id:
                a.status = "done"
                a.frame = 0
                break
    
    def agent_fail(self, agent_id: str, reason: str = ""):
        """Set agent to failed state."""
        for a in self.agents:
            if a.agent_id == agent_id:
                a.status = "failed"
                a.frame = 0
                break
    
    def remove_agent(self, agent_id: str):
        """Remove agent from visualization."""
        self.agents = [a for a in self.agents if a.agent_id != agent_id]
    
    def show_credit_flash(self, text: str):
        """Show a credit change flash."""
        self.credit_flash = text
        self.credit_flash_time = time.time()
    
    def _draw_hive(self, grid: list[list[str]], colors: list[list[str]]):
        """Draw the hive at the top."""
        frame_idx = self.hive_frame % len(HIVE_FRAMES)
        hive = HIVE_FRAMES[frame_idx]
        
        for dy, row in enumerate(hive):
            for dx, ch in enumerate(row):
                gx = self.hive_x + dx
                gy = self.hive_y + dy
                if 0 <= gx < self.width and 0 <= gy < self.height:
                    grid[gy][gx] = ch
                    colors[gy][gx] = "yellow" if ch in "/\\" else "bright_yellow" if ch == "*" else "white"
    
    def _draw_agent(self, grid: list[list[str]], colors: list[list[str]], agent: AgentSprite):
        """Draw an agent sprite."""
        elapsed = time.time() - agent.started
        
        if agent.status == "spawning":
            # Spawn animation: 3 frames
            frame_idx = min(int(elapsed * 4), 2)
            sprite = BEE_SPAWN[frame_idx]
            color = "cyan"
        elif agent.status == "working":
            # Work animation: bounce between frames
            frame_idx = int(elapsed * 3) % len(BEE_WORK)
            sprite = BEE_WORK[frame_idx]
            color = "green"
        elif agent.status == "done":
            # Done animation: 3 frames then remove
            frame_idx = min(int(elapsed * 5), 2)
            if frame_idx >= 2:
                return  # fully faded
            sprite = BEE_DONE[frame_idx]
            color = "bright_green"
        elif agent.status == "failed":
            # Fail animation: 3 frames then remove
            frame_idx = min(int(elapsed * 4), 2)
            if frame_idx >= 2:
                return
            sprite = BEE_FAIL[frame_idx]
            color = "red"
        else:
            sprite = BEE_IDLE
            color = "cyan"
        
        # Kind-specific coloring
        kind_colors = {
            "worker": "cyan",
            "forge": "bright_magenta",
            "cleanup": "red",
            "judge": "yellow",
            "safety": "red",
        }
        color = kind_colors.get(agent.kind, color)
        
        for dy, row in enumerate(sprite):
            for dx, ch in enumerate(row):
                gx = agent.x + dx
                gy = agent.y + dy
                if 0 <= gx < self.width and 0 <= gy < self.height and ch != " ":
                    grid[gy][gx] = ch
                    colors[gy][gx] = color
    
    def _draw_particles(self, grid: list[list[str]], colors: list[list[str]]):
        """Draw floating particles around working agents."""
        now = time.time()
        
        # Add new particles from working agents
        for agent in self.agents:
            if agent.status == "working" and now - agent.started > 0.5:
                if now - self.last_frame_time > 0.3:
                    import random
                    px = agent.x + random.randint(0, 6)
                    py = agent.y - 1
                    self.particles.append({
                        "x": px, "y": py,
                        "char": random.choice(PARTICLES),
                        "color": random.choice(PARTICLE_COLORS),
                        "born": now,
                        "life": 1.5,
                    })
        
        # Draw and cleanup particles
        alive = []
        for p in self.particles:
            age = now - p["born"]
            if age < p["life"]:
                # Float upward
                draw_y = p["y"] - int(age * 2)
                draw_x = p["x"]
                if 0 <= draw_x < self.width and 0 <= draw_y < self.height:
                    # Fade out
                    if age < p["life"] * 0.7:
                        grid[draw_y][draw_x] = p["char"]
                        colors[draw_y][draw_x] = p["color"]
                alive.append(p)
        self.particles = alive
    
    def _draw_work_lines(self, grid: list[list[str]], colors: list[list[str]]):
        """Draw dashed lines from hive to working agents."""
        if not self.agents:
            return
        
        hive_bottom = self.hive_y + 5
        for i, agent in enumerate(self.agents):
            if agent.status in ("working", "spawning"):
                # Draw vertical dashed line
                start_y = hive_bottom + 1
                end_y = agent.y - 1
                for y in range(start_y, min(end_y, self.height)):
                    if y % 2 == 0:
                        gx = self.hive_x + 4
                        if 0 <= gx < self.width and 0 <= y < self.height:
                            grid[y][gx] = "|"
                            colors[y][gx] = "dim"
    
    def _draw_status_bar(self, grid: list[list[str]], colors: list[list[str]]):
        """Draw status bar at bottom."""
        y = self.height - 1
        alive = sum(1 for a in self.agents if a.status in ("spawning", "working"))
        done = sum(1 for a in self.agents if a.status == "done")
        dead = sum(1 for a in self.agents if a.status == "failed")
        
        status = f" Q:1 W:{alive} D:{done} X:{dead}"
        for i, ch in enumerate(status):
            if i < self.width:
                grid[y][i] = ch
                colors[y][i] = "dim"
    
    def _draw_credit_flash(self, grid: list[list[str]], colors: list[list[str]]):
        """Show credit flash if active."""
        if not self.credit_flash:
            return
        
        elapsed = time.time() - self.credit_flash_time
        if elapsed > 2.0:
            self.credit_flash = None
            return
        
        text = self.credit_flash
        y = self.height - 2
        x = 1
        color = "red" if "-" in text else "green"
        
        for i, ch in enumerate(text):
            if x + i < self.width:
                grid[y][x + i] = ch
                colors[y][x + i] = color
    
    def render(self) -> Panel:
        """Render the current frame as a Rich Panel."""
        now = time.time()
        
        # Rate limit to ~4 FPS, but always render first frame
        if self._last_render is not None and (now - self.last_frame_time) < 0.25:
            return self._last_render
        
        self.last_frame_time = now
        self.frame_count += 1
        self.hive_frame = self.frame_count // 4
        
        # Initialize grid
        grid = [[" " for _ in range(self.width)] for _ in range(self.height)]
        colors = [["dim" for _ in range(self.width)] for _ in range(self.height)]
        
        # Draw components
        self._draw_work_lines(grid, colors)
        self._draw_hive(grid, colors)
        
        for agent in self.agents:
            self._draw_agent(grid, colors, agent)
        
        self._draw_particles(grid, colors)
        self._draw_status_bar(grid, colors)
        self._draw_credit_flash(grid, colors)
        
        # Build Rich Text
        text = Text()
        for y in range(self.height):
            for x in range(self.width):
                ch = grid[y][x]
                color = colors[y][x]
                text.append(ch, style=color)
            if y < self.height - 1:
                text.append("\n")
        
        # Clean up completed agents
        to_remove = []
        for a in self.agents:
            if a.status == "done" and time.time() - a.started > 1.5:
                to_remove.append(a.agent_id)
            elif a.status == "failed" and time.time() - a.started > 1.5:
                to_remove.append(a.agent_id)
        for aid in to_remove:
            self.remove_agent(aid)
        
        panel = Panel(
            text,
            title="[bold]Swarm[/bold]",
            border_style="green",
            box=box.ROUNDED,
            padding=(0, 0),
        )
        
        self._last_render = panel
        return panel


# Singleton
_viz: Optional[SwarmVisualizer] = None

def get_swarm_viz() -> SwarmVisualizer:
    global _viz
    if _viz is None:
        _viz = SwarmVisualizer()
    return _viz
