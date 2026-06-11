from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path
from typing import Any

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.credentials import (
    CREDENTIAL_FIELD_TO_ENV_VAR,
    ONBOARDING_MESSAGE,
    save_credentials,
)
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

    def _error_hint(self, error_msg: str) -> str:
        if "401" in error_msg:
            return "Invalid API key — double-check your tenant_api_key."
        if "403" in error_msg:
            return (
                "Your client_id and tenant_api_key may not match — double-check your credentials."
            )
        if "500" in error_msg:
            return "Server error — the API may be experiencing issues, try again later."
        if "Connection error" in error_msg:
            return "Could not reach the server — check your internet connection."
        return ""

    def _check_connectivity(self, client_id: str, client_secret: str, tenant_api_key: str) -> None:
        os.environ[CREDENTIAL_FIELD_TO_ENV_VAR["client_id"]] = client_id
        os.environ[CREDENTIAL_FIELD_TO_ENV_VAR["client_secret"]] = client_secret
        os.environ[CREDENTIAL_FIELD_TO_ENV_VAR["tenant_api_key"]] = tenant_api_key

        print("\nChecking API connectivity...")

        client = CogSolClient(api_key=tenant_api_key)
        error_msg = None

        for check in [
            lambda: client.list_mcp_servers(),
            lambda: client.list_nodes(),
        ]:
            try:
                check()
            except (CogSolAPIError, Exception) as exc:
                error_msg = str(exc)
                break

        if error_msg is None:
            print("  CogSol API: OK")
        else:
            print(f"  CogSol API: FAILED — {error_msg}")
            hint = self._error_hint(error_msg)
            if hint:
                print(f"  Hint: {hint}")

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

        self._check_connectivity(client_id, client_secret, tenant_api_key)

        return 0
