"""
Tests for API key and credential error messages (branch: csp-1666-api-key-error-msg).

Covers:
- CogSolClient._refresh_bearer_token: detailed error when COGSOL_AUTH_SECRET is missing.
- migrate Command: no-credentials check shows helpful message and returns 1.
- importagent Command: no-credentials check shows helpful message and returns 1.
- chat Command: no-credentials check shows helpful message and returns 1.
- Positive cases: having COGSOL_API_KEY or COGSOL_AUTH_CLIENT_ID bypasses the check.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from cogsol.core.api import CogSolAPIError, CogSolClient


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


# ---------------------------------------------------------------------------
# CogSolClient._refresh_bearer_token
# ---------------------------------------------------------------------------


class TestMissingAuthSecret:
    """_refresh_bearer_token must raise CogSolAPIError with a helpful message
    when COGSOL_AUTH_CLIENT_ID is set but COGSOL_AUTH_SECRET is missing."""

    def test_raises_cogsol_api_error(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError):
            _bare_client()._refresh_bearer_token()

    def test_error_mentions_missing_secret_var(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "COGSOL_AUTH_SECRET is not set" in str(exc_info.value)

    def test_error_includes_onboarding_url(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "https://onboarding.cogsol.ai" in str(exc_info.value)

    def test_error_mentions_implantation_portal(self, monkeypatch):
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.delenv("COGSOL_AUTH_SECRET", raising=False)

        with pytest.raises(CogSolAPIError) as exc_info:
            _bare_client()._refresh_bearer_token()

        assert "implantation portal" in str(exc_info.value)

    def test_no_error_when_secret_is_present(self, monkeypatch):
        """With a valid secret the error must NOT be raised (msal call may fail,
        but that is a different error path)."""
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("COGSOL_AUTH_SECRET", "some-secret")

        # The error about missing secret should not be raised;
        # msal.ConfidentialClientApplication is mocked to avoid network calls.
        with patch("cogsol.core.api.msal.ConfidentialClientApplication") as mock_app:
            mock_app.return_value.acquire_token_for_client.return_value = {
                "access_token": "fake-token"
            }
            # Should not raise CogSolAPIError about missing secret
            client = _bare_client()
            client._refresh_bearer_token()
            assert client.bearer_token == "fake-token"


# ---------------------------------------------------------------------------
# migrate Command – credential check
# ---------------------------------------------------------------------------


class TestMigrateCommandCredentialCheck:
    """migrate handle() must show a helpful error and return 1 when no credentials
    are available, and must proceed normally when credentials are present."""

    def test_no_credentials_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            result = Command().handle(project_path=tmp_path)

        assert result == 1

    def test_no_credentials_prints_no_credentials_message(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            Command().handle(project_path=tmp_path)

        out = capsys.readouterr().out
        assert "No API credentials found" in out

    def test_no_credentials_prints_api_key_instruction(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            Command().handle(project_path=tmp_path)

        out = capsys.readouterr().out
        assert "COGSOL_API_KEY" in out
        assert "https://onboarding.cogsol.ai" in out

    def test_no_credentials_prints_implantation_portal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            Command().handle(project_path=tmp_path)

        out = capsys.readouterr().out
        assert "implantation portal" in out

    def test_api_key_passes_credential_check(self, tmp_path, monkeypatch, capsys):
        """When COGSOL_API_KEY is set the command should pass the credentials check.
        It will still return 1 because there are no migration folders in tmp_path,
        but the credentials error must NOT be shown."""
        monkeypatch.setenv("COGSOL_API_KEY", "test-key-abc")
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            Command().handle(project_path=tmp_path)

        out = capsys.readouterr().out
        assert "No API credentials found" not in out
        # Confirms the command progressed past the check
        assert "No migrations folder found" in out

    def test_auth_client_id_passes_credential_check(self, tmp_path, monkeypatch, capsys):
        """When COGSOL_AUTH_CLIENT_ID is set the credential check should pass.
        It will still return 1 because there are no migration folders in tmp_path,
        but the credentials error must NOT be shown."""
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.setenv("COGSOL_AUTH_CLIENT_ID", "test-client-id")
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.migrate import Command

        with patch("cogsol.management.commands.migrate.load_dotenv"):
            Command().handle(project_path=tmp_path)

        out = capsys.readouterr().out
        assert "No API credentials found" not in out
        # Confirms the command progressed past the check
        assert "No migrations folder found" in out


# ---------------------------------------------------------------------------
# importagent Command – credential check
# ---------------------------------------------------------------------------


class TestImportagentCommandCredentialCheck:
    """importagent handle() must show a helpful error and return 1 when no
    credentials are available."""

    def test_no_credentials_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.importagent import Command

        with patch("cogsol.management.commands.importagent.load_dotenv"):
            result = Command().handle(project_path=tmp_path, assistant_id=1, app="agents")

        assert result == 1

    def test_no_credentials_prints_helpful_message(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.importagent import Command

        with patch("cogsol.management.commands.importagent.load_dotenv"):
            Command().handle(project_path=tmp_path, assistant_id=1, app="agents")

        out = capsys.readouterr().out
        assert "No API credentials found" in out
        assert "COGSOL_API_KEY" in out
        assert "https://onboarding.cogsol.ai" in out

    def test_no_credentials_prints_implantation_portal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.importagent import Command

        with patch("cogsol.management.commands.importagent.load_dotenv"):
            Command().handle(project_path=tmp_path, assistant_id=1, app="agents")

        out = capsys.readouterr().out
        assert "implantation portal" in out


# ---------------------------------------------------------------------------
# chat Command – credential check
# ---------------------------------------------------------------------------


class TestChatCommandCredentialCheck:
    """chat handle() must show a helpful error and return 1 when no credentials
    are available. chat uses print_error() which writes to stdout with ANSI codes;
    the plain text content must still be present."""

    def test_no_credentials_returns_1(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.chat import Command

        with patch("cogsol.management.commands.chat.load_dotenv"):
            result = Command().handle(project_path=tmp_path, agent="my-agent", app="agents")

        assert result == 1

    def test_no_credentials_prints_helpful_message(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.chat import Command

        with patch("cogsol.management.commands.chat.load_dotenv"):
            Command().handle(project_path=tmp_path, agent="my-agent", app="agents")

        out = capsys.readouterr().out
        assert "No API credentials found" in out
        assert "COGSOL_API_KEY" in out
        assert "https://onboarding.cogsol.ai" in out

    def test_no_credentials_prints_implantation_portal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("COGSOL_API_KEY", raising=False)
        monkeypatch.delenv("COGSOL_AUTH_CLIENT_ID", raising=False)
        (tmp_path / ".env").write_text("")

        from cogsol.management.commands.chat import Command

        with patch("cogsol.management.commands.chat.load_dotenv"):
            Command().handle(project_path=tmp_path, agent="my-agent", app="agents")

        out = capsys.readouterr().out
        assert "implantation portal" in out
