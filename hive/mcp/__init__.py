"""MCP (Model Context Protocol) integration for HIVE OS."""

from hive.mcp.config import mcp_config
from hive.mcp.client import mcp_client
from hive.mcp.bridge import mcp_bridge

__all__ = ["mcp_config", "mcp_client", "mcp_bridge"]
