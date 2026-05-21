"""Interactive command for adding MCP server + tool definitions.

Mirrors the frontend flow:
    Step 1  – prompt for server details (name, description, URL, auth type)
              • auth_type="none"    – no credentials needed
              • auth_type="headers" – static headers (e.g. API keys)
              • auth_type="oauth2"  – OAuth 2.1 / PKCE flow
    Step 2  – connect to the MCP server, list tools, let user select
              (OAuth servers are contacted without auth; full authorization
               is completed from the CogSol portal after ``migrate``)
    Step 3  – generate ``agents/mcp_servers.py`` and ``agents/mcp_tools.py``
              and update ``.env`` with any sensitive values.

OAuth 2.1 note
--------------
``client_id`` and ``client_secret`` are **both optional** — the cognitive
backend supports Dynamic Client Registration (RFC 7591) and will obtain them
automatically if omitted.

The ``client_secret`` is NEVER written to ``.env`` or to source files.  It is
sent write-only to the CogSol API, which stores it in Azure Key Vault.
"""

from __future__ import annotations

import os
import re
import time
import webbrowser
from getpass import getpass
from pathlib import Path
from typing import Any

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.mcp import MCPClient
from cogsol.management.base import BaseCommand

# Header keys offered by the frontend's McpToolGeneral component.
HEADER_KEYS = [
    "Authorization",
    "x-api-key",
    "Content-Type",
    "Accept",
    "User-Agent",
    "x-custom-header",
    "x-auth-token",
    "x-client-id",
]

AUTH_TYPES = ["none", "headers", "oauth2"]
OAUTH_POLL_SECONDS_DEFAULT = 300
OAUTH_POLL_INTERVAL_SECONDS = 2


