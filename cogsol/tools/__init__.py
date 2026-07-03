"""
Base classes for CogSol tools.
They are intentionally lightweight: enough to be instantiated and inspected.
"""

from __future__ import annotations

from typing import Any


class BaseTool:
    name: str | None = None
    description: str | None = None
    parameters: dict[str, Any] | None = None

    def __init__(self, name: str | None = None, description: str | None = None):
        if name:
            self.name = name
        if description:
            self.description = description
        if not getattr(self, "name", None):
            # Derive name from class (strip 'Tool' suffix if present)
            cls_name = self.__class__.__name__
            self.name = cls_name[:-4] if cls_name.endswith("Tool") else cls_name
        # Avoid sharing mutable metadata across subclasses/instances.
        self.parameters = dict(getattr(self, "parameters", {}) or {})

    def run(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - placeholder
        raise NotImplementedError("Tool execution is not implemented in the CLI framework.")

    def __repr__(self) -> str:
        return f"<Tool {self.name or self.__class__.__name__}>"


class BaseLesson:
    name: str | None = None
    content: str | None = None

    def __repr__(self) -> str:
        return f"<Lesson {self.name or self.__class__.__name__}>"


class BaseFAQ:
    question: str | None = None
    answer: str | None = None

    def __repr__(self) -> str:
        return f"<FAQ {self.question or self.__class__.__name__}>"


class BaseFixedResponse:
    key: str | None = None
    response: str | None = None

    def __repr__(self) -> str:
        return f"<FixedResponse {self.key or self.__class__.__name__}>"


class BaseRetrievalTool:
    name: str | None = None
    description: str | None = None
    parameters: list[dict[str, Any]] | None = None
    retrieval: str | None = None
    show_tool_message: bool = False
    show_assistant_message: bool = False
    edit_available: bool = True
    answer: bool = True
    # Metadata filters assigned to this search. Entries can be metadata config
    # names ("author"), topic-qualified names ("product_docs/author"), or
    # BaseMetadataConfig subclasses. They are resolved to Cognitive filter
    # definitions on migrate.
    filters: list[Any] | None = None

    def __init__(self, name: str | None = None, description: str | None = None):
        if name:
            self.name = name
        if description:
            self.description = description
        if not getattr(self, "name", None):
            cls_name = self.__class__.__name__
            self.name = cls_name[:-4] if cls_name.endswith("Tool") else cls_name
        # Avoid sharing mutable metadata across subclasses/instances.
        self.parameters = list(getattr(self, "parameters", []) or [])
        self.filters = list(getattr(self, "filters", []) or [])

    def __repr__(self) -> str:
        return f"<RetrievalTool {self.name or self.__class__.__name__}>"


class BaseMCPServer:
    """Base class for MCP server definitions.

    Subclass this to register an MCP server in your project.
    URL, header values and OAuth credentials should be read from environment
    variables (stored in .env) for security.

    ``auth_type`` controls how the server authenticates:
      - ``"none"``    – no authentication
      - ``"headers"`` – static headers (e.g. API keys)  **default**
      - ``"oauth2"``  – OAuth 2.1 / PKCE flow managed by the cognitive backend

    For OAuth 2.1, ``oauth_client_id`` and ``oauth_scopes`` are optional —
    cogsol supports Dynamic Client Registration (RFC 7591) when they are
    not provided.  The client secret is **never** stored as a class attribute;
    it is supplied interactively by ``addmcptools`` and sent write-only to the
    API (stored in Azure Key Vault by the backend).
    """

    name: str | None = None
    description: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    protocol_version: str = "2025-03-26"
    client_name: str = "cognitive-mcp-client"
    client_version: str = "1.0.0"
    active: bool = True

    # Authentication
    auth_type: str = "headers"  # "none" | "headers" | "oauth2"

    # OAuth 2.1 (only meaningful when auth_type == "oauth2")
    oauth_client_id: str | None = None  # Optional; DCR fills it when omitted
    oauth_scopes: str | None = None  # Space-separated scopes, e.g. "read:jira"
    # NOTE: oauth_client_secret is intentionally NOT declared here — it is
    # never stored in source code; addmcptools prompts for it and sends it
    # write-only to the CogSol API (Azure Key Vault).

    def __init__(self, name: str | None = None):
        if name:
            self.name = name
        if not getattr(self, "name", None):
            cls_name = self.__class__.__name__
            self.name = cls_name[:-9] if cls_name.endswith("MCPServer") else cls_name
        # Avoid sharing mutable headers across subclasses/instances.
        self.headers = dict(getattr(self, "headers", {}) or {})

    def __repr__(self) -> str:
        return f"<MCPServer {self.name or self.__class__.__name__}>"


class BaseMCPTool:
    """Base class for MCP tool definitions.

    Subclass this to register an MCP tool selected from an MCP server.
    The ``server`` attribute should reference the BaseMCPServer subclass.
    """

    name: str | None = None
    description: str | None = None
    server: type | None = None  # Reference to a BaseMCPServer subclass
    show_tool_message: bool = False
    show_assistant_message: bool = False
    edit_available: bool = True

    def __init__(self, name: str | None = None):
        if name:
            self.name = name
        if not getattr(self, "name", None):
            cls_name = self.__class__.__name__
            self.name = cls_name[:-7] if cls_name.endswith("MCPTool") else cls_name

    def __repr__(self) -> str:
        return f"<MCPTool {self.name or self.__class__.__name__}>"


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
    "BaseMCPServer",
    "BaseMCPTool",
    "tool_params",
]
