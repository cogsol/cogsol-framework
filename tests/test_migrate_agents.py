"""
Tests for the assistant payload built during migrations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cogsol.agents import BaseAgent, attachment, optimizations
from cogsol.core.api import CogSolAPIError
from cogsol.core.loader import serialize_value
from cogsol.management.commands.importagent import (
    _attachment_source,
    _attachment_specs_from_config,
    _attachment_state,
)
from cogsol.management.commands.migrate import Command

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS = "application/vnd.ms-excel"


def _payload(cls: type | None = None, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an assistant payload from a live class, a state dict, or both."""
    return Command()._assistant_payload(
        agent_name=getattr(cls, "__name__", "DemoAgent"),
        definition={"fields": fields or {}, "meta": {}},
        cls=cls,
        remote_ids={},
        project_path=Path("."),
        app="agents",
    )


class TestOptionalFieldsAreOnlySentWhenDeclared:
    def test_undeclared_optional_fields_are_absent(self) -> None:
        class DemoAgent(BaseAgent):
            temperature = 0.3

        payload = _payload(DemoAgent)

        for key in (
            "add_to_user_message",
            "strategy_to_optimize_tokens",
            "messages_window_to_generator",
            "matrix_mode_available",
            "async_available",
            "attachment_config",
            "reasoning_effort",
            "reasoning_summary",
            "web_search_mode",
            "web_search_allowed_domains",
            "web_search_location",
        ):
            assert key not in payload

    def test_base_agent_defaults_do_not_count_as_declared(self) -> None:
        class DemoAgent(BaseAgent):
            pass

        assert "async_available" not in _payload(DemoAgent)

    def test_declared_values_are_sent(self) -> None:
        class DemoAgent(BaseAgent):
            append_to_user_message = " (be brief)"
            user_interactions_window = 8
            asynchronous = True
            websearch_domains = ["cogsol.ai"]
            websearch_location = {"country": "AR"}

        payload = _payload(DemoAgent)

        assert payload["add_to_user_message"] == " (be brief)"
        assert payload["messages_window_to_generator"] == 8
        assert payload["async_available"] is True
        assert payload["web_search_allowed_domains"] == ["cogsol.ai"]
        assert payload["web_search_location"] == {"country": "AR"}

    def test_declared_none_clears_nullable_field(self) -> None:
        class DemoAgent(BaseAgent):
            append_to_user_message = None

        assert _payload(DemoAgent)["add_to_user_message"] is None

    def test_declared_none_is_skipped_for_non_nullable_field(self) -> None:
        class DemoAgent(BaseAgent):
            user_interactions_window = None

        assert "messages_window_to_generator" not in _payload(DemoAgent)

    def test_state_only_definitions_are_honoured(self) -> None:
        payload = _payload(None, {"asynchronous": True, "user_interactions_window": 4})

        assert payload["async_available"] is True
        assert payload["messages_window_to_generator"] == 4


class TestReasoningAndWebSearchMapping:
    def test_reasoning_uses_the_field_cognitive_exposes(self) -> None:
        class DemoAgent(BaseAgent):
            reasoning = True
            reasoning_effort = "high"
            reasoning_summary = "concise"

        payload = _payload(DemoAgent)

        assert payload["reasoning_enabled"] is True
        assert payload["reasoning_effort"] == "high"
        assert payload["reasoning_summary"] == "concise"
        assert "reasoning_available" not in payload

    def test_websearch_uses_the_field_cognitive_exposes(self) -> None:
        class DemoAgent(BaseAgent):
            websearch = True
            websearch_mode = "deep_research"

        payload = _payload(DemoAgent)

        assert payload["web_search_enabled"] is True
        assert payload["web_search_mode"] == "deep_research"
        assert "websearch_available" not in payload

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            ("reasoning_effort", "extreme"),
            ("reasoning_summary", "verbose"),
            ("websearch_mode", "agentic_deep"),
        ],
    )
    def test_invalid_choice_is_rejected(self, attr: str, value: str) -> None:
        cls = type("DemoAgent", (BaseAgent,), {attr: value})

        with pytest.raises(CogSolAPIError, match="Valid values"):
            _payload(cls)

    def test_websearch_domains_must_be_a_list(self) -> None:
        class DemoAgent(BaseAgent):
            websearch_domains = "cogsol.ai"

        with pytest.raises(CogSolAPIError, match="must be a list of domains"):
            _payload(DemoAgent)

    def test_websearch_location_must_be_a_dict(self) -> None:
        class DemoAgent(BaseAgent):
            websearch_location = "AR"

        with pytest.raises(CogSolAPIError, match="websearch_location must be a dict"):
            _payload(DemoAgent)


class TestSelfImprovementMode:
    def test_realtime_does_not_enable_matrix_mode(self) -> None:
        class DemoAgent(BaseAgent):
            realtime = True

        payload = _payload(DemoAgent)

        assert payload["realtime_available"] is True
        assert "matrix_mode_available" not in payload

    def test_self_improvement_mode_requires_faqs(self) -> None:
        class DemoAgent(BaseAgent):
            self_improvement_mode = True

        with pytest.raises(CogSolAPIError, match="declares no FAQs"):
            _payload(DemoAgent)

    def test_self_improvement_mode_with_faqs(self) -> None:
        class DemoAgent(BaseAgent):
            self_improvement_mode = True
            faqs = [object()]

        payload = _payload(DemoAgent)

        assert payload["matrix_mode_available"] is True
        assert payload["faq_available"] is True


