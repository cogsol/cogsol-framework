"""
Agent abstractions and lightweight configuration helpers.
The goal is to provide enough structure for code introspection and
file-based migrations without imposing a full runtime.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv


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

    def __init__(
        self,
        *,
        assistant_id: Optional[int] = None,
        chat_id: Optional[int] = None,
        api_base: Optional[str] = None,
        api_token: Optional[str] = None,
        project_path: Optional[Path] = None,
    ) -> None:
        self._assistant_id = assistant_id
        self._chat_id = chat_id
        self._api_base = api_base
        self._api_token = api_token
        self._project_path = project_path

    def reset(self) -> None:
        """Forget the current chat session so the next run starts a new chat."""
        self._chat_id = None

    def run(
        self,
        message: str,
        *,
        reset: bool = False,
        assistant_id: Optional[int] = None,
        api_base: Optional[str] = None,
        api_token: Optional[str] = None,
        project_path: Optional[Path] = None,
        async_mode: bool = False,
        streaming: bool = False,
        **params: Any,
    ) -> Any:
        """
        Send a message to the CogSol API. The first call creates a chat and stores its id.
        Subsequent calls reuse the same chat id unless reset=True or reset() is called.
        """
        if not message:
            raise ValueError("message is required")
        if reset:
            self.reset()

        project_path = self._resolve_project_path(project_path)
        if project_path is None:
            project_path = Path.cwd()
        load_dotenv(project_path / ".env")

        base_url = api_base or self._api_base or os.environ.get("COGSOL_API_BASE")
        if not base_url:
            raise CogSolAPIError("COGSOL_API_BASE is required to run agents.")
        token = api_token or self._api_token or os.environ.get("COGSOL_API_TOKEN")

        assistant_id = assistant_id or self._assistant_id
        if assistant_id is None:
            assistant_id = self._resolve_assistant_id(project_path)
        if assistant_id is None:
            raise CogSolAPIError(
                "Could not resolve assistant id. Run migrate or pass assistant_id explicitly."
            )
        self._assistant_id = assistant_id

        payload = {"message": message}
        for key, value in params.items():
            if value is None or key == "message":
                continue
            payload[key] = self._normalize_payload_value(value)

        client = CogSolClient(base_url, token=token)
        if self._chat_id is None:
            chat = client.create_chat(
                assistant_id,
                payload=payload,
                async_mode=async_mode,
                streaming=streaming,
            )
            chat_id = self._chat_id_from_response(chat)
            if chat_id is None:
                raise CogSolAPIError(f"Chat response did not include an id: {chat}")
            self._chat_id = chat_id
            return chat

        return client.send_message(
            self._chat_id,
            payload=payload,
            async_mode=async_mode,
            streaming=streaming,
        )

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

    def _resolve_project_path(self, project_path: Optional[Path]) -> Optional[Path]:
        if project_path is not None:
            return project_path
        if self._project_path is not None:
            return self._project_path
        module = sys.modules.get(self.__class__.__module__)
        module_path = getattr(module, "__file__", None)
        if module_path:
            path = Path(module_path).resolve()
            for parent in path.parents:
                if parent.name == "agents":
                    return parent.parent
        return None

    def _resolve_assistant_id(self, project_path: Optional[Path]) -> Optional[int]:
        if project_path is None:
            project_path = Path.cwd()
        state_path = project_path / "agents" / "migrations" / ".state.json"
        if not state_path.exists():
            return None
        try:
            import json

            data = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        remote = data.get("remote") if isinstance(data, dict) else None
        if not isinstance(remote, dict):
            return None
        agent_key = self.__class__.__name__
        value = remote.get("agents", {}).get(agent_key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None

    def _chat_id_from_response(self, chat_obj: Any) -> Optional[int]:
        if isinstance(chat_obj, dict):
            value = chat_obj.get("id")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def _normalize_payload_value(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (list, tuple)):
            return [self._normalize_payload_value(item) for item in value]
        if isinstance(value, dict):
            return {key: self._normalize_payload_value(val) for key, val in value.items()}
        return value


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
