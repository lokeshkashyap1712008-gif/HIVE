"""
HIVE — Personal-inbox verification code reader.

Connects to the user's own email account over IMAP (Gmail, Outlook, Yahoo,
or any custom host) and extracts verification / OTP codes from recent
messages, so login and signup flows can complete without a human typing
the code.

Configuration (checked in this order):
1. Vault credential stored under site "imap"  (vault_store_credential imap <email> <app_password>)
2. Env vars: HIVE_IMAP_USER, HIVE_IMAP_PASSWORD, and optional
   HIVE_IMAP_HOST / HIVE_IMAP_PORT (host is auto-guessed for
   gmail/outlook/yahoo/icloud addresses).

NOTE: Gmail and most providers require an "app password"
(not your normal password) when logging in over IMAP.
"""

from __future__ import annotations

import asyncio
import email
import email.utils
import imaplib
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.message import Message
from typing import Optional

logger = logging.getLogger(__name__)

# Well-known IMAP hosts by email domain
_KNOWN_HOSTS = {
    "gmail.com": "imap.gmail.com",
    "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com",
    "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com",
    "office365.com": "outlook.office365.com",
    "yahoo.com": "imap.mail.yahoo.com",
    "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com",
    "aol.com": "imap.aol.com",
    "zoho.com": "imap.zoho.com",
    "protonmail.com": "127.0.0.1",  # requires Proton Bridge running locally
    "proton.me": "127.0.0.1",
}

# Keywords that mark a message as a verification email
_VERIFY_KEYWORDS = [
    "verification", "verify", "confirm", "one-time", "one time", "otp",
    "security code", "login code", "sign-in code", "signin code",
    "access code", "passcode", "2fa", "two-factor", "authentication",
    "código", "confirmation code", "your code",
]


def resolve_imap_config() -> Optional[dict]:
    """Return {host, port, user, password} or None if not configured."""
    user = os.getenv("HIVE_IMAP_USER", "").strip()
    password = os.getenv("HIVE_IMAP_PASSWORD", "").strip()

    if not (user and password):
        try:
            from hive.browser.vault import get_credential
            cred = get_credential("imap")
            if cred:
                user = cred.get("username", "")
                password = cred.get("password", "")
        except Exception:
            pass

    if not (user and password):
        return None

    host = os.getenv("HIVE_IMAP_HOST", "").strip()
    if not host:
        domain = user.split("@")[-1].lower() if "@" in user else ""
        host = _KNOWN_HOSTS.get(domain, "")
        if not host and domain:
            host = f"imap.{domain}"  # common convention for custom domains

    if not host:
        return None

    port = int(os.getenv("HIVE_IMAP_PORT", "993"))
    return {"host": host, "port": port, "user": user, "password": password}


def extract_code(subject: str, body: str) -> Optional[str]:
    """Extract a verification code from an email's subject + body.

    Handles numeric codes (4-8 digits), Google's "G-123456" style, and
    alphanumeric codes explicitly labelled as a code.
    """
    combined = f"{subject}\n{body}"

    # Google style: G-123456
    m = re.search(r"\bG-(\d{6})\b", combined)
    if m:
        return m.group(1)

    # "code is: ABC123" / "code: 123456" — labelled codes, allow alphanumeric
    m = re.search(
        r"(?:code|otp|passcode|pin)\W{0,12}?\b([A-Z0-9]{4,8})\b",
        combined,
        re.IGNORECASE,
    )
    if m:
        candidate = m.group(1)
        # Reject pure-alpha words like "your" that sneak into the pattern
        if any(ch.isdigit() for ch in candidate):
            return candidate

    # Prefer digit groups on lines mentioning a verification keyword
    for line in combined.splitlines():
        low = line.lower()
        if any(kw in low for kw in _VERIFY_KEYWORDS + ["code"]):
            m = re.search(r"\b(\d{4,8})\b", line)
            if m:
                return m.group(1)

    # Fall back: a standalone 6-digit number anywhere (most common OTP length)
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", combined)
    if m:
        return m.group(1)

    return None


