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

import re
from pathlib import Path
from typing import Any

from cogsol.core.env import load_dotenv
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


def _ask(prompt: str, default: str = "") -> str:
    """Simple input wrapper with an optional default shown in brackets."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def _ask_secret(prompt: str) -> str:
    """Ask for a secret value (displayed as-is; use where getpass is unavailable)."""
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


class Command(BaseCommand):
    help = "Interactively configure an MCP server and select tools."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            default="agents",
            help="App folder (default: agents).",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:  # noqa: C901
        assert project_path is not None, "project_path is required"
        app = str(options.get("app") or "agents")

        load_dotenv(project_path / ".env")

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
        for i, t in enumerate(AUTH_TYPES, 1):
            suffix = "  ← default" if t == "headers" else ""
            print(f"  {i}. {t}{suffix}")
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

        if not connected and auth_type != "oauth2":
            print("Failed to connect to the MCP server. Check URL and headers.")
            return 1

        selected_tools: list[dict[str, Any]] = []

        if tools:
            print(f"\nFound {len(tools)} tool(s):\n")
            for i, t in enumerate(tools, 1):
                desc = t.get("description", "")
                print(f"  {i}. {t['name']}")
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
                    "Could not list tools without authorization (expected for OAuth 2.1 servers).\n"
                    "The server definition will be created without tool entries.\n"
                    "After running `migrate`, complete the OAuth authorization flow from the\n"
                    "CogSol portal, then re-run `addmcptools` or add tools manually.\n"
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
                f'    name = "{server_name}"',
                f'    description = "{server_description}"',
                '    auth_type = "none"',
                f'    url = "{server_url}"',
            ]

        elif auth_type == "headers":
            header_env_entries: dict[str, str] = {}
            header_attr_lines: list[str] = []
            for hk, hv in headers.items():
                env_key = _to_env_key(f"{server_name}_{hk}")
                header_env_entries[env_key] = hv
                env_new_vars[env_key] = hv
                header_attr_lines.append(f'        "{hk}": os.environ.get("{env_key}", ""),')
            headers_block = (
                "{\n" + "\n".join(header_attr_lines) + "\n    }" if header_attr_lines else "{}"
            )
            server_body_lines = [
                f'    name = "{server_name}"',
                f'    description = "{server_description}"',
                f'    url = "{server_url}"',
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
                f'    name = "{server_name}"',
                f'    description = "{server_description}"',
                '    auth_type = "oauth2"',
                f'    url = "{server_url}"',
            ]
            if oauth_client_id:
                server_body_lines.append(
                    f'    oauth_client_id = os.environ.get("{oauth_cid_env}", "")'
                )
            if oauth_scopes:
                server_body_lines.append(
                    f'    oauth_scopes = os.environ.get("{oauth_scopes_env}", "")'
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
                f'    """MCP server: {server_name}."""',
                "",
                server_body,
                "",
            ]
        )

        # ── Build mcp_tools.py snippet ───────────────────────────────
        tool_classes: list[str] = []
        for t in selected_tools:
            t_name = t["name"]
            t_desc = t.get("description", "") or ""
            t_cls_base = re.sub(r"[^a-zA-Z0-9]+", " ", t_name).title().replace(" ", "")
            t_cls_name = f"{t_cls_base}MCPTool"
            tool_classes.append(
                "\n".join(
                    [
                        "",
                        "",
                        f"class {t_cls_name}(BaseMCPTool):",
                        f'    """MCP tool: {t_name}."""',
                        "",
                        f'    name = "{t_name}"',
                        f'    description = """{t_desc}"""',
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

        if auth_type == "oauth2" and oauth_client_secret:
            print(
                "\n  ℹ  OAuth client_secret was entered but NOT written to .env.\n"
                "     It will be sent to the CogSol API when you run `python manage.py migrate`.\n"
                "     (Stored securely in Azure Key Vault by the backend.)\n"
                "     Please re-enter it if prompted during `migrate`."
            )

        print(
            "\nDone!  Run 'python manage.py makemigrations' followed by "
            "'python manage.py migrate'."
        )
        if auth_type == "oauth2":
            print("After migrate, complete the OAuth authorization flow from the CogSol portal.")
        return 0
