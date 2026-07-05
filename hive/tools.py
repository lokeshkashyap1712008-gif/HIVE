"""Tools — file, shell, git, web operations."""

import os
import asyncio
import time
import json
from pathlib import Path
import httpx
from rich.console import Console

console = Console()


# Tool registry with schemas for LLM function calling
TOOLS = {
    "read_file": {
        "description": "Read the contents of a file",
        "parameters": {
            "path": {"type": "string", "description": "File path to read"},
        },
    },
    "list_directory": {
        "description": "List contents of a directory",
        "parameters": {
            "path": {"type": "string", "description": "Directory path"},
        },
    },
    "search_content": {
        "description": "Search file contents using regex pattern",
        "parameters": {
            "pattern": {"type": "string", "description": "Regex pattern"},
            "path": {"type": "string", "description": "File or directory to search"},
            "include": {"type": "string", "description": "File glob pattern (e.g. *.py)"},
        },
    },
    "edit_file": {
        "description": "Edit a file by replacing text",
        "parameters": {
            "path": {"type": "string", "description": "File path"},
            "old": {"type": "string", "description": "Text to replace"},
            "new": {"type": "string", "description": "Replacement text"},
        },
    },
    "write_file": {
        "description": "Write content to a file",
        "parameters": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
        },
    },
    "run_command": {
        "description": "Run a shell command",
        "parameters": {
            "command": {"type": "string", "description": "Shell command to run"},
            "workdir": {"type": "string", "description": "Working directory (optional)"},
        },
    },
    "git_status": {
        "description": "Show git status",
        "parameters": {},
    },
    "git_diff": {
        "description": "Show git diff",
        "parameters": {
            "target": {"type": "string", "description": "Diff target (optional)"},
        },
    },
    "git_commit": {
        "description": "Create a git commit",
        "parameters": {
            "message": {"type": "string", "description": "Commit message"},
            "files": {"type": "string", "description": "Files to stage (space-separated)"},
        },
    },
    "web_fetch": {
        "description": "Fetch content from a URL",
        "parameters": {
            "url": {"type": "string", "description": "URL to fetch"},
        },
    },
}


async def execute_tool(tool_name: str, **kwargs) -> dict:
    """Execute a tool and return result."""
    start = time.time()
    try:
        detail = kwargs.get("path", kwargs.get("url", kwargs.get("command", "")))
        status_text = f"[dim]{tool_name}[/dim]"
        if detail:
            status_text += f" [dim]({detail[:40]})[/dim]"

        with console.status(status_text, spinner="dots"):
            if tool_name == "read_file":
                result = await _read_file(kwargs["path"])
            elif tool_name == "list_directory":
                result = await _list_directory(kwargs["path"])
            elif tool_name == "search_content":
                result = await _search_content(
                    kwargs["pattern"], kwargs["path"], kwargs.get("include", "*")
                )
            elif tool_name == "edit_file":
                result = await _edit_file(kwargs["path"], kwargs["old"], kwargs["new"])
            elif tool_name == "write_file":
                result = await _write_file(kwargs["path"], kwargs["content"])
            elif tool_name == "run_command":
                result = await _run_command(
                    kwargs["command"], kwargs.get("workdir", None)
                )
            elif tool_name == "git_status":
                result = await _run_command("git status")
            elif tool_name == "git_diff":
                target = kwargs.get("target", "")
                cmd = f"git diff {target}".strip()
                result = await _run_command(cmd)
            elif tool_name == "git_commit":
                files = kwargs.get("files", ".")
                await _run_command(f"git add {files}")
                result = await _run_command(f'git commit -m "{kwargs["message"]}"')
            elif tool_name == "web_fetch":
                result = await _web_fetch(kwargs["url"])
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

        duration_ms = int((time.time() - start) * 1000)
        result["duration_ms"] = duration_ms
        return result

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return {"error": str(e), "duration_ms": duration_ms}


async def _read_file(path: str) -> dict:
    """Read file contents."""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"File not found: {path}"}
    if not p.is_file():
        return {"error": f"Not a file: {path}"}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.count("\n") + 1
        return {"content": content, "lines": lines}
    except Exception as e:
        return {"error": str(e)}


async def _list_directory(path: str) -> dict:
    """List directory contents."""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"Directory not found: {path}"}
    if not p.is_dir():
        return {"error": f"Not a directory: {path}"}
    entries = []
    for entry in sorted(p.iterdir()):
        kind = "dir" if entry.is_dir() else "file"
        entries.append({"name": entry.name, "type": kind})
    return {"entries": entries, "count": len(entries)}


async def _search_content(pattern: str, path: str, include: str = "*") -> dict:
    """Search file contents using grep-like matching."""
    import re
    p = Path(path).resolve()
    matches = []

    if p.is_file():
        files = [p]
    elif p.is_dir():
        files = list(p.rglob(include))
    else:
        return {"error": f"Path not found: {path}"}

    regex = re.compile(pattern, re.IGNORECASE)
    for f in files[:100]:  # limit to 100 files
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    matches.append({
                        "file": str(f.relative_to(p) if p.is_dir() else f),
                        "line": i,
                        "content": line.strip()[:200],
                    })
        except Exception:
            continue

    return {"matches": matches[:50], "total": len(matches)}


async def _edit_file(path: str, old: str, new: str) -> dict:
    """Edit file by replacing text."""
    p = Path(path).resolve()
    if not p.exists():
        return {"error": f"File not found: {path}"}

    content = p.read_text(encoding="utf-8")
    if old not in content:
        return {"error": "Text not found in file"}

    count = content.count(old)
    new_content = content.replace(old, new, 1)
    p.write_text(new_content, encoding="utf-8")

    return {"replaced": True, "occurrences": count, "path": str(p)}


async def _write_file(path: str, content: str) -> dict:
    """Write content to file."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return {"written": True, "path": str(p), "bytes": len(content.encode())}


async def _run_command(command: str, workdir: str | None = None) -> dict:
    """Run shell command asynchronously."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    return {
        "stdout": stdout.decode(errors="replace")[:5000],
        "stderr": stderr.decode(errors="replace")[:2000],
        "exit_code": proc.returncode,
    }


async def _web_fetch(url: str) -> dict:
    """Fetch URL content."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=15.0)
        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            return {"content": resp.json(), "status": resp.status_code}
        return {"content": resp.text[:10000], "status": resp.status_code}
