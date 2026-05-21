from __future__ import annotations

from getpass import getpass
from pathlib import Path
from typing import Any

from cogsol.core.credentials import ONBOARDING_MESSAGE, save_credentials
from cogsol.management.base import BaseCommand


class Command(BaseCommand):
    requires_project = False
    help = "Interactively configure tenant credentials for cogsol-admin."

    def add_arguments(self, parser):
        pass

    def _ask_secret(self, prompt: str) -> str:
        try:
            return getpass(prompt).strip()
        except Exception:
            return input(prompt).strip()

    def handle(self, project_path: Path | None, **options: Any) -> int:
        print(ONBOARDING_MESSAGE)
        print()

        client_id = input("client_id: ").strip()
        client_secret = self._ask_secret("client_secret: ")
        tenant_api_key = self._ask_secret("tenant_api_key: ")

        if not client_id or not client_secret or not tenant_api_key:
            print("All fields are required. No credentials were saved.")
            return 1

        try:
            target = save_credentials(
                client_id=client_id,
                client_secret=client_secret,
                tenant_api_key=tenant_api_key,
            )
        except OSError as exc:
            print(f"Could not save credentials: {exc}")
            return 1

        print(f"Credentials saved to {target}.")
        return 0
