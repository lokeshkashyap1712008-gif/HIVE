"""MCP server configuration — load, save, validate server configs + OAuth tokens."""

import json
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

MCP_CONFIG_DIR = Path(os.environ.get("HIVE_HOME", Path.home() / ".hive"))
MCP_CONFIG_FILE = MCP_CONFIG_DIR / "mcp_servers.json"
MCP_TOKENS_FILE = MCP_CONFIG_DIR / "mcp_tokens.json"

# Google OAuth defaults for Google Workspace MCP servers
GOOGLE_OAUTH_DEFAULTS = {
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "token_url": "https://oauth2.googleapis.com/token",
    "scopes": "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose",
}


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    url: str
    transport: str = "http"
    headers: dict = field(default_factory=dict)
    enabled: bool = True
    description: str = ""
    # OAuth fields
    auth_type: str = "none"  # "none" | "bearer" | "oauth"
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_auth_url: str = ""
    oauth_token_url: str = ""
    oauth_scopes: str = ""
    oauth_redirect_port: int = 8766

    def validate(self) -> tuple[bool, str]:
        """Validate server config. Returns (valid, reason)."""
        if not self.name or not self.name.strip():
            return False, "Server name is required"
        if not self.url or not self.url.strip():
            return False, "Server URL is required"
        if self.transport not in ("http",):
            return False, f"Unsupported transport: {self.transport}"
        if not self.url.startswith(("http://", "https://")):
            return False, "URL must start with http:// or https://"
        if self.auth_type == "oauth":
            if not self.oauth_client_id:
                return False, "OAuth client_id is required"
            if not self.oauth_client_secret:
                return False, "OAuth client_secret is required"
        return True, ""

    def is_google_mcp(self) -> bool:
        """Check if this is a Google Workspace MCP server."""
        return "googleapis.com" in self.url

    def ensure_oauth_defaults(self):
        """Fill in default OAuth URLs for Google MCP servers if not set."""
        if self.is_google_mcp():
            if not self.oauth_auth_url:
                self.oauth_auth_url = GOOGLE_OAUTH_DEFAULTS["auth_url"]
            if not self.oauth_token_url:
                self.oauth_token_url = GOOGLE_OAUTH_DEFAULTS["token_url"]
            if not self.oauth_scopes:
                self.oauth_scopes = GOOGLE_OAUTH_DEFAULTS["scopes"]


# ─── Token Storage ──────────────────────────────────────────────────────

def _load_tokens() -> dict:
    """Load all MCP tokens from disk."""
    if not MCP_TOKENS_FILE.exists():
        return {}
    try:
        with open(MCP_TOKENS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_tokens(tokens: dict):
    """Save all MCP tokens to disk."""
    MCP_TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(MCP_TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def store_mcp_token(server_name: str, tokens: dict):
    """Store OAuth tokens for an MCP server.

    Tokens dict should contain:
        access_token, refresh_token, token_type, expires_in, scope
    """
    all_tokens = _load_tokens()
    expires_at = time.time() + tokens.get("expires_in", 3600)
    all_tokens[server_name] = {
        "access_token": tokens.get("access_token", ""),
        "refresh_token": tokens.get("refresh_token", ""),
        "token_type": tokens.get("token_type", "Bearer"),
        "expires_at": expires_at,
        "scope": tokens.get("scope", ""),
    }
    _save_tokens(all_tokens)


def load_mcp_token(server_name: str) -> Optional[dict]:
    """Load OAuth tokens for an MCP server. Returns None if not found."""
    all_tokens = _load_tokens()
    return all_tokens.get(server_name)


def update_mcp_token(server_name: str, access_token: str, expires_in: int = 3600):
    """Update just the access_token (after refresh)."""
    all_tokens = _load_tokens()
    if server_name in all_tokens:
        all_tokens[server_name]["access_token"] = access_token
        all_tokens[server_name]["expires_at"] = time.time() + expires_in
        _save_tokens(all_tokens)


def delete_mcp_token(server_name: str):
    """Delete stored tokens for an MCP server."""
    all_tokens = _load_tokens()
    if server_name in all_tokens:
        del all_tokens[server_name]
        _save_tokens(all_tokens)


def is_token_expired(server_name: str) -> bool:
    """Check if a server's token is expired or about to expire (within 60s)."""
    tokens = load_mcp_token(server_name)
    if not tokens:
        return True
    expires_at = tokens.get("expires_at", 0)
    return time.time() >= (expires_at - 60)


def has_stored_token(server_name: str) -> bool:
    """Check if we have stored tokens for a server."""
    tokens = load_mcp_token(server_name)
    return tokens is not None and bool(tokens.get("access_token"))


# ─── Config Manager ─────────────────────────────────────────────────────

class MCPConfigManager:
    """Manages MCP server configurations stored in ~/.hive/mcp_servers.json."""

    def __init__(self):
        self._config_file = MCP_CONFIG_FILE
        self._servers: dict[str, MCPServerConfig] = {}
        self._load()

    def _load(self):
        """Load config from disk."""
        if not self._config_file.exists():
            self._servers = {}
            return
        try:
            with open(self._config_file, "r") as f:
                data = json.load(f)
            for server_data in data.get("servers", []):
                config = MCPServerConfig(**server_data)
                self._servers[config.name] = config
        except (json.JSONDecodeError, TypeError, KeyError):
            self._servers = {}

    def _save(self):
        """Save config to disk."""
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "servers": [asdict(s) for s in self._servers.values()]
        }
        with open(self._config_file, "w") as f:
            json.dump(data, f, indent=2)

    def list_servers(self) -> list[MCPServerConfig]:
        """List all configured servers."""
        return list(self._servers.values())

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """Get a server config by name."""
        return self._servers.get(name)

    def add_server(self, config: MCPServerConfig) -> tuple[bool, str]:
        """Add a new server. Returns (success, reason)."""
        valid, reason = config.validate()
        if not valid:
            return False, reason
        self._servers[config.name] = config
        self._save()
        return True, f"Server '{config.name}' added"

    def update_server(self, name: str, **kwargs) -> tuple[bool, str]:
        """Update an existing server config."""
        config = self._servers.get(name)
        if not config:
            return False, f"Server '{name}' not found"
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
        valid, reason = config.validate()
        if not valid:
            return False, reason
        self._save()
        return True, f"Server '{name}' updated"

    def remove_server(self, name: str) -> tuple[bool, str]:
        """Remove a server config."""
        if name not in self._servers:
            return False, f"Server '{name}' not found"
        del self._servers[name]
        self._save()
        return True, f"Server '{name}' removed"

    def get_enabled_servers(self) -> list[MCPServerConfig]:
        """Get all enabled servers."""
        return [s for s in self._servers.values() if s.enabled]

    def toggle_server(self, name: str, enabled: bool) -> tuple[bool, str]:
        """Enable or disable a server."""
        config = self._servers.get(name)
        if not config:
            return False, f"Server '{name}' not found"
        config.enabled = enabled
        self._save()
        state = "enabled" if enabled else "disabled"
        return True, f"Server '{name}' {state}"


mcp_config = MCPConfigManager()
