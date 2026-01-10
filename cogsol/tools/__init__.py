"""
Base classes for CogSol tools.
They are intentionally lightweight: enough to be instantiated and inspected.
"""

from __future__ import annotations

from typing import Any, Optional


class BaseTool:
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: dict[str, Any] = {}

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        if name:
            self.name = name
        if description:
            self.description = description
        if not getattr(self, "name", None):
            # Derive name from class (strip 'Tool' suffix if present)
            cls_name = self.__class__.__name__
            self.name = cls_name[:-4] if cls_name.endswith("Tool") else cls_name

    def run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - placeholder
        raise NotImplementedError("Tool execution is not implemented in the CLI framework.")

    def __repr__(self) -> str:
        return f"<Tool {self.name or self.__class__.__name__}>"


class BaseLesson:
    name: Optional[str] = None
    content: Optional[str] = None

    def __repr__(self) -> str:
        return f"<Lesson {self.name or self.__class__.__name__}>"


class BaseFAQ:
    question: Optional[str] = None
    answer: Optional[str] = None

    def __repr__(self) -> str:
        return f"<FAQ {self.question or self.__class__.__name__}>"


class BaseFixedResponse:
    key: Optional[str] = None
    response: Optional[str] = None

    def __repr__(self) -> str:
        return f"<FixedResponse {self.key or self.__class__.__name__}>"


class BaseRetrievalTool:
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: list[dict[str, Any]] = []
    retrieval: Optional[str] = None
    show_tool_message: bool = False
    show_assistant_message: bool = False
    edit_available: bool = True
    answer: bool = True

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        if name:
            self.name = name
        if description:
            self.description = description
        if not getattr(self, "name", None):
            cls_name = self.__class__.__name__
            self.name = cls_name[:-4] if cls_name.endswith("Tool") else cls_name

    def __repr__(self) -> str:
        return f"<RetrievalTool {self.name or self.__class__.__name__}>"


def tool_params(**params: dict[str, Any]):
    """
    Decorator to attach parameter metadata to a tool's run method.
    Example:
        @tool_params(
            text={"description": "Text to echo", "type": "string", "required": True},
            count={"description": "Times to repeat", "type": "integer", "required": False},
        )
        def run(self, chat=None, data=None, secrets=None, log=None, text="", count=1):
            ...
    """

    def decorator(func):
        func.__tool_params__ = params
        return func

    return decorator


__all__ = [
    "BaseTool",
    "BaseLesson",
    "BaseFAQ",
    "BaseFixedResponse",
    "BaseRetrievalTool",
    "tool_params",
]
