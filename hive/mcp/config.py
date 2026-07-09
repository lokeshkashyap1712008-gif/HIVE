"""MCP server configuration — load, save, validate server configs."""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict

MCP_CONFIG_DIR = Path(os.environ.get("HIVE_HOME", Path.home() / ".hive"))
MCP_CONFIG_FILE = MCP_CONFIG_DIR / "mcp_servers.json"


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    url: str
    transport: str = "http"
    headers: dict = field(default_factory=dict)
    enabled: bool = True
    description: str = ""

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
        return True, ""


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
