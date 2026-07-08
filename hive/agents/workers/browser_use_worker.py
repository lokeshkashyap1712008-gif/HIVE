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
    """Create a fresh automation Chrome profile.

    Uses a clean profile to avoid Chrome's identity verification popup
    that triggers when cloning the real Chrome profile (DPAPI-bound keys).
    Credentials are loaded from the vault instead of saved logins.
    """
    automation_dir = Path(CHROME_AUTOMATION_PROFILE)
    marker = automation_dir / ".profile_ready"

    if marker.exists() and (automation_dir / "Default").exists():
        return str(automation_dir)

    automation_dir.mkdir(parents=True, exist_ok=True)

    # Write a fresh Local State with no Google account sync
    local_state = {
        "browser": {
            "enabled_labs_experiments": [],
            "check_default_browser": False,
        },
        "profile": {
            "name": "HIVE Automation",
            "default_content_setting_values": {
                "notifications": 2,
            },
        },
        "signin": {
            "allowed": False,
        },
    }
    import json
    (automation_dir / "Local State").write_text(json.dumps(local_state, indent=2))

    # Create Default profile directory with Preferences that disable sync
    default_dir = automation_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)
    preferences = {
        "browser": {
            "show_home_button": False,
            "check_default_browser": False,
        },
        "signin": {
            "allowed": False,
            "previous_modes": [],
        },
        "sync": {
            "disabled": True,
        },
        "google": {
            "services": {
                "account_id": "",
                "gaia_id": "",
            },
        },
    }
    (default_dir / "Preferences").write_text(json.dumps(preferences, indent=2))

    logger.info("Created fresh automation profile: %s", automation_dir)
    marker.touch()
    return str(automation_dir)


BROWSER_USE_WORKER_INSTRUCTIONS = """
BROWSER USE WORKER - Full Browser Automation

You control a real web browser using Browser Use.
Credentials are loaded from the HIVE vault, not Chrome saved logins.
You can navigate, click, type, read, and interact with any website.

CAPABILITIES:
- Navigate to any URL
- Click buttons, links, tabs
- Fill forms with text
- Read page content
- Take screenshots
- Save and load browser sessions
- Use credentials from the vault

WHAT YOU CAN DO:
- Login to websites using vault credentials
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
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-sync-preferences",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-identity-ecma",
            "--disable-component-extensions-with-background-pages",
            "--disable-default-apps",
            "--disable-features=TranslateUI",
            "--disable-ipc-flooding-protection",
            "--window-size=1280,900",
        ],
        "profile_directory": "Default",
        "window_size": {"width": 1280, "height": 900},
    }

    if profile_dir and os.path.exists(profile_dir):
        browser_config["user_data_dir"] = profile_dir

    browser = Browser(**browser_config)

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=5,
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


def _inject_vault_credentials(task: str) -> str:
    """Check vault for stored credentials and inject them into the task description."""
    import re
    from hive.browser.vault import get_credential

    task_lower = task.lower()

    # Only inject if task mentions login-related actions
    login_keywords = ["log in", "login", "sign in", "signin", "authenticate"]
    if not any(kw in task_lower for kw in login_keywords):
        return task

    # Extract site name from task
    # Try URL first
    url_match = re.search(r'https?://([^\s/]+)', task)
    if url_match:
        site = url_match.group(1).lower().replace("www.", "")
    else:
        # Try common brand names
        brand_map = {
            "spotify": "spotify.com",
            "github": "github.com",
            "google": "google.com",
            "amazon": "amazon.com",
            "twitter": "twitter.com",
            "x": "twitter.com",
            "facebook": "facebook.com",
            "instagram": "instagram.com",
            "linkedin": "linkedin.com",
            "netflix": "netflix.com",
            "youtube": "youtube.com",
        }
        site = ""
        for brand, domain in brand_map.items():
            if brand in task_lower:
                site = domain
                break
        if not site:
            # Try to find a site name mentioned before "credentials" or "login"
            site_match = re.search(r'(?:for|on|at|to)\s+(\w+)', task, re.IGNORECASE)
            if site_match:
                candidate = site_match.group(1).lower()
                if len(candidate) > 2 and candidate not in ("my", "the", "a", "an", "this", "that", "and", "or"):
                    site = candidate + ".com"

    if not site:
        return task

    # Look up credentials in vault
    cred = get_credential(site)
    if not cred:
        # Try without TLD
        site_bare = site.split(".")[0]
        cred = get_credential(site_bare)

    if not cred:
        logger.info("[BrowserUseWorker] No vault credentials found for %s", site)
        return task

    # Inject credentials into task description
    email = cred.get("username", "")
    password = cred.get("password", "")

    if email and password:
        credential_instruction = f"""CRITICAL LOGIN INSTRUCTIONS:
You have stored credentials for this site. Use them:

Step 1: Find the email/username input field and type: {email}
Step 2: Find and click the "Next" or "Continue" or "Log In" button (look for buttons with text like "Next", "Continue", "Log in", "Sign in", or any submit button)
Step 3: Wait for the password field to appear
Step 4: Find the password input field and type: {password}
Step 5: Find and click the "Log In" or "Sign In" or "Continue" button to submit

IMPORTANT RULES:
- After typing in each field, you MUST click the submit/next button to proceed
- If you see a "Next" button, click it — this advances to the password step
- Do NOT stop after filling the email field — you MUST click Next/Continue
- Wait 1-2 seconds after clicking for the page to load
- If a CAPTCHA or verification appears, report it and stop
"""
        # Insert before the original task
        return credential_instruction + "\nOriginal task: " + task

    return task


async def run(task: str, context: Optional[dict] = None) -> dict:
    """HIVE worker interface - run browser task using Browser Use."""
    try:
        actual_task = task
        if context and "task" in context:
            actual_task = context["task"]

        # Inject vault credentials if task mentions login and vault has stored creds
        actual_task = _inject_vault_credentials(actual_task)

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
