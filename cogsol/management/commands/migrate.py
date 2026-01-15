from __future__ import annotations

import ast
import copy
import inspect
import json
import re
import textwrap
from pathlib import Path
from typing import Any, Optional, cast

from cogsol.agents import genconfigs
from cogsol.content import BaseRetrieval
from cogsol.core import migrations as migutils
from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.core.loader import _extract_tool_params, collect_classes, collect_content_classes
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
        parser.add_argument(
            "app",
            nargs="?",
            default=None,
            help="App to migrate (agents, data, or both when omitted).",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        app = options.get("app")
        apps = [str(app)] if app else ["agents", "data"]

        load_dotenv(project_path / ".env")
        api_base = self._env("COGSOL_API_BASE")
        api_token = self._env("COGSOL_API_TOKEN", required=False)
        content_base = self._env("COGSOL_CONTENT_API_BASE", required=False) or api_base
        if not api_base:
            print("COGSOL_API_BASE is required in .env to run migrations against CogSol APIs.")
            return 1

        exit_code = 0
        for app_name in apps:
            migrations_path = project_path / app_name / "migrations"
            applied_path = migrations_path / ".applied.json"
            state_path = migrations_path / ".state.json"

            if not migrations_path.exists():
                print(f"No migrations folder found for app '{app_name}'.")
                exit_code = 1
                continue

            migration_files = list(migutils.iter_migration_files(migrations_path))
            if not migration_files:
                print(f"No migrations to apply for app '{app_name}'.")
                continue

            applied = migutils.load_applied(applied_path)

            if app_name == "data":
                state, remote_ids = self._load_content_state(state_path)
                state = migutils.empty_content_state()
            else:
                state, remote_ids = self._load_state(state_path)
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
                print(f"No pending migrations for app '{app_name}'.")
                continue

            temp_state = copy.deepcopy(state)
            pending_ops: list[Any] = []
            for mf in pending:
                module = migutils.load_migration_module(mf)
                migration_cls = getattr(module, "Migration", None)
                if migration_cls is None:
                    print(f"Skipping {mf.name}: Migration class not found.")
                    continue
                migration = migration_cls() if callable(migration_cls) else migration_cls
                print(f"Applying {app_name}.{mf.stem}...")
                ops = getattr(migration, "operations", [])
                pending_ops.extend(ops)
                migrations.apply_operations(temp_state, ops)

            try:
                touched = self._touched_entities(pending_ops)
                if app_name == "data":
                    class_map = collect_content_classes(project_path, app_name)
                    remote_ids = self._sync_content_with_api(
                        api_base=content_base or api_base,
                        api_token=api_token,
                        state=temp_state,
                        remote_ids=remote_ids,
                        class_map=class_map,
                        project_path=project_path,
                        touched=touched,
                    )
                else:
                    class_map = collect_classes(project_path, app_name)
                    remote_ids = self._sync_with_api(
                        api_base=api_base,
                        api_token=api_token,
                        state=temp_state,
                        remote_ids=remote_ids,
                        class_map=class_map,
                        project_path=project_path,
                        app=app_name,
                        touched=touched,
                    )
            except CogSolAPIError as exc:  # pragma: no cover - I/O
                print(f"API error while applying migrations: {exc}")
                exit_code = 1
                continue

            applied.extend([mf.stem for mf in pending])
            self._save_state(state_path, temp_state, remote_ids)
            migutils.write_applied(applied_path, applied)
            print(f"Applied {len(pending)} migration(s) for app '{app_name}'.")

        return exit_code

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
            "retrieval_tools": {},
            "lessons": {},
            "faqs": {},
            "fixed_responses": {},
        }

    def _empty_content_remote(self) -> dict[str, Any]:
        return {
            "topics": {},
            "formatters": {},
            "ingestion_configs": {},
            "retrievals": {},
            "metadata_configs": {},
        }

    def _touched_entities(self, operations: list[Any]) -> dict[str, set[str]]:
        touched: dict[str, set[str]] = {}
        for op in operations:
            entity = getattr(op, "entity", None)
            if not entity:
                continue
            name = getattr(op, "name", None)
            if isinstance(op, migrations.AlterField):
                name = getattr(op, "model_name", None)
            if not name:
                continue
            touched.setdefault(entity, set()).add(str(name))
        return touched

    def _load_content_state(self, state_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if not state_path.exists():
            return migutils.empty_content_state(), self._empty_content_remote()
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return migutils.empty_content_state(), self._empty_content_remote()

        if "state" in data and "remote" in data:
            return data["state"], data["remote"]
        return data, self._empty_content_remote()

    def _sync_content_with_api(
        self,
        *,
        api_base: str,
        api_token: Optional[str],
        state: dict[str, Any],
        remote_ids: dict[str, Any],
        class_map: dict[str, dict[str, type]],
        project_path: Path,
        touched: Optional[dict[str, set[str]]] = None,
    ) -> dict[str, Any]:
        """Sync Content API entities (topics, formatters, retrievals) with the API."""
        client = CogSolClient(api_base, token=api_token, content_base_url=api_base)
        created: list[tuple[str, Optional[int], int]] = []
        new_remote = copy.deepcopy(remote_ids)

        try:
            # Upsert topics (nodes) - need to handle parent relationships
            topic_id_map: dict[str, int] = {}  # path -> node_id

            # Sort topics by path depth to create parents first
            topics = list(state.get("topics", {}).items())
            topics.sort(key=lambda x: x[0].count("/"))

            for topic_path, definition in topics:
                if touched is not None and topic_path not in touched.get("topics", set()):
                    continue
                fields = definition.get("fields", {})
                meta = definition.get("meta", {})
                name = fields.get("name") or topic_path.split("/")[-1]
                description = fields.get("description", "") or meta.get("description", "")
                delete_orphaned_metadata = fields.get("delete_orphaned_metadata")

                # Determine parent_id
                parent_id = None
                path_parts = topic_path.split("/")
                if len(path_parts) > 1:
                    parent_path = "/".join(path_parts[:-1])
                    parent_id = topic_id_map.get(parent_path) or new_remote.get("topics", {}).get(
                        parent_path
                    )

                payload = {
                    "name": name,
                    "description": description,
                    "parent": parent_id,
                }
                if delete_orphaned_metadata is not None:
                    payload["delete_orphaned_metadata"] = bool(delete_orphaned_metadata)

                remote_id = new_remote.get("topics", {}).get(topic_path)
                new_id = client.upsert_node(remote_id=remote_id, payload=payload)

                if not remote_id:
                    created.append(("topic", None, new_id))

                topic_id_map[topic_path] = new_id
                new_remote.setdefault("topics", {})[topic_path] = new_id

            # Upsert reference formatters
            for fmt_name, definition in state.get("formatters", {}).items():
                if touched is not None and fmt_name not in touched.get("formatters", set()):
                    continue
                fields = definition.get("fields", {})
                payload = {
                    "name": fields.get("name", fmt_name),
                    "description": fields.get("description", ""),
                    "expression": fields.get("expression", ""),
                }

                remote_id = new_remote.get("formatters", {}).get(fmt_name)
                new_id = client.upsert_reference_formatter(remote_id=remote_id, payload=payload)

                if not remote_id:
                    created.append(("formatter", None, new_id))
                new_remote.setdefault("formatters", {})[fmt_name] = new_id

            # Upsert retrievals
            for ret_name, definition in state.get("retrievals", {}).items():
                if touched is not None and ret_name not in touched.get("retrievals", set()):
                    continue
                fields = definition.get("fields", {})

                # Resolve topic to node ID
                node_id = None
                topic_name = fields.get("topic")
                if topic_name:
                    node_id = topic_id_map.get(topic_name) or new_remote.get("topics", {}).get(
                        topic_name
                    )

                retrieval_payload: dict[str, Any] = {
                    "description": fields.get("name", ret_name),
                }

                if node_id is not None:
                    retrieval_payload["node"] = node_id

                # Only include fields explicitly defined in class
                def _set_if_defined(
                    key: str,
                    *,
                    _fields: dict[str, Any] = fields,
                    _payload: dict[str, Any] = retrieval_payload,
                ) -> None:
                    if key in _fields:
                        value = _fields.get(key)
                        if value is not None:
                            _payload[key] = value

                _set_if_defined("num_refs")
                _set_if_defined("max_msg_length")
                _set_if_defined("reordering")
                _set_if_defined("strategy_reordering")
                _set_if_defined("retrieval_window")
                _set_if_defined("reordering_metadata")
                _set_if_defined("fixed_blocks_reordering")
                _set_if_defined("previous_blocks")
                _set_if_defined("next_blocks")
                _set_if_defined("contingency_for_embedding")
                _set_if_defined("threshold_similarity")
                _set_if_defined("filters")

                if (
                    "strategy_reordering" in retrieval_payload
                    and "reordering_metadata" not in retrieval_payload
                ):
                    raise CogSolAPIError(
                        "reordering_metadata is required when strategy_reordering is set "
                        f"for retrieval '{ret_name}'."
                    )

                if "formatters" in fields:
                    formatters_value = fields.get("formatters")
                    formatters_payload: list[Any] = []
                    if isinstance(formatters_value, dict):
                        for doc_type, formatter in formatters_value.items():
                            fmt_key = formatter
                            if hasattr(formatter, "__name__"):
                                fmt_key = getattr(formatter, "name", None) or formatter.__name__
                            fmt_id = new_remote.get("formatters", {}).get(fmt_key)
                            if fmt_id is None:
                                raise CogSolAPIError(
                                    "Formatter must be migrated before use in retrieval. "
                                    f"Missing formatter id for '{fmt_key}' in '{ret_name}'."
                                )
                            formatters_payload.append(
                                {"doc_type": doc_type, "formatter_id": int(fmt_id)}
                            )
                    elif isinstance(formatters_value, list):
                        for item in formatters_value:
                            if not isinstance(item, dict):
                                raise CogSolAPIError(
                                    "formatters must be dicts with doc_type and formatter_id. "
                                    f"Fix retrieval '{ret_name}'."
                                )
                            if "doc_type" not in item or "formatter_id" not in item:
                                raise CogSolAPIError(
                                    "formatters entries must include doc_type and formatter_id. "
                                    f"Fix retrieval '{ret_name}'."
                                )
                            if not isinstance(item.get("formatter_id"), int):
                                raise CogSolAPIError(
                                    "formatter_id must be an integer (remote id). "
                                    f"Fix retrieval '{ret_name}'."
                                )
                            formatters_payload.append(item)
                    elif formatters_value:
                        raise CogSolAPIError(
                            "formatters must be a dict or list of dicts. "
                            f"Fix retrieval '{ret_name}'."
                        )
                    retrieval_payload["formatters"] = formatters_payload

                remote_id = new_remote.get("retrievals", {}).get(ret_name)
                new_id = client.upsert_retrieval(remote_id=remote_id, payload=retrieval_payload)

                if not remote_id:
                    created.append(("retrieval", None, new_id))
                new_remote.setdefault("retrievals", {})[ret_name] = new_id

            # Upsert ingestion configs
            for cfg_name, definition in state.get("ingestion_configs", {}).items():
                if touched is not None and cfg_name not in touched.get("ingestion_configs", set()):
                    continue
                fields = definition.get("fields", {})
                payload = {"name": fields.get("name", cfg_name), **fields}

                remote_id = new_remote.get("ingestion_configs", {}).get(cfg_name)
                new_id = client.upsert_ingestion_config(remote_id=remote_id, payload=payload)

                if not remote_id:
                    created.append(("ingestion_config", None, new_id))
                new_remote.setdefault("ingestion_configs", {})[cfg_name] = new_id

            # Upsert metadata configs
            for cfg_key, definition in state.get("metadata_configs", {}).items():
                if touched is not None and cfg_key not in touched.get("metadata_configs", set()):
                    continue
                fields = definition.get("fields", {})
                topic_path = definition.get("topic", "")
                cfg_name = fields.get("name")
                if not topic_path or not cfg_name:
                    continue
                node_id = topic_id_map.get(topic_path) or new_remote.get("topics", {}).get(
                    topic_path
                )
                if not node_id:
                    continue

                cfg_payload = {
                    "name": cfg_name,
                    "type": fields.get("type", "STRING"),
                    "possible_values": fields.get("possible_values", []),
                    "default_value": fields.get("default_value"),
                    "format": fields.get("format"),
                    "filtrable": fields.get("filtrable", False),
                    "required": fields.get("required", False),
                    "in_embedding": fields.get("in_embedding", False),
                    "in_retrieval": fields.get("in_retrieval", True),
                }
                if cfg_payload["required"] and cfg_payload.get("default_value") is None:
                    raise CogSolAPIError(
                        "Default value is required for required metadata configs. "
                        f"Set default_value for '{cfg_key}'."
                    )

                cfg_remote_id = new_remote.get("metadata_configs", {}).get(cfg_key)
                if cfg_remote_id:
                    client.update_metadata_config(cfg_remote_id, cfg_payload)
                else:
                    new_cfg_id = client.create_metadata_config(node_id=node_id, payload=cfg_payload)
                    created.append(("metadata_config", node_id, new_cfg_id))
                    new_remote.setdefault("metadata_configs", {})[cfg_key] = new_cfg_id

            return new_remote

        except Exception:
            # Rollback creations in reverse order
            for kind, parent_id, obj_id in reversed(created):
                try:
                    if kind == "topic":
                        client.delete_node(obj_id)
                    elif kind == "metadata_config" and parent_id is not None:
                        client.delete_metadata_config(parent_id, obj_id)
                    elif kind == "formatter":
                        client.delete_reference_formatter(obj_id)
                    elif kind == "ingestion_config":
                        client.delete_ingestion_config(obj_id)
                    elif kind == "retrieval":
                        client.delete_retrieval(obj_id)
                except Exception:
                    continue
            raise

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
        touched: Optional[dict[str, set[str]]] = None,
    ) -> dict[str, Any]:
        client = CogSolClient(api_base, token=api_token)
        created: list[tuple[str, Optional[int], int]] = []
        new_remote = copy.deepcopy(remote_ids)

        try:
            # Upsert script tools first (shared resources).
            for tool_name, definition in state.get("tools", {}).items():
                if touched is not None and tool_name not in touched.get("tools", set()):
                    continue
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

            # Upsert retrieval tools.
            for tool_name, definition in state.get("retrieval_tools", {}).items():
                if touched is not None and tool_name not in touched.get("retrieval_tools", set()):
                    continue
                cls = class_map.get("retrieval_tools", {}).get(tool_name)
                payload = self._retrieval_tool_payload(
                    tool_name=tool_name,
                    definition=definition,
                    cls=cls,
                    project_path=project_path,
                )
                remote_id = new_remote.get("retrieval_tools", {}).get(tool_name)
                new_id = client.upsert_retrieval_tool(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("retrieval_tool", None, new_id))
                new_remote.setdefault("retrieval_tools", {})[tool_name] = new_id
                if cls is not None:
                    new_remote["retrieval_tools"][cls.__name__] = new_id
                    explicit_name = getattr(cls, "name", None)
                    if explicit_name:
                        new_remote["retrieval_tools"][explicit_name] = new_id

            # Upsert agents.
            for agent_name, definition in state.get("agents", {}).items():
                if touched is not None and agent_name not in touched.get("agents", set()):
                    continue
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
            sync_related = True
            faq_filter: dict[str, set[str]] = {}
            fixed_filter: dict[str, set[str]] = {}
            lesson_filter: dict[str, set[str]] = {}
            if touched is not None:
                for key in touched.get("faqs", set()):
                    agent, _, name = key.partition("::")
                    if agent and name:
                        faq_filter.setdefault(agent, set()).add(name)
                for key in touched.get("fixed_responses", set()):
                    agent, _, name = key.partition("::")
                    if agent and name:
                        fixed_filter.setdefault(agent, set()).add(name)
                for key in touched.get("lessons", set()):
                    agent, _, name = key.partition("::")
                    if agent and name:
                        lesson_filter.setdefault(agent, set()).add(name)
                sync_related = bool(faq_filter or fixed_filter or lesson_filter)
            if not sync_related:
                return new_remote

            agents_filter = set(faq_filter) | set(fixed_filter) | set(lesson_filter)

            for agent_name, agent_cls in class_map.get("agents", {}).items():
                if agents_filter and agent_name not in agents_filter:
                    continue
                assistant_id = new_remote.get("agents", {}).get(agent_name)
                if not assistant_id:
                    continue
                new_remote.setdefault("faqs", {}).setdefault(agent_name, {})
                new_remote.setdefault("fixed_responses", {}).setdefault(agent_name, {})
                new_remote.setdefault("lessons", {}).setdefault(agent_name, {})

                for faq_obj in getattr(agent_cls, "faqs", []) or []:
                    payload = self._faq_payload(faq_obj)
                    if faq_filter.get(agent_name) and payload["name"] not in faq_filter[agent_name]:
                        continue
                    remote_id = new_remote["faqs"][agent_name].get(payload["name"])
                    new_id = client.upsert_common_question(
                        assistant_id=assistant_id,
                        remote_id=remote_id,
                        payload=payload,
                    )
                    if not remote_id:
                        created.append(("faq", assistant_id, new_id))
                    new_remote["faqs"][agent_name][payload["name"]] = new_id

                if fixed_filter:
                    for fx_obj in getattr(agent_cls, "fixed_responses", []) or []:
                        payload = self._fixed_payload(fx_obj)
                        if (
                            fixed_filter.get(agent_name)
                            and payload["name"] not in fixed_filter[agent_name]
                        ):
                            continue
                        remote_id = new_remote["fixed_responses"][agent_name].get(payload["name"])
                        new_id = client.upsert_fixed_response(
                            assistant_id=assistant_id,
                            remote_id=remote_id,
                            payload=payload,
                        )
                        if not remote_id:
                            created.append(("fixed", assistant_id, new_id))
                        new_remote["fixed_responses"][agent_name][payload["name"]] = new_id

                if lesson_filter:
                    for lesson_obj in getattr(agent_cls, "lessons", []) or []:
                        payload = self._lesson_payload(lesson_obj)
                        if (
                            lesson_filter.get(agent_name)
                            and payload["name"] not in lesson_filter[agent_name]
                        ):
                            continue
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
                    elif kind == "retrieval_tool":
                        client.delete_retrieval_tool(obj_id)
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

    def _retrieval_tool_payload(
        self,
        *,
        tool_name: str,
        definition: dict[str, Any],
        cls: Optional[type],
        project_path: Path,
    ) -> dict[str, Any]:
        fields = definition.get("fields", {}) if definition else {}

        def _get(attr: str, default=None):
            if cls is not None and hasattr(cls, attr):
                return getattr(cls, attr)
            return fields.get(attr, default)

        def _resolve_retrieval_id(value: Any) -> int:
            if value is None:
                raise CogSolAPIError(f"retrieval is required for retrieval tool '{tool_name}'.")
            # Normalize retrieval key
            retrieval_key = value
            if isinstance(value, type) and issubclass(value, BaseRetrieval):
                retrieval_key = getattr(value, "name", None) or value.__name__
            elif hasattr(value, "__name__"):
                retrieval_key = getattr(value, "name", None) or value.__name__
            try:
                state_path = project_path / "data" / "migrations" / ".state.json"
                _, remote = self._load_content_state(state_path)
                retrieval_id = remote.get("retrievals", {}).get(retrieval_key)
            except Exception:
                retrieval_id = None
            if retrieval_id is None:
                raise CogSolAPIError(
                    "Retrieval tool requires a migrated data retrieval. "
                    f"Missing retrieval id for '{retrieval_key}'."
                )
            return int(retrieval_id)

        params = list(_get("parameters") or [])
        if not params:
            params.append(
                {
                    "name": "question",
                    "description": "Search query",
                    "type": "string",
                    "required": True,
                }
            )
        description = _get("description") or f"Retrieval tool {tool_name}"
        retrieval_id = _resolve_retrieval_id(_get("retrieval"))

        return {
            "name": _get("name") or tool_name,
            "description": description,
            "parameters": params,
            "show_tool_message": bool(_get("show_tool_message", False)),
            "show_assistant_message": bool(_get("show_assistant_message", False)),
            "edit_available": bool(_get("edit_available", True)),
            "retrieval_id": retrieval_id,
            "answer": bool(_get("answer", True)),
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

        def _resolve_tool_id(t) -> Optional[int]:
            candidates = [
                getattr(t, "name", None),
                _tool_key(t),
                getattr(t, "__name__", None),
                t.__class__.__name__,
            ]
            for name in candidates:
                if not name:
                    continue
                tool_id = remote_ids.get("tools", {}).get(name)
                if isinstance(tool_id, int):
                    return tool_id
                if isinstance(tool_id, str) and tool_id.isdigit():
                    return int(tool_id)

                retrieval_id = remote_ids.get("retrieval_tools", {}).get(name)
                if isinstance(retrieval_id, int):
                    return retrieval_id
                if isinstance(retrieval_id, str) and retrieval_id.isdigit():
                    return int(retrieval_id)
            return None

        tool_ids: list[int] = []
        for t in tools:
            remote_id = _resolve_tool_id(t)
            if remote_id:
                tool_ids.append(remote_id)

        pretool_ids: list[int] = []
        for t in pretools:
            remote_id = _resolve_tool_id(t)
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

    def _tool_helper_source(self, node: ast.AST) -> str:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ""
        fn_node = ast.fix_missing_locations(ast.copy_location(node, node))
        fn_node.decorator_list = []
        if fn_node.args.posonlyargs and fn_node.args.posonlyargs[0].arg == "self":
            fn_node.args.posonlyargs = fn_node.args.posonlyargs[1:]
        if fn_node.args.args and fn_node.args.args[0].arg == "self":
            fn_node.args.args = fn_node.args.args[1:]
        return ast.unparse(fn_node).strip()

    def _replace_self_calls(self, code: str, helper_names: list[str]) -> str:
        rewritten = code
        for name in helper_names:
            rewritten = re.sub(rf"\bself\.{name}\b", name, rewritten)
        return rewritten

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

        helper_sources: list[str] = []
        helper_names: list[str] = []
        try:
            class_source = inspect.getsource(cls)
            class_source = _normalize_code(class_source)
            tree = ast.parse(class_source)
            class_def = next(
                (
                    node
                    for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == cls.__name__
                ),
                None,
            )
            if class_def is not None:
                for node in class_def.body:
                    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    name = node.name
                    if name == "run" or (name.startswith("__") and name.endswith("__")):
                        continue
                    helper_names.append(name)
                    helper_sources.append(self._tool_helper_source(node))
        except Exception:  # pragma: no cover - best effort
            helper_sources = []
            helper_names = []

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
        dedented = self._replace_self_calls(dedented, helper_names)

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

        run_script = "\n".join(result_lines).strip()
        if "response" not in run_script:
            run_script += ("\n\n" if run_script else "") + "response = None"

        script_parts: list[str] = []
        if helper_sources:
            helper_block = "\n\n".join(helper_sources)
            helper_block = self._replace_self_calls(helper_block, helper_names)
            script_parts.append(helper_block)
        if run_script:
            script_parts.append(run_script)

        return "\n\n".join(script_parts).strip()
