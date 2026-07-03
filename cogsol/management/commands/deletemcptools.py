"""Interactive command for removing an MCP server and its tool definitions.

Workflow
--------
1.  List MCP server classes defined in ``agents/mcp_servers.py``.
2.  User selects a server to remove.
3.  All tool classes in ``agents/mcp_tools.py`` that reference that server
    are shown for confirmation.
4.  On confirmation:
    - Deletes the server from the CogSol API.
    - Removes the server class from ``mcp_servers.py``.
    - Removes the associated tool classes from ``mcp_tools.py``.
    - Removes the related env vars from ``.env``.
"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.constants import get_cognitive_api_base_url
from cogsol.core.loader import collect_classes
from cogsol.management.base import BaseCommand
from cogsol.management.commands.addmcptools import (
    _ask,
    _ask_yes_no,
    _to_env_key,
)


def _remove_class_from_source(source: str, class_name: str) -> tuple[str, bool]:
    """Remove a top-level class definition from Python source using AST.

    Returns ``(new_source, was_removed)``.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, False

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            lines = source.splitlines(keepends=True)
            start = node.lineno - 1  # 0-based index
            end = node.end_lineno  # 0-based exclusive end

            # Also remove blank lines immediately before the class.
            while start > 0 and lines[start - 1].strip() == "":
                start -= 1

            return "".join(lines[:start] + lines[end:]), True

    return source, False


def _find_server_env_prefix(server_name: str) -> str:
    """Return the env-var prefix used for *server_name* (e.g. 'MCP_MY_SERVER_')."""
    return _to_env_key(server_name) + "_"


def _collect_server_env_keys(env_path: Path, prefix: str) -> set[str]:
    """Return all env-var keys in *env_path* that start with *prefix*."""
    if not env_path.exists():
        return set()
    result: set[str] = set()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key.startswith(prefix):
                result.add(key)
    return result


def _remove_env_keys(env_path: Path, keys: set[str]) -> int:
    """Remove env var lines (and orphaned section comments) from *.env*.

    Returns the number of variable lines removed.
    """
    if not env_path.exists() or not keys:
        return 0

    lines = env_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Check if this is a "# MCP Server: ..." comment whose entire block
        # is being removed — if so, skip the comment too.
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
            if block_keys and all(k in keys for k in block_keys):
                # Skip the comment and its whole block.
                i = j
                removed += len(block_keys)
                continue

        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in keys:
                removed += 1
                i += 1
                continue

        out.append(line)
        i += 1

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return removed


