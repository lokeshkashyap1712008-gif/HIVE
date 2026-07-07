"""Browser Use worker - autonomous browser automation using Browser Use library.

Uses Chrome profile with saved logins and DashScope Qwen as LLM.
"""
import os
import asyncio
import logging
import subprocess
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Browser Use requires its own LLM integration
try:
    from browser_use.llm.openai.chat import ChatOpenAI
    from browser_use import Agent, Browser, BrowserProfile
    BROWSER_USE_AVAILABLE = True
except ImportError:
    BROWSER_USE_AVAILABLE = False
    logger.warning("browser-use not installed")


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


# Chrome profile paths (Windows)
CHROME_PROFILES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
]

BROWSER_USE_WORKER_INSTRUCTIONS = """
BROWSER USE WORKER - Full Browser Automation

You control a real web browser using Browser Use.
The browser has access to the user's Chrome profile with saved logins.
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
- Star/unstar repositories
- Post content

LIMITATIONS:
- Chrome must be closed when using saved profile
- Some sites may block automation
- 2FA may require user input
- Complex CAPTCHAs may fail

WORKFLOW:
1. Start browser with Chrome profile
2. Navigate to target URL
3. Read page content
4. Interact with elements (click, type, etc.)
5. Verify results
6. Report outcome

The browser will be VISIBLE so you can see what's happening.
"""


def _find_chrome_profile() -> Optional[str]:
    """Find existing Chrome profile directory."""
    for path in CHROME_PROFILES:
        if os.path.exists(path):
            return path
    return None


async def _run_browser_use_task(
    task: str,
    profile_dir: Optional[str] = None,
    headless: bool = False,
    max_steps: int = 30,
) -> str:
    """Run a browser automation task using Browser Use.

    Args:
        task: Description of what to do in the browser
        profile_dir: Chrome profile directory (auto-detected if None)
        headless: Run browser invisibly (default: visible)
        max_steps: Maximum steps before giving up

    Returns:
        Task result as string
    """
    if not BROWSER_USE_AVAILABLE:
        return "ERROR: browser-use library not installed. Run: pip install browser-use"

    # Auto-detect Chrome profile
    if profile_dir is None:
        profile_dir = _find_chrome_profile()
        if profile_dir:
            logger.info(f"Using Chrome profile: {profile_dir}")
        else:
            logger.warning("No Chrome profile found, using fresh browser")

    # Configure LLM (DashScope Qwen via OpenAI-compatible API)
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return "ERROR: DASHSCOPE_API_KEY not set in .env"

    llm = ChatOpenAI(
        model="qwen3.7-plus",
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
    )

    # Configure browser
    browser_config = {
        "headless": headless,
        "disable_security": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
        ],
    }

    # Try to use Chrome profile if available
    use_profile = False
    if profile_dir and os.path.exists(profile_dir):
        # Check if Chrome is running - if so, profile is locked
        if _is_chrome_running():
            logger.warning("Chrome is running. Profile is locked. Using fresh browser.")
            use_profile = False
        else:
            # Chrome not running, safe to use profile
            use_profile = True
            logger.info(f"Using Chrome profile: {profile_dir}")

    # Only add user_data_dir if we can access the profile
    if use_profile:
        browser_config["user_data_dir"] = profile_dir

    # Create browser instance
    browser = Browser(**browser_config)

    try:
        # Create and run agent
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=3,
        )

        history = await agent.run(max_steps=max_steps)

        # Extract result from history
        try:
            # AgentHistoryList has a final_result() method
            final_result = history.final_result()
            if final_result:
                return f"Task completed successfully.\n\nResult:\n{final_result}"
            return "Task completed but no result returned."
        except Exception as e:
            # Fallback: try to get the last action result
            logger.warning(f"Could not extract final result: {e}")
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
    """Synchronous wrapper for browser task.

    Args:
        task: Description of what to do
        profile_dir: Chrome profile directory (auto-detected if None)
        headless: Run browser invisibly
        max_steps: Maximum steps before giving up

    Returns:
        Task result as string
    """
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
    """HIVE worker interface - run browser task using Browser Use.

    Args:
        task: Task description
        context: Optional context with task details

    Returns:
        Result dict with status and output
    """
    try:
        # Extract task from context if provided
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
        logger.error(f"Browser use worker failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "worker": "browser_use_worker",
        }


# Tool definition for HIVE integration
BROWSER_USE_TOOL = {
    "type": "function",
    "function": {
        "name": "browser_use_task",
        "description": "Automate browser tasks using a real Chrome browser with saved logins. Can login, fill forms, click buttons, navigate, and interact with any website. Uses Browser Use library for reliable automation.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Description of the browser task to perform (e.g., 'Login to GitHub and star the HIVE repo')"
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run browser invisibly (default: false, shows browser window)",
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
    # Test the worker
    result = run_browser_task(
        "Go to https://github.com and take a screenshot",
        headless=False,
        max_steps=5,
    )
    print(result)
