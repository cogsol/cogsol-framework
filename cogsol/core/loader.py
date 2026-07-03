"""
Utilities to import project modules and collect agent definitions.
"""

from __future__ import annotations

import ast
import importlib
import importlib.abc
import importlib.machinery
import inspect
import sys
import textwrap
import types
from enum import Enum
from pathlib import Path
from typing import Any, Union, cast

from typing_extensions import TypeAlias

from cogsol.agents import BaseAgent, _ConfigBase
from cogsol.content import (
    BaseIngestionConfig,
    BaseMetadataConfig,
    BaseReferenceFormatter,
    BaseRetrieval,
    BaseTopic,
)
from cogsol.prompts import Prompt
from cogsol.tools import (
    BaseFAQ,
    BaseFixedResponse,
    BaseLesson,
    BaseMCPServer,
    BaseMCPTool,
    BaseRetrievalTool,
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
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, (BaseTool, BaseLesson, BaseFAQ, BaseFixedResponse, BaseRetrievalTool)):
        return (
            getattr(value, "name", None) or getattr(value, "key", None) or value.__class__.__name__
        )
    if isinstance(value, type) and issubclass(value, BaseMCPServer):
        return getattr(value, "name", None) or value.__name__
    if isinstance(value, type):
        if issubclass(value, BaseRetrieval):
            return getattr(value, "name", None) or value.__name__
        if issubclass(value, BaseReferenceFormatter):
            return getattr(value, "name", None) or value.__name__
        if issubclass(value, BaseTopic):
            return getattr(value, "name", None) or value.__name__
        if issubclass(value, BaseIngestionConfig):
            return getattr(value, "name", None) or value.__name__
        if issubclass(value, BaseMetadataConfig):
            return getattr(value, "name", None) or value.__name__
        if issubclass(value, BaseRetrievalTool):
            return getattr(value, "name", None) or value.__name__
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


class _StubValue:
    """Inert placeholder for attributes of packages that are not installed locally."""

    def __init__(self, name: str) -> None:
        self._stub_name = name

    def __getattr__(self, item: str) -> "_StubValue":
        return _StubValue(f"{self._stub_name}.{item}")

    def __call__(self, *args: Any, **kwargs: Any) -> "_StubValue":
        return _StubValue(f"{self._stub_name}()")

    def __repr__(self) -> str:
        return f"<stubbed missing dependency {self._stub_name}>"


