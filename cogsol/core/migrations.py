from __future__ import annotations

import datetime
import importlib.util
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cogsol.db import migrations as ops


def empty_state() -> dict[str, dict[str, dict[str, Any]]]:
    return {
        "agents": {},
        "tools": {},
        "lessons": {},
        "faqs": {},
        "fixed_responses": {},
    }


def _load_migration_module(path: Path):
    module_name = f"cogsol_migration_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load migration module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_migration_module(path: Path):
    """Public wrapper for loading migration modules from disk."""
    return _load_migration_module(path)


def iter_migration_files(migrations_path: Path) -> Iterable[Path]:
    if not migrations_path.exists():
        return []
    return sorted(
        [p for p in migrations_path.glob("*.py") if p.name != "__init__.py"],
        key=lambda p: p.name,
    )


def state_from_migrations(migrations_path: Path) -> dict[str, Any]:
    state = empty_state()
    for path in iter_migration_files(migrations_path):
        module = _load_migration_module(path)
        migration_cls = getattr(module, "Migration", None)
        if migration_cls is None:
            continue
        migration = migration_cls() if callable(migration_cls) else migration_cls
        ops.apply_operations(state, getattr(migration, "operations", []))
    return state


def _diff_bucket(entity: str, prev_defs: dict[str, Any], current_defs: dict[str, Any]) -> list[Any]:
    operations: list[Any] = []
    create_cls = {
        "agents": ops.CreateAgent,
        "tools": ops.CreateTool,
        "lessons": ops.CreateLesson,
        "faqs": ops.CreateFAQ,
        "fixed_responses": ops.CreateFixedResponse,
    }[entity]

    for name, definition in current_defs.items():
        if name not in prev_defs:
            fields = definition.get("fields", {})
            if entity == "agents":
                operations.append(
                    create_cls(
                        name=name,
                        fields=fields,
                        meta=definition.get("meta", {}),
                    )
                )
            else:
                operations.append(create_cls(name=name, fields=fields))
            continue

        prev_fields = prev_defs[name].get("fields", {})
        curr_fields = definition.get("fields", {})
        for field_name, value in curr_fields.items():
            if prev_fields.get(field_name) != value:
                operations.append(
                    ops.AlterField(
                        model_name=name,
                        name=field_name,
                        value=value,
                        entity=entity,
                        scope="fields",
                    )
                )

        if entity == "agents":
            prev_meta = prev_defs[name].get("meta", {})
            curr_meta = definition.get("meta", {})
            for meta_name, meta_val in curr_meta.items():
                if prev_meta.get(meta_name) != meta_val:
                    operations.append(
                        ops.AlterField(
                            model_name=name,
                            name=meta_name,
                            value=meta_val,
                            entity=entity,
                            scope="meta",
                        )
                    )

    for name in prev_defs:
        if name not in current_defs:
            operations.append(ops.DeleteDefinition(name=name, entity=entity))

    return operations


def diff_states(previous: dict[str, Any], current: dict[str, Any]) -> list[Any]:
    operations: list[Any] = []
    for entity in ["tools", "lessons", "faqs", "fixed_responses", "agents"]:
        operations.extend(
            _diff_bucket(
                entity,
                previous.get(entity, {}),
                current.get(entity, {}),
            )
        )
    return operations


def format_operations(operations: Iterable[Any]) -> list[str]:
    lines: list[str] = []
    for op in operations:
        if isinstance(op, ops.AlterField):
            lines.append(
                f"        migrations.AlterField(model_name={op.model_name!r}, "
                f"name={op.name!r}, value={op.value!r}, "
                f"entity={op.entity!r}, scope={op.scope!r}),"
            )
        elif isinstance(op, ops.CreateDefinition):
            cls_name = op.__class__.__name__
            meta_arg = f", meta={op.meta!r}" if op.meta else ""
            lines.append(
                f"        migrations.{cls_name}(name={op.name!r}, "
                f"fields={op.fields!r}{meta_arg}),"
            )
        elif isinstance(op, ops.DeleteDefinition):
            lines.append(
                f"        migrations.DeleteDefinition(name={op.name!r}, entity={op.entity!r}),"
            )
        else:
            lines.append(f"        {repr(op)},")
    return lines


def next_migration_name(migrations_path: Path, explicit_name: str | None = None) -> str:
    existing = list(iter_migration_files(migrations_path))
    if not existing:
        return "0001_initial"
    last = existing[-1].stem
    try:
        last_num = int(last.split("_", 1)[0])
    except (ValueError, IndexError):
        last_num = len(existing)
    next_num = last_num + 1
    suffix = explicit_name or datetime.datetime.now().strftime("auto_%Y%m%d_%H%M")
    return f"{next_num:04d}_{suffix}"


def load_applied(applied_path: Path) -> list[str]:
    if not applied_path.exists():
        return []
    data = json.loads(applied_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def write_applied(applied_path: Path, applied: list[str]) -> None:
    applied_path.write_text(json.dumps(applied, indent=2), encoding="utf-8")


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
