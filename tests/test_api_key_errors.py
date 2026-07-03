"""
Tests for credential-related error handling and fail-fast checks.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from cogsol.core import credentials as credentials_mod
from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.credentials import CREDENTIALS_NOT_CONFIGURED_MESSAGE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bare_client() -> CogSolClient:
    """Instantiate CogSolClient without triggering __init__ network calls."""
    client = CogSolClient.__new__(CogSolClient)
    client.bearer_token = None
    client.bearer_token_expires_at = None
    client.api_key = None
    client.base_url = "https://fake.api.example.com"
    client.content_base_url = None
    return client


def _clear_credentials_env(monkeypatch) -> None:
    for env_var in (
        "COGSOL_API_KEY",
        "COGSOL_AUTH_CLIENT_ID",
        "COGSOL_AUTH_SECRET",
        "COGSOL_ENV",
        "cogsol_env",
    ):
        monkeypatch.delenv(env_var, raising=False)


def _isolate_credentials_store(monkeypatch, tmp_path) -> None:
    creds_path = Path(tmp_path) / ".config" / "cogsol" / "credentials.json"
    monkeypatch.setattr(credentials_mod, "get_credentials_path", lambda: creds_path)


# ---------------------------------------------------------------------------
# CogSol constants / scope resolution
# ---------------------------------------------------------------------------


class TestAuthScopeIdResolution:
    """get_auth_scope_id must resolve to the expected scope values."""

    def test_returns_implantation_scope_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("COGSOL_ENV", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_SCOPE_ID", raising=False)

        from cogsol.core.constants import AUTH_SCOPE_IDS, get_auth_scope_id

        assert get_auth_scope_id() == AUTH_SCOPE_IDS["implantation"]

    def test_returns_implantation_scope_when_env_is_unknown(self, monkeypatch):
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.delenv("COGSOL_AUTH_SCOPE_ID", raising=False)

        from cogsol.core.constants import AUTH_SCOPE_IDS, get_auth_scope_id

        assert get_auth_scope_id() == AUTH_SCOPE_IDS["implantation"]

    def test_returns_production_scope_when_env_is_production(self, monkeypatch):
        monkeypatch.setenv("COGSOL_ENV", "production")
        monkeypatch.delenv("COGSOL_AUTH_SCOPE_ID", raising=False)

        from cogsol.core.constants import AUTH_SCOPE_IDS, get_auth_scope_id

        assert get_auth_scope_id() == AUTH_SCOPE_IDS["production"]

    def test_scope_id_env_var_overrides_derived_value(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_SCOPE_ID", "custom-scope-id-override")
        monkeypatch.setenv("COGSOL_ENV", "production")

        from cogsol.core.constants import get_auth_scope_id

        assert get_auth_scope_id() == "custom-scope-id-override"


# ---------------------------------------------------------------------------
# CogSolClient._refresh_bearer_token
# ---------------------------------------------------------------------------


class TestMissingAuthSecret:
    """_refresh_bearer_token should explain missing client secret clearly."""

    def test_raises_cogsol_api_error(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError):
            _bare_client()._refresh_bearer_token()

    def test_error_mentions_missing_secret_var(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "COGSOL_AUTH_SECRET is not set" in str(exc_info.value)

    def test_error_includes_onboarding_url(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "https://onboarding.cogsol.ai" in str(exc_info.value)

    def test_error_mentions_credentials_setup_command(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "cogsol-admin credentials-setup" in str(exc_info.value)

    def test_no_error_when_secret_is_present(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_ENV", "development")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "some-secret")

        with patch("cogsol.core.api.msal.ConfidentialClientApplication") as mock_app:
            mock_app.return_value.acquire_token_for_client.return_value = {
                "access_token": "fake-token"
            }
            client = _bare_client()
            client._refresh_bearer_token()
            assert client.bearer_token == "fake-token"


# ---------------------------------------------------------------------------
# Command preflight checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module_path,kwargs",
    [
        ("cogsol.management.commands.migrate", {}),
        ("cogsol.management.commands.importagent", {"assistant_id": 1, "app": "agents"}),
        ("cogsol.management.commands.chat", {"agent": "my-agent", "app": "agents"}),
    ],
)
def test_commands_fail_fast_when_credentials_missing(
    tmp_path, monkeypatch, capsys, module_path, kwargs
):
    _clear_credentials_env(monkeypatch)
    _isolate_credentials_store(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    module = importlib.import_module(module_path)
    result = module.Command().handle(project_path=tmp_path, **kwargs)

    assert result == 1
    out = capsys.readouterr().out
    assert CREDENTIALS_NOT_CONFIGURED_MESSAGE in out


def test_migrate_requires_all_three_credentials(tmp_path, monkeypatch, capsys):
    _clear_credentials_env(monkeypatch)
    _isolate_credentials_store(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    monkeypatch.setenv("COGSOL_API_KEY", "test-key")
    monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client")
    # Missing COGSOL_AUTH_SECRET on purpose.

    from cogsol.management.commands.migrate import Command

    result = Command().handle(project_path=tmp_path)

    assert result == 1
    out = capsys.readouterr().out
    assert CREDENTIALS_NOT_CONFIGURED_MESSAGE in out


def test_migrate_proceeds_when_all_credentials_present(tmp_path, monkeypatch, capsys):
    _clear_credentials_env(monkeypatch)
    _isolate_credentials_store(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text("", encoding="utf-8")

    monkeypatch.setenv("COGSOL_API_KEY", "test-key")
    monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("COGSOL_AUTH_SECRET", "test-secret")

    from cogsol.management.commands.migrate import Command

    result = Command().handle(project_path=tmp_path)

    assert result == 1
    out = capsys.readouterr().out
    assert CREDENTIALS_NOT_CONFIGURED_MESSAGE not in out
    assert "No migrations folder found" in out
