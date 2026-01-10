"""Management command to create a new topic folder under data/."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from cogsol.management.base import BaseCommand

TOPIC_INIT_PY = """\
from cogsol.content import BaseTopic


class {class_name}(BaseTopic):
    \"\"\"Topic node for organizing {topic_name} documents.\"\"\"

    name = "{topic_name}"

    class Meta:
        description = "{topic_name} topic - add a description here."
"""

METADATA_PY = """\
from cogsol.content import BaseMetadataConfig, MetadataType


# Define metadata configurations for this topic.
# Example:
#
# class CategoryMetadata(BaseMetadataConfig):
#     name = "category"
#     type = MetadataType.STRING
#     possible_values = ["General", "Technical", "FAQ"]
#     filtrable = True
#     required = False
#     # If required is True, default_value must be set.
#     # default_value = "General"
"""


def to_class_name(name: str) -> str:
    """Convert a snake_case or kebab-case name to PascalCase."""
    # Replace hyphens with underscores, split on underscores
    parts = name.replace("-", "_").split("_")
    return "".join(word.capitalize() for word in parts if word) + "Topic"


def validate_topic_name(name: str) -> bool:
    """Validate that the topic name is a valid Python identifier."""
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))


class Command(BaseCommand):
    requires_project = True
    help = "Create a new topic folder under data/."

    def add_arguments(self, parser):
        parser.add_argument("name", help="Topic name (used as folder and class name).")
        parser.add_argument(
            "--path",
            default="",
            help=(
                "Optional parent path within data/. Use forward slashes for nesting. "
                "E.g., --path 'parent/child' creates data/parent/child/name/."
            ),
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        if not project_path:
            print("Could not find project path. Run from within a CogSol project.")
            return 1

        topic_name = str(options.get("name") or "")
        parent_path = str(options.get("path") or "")

        # Validate topic name
        if not validate_topic_name(topic_name):
            print(
                f"Invalid topic name '{topic_name}'. "
                "Use only letters, numbers, and underscores, starting with a letter or underscore."
            )
            return 1

        # Build the target path
        data_dir = project_path / "data"
        if not data_dir.exists():
            print(f"Data directory not found at {data_dir}. Is this a CogSol project?")
            return 1

        if parent_path:
            # Normalize path separators and create parent directories
            parent_path = parent_path.replace("\\", "/").strip("/")
            topic_dir = data_dir / parent_path / topic_name
        else:
            topic_dir = data_dir / topic_name

        # Check if topic already exists
        if topic_dir.exists():
            print(f"Topic folder already exists at {topic_dir}")
            return 1

        # Validate parent path components
        if parent_path:
            path_parts = parent_path.split("/")
            for part in path_parts:
                if not validate_topic_name(part):
                    print(
                        f"Invalid path component '{part}'. "
                        "Use only letters, numbers, and underscores."
                    )
                    return 1
            # Check that parent path exists within data/
            parent_dir = data_dir / parent_path
            if not parent_dir.exists():
                print(
                    f"Parent path '{parent_path}' does not exist. "
                    "Create parent topics first or check the path."
                )
                return 1

        # Create the topic folder structure
        topic_dir.mkdir(parents=True, exist_ok=True)

        class_name = to_class_name(topic_name)

        files = {
            "__init__.py": TOPIC_INIT_PY.format(class_name=class_name, topic_name=topic_name),
            "metadata.py": METADATA_PY,
        }

        for filename, content in files.items():
            file_path = topic_dir / filename
            file_path.write_text(textwrap.dedent(content), encoding="utf-8")

        # Calculate relative path for display
        relative_path = topic_dir.relative_to(project_path)
        print(f"Created topic '{topic_name}' at {relative_path}")
        print(f"  - Edit {relative_path / '__init__.py'} to configure the topic")
        print(f"  - Edit {relative_path / 'metadata.py'} to add metadata configurations")
        print(f"  - Run 'python manage.py ingest {topic_name} <files>' to upload documents")

        return 0
