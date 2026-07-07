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
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-max")
QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

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


def get_sanitized_context():
    """Context safe to send to LLM (no secrets)."""
    return {
        "project_dir": os.getcwd(),
        "platform": os.name,
    }
