"""Management command to list topics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from cogsol.core.api import CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.management.base import BaseCommand


def get_client(project_path: Path) -> CogSolClient:
    """Get an API client configured for the project."""
    import sys

    load_dotenv(project_path / ".env")

    sys.path.insert(0, str(project_path))
    try:
        import settings

        api_base = getattr(settings, "COGSOL_API_BASE", None)
        content_base = getattr(settings, "COGSOL_CONTENT_API_BASE", None)
    except ImportError:
        api_base = None
        content_base = None
    finally:
        sys.path.pop(0)

    import os

    api_base = api_base or os.environ.get("COGSOL_API_BASE", "http://localhost:8000")
    content_base = content_base or os.environ.get("COGSOL_CONTENT_API_BASE", api_base)
    token = os.environ.get("COGSOL_API_TOKEN")

    return CogSolClient(base_url=api_base, token=token, content_base_url=content_base)


def build_tree(nodes: list[dict], parent_id: Optional[int] = None, prefix: str = "") -> list[str]:
    """Build a tree representation of nodes."""
    lines = []
    children = [n for n in nodes if n.get("parent") == parent_id]
    children.sort(key=lambda n: n.get("name", ""))

    for i, node in enumerate(children):
        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        node_name = node.get("name", "unknown")
        node_id = node.get("id", "?")
        doc_count = node.get("document_count", 0)

        line = f"{prefix}{connector}{node_name} (id={node_id}, docs={doc_count})"
        lines.append(line)

        # Recursively add children
        child_prefix = prefix + ("    " if is_last else "│   ")
        lines.extend(build_tree(nodes, parent_id=node["id"], prefix=child_prefix))

    return lines


def list_local_topics(data_dir: Path, prefix: str = "") -> list[str]:
    """List topics defined locally in the data/ folder."""
    lines = []
    items = sorted(
        [
            d
            for d in data_dir.iterdir()
            if d.is_dir() and not d.name.startswith(("_", ".", "migrations"))
        ]
    )

    for i, item in enumerate(items):
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "

        # Check if it has __init__.py with BaseTopic
        init_file = item / "__init__.py"
        is_topic = init_file.exists()

        status = "✓" if is_topic else "?"
        lines.append(f"{prefix}{connector}[{status}] {item.name}")

        # Recursively check subdirectories
        child_prefix = prefix + ("    " if is_last else "│   ")
        lines.extend(list_local_topics(item, child_prefix))

    return lines


class Command(BaseCommand):
    requires_project = True
    help = "List topics from the API or local definitions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--local",
            action="store_true",
            help="List topics defined locally in data/ instead of from the API.",
        )
        parser.add_argument(
            "--flat",
            action="store_true",
            help="Show flat list instead of tree view.",
        )
        parser.add_argument(
            "--sync-status",
            dest="sync_status",
            action="store_true",
            help="Show sync status between local and remote topics.",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        if not project_path:
            print("Could not find project path. Run from within a CogSol project.")
            return 1

        local_only = bool(options.get("local"))
        flat_view = bool(options.get("flat"))
        sync_status = bool(options.get("sync_status"))

        if local_only:
            return self._list_local(project_path)

        if sync_status:
            return self._show_sync_status(project_path)

        return self._list_remote(project_path, flat_view)

    def _list_local(self, project_path: Path) -> int:
        """List locally defined topics."""
        data_dir = project_path / "data"
        if not data_dir.exists():
            print("No data/ folder found.")
            return 1

        print("Local topics (data/):")
        print("  [✓] = has topic definition, [?] = folder only")
        print()

        lines = list_local_topics(data_dir)
        if lines:
            for line in lines:
                print(f"  {line}")
        else:
            print("  (no topics found)")

        return 0

    def _list_remote(self, project_path: Path, flat_view: bool) -> int:
        """List topics from the API."""
        client = get_client(project_path)

        try:
            nodes = client.list_nodes()
        except Exception as e:
            print(f"Error fetching topics from API: {e}")
            return 1

        if not nodes:
            print("No topics found in the API.")
            print("Create topics with 'python manage.py starttopic <name>' and migrate.")
            return 0

        print(f"Topics from API ({len(nodes)} total):")
        print()

        if flat_view:
            for node in sorted(nodes, key=lambda n: n.get("name", "")):
                name = node.get("name", "unknown")
                node_id = node.get("id", "?")
                parent = node.get("parent")
                doc_count = node.get("document_count", 0)
                parent_str = f", parent={parent}" if parent else ""
                print(f"  {name} (id={node_id}, docs={doc_count}{parent_str})")
        else:
            lines = build_tree(nodes)
            for line in lines:
                print(f"  {line}")

        return 0

    def _show_sync_status(self, project_path: Path) -> int:
        """Show sync status between local and remote topics."""
        data_dir = project_path / "data"
        client = get_client(project_path)

        # Get local topics
        local_topics = set()
        if data_dir.exists():
            for item in data_dir.rglob("__init__.py"):
                # Check if parent folder is a topic (not data/ itself or migrations/)
                local_parent = item.parent
                if local_parent != data_dir and "migrations" not in str(local_parent):
                    # Build relative path from data/
                    rel_path = local_parent.relative_to(data_dir)
                    local_topics.add(str(rel_path).replace("\\", "/"))

        # Get remote topics
        remote_topics = {}
        try:
            nodes = client.list_nodes()
            # Build paths for remote topics
            node_map = {n["id"]: n for n in nodes}
            for node in nodes:
                path_parts = [node["name"]]
                parent_id = node.get("parent")
                while parent_id:
                    parent_node = node_map.get(parent_id)
                    if parent_node:
                        path_parts.insert(0, parent_node["name"])
                        parent_id = parent_node.get("parent")
                    else:
                        break
                path = "/".join(path_parts)
                remote_topics[path] = node["id"]
        except Exception as e:
            print(f"Warning: Could not fetch remote topics: {e}")
            remote_topics = {}

        # Compare
        only_local = local_topics - set(remote_topics.keys())
        only_remote = set(remote_topics.keys()) - local_topics
        synced = local_topics & set(remote_topics.keys())

        print("Topic Sync Status:")
        print()

        if synced:
            print("  Synced (local ↔ remote):")
            for topic in sorted(synced):
                print(f"    ✓ {topic} (id={remote_topics[topic]})")
            print()

        if only_local:
            print("  Local only (needs migrate):")
            for topic in sorted(only_local):
                print(f"    ⚠ {topic}")
            print()

        if only_remote:
            print("  Remote only (not in local code):")
            for topic in sorted(only_remote):
                print(f"    ⚠ {topic} (id={remote_topics[topic]})")
            print()

        if not synced and not only_local and not only_remote:
            print("  No topics found locally or remotely.")

        return 0