def _message_text(msg: Message) -> str:
    """Get plain-text content from an email message (falls back to HTML)."""
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode(msg.get_content_charset() or "utf-8", errors="replace"))
        except Exception:
            pass

    text = "\n".join(parts)
    # Strip HTML tags crudely — good enough for code extraction
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def _decode_header(value: str) -> str:
    try:
        decoded = email.header.decode_header(value)
        return " ".join(
            part.decode(enc or "utf-8", errors="replace") if isinstance(part, bytes) else part
            for part, enc in decoded
        )
    except Exception:
        return value or ""


def _check_inbox_once(config: dict, newer_than: datetime, sender_hint: str = "") -> Optional[dict]:
    """Blocking: connect over IMAP and look for a fresh verification code."""
    conn = imaplib.IMAP4_SSL(config["host"], config["port"])
    try:
        conn.login(config["user"], config["password"])
        conn.select("INBOX", readonly=True)

        since = newer_than.strftime("%d-%b-%Y")
        status, data = conn.search(None, f'(SINCE "{since}")')
        if status != "OK" or not data or not data[0]:
            return None

        ids = data[0].split()
        # Newest first, only look at the last few messages
        for msg_id in reversed(ids[-15:]):
            status, msg_data = conn.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            # Skip messages older than our start time (SINCE is day-granular)
            date_hdr = msg.get("Date", "")
            try:
                msg_dt = email.utils.parsedate_to_datetime(date_hdr)
                if msg_dt.tzinfo is None:
                    msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                if msg_dt < newer_than:
                    continue
            except Exception:
                pass

            sender = _decode_header(msg.get("From", ""))
            if sender_hint and sender_hint.lower() not in sender.lower():
                continue

            subject = _decode_header(msg.get("Subject", ""))
            combined_meta = f"{subject} {sender}".lower()
            body = _message_text(msg)

            # Only treat as a verification mail if it looks like one
            looks_like_verify = any(kw in combined_meta for kw in _VERIFY_KEYWORDS) or any(
                kw in body.lower() for kw in _VERIFY_KEYWORDS
            )
            if not looks_like_verify:
                continue

            code = extract_code(subject, body)
            if code:
                return {"code": code, "from": sender, "subject": subject}
        return None
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def wait_for_code_imap(
    timeout: int = 90,
    sender_hint: str = "",
    lookback_seconds: int = 60,
) -> dict:
    """Poll the user's personal inbox for a verification code.

    Returns {"status": "received", "code": ...} or {"error": ...}.
    """
    config = resolve_imap_config()
    if not config:
        return {
            "error": (
                "Personal inbox not configured. Either store an app password with "
                "`/vault imap <email> <app_password>` (vault_store_credential) or set "
                "HIVE_IMAP_USER / HIVE_IMAP_PASSWORD in .env. "
                "Gmail: create an App Password at https://myaccount.google.com/apppasswords"
            )
        }

    # Accept codes that arrived slightly before we started waiting
    newer_than = datetime.now(timezone.utc) - timedelta(seconds=lookback_seconds)
    deadline = time.time() + timeout
    last_error = None

    logger.info("[EmailCodes] Polling %s inbox for verification code (timeout %ds)", config["host"], timeout)

    while time.time() < deadline:
        try:
            found = await asyncio.to_thread(_check_inbox_once, config, newer_than, sender_hint)
            if found:
                logger.info("[EmailCodes] Code found in mail from %s", found["from"][:60])
                return {"status": "received", **found}
        except imaplib.IMAP4.error as e:
            # Auth errors won't fix themselves — bail immediately with guidance
            msg = str(e)
            if any(k in msg.lower() for k in ["auth", "login", "credentials", "password"]):
                return {
                    "error": (
                        f"IMAP login failed for {config['user']}: {msg}. "
                        "Most providers need an APP PASSWORD for IMAP, not your normal password. "
                        "Gmail: https://myaccount.google.com/apppasswords (2FA must be enabled)."
                    )
                }
            last_error = msg
        except Exception as e:
            last_error = str(e)

        await asyncio.sleep(5)

    if last_error:
        return {"error": f"No code received within {timeout}s (last error: {last_error})"}
    return {"error": f"No verification code arrived in {config['user']} within {timeout}s"}
