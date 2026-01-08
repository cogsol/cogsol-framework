"""
Agent abstractions and lightweight configuration helpers.
The goal is to provide enough structure for code introspection and
file-based migrations without imposing a full runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


class BaseAgent:
    """
    Minimal base class for CogSol agents.
    Subclasses typically override class attributes to define behaviour.
    """

    system_prompt: Any = None
    initial_message: Optional[str] = None
    forced_termination_message: Optional[str] = None
    no_information_message: Optional[str] = None
    pregeneration_config: Any = None
    generation_config: Any = None
    pretools: list[Any] = []
    tools: list[Any] = []
    temperature: Optional[float] = None
    max_interactions: Optional[int] = None
    user_message_length: Optional[int] = None
    consecutive_tool_calls_limit: Optional[int] = None
    user_interactions_window: Optional[int] = None
    token_optimization: Any = None
    streaming: bool = False
    self_improvement_mode: bool = False
    realtime: bool = False
    lessons: list[Any] = []
    faqs: list[Any] = []
    fixed_responses: list[Any] = []

    class Meta:
        name: Optional[str] = None
        chat_name: Optional[str] = None
        logo_url: Optional[str] = None
        assistant_name_color: Optional[str] = None
        primary_color: Optional[str] = None
        secondary_color: Optional[str] = None
        border_color: Optional[str] = None

    @classmethod
    def definition(cls) -> dict[str, Any]:
        """Helper used by migration tooling to capture class attributes."""
        return {
            "fields": {
                key: value
                for key, value in cls.__dict__.items()
                if not key.startswith("_") and key not in {"Meta", "__module__", "__doc__"}
            },
            "meta": {
                key: value
                for key, value in getattr(cls, "Meta", {}).__dict__.items()
                if not key.startswith("_")
            },
        }


@dataclass
class _ConfigBase:
    """Base dataclass for configuration helpers."""

    name: str

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


# Generation configuration stubs
class genconfigs:
    class QA(_ConfigBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__("qa")
            self.params = kwargs

    class FastRetrieval(_ConfigBase):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__("fast_retrieval")
            self.params = kwargs


class optimizations:
    class DescriptionOnly(_ConfigBase):
        def __init__(self) -> None:
            super().__init__("description_only")


__all__ = ["BaseAgent", "genconfigs", "optimizations"]
