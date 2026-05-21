from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from cogsol.core.credentials import (
    CREDENTIALS_NOT_CONFIGURED_MESSAGE,
    ensure_credentials_configured,
    load_runtime_credentials,
)


class BaseCommand:
    requires_project: bool = True
    help: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def handle(self, project_path: Path | None, **options: Any) -> int:
        raise NotImplementedError

    def load_runtime_environment(self, project_path: Path | None) -> None:
        """Load credentials from .env and user-level CLI config."""
        load_runtime_credentials(project_path)

    def ensure_credentials_configured(self, project_path: Path | None) -> bool:
        """Ensure required API credentials are available before running API commands."""
        if ensure_credentials_configured(project_path):
            return True
        print(CREDENTIALS_NOT_CONFIGURED_MESSAGE)
        return False

    def run(self, argv: list[str], project_path: Path | None) -> int:
        parser = argparse.ArgumentParser(
            prog=self.__class__.__name__.lower(), description=self.help
        )
        self.add_arguments(parser)
        options = vars(parser.parse_args(argv))
        return self.handle(project_path=project_path, **options)
