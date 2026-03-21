from __future__ import annotations

import ast
import copy
import json
import os
import re
import textwrap
from pathlib import Path
from typing import Any, cast

from cogsol.agents import genconfigs
from cogsol.content import BaseRetrieval
from cogsol.core import migrations as migutils
from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.constants import (
    get_cognitive_api_base_url,
    get_content_api_base_url,
)
from cogsol.core.env import load_dotenv
from cogsol.db import migrations
from cogsol.management.base import BaseCommand


def _normalize_code(code: Any) -> str:
    if not isinstance(code, str):
        return str(code)
    code = code.replace("\r\n", "\n").rstrip()
    return textwrap.dedent(code).rstrip()


def _name_aliases(name: str) -> set[str]:
    aliases = {name}
    if name.endswith("Tool") and len(name) > 4:
        aliases.add(name[:-4])
    elif not name.endswith("Tool"):
        aliases.add(f"{name}Tool")
    return aliases


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
        apps = [str(app)] if app else ["data", "agents"]

        load_dotenv(project_path / ".env")
        api_base = get_cognitive_api_base_url()
        api_key = self._env("COGSOL_API_KEY", required=False)
        content_base = get_content_api_base_url()
        if not api_key and not os.environ.get("COGSOL_AUTH_CLIENT_ID"):
            print(
                "Error: No API credentials found.\n"
                "Set COGSOL_API_KEY in your .env file to authenticate with the CogSol API.\n"
                "\n"
                "To obtain your credentials:\n"
                "  1. Visit https://onboarding.cogsol.ai\n"
                "  2. Configure the service API key in the implantation portal\n"
                "  3. Copy the key to COGSOL_API_KEY in your .env file"
            )
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

            created: list[tuple[str, int | None, int]] = []
            try:
                touched = self._touched_entities(pending_ops)
                if app_name == "data":
                    remote_ids, created = self._sync_content_with_api(
                        api_base=content_base or api_base,
                        api_key=api_key,
                        state=temp_state,
                        remote_ids=remote_ids,
                        touched=touched,
                    )
                else:
                    remote_ids, created = self._sync_with_api(
                        api_base=api_base,
                        api_key=api_key,
                        state=temp_state,
                        remote_ids=remote_ids,
                        project_path=project_path,
                        touched=touched,
                    )

                applied.extend([mf.stem for mf in pending])
                self._save_state(state_path, temp_state, remote_ids)
                migutils.write_applied(applied_path, applied)
                print(f"Applied {len(pending)} migration(s) for app '{app_name}'.")
            except CogSolAPIError as exc:  # pragma: no cover - I/O
                print(f"API error while applying migrations: {exc}")
                exit_code = 1
                continue
            except Exception as exc:
                print(f"Error while finalizing migrations: {exc}")
                exit_code = 1
                if app_name == "data":
                    self._rollback_content_created(
                        created=created,
                        api_base=content_base or api_base,
                        api_key=api_key,
                    )
                else:
                    self._rollback_created(
                        created=created,
                        api_base=api_base,
                        api_key=api_key,
                    )
                continue

        return exit_code

    # ------------------------------------------------------------------ helpers
    def _env(self, key: str, required: bool = True) -> str | None:
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
        api_key: str | None,
        state: dict[str, Any],
        remote_ids: dict[str, Any],
        touched: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, Any], list[tuple[str, int | None, int]]]:
        """Sync Content API entities (topics, formatters, retrievals) with the API."""
        client = CogSolClient(api_base, api_key=api_key, content_base_url=api_base)
        created: list[tuple[str, int | None, int]] = []
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

            return new_remote, created

        except Exception:
            # Rollback creations in reverse order
            for kind, parent_id, obj_id in reversed(created):
                try:
                    self._delete_content_created_entry(client, kind, parent_id, obj_id)
                except Exception as e:
                    print(f"Warning: failed to rollback {kind} {obj_id}: {e}")
                    continue
            raise

    def _sync_with_api(
        self,
        *,
        api_base: str,
        api_key: str | None,
        state: dict[str, Any],
        remote_ids: dict[str, Any],
        project_path: Path,
        touched: dict[str, set[str]] | None = None,
    ) -> tuple[dict[str, Any], list[tuple[str, int | None, int]]]:
        client = CogSolClient(api_base, api_key=api_key)
        created: list[tuple[str, int | None, int]] = []
        new_remote = copy.deepcopy(remote_ids)

        try:
            # Upsert script tools first (shared resources).
            for tool_name, definition in state.get("tools", {}).items():
                if touched is not None and tool_name not in touched.get("tools", set()):
                    continue
                payload = self._tool_payload(tool_name, definition)
                remote_id = new_remote.get("tools", {}).get(tool_name)
                if remote_id is None and payload.get("name"):
                    remote_id = new_remote.get("tools", {}).get(str(payload["name"]))
                new_id = client.upsert_script(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("tool", None, new_id))
                new_remote.setdefault("tools", {})[tool_name] = new_id
                if payload.get("name"):
                    new_remote["tools"][str(payload["name"])] = new_id
                for alias in _name_aliases(tool_name):
                    new_remote["tools"][alias] = new_id

            # Upsert retrieval tools.
            for tool_name, definition in state.get("retrieval_tools", {}).items():
                if touched is not None and tool_name not in touched.get("retrieval_tools", set()):
                    continue
                payload = self._retrieval_tool_payload(
                    tool_name=tool_name,
                    definition=definition,
                    project_path=project_path,
                )
                remote_id = new_remote.get("retrieval_tools", {}).get(tool_name)
                if remote_id is None and payload.get("name"):
                    remote_id = new_remote.get("retrieval_tools", {}).get(str(payload["name"]))
                new_id = client.upsert_retrieval_tool(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("retrieval_tool", None, new_id))
                new_remote.setdefault("retrieval_tools", {})[tool_name] = new_id
                if payload.get("name"):
                    new_remote["retrieval_tools"][str(payload["name"])] = new_id
                for alias in _name_aliases(tool_name):
                    new_remote["retrieval_tools"][alias] = new_id

            agents_with_faqs = self._agents_from_related_bucket(state.get("faqs", {}))
            agents_with_fixed = self._agents_from_related_bucket(state.get("fixed_responses", {}))
            agents_with_lessons = self._agents_from_related_bucket(state.get("lessons", {}))

            # Upsert agents.
            for agent_name, definition in state.get("agents", {}).items():
                if touched is not None and agent_name not in touched.get("agents", set()):
                    continue
                payload = self._assistant_payload(
                    agent_name=agent_name,
                    definition=definition,
                    remote_ids=new_remote,
                    faq_available=agent_name in agents_with_faqs,
                    fixed_available=agent_name in agents_with_fixed,
                    lessons_available=agent_name in agents_with_lessons,
                )
                remote_id = new_remote.get("agents", {}).get(agent_name)
                new_id = client.upsert_assistant(remote_id=remote_id, payload=payload)
                if not remote_id:
                    created.append(("assistant", None, new_id))
                new_remote.setdefault("agents", {})[agent_name] = new_id

            # Upsert FAQs (common questions), fixed responses, lessons per agent from migration state.
            for key, definition in state.get("faqs", {}).items():
                if touched is not None and key not in touched.get("faqs", set()):
                    continue
                fields = definition.get("fields", {}) if definition else {}
                agent_name = str(fields.get("agent") or str(key).partition("::")[0])
                assistant_id = new_remote.get("agents", {}).get(agent_name)
                if not assistant_id:
                    continue
                payload = self._faq_payload_from_fields(str(key), fields)
                new_remote.setdefault("faqs", {}).setdefault(agent_name, {})
                remote_id = new_remote["faqs"][agent_name].get(payload["name"])
                new_id = client.upsert_common_question(
                    assistant_id=assistant_id,
                    remote_id=remote_id,
                    payload=payload,
                )
                if not remote_id:
                    created.append(("faq", assistant_id, new_id))
                new_remote["faqs"][agent_name][payload["name"]] = new_id

            for key, definition in state.get("fixed_responses", {}).items():
                if touched is not None and key not in touched.get("fixed_responses", set()):
                    continue
                fields = definition.get("fields", {}) if definition else {}
                agent_name = str(fields.get("agent") or str(key).partition("::")[0])
                assistant_id = new_remote.get("agents", {}).get(agent_name)
                if not assistant_id:
                    continue
                payload = self._fixed_payload_from_fields(str(key), fields)
                new_remote.setdefault("fixed_responses", {}).setdefault(agent_name, {})
                remote_id = new_remote["fixed_responses"][agent_name].get(payload["name"])
                new_id = client.upsert_fixed_response(
                    assistant_id=assistant_id,
                    remote_id=remote_id,
                    payload=payload,
                )
                if not remote_id:
                    created.append(("fixed", assistant_id, new_id))
                new_remote["fixed_responses"][agent_name][payload["name"]] = new_id

            for key, definition in state.get("lessons", {}).items():
                if touched is not None and key not in touched.get("lessons", set()):
                    continue
                fields = definition.get("fields", {}) if definition else {}
                agent_name = str(fields.get("agent") or str(key).partition("::")[0])
                assistant_id = new_remote.get("agents", {}).get(agent_name)
                if not assistant_id:
                    continue
                payload = self._lesson_payload_from_fields(str(key), fields)
                new_remote.setdefault("lessons", {}).setdefault(agent_name, {})
                remote_id = new_remote["lessons"][agent_name].get(payload["name"])
                new_id = client.upsert_lesson(
                    assistant_id=assistant_id,
                    remote_id=remote_id,
                    payload=payload,
                )
                if not remote_id:
                    created.append(("lesson", assistant_id, new_id))
                new_remote["lessons"][agent_name][payload["name"]] = new_id

            return new_remote, created
        except Exception:
            # Rollback creations in reverse order.
            for kind, assistant_id, obj_id in reversed(created):
                try:
                    self._delete_created_entry(client, kind, assistant_id, obj_id)
                except Exception as e:
                    print(f"Warning: failed to rollback {kind} {obj_id}: {e}")
                    continue
            raise

    def _delete_created_entry(
        self, client: CogSolClient, kind: str, parent_id: int | None, obj_id: int
    ) -> None:
        if kind == "faq" and parent_id is not None:
            client.delete_common_question(parent_id, obj_id)
        elif kind == "fixed" and parent_id is not None:
            client.delete_fixed_response(parent_id, obj_id)
        elif kind == "lesson" and parent_id is not None:
            client.delete_lesson(parent_id, obj_id)
        elif kind == "assistant":
            client.delete_assistant(obj_id)
        elif kind == "tool":
            client.delete_script(obj_id)
        elif kind == "retrieval_tool":
            client.delete_retrieval_tool(obj_id)

    def _delete_content_created_entry(
        self, client: CogSolClient, kind: str, parent_id: int | None, obj_id: int
    ) -> None:
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

    def _rollback_created(
        self, *, created: list[tuple[str, int | None, int]], api_base: str, api_key: str | None
    ) -> None:
        if not created:
            return
        client = CogSolClient(api_base, api_key=api_key)
        for kind, assistant_id, obj_id in reversed(created):
            try:
                self._delete_created_entry(client, kind, assistant_id, obj_id)
            except Exception as e:
                print(f"Warning: failed to rollback {kind} {obj_id}: {e}")
                continue

    def _rollback_content_created(
        self, *, created: list[tuple[str, int | None, int]], api_base: str, api_key: str | None
    ) -> None:
        if not created:
            return
        client = CogSolClient(api_base, api_key=api_key, content_base_url=api_base)
        for kind, parent_id, obj_id in reversed(created):
            try:
                self._delete_content_created_entry(client, kind, parent_id, obj_id)
            except Exception as e:
                print(f"Warning: failed to rollback {kind} {obj_id}: {e}")
                continue

    def _tool_payload(
        self,
        tool_name: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        fields = definition.get("fields", {}) if definition else {}

        params: list[dict[str, Any]] = []
        raw_params = fields.get("parameters", {})
        if isinstance(raw_params, dict):
            for name, meta in raw_params.items():
                meta = meta or {}
                param_entry = {
                    "name": str(name),
                    "description": meta.get("description") or str(name),
                    "type": meta.get("type") or "string",
                    "required": bool(meta.get("required", True)),
                }
                if param_entry["type"] == "array" and "items" in meta:
                    param_entry["items"] = meta["items"]
                params.append(param_entry)
        elif isinstance(raw_params, list):
            for item in raw_params:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "")
                if not name:
                    continue
                param_entry = {
                    "name": name,
                    "description": item.get("description") or name,
                    "type": item.get("type") or "string",
                    "required": bool(item.get("required", True)),
                }
                if param_entry["type"] == "array" and "items" in item:
                    param_entry["items"] = item["items"]
                params.append(param_entry)

        description = fields.get("description") or f"Tool {tool_name}"
        code = self._tool_script_from_state(fields)
        code = code or "# TODO: provide implementation\nresponse = None"

        return {
            "name": fields.get("name") or tool_name,
            "description": description,
            "parameters": params,
            "show_tool_message": bool(fields.get("show_tool_message", False)),
            "show_assistant_message": bool(fields.get("show_assistant_message", False)),
            "edit_available": bool(fields.get("edit_available", True)),
            "code": code,
        }

    def _retrieval_tool_payload(
        self,
        *,
        tool_name: str,
        definition: dict[str, Any],
        project_path: Path,
    ) -> dict[str, Any]:
        fields = definition.get("fields", {}) if definition else {}

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

        params = list(fields.get("parameters") or [])
        if not any(p.get("name") == "question" for p in params):
            params.insert(
                0,
                {
                    "name": "question",
                    "description": "Search query",
                    "type": "string",
                    "required": True,
                },
            )
        description = fields.get("description") or f"Retrieval tool {tool_name}"
        retrieval_id = _resolve_retrieval_id(fields.get("retrieval"))

        return {
            "name": fields.get("name") or tool_name,
            "description": description,
            "parameters": params,
            "show_tool_message": bool(fields.get("show_tool_message", False)),
            "show_assistant_message": bool(fields.get("show_assistant_message", False)),
            "edit_available": bool(fields.get("edit_available", True)),
            "retrieval_id": retrieval_id,
            "answer": bool(fields.get("answer", True)),
        }

    def _assistant_payload(
        self,
        *,
        agent_name: str,
        definition: dict[str, Any],
        remote_ids: dict[str, Any],
        faq_available: bool,
        fixed_available: bool,
        lessons_available: bool,
    ) -> dict[str, Any]:
        fields = definition.get("fields", {}) if definition else {}
        meta = definition.get("meta", {}) if definition else {}

        def _get(attr: str, default=None):
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

        def _resolve_tool_id(raw: Any) -> int | None:
            candidates: list[str] = []
            if isinstance(raw, str):
                candidates.append(raw)
            elif isinstance(raw, dict) and raw.get("name"):
                candidates.append(str(raw.get("name")))
            if not candidates and raw is not None:
                candidates.append(str(raw))

            for candidate in candidates:
                for alias in _name_aliases(candidate):
                    tool_id = remote_ids.get("tools", {}).get(alias)
                    if isinstance(tool_id, int):
                        return tool_id
                    if isinstance(tool_id, str) and tool_id.isdigit():
                        return int(tool_id)
                    retrieval_id = remote_ids.get("retrieval_tools", {}).get(alias)
                    if isinstance(retrieval_id, int):
                        return retrieval_id
                    if isinstance(retrieval_id, str) and retrieval_id.isdigit():
                        return int(retrieval_id)
            return None

        tool_ids: list[int] = []
        for t in list(_get("tools", []) or []):
            remote_id = _resolve_tool_id(t)
            if remote_id:
                tool_ids.append(remote_id)

        pretool_ids: list[int] = []
        for t in list(_get("pretools", []) or []):
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
            "system_prompt": str(_get("system_prompt") or ""),
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
            "faq_available": bool(faq_available or fields.get("faqs")),
            "fixed_available": bool(fixed_available or fields.get("fixed_responses")),
            "lessons_available": bool(lessons_available or fields.get("lessons")),
            "realtime_available": bool(_get("realtime", False)),
            "info": None,
            "colors": colors,
            "logo": _get_meta("logo_url"),
            "streaming_available": bool(_get("streaming", False)),
            "tools": tool_ids,
            "pretools": pretool_ids,
        }
        return payload

    def _agents_from_related_bucket(self, bucket: dict[str, Any]) -> set[str]:
        agents: set[str] = set()
        for key, definition in (bucket or {}).items():
            fields = definition.get("fields", {}) if isinstance(definition, dict) else {}
            agent_name = str(fields.get("agent") or str(key).partition("::")[0]).strip()
            if agent_name:
                agents.add(agent_name)
        return agents

    def _faq_payload_from_fields(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        _, _, default_name = key.partition("::")
        name = str(fields.get("name") or default_name or key)
        content = str(fields.get("content") or "")
        return {
            "name": name,
            "content": content,
            "additional_metadata": {},
        }

    def _fixed_payload_from_fields(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        _, _, default_name = key.partition("::")
        name = str(fields.get("name") or default_name or key)
        content = str(fields.get("content") or "")
        meta = fields.get("meta")
        topic = None
        if isinstance(meta, dict):
            topic = meta.get("topic")
        topic = topic or name
        return {
            "topic": topic,
            "content": content,
            "name": name,
            "additional_metadata": {},
        }

    def _lesson_payload_from_fields(self, key: str, fields: dict[str, Any]) -> dict[str, Any]:
        _, _, default_name = key.partition("::")
        name = str(fields.get("name") or default_name or key)
        content = str(fields.get("content") or "")
        context = "general"
        meta = fields.get("meta")
        if isinstance(meta, dict):
            context = str(meta.get("context_of_application") or "general")
        return {
            "name": name,
            "content": content,
            "context_of_application": context,
            "additional_metadata": {},
        }

    def _tool_script_from_state(self, fields: dict[str, Any]) -> str:
        raw_code = fields.get("__code__")
        if not isinstance(raw_code, str) or not raw_code.strip():
            return ""
        code = _normalize_code(raw_code)
        if not code:
            return ""
        params_to_bind = self._tool_param_names_from_fields(fields.get("parameters"))
        return self._tool_script_from_code(code, params_to_bind)

    def _tool_param_names_from_fields(self, raw_params: Any) -> list[str]:
        names: list[str] = []
        if isinstance(raw_params, dict):
            names = [str(k) for k in raw_params]
        elif isinstance(raw_params, list):
            for item in raw_params:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
        return names

    def _tool_script_from_code(self, code: str, params_to_bind: list[str]) -> str:
        normalized = _normalize_code(code)
        try:
            tree = ast.parse(normalized)
        except SyntaxError:
            script = normalized.strip()
            if script and "response" not in script:
                script += "\n\nresponse = None"
            return script

        fn_nodes = [
            node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        run_node = next((node for node in fn_nodes if node.name == "run"), None)
        helper_nodes = [
            node
            for node in fn_nodes
            if node is not run_node
            and not (node.name.startswith("__") and node.name.endswith("__"))
        ]
        helper_names = [node.name for node in helper_nodes]
        helper_sources = [
            src
            for src in (self._tool_helper_source(node, normalized) for node in helper_nodes)
            if src
        ]

        if run_node is None:
            helper_block = self._replace_self_calls(
                "\n\n".join(helper_sources), helper_names
            ).strip()
            if helper_block and "response" not in helper_block:
                helper_block += "\n\nresponse = None"
            return helper_block

        if not params_to_bind:
            params_to_bind = self._tool_param_names_from_run_node(run_node)

        run_body = self._run_body_source(run_node, normalized)
        run_body = self._replace_self_calls(run_body, helper_names)

        result_lines: list[str] = []
        for p in params_to_bind:
            result_lines.append(f"{p} = params.get('{p}') if params else None")
        for line in run_body.splitlines():
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
            helper_block = self._replace_self_calls("\n\n".join(helper_sources), helper_names)
            script_parts.append(helper_block.strip())
        if run_script:
            script_parts.append(run_script)
        return "\n\n".join(part for part in script_parts if part).strip()

    def _tool_param_names_from_run_node(self, run_node: ast.AST) -> list[str]:
        if not isinstance(run_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return []
        ignore = {"self", "chat", "data", "secrets", "log", "params"}
        names: list[str] = []
        arg_nodes = (
            list(run_node.args.posonlyargs)
            + list(run_node.args.args)
            + list(run_node.args.kwonlyargs)
        )
        for arg in arg_nodes:
            if arg.arg in ignore or arg.arg in names:
                continue
            names.append(arg.arg)
        return names

    def _node_source(self, node: ast.AST, source: str) -> str:
        segment = ast.get_source_segment(source, node)
        if segment:
            return segment
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    def _relative_node_source(self, node: ast.AST, source: str) -> str:
        segment = self._node_source(node, source)
        if not segment:
            return ""
        lines = segment.splitlines()
        if len(lines) <= 1:
            return segment
        indent = max(getattr(node, "col_offset", 0), 0)
        normalized = [lines[0]]
        for line in lines[1:]:
            if line.startswith(" " * indent):
                normalized.append(line[indent:])
            else:
                normalized.append(line.lstrip() if line.strip() else "")
        return "\n".join(normalized)

    def _function_body_source(self, node: ast.AST, source: str) -> str:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ""
        body_parts = [
            part
            for part in (self._relative_node_source(stmt, source) for stmt in node.body)
            if part
        ]
        return _normalize_code("\n".join(body_parts))

    def _source_offset(self, source: str, node: ast.AST, target: ast.AST) -> int:
        if (
            not hasattr(node, "lineno")
            or not hasattr(target, "lineno")
            or not hasattr(target, "col_offset")
        ):
            return len(source)
        lines = source.splitlines(keepends=True)
        line_index = max(target.lineno - node.lineno, 0)
        if line_index >= len(lines):
            return len(source)
        offset = sum(len(line) for line in lines[:line_index])
        if line_index == 0:
            col = max(target.col_offset - getattr(node, "col_offset", 0), 0)
        else:
            col = max(target.col_offset, 0)
        return cast(int, min(offset + col, len(source)))

    def _strip_first_self_param(self, signature: str) -> str:
        updated = re.sub(r"(\(\s*)self(\s*,\s*)", r"\1", signature, count=1)
        return re.sub(r"(\(\s*)self(\s*\))", r"\1\2", updated, count=1)

    def _run_body_source(self, run_node: ast.AST, source: str) -> str:
        return self._function_body_source(run_node, source)

    def _tool_helper_source(self, node: ast.AST, source: str) -> str:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ""
        helper_src = self._node_source(node, source)
        if not helper_src:
            return ""
        body_source = self._function_body_source(node, source)
        header_source = helper_src
        if node.body:
            header_source = helper_src[: self._source_offset(helper_src, node, node.body[0])]
        header_source = self._strip_first_self_param(header_source.rstrip())
        if not body_source:
            return _normalize_code(header_source)
        return _normalize_code(f"{header_source}\n{textwrap.indent(body_source, '    ')}")

    def _replace_self_calls(self, code: str, helper_names: list[str]) -> str:
        rewritten = code
        for name in helper_names:
            rewritten = re.sub(rf"\bself\.{name}\b", name, rewritten)
        return rewritten
