"""
HIVE — Account Manager Agent
OAuth2 flows, 2FA/TOTP, session management, credential storage.
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

from hive.core.llm_router import chat, QWEN_TURBO

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
    if timestamp is None:
        timestamp = int(time.time() // 30)

    try:
        import pyotp
        return pyotp.TOTP(secret).at(timestamp)
    except ImportError:
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
    current = int(time.time() // 30)
    for offset in range(-1, 2):
        expected = generate_totp(secret, current + offset)
        if secrets.compare_digest(expected, code):
            return True
    return False


def store_session(platform: str, user_id: str, tokens: dict, metadata: Optional[dict] = None) -> str:
    sessions = _load_sessions()
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
    return session_id


def get_session(session_id: str) -> Optional[dict]:
    sessions = _load_sessions()
    session = sessions.get(session_id)
    if session:
        session["last_used"] = time.time()
        sessions[session_id] = session
        _save_sessions(sessions)
    return session


def revoke_session(session_id: str) -> bool:
    sessions = _load_sessions()
    if session_id in sessions:
        del sessions[session_id]
        _save_sessions(sessions)
        return True
    return False


async def run(task: str) -> dict:
    task_lower = task.lower()

    if "oauth" in task_lower or "authorize" in task_lower:
        import re
        platform_match = re.search(r'(github|slack|discord|stripe|paypal|google|microsoft)', task_lower)
        platform = platform_match.group(0) if platform_match else "unknown"

        return {
            "status": "auth_required",
            "platform": platform,
            "instruction": f"Configure {platform.upper()}_CLIENT_ID and {platform.upper()}_CLIENT_SECRET in .env",
        }

    elif "2fa" in task_lower or "totp" in task_lower:
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
                    {"id": k, "platform": v["platform"], "user_id": v["user_id"]}
                    for k, v in sessions.items()
                ],
            }

    else:
        return {
            "status": "ok",
            "message": "Account Manager: supports OAuth2, 2FA/TOTP, session management",
            "examples": [
                "authorize github via OAuth2",
                "verify 2fa with secret XXX code 123456",
                "list active sessions",
            ],
        }
