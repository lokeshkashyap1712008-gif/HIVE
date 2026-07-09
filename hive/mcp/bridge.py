"""MCP Tool Bridge — discovers MCP tools and routes calls to servers."""

import json
import logging
from typing import Optional
from hive.mcp.client import mcp_client, MCPServerConnection
from hive.mcp.config import mcp_config

logger = logging.getLogger(__name__)

# Prefix for all MCP tools in the TOOLS registry
MCP_TOOL_PREFIX = "mcp_"

# Separator between server name and tool name
MCP_SEPARATOR = "__"


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Convert MCP tool name to HIVE tool name format.

    Example: mcp_tool_name("gmail", "send_email") -> "mcp_gmail__send_email"
    """
    return f"{MCP_TOOL_PREFIX}{server_name}{MCP_SEPARATOR}{tool_name}"


def parse_mcp_tool_name(hive_tool_name: str) -> Optional[tuple[str, str]]:
    """Parse a HIVE tool name back to MCP server and tool names.

    Example: parse_mcp_tool_name("mcp_gmail__send_email") -> ("gmail", "send_email")
    Returns None if not an MCP tool.
    """
    if not hive_tool_name.startswith(MCP_TOOL_PREFIX):
        return None

    rest = hive_tool_name[len(MCP_TOOL_PREFIX):]
    parts = rest.split(MCP_SEPARATOR, 1)
    if len(parts) != 2:
        return None

    return parts[0], parts[1]


def convert_mcp_tool_to_hive(server_name: str, mcp_tool: dict) -> tuple[str, dict]:
    """Convert an MCP tool schema to HIVE TOOLS format.

    MCP tool format:
    {
        "name": "send_email",
        "description": "Send an email",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient"},
                "subject": {"type": "string", "description": "Subject line"},
                "body": {"type": "string", "description": "Email body"}
            },
            "required": ["to", "subject", "body"]
        }
    }

    HIVE tool format:
    {
        "description": "Send an email (via MCP: gmail)",
        "parameters": {
            "to": {"type": "string", "description": "Recipient"},
            "subject": {"type": "string", "description": "Subject line"},
            "body": {"type": "string", "description": "Email body"}
        }
    }
    """
    tool_name = mcp_tool.get("name", "")
    description = mcp_tool.get("description", "")
    input_schema = mcp_tool.get("inputSchema", {})

    hive_name = mcp_tool_name(server_name, tool_name)
    hive_description = f"{description} [MCP: {server_name}]"

    # Convert inputSchema.properties to HIVE parameters format
    properties = {}
    for prop_name, prop_spec in input_schema.get("properties", {}).items():
        properties[prop_name] = {
            "type": prop_spec.get("type", "string"),
            "description": prop_spec.get("description", prop_name),
        }

    hive_tool = {
        "description": hive_description,
        "parameters": properties,
        "_mcp": {
            "server": server_name,
            "tool": tool_name,
            "required": input_schema.get("required", []),
        },
    }

    return hive_name, hive_tool


class MCPToolBridge:
    """Bridges MCP tools to HIVE's tool system.

    Responsibilities:
    1. Connect to all configured MCP servers
    2. Discover tools from each server
    3. Convert MCP tool schemas to HIVE format
    4. Provide execute_mcp_tool() for routing tool calls
    5. Track which server owns each tool
    """

    def __init__(self):
        # Maps HIVE tool name -> (server_name, original_mcp_tool_name)
        self._tool_map: dict[str, tuple[str, str]] = {}
        # Maps server_name -> list of HIVE tool names
        self._server_tools: dict[str, list[str]] = {}
        self._initialized = False

    async def initialize(self) -> dict:
        """Connect to all configured MCP servers and discover their tools.

        Returns a summary: {connected: int, tools: int, errors: [...]}
        """
        self._tool_map.clear()
        self._server_tools.clear()

        servers = mcp_config.get_enabled_servers()
        connected = 0
        total_tools = 0
        errors = []

        for server_config in servers:
            try:
                success, msg = await mcp_client.connect(server_config)
                if not success:
                    errors.append(f"{server_config.name}: {msg}")
                    continue

                connected += 1

                # Discover tools
                ok, tools = await mcp_client.list_tools(server_config.name)
                if not ok:
                    errors.append(f"{server_config.name} tools: {tools}")
                    continue

                # Convert and register tools
                server_tool_names = []
                for mcp_tool in tools:
                    hive_name, hive_tool = convert_mcp_tool_to_hive(
                        server_config.name, mcp_tool
                    )
                    self._tool_map[hive_name] = (server_config.name, mcp_tool["name"])
                    server_tool_names.append(hive_name)
                    total_tools += 1

                self._server_tools[server_config.name] = server_tool_names
                logger.info(
                    f"MCP bridge: {server_config.name} -> {len(tools)} tools"
                )

            except Exception as e:
                errors.append(f"{server_config.name}: {str(e)}")
                logger.error(f"MCP bridge init error for {server_config.name}: {e}")

        self._initialized = True

        return {
            "connected": connected,
            "tools": total_tools,
            "errors": errors,
        }

    def get_hive_tools(self) -> dict[str, dict]:
        """Get all MCP tools in HIVE TOOLS format.

        Returns a dict suitable for merging into TOOLS.
        """
        hive_tools = {}
        for server_name, tool_names in self._server_tools.items():
            for hive_name in tool_names:
                server_conn = mcp_client.get_connection(server_name)
                if not server_conn:
                    continue
                # Find the original MCP tool to get its schema
                _, original_name = self._tool_map[hive_name]
                for mcp_tool in server_conn.tools:
                    if mcp_tool["name"] == original_name:
                        _, hive_tool = convert_mcp_tool_to_hive(
                            server_name, mcp_tool
                        )
                        hive_tools[hive_name] = hive_tool
                        break
        return hive_tools

    async def execute_mcp_tool(self, hive_tool_name: str, **kwargs) -> dict:
        """Execute an MCP tool call.

        Args:
            hive_tool_name: The HIVE tool name (e.g., "mcp_gmail__send_email")
            **kwargs: Tool arguments

        Returns:
            Tool result dict
        """
        parsed = parse_mcp_tool_name(hive_tool_name)
        if not parsed:
            return {"error": f"Not an MCP tool: {hive_tool_name}"}

        server_name, original_tool_name = parsed

        # Remove internal _mcp metadata from kwargs if present
        kwargs.pop("_mcp", None)

        result = await mcp_client.call_tool(server_name, original_tool_name, kwargs)

        # Normalize result format
        if isinstance(result, dict):
            if "content" in result:
                # MCP content format: [{"type": "text", "text": "..."}]
                content = result["content"]
                if isinstance(content, list):
                    texts = [item.get("text", str(item)) for item in content]
                    return {"result": "\n".join(texts)}
                return {"result": str(content)}
            if "error" in result:
                return {"error": result["error"]}
            return result
        return {"result": str(result)}

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool name belongs to an MCP server."""
        return tool_name in self._tool_map

    def get_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Get the server name that provides a tool."""
        parsed = parse_mcp_tool_name(tool_name)
        return parsed[0] if parsed else None

    def get_tools_for_server(self, server_name: str) -> list[str]:
        """Get all HIVE tool names for a specific server."""
        return self._server_tools.get(server_name, [])

    def get_status(self) -> dict:
        """Get bridge status summary."""
        return {
            "initialized": self._initialized,
            "servers": len(self._server_tools),
            "total_tools": len(self._tool_map),
            "server_details": {
                name: len(tools)
                for name, tools in self._server_tools.items()
            },
        }

    async def refresh_server(self, server_name: str) -> tuple[bool, str]:
        """Re-discover tools for a specific server."""
        server_conn = mcp_client.get_connection(server_name)
        if not server_conn or not server_conn.connected:
            return False, f"Not connected to '{server_name}'"

        # Clear old tools
        old_tools = self._server_tools.get(server_name, [])
        for tool_name in old_tools:
            self._tool_map.pop(tool_name, None)
        self._server_tools.pop(server_name, None)

        # Re-discover
        ok, tools = await mcp_client.list_tools(server_name)
        if not ok:
            return False, f"Failed to list tools: {tools}"

        server_tool_names = []
        for mcp_tool in tools:
            hive_name, hive_tool = convert_mcp_tool_to_hive(server_name, mcp_tool)
            self._tool_map[hive_name] = (server_name, mcp_tool["name"])
            server_tool_names.append(hive_name)

        self._server_tools[server_name] = server_tool_names
        return True, f"Refreshed {len(tools)} tools from '{server_name}'"

    async def shutdown(self):
        """Clean up bridge resources."""
        self._tool_map.clear()
        self._server_tools.clear()
        self._initialized = False


mcp_bridge = MCPToolBridge()
