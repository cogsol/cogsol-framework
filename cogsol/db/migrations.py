"""
Lightweight migration primitives used by the CogSol CLI.
They operate over an in-memory state dictionary and persist to disk
via the management commands (no external database required).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Optional, cast


class Migration:
    """Base migration class mirrored in generated migration files."""

    initial: bool = False
    dependencies: list[Any] = []
    operations: list[Any] = []


def _ensure_bucket(state: dict[str, Any], entity: str) -> dict[str, Any]:
    state.setdefault(entity, {})
    return cast(dict[str, Any], state[entity])


@dataclass
class CreateDefinition:
    name: str
    fields: dict[str, Any]
    meta: Optional[dict[str, Any]] = None
    entity: str = field(default="agents")

    def apply(self, state: dict[str, Any]) -> None:
        bucket = _ensure_bucket(state, self.entity)
        bucket[self.name] = {"fields": self.fields, "meta": self.meta or {}}

    def __repr__(self) -> str:  # pragma: no cover - used for file generation
        meta_repr = f", meta={self.meta!r}" if self.meta else ""
        return (
            f"{self.__class__.__name__}(name={self.name!r}, " f"fields={self.fields!r}{meta_repr})"
        )


class CreateAgent(CreateDefinition):
    def __init__(
        self, name: str, fields: dict[str, Any], meta: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(name=name, fields=fields, meta=meta, entity="agents")


class CreateTool(CreateDefinition):
    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="tools")


class CreateRetrievalTool(CreateDefinition):
    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="retrieval_tools")


class CreateLesson(CreateDefinition):
    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="lessons")


class CreateFAQ(CreateDefinition):
    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="faqs")


class CreateFixedResponse(CreateDefinition):
    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="fixed_responses")


# =============================================================================
# Content API entities (data/ folder)
# =============================================================================


class CreateTopic(CreateDefinition):
    """Creates a Topic (Node) in the Content API."""

    def __init__(
        self, name: str, fields: dict[str, Any], meta: Optional[dict[str, Any]] = None
    ) -> None:
        super().__init__(name=name, fields=fields, meta=meta, entity="topics")


class CreateMetadataConfig(CreateDefinition):
    """Creates a Metadata Configuration for a Topic."""

    topic: str = ""

    def __init__(self, name: str, fields: dict[str, Any], topic: str = "") -> None:
        super().__init__(name=name, fields=fields, entity="metadata_configs")
        self.topic = topic

    def apply(self, state: dict[str, Any]) -> None:
        bucket = _ensure_bucket(state, self.entity)
        bucket[self.name] = {"fields": self.fields, "meta": {}, "topic": self.topic}

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"fields={self.fields!r}, topic={self.topic!r})"
        )


class CreateReferenceFormatter(CreateDefinition):
    """Creates a Reference Formatter in the Content API."""

    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="formatters")


class CreateIngestionConfig(CreateDefinition):
    """Creates an Ingestion Configuration for document processing."""

    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="ingestion_configs")


class CreateRetrieval(CreateDefinition):
    """Creates a Retrieval configuration in the Content API."""

    def __init__(self, name: str, fields: dict[str, Any]) -> None:
        super().__init__(name=name, fields=fields, entity="retrievals")


@dataclass
class AlterField:
    model_name: str
    name: str
    value: Any
    entity: str = "agents"
    scope: str = "fields"

    def apply(self, state: dict[str, Any]) -> None:
        bucket = _ensure_bucket(state, self.entity)
        definition = bucket.setdefault(self.model_name, {"fields": {}, "meta": {}})
        definition.setdefault("fields", {})
        definition.setdefault("meta", {})
        target = definition["fields"] if self.scope == "fields" else definition["meta"]
        target[self.name] = self.value

    def __repr__(self) -> str:  # pragma: no cover - used for file generation
        return (
            f"{self.__class__.__name__}(model_name={self.model_name!r}, "
            f"name={self.name!r}, value={self.value!r}, "
            f"entity={self.entity!r}, scope={self.scope!r})"
        )


@dataclass
class DeleteDefinition:
    name: str
    entity: str = "agents"

    def apply(self, state: dict[str, Any]) -> None:
        bucket = _ensure_bucket(state, self.entity)
        bucket.pop(self.name, None)

    def __repr__(self) -> str:  # pragma: no cover - used for file generation
        return f"{self.__class__.__name__}(name={self.name!r}, entity={self.entity!r})"


def apply_operations(state: dict[str, Any], operations: Iterable[Any]) -> dict[str, Any]:
    """
    Apply migration operations to the given state dictionary.
    Operations are expected to expose an ``apply`` method.
    """
    for op in operations:
        apply = getattr(op, "apply", None)
        if apply is None:
            raise TypeError(f"Operation {op} has no apply()")
        apply(state)
    return state