class Command(BaseCommand):
    help = "Remove an MCP server and its tool definitions from the project."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            default="agents",
            help="App folder (default: agents).",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        app = str(options.get("app") or "agents")

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

        choice = _ask("Select server to delete (number, or 0 to cancel)", "0")
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

        server_key = server_names[idx]
        server_cls = servers[server_key]
        server_real_name: str = getattr(server_cls, "name", None) or server_key

        # ── Find tools that belong to this server ─────────────────────
        all_tools: dict[str, Any] = classes.get("mcp_tools", {})
        server_tools = {
            name: cls
            for name, cls in all_tools.items()
            if (
                getattr(cls, "server", None) is server_cls
                or getattr(getattr(cls, "server", None), "__name__", None)
                == server_cls.__name__
            )
        }

        # ── Summary & confirmation ────────────────────────────────────
        print(f"\nWill delete:")
        print(f"  Server : {server_real_name}  (class: {server_cls.__name__})")
        if server_tools:
            tool_list = ", ".join(sorted(server_tools.keys()))
            print(f"  Tools  : {tool_list}")
        else:
            print("  Tools  : none")
        print()

        if not _ask_yes_no("Confirm deletion?", default=False):
            print("Cancelled.")
            return 0

        # ── Delete from CogSol API ────────────────────────────────────
        api_base = get_cognitive_api_base_url()
        api_key = os.environ.get("COGSOL_API_KEY")
        if api_base:
            client = CogSolClient(base_url=api_base, api_key=api_key)
            # Find remote server by name (same approach as addmcptools)
            try:
                servers_remote = client.list_mcp_servers()
                results = (
                    servers_remote
                    if isinstance(servers_remote, list)
                    else (servers_remote or {}).get("results", [])
                )
                server_url = getattr(server_cls, "url", "") or ""
                remote_entry = next(
                    (
                        s
                        for s in results
                        if isinstance(s, dict)
                        and (
                            str(s.get("name", "")).strip().casefold()
                            == server_real_name.strip().casefold()
                            or str(s.get("url", "")).rstrip("/")
                            == str(server_url).rstrip("/")
                        )
                    ),
                    None,
                )
                if remote_entry and remote_entry.get("id"):
                    client.delete_mcp_server(int(remote_entry["id"]))
                    print(f"  Deleted MCP server from Cognitive (id={remote_entry['id']}).")
                else:
                    print(
                        "  Warning: MCP server not found in Cognitive; skipping API deletion."
                    )
            except CogSolAPIError as exc:
                print(f"  Warning: could not delete server from API: {exc}")
        else:
            print("  COGSOL_API_BASE not set — skipping API deletion.")

        # ── Remove server class from mcp_servers.py ──────────────────
        servers_file = project_path / app / "mcp_servers.py"
        if servers_file.exists():
            source = servers_file.read_text(encoding="utf-8")
            new_source, removed = _remove_class_from_source(source, server_cls.__name__)
            if removed:
                servers_file.write_text(new_source, encoding="utf-8")
                print(f"  Removed {server_cls.__name__} from mcp_servers.py")
            else:
                print(
                    f"  Warning: {server_cls.__name__} not found in mcp_servers.py"
                )

        # ── Remove tool classes from mcp_tools.py ────────────────────
        tools_file = project_path / app / "mcp_tools.py"
        if tools_file.exists() and server_tools:
            source = tools_file.read_text(encoding="utf-8")
            for tool_name, tool_cls in server_tools.items():
                new_source, removed = _remove_class_from_source(source, tool_cls.__name__)
                if removed:
                    source = new_source
                    print(f"  Removed {tool_cls.__name__} from mcp_tools.py")

            # Remove the import line referencing this server class.
            import_line = f"from {app}.mcp_servers import {server_cls.__name__}"
            source = source.replace(import_line + "\n", "").replace(import_line, "")
            tools_file.write_text(source, encoding="utf-8")

        # ── Clean .env ────────────────────────────────────────────────
        env_path = project_path / ".env"
        prefix = _find_server_env_prefix(server_real_name)
        keys_to_remove = _collect_server_env_keys(env_path, prefix)
        if keys_to_remove:
            count = _remove_env_keys(env_path, keys_to_remove)
            print(f"  Removed {count} env var(s) from .env")
        else:
            print("  No env vars found to remove.")

        # ── Update .state.json ────────────────────────────────────────
        state_path = project_path / app / "migrations" / ".state.json"
        if state_path.exists():
            try:
                state: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                state = {}

            remote = state.get("remote", {})
            mcp_srv = remote.get("mcp_servers", {})
            for k in list(mcp_srv.keys()):
                if k in (server_key, server_real_name, server_cls.__name__):
                    del mcp_srv[k]

            mcp_tools_remote = remote.get("mcp_tools", {})
            for tool_name in server_tools:
                mcp_tools_remote.pop(tool_name, None)

            local_state = state.get("state", {})
            local_state.get("mcp_servers", {}).pop(server_key, None)
            for tool_name in server_tools:
                local_state.get("mcp_tools", {}).pop(tool_name, None)

            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print("  Updated .state.json")

        print(
            "\nDone! Run 'python manage.py makemigrations' followed by "
            "'python manage.py migrate' to apply the deletion."
        )
        return 0
