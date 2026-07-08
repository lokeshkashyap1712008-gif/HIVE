"""Browser Use worker - autonomous browser automation using Browser Use library.

Uses a dedicated cloned Chrome profile (or user's Chrome profile) with saved logins.
"""
import os
import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

from hive.config import QWEN_MODEL, DASHSCOPE_API_KEY, CHROME_AUTOMATION_PROFILE

# Browser Use requires its own LLM integration
try:
    from browser_use.llm.openai.chat import ChatOpenAI
    from browser_use import Agent, Browser, BrowserProfile
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("browser-use not installed")

# Source Chrome profile paths (Windows)
CHROME_SOURCE_PROFILES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
]


def _is_chrome_running() -> bool:
    """Check if Chrome browser is running on Windows."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return "chrome.exe" in result.stdout.lower()
    except Exception:
        return False


def _find_source_chrome_profile() -> Optional[str]:
    """Find existing Chrome profile directory."""
    for path in CHROME_SOURCE_PROFILES:
        if os.path.exists(path):
            return path
    return None


def _ensure_automation_profile() -> str:
    """Clone Chrome profile to dedicated automation dir if needed.

    This allows automation while user's normal Chrome can stay open.
  Profile is refreshed if older than 7 days.
    """
    import time
    automation_dir = Path(CHROME_AUTOMATION_PROFILE)
    marker = automation_dir / ".profile_ready"
    max_age = 7 * 24 * 3600

    if marker.exists():
        age = time.time() - marker.stat().st_mtime
        if age < max_age and (automation_dir / "Default").exists():
            return str(automation_dir)

    source = _find_source_chrome_profile()
    automation_dir.mkdir(parents=True, exist_ok=True)

    if source and os.path.exists(source):
        # Copy only essential profile data (not full cache)
        for item in ["Default", "Local State"]:
            src = os.path.join(source, item)
            dst = automation_dir / item
            if os.path.exists(src):
                try:
                    if os.path.isdir(src):
                        if dst.exists():
                            shutil.rmtree(dst, ignore_errors=True)
                        shutil.copytree(
                            src, dst,
                            ignore=shutil.ignore_patterns(
                                "Cache", "Code Cache", "GPUCache", "Service Worker",
                                "ShaderCache", "*.tmp", "Crashpad",
                            ),
                            dirs_exist_ok=True,
                        )
                    else:
                        shutil.copy2(src, dst)
                except Exception as e:
                    logger.warning("Could not copy %s: %s", item, e)
        logger.info("Cloned Chrome profile to automation dir: %s", automation_dir)
    else:
        logger.info("No source Chrome profile found; using fresh automation profile")

    marker.touch()
    return str(automation_dir)


BROWSER_USE_WORKER_INSTRUCTIONS = """
BROWSER USE WORKER - Full Browser Automation

You control a real web browser using Browser Use.
The browser has access to saved logins from a cloned Chrome profile.
You can navigate, click, type, read, and interact with any website.

CAPABILITIES:
- Navigate to any URL
- Click buttons, links, tabs
- Fill forms with text
- Read page content
- Take screenshots
- Save and load browser sessions
- Use saved logins from Chrome profile

WHAT YOU CAN DO:
- Login to websites using saved credentials
- Fill out forms
- Click buttons
- Navigate between pages
- Extract information
- Submit data
- Complete checkout flows (with human confirmation for final purchase)

LIMITATIONS:
- Some sites may block automation
- 2FA may require user input
- Complex CAPTCHAs may fail

The browser will be VISIBLE so you can see what's happening.
"""


async def _run_browser_use_task(
    task: str,
    profile_dir: Optional[str] = None,
    headless: bool = False,
    max_steps: int = 30,
) -> str:
    """Run a browser automation task using Browser Use."""
    if not BROWSER_USE_AVAILABLE:
        return "ERROR: browser-use library not installed. Run: pip install browser-use"

    if profile_dir is None:
        profile_dir = _ensure_automation_profile()
        logger.info("Using automation Chrome profile: %s", profile_dir)

    api_key = DASHSCOPE_API_KEY or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return "ERROR: DASHSCOPE_API_KEY not set in .env"

    llm = ChatOpenAI(
        model=QWEN_MODEL,
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
    )

    browser_config = {
        "headless": headless,
        "disable_security": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
        ],
    }

    if profile_dir and os.path.exists(profile_dir):
        browser_config["user_data_dir"] = profile_dir

    browser = Browser(**browser_config)

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=3,
        )

        history = await agent.run(max_steps=max_steps)

        try:
            final_result = history.final_result()
            if final_result:
                return f"Task completed successfully.\n\nResult:\n{final_result}"
            return "Task completed but no result returned."
        except Exception as e:
            logger.warning("Could not extract final result: %s", e)
            return "Task completed successfully."

    except Exception as e:
        error_msg = f"Browser task failed: {str(e)}"
        logger.error(error_msg)
        return error_msg

    finally:
        await browser.close()


def run_browser_task(
    task: str,
    profile_dir: Optional[str] = None,
    headless: bool = False,
    max_steps: int = 30,
) -> str:
    """Synchronous wrapper for browser task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    _run_browser_use_task(task, profile_dir, headless, max_steps)
                )
                return future.result(timeout=300)
        else:
            return loop.run_until_complete(
                _run_browser_use_task(task, profile_dir, headless, max_steps)
            )
    except Exception as e:
        return f"ERROR: {str(e)}"


async def run(task: str, context: Optional[dict] = None) -> dict:
    """HIVE worker interface - run browser task using Browser Use."""
    try:
        actual_task = task
        if context and "task" in context:
            actual_task = context["task"]

        result = await _run_browser_use_task(
            actual_task,
            headless=False,
            max_steps=30,
        )

        return {
            "status": "completed",
            "output": result,
            "worker": "browser_use_worker",
        }
    except Exception as e:
        logger.error("Browser use worker failed: %s", e)
        return {
            "status": "error",
            "error": str(e),
            "worker": "browser_use_worker",
        }


BROWSER_USE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_use_task",
        "description": "Automate browser tasks using a real Chrome browser with saved logins. Can login, fill forms, click buttons, navigate, and interact with any website.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Description of the browser task to perform",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run browser invisibly (default: false)",
                    "default": False,
                },
                "max_steps": {
                    "type": "integer",
                    "description": "Maximum steps before giving up (default: 30)",
                    "default": 30,
                },
            },
            "required": ["task"],
        },
    },
}


if __name__ == "__main__":
    result = run_browser_task(
        "Go to https://github.com and take a screenshot",
        headless=False,
        max_steps=5,
    )
    print(result)
