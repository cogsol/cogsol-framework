"""Interactive command for editing an existing MCP server configuration.

Workflow
--------
1.  List MCP server classes defined in ``agents/mcp_servers.py``.
2.  User selects a server to edit.
3.  Re-prompt for server details (name, description, URL, auth type,
    credentials) — current values are shown as defaults.
4.  Reconnect to the MCP server and re-discover tools.
5.  User selects which tools to keep.
6.  Remove the old server class (and its tools) from the source files.
7.  Append the updated class definitions.
8.  Update ``.env`` — rename prefix if the server name changed, and
    update/add only the changed credential vars.
9.  PATCH the server in the CogSol API and re-sync its tools.

Notes
-----
If the server name changes, the class name, env-var prefix, import line,
and ``server =`` attribute in tool classes are all updated to match.
"""

from __future__ import annotations

import ast
import json
import os
import re
import time
import webbrowser
from pathlib import Path
from typing import Any

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.constants import get_cognitive_api_base_url
from cogsol.core.loader import collect_classes
from cogsol.core.mcp import MCPClient
from cogsol.management.base import BaseCommand
from cogsol.management.commands.addmcptools import (
    AUTH_TYPES,
    HEADER_KEYS,
    OAUTH_POLL_INTERVAL_SECONDS,
    OAUTH_POLL_SECONDS_DEFAULT,
    _ask,
    _ask_secret,
    _ask_yes_no,
    _oauth_config,
    _py_str,
    _to_env_key,
)

# ---------------------------------------------------------------------------
# File-manipulation helpers
# ---------------------------------------------------------------------------


