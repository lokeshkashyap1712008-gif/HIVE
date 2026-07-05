"""Theme system — configurable colors for the HIVE CLI."""

import os
from rich.theme import Theme
from rich.console import Console

DEFAULT_COLORS = {
    "banner": "bold #F7F1E3",
    "banner.shadow": "#B45309",
    "accent": "#F6AD55",
    "accent.soft": "#D6BCFA",
    "muted": "#8B949E",
    "surface": "#161B22",
    "border": "#30363D",
    "dim": "dim #8B949E",
    "success": "bold green",
    "warning": "bold yellow",
    "error": "bold red",
    "agent": "bold #F6AD55",
    "tool": "#63B3ED",
    "user.input": "bold white",
    "permission": "bold yellow",
    "header": "bold #D6BCFA",
    "link": "bold blue",
    "code": "#D6BCFA",
    "prompt": "bold #D6BCFA",
    "prompt.dim": "#6E7681",
    "thinking": "bold #F6AD55",
    "status": "bold #63B3ED",
}


def get_colors() -> dict:
    colors = DEFAULT_COLORS.copy()
    for key in DEFAULT_COLORS:
        env_key = f"HIVE_COLOR_{key.upper().replace('.', '_')}"
        env_val = os.environ.get(env_key)
        if env_val:
            colors[key] = env_val
    return colors


def build_theme() -> Theme:
    colors = get_colors()
    return Theme(colors)


def get_console() -> Console:
    return Console(theme=build_theme(), highlight=False, markup=True)
