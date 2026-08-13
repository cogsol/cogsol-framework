"""
Tests for importing an existing assistant back into a project.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from cogsol.core.loader import collect_definitions
from cogsol.management.commands import importagent
from cogsol.management.commands.importagent import Command
from cogsol.management.commands.migrate import Command as MigrateCommand

ASSISTANT: dict[str, Any] = {
    "id": 42,
    "description": "Support",
    "info": "Soporte",
    "system_prompt": "You are support.",
    "generation_config": "QA",
    "generation_config_pretools": "QA",
    "temperature": 0.3,
    "max_responses": 5,
    "max_msg_length": 2048,
    "max_consecutive_tool_calls": 3,
    "messages_window_to_generator": 12,
    "initial_message": "Hello!",
    "end_message": "Goodbye.",
    "not_info_message": "I don't have that information.",
    "add_to_user_message": " (be brief)",
    "strategy_to_optimize_tokens": "description_only",
    "streaming_available": True,
    "realtime_available": False,
    "async_available": True,
    "matrix_mode_available": True,
    "reasoning_enabled": True,
    "reasoning_effort": "high",
    "reasoning_summary": "concise",
    "web_search_enabled": True,
    "web_search_mode": "agentic",
    "web_search_allowed_domains": ["cogsol.ai"],
    "web_search_location": {"country": "AR", "city": "Buenos Aires"},
    "attachment_config": {
        "application/pdf": {"accepted": True, "send_to_model": True, "pdf_mode": "text"},
        "image/png": {"accepted": True, "send_to_model": True},
        "image/jpeg": {"accepted": True, "send_to_model": True},
        "text/plain": {"accepted": True, "send_to_model": False},
    },
    "colors": {"primaryColor": "#1A3C5E"},
    "logo": "https://example.test/logo.png",
    "tools": [],
    "pretools": [],
}


class _StubClient:
    """Stands in for CogSolClient, serving a single assistant with no tools."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def get_assistant(self, assistant_id: int) -> dict[str, Any]:
        return dict(ASSISTANT)

    def list_common_questions(self, assistant_id: int) -> list[dict[str, Any]]:
        return [{"id": 1, "name": "How do I start?", "content": "Just ask."}]

    def list_fixed_responses(self, assistant_id: int) -> list[dict[str, Any]]:
        return []

    def list_lessons(self, assistant_id: int) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def imported_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run importagent against the stub client and return the project path."""
    monkeypatch.setattr(importagent, "CogSolClient", _StubClient)
    monkeypatch.setattr(Command, "ensure_credentials_configured", lambda self, path: True)

    agents = tmp_path / "agents"
    (agents / "migrations").mkdir(parents=True)
    (agents / "__init__.py").write_text("", encoding="utf-8")
    (agents / "tools.py").write_text("", encoding="utf-8")
    (agents / "migrations" / "__init__.py").write_text("", encoding="utf-8")

    assert Command().handle(project_path=tmp_path, assistant_id=42, app="agents") == 0
    return tmp_path


class TestImportedAgentSource:
    def test_generated_agent_is_valid_python(self, imported_project: Path) -> None:
        source = (imported_project / "agents" / "support" / "agent.py").read_text(encoding="utf-8")

        ast.parse(source)

    def test_imports_only_the_namespaces_it_uses(self, imported_project: Path) -> None:
        source = (imported_project / "agents" / "support" / "agent.py").read_text(encoding="utf-8")

        assert "attachment" in source.splitlines()[0]
        assert "optimizations" in source.splitlines()[0]

    def test_declares_the_optional_configuration(self, imported_project: Path) -> None:
        source = (imported_project / "agents" / "support" / "agent.py").read_text(encoding="utf-8")

        for expected in (
            "streaming = True",
            "asynchronous = True",
            "self_improvement_mode = True",
            "reasoning = True",
            "reasoning_effort = 'high'",
            "reasoning_summary = 'concise'",
            "websearch = True",
            "websearch_mode = 'agentic'",
            "websearch_domains = ['cogsol.ai']",
            "append_to_user_message = ' (be brief)'",
            "user_interactions_window = 12",
            "token_optimization = optimizations.DescriptionOnly()",
            "attachment.Pdf(accepted=True, send_to_model=True, mode='text')",
            "attachment.Image(accepted=True, send_to_model=True)",
        ):
            assert expected in source

    def test_does_not_declare_disabled_features(self, imported_project: Path) -> None:
        source = (imported_project / "agents" / "support" / "agent.py").read_text(encoding="utf-8")

        assert "realtime" not in source


class TestImportedAgentRoundTrip:
    """A migrate of the imported project must reproduce the assistant it came from."""

    def _payload(self, project_path: Path) -> dict[str, Any]:
        definitions = collect_definitions(project_path, "agents")
        return MigrateCommand()._assistant_payload(
            agent_name="SupportAgent",
            definition=definitions["agents"]["SupportAgent"],
            cls=None,
            remote_ids={},
            project_path=project_path,
            app="agents",
            slug="support",
        )

    @pytest.mark.parametrize(
        "field",
        [
            "attachment_config",
            "reasoning_enabled",
            "reasoning_effort",
            "reasoning_summary",
            "web_search_enabled",
            "web_search_mode",
            "web_search_allowed_domains",
            "web_search_location",
            "async_available",
            "matrix_mode_available",
            "add_to_user_message",
            "messages_window_to_generator",
            "strategy_to_optimize_tokens",
            "streaming_available",
        ],
    )
    def test_field_survives_the_round_trip(self, imported_project: Path, field: str) -> None:
        payload = self._payload(imported_project)

        assert payload[field] == ASSISTANT[field]

    def test_undeclared_features_stay_out_of_the_payload(self, imported_project: Path) -> None:
        payload = self._payload(imported_project)

        assert payload["realtime_available"] is False
