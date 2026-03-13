"""Lightweight MCP (Model Context Protocol) client using only stdlib.

Used by the ``addmcptools`` CLI command to discover tools exposed by an
MCP server.  No third-party dependencies are required.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from urllib import error, request


class MCPClientError(RuntimeError):
    """Raised when an MCP protocol or connection error occurs."""


class MCPClient:
    """Simplified MCP client that speaks JSON-RPC 2.0 over HTTP(S).

    Parameters
    ----------
    server_url:
        The base URL of the MCP server (e.g. ``https://mcp.example.com/sse``).
    headers:
        Optional extra headers to send with every request (e.g. API keys).
    auth_type:
        Authentication type declared on the server (``"none"``, ``"headers"``
        or ``"oauth2"``).  Used only to produce a helpful diagnostic when the
        server responds with 401 during tool discovery.
    """

    def __init__(
        self,
        server_url: str,
        headers: dict[str, str] | None = None,
        auth_type: str = "headers",
    ):
        self.server_url = server_url.rstrip("/")
        self.extra_headers: dict[str, str] = dict(headers or {})
        self.auth_type = auth_type
        self.session_id: str | None = None
        self.tools: list[dict[str, Any]] = []
        self.initialized = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Perform the MCP ``initialize`` + ``tools/list`` handshake.

        Returns ``True`` on success, ``False`` on failure.
        """
        try:
            self._make_request(
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "clientInfo": {
                        "name": "cognitive-mcp-client",
                        "version": "1.0.0",
                    },
                },
            )

            result = self._make_request("tools/list")
            self.tools = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("inputSchema", {}),
                }
                for t in result.get("tools", [])
            ]
            self.initialized = True
            return True
        except MCPClientError as exc:
            msg = str(exc)
            if "HTTP 401" in msg and self.auth_type == "oauth2":
                print(
                    "[MCPClient] Received 401 — this OAuth 2.1 server requires user "
                    "authorization.\n"
                    "  Tool discovery without auth failed, but you can still create the "
                    "server definition.\n"
                    "  Complete the OAuth authorization flow from the CogSol portal after "
                    "running `migrate`."
                )
            else:
                print(f"[MCPClient] Failed to initialize: {exc}")
            return False
        except Exception as exc:
            print(f"[MCPClient] Failed to initialize: {exc}")
            return False

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tools discovered during ``initialize``."""
        return list(self.tools)

    def disconnect(self) -> None:
        """Send a best-effort DELETE to close the session."""
        if not self.session_id:
            return
        try:
            headers = {"Mcp-Session-Id": self.session_id}
            headers.update(self.extra_headers)
            req = request.Request(self.server_url, headers=headers, method="DELETE")
            with request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        headers.update(self.extra_headers)

        body = json.dumps(payload).encode("utf-8")
        req = request.Request(self.server_url, data=body, headers=headers, method="POST")

        try:
            with request.urlopen(req, timeout=30) as resp:
                # Capture session id on initialize
                if method == "initialize":
                    sid = resp.headers.get("Mcp-Session-Id")
                    if sid:
                        self.session_id = sid

                content_type = (resp.headers.get("Content-Type") or "").lower()
                raw = resp.read().decode("utf-8")

                if "text/event-stream" in content_type:
                    return self._parse_sse(raw)

                # Default: treat as JSON
                result = json.loads(raw)
                if "error" in result:
                    raise MCPClientError(f"MCP Error: {result['error']}")
                return result.get("result", {})

        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise MCPClientError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc
        except error.URLError as exc:
            raise MCPClientError(f"Connection error: {exc.reason}") from exc

    @staticmethod
    def _parse_sse(text: str) -> dict[str, Any]:
        """Extract the first JSON-RPC result from an SSE stream."""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if "result" in data:
                        return data["result"]
                    if "error" in data:
                        raise MCPClientError(f"MCP Error: {data['error']}")
                except json.JSONDecodeError:
                    continue
        raise MCPClientError("No valid JSON-RPC response found in SSE stream")
