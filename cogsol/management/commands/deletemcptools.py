"""Interactive command for removing an MCP server and its tool definitions.

Workflow
--------
1.  List MCP server classes defined in ``agents/mcp_servers.py``.
2.  User selects a server to remove.
3.  All tool classes in ``agents/mcp_tools.py`` that reference that server
    are shown for confirmation.
4.  On confirmation, the project is updated:
    - Removes the server class from ``mcp_servers.py``.
    - Removes the associated tool classes from ``mcp_tools.py``.
    - Removes references to those tools (and their imports) from every
      ``agent.py``, so the project still imports afterwards.
    - Removes the related env vars from ``.env``.

Nothing is deleted in Cognitive by this command.  The project is the source of
truth, so the removal is published by ``makemigrations`` + ``migrate`` like any
other change; the remote ids stay in ``.state.json`` until then.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

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


def _element_class_name(node: ast.expr) -> str | None:
    """Return the class name an element of a ``tools`` list refers to.

    Handles both ``MyTool()`` and a bare ``MyTool``.
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Name):
        return node.id
    return None


def _span(source_lines: list[str], node: ast.expr | ast.stmt) -> tuple[int, int]:
    """Return the ``(start, end)`` character offsets of a node."""
    offsets = [0]
    for line in source_lines:
        offsets.append(offsets[-1] + len(line))
    start = offsets[node.lineno - 1] + node.col_offset
    end = offsets[(node.end_lineno or node.lineno) - 1] + (node.end_col_offset or 0)
    return start, end


def _remove_tool_references(source: str, class_names: set[str]) -> tuple[str, list[str]]:
    """Drop the given tool classes from ``tools``/``pretools`` lists and imports.

    Returns ``(new_source, removed_names)``.  Formatting of the surviving
    entries is preserved: single-line lists stay on one line, multi-line lists
    keep one entry per line.
    """
    if not class_names:
        return source, []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    lines = source.splitlines(keepends=True)
    removed: list[str] = []
    # (start, end, replacement), applied back-to-front so offsets stay valid.
    edits: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if not targets & {"tools", "pretools"}:
                continue

            keep: list[str] = []
            dropped: list[str] = []
            for element in node.value.elts:
                name = _element_class_name(element)
                if name and name in class_names:
                    dropped.append(name)
                    continue
                el_start, el_end = _span(lines, element)
                keep.append(source[el_start:el_end])
            if not dropped:
                continue
            removed.extend(dropped)

            list_start, list_end = _span(lines, node.value)
            original = source[list_start:list_end]
            if not keep:
                replacement = "[]"
            elif "\n" in original:
                indent = " " * (node.col_offset + 4)
                body = "".join(f"{indent}{entry},\n" for entry in keep)
                replacement = "[\n" + body + " " * node.col_offset + "]"
            else:
                replacement = "[" + ", ".join(keep) + "]"
            edits.append((list_start, list_end, replacement))

        elif isinstance(node, ast.ImportFrom) and (node.module or "").endswith("mcp_tools"):
            surviving = [alias for alias in node.names if alias.name not in class_names]
            if len(surviving) == len(node.names):
                continue
            start, end = _span(lines, node)
            if surviving:
                names = ", ".join(
                    alias.name + (f" as {alias.asname}" if alias.asname else "")
                    for alias in surviving
                )
                edits.append((start, end, f"from {node.module} import {names}"))
            else:
                # Drop the whole statement, including its trailing newline.
                line_end = end
                while line_end < len(source) and source[line_end] != "\n":
                    line_end += 1
                edits.append((start, min(line_end + 1, len(source)), ""))

    if not edits:
        return source, []

    new_source = source
    for start, end, replacement in sorted(edits, reverse=True):
        new_source = new_source[:start] + replacement + new_source[end:]
    return new_source, removed


def _clean_agent_references(app_path: Path, class_names: set[str]) -> list[tuple[Path, list[str]]]:
    """Remove references to the given tool classes from every agent module."""
    candidates = sorted(app_path.glob("*/agent.py"))
    flat_agent = app_path / "agent.py"
    if flat_agent.exists():
        candidates.append(flat_agent)

    cleaned: list[tuple[Path, list[str]]] = []
    for agent_file in candidates:
        source = agent_file.read_text(encoding="utf-8")
        new_source, removed = _remove_tool_references(source, class_names)
        if removed:
            agent_file.write_text(new_source, encoding="utf-8")
            cleaned.append((agent_file, removed))
    return cleaned


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
                or getattr(getattr(cls, "server", None), "__name__", None) == server_cls.__name__
            )
        }

        # ── Summary & confirmation ────────────────────────────────────
        print("\nWill delete:")
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

        # Nothing is deleted in Cognitive here: the project is the source of
        # truth, so the removal travels through a migration like any other
        # change.  ``migrate`` applies it using the ids kept in .state.json.

        # ── Remove server class from mcp_servers.py ──────────────────
        servers_file = project_path / app / "mcp_servers.py"
        if servers_file.exists():
            source = servers_file.read_text(encoding="utf-8")
            new_source, removed = _remove_class_from_source(source, server_cls.__name__)
            if removed:
                servers_file.write_text(new_source, encoding="utf-8")
                print(f"  Removed {server_cls.__name__} from mcp_servers.py")
            else:
                print(f"  Warning: {server_cls.__name__} not found in mcp_servers.py")

        # ── Remove tool classes from mcp_tools.py ────────────────────
        tools_file = project_path / app / "mcp_tools.py"
        if tools_file.exists() and server_tools:
            source = tools_file.read_text(encoding="utf-8")
            for tool_cls in server_tools.values():
                new_source, removed = _remove_class_from_source(source, tool_cls.__name__)
                if removed:
                    source = new_source
                    print(f"  Removed {tool_cls.__name__} from mcp_tools.py")

            # Remove the import line referencing this server class.
            import_line = f"from {app}.mcp_servers import {server_cls.__name__}"
            source = source.replace(import_line + "\n", "").replace(import_line, "")
            tools_file.write_text(source, encoding="utf-8")

        # ── Remove references from the agents that used those tools ───
        tool_class_names = {cls.__name__ for cls in server_tools.values()}
        for agent_file, removed_names in _clean_agent_references(
            project_path / app, tool_class_names
        ):
            names = ", ".join(sorted(set(removed_names)))
            print(f"  Removed {names} from {agent_file.relative_to(project_path)}")

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

            # The remote ids are deliberately kept: 'migrate' needs them to
            # delete the server and its tools in Cognitive, and drops them
            # afterwards.
            local_state = state.get("state", {})
            local_state.get("mcp_servers", {}).pop(server_key, None)
            for tool_name in server_tools:
                local_state.get("mcp_tools", {}).pop(tool_name, None)

            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            print("  Updated .state.json")

        print(
            "\nRemoved from the project. Nothing was deleted in Cognitive yet — run\n"
            "'python manage.py makemigrations' followed by 'python manage.py migrate' "
            "to apply it."
        )
        return 0