class TestTokenOptimization:
    def test_strategy_is_sent_when_declared(self) -> None:
        class DemoAgent(BaseAgent):
            token_optimization = optimizations.SkipAllContent()

        assert _payload(DemoAgent)["strategy_to_optimize_tokens"] == "skip_all_content"

    def test_declared_none_falls_back_to_no_optimization(self) -> None:
        class DemoAgent(BaseAgent):
            token_optimization = None

        assert _payload(DemoAgent)["strategy_to_optimize_tokens"] == "no_optimization"

    def test_strategy_from_state(self) -> None:
        payload = _payload(None, {"token_optimization": "description_only"})

        assert payload["strategy_to_optimize_tokens"] == "description_only"


class TestAttachmentConfig:
    def test_specs_become_attachment_config(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [
                attachment.Pdf(send_to_model=True, mode="text"),
                attachment.Image(send_to_model=True),
                attachment.Excel(),
            ]

        config = _payload(DemoAgent)["attachment_config"]

        assert config[PDF] == {"accepted": True, "send_to_model": True, "pdf_mode": "text"}
        assert config[PNG] == {"accepted": True, "send_to_model": True}
        assert config[JPEG] == {"accepted": True, "send_to_model": True}
        assert config[XLSX] == {"accepted": True, "send_to_model": False}
        assert config[XLS] == {"accepted": True, "send_to_model": False}

    def test_pdf_defaults_to_image_mode(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Pdf()]

        assert _payload(DemoAgent)["attachment_config"][PDF]["pdf_mode"] == "image"

    def test_empty_list_clears_the_configuration(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = []

        assert _payload(DemoAgent)["attachment_config"] == {}

    def test_migrated_state_matches_live_specs(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Pdf(send_to_model=True, mode="text"), attachment.Text()]

        from_class = _payload(DemoAgent)["attachment_config"]
        from_state = _payload(None, {"attachments": serialize_value(DemoAgent.attachments)})[
            "attachment_config"
        ]

        assert from_class == from_state

    def test_custom_accepts_extra_content_types(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Custom(content_types=(XLS,), send_to_model=True)]

        assert _payload(DemoAgent)["attachment_config"] == {
            XLS: {"accepted": True, "send_to_model": True}
        }

    def test_unsupported_content_type_is_rejected(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Custom(content_types=("audio/mpeg",))]

        with pytest.raises(CogSolAPIError, match="Unsupported attachment content type"):
            _payload(DemoAgent)

    def test_duplicated_content_type_is_rejected(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Text(), attachment.Custom(content_types=("text/plain",))]

        with pytest.raises(CogSolAPIError, match="configured twice"):
            _payload(DemoAgent)

    def test_invalid_pdf_mode_is_rejected(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Pdf(mode="binary")]

        with pytest.raises(CogSolAPIError, match="Invalid attachment mode"):
            _payload(DemoAgent)

    def test_send_to_model_without_accepted_is_rejected(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Image(accepted=False, send_to_model=True)]

        with pytest.raises(CogSolAPIError, match="never reaches the model"):
            _payload(DemoAgent)

    def test_spec_without_content_types_is_rejected(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = [attachment.Custom()]

        with pytest.raises(CogSolAPIError, match="at least one content type"):
            _payload(DemoAgent)

    def test_attachments_must_be_a_list(self) -> None:
        class DemoAgent(BaseAgent):
            attachments = attachment.Pdf()

        with pytest.raises(CogSolAPIError, match="attachments must be a list"):
            _payload(DemoAgent)


class TestAttachmentConfigImport:
    def test_named_groups_are_reconstructed(self) -> None:
        specs = _attachment_specs_from_config(
            {
                PDF: {"accepted": True, "send_to_model": True, "pdf_mode": "text"},
                PNG: {"accepted": True, "send_to_model": True},
                JPEG: {"accepted": True, "send_to_model": True},
            }
        )

        assert [name for name, _, _ in specs] == ["Image", "Pdf"]
        assert "attachment.Pdf(accepted=True, send_to_model=True, mode='text')" in (
            _attachment_source(specs)
        )

    def test_leftover_types_become_custom(self) -> None:
        specs = _attachment_specs_from_config({XLS: {"accepted": True, "send_to_model": False}})

        assert [name for name, _, _ in specs] == ["Custom"]

    def test_generated_source_matches_generated_state(self) -> None:
        specs = _attachment_specs_from_config(
            {
                PDF: {"accepted": True, "send_to_model": True, "pdf_mode": "image"},
                "text/plain": {"accepted": True, "send_to_model": False},
            }
        )
        source = _attachment_source(specs).replace("    attachments", "attachments", 1)
        namespace: dict[str, Any] = {"attachment": attachment}
        exec(source, namespace)

        assert serialize_value(namespace["attachments"]) == _attachment_state(specs)

    def test_empty_config_produces_no_specs(self) -> None:
        assert _attachment_specs_from_config(None) == []
        assert _attachment_specs_from_config({}) == []
        assert _attachment_source([]) == ""

    def test_round_trip_through_the_payload_builder(self) -> None:
        config = {
            PDF: {"accepted": True, "send_to_model": True, "pdf_mode": "text"},
            PNG: {"accepted": True, "send_to_model": False},
            JPEG: {"accepted": True, "send_to_model": False},
        }
        specs = _attachment_specs_from_config(config)

        payload = _payload(None, {"attachments": _attachment_state(specs)})

        assert payload["attachment_config"] == config