class _MissingDependencyStubber(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Fabricates inert stub modules for packages not installed locally.

    Tool ``run()`` code executes remotely in Cognitive, where its imports are
    available. Locally we only need the class *definitions*, so module-level
    imports of missing third-party packages (e.g. ``django``) are satisfied
    with stubs while collecting definitions.

    The finder is appended at the END of ``sys.meta_path``, so installed
    packages always resolve normally; only genuinely missing ones are stubbed.
    """

    def __init__(self, project_path: Path) -> None:
        self.project_path = project_path
        self.stubbed_roots: set[str] = set()
        self.created_modules: list[str] = []

    def _is_stubbable(self, fullname: str) -> bool:
        top = fullname.split(".")[0]
        stdlib_names = getattr(sys, "stdlib_module_names", frozenset())
        if top == "cogsol" or top in stdlib_names:
            return False
        # Never stub project-local modules — a typo there is a real error.
        if (self.project_path / top).exists() or (self.project_path / f"{top}.py").exists():
            return False
        return True

    def find_spec(self, fullname, path=None, target=None):
        if not self._is_stubbable(fullname):
            return None
        return importlib.machinery.ModuleSpec(fullname, self, is_package=True)

    def create_module(self, spec):
        module = types.ModuleType(spec.name)
        module.__path__ = []  # behave as a package so submodule imports resolve too
        module.__getattr__ = lambda item, _n=spec.name: _StubValue(f"{_n}.{item}")
        self.stubbed_roots.add(spec.name.split(".")[0])
        self.created_modules.append(spec.name)
        return module

    def exec_module(self, module):
        return None


def _purge_module_cache(module_name: str) -> None:
    parts = module_name.split(".")
    for i in range(1, len(parts) + 1):
        sys.modules.pop(".".join(parts[:i]), None)
    for name in list(sys.modules):
        if name.startswith(f"{module_name}."):
            sys.modules.pop(name, None)


def _import_module(module_name: str, project_path: Path):
    # Ensure project modules are reloaded from the current project path.
    _purge_module_cache(module_name)
    sys.path.insert(0, str(project_path))
    try:
        importlib.invalidate_caches()
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            missing_root = (exc.name or "").split(".")[0]
            target_root = module_name.split(".")[0]
            # Only stub genuinely foreign packages. If the project module
            # itself (or another project-local module) is missing, keep the
            # original error so callers can handle/report it.
            if (
                not missing_root
                or missing_root == target_root
                or missing_root == "cogsol"
                or (project_path / missing_root).exists()
                or (project_path / f"{missing_root}.py").exists()
            ):
                raise
            return _import_module_with_stubs(module_name, project_path)
    finally:
        try:
            sys.path.remove(str(project_path))
        except ValueError:
            pass


def _import_module_with_stubs(module_name: str, project_path: Path):
    """Retry a project-module import stubbing missing third-party packages."""
    _purge_module_cache(module_name)
    finder = _MissingDependencyStubber(project_path)
    sys.meta_path.append(finder)
    try:
        importlib.invalidate_caches()
        module = importlib.import_module(module_name)
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        # Drop fabricated modules so they never shadow real installs later.
        for name in finder.created_modules:
            sys.modules.pop(name, None)
    if finder.stubbed_roots:
        missing = ", ".join(sorted(finder.stubbed_roots))
        print(
            f"  Warning: '{module_name}' imports packages not installed locally: {missing}. "
            "They were stubbed to collect definitions — this code still runs in Cognitive."
        )
    return module


def _ignore_missing_module(exc: ModuleNotFoundError, module_name: str) -> bool:
    return exc.name == module_name


def _raise_import_error(context: str, module_name: str, exc: ModuleNotFoundError) -> None:
    raise RuntimeError(f"Failed to import {context} '{module_name}': {exc}") from exc


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


def _load_prompt_text(
    value: Any,
    project_path: Path,
    app_name: str,
    slug: str | None = None,
) -> str | None:
    def _read(path: Path) -> str | None:
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return None

    candidates: list[Path] = []
    if isinstance(value, Prompt):
        if value.base_dir:
            candidates.append(Path(value.base_dir) / "prompts" / value.path)
        if slug:
            candidates.append(project_path / app_name / slug / "prompts" / value.path)
        candidates.append(project_path / app_name / "prompts" / value.path)
        candidates.append(Path(value.path))
    elif isinstance(value, Path):
        candidates.append(value)
        if slug:
            candidates.append(project_path / app_name / slug / "prompts" / value.name)
        candidates.append(project_path / app_name / "prompts" / value.name)

    for candidate in candidates:
        text = _read(candidate)
        if text is not None:
            return text.replace("\r\n", "\n").rstrip()
    return None


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
        param_dict = {"description": desc, "type": typ, "required": bool(required)}
        # Include 'items' for array types if specified in decorator
        if typ == "array" and "items" in meta:
            param_dict["items"] = meta["items"]
        params[name] = param_dict
    return params


def _extract_tool_code(tool_cls: type[BaseTool]) -> str:
    """
    Build a stable code snapshot for migration diffing.

    Prefer all non-dunder methods from the class body so helper method changes
    are tracked by makemigrations. Fallback to run() source when needed.
    """

    run_source = ""
    try:
        run_source = _normalize_code(inspect.getsource(tool_cls.run))
    except Exception:
        run_source = ""

    try:
        raw_class_source = inspect.getsource(tool_cls)
        normalized_class_source = _normalize_code(raw_class_source)
    except Exception:
        return run_source

    try:
        tree = ast.parse(normalized_class_source)
    except SyntaxError:
        return run_source

    class_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == tool_cls.__name__
        ),
        None,
    )
    if class_node is None:
        return run_source

    helper_methods: list[str] = []
    for node in class_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "run":
            continue
        if node.name.startswith("__") and node.name.endswith("__"):
            continue
        source = ast.get_source_segment(normalized_class_source, node)
        if not source:
            source = ast.unparse(node)
        helper_methods.append(_normalize_code(source))

    if not helper_methods:
        return run_source

    code_parts = helper_methods + ([run_source] if run_source else [])
    return cast(str, _normalize_code("\n\n".join(code_parts)))


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
        "retrieval_tools": {},
        "mcp_servers": {},
        "mcp_tools": {},
        "faqs": {},
        "fixed_responses": {},
        "lessons": {},
    }

    # Tools (global, reusable)
    try:
        tool_module = _import_module(f"{app_name}.tools", project_path)
        tool_prefix = f"{tool_module.__name__}."
        for _, obj in inspect.getmembers(tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseTool)
                and obj is not BaseTool
                and (
                    obj.__module__ == tool_module.__name__ or obj.__module__.startswith(tool_prefix)
                )
            ):
                fields, meta = _extract_class_fields(obj)
                normalized = _tool_key_from_class(obj)
                current_name = fields.get("name")
                if not current_name or current_name == obj.__name__:
                    fields["name"] = normalized
                fields["parameters"] = _extract_tool_params(obj)
                fields["__code__"] = _extract_tool_code(obj)
                definitions["tools"][normalized] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.tools"):
            _raise_import_error("tools module", f"{app_name}.tools", exc)

    # Retrieval tools (global, reusable)
    try:
        retrieval_module = _import_module(f"{app_name}.searches", project_path)
        retrieval_prefix = f"{retrieval_module.__name__}."
        for _, obj in inspect.getmembers(retrieval_module, inspect.isclass):
            if (
                issubclass(obj, BaseRetrievalTool)
                and obj is not BaseRetrievalTool
                and (
                    obj.__module__ == retrieval_module.__name__
                    or obj.__module__.startswith(retrieval_prefix)
                )
            ):
                fields, meta = _extract_class_fields(obj)
                name = fields.get("name") or obj.__name__
                fields["name"] = name
                if "parameters" not in fields:
                    fields["parameters"] = []
                definitions["retrieval_tools"][name] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.searches"):
            _raise_import_error("retrieval tools module", f"{app_name}.searches", exc)

    # MCP servers (global)
    try:
        mcp_server_module = _import_module(f"{app_name}.mcp_servers", project_path)
        mcp_srv_prefix = f"{mcp_server_module.__name__}."
        for _, obj in inspect.getmembers(mcp_server_module, inspect.isclass):
            if (
                issubclass(obj, BaseMCPServer)
                and obj is not BaseMCPServer
                and (
                    obj.__module__ == mcp_server_module.__name__
                    or obj.__module__.startswith(mcp_srv_prefix)
                )
            ):
                fields, meta = _extract_class_fields(obj)
                name = fields.get("name") or obj.__name__
                fields["name"] = name
                # Resolve env-var references so values are evaluated at collect time
                if hasattr(obj, "url") and obj.url is not None:
                    fields["url"] = obj.url
                if hasattr(obj, "headers") and obj.headers:
                    fields["headers"] = obj.headers
                # OAuth fields
                if hasattr(obj, "auth_type"):
                    fields["auth_type"] = obj.auth_type
                if hasattr(obj, "oauth_client_id") and obj.oauth_client_id is not None:
                    fields["oauth_client_id"] = obj.oauth_client_id
                if hasattr(obj, "oauth_scopes") and obj.oauth_scopes is not None:
                    fields["oauth_scopes"] = obj.oauth_scopes
                definitions["mcp_servers"][name] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.mcp_servers"):
            _raise_import_error("MCP servers module", f"{app_name}.mcp_servers", exc)

    # MCP tools (global)
    try:
        mcp_tool_module = _import_module(f"{app_name}.mcp_tools", project_path)
        mcp_tool_prefix = f"{mcp_tool_module.__name__}."
        for _, obj in inspect.getmembers(mcp_tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseMCPTool)
                and obj is not BaseMCPTool
                and (
                    obj.__module__ == mcp_tool_module.__name__
                    or obj.__module__.startswith(mcp_tool_prefix)
                )
            ):
                fields, meta = _extract_class_fields(obj)
                name = fields.get("name") or obj.__name__
                fields["name"] = name
                # Serialize server reference as the server class name
                server_cls = getattr(obj, "server", None)
                if server_cls is not None and isinstance(server_cls, type):
                    fields["server"] = getattr(server_cls, "name", None) or server_cls.__name__
                definitions["mcp_tools"][name] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.mcp_tools"):
            _raise_import_error("MCP tools module", f"{app_name}.mcp_tools", exc)

    # Per-agent packages (agents/<slug>/agent.py)
    for sub in sorted(app_path.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in {"migrations", "__pycache__", "prompts"}:
            continue
        agent_module_path = f"{app_name}.{sub.name}.agent"
        try:
            agent_module = _import_module(agent_module_path, project_path)
        except ModuleNotFoundError as exc:
            if _ignore_missing_module(exc, agent_module_path):
                continue
            _raise_import_error("agent module", agent_module_path, exc)

        for _, obj in inspect.getmembers(agent_module, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != agent_module.__name__ and not obj.__module__.startswith(
                f"{app_name}.{sub.name}."
            ):
                continue
            _attach_related(obj, project_path, app_name, sub.name)
            fields, meta = _extract_class_fields(obj)
            prompt_value = getattr(obj, "system_prompt", None)
            if prompt_value is not None:
                prompt_text = _load_prompt_text(prompt_value, project_path, app_name, sub.name)
                if prompt_text is not None:
                    fields["system_prompt"] = prompt_text
            if not getattr(obj, "name", None):
                fields["name"] = (
                    obj.__name__[:-5] if obj.__name__.endswith("Agent") else obj.__name__
                )
            faqs = _serialize_related_list(getattr(obj, "faqs", []))
            fixed = _serialize_related_list(getattr(obj, "fixed_responses", []))
            lessons = _serialize_related_list(getattr(obj, "lessons", []))
            for item in faqs:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["faqs"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            for item in fixed:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["fixed_responses"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            for item in lessons:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["lessons"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            definitions["agents"][obj.__name__] = {"fields": fields, "meta": meta}

    # Fallback: legacy single module agents.py
    try:
        legacy_agents = _import_module(f"{app_name}.agents", project_path)
        for _, obj in inspect.getmembers(legacy_agents, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != legacy_agents.__name__ and not obj.__module__.startswith(
                f"{app_name}."
            ):
                continue
            fields, meta = _extract_class_fields(obj)
            prompt_value = getattr(obj, "system_prompt", None)
            if prompt_value is not None:
                prompt_text = _load_prompt_text(prompt_value, project_path, app_name)
                if prompt_text is not None:
                    fields["system_prompt"] = prompt_text
            faqs = _serialize_related_list(getattr(obj, "faqs", []))
            fixed = _serialize_related_list(getattr(obj, "fixed_responses", []))
            lessons = _serialize_related_list(getattr(obj, "lessons", []))
            for item in faqs:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["faqs"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            for item in fixed:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["fixed_responses"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            for item in lessons:
                key = f"{obj.__name__}::{item.get('name')}"
                definitions["lessons"][key] = {
                    "fields": {
                        "name": item.get("name"),
                        "content": item.get("content"),
                        "meta": item.get("meta", {}),
                        "agent": obj.__name__,
                    }
                }
            definitions["agents"][obj.__name__] = {"fields": fields, "meta": meta}
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.agents"):
            _raise_import_error("legacy agents module", f"{app_name}.agents", exc)

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
        "retrieval_tools": {},
        "mcp_servers": {},
        "mcp_tools": {},
    }

    # Tools
    try:
        tool_module = _import_module(f"{app_name}.tools", project_path)
        tool_prefix = f"{tool_module.__name__}."
        for _, obj in inspect.getmembers(tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseTool)
                and obj is not BaseTool
                and (
                    obj.__module__ == tool_module.__name__ or obj.__module__.startswith(tool_prefix)
                )
            ):
                key = _tool_key_from_class(obj)
                classes["tools"][key] = obj
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.tools"):
            _raise_import_error("tools module", f"{app_name}.tools", exc)

    # Retrieval tools
    try:
        retrieval_module = _import_module(f"{app_name}.searches", project_path)
        retrieval_prefix = f"{retrieval_module.__name__}."
        for _, obj in inspect.getmembers(retrieval_module, inspect.isclass):
            if (
                issubclass(obj, BaseRetrievalTool)
                and obj is not BaseRetrievalTool
                and (
                    obj.__module__ == retrieval_module.__name__
                    or obj.__module__.startswith(retrieval_prefix)
                )
            ):
                key = getattr(obj, "name", None) or obj.__name__
                classes["retrieval_tools"][key] = obj
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.searches"):
            _raise_import_error("retrieval tools module", f"{app_name}.searches", exc)

    # MCP servers
    try:
        mcp_server_module = _import_module(f"{app_name}.mcp_servers", project_path)
        mcp_srv_prefix = f"{mcp_server_module.__name__}."
        for _, obj in inspect.getmembers(mcp_server_module, inspect.isclass):
            if (
                issubclass(obj, BaseMCPServer)
                and obj is not BaseMCPServer
                and (
                    obj.__module__ == mcp_server_module.__name__
                    or obj.__module__.startswith(mcp_srv_prefix)
                )
            ):
                name = getattr(obj, "name", None) or obj.__name__
                classes["mcp_servers"][name] = obj
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.mcp_servers"):
            _raise_import_error("MCP servers module", f"{app_name}.mcp_servers", exc)

    # MCP tools
    try:
        mcp_tool_module = _import_module(f"{app_name}.mcp_tools", project_path)
        mcp_tool_prefix = f"{mcp_tool_module.__name__}."
        for _, obj in inspect.getmembers(mcp_tool_module, inspect.isclass):
            if (
                issubclass(obj, BaseMCPTool)
                and obj is not BaseMCPTool
                and (
                    obj.__module__ == mcp_tool_module.__name__
                    or obj.__module__.startswith(mcp_tool_prefix)
                )
            ):
                name = getattr(obj, "name", None) or obj.__name__
                classes["mcp_tools"][name] = obj
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.mcp_tools"):
            _raise_import_error("MCP tools module", f"{app_name}.mcp_tools", exc)

    # Agents per folder
    for sub in sorted(app_path.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in {"migrations", "__pycache__", "prompts"}:
            continue
        agent_module_path = f"{app_name}.{sub.name}.agent"
        try:
            agent_module = _import_module(agent_module_path, project_path)
        except ModuleNotFoundError as exc:
            if _ignore_missing_module(exc, agent_module_path):
                continue
            _raise_import_error("agent module", agent_module_path, exc)

        for _, obj in inspect.getmembers(agent_module, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != agent_module.__name__ and not obj.__module__.startswith(
                f"{app_name}.{sub.name}."
            ):
                continue
            _attach_related(obj, project_path, app_name, sub.name)
            classes["agents"][obj.__name__] = obj

    # Fallback: legacy single module agents.py
    try:
        legacy_agents = _import_module(f"{app_name}.agents", project_path)
        for _, obj in inspect.getmembers(legacy_agents, inspect.isclass):
            if not issubclass(obj, BaseAgent) or obj is BaseAgent:
                continue
            if obj.__module__ != legacy_agents.__name__ and not obj.__module__.startswith(
                f"{app_name}."
            ):
                continue
            classes["agents"][obj.__name__] = obj
    except ModuleNotFoundError as exc:
        if not _ignore_missing_module(exc, f"{app_name}.agents"):
            _raise_import_error("legacy agents module", f"{app_name}.agents", exc)
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


# =============================================================================
# Content API (data/) Loader Functions
# =============================================================================


def _extract_topic_path(topic_dir: Path, data_dir: Path) -> str:
    """Extract the topic path relative to data/."""
    rel_path = topic_dir.relative_to(data_dir)
    return str(rel_path).replace("\\", "/")


def _collect_topics_recursive(
    data_dir: Path,
    current_dir: Path,
    project_path: Path,
    parent_path: str = "",
) -> dict[str, dict[str, Any]]:
    """Recursively collect topic definitions from nested folders."""
    topics: dict[str, dict[str, Any]] = {}

    for sub in sorted(current_dir.iterdir()):
        if not sub.is_dir():
            continue
        if sub.name in {"migrations", "__pycache__", ".git"}:
            continue
        if sub.name.startswith(("_", ".")):
            continue

        init_file = sub / "__init__.py"
        if not init_file.exists():
            # Recurse into subdirectories even without __init__.py
            sub_path = f"{parent_path}/{sub.name}" if parent_path else sub.name
            topics.update(_collect_topics_recursive(data_dir, sub, project_path, sub_path))
            continue

        # Import the topic module
        topic_path = _extract_topic_path(sub, data_dir)
        module_path = f"data.{topic_path.replace('/', '.')}"

        try:
            module = _import_module(module_path, project_path)
        except ModuleNotFoundError as exc:
            if _ignore_missing_module(exc, module_path):
                continue
            _raise_import_error("topic module", module_path, exc)

        # Find BaseTopic subclass
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseTopic) or obj is BaseTopic:
                continue
            if obj.__module__ != module.__name__:
                continue

            fields, meta = _extract_class_fields(obj)
            # Ensure name is set
            if not fields.get("name"):
                fields["name"] = sub.name

            # Store with path as key
            topics[topic_path] = {
                "fields": fields,
                "meta": meta,
                "class": obj,
            }
            break

        # Also collect metadata configs from metadata.py
        metadata_module_path = f"{module_path}.metadata"
        try:
            metadata_module = _import_module(metadata_module_path, project_path)
            metadata_configs = []
            for _, obj in inspect.getmembers(metadata_module, inspect.isclass):
                if not issubclass(obj, BaseMetadataConfig) or obj is BaseMetadataConfig:
                    continue
                if obj.__module__ != metadata_module.__name__:
                    continue
                fields, _ = _extract_class_fields(obj)
                metadata_configs.append(fields)
            if metadata_configs and topic_path in topics:
                topics[topic_path]["metadata_configs"] = metadata_configs
        except ModuleNotFoundError as exc:
            if not _ignore_missing_module(exc, metadata_module_path):
                _raise_import_error("metadata module", metadata_module_path, exc)

        # Recurse into subdirectories
        topics.update(_collect_topics_recursive(data_dir, sub, project_path, topic_path))

    return topics


def _collect_formatters(project_path: Path) -> dict[str, dict[str, Any]]:
    """Collect reference formatters from data/formatters.py."""
    formatters: dict[str, dict[str, Any]] = {}

    try:
        module = _import_module("data.formatters", project_path)
    except ModuleNotFoundError as exc:
        if _ignore_missing_module(exc, "data.formatters"):
            return formatters
        _raise_import_error("formatters module", "data.formatters", exc)
        return formatters

    module_prefix = f"{module.__name__}."
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, BaseReferenceFormatter) or obj is BaseReferenceFormatter:
            continue
        if obj.__module__ != module.__name__ and not obj.__module__.startswith(module_prefix):
            continue

        fields, meta = _extract_class_fields(obj)
        name = fields.get("name") or obj.__name__
        formatters[name] = {"fields": fields, "meta": meta, "class": obj}

    return formatters


def _collect_ingestion_configs(project_path: Path) -> dict[str, dict[str, Any]]:
    """Collect ingestion configs from data/ingestion.py."""
    configs: dict[str, dict[str, Any]] = {}

    try:
        module = _import_module("data.ingestion", project_path)
    except ModuleNotFoundError as exc:
        if _ignore_missing_module(exc, "data.ingestion"):
            return configs
        _raise_import_error("ingestion module", "data.ingestion", exc)
        return configs

    module_prefix = f"{module.__name__}."
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, BaseIngestionConfig) or obj is BaseIngestionConfig:
            continue
        if obj.__module__ != module.__name__ and not obj.__module__.startswith(module_prefix):
            continue

        fields, meta = _extract_class_fields(obj)
        name = fields.get("name") or obj.__name__
        configs[name] = {"fields": fields, "meta": meta, "class": obj}

    return configs


def _collect_retrievals(project_path: Path) -> dict[str, dict[str, Any]]:
    """Collect retrieval configs from data/retrievals.py."""
    retrievals: dict[str, dict[str, Any]] = {}

    try:
        module = _import_module("data.retrievals", project_path)
    except ModuleNotFoundError as exc:
        if _ignore_missing_module(exc, "data.retrievals"):
            return retrievals
        _raise_import_error("retrievals module", "data.retrievals", exc)
        return retrievals

    module_prefix = f"{module.__name__}."
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if not issubclass(obj, BaseRetrieval) or obj is BaseRetrieval:
            continue
        if obj.__module__ != module.__name__ and not obj.__module__.startswith(module_prefix):
            continue

        fields, meta = _extract_class_fields(obj)
        topic_value = getattr(obj, "topic", None)
        topic_cls: type[BaseTopic] | None = None
        if isinstance(topic_value, BaseTopic):
            topic_cls = type(topic_value)
        elif isinstance(topic_value, type) and issubclass(topic_value, BaseTopic):
            topic_cls = topic_value
        if topic_cls and topic_cls.__module__.startswith("data."):
            topic_path = topic_cls.__module__[len("data.") :].replace(".", "/")
            fields["topic"] = topic_path
        name = fields.get("name") or obj.__name__
        retrievals[name] = {"fields": fields, "meta": meta, "class": obj}

    return retrievals


def collect_content_definitions(
    project_path: Path, app_name: str = "data"
) -> dict[str, dict[str, dict[str, Any]]]:
    """
    Collect all Content API definitions from the data/ folder.

    Returns a structured dict with:
    - topics: Topic definitions (nodes in Content API)
    - formatters: Reference formatter definitions
    - ingestion_configs: Ingestion configuration definitions
    - retrievals: Retrieval configuration definitions
    """
    data_path = project_path / app_name
    if not data_path.exists():
        return {
            "topics": {},
            "formatters": {},
            "ingestion_configs": {},
            "retrievals": {},
            "metadata_configs": {},
        }

    topics = _collect_topics_recursive(data_path, data_path, project_path)
    metadata_configs: dict[str, dict[str, Any]] = {}
    for topic_path, definition in topics.items():
        for cfg_fields in definition.get("metadata_configs", []) or []:
            cfg_name = cfg_fields.get("name")
            if not cfg_name:
                continue
            cfg_key = f"{topic_path}/{cfg_name}"
            metadata_configs[cfg_key] = {
                "fields": cfg_fields,
                "meta": {},
                "topic": topic_path,
            }

    definitions: dict[str, dict[str, dict[str, Any]]] = {
        "topics": topics,
        "formatters": _collect_formatters(project_path),
        "ingestion_configs": _collect_ingestion_configs(project_path),
        "retrievals": _collect_retrievals(project_path),
        "metadata_configs": metadata_configs,
    }

    return definitions


def collect_content_classes(
    project_path: Path, app_name: str = "data"
) -> dict[str, dict[str, type]]:
    """
    Return actual class objects for Content API entities.
    """
    definitions = collect_content_definitions(project_path, app_name)

    classes: dict[str, dict[str, type]] = {
        "topics": {},
        "formatters": {},
        "ingestion_configs": {},
        "retrievals": {},
    }

    for key, topic_def in definitions["topics"].items():
        if "class" in topic_def:
            classes["topics"][key] = topic_def["class"]

    for key, fmt_def in definitions["formatters"].items():
        if "class" in fmt_def:
            classes["formatters"][key] = fmt_def["class"]

    for key, ing_def in definitions["ingestion_configs"].items():
        if "class" in ing_def:
            classes["ingestion_configs"][key] = ing_def["class"]

    for key, ret_def in definitions["retrievals"].items():
        if "class" in ret_def:
            classes["retrievals"][key] = ret_def["class"]

    return classes
