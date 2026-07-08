"""Google login helper — visible browser, human completes login, HIVE saves session."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

GOOGLE_LOGIN_URL = "https://accounts.google.com/"
SESSION_NAME = "google_com"
SUCCESS_URL_PATTERNS = [
    r"myaccount\.google\.com",
    r"mail\.google\.com",
    r"accounts\.google\.com/ManageAccount",
    r"accounts\.google\.com/b/",
]
SUCCESS_PAGE_INDICATORS = [
    "my account", "google account", "welcome", "gmail", "sign out", "log out",
]


async def run_google_login(
    email: Optional[str] = None,
    timeout_seconds: int = 300,
) -> dict:
    """Open visible browser for Google login; wait for human; save session.

    Best approach when automation is blocked by CAPTCHA:
    1. Browser opens visibly at accounts.google.com
    2. You log in manually (solve CAPTCHA, 2FA, etc.)
    3. HIVE detects success and saves session + optional vault entry
    """
    from playwright.async_api import async_playwright

    try:
        from playwright_stealth import Stealth
    except ImportError:
        Stealth = None

    email_hint = email or ""
    started_url = GOOGLE_LOGIN_URL
    if email_hint:
        started_url = f"https://accounts.google.com/signin/v2/identifier?Email={email_hint}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        if Stealth:
            await Stealth().apply_stealth_async(context)

        page = await context.new_page()
        await page.goto(started_url, wait_until="domcontentloaded", timeout=60000)

        logger.info("Google login: complete sign-in in the browser window")
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        logged_in = False
        final_url = page.url

        while asyncio.get_event_loop().time() < deadline:
            final_url = page.url
            if _url_indicates_success(final_url):
                logged_in = True
                break
            try:
                body = (await page.inner_text("body"))[:3000].lower()
                if any(ind in body for ind in SUCCESS_PAGE_INDICATORS) and "sign in" not in final_url.lower():
                    if "password" not in body or "my account" in body:
                        logged_in = True
                        break
            except Exception:
                pass
            await asyncio.sleep(2)

        if not logged_in:
            await browser.close()
            return {
                "status": "timeout",
                "message": f"Login not detected within {timeout_seconds}s. Try again.",
                "url": final_url,
            }

        # Persist session via browser pool format
        from pathlib import Path
        import json
        import os

        sessions_dir = Path(".hive") / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        storage = await context.storage_state()
        session_path = sessions_dir / f"{SESSION_NAME}.json"
        session_path.write_text(json.dumps(storage, indent=2))

        detected_email = email_hint
        try:
            # Try to read account email from page
            content = await page.content()
            em = re.search(r'[\w.+-]+@gmail\.com', content)
            if em:
                detected_email = em.group(0)
        except Exception:
            pass

        if detected_email:
            try:
                from hive.browser.vault import store_credential, store_account
                store_account("google.com", detected_email, session_name=SESSION_NAME)
                logger.info("Saved Google account to vault: %s", detected_email)
            except Exception as e:
                logger.debug("Vault save skipped: %s", e)

        await browser.close()

        return {
            "status": "completed",
            "message": "Google login successful. Session saved as 'google_com'.",
            "session_name": SESSION_NAME,
            "session_path": str(session_path),
            "email": detected_email or "unknown",
            "url": final_url,
        }


def _url_indicates_success(url: str) -> bool:
    for pat in SUCCESS_URL_PATTERNS:
        if re.search(pat, url, re.IGNORECASE):
            return True
    return False