def _ask(prompt: str, default: str = "") -> str:
    """Simple input wrapper with an optional default shown in brackets."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _ask_secret(prompt: str) -> str:
    """Ask for a secret value using masked terminal input when possible."""
    try:
        value = getpass(f"{prompt} (leave blank to skip): ").strip()
    except Exception:
        value = input(f"{prompt} (leave blank to skip): ").strip()
    return value


def _ask_yes_no(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer.startswith("y")


def _to_env_key(name: str) -> str:
    """Derive an env-var name from a server/header name."""
    key = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").upper()
    return f"MCP_{key}"


def _py_str(value: str) -> str:
    """Return a safe Python string literal for generated source."""
    return repr(value)


def _oauth_config(client_id: str, scopes: str) -> dict[str, Any]:
    """Build oauth_config payload for the API, omitting empty values."""
    cfg: dict[str, Any] = {}
    if client_id:
        cfg["client_id"] = client_id
    if scopes:
        cfg["scopes"] = scopes
    return cfg


class Command(BaseCommand):
    help = "Interactively configure an MCP server and select tools."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            default="agents",
            help="App folder (default: agents).",
        )
        parser.add_argument(
            "--oauth-timeout",
            default=OAUTH_POLL_SECONDS_DEFAULT,
            type=int,
            help="Seconds to wait for OAuth completion when browser flow is triggered.",
        )

    def _extract_results(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            if isinstance(payload.get("results"), list):
                return [item for item in payload["results"] if isinstance(item, dict)]
            if isinstance(payload.get("tools"), list):
                return [item for item in payload["tools"] if isinstance(item, dict)]
        return []

    def _norm(self, value: Any) -> str:
        text = str(value or "")
        return re.sub(r"\s+", " ", text).strip().casefold()

    def _find_remote_server(
        self,
        *,
        client: CogSolClient,
        server_name: str,
        server_url: str,
    ) -> dict[str, Any] | None:
        servers = self._extract_results(client.list_mcp_servers())
        server_name_n = self._norm(server_name)
        server_url_n = self._norm(str(server_url).rstrip("/"))

        exact = [
            s
            for s in servers
            if self._norm(s.get("name")) == server_name_n
            and self._norm(str(s.get("url", "")).rstrip("/")) == server_url_n
        ]
        if exact:
            return exact[0]

        name_match = [s for s in servers if self._norm(s.get("name")) == server_name_n]
        if len(name_match) == 1:
            return name_match[0]

        url_match = [
            s for s in servers if self._norm(str(s.get("url", "")).rstrip("/")) == server_url_n
        ]
        if len(url_match) == 1:
            return url_match[0]

        # If duplicates exist for the same URL, prefer oauth2 and most recently updated.
        if len(url_match) > 1:
            oauth_candidates = [s for s in url_match if self._norm(s.get("auth_type")) == "oauth2"]
            candidates = oauth_candidates or url_match
            candidates.sort(
                key=lambda s: str(s.get("updated_at") or s.get("created_at") or ""),
                reverse=True,
            )
            return candidates[0]

        if len(name_match) > 1:
            name_match.sort(
                key=lambda s: str(s.get("updated_at") or s.get("created_at") or ""),
                reverse=True,
            )
            return name_match[0]

        return None

    def _wait_for_oauth_connected(
        self,
        *,
        client: CogSolClient,
        server_id: int,
        timeout_seconds: int,
    ) -> bool:
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                data = client.get_mcp_server(server_id) or {}
                status = str(data.get("oauth_status", "")).lower()
                if status == "connected":
                    return True
            except CogSolAPIError:
                # Keep polling; callback might still be processing.
                pass
            time.sleep(OAUTH_POLL_INTERVAL_SECONDS)
        return False

    def _is_oauth_reauthorization_error(self, exc: CogSolAPIError) -> bool:
        return "oauth re-authorization required" in str(exc).lower()

    def _start_oauth_authorization(
        self,
        *,
        client: CogSolClient,
        server_id: int,
        server_name: str,
        oauth_timeout: int,
    ) -> None:
        auth_payload = client.get_mcp_oauth_authorization_url(server_id) or {}
        authorization_url = auth_payload.get("authorization_url")
        if not authorization_url:
            raise CogSolAPIError(
                "OAuth authorization URL could not be generated for " f"MCP server '{server_name}'."
            )

        opened = webbrowser.open(str(authorization_url), new=1, autoraise=True)
        if not opened:
            print("  Could not auto-open browser. Open this URL manually:")
            print(f"  {authorization_url}")

        connected = self._wait_for_oauth_connected(
            client=client,
            server_id=server_id,
            timeout_seconds=max(5, int(oauth_timeout)),
        )
        if not connected:
            raise CogSolAPIError(
                "OAuth authorization did not complete within timeout. "
                "Please finish OAuth in browser and retry addmcptools."
            )

    def _oauth_assisted_discovery(
        self,
        *,
        server_name: str,
        server_description: str,
        server_url: str,
        oauth_client_id: str,
        oauth_client_secret: str,
        oauth_scopes: str,
        oauth_timeout: int,
    ) -> list[dict[str, Any]]:
        api_base = os.environ.get("COGSOL_API_BASE")
        api_key = os.environ.get("COGSOL_API_KEY")
        if not api_base:
            print("COGSOL_API_BASE is required to run assisted OAuth tool discovery.")
            return []

        api_client = CogSolClient(base_url=api_base, api_key=api_key)
        remote = self._find_remote_server(
            client=api_client,
            server_name=server_name,
            server_url=server_url,
        )
        if not remote or "id" not in remote:
            payload: dict[str, Any] = {
                "name": server_name,
                "description": server_description,
                "url": server_url,
                "headers": {},
                "protocol_version": "2025-03-26",
                "client_name": "cognitive-mcp-client",
                "client_version": "1.0.0",
                "active": True,
                "auth_type": "oauth2",
                "oauth_config": _oauth_config(oauth_client_id, oauth_scopes),
            }
            if oauth_client_secret:
                payload["oauth_client_secret"] = oauth_client_secret
            try:
                print("MCP server not found in API. Creating it now for OAuth discovery...")
                server_id = int(api_client.upsert_mcp_server(remote_id=None, payload=payload))
            except CogSolAPIError as exc:
                print(
                    "Could not create MCP server in CogSol API during OAuth onboarding.\n"
                    f"Details: {exc}"
                )
                return []
        else:
            server_id = int(remote["id"])

        try:
            print("Discovering OAuth metadata from CogSol API...")
            api_client.discover_mcp_oauth(server_id)
            auth_payload = api_client.get_mcp_oauth_authorization_url(server_id) or {}
            authorization_url = auth_payload.get("authorization_url")
            if not authorization_url:
                print("Could not obtain OAuth authorization URL from the API.")
                return []

            print("Opening browser for OAuth authorization...")
            opened = webbrowser.open(str(authorization_url), new=1, autoraise=True)
            if not opened:
                print("Could not auto-open browser. Open this URL manually:")
                print(str(authorization_url))

            print(f"Waiting for OAuth completion (timeout: {oauth_timeout}s)...")
            connected = self._wait_for_oauth_connected(
                client=api_client,
                server_id=server_id,
                timeout_seconds=max(5, int(oauth_timeout)),
            )
            if not connected:
                print("OAuth authorization timeout. You can retry addmcptools after authorizing.")
                return []

            tools_payload = api_client.list_mcp_server_tools(server_id)
            tools = self._extract_results(tools_payload)
            if not tools:
                print("OAuth connected, but no tools were returned by the MCP server.")
                return []

            normalized: list[dict[str, Any]] = []
            for tool in tools:
                if not tool.get("name"):
                    continue
                normalized.append(
                    {
                        "name": str(tool.get("name")),
                        "description": str(tool.get("description") or ""),
                        "input_schema": tool.get("input_schema") or tool.get("inputSchema") or {},
                    }
                )
            return normalized
        except CogSolAPIError as exc:
            print(f"OAuth discovery via CogSol API failed: {exc}")
            return []

    def _publish_to_cognitive(
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
        oauth_timeout: int,
    ) -> None:
        api_base = os.environ.get("COGSOL_API_BASE")
        api_key = os.environ.get("COGSOL_API_KEY")
        if not api_base:
            raise CogSolAPIError(
                "COGSOL_API_BASE is required. addmcptools now publishes MCP servers/tools "
                "directly to Cognitive."
            )

        client = CogSolClient(base_url=api_base, api_key=api_key)
        existing = self._find_remote_server(
            client=client,
            server_name=server_name,
            server_url=server_url,
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
        if auth_type != "headers" or headers:
            # For non-headers auth types always send headers: {}.
            # For headers auth, only include the key when the user provided values so that
            # a re-run without new input leaves existing Key Vault secrets untouched.
            payload["headers"] = headers if auth_type == "headers" else {}
        if auth_type == "oauth2":
            payload["oauth_config"] = _oauth_config(oauth_client_id, oauth_scopes)
            if oauth_client_secret:
                payload["oauth_client_secret"] = oauth_client_secret

        server_id = int(client.upsert_mcp_server(remote_id=remote_id, payload=payload))
        action = "Updated" if remote_id else "Created"
        print(f"  {action} MCP server in Cognitive (id={server_id}).")

        if auth_type == "oauth2":
            print(f"  Refreshing OAuth metadata for server id={server_id}...")
            force_authorization = False
            try:
                client.discover_mcp_oauth(server_id)
            except CogSolAPIError as exc:
                if self._is_oauth_reauthorization_error(exc):
                    print(
                        "  OAuth re-authorization required while refreshing metadata; "
                        "continuing with authorization flow..."
                    )
                    force_authorization = True
                else:
                    raise

            server_data = client.get_mcp_server(server_id) or {}
            status = str(server_data.get("oauth_status", "")).lower()
            if force_authorization or status != "connected":
                print("  OAuth server is not connected yet. Starting authorization flow...")
                self._start_oauth_authorization(
                    client=client,
                    server_id=server_id,
                    server_name=server_name,
                    oauth_timeout=oauth_timeout,
                )

        tool_names = [str(t.get("name")) for t in selected_tools if t.get("name")]
        if not tool_names:
            print("  No MCP tools selected to sync in Cognitive.")
            return

        try:
            client.sync_mcp_server_tools(server_id, tool_names)
        except CogSolAPIError as exc:
            if auth_type != "oauth2" or not self._is_oauth_reauthorization_error(exc):
                raise

            print(
                "  OAuth re-authorization required during tools sync. "
                "Starting recovery flow and retrying once..."
            )
            self._start_oauth_authorization(
                client=client,
                server_id=server_id,
                server_name=server_name,
                oauth_timeout=oauth_timeout,
            )
            client.sync_mcp_server_tools(server_id, tool_names)
        print(f"  Synced {len(tool_names)} MCP tool(s) in Cognitive.")

    def handle(self, project_path: Path | None, **options: Any) -> int:  # noqa: C901
        assert project_path is not None, "project_path is required"
        app = str(options.get("app") or "agents")
        oauth_timeout = int(options.get("oauth_timeout") or OAUTH_POLL_SECONDS_DEFAULT)

        if not self.ensure_credentials_configured(project_path):
            return 1

        # ── Step 1: Server details ───────────────────────────────────
        print("\n=== Step 1: MCP Server Configuration ===\n")
        server_name = _ask("Server name")
        if not server_name:
            print("A server name is required.")
            return 1
        server_description = _ask("Description", "")
        server_url = _ask("Server URL (e.g. https://mcp.example.com/mcp)")
        if not server_url:
            print("A server URL is required.")
            return 1

        # Auth type
        print("\nAuthentication type:")
        for i, auth_option in enumerate(AUTH_TYPES, 1):
            suffix = "  ← default" if auth_option == "headers" else ""
            print(f"  {i}. {auth_option}{suffix}")
        auth_choice = _ask("Select auth type", "2")
        try:
            auth_idx = int(auth_choice) - 1
            if auth_idx < 0 or auth_idx >= len(AUTH_TYPES):
                raise ValueError
        except ValueError:
            print("Invalid selection, defaulting to 'headers'.")
            auth_idx = 1
        auth_type = AUTH_TYPES[auth_idx]
        print(f"  → auth_type: {auth_type}\n")

        # Credentials depending on auth type
        headers: dict[str, str] = {}
        oauth_client_id = ""
        oauth_client_secret = ""
        oauth_scopes = ""

        if auth_type == "headers":
            print("Available header keys:")
            for i, key in enumerate(HEADER_KEYS, 1):
                print(f"  {i}. {key}")
            print("  0. Skip / done adding headers")
            print()

            while True:
                choice = _ask("Select header key number (0 to finish)", "0")
                if choice == "0":
                    break
                try:
                    idx = int(choice) - 1
                    if idx < 0 or idx >= len(HEADER_KEYS):
                        raise ValueError
                except ValueError:
                    print("Invalid selection, try again.")
                    continue
                hdr_key = HEADER_KEYS[idx]
                hdr_value = _ask(f"  Value for '{hdr_key}'")
                if hdr_value:
                    headers[hdr_key] = hdr_value

        if auth_type == "headers" and headers:
            print(
                "\n  ℹ  Header values are sent securely to the CogSol API"
                " and stored in Azure Key Vault."
            )

        elif auth_type == "oauth2":
            print("OAuth 2.1 Configuration")
            print("(All fields are optional — the server supports Dynamic Client Registration)\n")
            oauth_client_id = _ask("Client ID     (leave blank for auto-registration)", "")
            oauth_client_secret = _ask_secret(
                "Client Secret (leave blank for auto-registration)"
                "\n  ⚠  This value will NOT be saved to .env or source files."
                "\n  It is sent securely to the CogSol API (Azure Key Vault)."
            )
            oauth_scopes = _ask(
                "Scopes        (space-separated, e.g. 'read:jira write:confluence')", ""
            )

        # ── Step 2: Connect & list tools ─────────────────────────────
        print("\n=== Step 2: Discovering Tools ===\n")
        print(f"Connecting to {server_url} ...")

        # For OAuth servers, attempt discovery without auth (many servers allow
        # tools/list unauthenticated; actual execution requires the portal auth flow)
        discovery_headers = headers if auth_type == "headers" else {}
        client = MCPClient(server_url, headers=discovery_headers, auth_type=auth_type)
        connected = client.initialize()

        tools = client.list_tools() if connected else []
        client.disconnect()

        if auth_type == "oauth2" and not tools:
            tools = self._oauth_assisted_discovery(
                server_name=server_name,
                server_description=server_description,
                server_url=server_url,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_scopes=oauth_scopes,
                oauth_timeout=oauth_timeout,
            )

        if not connected and auth_type != "oauth2":
            print("Failed to connect to the MCP server. Check URL and headers.")
            return 1

        selected_tools: list[dict[str, Any]] = []

        if tools:
            print(f"\nFound {len(tools)} tool(s):\n")
            for i, tool in enumerate(tools, 1):
                desc = tool.get("description", "")
                print(f"  {i}. {tool['name']}")
                if desc:
                    print(f"     {desc[:100]}")
            print()

            print("Enter tool numbers to add (e.g. '1,3,5'), 'all' for all, or '0' to cancel:")
            selection = _ask("Selection", "all")
            if selection == "0":
                print("Cancelled.")
                return 0

            if selection.lower() == "all":
                selected_tools = tools
            else:
                selected_indices: list[int] = []
                for part in selection.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(tools):
                            selected_indices.append(idx)
                selected_tools = [tools[i] for i in selected_indices]

            if not selected_tools:
                print("No tools selected.")
                return 1

            print(f"\nSelected {len(selected_tools)} tool(s).\n")
        else:
            if auth_type == "oauth2":
                print(
                    "Could not list tools yet (OAuth still required or unavailable).\n"
                    "The server definition will be created without tool entries.\n"
                    "Complete OAuth authorization and re-run `addmcptools`, or add tools manually.\n"
                )
            else:
                print("The server reported no tools.")

        # ── Step 3: Generate files ───────────────────────────────────
        print("=== Step 3: Generating Files ===\n")

        # Python-safe class name from the server name
        cls_base = re.sub(r"[^a-zA-Z0-9]+", " ", server_name).title().replace(" ", "")
        server_cls_name = f"{cls_base}MCPServer"

        # ── Build mcp_servers.py snippet ─────────────────────────────
        # URL is hardcoded in the class — it lives in the CogSol API after migrate.
        env_new_vars: dict[str, str] = {}

        if auth_type == "none":
            server_body_lines = [
                f"    name = {_py_str(server_name)}",
                f"    description = {_py_str(server_description)}",
                '    auth_type = "none"',
                f"    url = {_py_str(server_url)}",
            ]

        elif auth_type == "headers":
            header_env_entries: dict[str, str] = {}
            header_attr_lines: list[str] = []
            for hk, hv in headers.items():
                env_key = _to_env_key(f"{server_name}_{hk}")
                header_env_entries[env_key] = hv
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

        server_body = "\n".join(server_body_lines)
        # Build server_code line-by-line to avoid f-string + textwrap.dedent
        # indentation issues when server_body spans multiple lines.
        # Only emit `import os` when auth type uses os.environ (headers/oauth2).
        header_lines = (["import os", ""] if auth_type != "none" else []) + [
            "from cogsol.tools import BaseMCPServer",
            "",
            "",
        ]
        server_code = "\n".join(
            header_lines
            + [
                f"class {server_cls_name}(BaseMCPServer):",
                '    """MCP server definition."""',
                "",
                server_body,
                "",
            ]
        )

        # ── Build mcp_tools.py snippet ───────────────────────────────
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
                        f"    server = {server_cls_name}",
                        "",
                    ]
                )
            )

        tools_code = "\n".join(
            [
                "from cogsol.tools import BaseMCPTool",
                "",
                f"from {app}.mcp_servers import {server_cls_name}",
            ]
        ) + "".join(tool_classes)

        # ── Write files ───────────────────────────────────────────────
        app_path = project_path / app
        app_path.mkdir(parents=True, exist_ok=True)

        servers_file = app_path / "mcp_servers.py"
        tools_file = app_path / "mcp_tools.py"

        if servers_file.exists():
            existing = servers_file.read_text(encoding="utf-8")
            if server_cls_name in existing:
                print(
                    f"  Server class '{server_cls_name}' already exists in "
                    f"{servers_file.name}; skipping."
                )
            else:
                class_only = (
                    "\n\n"
                    + "\n".join(
                        line
                        for line in server_code.splitlines()
                        if not line.startswith("import ") and not line.startswith("from ")
                    ).strip()
                    + "\n"
                )
                servers_file.write_text(existing.rstrip() + class_only, encoding="utf-8")
                print(f"  Appended {server_cls_name} to {servers_file.name}")
        else:
            servers_file.write_text(server_code, encoding="utf-8")
            print(f"  Created {servers_file.name}")

        if tool_classes:
            if tools_file.exists():
                existing = tools_file.read_text(encoding="utf-8")
                import_line = f"from {app}.mcp_servers import {server_cls_name}"
                if import_line not in existing:
                    existing = existing.rstrip() + f"\n{import_line}\n"
                for cls_block in tool_classes:
                    cls_name_match = re.search(r"class (\w+)\(", cls_block)
                    if cls_name_match and cls_name_match.group(1) not in existing:
                        existing += cls_block
                tools_file.write_text(existing, encoding="utf-8")
                print(f"  Updated {tools_file.name}")
            else:
                tools_file.write_text(tools_code, encoding="utf-8")
                print(f"  Created {tools_file.name}")
        else:
            if not tools_file.exists():
                # Create a placeholder so the module is importable
                placeholder = "\n".join(
                    [
                        "from cogsol.tools import BaseMCPTool",
                        "",
                        f"from {app}.mcp_servers import {server_cls_name}",
                        "# No tools selected yet.",
                        "# Re-run `python manage.py addmcptools` after completing OAuth",
                        "# authorization in the CogSol portal to select tools.",
                        "",
                    ]
                )
                tools_file.write_text(placeholder, encoding="utf-8")
                print(f"  Created {tools_file.name} (placeholder — tools to be added later)")

        # ── Update .env ───────────────────────────────────────────────
        env_path = project_path / ".env"
        env_lines: list[str] = []
        if env_path.exists():
            env_lines = env_path.read_text(encoding="utf-8").splitlines()

        existing_keys = {
            line.split("=", 1)[0].strip()
            for line in env_lines
            if "=" in line and not line.strip().startswith("#")
        }
        additions: list[str] = []
        for k, v in env_new_vars.items():
            if k not in existing_keys:
                additions.append(f"{k}={v}")

        if additions:
            env_lines.append("")
            env_lines.append(f"# MCP Server: {server_name}")
            env_lines.extend(additions)
            env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
            print(f"  Updated .env with {len(additions)} new variable(s).")
        else:
            print("  .env already up-to-date.")

        print(
            "\nPublishing MCP server/tools to Cognitive now "
            "(this updates what appears in the portal immediately)..."
        )
        try:
            self._publish_to_cognitive(
                server_name=server_name,
                server_description=server_description,
                server_url=server_url,
                auth_type=auth_type,
                headers=headers,
                oauth_client_id=oauth_client_id,
                oauth_client_secret=oauth_client_secret,
                oauth_scopes=oauth_scopes,
                selected_tools=selected_tools,
                oauth_timeout=oauth_timeout,
            )
        except CogSolAPIError as exc:
            print(f"Failed to publish MCP catalog to Cognitive: {exc}")
            return 1

        if auth_type == "oauth2" and oauth_client_secret:
            print(
                "\n  ℹ  OAuth client_secret was entered but NOT written to .env.\n"
                "     It was sent securely to the CogSol API and stored in Azure Key Vault."
            )

        print(
            "\nDone!  Run 'python manage.py makemigrations' followed by "
            "'python manage.py migrate'."
        )
        if auth_type == "oauth2":
            print("OAuth authorization was completed (or attempted) during addmcptools.")
        return 0
