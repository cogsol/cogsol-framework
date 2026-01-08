from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


class BaseCommand:
    requires_project: bool = True
    help: str = ""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        pass

    def handle(self, project_path: Path | None, **options: Any) -> int:
        raise NotImplementedError

    def run(self, argv: list[str], project_path: Path | None) -> int:
        parser = argparse.ArgumentParser(
            prog=self.__class__.__name__.lower(), description=self.help
        )
        self.add_arguments(parser)
        options = vars(parser.parse_args(argv))
        return self.handle(project_path=project_path, **options)