def _remove_class_from_source(source: str, class_name: str) -> tuple[str, bool]:
    """Remove a top-level class definition using AST line ranges.

    Returns ``(new_source, was_removed)``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            lines = source.splitlines(keepends=True)
            start = node.lineno - 1  # 0-based
            end = node.end_lineno  # 0-based exclusive

            while start > 0 and lines[start - 1].strip() == "":
                start -= 1

            return "".join(lines[:start] + lines[end:]), True

    return source, False


def _read_env_vars(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _, v = stripped.partition("=")
            result[k.strip()] = v.strip()
    return result


def _update_env_file(
    env_path: Path,
    *,
    remove_keys: set[str],
    update: dict[str, str],
    section_comment: str = "",
) -> None:
    """Atomically update a .env file.

    - Removes lines whose key is in *remove_keys*.
    - Updates the value of existing keys found in *update*.
    - Appends any remaining keys from *update* that weren't already in the file.
    """
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    # Pass 1: drop removed keys and orphaned section comment for those keys.
    filtered: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("#") and "MCP Server:" in stripped:
            j = i + 1
            block_keys: list[str] = []
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt or nxt.startswith("#"):
                    break
                if "=" in nxt:
                    block_keys.append(nxt.split("=", 1)[0].strip())
                j += 1
            if block_keys and all(k in remove_keys for k in block_keys):
                i = j
                continue
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in remove_keys:
                i += 1
                continue
        filtered.append(lines[i])
        i += 1

    # Pass 2: update existing values in-place.
    written: set[str] = set()
    out: list[str] = []
    for line in filtered:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in update:
                out.append(f"{key}={update[key]}")
                written.add(key)
                continue
        out.append(line)

    # Pass 3: append new keys.
    additions = {k: v for k, v in update.items() if k not in written}
    if additions:
        out.append("")
        if section_comment:
            out.append(f"# MCP Server: {section_comment}")
        out.extend(f"{k}={v}" for k, v in additions.items())

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# OAuth helpers (re-used from addmcptools flow)
# ---------------------------------------------------------------------------


def _is_authorized(*, client: CogSolClient, server_id: int) -> bool:
    """True when the API can reach the MCP server with the stored OAuth token.

    The API exposes no ``oauth_status`` field; the tools endpoint answers
    511 + ``mcp_oauth_required`` while authorization is still pending.
    """
    try:
        client.list_mcp_server_tools(server_id)
        return True
    except CogSolAPIError as exc:
        if _is_oauth_required_error(exc):
            return False
        raise


def _wait_for_oauth_connected(
    *, client: CogSolClient, server_id: int, timeout_seconds: int
) -> bool:
    start = time.time()
    last_error = ""
    while True:
        try:
            if _is_authorized(client=client, server_id=server_id):
                return True
        except CogSolAPIError as exc:
            # Keep polling, but surface the reason instead of hiding it.
            if str(exc) != last_error:
                last_error = str(exc)
                print(f"  Still waiting; last API response: {exc}")
        if time.time() - start >= timeout_seconds:
            return False
        time.sleep(OAUTH_POLL_INTERVAL_SECONDS)


def _is_oauth_reauth_error(exc: CogSolAPIError) -> bool:
    return "oauth re-authorization required" in str(exc).lower()


def _is_oauth_required_error(exc: CogSolAPIError) -> bool:
    """True when the API says the MCP server needs OAuth before serving tools."""
    text = str(exc).lower()
    return (
        "mcp_oauth_required" in text
        or "network authentication required" in text
        or "oauth re-authorization required" in text
    )


def _start_oauth_authorization(
    *, client: CogSolClient, server_id: int, server_name: str, timeout: int
) -> None:
    auth_payload = client.get_mcp_oauth_authorization_url(server_id) or {}
    url = auth_payload.get("authorization_url")
    if not url:
        raise CogSolAPIError(f"OAuth authorization URL could not be generated for '{server_name}'.")
    if not webbrowser.open(str(url), new=1, autoraise=True):
        print(f"  Open this URL manually: {url}")
    if not _wait_for_oauth_connected(
        client=client, server_id=server_id, timeout_seconds=max(5, timeout)
    ):
        raise CogSolAPIError(
            "OAuth authorization did not complete within timeout. "
            "Re-run editmcptools after finishing OAuth in the browser."
        )


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = "Interactively edit an existing MCP server configuration and its tools."

    def add_arguments(self, parser):
        parser.add_argument("--app", default="agents", help="App folder (default: agents).")
        parser.add_argument(
            "--oauth-timeout",
            default=OAUTH_POLL_SECONDS_DEFAULT,
            type=int,
            help="Seconds to wait for OAuth completion.",
        )

    def _find_remote_server(
        self,
        *,
        client: CogSolClient,
        server_name: str,
        server_url: str,
    ) -> dict[str, Any] | None:
        def norm(s: Any) -> str:
            return re.sub(r"\s+", " ", str(s or "")).strip().casefold()

        try:
            payload = client.list_mcp_servers()
            results = payload if isinstance(payload, list) else (payload or {}).get("results", [])
        except CogSolAPIError:
            return None

        name_n = norm(server_name)
        url_n = norm(str(server_url).rstrip("/"))

        # The name is part of a server's identity: never adopt a remote server
        # just because the URL matches, or editing one server would silently
        # take over another that happens to share the same MCP endpoint.
        by_name = [s for s in results if isinstance(s, dict) and norm(s.get("name")) == name_n]
        if not by_name:
            return None

        by_url = [s for s in by_name if norm(str(s.get("url", "")).rstrip("/")) == url_n]
        candidates = by_url or by_name
        if len(candidates) == 1:
            return candidates[0]

        candidates.sort(
            key=lambda s: str(s.get("updated_at") or s.get("created_at") or ""),
            reverse=True,
        )
        return candidates[0]

    def _discover_tools_via_api(
        self,
        *,
        old_server_name: str,
        old_server_url: str,
        server_name: str,
        server_url: str,
        oauth_timeout: int,
    ) -> list[dict[str, Any]]:
        """Discover tools through the Cognitive API (backend holds OAuth tokens).

        Used when a direct MCP connection is not possible (e.g. Cloudflare
        blocks non-browser clients, or the server requires OAuth).
        """
        api_base = get_cognitive_api_base_url()
        api_key = os.environ.get("COGSOL_API_KEY")
        client = CogSolClient(base_url=api_base, api_key=api_key)

        remote = self._find_remote_server(
            client=client, server_name=old_server_name, server_url=old_server_url
        ) or self._find_remote_server(client=client, server_name=server_name, server_url=server_url)
        if not remote or not remote.get("id"):
            print("  Server not found in Cognitive; cannot discover tools via API.")
            return []
        server_id = int(remote["id"])

        def _list_tools() -> list[dict[str, Any]]:
            payload = client.list_mcp_server_tools(server_id)
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                items = next(
                    (
                        payload[k]
                        for k in ("results", "configured_tools", "tools")
                        if isinstance(payload.get(k), list)
                    ),
                    [],
                )
            else:
                items = []
            return [
                {
                    "name": str(t.get("name")),
                    "description": str(t.get("description") or ""),
                }
                for t in items
                if isinstance(t, dict) and t.get("name")
            ]

        try:
            return _list_tools()
        except CogSolAPIError as exc:
            if not _is_oauth_required_error(exc):
                print(f"  Could not list tools via Cognitive API: {exc}")
                return []
            print("  OAuth authorization required — starting browser flow...")
            try:
                try:
                    client.discover_mcp_oauth(server_id)
                except CogSolAPIError:
                    pass
                _start_oauth_authorization(
                    client=client,
                    server_id=server_id,
                    server_name=old_server_name,
                    timeout=oauth_timeout,
                )
                return _list_tools()
            except CogSolAPIError as exc2:
                print(f"  OAuth-assisted discovery failed: {exc2}")
                return []

    def _publish_update(
        self,
        *,
        server_name: str,
        server_description: str,
        server_url: str,
        auth_type: str,
        headers: dict[str, str],
        oauth_client_id: str,
        oauth_client_secret: str,
        oauth_scopes: str,
        selected_tools: list[dict[str, Any]],
        old_server_name: str,
        old_server_url: str,
        oauth_timeout: int,
    ) -> int:
        """Publish the updated server and its tools, returning its remote id."""
        api_base = get_cognitive_api_base_url()
        api_key = os.environ.get("COGSOL_API_KEY")

        client = CogSolClient(base_url=api_base, api_key=api_key)

        # Look up by old name/url first, then new.
        existing = self._find_remote_server(
            client=client, server_name=old_server_name, server_url=old_server_url
        )
        if existing is None:
            existing = self._find_remote_server(
                client=client, server_name=server_name, server_url=server_url
            )
        remote_id = int(existing["id"]) if existing and existing.get("id") else None

        payload: dict[str, Any] = {
            "name": server_name,
            "description": server_description,
            "url": server_url,
            "protocol_version": "2025-03-26",
            "client_name": "cognitive-mcp-client",
            "client_version": "1.0.0",
            "active": True,
            "auth_type": auth_type,
        }
        if auth_type == "headers":
            if headers:
                payload["headers"] = headers
        else:
            payload["headers"] = {}
        if auth_type == "oauth2":
            payload["oauth_config"] = _oauth_config(oauth_client_id, oauth_scopes)
            if oauth_client_secret:
                payload["oauth_client_secret"] = oauth_client_secret

        server_id = int(client.upsert_mcp_server(remote_id=remote_id, payload=payload))
        action = "Updated" if remote_id else "Created"
        print(f"  {action} MCP server in Cognitive (id={server_id}).")

        if auth_type == "oauth2":
            force_auth = False
            try:
                client.discover_mcp_oauth(server_id)
            except CogSolAPIError as exc:
                if _is_oauth_reauth_error(exc):
                    force_auth = True
                else:
                    raise
            if force_auth or not _is_authorized(client=client, server_id=server_id):
                print("  OAuth not connected yet — starting authorization flow...")
                _start_oauth_authorization(
                    client=client,
                    server_id=server_id,
                    server_name=server_name,
                    timeout=oauth_timeout,
                )

        tool_names = [str(t.get("name")) for t in selected_tools if t.get("name")]
        if not tool_names:
            print("  No MCP tools selected.")
            return server_id

        try:
            client.sync_mcp_server_tools(server_id, tool_names)
        except CogSolAPIError as exc:
            if auth_type != "oauth2" or not _is_oauth_reauth_error(exc):
                raise
            print("  OAuth re-authorization required during tool sync — retrying...")
            _start_oauth_authorization(
                client=client, server_id=server_id, server_name=server_name, timeout=oauth_timeout
            )
            client.sync_mcp_server_tools(server_id, tool_names)
        print(f"  Synced {len(tool_names)} MCP tool(s) in Cognitive.")
        return server_id

    def handle(self, project_path: Path | None, **options: Any) -> int:  # noqa: C901
        assert project_path is not None, "project_path is required"
        app = str(options.get("app") or "agents")
        oauth_timeout = int(options.get("oauth_timeout") or OAUTH_POLL_SECONDS_DEFAULT)

        if not self.ensure_credentials_configured(project_path):
            return 1

        # ── Load local MCP definitions ────────────────────────────────
        try:
            classes = collect_classes(project_path, app)
        except Exception as exc:
            print(f"Could not load MCP definitions: {exc}")
            return 1

        servers: dict[str, Any] = classes.get("mcp_servers", {})
        if not servers:
            print("No MCP server definitions found in this project.")
            return 0

        server_names = sorted(servers.keys())
        print("\nAvailable MCP servers:\n")
        for i, name in enumerate(server_names, 1):
            cls = servers[name]
            url = getattr(cls, "url", "") or ""
            auth = getattr(cls, "auth_type", "headers")
            print(f"  {i}. {name}  ({url})  [{auth}]")
        print()

        choice = _ask("Select server to edit (number, or 0 to cancel)", "0")
        if choice == "0" or not choice:
            print("Cancelled.")
            return 0
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(server_names):
                raise ValueError
        except ValueError:
            print("Invalid selection.")
            return 1

        old_server_key = server_names[idx]
        server_cls = servers[old_server_key]

        old_server_name: str = getattr(server_cls, "name", None) or old_server_key
        old_cls_name: str = server_cls.__name__
        old_url: str = getattr(server_cls, "url", "") or ""
        old_auth: str = getattr(server_cls, "auth_type", "headers") or "headers"

        # Read current credential values from .env
        env_path = project_path / ".env"
        env_vars = _read_env_vars(env_path)
        old_env_prefix = _to_env_key(old_server_name) + "_"

        # Reconstruct current headers from .env
        current_headers: dict[str, str] = {}
        for hk in HEADER_KEYS:
            env_key = _to_env_key(f"{old_server_name}_{hk}")
            if env_key in env_vars:
                current_headers[hk] = env_vars[env_key]

        current_oauth_client_id = env_vars.get(
            _to_env_key(f"{old_server_name}_OAUTH_CLIENT_ID"), ""
        )
        current_oauth_scopes = env_vars.get(_to_env_key(f"{old_server_name}_OAUTH_SCOPES"), "")

        # ── Step 1: Server details ────────────────────────────────────
        print(f"\n=== Step 1: Edit Server Configuration (current name: {old_server_name}) ===\n")

        server_name = _ask("Server name", old_server_name)
        if not server_name:
            print("A server name is required.")
            return 1
        server_description = _ask("Description", getattr(server_cls, "description", "") or "")
        server_url = _ask("Server URL", old_url)
        if not server_url:
            print("A server URL is required.")
            return 1

        print("\nAuthentication type:")
        for i, auth_option in enumerate(AUTH_TYPES, 1):
            marker = "  ← current" if auth_option == old_auth else ""
            print(f"  {i}. {auth_option}{marker}")
        try:
            old_auth_idx = AUTH_TYPES.index(old_auth) + 1
        except ValueError:
            old_auth_idx = 2
        auth_choice = _ask("Select auth type", str(old_auth_idx))
        try:
            auth_idx = int(auth_choice) - 1
            if auth_idx < 0 or auth_idx >= len(AUTH_TYPES):
                raise ValueError
        except ValueError:
            auth_idx = old_auth_idx - 1
        auth_type = AUTH_TYPES[auth_idx]
        print(f"  → auth_type: {auth_type}\n")

        headers: dict[str, str] = {}
        oauth_client_id = ""
        oauth_client_secret = ""
        oauth_scopes = ""

        if auth_type == "headers":
            if current_headers:
                print("Current headers:")
                for k, v in current_headers.items():
                    masked = v[:4] + "***" if len(v) > 4 else "***"
                    print(f"  {k}: {masked}")
                print()

            print("Available header keys:")
            for i, key in enumerate(HEADER_KEYS, 1):
                current_marker = (
                    f"  ← {current_headers[key][:4]}***" if key in current_headers else ""
                )
                print(f"  {i}. {key}{current_marker}")
            print("  0. Done adding headers")
            print()

            # Pre-fill current headers (user can replace or skip to keep them)
            if current_headers and _ask_yes_no("Keep existing header values?", default=True):
                headers = dict(current_headers)
            else:
                while True:
                    hdr_choice = _ask("Select header key number (0 to finish)", "0")
                    if hdr_choice == "0":
                        break
                    try:
                        h_idx = int(hdr_choice) - 1
                        if h_idx < 0 or h_idx >= len(HEADER_KEYS):
                            raise ValueError
                    except ValueError:
                        print("Invalid selection, try again.")
                        continue
                    hk = HEADER_KEYS[h_idx]
                    hv = _ask(f"  Value for '{hk}'", current_headers.get(hk, ""))
                    if hv:
                        headers[hk] = hv

        elif auth_type == "oauth2":
            print("OAuth 2.1 Configuration")
            print("(Leave blank to keep current value)\n")
            oauth_client_id = _ask("Client ID", current_oauth_client_id)
            oauth_client_secret_raw = _ask_secret(
                "Client Secret (leave blank to keep / skip)"
                "\n  It is sent securely to the CogSol API (Azure Key Vault)."
            )
            oauth_client_secret = oauth_client_secret_raw
            oauth_scopes = _ask("Scopes", current_oauth_scopes)

        # ── Step 2: Tool discovery ────────────────────────────────────
        print("\n=== Step 2: Discovering Tools ===\n")
        print(f"Connecting to {server_url} ...")

        discovery_headers = headers if auth_type == "headers" else {}
        mcp_client = MCPClient(server_url, headers=discovery_headers, auth_type=auth_type)
        connected = mcp_client.initialize()
        tools = mcp_client.list_tools() if connected else []
        mcp_client.disconnect()

        if not tools and auth_type == "oauth2":
            print("Direct connection failed — discovering tools via the Cognitive API...")
            tools = self._discover_tools_via_api(
                old_server_name=old_server_name,
                old_server_url=old_url,
                server_name=server_name,
                server_url=server_url,
                oauth_timeout=oauth_timeout,
            )

        keep_existing_tools = False
        if not tools:
            print("\nNo tools could be discovered (connection failed or none returned).")
            if _ask_yes_no("Keep the existing tool definitions for this server?", default=True):
                keep_existing_tools = True
                print("  Existing tool classes will be kept (references updated if renamed).\n")
            else:
                print("  Existing tool classes will be REMOVED.\n")

        selected_tools: list[dict[str, Any]] = []

        if tools:
            # Load current tools for this server to pre-mark as selected
            all_tools: dict[str, Any] = classes.get("mcp_tools", {})
            current_tool_names = {
                getattr(tc, "name", tn)
                for tn, tc in all_tools.items()
                if (
                    getattr(tc, "server", None) is server_cls
                    or getattr(getattr(tc, "server", None), "__name__", None) == server_cls.__name__
                )
            }

            print(f"\nFound {len(tools)} tool(s):\n")
            for i, tool in enumerate(tools, 1):
                current_mark = " [current]" if tool["name"] in current_tool_names else ""
                desc = tool.get("description", "")
                print(f"  {i}. {tool['name']}{current_mark}")
                if desc:
                    print(f"     {desc[:100]}")
            print()

            print("Enter tool numbers to keep (e.g. '1,3,5'), 'all' for all, or '0' to cancel:")
            selection = _ask("Selection", "all")
            if selection == "0":
                print("Cancelled.")
                return 0
            if selection.lower() == "all":
                selected_tools = tools
            else:
                idxs: list[int] = []
                for part in selection.split(","):
                    part = part.strip()
                    if part.isdigit():
                        ti = int(part) - 1
                        if 0 <= ti < len(tools):
                            idxs.append(ti)
                selected_tools = [tools[i] for i in idxs]

        # ── Step 3: Update source files ───────────────────────────────
        print("=== Step 3: Updating Files ===\n")

        # Derive new class name from (possibly new) server name.
        cls_base = re.sub(r"[^a-zA-Z0-9]+", " ", server_name).title().replace(" ", "")
        new_cls_name = f"{cls_base}MCPServer"

        # Build env vars for new credentials.
        env_new_vars: dict[str, str] = {}

        if auth_type == "none":
            server_body_lines = [
                f"    name = {_py_str(server_name)}",
                f"    description = {_py_str(server_description)}",
                '    auth_type = "none"',
                f"    url = {_py_str(server_url)}",
            ]
        elif auth_type == "headers":
            header_attr_lines: list[str] = []
            for hk, hv in headers.items():
                env_key = _to_env_key(f"{server_name}_{hk}")
                env_new_vars[env_key] = hv
                header_attr_lines.append(
                    f"        {_py_str(hk)}: os.environ.get({_py_str(env_key)}, ''),"
                )
            headers_block = (
                "{\n" + "\n".join(header_attr_lines) + "\n    }" if header_attr_lines else "{}"
            )
            server_body_lines = [
                f"    name = {_py_str(server_name)}",
                f"    description = {_py_str(server_description)}",
                f"    url = {_py_str(server_url)}",
                f"    headers = {headers_block}",
            ]
        else:  # oauth2
            oauth_cid_env = _to_env_key(f"{server_name}_OAUTH_CLIENT_ID")
            oauth_scopes_env = _to_env_key(f"{server_name}_OAUTH_SCOPES")
            if oauth_client_id:
                env_new_vars[oauth_cid_env] = oauth_client_id
            if oauth_scopes:
                env_new_vars[oauth_scopes_env] = oauth_scopes
            server_body_lines = [
                f"    name = {_py_str(server_name)}",
                f"    description = {_py_str(server_description)}",
                '    auth_type = "oauth2"',
                f"    url = {_py_str(server_url)}",
            ]
            if oauth_client_id:
                server_body_lines.append(
                    f"    oauth_client_id = os.environ.get({_py_str(oauth_cid_env)}, '')"
                )
            if oauth_scopes:
                server_body_lines.append(
                    f"    oauth_scopes = os.environ.get({_py_str(oauth_scopes_env)}, '')"
                )

        header_imports = (["import os", ""] if auth_type != "none" else []) + [
            "from cogsol.tools import BaseMCPServer",
            "",
            "",
        ]
        server_code = "\n".join(
            header_imports
            + [
                f"class {new_cls_name}(BaseMCPServer):",
                '    """MCP server definition."""',
                "",
                "\n".join(server_body_lines),
                "",
            ]
        )

        # Build tool classes.
        tool_classes: list[str] = []
        for tool in selected_tools:
            t_name = tool["name"]
            t_desc = tool.get("description", "") or ""
            t_cls_base = re.sub(r"[^a-zA-Z0-9]+", " ", t_name).title().replace(" ", "")
            t_cls_name = f"{t_cls_base}MCPTool"
            tool_classes.append(
                "\n".join(
                    [
                        "",
                        "",
                        f"class {t_cls_name}(BaseMCPTool):",
                        '    """MCP tool definition."""',
                        "",
                        f"    name = {_py_str(t_name)}",
                        f"    description = {_py_str(t_desc)}",
                        f"    server = {new_cls_name}",
                        "",
                    ]
                )
            )

        tools_header = "\n".join(
            [
                "from cogsol.tools import BaseMCPTool",
                "",
                f"from {app}.mcp_servers import {new_cls_name}",
            ]
        )
        tools_code = tools_header + "".join(tool_classes)

        app_path = project_path / app
        servers_file = app_path / "mcp_servers.py"
        tools_file = app_path / "mcp_tools.py"

        # -- Remove old server class --
        if servers_file.exists():
            source = servers_file.read_text(encoding="utf-8")
            new_source, removed = _remove_class_from_source(source, old_cls_name)
            if removed:
                # Append new class (strip duplicate imports — they likely already exist)
                existing = new_source.rstrip()
                class_only = (
                    "\n\n"
                    + "\n".join(
                        ln
                        for ln in server_code.splitlines()
                        if not ln.startswith("import ") and not ln.startswith("from ")
                    ).strip()
                    + "\n"
                )
                servers_file.write_text(existing + class_only, encoding="utf-8")
                print(f"  Updated {old_cls_name} → {new_cls_name} in mcp_servers.py")
            else:
                # Class not found — append as new.
                servers_file.write_text(
                    servers_file.read_text(encoding="utf-8").rstrip()
                    + "\n\n"
                    + "\n".join(
                        ln
                        for ln in server_code.splitlines()
                        if not ln.startswith("import ") and not ln.startswith("from ")
                    ).strip()
                    + "\n",
                    encoding="utf-8",
                )
                print(f"  Appended {new_cls_name} to mcp_servers.py (old class not found)")
        else:
            servers_file.write_text(server_code, encoding="utf-8")
            print(f"  Created mcp_servers.py with {new_cls_name}")

        # -- Remove old tool classes that referenced the old server --
        old_import_line = f"from {app}.mcp_servers import {old_cls_name}"
        new_import_line = f"from {app}.mcp_servers import {new_cls_name}"

        if tools_file.exists():
            source = tools_file.read_text(encoding="utf-8")
            if not keep_existing_tools:
                # Remove tool classes belonging to the old server.
                all_tools_classes: dict[str, Any] = classes.get("mcp_tools", {})
                for tc in all_tools_classes.values():
                    if (
                        getattr(tc, "server", None) is server_cls
                        or getattr(getattr(tc, "server", None), "__name__", None) == old_cls_name
                    ):
                        source, _ = _remove_class_from_source(source, tc.__name__)

            # Update import line and server references in kept tool classes.
            source = source.replace(old_import_line, new_import_line)
            source = source.replace(f"server = {old_cls_name}", f"server = {new_cls_name}")

            # Ensure new import line exists.
            if new_import_line not in source:
                source = source.rstrip() + f"\n{new_import_line}\n"

            # Append new tool classes.
            for cls_block in tool_classes:
                cls_name_match = re.search(r"class (\w+)\(", cls_block)
                if cls_name_match and cls_name_match.group(1) not in source:
                    source = source.rstrip() + cls_block

            tools_file.write_text(source, encoding="utf-8")
            print("  Updated mcp_tools.py")
        elif tool_classes:
            tools_file.write_text(tools_code, encoding="utf-8")
            print("  Created mcp_tools.py")

        # -- Update .env --
        # If the server name changed, remove all old prefix vars and write new ones.
        name_changed = old_server_name.strip().casefold() != server_name.strip().casefold()
        old_env_keys_for_server: set[str] = set()
        if name_changed:
            for k in env_vars:
                if k.startswith(old_env_prefix):
                    old_env_keys_for_server.add(k)

        _update_env_file(
            env_path,
            remove_keys=old_env_keys_for_server,
            update=env_new_vars,
            section_comment=server_name if env_new_vars else "",
        )
        if env_new_vars or old_env_keys_for_server:
            changes = len(env_new_vars) + len(old_env_keys_for_server)
            print(f"  Updated .env ({changes} change(s)).")
        else:
            print("  .env already up-to-date.")

        # -- Publish to Cognitive --
        print("\nPublishing updated MCP server/tools to Cognitive...")
        try:
            server_id = self._publish_update(
                server_name=server_name,
                server_description=server_description,
                server_url=server_url,
                auth_type=auth_type,
                headers=headers,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_scopes=oauth_scopes,
                selected_tools=selected_tools,
                old_server_name=old_server_name,
                old_server_url=old_url,
                oauth_timeout=oauth_timeout,
            )
        except CogSolAPIError as exc:
            print(f"Failed to publish to Cognitive: {exc}")
            return 1

        # -- Update .state.json --
        state_path = project_path / app / "migrations" / ".state.json"
        if state_path.exists():
            try:
                state: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}

            local_state = state.get("state", {})
            # Move state entry if name changed.
            if name_changed:
                mcp_srv_state = local_state.get("mcp_servers", {})
                entry = mcp_srv_state.pop(old_server_key, None)
                if entry:
                    mcp_srv_state[server_name] = entry

            # Keep the remote id under the current name, so migrate can still
            # delete the server after a rename.
            remote_servers = state.setdefault("remote", {}).setdefault("mcp_servers", {})
            if name_changed:
                remote_servers.pop(old_server_key, None)
            remote_servers[server_name] = server_id

            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print("  Updated .state.json")

        print(
            "\nDone! Run 'python manage.py makemigrations' followed by "
            "'python manage.py migrate'."
        )
        return 0
