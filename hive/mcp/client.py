"""MCP Client Manager — connects to MCP servers via Streamable HTTP transport."""

import json
import uuid
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass, field
import httpx

from hive.mcp.config import MCPServerConfig, mcp_config

logger = logging.getLogger(__name__)

# MCP JSON-RPC version
JSONRPC_VERSION = "2.0"

# MCP protocol version
MCP_PROTOCOL_VERSION = "2025-06-18"


@dataclass
class MCPServerConnection:
    """Tracks connection state for a single MCP server."""
    name: str
    url: str
    headers: dict = field(default_factory=dict)
    session_id: Optional[str] = None
    server_capabilities: dict = field(default_factory=dict)
    server_info: dict = field(default_factory=dict)
    connected: bool = False
    tools: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    _request_id: int = 0

    def next_id(self) -> int:
        self._request_id += 1
        return self._request_id


class MCPClientManager:
    """Manages connections to multiple MCP servers via HTTP transport."""

    def __init__(self):
        self._connections: dict[str, MCPServerConnection] = {}
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http_client

    async def _send_request(
        self, connection: MCPServerConnection, method: str, params: dict = None
    ) -> dict:
        """Send a JSON-RPC request to an MCP server."""
        client = await self._get_client()

        request_id = connection.next_id()
        payload = {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **connection.headers,
        }

        # Add session ID if we have one
        if connection.session_id:
            headers["Mcp-Session-Id"] = connection.session_id

        try:
            response = await client.post(
                connection.url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            # Capture session ID from response
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                connection.session_id = session_id

            # Handle SSE responses
            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return await self._parse_sse_response(response)
            else:
                return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"MCP HTTP error for {connection.name}: {e.response.status_code}")
            return {"error": {"code": -32000, "message": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}}
        except httpx.ConnectError as e:
            logger.error(f"MCP connection error for {connection.name}: {e}")
            return {"error": {"code": -32000, "message": f"Connection failed: {e}"}}
        except Exception as e:
            logger.error(f"MCP request error for {connection.name}: {e}")
            return {"error": {"code": -32603, "message": str(e)}}

    async def _parse_sse_response(self, response: httpx.Response) -> dict:
        """Parse Server-Sent Events response to extract JSON-RPC result."""
        result = None
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str:
                    try:
                        data = json.loads(data_str)
                        if "result" in data or "error" in data:
                            result = data
                    except json.JSONDecodeError:
                        continue
        return result or {"error": {"code": -32603, "message": "No valid JSON-RPC response in SSE stream"}}

    async def connect(self, server_config: MCPServerConfig) -> tuple[bool, str]:
        """Connect to an MCP server and initialize the session."""
        name = server_config.name

        # Create connection
        connection = MCPServerConnection(
            name=name,
            url=server_config.url,
            headers=server_config.headers,
        )

        # Send initialize request
        init_result = await self._send_request(connection, "initialize", {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": False},
                "sampling": {},
            },
            "clientInfo": {
                "name": "hive-os",
                "version": "0.1.0",
            },
        })

        if "error" in init_result:
            error_msg = init_result["error"].get("message", "Unknown error")
            return False, f"Initialize failed: {error_msg}"

        result = init_result.get("result", {})
        connection.server_info = result.get("serverInfo", {})
        connection.server_capabilities = result.get("capabilities", {})
        connection.connected = True

        # Send initialized notification
        await self._send_request(connection, "notifications/initialized")

        self._connections[name] = connection
        logger.info(f"MCP connected to '{name}' at {server_config.url}")
        return True, f"Connected to {name}"

    async def disconnect(self, name: str) -> tuple[bool, str]:
        """Disconnect from an MCP server."""
        connection = self._connections.get(name)
        if not connection:
            return False, f"Not connected to '{name}'"

        connection.connected = False
        del self._connections[name]
        logger.info(f"MCP disconnected from '{name}'")
        return True, f"Disconnected from {name}"

    async def list_tools(self, name: str) -> tuple[bool, list[dict] | str]:
        """List available tools from a connected server."""
        connection = self._connections.get(name)
        if not connection or not connection.connected:
            return False, f"Not connected to '{name}'"

        # Check if server supports tools
        if not connection.server_capabilities.get("tools"):
            return False, f"Server '{name}' does not expose tools"

        result = await self._send_request(connection, "tools/list")

        if "error" in result:
            return False, result["error"].get("message", "Unknown error")

        tools = result.get("result", {}).get("tools", [])
        connection.tools = tools
        return True, tools

    async def call_tool(
        self, name: str, tool_name: str, arguments: dict = None
    ) -> dict:
        """Call a tool on a connected MCP server."""
        connection = self._connections.get(name)
        if not connection or not connection.connected:
            return {"error": f"Not connected to '{name}'"}

        result = await self._send_request(connection, "tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

        if "error" in result:
            return {"error": result["error"].get("message", "Unknown error")}

        return result.get("result", {})

    async def list_resources(self, name: str) -> tuple[bool, list[dict] | str]:
        """List available resources from a connected server."""
        connection = self._connections.get(name)
        if not connection or not connection.connected:
            return False, f"Not connected to '{name}'"

        if not connection.server_capabilities.get("resources"):
            return False, f"Server '{name}' does not expose resources"

        result = await self._send_request(connection, "resources/list")

        if "error" in result:
            return False, result["error"].get("message", "Unknown error")

        resources = result.get("result", {}).get("resources", [])
        connection.resources = resources
        return True, resources

    async def read_resource(self, name: str, uri: str) -> dict:
        """Read a resource from a connected MCP server."""
        connection = self._connections.get(name)
        if not connection or not connection.connected:
            return {"error": f"Not connected to '{name}'"}

        result = await self._send_request(connection, "resources/read", {
            "uri": uri,
        })

        if "error" in result:
            return {"error": result["error"].get("message", "Unknown error")}

        return result.get("result", {})

    def get_connection(self, name: str) -> Optional[MCPServerConnection]:
        """Get a connection by server name."""
        return self._connections.get(name)

    def list_connected(self) -> list[MCPServerConnection]:
        """List all active connections."""
        return [c for c in self._connections.values() if c.connected]

    def is_connected(self, name: str) -> bool:
        """Check if connected to a server."""
        conn = self._connections.get(name)
        return conn is not None and conn.connected

    def get_all_tools(self) -> dict[str, list[dict]]:
        """Get tools from all connected servers. Returns {server_name: [tools]}."""
        return {
            name: conn.tools
            for name, conn in self._connections.items()
            if conn.connected and conn.tools
        }

    async def shutdown(self):
        """Disconnect from all servers and close HTTP client."""
        for name in list(self._connections.keys()):
            await self.disconnect(name)
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None


mcp_client = MCPClientManager()
