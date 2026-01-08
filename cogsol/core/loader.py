"""
Utilities to import project modules and collect agent definitions.
"""

from __future__ import annotations

import importlib
import inspect
import sys
import textwrap
from pathlib import Path
from typing import Any, Union, cast

from typing_extensions import TypeAlias

from cogsol.agents import BaseAgent, _ConfigBase
from cogsol.prompts import Prompt
from cogsol.tools import (
    BaseFAQ,
    BaseFixedResponse,
    BaseLesson,
    BaseTool,
)


def _normalize_code(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.replace("\r\n", "\n").rstrip()
    return textwrap.dedent(text).rstrip()


def serialize_value(value: Any) -> Any:
    """
    Convert runtime objects into simple, comparable representations
    that can be written into migration files.
    """
    from dataclasses import asdict, is_dataclass

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Prompt):
        return value.path
    if isinstance(value, _ConfigBase):
        if str(value.name).lower() == "qa":
            return "QA"
        return value.name
    if isinstance(value, str) and value.startswith("def run"):
        return _normalize_code(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (BaseTool, BaseLesson, BaseFAQ, BaseFixedResponse)):
        return (
            getattr(value, "name", None) or getattr(value, "key", None) or value.__class__.__name__
        )
    if is_dataclass(value) and not isinstance(value, type):
        data = asdict(value)
        extras = {k: v for k, v in value.__dict__.items() if k not in data}
        if extras:
            data["__extra__"] = serialize_value(extras)
        return serialize_value(data)
    if hasattr(value, "__class__") and value.__class__.__module__ != "builtins":
        label = getattr(value, "name", None) or getattr(value, "key", None)
        return label or value.__class__.__name__
    return repr(value)


def _import_module(module_name: str, project_path: Path):
    sys.path.insert(0, str(project_path))
    try:
        importlib.invalidate_caches()
        return importlib.import_module(module_name)
    finally:
        try:
            sys.path.remove(str(project_path))
        except ValueError:
            pass


def _extract_class_fields(cls: type) -> tuple[dict[str, Any], dict[str, Any]]:
    fields: dict[str, Any] = {}
    for key, value in cls.__dict__.items():
        if key.startswith("_") or key in {"Meta", "__module__", "__doc__"}:
            continue
        if inspect.isfunction(value) or inspect.ismethoddescriptor(value) or inspect.isclass(value):
            continue
        fields[key] = serialize_value(value)

    meta: dict[str, Any] = {}
    meta_obj = getattr(cls, "Meta", None)
    if meta_obj:
        for key, value in meta_obj.__dict__.items():
            if (
                key.startswith("_")
                or inspect.isfunction(value)
                or inspect.ismethoddescriptor(value)
            ):
                continue
            meta[key] = serialize_value(value)
    return fields, meta


def _extract_tool_params(tool_cls: type[BaseTool]) -> dict[str, Any]:
    """
    Build parameter metadata for tools from run() signature, decorator or docstring.
    Returns a dict keyed by param name with description/type/required.
    """
    IGNORE = {"self", "chat", "data", "secrets", "log", "params"}
    params: dict[str, Any] = {}
    try:
        run_fn = tool_cls.run
    except AttributeError:
        return params

    sig = inspect.signature(run_fn)
    hints = getattr(run_fn, "__annotations__", {})
    decorator_meta = getattr(run_fn, "__tool_params__", {})
    doc = inspect.getdoc(run_fn) or ""
    doc_lines = {
        line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip()
        for line in doc.splitlines()
        if ":" in line
    }

    for name, param in sig.parameters.items():
        if name in IGNORE:
            continue
        meta = decorator_meta.get(name, {}) if isinstance(decorator_meta, dict) else {}
        desc = meta.get("description") or doc_lines.get(name) or name
        typ = meta.get("type")
        if not typ:
            hint = hints.get(name)
            typ = getattr(hint, "__name__", None) if hasattr(hint, "__name__") else None
            if typ is None and hint:
                typ = str(hint)
            typ = typ or "string"
        required = meta.get("required")
        if required is None:
            required = param.default is inspect._empty
        params[name] = {"description": desc, "type": typ, "required": bool(required)}
    return params


