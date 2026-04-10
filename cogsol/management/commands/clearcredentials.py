from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cogsol.core.credentials import CREDENTIAL_FIELD_TO_ENV_VAR, clear_stored_credentials
from cogsol.management.base import BaseCommand


class Command(BaseCommand):
    requires_project = False
    help = "Clear locally stored tenant credentials for cogsol-admin."

    def add_arguments(self, parser):
        pass

    def handle(self, project_path: Path | None, **options: Any) -> int:
        removed = clear_stored_credentials()
        for env_var in CREDENTIAL_FIELD_TO_ENV_VAR.values():
            os.environ.pop(env_var, None)

        if removed:
            print("Credentials cleared.")
        else:
            print("No stored credentials were found.")
        return 0
