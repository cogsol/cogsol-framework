"""
Command dispatcher used by manage.py and cogsol-admin.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from cogsol.management.base import BaseCommand


def _command_registry() -> dict[str, str]:
    return {
        "startproject": "cogsol.management.commands.startproject",
        "startagent": "cogsol.management.commands.startagent",
        "starttopic": "cogsol.management.commands.starttopic",
        "topics": "cogsol.management.commands.topics",
        "ingest": "cogsol.management.commands.ingest",
        "importagent": "cogsol.management.commands.importagent",
        "makemigrations": "cogsol.management.commands.makemigrations",
        "migrate": "cogsol.management.commands.migrate",
        "chat": "cogsol.management.commands.chat",
    }


def _load_command(name: str) -> BaseCommand:
    from importlib import import_module

    module_path = _command_registry()[name]
    module = import_module(module_path)
    return cast(BaseCommand, module.Command())


def execute_from_command_line(argv=None, project_path: Path | None = None) -> int:
    argv = list(argv or sys.argv)
    if len(argv) < 2:
        available = ", ".join(sorted(_command_registry().keys()))
        print(f"A command is required. Available commands: {available}")
        return 1

    command_name = argv[1]
    commands = _command_registry()
    if command_name not in commands:
        available = ", ".join(sorted(commands.keys()))
        print(f"Unknown command '{command_name}'. Available commands: {available}")
        return 1

    command = _load_command(command_name)
    if getattr(command, "requires_project", True) and project_path is None:
        print(f"The command '{command_name}' must be run from inside a CogSol project.")
        return 1

    return command.run(argv[2:], project_path=project_path)
