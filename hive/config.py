"""HIVE configuration — paths, settings, env vars."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
HIVE_HOME = Path(os.environ.get("HIVE_HOME", Path.home() / ".hive"))
HIVE_DB = HIVE_HOME / "hive.db"
AGENTS_DIR = HIVE_HOME / "agents" / "generated"
SKILLS_DIR = HIVE_HOME / "skills"

# LLM
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.7-plus")
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Browser automation
BROWSER_SCREENSHOT_DIR = Path(
    os.environ.get("HIVE_SCREENSHOT_DIR", str(HIVE_HOME / "screenshots"))
)
CHROME_AUTOMATION_PROFILE = Path(
    os.environ.get("HIVE_CHROME_PROFILE", str(HIVE_HOME / "chrome-automation"))
)

# Reuse the user's REAL Chrome login state (cookies/sessions). When enabled,
# HIVE snapshots the real Chrome profile (read-only copy — your original is
# never touched) so the automated browser inherits sites you're already
# logged into (Spotify, Google, etc.) and can skip the login form entirely.
HIVE_CHROME_PROFILE_REUSE = os.environ.get(
    "HIVE_CHROME_PROFILE_REUSE", "false"
).lower() in ("1", "true", "yes")
# Which Chrome profile to copy from (display/dir name, e.g. "Default", "Profile 1")
HIVE_CHROME_SOURCE_PROFILE = os.environ.get("HIVE_CHROME_SOURCE_PROFILE", "Default")
# Optional explicit path to Chrome's "User Data" dir (auto-detected if empty)
HIVE_CHROME_USER_DATA_DIR = os.environ.get("HIVE_CHROME_USER_DATA_DIR", "")

# Which browser binary Playwright drives:
#   "chromium" (default) — Playwright's bundled Chromium
#   "chrome"             — your REAL installed Google Chrome (better fingerprint,
#                          higher chance of passing login/bot challenges on hard
#                          sites like Spotify). Requires Chrome to be installed.
HIVE_BROWSER_CHANNEL = os.environ.get("HIVE_BROWSER_CHANNEL", "chromium").strip().lower()

# Checkout / payments guardrails
HIVE_CHECKOUT_AUTONOMOUS = os.environ.get("HIVE_CHECKOUT_AUTONOMOUS", "false").lower() in ("1", "true", "yes")
HIVE_MAX_ORDER_AMOUNT = float(os.environ.get("HIVE_MAX_ORDER_AMOUNT", "500"))
HIVE_MAX_DAILY_SPEND = float(os.environ.get("HIVE_MAX_DAILY_SPEND", "1000"))
HIVE_CHECKOUT_ALLOWED_MERCHANTS = [
    m.strip().lower()
    for m in os.environ.get("HIVE_CHECKOUT_ALLOWED_MERCHANTS", "").split(",")
    if m.strip()
]

# Exa — Web Search
EXA_API_KEY = os.environ.get("EXA_API_KEY", "")

# Runtime
MAX_AGENTS = int(os.environ.get("HIVE_MAX_AGENTS", "4"))
MAX_MESSAGES = int(os.environ.get("HIVE_MAX_MESSAGES", "50"))
MAX_TOOL_CACHE = int(os.environ.get("HIVE_MAX_TOOL_CACHE", "20"))
AGENT_TIMEOUT = int(os.environ.get("HIVE_AGENT_TIMEOUT", "60"))
MAX_TOKENS = int(os.environ.get("HIVE_MAX_TOKENS", "4000"))

# Security
ALLOWED_DOMAINS = [
    "api.dashscope.aliyuncs.com",
    "dashscope-intl.aliyuncs.com",
    "registry.npmjs.org",
    "pypi.org",
    "api.github.com",
    "raw.githubusercontent.com",
    "httpbin.org",
    "httpbin.org",
    "localhost",
    "127.0.0.1",
]

DENIED_PATTERNS = [
    r"rm\s+-rf",
    r"curl.*\|\s*bash",
    r"wget.*\|\s*bash",
    r"eval\s*\(",
    r"exec\s*\(",
    r">\s*/dev/sd",
    r"chmod\s+777",
    r"sudo\s+.*",
]

BLOCKED_ENV_VARS = [
    "DASHSCOPE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
]

CREDENTIAL_PATTERNS = [
    "*.env", "*.key", "*.pem", "*.p12", "*.pfx",
    "*credentials*", "*secret*", "*token*",
]

DENIED_PATHS = [
    "~/.ssh", "~/.aws", "~/.gnupg",
    "/etc", "/usr", "/bin", "/sbin", "/proc", "/sys",
]

THEME_BANNER = os.environ.get("HIVE_COLOR_BANNER", "gold1")
THEME_ACCENT = os.environ.get("HIVE_COLOR_ACCENT", "cyan")


def ensure_dirs():
    """Create HIVE directories if they don't exist."""
    HIVE_HOME.mkdir(parents=True, exist_ok=True)
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    BROWSER_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    CHROME_AUTOMATION_PROFILE.mkdir(parents=True, exist_ok=True)


def get_sanitized_context():
    """Context safe to send to LLM (no secrets)."""
    return {
        "project_dir": os.getcwd(),
        "platform": os.name,
    }
