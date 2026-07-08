"""Account signup flow with email verification and CAPTCHA handoff."""

from __future__ import annotations

import logging
import re
from typing import Optional

from hive.browser.vault import store_account, store_credential

logger = logging.getLogger(__name__)

CAPTCHA_SOLVER_ENABLED = __import__("os").environ.get("HIVE_CAPTCHA_SOLVER", "false").lower() in ("1", "true", "yes")


def _is_captcha_page(elements: list) -> bool:
    """Detect CAPTCHA presence on page."""
    captcha_indicators = [
        "captcha", "recaptcha", "hcaptcha", "challenge", "verify you are human",
        "i'm not a robot", "security check",
    ]
    for el in elements:
        combined = " ".join([
            (el.get("text") or ""),
            (el.get("placeholder") or ""),
            (el.get("ariaLabel") or ""),
            (el.get("selector") or ""),
        ]).lower()
        if any(ind in combined for ind in captcha_indicators):
            return True
    return False


def _extract_site_from_task(task: str) -> str:
    url_match = re.search(r"https?://([^/\s]+)", task)
    if url_match:
        return url_match.group(1).lower().replace("www.", "")
    # Try domain-like words
    for word in ["github", "amazon", "google", "shopify", "stripe"]:
        if word in task.lower():
            return f"{word}.com"
    return "unknown"


async def run_signup(
    task: str,
    url: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    use_disposable_email: bool = True,
) -> dict:
    """Run account signup via browser_agent with verification support."""
    from hive.tools import execute_tool
    from hive.agents.workers.browser_agent import run as browser_run

    site = _extract_site_from_task(url or task)
    session_name = site.replace(".", "_")

    # Create disposable email if needed
    signup_email = email
    if not signup_email and use_disposable_email:
        inbox_result = await execute_tool("browser_create_inbox")
        if "email" in inbox_result:
            signup_email = inbox_result["email"]
            logger.info("Created disposable email: %s", signup_email)
        else:
            return {
                "status": "error",
                "reason": f"Could not create inbox: {inbox_result.get('error', 'unknown')}",
            }

    if not signup_email:
        return {"status": "error", "reason": "No email provided and disposable email creation failed"}

    if not password:
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        password = "".join(secrets.choice(alphabet) for _ in range(16))

    signup_task = f"""
ACCOUNT SIGNUP TASK:
Site: {site}
URL: {url or 'detect from task'}
Email to use: {signup_email}
Password: use ${{password}} placeholder with sensitive_data

Steps:
1. Navigate to the signup/register page
2. Fill registration form (email, password, name if required)
3. Submit the form
4. If email verification is required, wait — verification code will be provided
5. Complete any onboarding steps
6. Report success when account is created and logged in

Original request: {task}
"""

    credentials = {"email": signup_email, "password": password}
    context = {"credentials": credentials}

    # Open URL if provided
    if url:
        await execute_tool("browser_open", url=url)

    result = await browser_run(signup_task, context=context)

    # Handle 2FA / email verification
    if result.get("status") == "waiting_for_2fa":
        code_result = await execute_tool("browser_wait_for_code", timeout=60)
        if "code" in code_result:
            verify_task = f"Enter verification code {code_result['code']} in the verification field and submit"
            result = await browser_run(verify_task, context=context)
        else:
            return {
                "status": "waiting_for_verification",
                "message": "Email verification required but no code received yet",
                "email": signup_email,
                "browser_result": result,
            }

    # Check for CAPTCHA
    inspect = await execute_tool("browser_inspect")
    if not inspect.get("error") and _is_captcha_page(inspect.get("elements", [])):
        if CAPTCHA_SOLVER_ENABLED:
            logger.info("CAPTCHA detected — solver enabled but not implemented; handing off to human")
        return {
            "status": "captcha_required",
            "message": "CAPTCHA detected. Please solve it in the browser, then retry.",
            "email": signup_email,
            "requires_human": True,
        }

    if result.get("status") == "completed":
        # Persist to vault
        store_credential(site, signup_email, password)
        store_account(site, signup_email, session_name=session_name)
        await execute_tool("browser_session_save", name=session_name)
        return {
            "status": "completed",
            "site": site,
            "email": signup_email,
            "session_name": session_name,
            "message": f"Account created and session saved as '{session_name}'",
            "browser_result": result,
        }

    return {
        "status": result.get("status", "unknown"),
        "site": site,
        "email": signup_email,
        "browser_result": result,
    }
