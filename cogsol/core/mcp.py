"""Lightweight MCP (Model Context Protocol) client using only stdlib.

Used by the ``addmcptools`` CLI command to discover tools exposed by an
MCP server.  No third-party dependencies are required.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast
from urllib import error, request

from cogsol import __version__
from cogsol.core.http_errors import summarize_http_error

# ``urllib`` otherwise announces itself as ``Python-urllib/x.y``, a signature
# that CDNs in front of public MCP servers (e.g. Cloudflare rule 1010) reject
# with 403 before the request ever reaches the server.
DEFAULT_USER_AGENT = f"cogsol-framework/{__version__} (+https://cogsol.ai; MCP client)"


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
            print(self._describe_initialize_failure(exc))
            return False
        except Exception as exc:
            print(f"[MCPClient] Failed to initialize: {exc}")
            return False

    def _describe_initialize_failure(self, exc: MCPClientError) -> str:
        """Turn a handshake failure into an explanation instead of a raw payload."""
        msg = str(exc)

        if "HTTP 401" in msg:
            if self.auth_type == "oauth2":
                return (
                    "[MCPClient] The server answered 401 — it requires user authorization "
                    "before listing tools.\n"
                    "  This is expected for OAuth 2.1 servers: discovery continues through "
                    "the CogSol API,\n"
                    "  which holds the OAuth tokens."
                )
            return (
                "[MCPClient] The server answered 401 Unauthorized — the credentials sent "
                "were rejected.\n"
                "  Check the header values you entered (or whether this server needs "
                "auth_type='oauth2')."
            )

        if "HTTP 403" in msg:
            detail = (
                "  A CDN or WAF in front of the server blocked the request before it "
                "reached the MCP endpoint\n"
                "  (Cloudflare error 1010 means the client signature was rejected)."
            )
            if self.auth_type == "oauth2":
                return (
                    "[MCPClient] The server answered 403 — a direct connection from here "
                    "is not allowed.\n" + detail + "\n"
                    "  Discovery continues through the CogSol API, so this is not fatal."
                )
            return (
                "[MCPClient] The server answered 403 — a direct connection from here is "
                "not allowed.\n" + detail + "\n"
                "  Tools cannot be listed; verify the URL and whether the server requires "
                "specific headers."
            )

        if "Connection error" in msg:
            return (
                f"[MCPClient] Could not reach the server: {msg}\n"
                "  Check the URL and your network connection."
            )

        return f"[MCPClient] Failed to initialize: {exc}"

    def list_tools(self) -> list[dict[str, Any]]:
        """Return tools discovered during ``initialize``."""
        return list(self.tools)

    def disconnect(self) -> None:
        """Send a best-effort DELETE to close the session."""
        if not self.session_id:
            return
        try:
            headers = {
                "Mcp-Session-Id": self.session_id,
                "User-Agent": DEFAULT_USER_AGENT,
            }
            headers.update(self.extra_headers)
            req = request.Request(self.server_url, headers=headers, method="DELETE")
            with request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_http_error(detail: str) -> str:
        """Return a concise HTTP error detail suitable for terminal output."""
        return summarize_http_error(detail)

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
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        # User-supplied headers win, so a custom User-Agent can still be set.
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
                result_obj = json.loads(raw)
                if not isinstance(result_obj, dict):
                    raise MCPClientError("Invalid JSON-RPC response payload")
                result = cast(dict[str, Any], result_obj)
                if "error" in result:
                    raise MCPClientError(f"MCP Error: {result['error']}")
                result_payload = result.get("result", {})
                if isinstance(result_payload, dict):
                    return cast(dict[str, Any], result_payload)
                raise MCPClientError("Invalid JSON-RPC result payload")

        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            short_detail = self._summarize_http_error(detail)
            if short_detail:
                raise MCPClientError(f"HTTP {exc.code} {exc.reason}: {short_detail}") from exc
            raise MCPClientError(f"HTTP {exc.code} {exc.reason}") from exc
        except error.URLError as exc:
            raise MCPClientError(f"Connection error: {exc.reason}") from exc

    @staticmethod
    def _parse_sse(text: str) -> dict[str, Any]:
        """Extract the first JSON-RPC result from an SSE stream."""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data_obj = json.loads(line[6:])
                    if not isinstance(data_obj, dict):
                        continue
                    data = cast(dict[str, Any], data_obj)
                    if "result" in data:
                        result_payload = data["result"]
                        if isinstance(result_payload, dict):
                            return cast(dict[str, Any], result_payload)
                        raise MCPClientError("Invalid JSON-RPC result payload")
                    if "error" in data:
                        raise MCPClientError(f"MCP Error: {data['error']}")
                except json.JSONDecodeError:
                    continue
        raise MCPClientError("No valid JSON-RPC response found in SSE stream")
