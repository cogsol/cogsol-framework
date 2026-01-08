from __future__ import annotations

import copy
import inspect
import json
import textwrap
from pathlib import Path
from typing import Any, Optional, cast

from cogsol.agents import genconfigs
from cogsol.core import migrations as migutils
from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.core.loader import _extract_tool_params, collect_classes
from cogsol.db import migrations
from cogsol.management.base import BaseCommand
from cogsol.prompts import Prompt
from cogsol.tools import BaseTool


def _tool_key(obj: Any) -> str:
    cls = obj if isinstance(obj, type) else obj.__class__
    cname = cls.__name__
    return cname[:-4] if cname.endswith("Tool") else cname


def _normalize_code(code: Any) -> str:
    if not isinstance(code, str):
        return str(code)
    code = code.replace("\r\n", "\n").rstrip()
    return textwrap.dedent(code).rstrip()


def sub_slug(cls: Optional[type]) -> Optional[str]:
    if cls and hasattr(cls, "__module__"):
        parts = cls.__module__.split(".")
        if len(parts) >= 2:
            return parts[1]
    return None


class Command(BaseCommand):
    help = "Apply migrations for the CogSol project."

    def add_arguments(self, parser):
        parser.add_argument("app", nargs="?", default="agents", help="App to migrate.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        app = str(options.get("app") or "agents")
        migrations_path = project_path / app / "migrations"
        applied_path = migrations_path / ".applied.json"
        state_path = migrations_path / ".state.json"

        if not migrations_path.exists():
            print(f"No migrations folder found for app '{app}'.")
            return 1

        migration_files = list(migutils.iter_migration_files(migrations_path))
        if not migration_files:
            print("No migrations to apply.")
            return 0

        load_dotenv(project_path / ".env")
        api_base = self._env("COGSOL_API_BASE")
        api_token = self._env("COGSOL_API_TOKEN", required=False)
        if not api_base:
            print("COGSOL_API_BASE is required in .env to run migrations against CogSol APIs.")
            return 1

        applied = migutils.load_applied(applied_path)
        state, remote_ids = self._load_state(state_path)

        # Rebuild state from already applied migrations to avoid stale cache issues.
        state = migutils.empty_state()
        for mf in migration_files:
            module = migutils.load_migration_module(mf)
            migration_cls = getattr(module, "Migration", None)
            if migration_cls is None:
                continue
            migration = migration_cls() if callable(migration_cls) else migration_cls
            if mf.stem in applied:
                migrations.apply_operations(state, getattr(migration, "operations", []))

        pending = [mf for mf in migration_files if mf.stem not in applied]
        if not pending:
            print("No pending migrations.")
            return 0

        for mf in pending:
            module = migutils.load_migration_module(mf)
            migration_cls = getattr(module, "Migration", None)
            if migration_cls is None:
                print(f"Skipping {mf.name}: Migration class not found.")
                continue
            migration = migration_cls() if callable(migration_cls) else migration_cls
            print(f"Applying {app}.{mf.stem}...")
            migrations.apply_operations(state, getattr(migration, "operations", []))
            applied.append(mf.stem)
            print("  Recorded.")

        # Push resulting state to CogSol API.
        try:
            class_map = collect_classes(project_path, app)
            remote_ids = self._sync_with_api(
                api_base=api_base,
                api_token=api_token,
                state=state,
                remote_ids=remote_ids,
                class_map=class_map,
                project_path=project_path,
                app=app,
            )
        except CogSolAPIError as exc:  # pragma: no cover - I/O
            print(f"API error while applying migrations: {exc}")
            return 1

        self._save_state(state_path, state, remote_ids)
        migutils.write_applied(applied_path, applied)
        print(f"Applied {len(pending)} migration(s) and synced with CogSol API.")
        return 0

    # ------------------------------------------------------------------ helpers
    def _env(self, key: str, required: bool = True) -> Optional[str]:
        import os

        value = os.environ.get(key)
        if required and not value:
            return None
        return value

    def _load_state(self, state_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if not state_path.exists():
            return migutils.empty_state(), self._empty_remote()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return migutils.empty_state(), self._empty_remote()

        if "state" in data and "remote" in data:
            return data["state"], data["remote"]
        return data, self._empty_remote()

    def _save_state(self, state_path: Path, state: dict[str, Any], remote: dict[str, Any]) -> None:
        state_path.write_text(
            json.dumps({"state": state, "remote": remote}, indent=2), encoding="utf-8"
        )

    def _empty_remote(self) -> dict[str, Any]:
        return {
            "agents": {},
            "tools": {},
            "lessons": {},
            "faqs": {},
            "fixed_responses": {},
        }

    def _sync_with_api(
        self,
        *,
        api_base: str,
        api_token: Optional[str],
        state: dict[str, Any],
        remote_ids: dict[str, Any],
        class_map: dict[str, dict[str, type]],
        project_path: Path,
        app: str,
    ) -> dict[str, Any]:
        client = CogSolClient(api_base, token=api_token)
        created: list[tuple[str, Optional[int], int]] = []
        new_remote = copy.deepcopy(remote_ids)

        try:
            # Upsert script tools first (shared resources).
            for tool_name, definition in state.get("tools", {}).items():
                cls = cast(Optional[type[BaseTool]], class_map.get("tools", {}).get(tool_name))
                payload = self._tool_payload(tool_name, definition, cls)
                remote_id = new_remote.get("tools", {}).get(tool_name)
                new_id = client.upsert_script(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("tool", None, new_id))
                # store under multiple keys to ensure lookup (normalized, class name, explicit name)
                new_remote.setdefault("tools", {})[tool_name] = new_id
                if cls is not None:
                    norm = _tool_key(cls)
                    new_remote["tools"][norm] = new_id
                    new_remote["tools"][cls.__name__] = new_id
                    explicit_name = getattr(cls, "name", None)
                    if explicit_name:
                        new_remote["tools"][explicit_name] = new_id

            # Upsert agents.
            for agent_name, definition in state.get("agents", {}).items():
                cls = class_map.get("agents", {}).get(agent_name)
                payload = self._assistant_payload(
                    agent_name=agent_name,
                    definition=definition,
                    cls=cls,
                    remote_ids=new_remote,
                    project_path=project_path,
                    app=app,
                    slug=sub_slug(cls),
                )
                remote_id = new_remote.get("agents", {}).get(agent_name)
                new_id = client.upsert_assistant(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("assistant", None, new_id))
                new_remote.setdefault("agents", {})[agent_name] = new_id

            # Upsert FAQs (common questions), fixed responses, lessons per agent.
            for agent_name, agent_cls in class_map.get("agents", {}).items():
                assistant_id = new_remote.get("agents", {}).get(agent_name)
                if not assistant_id:
                    continue
                new_remote.setdefault("faqs", {}).setdefault(agent_name, {})
                new_remote.setdefault("fixed_responses", {}).setdefault(agent_name, {})
                new_remote.setdefault("lessons", {}).setdefault(agent_name, {})

                for faq_obj in getattr(agent_cls, "faqs", []) or []:
                    payload = self._faq_payload(faq_obj)
                    remote_id = new_remote["faqs"][agent_name].get(payload["name"])
                    new_id = client.upsert_common_question(
                        assistant_id=assistant_id,
                        remote_id=remote_id,
                        payload=payload,
                    )
                    if not remote_id:
                        created.append(("faq", assistant_id, new_id))
                    new_remote["faqs"][agent_name][payload["name"]] = new_id

                for fx_obj in getattr(agent_cls, "fixed_responses", []) or []:
                    payload = self._fixed_payload(fx_obj)
                    remote_id = new_remote["fixed_responses"][agent_name].get(payload["name"])
                    new_id = client.upsert_fixed_response(
                        assistant_id=assistant_id,
                        remote_id=remote_id,
                        payload=payload,
                    )
                    if not remote_id:
                        created.append(("fixed", assistant_id, new_id))
                    new_remote["fixed_responses"][agent_name][payload["name"]] = new_id

                for lesson_obj in getattr(agent_cls, "lessons", []) or []:
                    payload = self._lesson_payload(lesson_obj)
                    remote_id = new_remote["lessons"][agent_name].get(payload["name"])
                    new_id = client.upsert_lesson(
                        assistant_id=assistant_id,
                        remote_id=remote_id,
                        payload=payload,
                    )
                    if not remote_id:
                        created.append(("lesson", assistant_id, new_id))
                    new_remote["lessons"][agent_name][payload["name"]] = new_id

            return new_remote
        except Exception:
            # Rollback creations in reverse order.
            for kind, assistant_id, obj_id in reversed(created):
                try:
                    if kind == "faq" and assistant_id is not None:
                        client.delete_common_question(assistant_id, obj_id)
                    elif kind == "fixed" and assistant_id is not None:
                        client.delete_fixed_response(assistant_id, obj_id)
                    elif kind == "lesson" and assistant_id is not None:
                        client.delete_lesson(assistant_id, obj_id)
                    elif kind == "assistant":
                        client.delete_assistant(obj_id)
                    elif kind == "tool":
                        client.delete_script(obj_id)
                except Exception:
                    continue
            raise

    def _tool_payload(
        self,
        tool_name: str,
        definition: dict[str, Any],
        cls: Optional[type[BaseTool]],
    ) -> dict[str, Any]:
        params = []
        if cls is not None:
            param_def = _extract_tool_params(cls)
        else:
            param_def = definition.get("fields", {}).get("parameters", {}) if definition else {}
        for name, meta in (param_def or {}).items():
            meta = meta or {}
            params.append(
                {
                    "name": name,
                    "description": meta.get("description") or name,
                    "type": meta.get("type") or "string",
                    "required": bool(meta.get("required", True)),
                }
            )

        description = (
            (definition.get("fields", {}) or {}).get("description") if definition else None
        )
        if not description and cls is not None:
            description = getattr(cls, "description", None)
        description = description or f"Tool {tool_name}"

        code = self._tool_script_from_class(cls) if cls is not None else ""
        code = code or "# TODO: provide implementation\nresponse = None"

        return {
            "name": tool_name,
            "description": description,
            "parameters": params,
            "show_tool_message": True,
            "show_assistant_message": False,
            "edit_available": False,
            "code": code,
        }

    def _assistant_payload(
        self,
        *,
        agent_name: str,
        definition: dict[str, Any],
        cls: Optional[type],
        remote_ids: dict[str, Any],
        project_path: Path,
        app: str,
        slug: Optional[str] = None,
    ) -> dict[str, Any]:
        fields = definition.get("fields", {}) if definition else {}
        meta = definition.get("meta", {}) if definition else {}

        def _get(attr: str, default=None):
            if cls is not None and hasattr(cls, attr):
                return getattr(cls, attr)
            return fields.get(attr, default)

        def _get_meta(attr: str, default=None):
            if meta and attr in meta:
                return meta.get(attr, default)
            return default

        def _normalize_config(value: Any, default: str = "default") -> str:
            if value is None:
                return default
            if isinstance(value, str):
                return value
            name = getattr(value, "name", None)
            if name:
                if isinstance(value, genconfigs.QA) and str(name).lower() == "qa":
                    return "QA"
                return str(name)
            return type(value).__name__

        def _int_or_default(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def _first_non_none(*values: Any) -> Any:
            for v in values:
                if v is not None:
                    return v
            return None

        def _prompt_text(value: Any) -> str:
            if isinstance(value, Prompt):
                candidates = []
                if value.base_dir:
                    candidates.append(Path(value.base_dir) / "prompts" / value.path)
                if slug:
                    candidates.append(project_path / app / slug / "prompts" / value.path)
                candidates.append(project_path / app / "prompts" / value.path)
                for candidate in candidates:
                    if candidate.exists():
                        try:
                            return candidate.read_text(encoding="utf-8")
                        except FileNotFoundError:
                            continue
                return str(value.path)
            if isinstance(value, Path):
                try:
                    return value.read_text(encoding="utf-8")
                except FileNotFoundError:
                    return str(value)
            return str(value) if value is not None else ""

        tools = getattr(cls, "tools", []) if cls else []
        pretools = getattr(cls, "pretools", []) if cls else []

        tool_ids: list[int] = []
        for t in tools:
            candidates = [
                getattr(t, "name", None),
                _tool_key(t),
                getattr(t, "__name__", None),
                t.__class__.__name__,
            ]
            remote_id = None
            for name in candidates:
                if name and name in remote_ids.get("tools", {}):
                    remote_id = remote_ids["tools"][name]
                    break
            if remote_id:
                tool_ids.append(remote_id)

        pretool_ids: list[int] = []
        for t in pretools:
            candidates = [
                getattr(t, "name", None),
                _tool_key(t),
                getattr(t, "__name__", None),
                t.__class__.__name__,
            ]
            remote_id = None
            for name in candidates:
                if name and name in remote_ids.get("tools", {}):
                    remote_id = remote_ids["tools"][name]
                    break
            if remote_id:
                pretool_ids.append(remote_id)

        colors = {}
        if _get_meta("assistant_name_color"):
            colors["assistant_name_color"] = _get_meta("assistant_name_color")
        if _get_meta("primary_color"):
            colors["primary_color"] = _get_meta("primary_color")
        if _get_meta("secondary_color"):
            colors["secondary_color"] = _get_meta("secondary_color")
        if _get_meta("border_color"):
            colors["border_color"] = _get_meta("border_color")

        payload = {
            "generation_config": _normalize_config(_get("generation_config")),
            "generation_config_pretools": _normalize_config(_get("pregeneration_config")),
            "description": _get_meta("chat_name") or f"Agent {agent_name}",
            "system_prompt": _prompt_text(_get("system_prompt")),
            "temperature": float(_get("temperature") or 0.0),
            "max_responses": _int_or_default(
                _first_non_none(_get("max_responses"), _get("max_interactions")), default=0
            ),
            "max_msg_length": _int_or_default(
                _first_non_none(_get("max_msg_length"), _get("user_message_length")),
                default=0,
            ),
            "initial_message": _get("initial_message"),
            "end_message": _get("forced_termination_message"),
            "add_to_user_message": None,
            "max_consecutive_tool_calls": _int_or_default(
                _first_non_none(
                    _get("max_consecutive_tool_calls"),
                    _get("consecutive_tool_calls_limit"),
                ),
                default=0,
            ),
            "matrix_mode_available": bool(_get("realtime", False)),
            "not_info_message": _get("no_information_message"),
            "strategy_to_optimize_tokens": None,
            "faq_available": bool(getattr(cls, "faqs", []) if cls else fields.get("faqs")),
            "fixed_available": bool(
                getattr(cls, "fixed_responses", []) if cls else fields.get("fixed_responses")
            ),
            "lessons_available": bool(
                getattr(cls, "lessons", []) if cls else fields.get("lessons")
            ),
            "realtime_available": bool(_get("realtime", False)),
            "info": None,
            "colors": colors,
            "logo": _get_meta("logo_url"),
            "streaming_available": bool(_get("streaming", False)),
            "tools": tool_ids,
            "pretools": pretool_ids,
        }
        return payload

    def _faq_payload(self, faq_obj: Any) -> dict[str, Any]:
        name = (
            getattr(faq_obj, "question", None)
            or getattr(faq_obj, "name", None)
            or faq_obj.__class__.__name__
        )
        content = getattr(faq_obj, "answer", None) or getattr(faq_obj, "content", None) or ""
        return {
            "name": name,
            "content": content,
            "additional_metadata": {},
        }

    def _fixed_payload(self, obj: Any) -> dict[str, Any]:
        key = getattr(obj, "key", None) or getattr(obj, "name", None) or obj.__class__.__name__
        content = getattr(obj, "response", None) or getattr(obj, "content", None) or ""
        return {
            "topic": key,
            "content": content,
            "name": key,
            "additional_metadata": {},
        }

    def _lesson_payload(self, obj: Any) -> dict[str, Any]:
        name = getattr(obj, "name", None) or obj.__class__.__name__
        content = getattr(obj, "content", None) or ""
        context = getattr(obj, "context_of_application", None) or "general"
        return {
            "name": name,
            "content": content,
            "context_of_application": context,
            "additional_metadata": {},
        }

    def _tool_script_from_class(self, cls: Optional[type[BaseTool]]) -> str:
        if cls is None:
            return ""
        try:
            run_fn = cls.run
        except AttributeError:
            return getattr(cls, "__doc__", "") or ""

        try:
            source = inspect.getsource(run_fn)
        except (OSError, TypeError):  # pragma: no cover - best effort
            return getattr(cls, "__doc__", "") or ""

        source = _normalize_code(source)
        lines = source.splitlines()
        # Strip decorator lines if any (not expected but safe).
        while lines and lines[0].lstrip().startswith("@"):
            lines.pop(0)

        # Find def line
        def_idx = None
        for i, line in enumerate(lines):
            if line.lstrip().startswith("def "):
                def_idx = i
                break
        if def_idx is None:
            return textwrap.dedent(source)

        body = "\n".join(lines[def_idx + 1 :])
        dedented = textwrap.dedent(body)

        # Detect parameters to bind from signature (excluding runtime args)
        params_to_bind = []
        try:
            sig = inspect.signature(run_fn)
            for name, _param in sig.parameters.items():
                if name in {"self", "chat", "data", "secrets", "log", "params"}:
                    continue
                params_to_bind.append(name)
        except Exception:
            params_to_bind = []

        result_lines: list[str] = []
        # Prepend param extraction
        for p in params_to_bind:
            result_lines.append(f"{p} = params.get('{p}') if params else None")

        for line in dedented.splitlines():
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            if stripped.startswith("return "):
                result_lines.append(f"{indent}response = {stripped[len('return '):]}")
                continue
            if stripped == "return":
                result_lines.append(f"{indent}response = None")
                continue
            result_lines.append(line)

        script = "\n".join(result_lines).strip()
        if "response" not in script:
            script += ("\n\n" if script else "") + "response = None"
        return script