def collect_definitions(
    project_path: Path, app_name: str = "agents"
) -> dict[str, dict[str, dict[str, Any]]]:
    """
    Import project modules and return a structured definition map.
    Supports per-agent packages under agents/<slug>/agent.py and global tools.
    """
    app_path = project_path / app_name
    if not app_path.exists():
        raise FileNotFoundError(f"App '{app_name}' not found at {app_path}")

    definitions: dict[str, dict[str, dict[str, Any]]] = {
        "agents": {},
        "tools": {},
    }

    # Tools (global, reusable)
    try:
        tool_module = _import_module(f"{app_name}.tools", project_path)
        for _, obj in inspect.getmembers(tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseTool)
                and obj is not BaseTool
                and obj.__module__ == tool_module.__name__
            ):
                fields, meta = _extract_class_fields(obj)
                normalized = _tool_key_from_class(obj)
                current_name = fields.get("name")
                if not current_name or current_name == obj.__name__:
                    fields["name"] = normalized
                fields["parameters"] = _extract_tool_params(obj)
                code_repr = ""
                try:
                    run_fn = obj.run
                    code_repr = textwrap.dedent(inspect.getsource(run_fn))
                except Exception:
                    code_repr = ""
                fields["__code__"] = _normalize_code(code_repr)
                definitions["tools"][normalized] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError:
        pass

    # Per-agent packages (agents/<slug>/agent.py)
    for sub in sorted(app_path.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in {"migrations", "__pycache__", "prompts"}:
            continue
        agent_module_path = f"{app_name}.{sub.name}.agent"
        try:
            agent_module = _import_module(agent_module_path, project_path)
        except ModuleNotFoundError:
            continue

        for _, obj in inspect.getmembers(agent_module, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != agent_module.__name__:
                continue
            _attach_related(obj, project_path, app_name, sub.name)
            fields, meta = _extract_class_fields(obj)
            if not getattr(obj, "name", None):
                fields["name"] = (
                    obj.__name__[:-5] if obj.__name__.endswith("Agent") else obj.__name__
                )
            fields["faqs"] = _serialize_related_list(getattr(obj, "faqs", []))
            fields["fixed_responses"] = _serialize_related_list(getattr(obj, "fixed_responses", []))
            fields["lessons"] = _serialize_related_list(getattr(obj, "lessons", []))
            definitions["agents"][obj.__name__] = {"fields": fields, "meta": meta}

    # Fallback: legacy single module agents.py
    try:
        legacy_agents = _import_module(f"{app_name}.agents", project_path)
        for _, obj in inspect.getmembers(legacy_agents, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != legacy_agents.__name__:
                continue
            fields, meta = _extract_class_fields(obj)
            fields["faqs"] = _serialize_related_list(getattr(obj, "faqs", []))
            fields["fixed_responses"] = _serialize_related_list(getattr(obj, "fixed_responses", []))
            fields["lessons"] = _serialize_related_list(getattr(obj, "lessons", []))
            definitions["agents"][obj.__name__] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError:
        pass

    return definitions


def collect_classes(project_path: Path, app_name: str = "agents") -> dict[str, dict[str, type]]:
    """
    Return actual class objects indexed by entity type and name.
    Supports per-agent packages under agents/<slug>/agent.py and global tools.
    """
    app_path = project_path / app_name
    if not app_path.exists():
        raise FileNotFoundError(f"App '{app_name}' not found at {app_path}")

    classes: dict[str, dict[str, type]] = {
        "agents": {},
        "tools": {},
    }

    # Tools
    try:
        tool_module = _import_module(f"{app_name}.tools", project_path)
        for _, obj in inspect.getmembers(tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseTool)
                and obj is not BaseTool
                and obj.__module__ == tool_module.__name__
            ):
                key = _tool_key_from_class(obj)
                classes["tools"][key] = obj
    except ModuleNotFoundError:
        pass

    # Agents per folder
    for sub in sorted(app_path.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in {"migrations", "__pycache__", "prompts"}:
            continue
        agent_module_path = f"{app_name}.{sub.name}.agent"
        try:
            agent_module = _import_module(agent_module_path, project_path)
        except ModuleNotFoundError:
            continue

        for _, obj in inspect.getmembers(agent_module, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != agent_module.__name__:
                continue
            _attach_related(obj, project_path, app_name, sub.name)
            classes["agents"][obj.__name__] = obj

    # Fallback: legacy single module agents.py
    try:
        legacy_agents = _import_module(f"{app_name}.agents", project_path)
        for _, obj in inspect.getmembers(legacy_agents, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != legacy_agents.__name__:
                continue
            classes["agents"][obj.__name__] = obj
    except ModuleNotFoundError:
        pass
    return classes


RelatedItem: TypeAlias = Union[BaseFAQ, BaseFixedResponse, BaseLesson]
RelatedList: TypeAlias = list[RelatedItem]


def _load_related(
    module_name: str,
    project_path: Path,
) -> RelatedList:
    try:
        module = _import_module(module_name, project_path)
    except ModuleNotFoundError:
        return []
    # Preferred: instantiate classes defined in the module
    items: RelatedList = []
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module.__name__:
            continue
        if issubclass(obj, BaseFAQ) and obj is not BaseFAQ:
            items.append(obj())
        if issubclass(obj, BaseFixedResponse) and obj is not BaseFixedResponse:
            items.append(obj())
        if issubclass(obj, BaseLesson) and obj is not BaseLesson:
            items.append(obj())
    if items:
        return items
    # Fallbacks
    if hasattr(module, "get_faqs"):
        return cast(RelatedList, module.get_faqs())
    if hasattr(module, "get_fixed"):
        return cast(RelatedList, module.get_fixed())
    if hasattr(module, "get_lessons"):
        return cast(RelatedList, module.get_lessons())
    if hasattr(module, "faqs"):
        return cast(RelatedList, module.faqs)
    if hasattr(module, "fixed"):
        return cast(RelatedList, module.fixed)
    if hasattr(module, "lessons"):
        return cast(RelatedList, module.lessons)
    return []


def _attach_related(agent_cls, project_path: Path, app_name: str, slug: str):
    faqs = _load_related(f"{app_name}.{slug}.faqs", project_path)
    fixed = _load_related(f"{app_name}.{slug}.fixed", project_path)
    lessons = _load_related(f"{app_name}.{slug}.lessons", project_path)
    if faqs and not getattr(agent_cls, "faqs", None):
        agent_cls.faqs = faqs
    if fixed and not getattr(agent_cls, "fixed_responses", None):
        agent_cls.fixed_responses = fixed
    if lessons and not getattr(agent_cls, "lessons", None):
        agent_cls.lessons = lessons


def _serialize_related_list(items: Any) -> Any:
    if not items:
        return []
    serialized = []
    for item in items:
        name = (
            getattr(item, "name", None)
            or getattr(item, "question", None)
            or getattr(item, "key", None)
        )
        if not name:
            cls_name = item.__class__.__name__
            if (
                cls_name.endswith("FAQ")
                or cls_name.endswith("FixedResponse")
                or cls_name.endswith("Lesson")
            ):
                name = cls_name
        content = (
            getattr(item, "content", None)
            or getattr(item, "answer", None)
            or getattr(item, "response", None)
        )
        serialized.append(
            {
                "name": name,
                "content": content,
                "meta": {
                    "topic": getattr(item, "key", None),
                    "context_of_application": getattr(item, "context_of_application", None),
                },
            }
        )
    return serialized


def _tool_key_from_class(cls: type) -> str:
    cname = cls.__name__
    return cname[:-4] if cname.endswith("Tool") else cname
