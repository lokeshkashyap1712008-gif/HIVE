"""Permission system — risk tiers, validation, audit."""

import re
import os
from pathlib import Path
from hive.config import (
    DENIED_PATTERNS, DENIED_PATHS, CREDENTIAL_PATTERNS, ALLOWED_DOMAINS,
)

# Risk tiers
TIERS = {
    "safe": "allow",
    "moderate": "ask",
    "sensitive": "ask_always",
    "dangerous": "deny",
}

# Tool → tier mapping
TOOL_TIERS = {
    "read_file": "safe",
    "list_directory": "safe",
    "search_content": "safe",
    "git_status": "safe",
    "git_diff": "safe",
    "edit_file": "moderate",
    "write_file": "moderate",
    "run_command": "moderate",
    "web_fetch": "moderate",
    "web_search": "moderate",
    "git_commit": "sensitive",
    "install_package": "sensitive",
    "delete_file": "dangerous",
}

# Compiled dangerous patterns
_dangerous_re = [re.compile(p) for p in DENIED_PATTERNS]


def get_tool_tier(tool_name: str) -> str:
    """Get risk tier for a tool."""
    return TOOL_TIERS.get(tool_name, "moderate")


def check_dangerous_command(command: str) -> bool:
    """Returns True if command matches a dangerous pattern."""
    for pattern in _dangerous_re:
        if pattern.search(command):
            return True
    return False


def check_path_access(path: str, mode: str = "read") -> tuple[bool, str]:
    """Check if path is allowed. Returns (allowed, reason)."""
    expanded = os.path.expanduser(path)
    resolved = str(Path(expanded).resolve())
    home = str(Path.home())

    # Check denied paths
    for denied in DENIED_PATHS:
        denied_expanded = os.path.expanduser(denied)
        if resolved.startswith(denied_expanded):
            return False, f"Access denied: {denied}"

    # Check credential patterns
    basename = os.path.basename(resolved)
    for pattern in CREDENTIAL_PATTERNS:
        import fnmatch
        if fnmatch.fnmatch(basename, pattern):
            return False, f"Access denied: credential file"

    # Check project directory (must be under cwd or ~/.hive)
    cwd = os.getcwd()
    hive_home = str(os.path.expanduser("~/.hive"))
    if not resolved.startswith(cwd) and not resolved.startswith(hive_home):
        return False, f"Access denied: outside project directory"

    return True, ""


def check_url_access(url: str) -> tuple[bool, str]:
    """Check if URL domain is allowed. Returns (allowed, reason)."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.hostname or ""

    if domain in ALLOWED_DOMAINS:
        return True, ""

    # Allow localhost for dev
    if domain in ("localhost", "127.0.0.1"):
        return True, ""

    return False, f"Domain not in allowlist: {domain}"


def validate_agent_code(code: str) -> tuple[bool, str]:
    """Validate generated agent code for dangerous patterns."""
    dangerous_imports = [
        "import os", "import subprocess", "import shutil",
        "from os import", "from subprocess import",
    ]
    dangerous_calls = [
        "os.system(", "subprocess.call(", "subprocess.Popen(",
        "subprocess.run(", "os.popen(",
    ]
    dangerous_file = [
        "open('/etc/", "open('/usr/", "open('/bin/",
        "open('~/.ssh/", "open('~/.aws/",
    ]
    dangerous_eval = [
        "eval(", "exec(", "__import__(",
    ]

    all_patterns = dangerous_imports + dangerous_calls + dangerous_file + dangerous_eval

    for pattern in all_patterns:
        if pattern in code:
            return False, f"Dangerous pattern found: {pattern}"

    return True, ""


def should_auto_allow(tool_name: str, target: str = "") -> bool:
    """Check if tool call can be auto-approved."""
    tier = get_tool_tier(tool_name)

    if tier == "safe":
        return True

    if tier == "moderate" and target:
        allowed, _ = check_path_access(target)
        if allowed:
            return True

    return False
