"""OAuth 2.0 flows for GitHub and Google — local callback server + token storage."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

logger = logging.getLogger(__name__)

CALLBACK_PORT = int(os.environ.get("HIVE_OAUTH_PORT", "8765"))
CALLBACK_URI = f"http://localhost:{CALLBACK_PORT}/callback"

OAUTH_CONFIG = {
    "github": {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": os.environ.get("GITHUB_OAUTH_SCOPES", "read:user user:email"),
        "client_id_env": "GITHUB_CLIENT_ID",
        "client_secret_env": "GITHUB_CLIENT_SECRET",
    },
    "google": {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "scopes": os.environ.get(
            "GOOGLE_OAUTH_SCOPES",
            "openid email profile",
        ),
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
    },
}


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    code: Optional[str] = None
    error: Optional[str] = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        _OAuthCallbackHandler.code = params.get("code", [None])[0]
        _OAuthCallbackHandler.error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _OAuthCallbackHandler.code:
            body = "<html><body><h2>Authorization successful!</h2><p>You can close this tab and return to HIVE.</p></body></html>"
        else:
            body = f"<html><body><h2>Authorization failed</h2><p>{_OAuthCallbackHandler.error}</p></body></html>"
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass


def _get_credentials(platform: str) -> tuple[str, str]:
    cfg = OAUTH_CONFIG[platform]
    client_id = os.environ.get(cfg["client_id_env"], "")
    client_secret = os.environ.get(cfg["client_secret_env"], "")
    if not client_id or not client_secret:
        raise ValueError(
            f"Set {cfg['client_id_env']} and {cfg['client_secret_env']} in .env"
        )
    return client_id, client_secret


def _wait_for_callback(timeout: int = 120) -> tuple[Optional[str], Optional[str]]:
    _OAuthCallbackHandler.code = None
    _OAuthCallbackHandler.error = None
    server = HTTPServer(("localhost", CALLBACK_PORT), _OAuthCallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _OAuthCallbackHandler.code or _OAuthCallbackHandler.error:
            server.server_close()
            return _OAuthCallbackHandler.code, _OAuthCallbackHandler.error
        time.sleep(0.3)
    server.server_close()
    return None, "timeout"


async def start_oauth(platform: str) -> dict:
    """Run OAuth authorization code flow for github or google."""
    platform = platform.lower().strip()
    if platform not in OAUTH_CONFIG:
        return {"status": "error", "reason": f"Unsupported platform: {platform}"}

    try:
        client_id, client_secret = _get_credentials(platform)
    except ValueError as e:
        return {"status": "auth_required", "platform": platform, "instruction": str(e)}

    state = secrets.token_urlsafe(16)
    cfg = OAUTH_CONFIG[platform]

    params = {
        "client_id": client_id,
        "redirect_uri": CALLBACK_URI,
        "scope": cfg["scopes"],
        "state": state,
        "response_type": "code",
    }
    if platform == "google":
        params["access_type"] = "offline"
        params["prompt"] = "consent"

    auth_url = f"{cfg['auth_url']}?{urlencode(params)}"
    logger.info("Opening OAuth URL for %s", platform)
    webbrowser.open(auth_url)

    code, error = _wait_for_callback()
    if error:
        return {"status": "error", "platform": platform, "reason": error}
    if not code:
        return {"status": "error", "platform": platform, "reason": "No authorization code received"}

    # Exchange code for token
    token_data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": CALLBACK_URI,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(cfg["token_url"], data=token_data, headers=headers, timeout=30)
        if resp.status_code != 200:
            return {
                "status": "error",
                "platform": platform,
                "reason": f"Token exchange failed: {resp.text[:200]}",
            }
        tokens = resp.json()

    # Store session
    from hive.agents.workers.account_manager import store_session

    user_id = "oauth_user"
    if platform == "github" and tokens.get("access_token"):
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
                timeout=15,
            )
            if r.status_code == 200:
                user_id = r.json().get("login", user_id)

    session_id = store_session(platform, user_id, tokens, metadata={"oauth": True})

    # Also save token reference in vault extra field
    try:
        from hive.browser.vault import store_credential
        store_credential(
            f"{platform}.com",
            user_id,
            tokens.get("access_token", "")[:8] + "...",  # don't store full token as password
            extra={"session_id": session_id, "has_refresh": bool(tokens.get("refresh_token"))},
        )
    except Exception:
        pass

    return {
        "status": "completed",
        "platform": platform,
        "user_id": user_id,
        "session_id": session_id,
        "scopes": cfg["scopes"],
        "expires_in": tokens.get("expires_in"),
        "message": f"OAuth complete for {platform}. Session ID: {session_id}",
    }
