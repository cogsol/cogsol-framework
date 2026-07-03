"""Tests for CLI credential storage, loading, and credential commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cogsol.core import credentials as credentials_mod
from cogsol.core.credentials import (
    CREDENTIALS_NOT_CONFIGURED_MESSAGE,
    clear_stored_credentials,
    credentials_are_configured,
    ensure_credentials_configured,
    load_runtime_credentials,
    load_stored_credentials,
    missing_required_env_vars,
    save_credentials,
)
from cogsol.core.management import _command_registry
from cogsol.management.commands.clearcredentials import Command as ClearCredentialsCommand
from cogsol.management.commands.credentialssetup import Command as CredentialsSetupCommand


def _clear_credential_env(monkeypatch) -> None:
    for name in ("COGSOL_API_KEY", "COGSOL_AUTH_CLIENT_ID", "COGSOL_AUTH_SECRET"):
        monkeypatch.delenv(name, raising=False)


def _isolate_store(monkeypatch, tmp_path: Path) -> None:
    creds_path = tmp_path / ".config" / "cogsol" / "credentials.json"
    monkeypatch.setattr("cogsol.core.credentials.get_credentials_path", lambda: creds_path)


def test_save_and_load_credentials_roundtrip(tmp_path):
    path = tmp_path / "credentials.json"
    target = save_credentials(
        client_id="client-id",
        client_secret="client-secret",
        tenant_api_key="tenant-key",
        path=path,
    )

    assert target == path
    assert path.exists()
    loaded = load_stored_credentials(path)
    assert loaded == {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "tenant_api_key": "tenant-key",
    }

    if os.name == "posix":
        # File should not be world-readable/writable in POSIX systems.
        mode = path.stat().st_mode & 0o777
        assert mode & 0o077 == 0


def test_save_credentials_requires_all_fields(tmp_path):
    with pytest.raises(ValueError):
        save_credentials(
            client_id="",
            client_secret="client-secret",
            tenant_api_key="tenant-key",
            path=tmp_path / "credentials.json",
        )


def test_clear_stored_credentials(tmp_path):
    path = tmp_path / "credentials.json"
    save_credentials(
        client_id="client-id",
        client_secret="client-secret",
        tenant_api_key="tenant-key",
        path=path,
    )

    assert clear_stored_credentials(path) is True
    assert not path.exists()
    assert clear_stored_credentials(path) is False


def test_load_runtime_credentials_prefers_dotenv_over_stored(tmp_path, monkeypatch):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    # Save global credentials.
    save_credentials(
        client_id="stored-client",
        client_secret="stored-secret",
        tenant_api_key="stored-api-key",
    )

    # .env should win over global credentials.
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(
        "\n".join(
            [
                "COGSOL_AUTH_CLIENT_ID=dotenv-client",
                "COGSOL_AUTH_SECRET=dotenv-secret",
                "COGSOL_API_KEY=dotenv-api-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    load_runtime_credentials(project)

    assert os.environ.get("COGSOL_AUTH_CLIENT_ID") == "dotenv-client"
    assert os.environ.get("COGSOL_AUTH_SECRET") == "dotenv-secret"
    assert os.environ.get("COGSOL_API_KEY") == "dotenv-api-key"


def test_load_runtime_credentials_uses_stored_when_dotenv_missing(tmp_path, monkeypatch):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    save_credentials(
        client_id="stored-client",
        client_secret="stored-secret",
        tenant_api_key="stored-api-key",
    )

    project = tmp_path / "project"
    project.mkdir()

    load_runtime_credentials(project)

    assert os.environ.get("COGSOL_AUTH_CLIENT_ID") == "stored-client"
    assert os.environ.get("COGSOL_AUTH_SECRET") == "stored-secret"
    assert os.environ.get("COGSOL_API_KEY") == "stored-api-key"


def test_ensure_credentials_configured_false_when_missing(tmp_path, monkeypatch):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    project = tmp_path / "project"
    project.mkdir()

    assert ensure_credentials_configured(project) is False
    assert credentials_are_configured() is False
    assert set(missing_required_env_vars()) == {
        "COGSOL_API_KEY",
        "COGSOL_AUTH_CLIENT_ID",
        "COGSOL_AUTH_SECRET",
    }


def test_credentials_setup_command_saves_credentials(tmp_path, monkeypatch):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    answers = iter(["client-id"])
    secrets = iter(["client-secret", "tenant-key"])

    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(CredentialsSetupCommand, "_ask_secret", lambda self, _prompt: next(secrets))

    result = CredentialsSetupCommand().handle(project_path=None)

    assert result == 0
    path = credentials_mod.get_credentials_path()
    assert path.exists()
    assert load_stored_credentials(path) == {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "tenant_api_key": "tenant-key",
    }


def test_credentials_setup_command_handles_connectivity_failure_on_client_init(
    tmp_path, monkeypatch
):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    answers = iter(["client-id"])
    secrets = iter(["client-secret", "tenant-key"])

    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(CredentialsSetupCommand, "_ask_secret", lambda self, _prompt: next(secrets))
    monkeypatch.setattr(
        "cogsol.management.commands.credentialssetup.CogSolClient",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("invalid_grant")),
    )

    result = CredentialsSetupCommand().handle(project_path=None)

    assert result == 0
    assert load_stored_credentials(credentials_mod.get_credentials_path()) == {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "tenant_api_key": "tenant-key",
    }


def test_clear_credentials_command_removes_file_and_env(tmp_path, monkeypatch):
    _clear_credential_env(monkeypatch)
    _isolate_store(monkeypatch, tmp_path)

    save_credentials(
        client_id="client-id",
        client_secret="client-secret",
        tenant_api_key="tenant-key",
    )
    monkeypatch.setenv("COGSOL_API_KEY", "tenant-key")
    monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("COGSOL_AUTH_SECRET", "client-secret")

    result = ClearCredentialsCommand().handle(project_path=None)

    assert result == 0
    assert credentials_mod.get_credentials_path().exists() is False
    assert os.environ.get("COGSOL_API_KEY") is None
    assert os.environ.get("COGSOL_AUTH_CLIENT_ID") is None
    assert os.environ.get("COGSOL_AUTH_SECRET") is None


def test_command_registry_includes_credentials_commands():
    commands = _command_registry()

    assert "credentials-setup" in commands
    assert "logout" in commands


def test_not_configured_message_is_stable():
    assert "credentials-setup" in CREDENTIALS_NOT_CONFIGURED_MESSAGE
