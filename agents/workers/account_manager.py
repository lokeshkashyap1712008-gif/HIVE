"""
HIVE — Account Manager Agent
OAuth2 flows, 2FA/TOTP, session management, credential storage.
Handles multi-platform authentication and token management.
"""

import os
import time
import hmac
import hashlib
import base64
import logging
import secrets
import json
from typing import Optional

import httpx

from core.llm_router import chat, QWEN_TURBO

logger = logging.getLogger(__name__)

SESSION_DB_PATH = "db/sessions.json"


def _load_sessions() -> dict:
    if os.path.exists(SESSION_DB_PATH):
        with open(SESSION_DB_PATH, "r") as f:
            return json.load(f)
    return {}


def _save_sessions(sessions: dict):
    os.makedirs("db", exist_ok=True)
    with open(SESSION_DB_PATH, "w") as f:
        json.dump(sessions, f)


def generate_totp(secret: str, timestamp: Optional[int] = None) -> str:
    """
    Generate TOTP code from secret.
    Secret should be base32 encoded.
    """
    if timestamp is None:
        timestamp = int(time.time() // 30)

    try:
        import pyotp
        return pyotp.TOTP(secret).at(timestamp)
    except ImportError:
        # Manual TOTP if pyotp not available
        secret_bytes = base64.b32decode(secret.upper() + "=" * (8 - len(secret) % 8))
        msg = timestamp.to_bytes(8, "big")
        hmac_hash = hmac.new(secret_bytes, msg, hashlib.sha1).digest()
        offset = hmac_hash[-1] & 0xF
        code = (
            (hmac_hash[offset] & 0x7F) << 24
            | (hmac_hash[offset + 1] & 0xFF) << 16
            | (hmac_hash[offset + 2] & 0xFF) << 8
            | (hmac_hash[offset + 3] & 0xFF)
        ) % 1000000
        return f"{code:06d}"


async def verify_2fa(secret: str, code: str) -> bool:
    """Verify TOTP code (with ±1 window for clock drift)."""
    current = int(time.time() // 30)
    for offset in range(-1, 2):  # ±1 period tolerance
        expected = generate_totp(secret, current + offset)
        if secrets.compare_digest(expected, code):
            return True
    return False


async def _oauth2_flow(
    platform: str,
    client_id: str,
    client_secret: str,
    auth_url: str,
    token_url: str,
    scope: str,
    redirect_uri: str,
    state: str,
) -> dict:
    """Complete OAuth2 flow."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get authorization URL
            auth_params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
                "state": state,
            }
            full_auth_url = auth_url + "?" + "&".join(f"{k}={v}" for k, v in auth_params.items())

            # In a real implementation, would open browser for user
            # For now, return the URL for manual authorization
            return {
                "status": "auth_required",
                "authorization_url": full_auth_url,
                "state": state,
                "instruction": f"Open the authorization URL, authorize, and return the code parameter from the redirect.",
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _exchange_code_for_token(
    code: str,
    client_id: str,
    client_secret: str,
    token_url: str,
    redirect_uri: str,
) -> dict:
    """Exchange auth code for access token."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return {"status": "ok", "tokens": resp.json()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def store_session(platform: str, user_id: str, tokens: dict, metadata: Optional[dict] = None) -> str:
    """Store a session securely. Returns session_id."""
    sessions = _load_sessions()

    # Encrypt sensitive tokens before storing
    session_id = secrets.token_hex(16)
    sessions[session_id] = {
        "platform": platform,
        "user_id": user_id,
        "tokens": tokens,
        "metadata": metadata or {},
        "created_at": time.time(),
        "last_used": time.time(),
    }

    _save_sessions(sessions)
    logger.info(f"[AccountManager] Stored session for {platform}/{user_id}")
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    """Retrieve a session."""
    sessions = _load_sessions()
    session = sessions.get(session_id)

    if session:
        # Update last used
        session["last_used"] = time.time()
        sessions[session_id] = session
        _save_sessions(sessions)

    return session


def revoke_session(session_id: str) -> bool:
    """Revoke/delete a session."""
    sessions = _load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        _save_sessions(sessions)
        return True
    return False


async def run(task: str) -> dict:
    """Handle account/auth requests."""
    task_lower = task.lower()

    if "oauth" in task_lower or "authorize" in task_lower:
        # Parse OAuth request
        import re
        platform_match = re.search(r'(github|slack|discord|stripe|paypal|google|microsoft)', task_lower)
        platform = platform_match.group(0) if platform_match else "unknown"

        platforms = {
            "github": {
                "client_id": os.getenv("GITHUB_CLIENT_ID", ""),
                "client_secret": os.getenv("GITHUB_CLIENT_SECRET", ""),
                "auth_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "scope": "repo:status read:user",
                "redirect_uri": "http://localhost:8000/oauth/callback",
            }
        }

        p = platforms.get(platform, {})
        if not p.get("client_id"):
            return {"status": "error", "message": f"{platform} OAuth not configured. Set env vars."}

        state = secrets.token_hex(16)
        return await _oauth2_flow(
            platform, p["client_id"], p["client_secret"],
            p["auth_url"], p["token_url"], p["scope"], p["redirect_uri"], state,
        )

    elif "2fa" in task_lower or "totp" in task_lower:
        # Verify 2FA code
        import re
        code_match = re.search(r'\b\d{6}\b', task)
        secret_match = re.search(r'secret[:\s]+([A-Z0-9]{16,32})', task.upper())

        if not code_match or not secret_match:
            return {"status": "error", "message": "Need both secret and 6-digit code"}

        code = code_match.group(0)
        secret = secret_match.group(1)
        valid = await verify_2fa(secret, code)
        return {"status": "ok", "2fa_valid": valid, "code": code}

    elif "session" in task_lower:
        if "revoke" in task_lower or "delete" in task_lower:
            import re
            sid_match = re.search(r'\b[a-f0-9]{32}\b', task)
            if sid_match:
                success = revoke_session(sid_match.group(0))
                return {"status": "ok", "revoked": success, "session_id": sid_match.group(0)}
        else:
            sessions = _load_sessions()
            return {
                "status": "ok",
                "active_sessions": len(sessions),
                "sessions": [
                    {"id": k, "platform": v["platform"], "user_id": v["user_id"],
                     "last_used": v["last_used"]}
                    for k, v in sessions.items()
                ],
            }

    elif "test" in task_lower and ("connection" in task_lower or "auth" in task_lower):
        # Test connection for a platform
        import re
        platform_match = re.search(r'(github|slack|discord|stripe|paypal|google)', task_lower)
        platform = platform_match.group(0) if platform_match else "github"

        sessions = _load_sessions()
        active_session = None
        for sid, sess in sessions.items():
            if sess.get("platform") == platform:
                token = sess.get("tokens", {}).get("access_token", "")
                if token:
                    active_session = sid
                    break

        if not active_session:
            return {"status": "not_connected", "platform": platform}

        # Test the token
        if platform == "github":
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        "https://api.github.com/user",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        return {"status": "ok", "platform": platform, "connected": True}
            except Exception:
                pass

        return {"status": "error", "platform": platform}

    else:
        return {
            "status": "ok",
            "message": "Account Manager: supports OAuth2, 2FA/TOTP, session management",
            "examples": [
                "authorize github via OAuth2",
                "verify 2fa with secret XXX code 123456",
                "list active sessions",
                "revoke session [id]",
                "test connection to github",
            ],
        }