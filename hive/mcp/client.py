"""MCP Client Manager — connects to MCP servers via HTTP transport with OAuth support."""

import json
import time
import secrets
import asyncio
import logging
import webbrowser
import threading
from typing import Optional
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
import httpx

from hive.mcp.config import (
    MCPServerConfig, mcp_config,
    store_mcp_token, load_mcp_token, update_mcp_token,
    is_token_expired, has_stored_token,
)

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
    auth_type: str = "none"
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


# ─── OAuth Callback Server ──────────────────────────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect callback."""
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


def _wait_for_oauth_callback(port: int, timeout: int = 120) -> tuple[Optional[str], Optional[str]]:
    """Start a local server and wait for the OAuth callback."""
    _OAuthCallbackHandler.code = None
    _OAuthCallbackHandler.error = None
    server = HTTPServer(("localhost", port), _OAuthCallbackHandler)
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


# ─── MCP Client Manager ─────────────────────────────────────────────────

class MCPClientManager:
    """Manages connections to multiple MCP servers via HTTP transport."""

    def __init__(self):
        self._connections: dict[str, MCPServerConnection] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._server_configs: dict[str, MCPServerConfig] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http_client

    async def _send_request(
        self, connection: MCPServerConnection, method: str, params: dict = None,
        retry_on_401: bool = True,
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

            # Handle 401 — try token refresh if OAuth
            if response.status_code == 401 and retry_on_401 and connection.auth_type == "oauth":
                refreshed = await self._refresh_token(connection)
                if refreshed:
                    # Update headers with new token and retry
                    headers["Authorization"] = f"Bearer {connection.headers.get('Authorization', '').split(' ', 1)[-1]}"
                    return await self._send_request(connection, method, params, retry_on_401=False)

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

    async def _refresh_token(self, connection: MCPServerConnection) -> bool:
        """Refresh an expired OAuth token. Returns True if successful."""
        config = self._server_configs.get(connection.name)
        if not config or config.auth_type != "oauth":
            return False

        tokens = load_mcp_token(connection.name)
        if not tokens or not tokens.get("refresh_token"):
            return False

        try:
            client = await self._get_client()
            resp = await client.post(
                config.oauth_token_url,
                data={
                    "client_id": config.oauth_client_id,
                    "client_secret": config.oauth_client_secret,
                    "refresh_token": tokens["refresh_token"],
                    "grant_type": "refresh_token",
                },
                headers={"Accept": "application/json"},
                timeout=15,
            )

            if resp.status_code != 200:
                logger.error(f"Token refresh failed for {connection.name}: {resp.text[:200]}")
                return False

            new_tokens = resp.json()
            access_token = new_tokens.get("access_token")
            if not access_token:
                return False

            # Update stored tokens
            expires_in = new_tokens.get("expires_in", 3600)
            update_mcp_token(connection.name, access_token, expires_in)

            # Update connection headers
            connection.headers["Authorization"] = f"Bearer {access_token}"
            logger.info(f"Token refreshed for {connection.name}")
            return True

        except Exception as e:
            logger.error(f"Token refresh error for {connection.name}: {e}")
            return False

    async def authenticate_oauth(self, server_config: MCPServerConfig) -> tuple[bool, str]:
        """Run OAuth 2.0 Authorization Code flow for an MCP server.

        1. Build OAuth consent URL
        2. Open browser
        3. Wait for callback on localhost
        4. Exchange code for tokens
        5. Store tokens
        6. Update connection headers
        """
        server_config.ensure_oauth_defaults()
        port = server_config.oauth_redirect_port
        redirect_uri = f"http://localhost:{port}/callback"

        state = secrets.token_urlsafe(16)
        params = {
            "client_id": server_config.oauth_client_id,
            "redirect_uri": redirect_uri,
            "scope": server_config.oauth_scopes,
            "state": state,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
        }

        auth_url = f"{server_config.oauth_auth_url}?{urlencode(params)}"
        logger.info(f"Opening OAuth URL for {server_config.name}")

        # Open browser for authentication
        webbrowser.open(auth_url)

        # Wait for callback
        code, error = _wait_for_oauth_callback(port)
        if error:
            return False, f"OAuth failed: {error}"
        if not code:
            return False, "No authorization code received"

        # Exchange code for tokens
        try:
            client = await self._get_client()
            resp = await client.post(
                server_config.oauth_token_url,
                data={
                    "client_id": server_config.oauth_client_id,
                    "client_secret": server_config.oauth_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )

            if resp.status_code != 200:
                return False, f"Token exchange failed: {resp.text[:200]}"

            tokens = resp.json()
            if "error" in tokens:
                return False, f"Token error: {tokens['error_description']}"

            # Store tokens
            store_mcp_token(server_config.name, tokens)

            return True, f"Authenticated successfully"

        except Exception as e:
            return False, f"Token exchange error: {e}"

    async def connect(self, server_config: MCPServerConfig) -> tuple[bool, str]:
        """Connect to an MCP server and initialize the session."""
        name = server_config.name
        self._server_configs[name] = server_config

        # Build headers
        headers = dict(server_config.headers)

        # Handle OAuth — use stored token or authenticate
        if server_config.auth_type == "oauth":
            if has_stored_token(name) and not is_token_expired(name):
                tokens = load_mcp_token(name)
                headers["Authorization"] = f"Bearer {tokens['access_token']}"
            elif has_stored_token(name) and is_token_expired(name):
                # Token expired, will be refreshed on first 401
                tokens = load_mcp_token(name)
                headers["Authorization"] = f"Bearer {tokens['access_token']}"
            else:
                # No tokens — need to authenticate
                return False, f"Run /mcp auth {name} to authenticate first"

        # Create connection
        connection = MCPServerConnection(
            name=name,
            url=server_config.url,
            headers=headers,
            auth_type=server_config.auth_type,
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
        if "tools" not in connection.server_capabilities:
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

        if "resources" not in connection.server_capabilities:
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
