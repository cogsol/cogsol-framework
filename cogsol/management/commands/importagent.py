from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, cast

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.core.loader import (
    _extract_tool_params,
    collect_content_definitions,
    collect_definitions,
)
from cogsol.core.migrations import next_migration_name
from cogsol.management.base import BaseCommand


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _camelize(value: str, suffix: str = "") -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    name = "".join(p.capitalize() for p in parts if p)
    return f"{name}{suffix}" if name else suffix


def _safe_class_name(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", name).strip()
    if not cleaned:
        return fallback
    return _camelize(cleaned, "")


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ensure_import(path: Path, import_line: str) -> None:
    if not path.exists():
        _write_file(path, import_line + "\n")
        return
    existing = path.read_text(encoding="utf-8")
    if import_line in existing:
        return
    _write_file(path, import_line + "\n" + existing)


def _append_block(path: Path, block: str, marker: str) -> bool:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        return False
    if existing and not existing.endswith("\n"):
        existing += "\n"
    content = existing + "\n" + block.strip() + "\n"
    _write_file(path, content)
    return True


def _import_module(module_name: str, project_path: Path):
    import importlib
    import sys

    sys.path.insert(0, str(project_path))
    try:
        importlib.invalidate_caches()
        if module_name in sys.modules:
            return importlib.reload(sys.modules[module_name])
        return importlib.import_module(module_name)
    finally:
        try:
            sys.path.remove(str(project_path))
        except ValueError:
            pass


def _dedent_source(source: str) -> str:
    import textwrap

    return textwrap.dedent(source.replace("\r\n", "\n")).rstrip()


def _format_params_decorator(params: list[dict[str, Any]]) -> str:
    if not params:
        return ""
    lines = ["@tool_params("]
    for p in params:
        desc = p.get("description") or p.get("name")
        typ = p.get("type") or "string"
        req = p.get("required", True)
        lines.append(
            f"    {p['name']}={{\"description\": {desc!r}, \"type\": {typ!r}, \"required\": {bool(req)}}},"
        )
    lines.append(")")
    return "\n".join(lines)


def _normalize_params(params: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for p in params or []:
        name = p.get("name")
        if not name:
            continue
        normalized[name] = {
            "description": p.get("description") or name,
            "type": p.get("type") or "string",
            "required": bool(p.get("required", True)),
        }
    return normalized


def _strip_class_refs(definitions: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in definitions.items():
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if k != "class"}
            cleaned[key] = _strip_class_refs(value)
        elif isinstance(value, list):
            cleaned[key] = [
                {k: v for k, v in item.items() if k != "class"} if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def _tool_class_from_script(script: dict[str, Any]) -> str:
    name = script.get("name") or "Tool"
    base_name = _safe_class_name(name, "ImportedTool")
    class_name = base_name if base_name.endswith("Tool") else base_name + "Tool"
    description = script.get("description") or f"Tool {name}"
    params = script.get("parameters") or []
    decorator = _format_params_decorator(params)

    # Build run signature
    param_names = [p["name"] for p in params if p.get("name")]
    signature_params = ", ".join([f"{p}: str = None" for p in param_names])
    signature_params = (", " + signature_params) if signature_params else ""

    code = script.get("code") or ""
    code = _rewrite_script_code(code, param_names)
    code = code.strip()
    if code and not code.endswith("\n"):
        code += "\n"
    indented_code = "\n".join(
        f"        {line}" if line.strip() else "" for line in code.splitlines()
    )
    if not indented_code:
        indented_code = "        response = None"
    template = f"""
class {class_name}(BaseTool):
    description = {description!r}
    name = {name!r}

    {decorator if decorator else ""}
    def run(self, chat=None, data=None, secrets=None, log=None{signature_params}):
        # Imported from CogSol API
{indented_code}
        return response
"""
    return "\n".join(line.rstrip() for line in template.strip().splitlines())


def _retrieval_tool_class_name(tool: dict[str, Any]) -> str:
    name = tool.get("name") or "Search"
    base_name = _safe_class_name(name, "Search")
    return base_name if base_name.endswith("Search") else base_name + "Search"


def _retrieval_tool_class_from_api(tool: dict[str, Any], retrieval_name: Optional[str]) -> str:
    name = tool.get("name") or "Search"
    class_name = _retrieval_tool_class_name(tool)
    description = tool.get("description") or f"Retrieval tool {name}"
    params = list(tool.get("parameters") or [])
    if not params:
        params.append(
            {
                "name": "question",
                "description": "Search query",
                "type": "string",
                "required": True,
            }
        )
    retrieval_value = retrieval_name if retrieval_name is not None else None

    template = f"""
class {class_name}(BaseRetrievalTool):
    \"\"\"Retrieval tool imported from CogSol API.\"\"\"

    name = {name!r}
    description = {description!r}
    retrieval = {retrieval_value!r}
    parameters = {params!r}
    show_tool_message = {bool(tool.get("show_tool_message", False))}
    show_assistant_message = {bool(tool.get("show_assistant_message", False))}
    edit_available = {bool(tool.get("edit_available", True))}
    answer = {bool(tool.get("answer", True))}
"""
    return "\n".join(line.rstrip() for line in template.strip().splitlines())


def _rewrite_script_code(code: str, param_names: list[str]) -> str:
    """
    Convert API-style params usage into direct argument usage.
    Removes param binding lines and replaces params['x'] / params.get('x') with x.
    """
    if not code or not param_names:
        return code
    lines = []
    for line in code.splitlines():
        stripped = line.strip()
        skip = False
        for p in param_names:
            if stripped.startswith(f"{p} = params.get(") or stripped.startswith(f"{p}=params.get("):
                skip = True
                break
        if not skip:
            lines.append(line)

    rewritten = "\n".join(lines)
    for p in param_names:
        rewritten = rewritten.replace(f"params.get('{p}')", p)
        rewritten = rewritten.replace(f'params.get("{p}")', p)
        rewritten = rewritten.replace(f"params['{p}']", p)
        rewritten = rewritten.replace(f'params["{p}"]', p)
    return rewritten


def _topic_class_name(name: str) -> str:
    base = _safe_class_name(name, "Topic")
    return base if base.endswith("Topic") else base + "Topic"


def _retrieval_class_name(name: str) -> str:
    base = _safe_class_name(name, "Retrieval")
    return base if base.endswith("Retrieval") else base + "Retrieval"


def _formatter_class_name(name: str) -> str:
    base = _safe_class_name(name, "Formatter")
    return base if base.endswith("Formatter") else base + "Formatter"


def _faq_class(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("question") or "FAQ"
    cls_name = _safe_class_name(name, "FAQ") + "FAQ"
    content = item.get("content") or ""
    return f"""class {cls_name}(BaseFAQ):\n    question = {name!r}\n    answer = {content!r}\n"""


def _fixed_class(item: dict[str, Any]) -> str:
    name = item.get("name") or item.get("topic") or "Fixed"
    cls_name = _safe_class_name(name, "Fixed") + "Fixed"
    content = item.get("content") or ""
    return f"""class {cls_name}(BaseFixedResponse):\n    key = {name!r}\n    response = {content!r}\n"""


def _lesson_class(item: dict[str, Any]) -> str:
    name = item.get("name") or "Lesson"
    cls_name = _safe_class_name(name, "Lesson") + "Lesson"
    content = item.get("content") or ""
    context = item.get("context_of_application") or "general"
    return (
        f"class {cls_name}(BaseLesson):\n"
        f"    name = {name!r}\n"
        f"    content = {content!r}\n"
        f"    context_of_application = {context!r}\n"
    )


class Command(BaseCommand):
    help = "Import an existing CogSol assistant into the local project."

    def add_arguments(self, parser):
        parser.add_argument(
            "assistant_id", type=int, help="Assistant ID to import from CogSol API."
        )
        parser.add_argument("app", nargs="?", default="agents", help="App name. Default: agents.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        load_dotenv(project_path / ".env")

        assistant_id = cast(int, options.get("assistant_id"))
        app = str(options.get("app") or "agents")

        import os

        api_base = os.environ.get("COGSOL_API_BASE")
        api_token = os.environ.get("COGSOL_API_TOKEN")
        content_base = os.environ.get("COGSOL_CONTENT_API_BASE") or api_base
        if not api_base:
            print("COGSOL_API_BASE is required in .env to import.")
            return 1

        client = CogSolClient(api_base, token=api_token, content_base_url=content_base)
        try:
            assistant = client.get_assistant(assistant_id)
            faqs = client.list_common_questions(assistant_id) or []
            fixed = client.list_fixed_responses(assistant_id) or []
            lessons = client.list_lessons(assistant_id) or []
        except CogSolAPIError as exc:
            print(f"API error: {exc}")
            return 1

        import_messages: list[str] = []

        # Build agent folder
        agent_desc = assistant.get("description") or f"Assistant {assistant_id}"
        slug = _slugify(agent_desc) or f"assistant_{assistant_id}"
        class_name = _safe_class_name(agent_desc, f"Assistant{assistant_id}") + "Agent"
        agent_dir = project_path / app / slug
        prompts_dir = agent_dir / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)

        prompt_file = prompts_dir / f"{slug}.md"
        prompt_text = assistant.get("system_prompt") or ""
        _write_file(prompt_file, prompt_text)

        # Write faqs/fixed/lessons modules
        faqs_body = "\n\n".join(_faq_class(item) for item in faqs) or "# No FAQs"
        fixed_body = "\n\n".join(_fixed_class(item) for item in fixed) or "# No fixed responses"
        lessons_body = "\n\n".join(_lesson_class(item) for item in lessons) or "# No lessons"
        _write_file(
            agent_dir / "faqs.py", "from cogsol.tools import BaseFAQ\n\n" + faqs_body + "\n"
        )
        _write_file(
            agent_dir / "fixed.py",
            "from cogsol.tools import BaseFixedResponse\n\n" + fixed_body + "\n",
        )
        _write_file(
            agent_dir / "lessons.py",
            "from cogsol.tools import BaseLesson\n\n" + lessons_body + "\n",
        )

        # Write agent.py
        gen_main = assistant.get("generation_config")
        gen_pre = assistant.get("generation_config_pretools")
        gen_main_expr = "genconfigs.QA()" if str(gen_main).upper() == "QA" else repr(gen_main)
        gen_pre_expr = "genconfigs.QA()" if str(gen_pre).upper() == "QA" else repr(gen_pre)

        has_retrieval_tools = False
        agent_py = f"""from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import *


class {class_name}(BaseAgent):
    system_prompt = Prompts.load("{slug}.md")
    generation_config = {gen_main_expr}
    pregeneration_config = {gen_pre_expr}
    tools = []
    pretools = []
    max_responses = {assistant.get("max_responses") or 0}
    max_msg_length = {assistant.get("max_msg_length") or 0}
    max_consecutive_tool_calls = {assistant.get("max_consecutive_tool_calls") or 0}
    temperature = {assistant.get("temperature") or 0.0}

    class Meta:
        name = {class_name!r}
        chat_name = {agent_desc!r}
        logo_url = {assistant.get("logo")!r}
"""
        _write_file(agent_dir / "agent.py", agent_py)
        _write_file(agent_dir / "__init__.py", f"from .agent import {class_name}\n")
        import_messages.append(f"Agent: {class_name} -> {agent_dir}")

        # Tools import
        tools_ids = assistant.get("tools") or []
        pretools_ids = assistant.get("pretools") or []
        scripts: list[dict[str, Any]] = []
        scripts_by_id: dict[int, dict[str, Any]] = {}
        retrieval_tools: list[dict[str, Any]] = []
        retrieval_tools_by_id: dict[int, dict[str, Any]] = {}
        retrieval_cache: dict[int, Optional[str]] = {}

        def _resolve_retrieval_name(retrieval_id: Optional[int]) -> Optional[str]:
            if not retrieval_id:
                return None
            if retrieval_id in retrieval_cache:
                return retrieval_cache[retrieval_id]
            try:
                data = client.get_retrieval(int(retrieval_id))
            except CogSolAPIError:
                retrieval_cache[retrieval_id] = None
                return None
            name = None
            if isinstance(data, dict):
                name = data.get("name") or data.get("description")
            retrieval_cache[retrieval_id] = name
            return name

        for tool_id in tools_ids + pretools_ids:
            try:
                script = client.get_script(tool_id)
                scripts.append(script)
                scripts_by_id[int(tool_id)] = script
            except CogSolAPIError:
                try:
                    retrieval_tool = client.get_retrieval_tool(tool_id)
                    retrieval_id = retrieval_tool.get("retrieval_id")
                    retrieval_name = _resolve_retrieval_name(retrieval_id)
                    retrieval_tool["_retrieval_name"] = retrieval_name
                    retrieval_tools.append(retrieval_tool)
                    retrieval_tools_by_id[int(tool_id)] = retrieval_tool
                except CogSolAPIError as exc2:
                    print(f"Warning: could not import tool {tool_id}: {exc2}")

        tools_file = project_path / app / "tools.py"
        existing = tools_file.read_text(encoding="utf-8") if tools_file.exists() else ""
        if not tools_file.exists():
            _write_file(tools_file, "from cogsol.tools import BaseTool, tool_params\n\n")
            existing = tools_file.read_text(encoding="utf-8")

        additions = []
        for script in scripts:
            class_def = _tool_class_from_script(script)
            cls_name = class_def.split()[1].split("(")[0]
            if f"class {cls_name}" in existing:
                continue
            additions.append(class_def)

        if additions:
            _write_file(tools_file, existing + "\n\n" + "\n\n".join(additions) + "\n")

        searches_file = project_path / app / "searches.py"
        existing_searches = (
            searches_file.read_text(encoding="utf-8") if searches_file.exists() else ""
        )
        if retrieval_tools and not searches_file.exists():
            _write_file(searches_file, "from cogsol.tools import BaseRetrievalTool\n\n")
            existing_searches = searches_file.read_text(encoding="utf-8")

        retrieval_additions = []
        for tool in retrieval_tools:
            class_def = _retrieval_tool_class_from_api(tool, tool.get("_retrieval_name") or None)
            cls_name = class_def.split()[1].split("(")[0]
            if f"class {cls_name}" in existing_searches:
                continue
            retrieval_additions.append(class_def)

        if retrieval_additions:
            _write_file(
                searches_file,
                existing_searches + "\n\n" + "\n\n".join(retrieval_additions) + "\n",
            )
            has_retrieval_tools = True
            import_messages.append(f"Retrieval tools -> {searches_file}")

        if retrieval_tools:
            has_retrieval_tools = True

        # Update tools list in agent.py
        def class_name_for_script(script_id: int) -> Optional[str]:
            script = scripts_by_id.get(int(script_id))
            if not script:
                return None
            base_name = _safe_class_name(script.get("name") or "Tool", "Imported")
            return base_name if base_name.endswith("Tool") else base_name + "Tool"

        def class_name_for_retrieval_tool(tool_id: int) -> Optional[str]:
            tool = retrieval_tools_by_id.get(int(tool_id))
            if not tool:
                return None
            return _retrieval_tool_class_name(tool)

        def _tool_class_for_id(tool_id: int) -> Optional[str]:
            return class_name_for_script(tool_id) or class_name_for_retrieval_tool(tool_id)

        tool_class_names = [n for n in (_tool_class_for_id(sid) for sid in tools_ids) if n]
        pretool_class_names = [n for n in (_tool_class_for_id(sid) for sid in pretools_ids) if n]

        agent_source = (agent_dir / "agent.py").read_text(encoding="utf-8")
        if has_retrieval_tools and "from ..searches import *" not in agent_source:
            agent_source = agent_source.replace(
                "from ..tools import *",
                "from ..tools import *\nfrom ..searches import *",
            )
        agent_source = agent_source.replace(
            "    tools = []", f"    tools = [{', '.join(n + '()' for n in tool_class_names)}]"
        )
        agent_source = agent_source.replace(
            "    pretools = []",
            f"    pretools = [{', '.join(n + '()' for n in pretool_class_names)}]",
        )
        _write_file(agent_dir / "agent.py", agent_source)

        # Create migration and mark applied/state
        migrations_path = project_path / app / "migrations"
        migrations_path.mkdir(parents=True, exist_ok=True)
        migration_name = next_migration_name(migrations_path, explicit_name=f"import_{slug}")
        mig_path = migrations_path / f"{migration_name}.py"
        # Build migration operations (CreateTool/CreateAgent)
        try:
            tools_module = _import_module(f"{app}.tools", project_path)
        except ModuleNotFoundError:
            tools_module = None
        tool_ops = []
        for script in scripts:
            tname = script.get("name") or f"tool_{script.get('id')}"
            params_norm = _normalize_params(script.get("parameters") or [])
            run_source = _dedent_source(script.get("code") or "")
            if tools_module:
                cls_name = _safe_class_name(script.get("name") or "Tool", "Imported")
                cls_name = cls_name if cls_name.endswith("Tool") else cls_name + "Tool"
                tool_cls = getattr(tools_module, cls_name, None)
                if tool_cls:
                    import inspect

                    run_source = _dedent_source(inspect.getsource(tool_cls.run))
                    params_norm = _extract_tool_params(tool_cls)
            fields = {
                "name": tname,
                "description": script.get("description"),
                "parameters": params_norm,
                "__code__": run_source,
            }
            tool_ops.append(f"        migrations.CreateTool(name={tname!r}, fields={fields!r}),")

        retrieval_tool_ops = []
        for tool in retrieval_tools:
            tname = tool.get("name") or f"retrieval_tool_{tool.get('id')}"
            fields = {
                "name": tname,
                "description": tool.get("description"),
                "parameters": tool.get("parameters") or [],
                "retrieval": tool.get("_retrieval_name") or None,
                "show_tool_message": bool(tool.get("show_tool_message", False)),
                "show_assistant_message": bool(tool.get("show_assistant_message", False)),
                "edit_available": bool(tool.get("edit_available", True)),
                "answer": bool(tool.get("answer", True)),
            }
            retrieval_tool_ops.append(
                f"        migrations.CreateRetrievalTool(name={tname!r}, fields={fields!r}),"
            )

        def _tool_name_for_id(tool_id: int) -> Optional[str]:
            script = scripts_by_id.get(int(tool_id))
            if script:
                return script.get("name")
            rtool = retrieval_tools_by_id.get(int(tool_id))
            if rtool:
                return rtool.get("name")
            return None

        agent_fields = {
            "name": class_name[:-5] if class_name.endswith("Agent") else class_name,
            "system_prompt": prompt_text,
            "generation_config": assistant.get("generation_config"),
            "pregeneration_config": assistant.get("generation_config_pretools"),
            "temperature": assistant.get("temperature"),
            "max_responses": assistant.get("max_responses"),
            "max_msg_length": assistant.get("max_msg_length"),
            "max_consecutive_tool_calls": assistant.get("max_consecutive_tool_calls"),
            "streaming": assistant.get("streaming_available"),
            "realtime": assistant.get("realtime_available"),
            "tools": [n for n in (_tool_name_for_id(sid) for sid in tools_ids) if n],
            "pretools": [n for n in (_tool_name_for_id(sid) for sid in pretools_ids) if n],
            "faqs": [
                {
                    "name": f.get("name"),
                    "content": f.get("content"),
                    "meta": {"topic": None, "context_of_application": None},
                }
                for f in faqs
            ],
            "fixed_responses": [
                {
                    "name": f.get("name") or f.get("topic"),
                    "content": f.get("content"),
                    "meta": {"topic": f.get("topic"), "context_of_application": None},
                }
                for f in fixed
            ],
            "lessons": [
                {
                    "name": le.get("name"),
                    "content": le.get("content"),
                    "meta": {
                        "topic": None,
                        "context_of_application": le.get("context_of_application"),
                    },
                }
                for le in lessons
            ],
        }
        meta = {
            "name": class_name,
            "chat_name": agent_desc,
            "logo_url": assistant.get("logo"),
        }

        ops_lines = (
            tool_ops
            + retrieval_tool_ops
            + [
                f"        migrations.CreateAgent(name={class_name!r}, fields={agent_fields!r}, meta={meta!r}),"
            ]
        )
        mig_body = "\n".join(ops_lines) if ops_lines else ""
        mig_path.write_text(
            "# Generated by CogSol import\nfrom cogsol.db import migrations\n\n"
            "class Migration(migrations.Migration):\n"
            "    initial = False\n"
            "    dependencies = []\n"
            "    operations = [\n"
            f"{mig_body}\n"
            "    ]\n",
            encoding="utf-8",
        )
        import_messages.append(f"Agents migration -> {mig_path}")

        applied_path = migrations_path / ".applied.json"
        applied = (
            json.loads(applied_path.read_text(encoding="utf-8")) if applied_path.exists() else []
        )
        if migration_name not in applied:
            applied.append(migration_name)
        applied_path.write_text(json.dumps(applied, indent=2), encoding="utf-8")

        state_path = migrations_path / ".state.json"
        state: dict[str, Any] = {
            "state": {
                "agents": {},
                "tools": {},
                "retrieval_tools": {},
                "faqs": {},
                "fixed_responses": {},
                "lessons": {},
            },
            "remote": {},
        }
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        state.setdefault("remote", {}).setdefault("agents", {})[class_name] = assistant_id
        # tools remote ids
        for script in scripts:
            name = script.get("name") or script.get("id")
            state.setdefault("remote", {}).setdefault("tools", {})[name] = script.get("id")
            base_name = _safe_class_name(str(name), "Imported")
            class_name = base_name if base_name.endswith("Tool") else base_name + "Tool"
            normalized = class_name[:-4] if class_name.endswith("Tool") else class_name
            state["remote"]["tools"][class_name] = script.get("id")
            state["remote"]["tools"][normalized] = script.get("id")

        for tool in retrieval_tools:
            name = tool.get("name") or tool.get("id")
            state.setdefault("remote", {}).setdefault("retrieval_tools", {})[name] = tool.get("id")
            class_name = _retrieval_tool_class_name(tool)
            state["remote"]["retrieval_tools"][class_name] = tool.get("id")

        # Populate local state snapshot directly from project code
        state["state"] = collect_definitions(project_path, app)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        # ------------------------------------------------------------------
        # Import retrievals/topics/formatters into data app if needed.
        retrieval_ids: set[int] = set()
        for tool in retrieval_tools:
            value = tool.get("retrieval_id")
            if isinstance(value, int):
                retrieval_ids.add(value)
            elif isinstance(value, str) and value.isdigit():
                retrieval_ids.add(int(value))
        if retrieval_ids:
            data_app = "data"
            data_path = project_path / data_app
            data_path.mkdir(parents=True, exist_ok=True)
            (data_path / "migrations").mkdir(parents=True, exist_ok=True)
            data_init = data_path / "__init__.py"
            if not data_init.exists():
                _write_file(data_init, "")

            formatters_file = data_path / "formatters.py"
            retrievals_file = data_path / "retrievals.py"
            _ensure_import(formatters_file, "from cogsol.content import BaseReferenceFormatter")
            _ensure_import(retrievals_file, "from cogsol.content import BaseRetrieval")

            # Map formatter ids to details
            formatter_map: dict[int, dict[str, Any]] = {}
            try:
                for fmt in client.list_reference_formatters() or []:
                    if isinstance(fmt, dict) and isinstance(fmt.get("id"), int):
                        formatter_map[int(fmt["id"])] = fmt
            except CogSolAPIError:
                formatter_map = {}

            # Cache nodes for topic resolution
            node_cache: dict[int, dict[str, Any]] = {}

            def _get_node(node_id: int) -> dict[str, Any]:
                if node_id in node_cache:
                    return node_cache[node_id]
                node = client.get_node(node_id)
                if isinstance(node, dict):
                    node_cache[node_id] = node
                    return node
                return {}

            def _node_parent_id(node: dict[str, Any]) -> Optional[int]:
                parent = node.get("parent")
                if isinstance(parent, dict):
                    return parent.get("id")
                if isinstance(parent, int):
                    return parent
                return None

            def _node_chain(node_id: int) -> list[dict[str, Any]]:
                chain: list[dict[str, Any]] = []
                current: Optional[int] = node_id
                while current is not None:
                    node = _get_node(current)
                    if not node:
                        break
                    chain.append(node)
                    current = _node_parent_id(node)
                return list(reversed(chain))

            def _topic_path(chain: list[dict[str, Any]]) -> str:
                parts = []
                for node in chain:
                    name = node.get("name") or "topic"
                    parts.append(_slugify(str(name)))
                return "/".join(parts)

            imported_topics: dict[str, dict[str, Any]] = {}
            imported_formatters: dict[str, dict[str, Any]] = {}
            imported_retrievals: dict[str, dict[str, Any]] = {}
            remote_topics: dict[str, int] = {}
            remote_formatters: dict[str, int] = {}
            remote_retrievals: dict[str, int] = {}
            formatter_class_names: dict[int, str] = {}

            for retrieval_id in sorted(retrieval_ids):
                try:
                    retrieval = client.get_retrieval(retrieval_id)
                except CogSolAPIError as exc:
                    print(f"Warning: could not import retrieval {retrieval_id}: {exc}")
                    continue
                if not isinstance(retrieval, dict):
                    continue

                description = retrieval.get("description") or f"retrieval_{retrieval_id}"
                retrieval_name = str(description)
                retrieval_class = _retrieval_class_name(retrieval_name)

                topic_path = None
                node_id = retrieval.get("node")
                if isinstance(node_id, dict):
                    node_id = node_id.get("id")
                if isinstance(node_id, int):
                    chain = _node_chain(node_id)
                    if chain:
                        topic_path = _topic_path(chain)
                        # Create topic modules for each node in chain.
                        for depth, node in enumerate(chain, start=1):
                            node_name = node.get("name") or f"topic_{depth}"
                            node_desc = node.get("description")
                            node_path = "/".join(
                                _slugify(str(n.get("name") or "topic")) for n in chain[:depth]
                            )
                            module_dir = data_path.joinpath(*node_path.split("/"))
                            init_file = module_dir / "__init__.py"
                            _ensure_import(init_file, "from cogsol.content import BaseTopic")
                            class_name = _topic_class_name(str(node_name))
                            if _append_block(
                                init_file,
                                (
                                    f"class {class_name}(BaseTopic):\n"
                                    f"    name = {str(node_name)!r}\n"
                                    + (
                                        f"\n    class Meta:\n        description = {node_desc!r}\n"
                                        if node_desc
                                        else ""
                                    )
                                ),
                                f"class {class_name}(BaseTopic):",
                            ):
                                import_messages.append(f"Topic: {node_path} -> {init_file}")
                            imported_topics[node_path] = {
                                "fields": {"name": str(node_name)},
                                "meta": {"description": node_desc} if node_desc else {},
                            }
                            if isinstance(node.get("id"), int):
                                remote_topics[node_path] = int(node["id"])

                # Formatters used by retrieval
                formatters_value = {}
                fmt_items = retrieval.get("formatters") or []
                for item in fmt_items:
                    if not isinstance(item, dict):
                        continue
                    fmt_id = item.get("formatter_id")
                    doc_type = item.get("doc_type")
                    if not isinstance(fmt_id, int) or not doc_type:
                        continue
                    fmt = formatter_map.get(fmt_id)
                    if not fmt:
                        try:
                            fmt = client.get_reference_formatter(fmt_id)
                        except CogSolAPIError:
                            fmt = None
                    if not isinstance(fmt, dict):
                        continue
                    fmt_name = fmt.get("name") or f"formatter_{fmt_id}"
                    fmt_class = formatter_class_names.get(fmt_id) or _formatter_class_name(
                        str(fmt_name)
                    )
                    formatter_class_names[fmt_id] = fmt_class
                    if _append_block(
                        formatters_file,
                        (
                            f"class {fmt_class}(BaseReferenceFormatter):\n"
                            f"    name = {str(fmt_name)!r}\n"
                            + (
                                f"    description = {fmt.get('description')!r}\n"
                                if fmt.get("description") is not None
                                else ""
                            )
                            + (
                                f"    expression = {fmt.get('expression')!r}\n"
                                if fmt.get("expression") is not None
                                else ""
                            )
                        ),
                        f"class {fmt_class}(BaseReferenceFormatter):",
                    ):
                        import_messages.append(f"Formatter: {fmt_name} -> {formatters_file}")
                    imported_formatters[str(fmt_name)] = {
                        "fields": {
                            "name": fmt_name,
                            "description": fmt.get("description") or "",
                            "expression": fmt.get("expression") or "",
                        },
                        "meta": {},
                    }
                    if isinstance(fmt.get("id"), int):
                        remote_formatters[str(fmt_name)] = int(fmt["id"])
                    formatters_value[str(doc_type)] = fmt_class

                if formatters_value:
                    import_line = "from data.formatters import " + ", ".join(
                        sorted(set(formatters_value.values()))
                    )
                    _ensure_import(retrievals_file, import_line)

                formatters_literal = None
                if formatters_value:
                    pairs = [
                        f"{doc_type!r}: {cls_name}"
                        for doc_type, cls_name in sorted(formatters_value.items())
                    ]
                    formatters_literal = "{" + ", ".join(pairs) + "}"

                retrieval_lines = [
                    f"class {retrieval_class}(BaseRetrieval):",
                    '    """Imported retrieval configuration."""',
                    f"    name = {retrieval_name!r}",
                ]
                if topic_path:
                    retrieval_lines.append(f"    topic = {topic_path!r}")
                if "num_refs" in retrieval:
                    retrieval_lines.append(f"    num_refs = {retrieval.get('num_refs')!r}")
                if "reordering" in retrieval:
                    retrieval_lines.append(f"    reordering = {retrieval.get('reordering')!r}")
                if retrieval.get("strategy_reordering") is not None:
                    retrieval_lines.append(
                        f"    strategy_reordering = {retrieval.get('strategy_reordering')!r}"
                    )
                if "reordering_metadata" in retrieval:
                    retrieval_lines.append(
                        f"    reordering_metadata = {retrieval.get('reordering_metadata')!r}"
                    )
                if "retrieval_window" in retrieval:
                    retrieval_lines.append(
                        f"    retrieval_window = {retrieval.get('retrieval_window')!r}"
                    )
                if "fixed_blocks_reordering" in retrieval:
                    retrieval_lines.append(
                        f"    fixed_blocks_reordering = {retrieval.get('fixed_blocks_reordering')!r}"
                    )
                if "previous_blocks" in retrieval:
                    retrieval_lines.append(
                        f"    previous_blocks = {retrieval.get('previous_blocks')!r}"
                    )
                if "next_blocks" in retrieval:
                    retrieval_lines.append(f"    next_blocks = {retrieval.get('next_blocks')!r}")
                if "contingency_for_embedding" in retrieval:
                    retrieval_lines.append(
                        f"    contingency_for_embedding = {retrieval.get('contingency_for_embedding')!r}"
                    )
                if "threshold_similarity" in retrieval:
                    retrieval_lines.append(
                        f"    threshold_similarity = {retrieval.get('threshold_similarity')!r}"
                    )
                if "max_msg_length" in retrieval:
                    retrieval_lines.append(
                        f"    max_msg_length = {retrieval.get('max_msg_length')!r}"
                    )
                if formatters_literal:
                    retrieval_lines.append(f"    formatters = {formatters_literal}")
                if "filters" in retrieval:
                    retrieval_lines.append(f"    filters = {retrieval.get('filters')!r}")

                retrieval_block = "\n".join(retrieval_lines)
                if _append_block(
                    retrievals_file,
                    retrieval_block,
                    f"class {retrieval_class}(BaseRetrieval):",
                ):
                    import_messages.append(f"Retrieval: {retrieval_name} -> {retrievals_file}")

                imported_retrievals[retrieval_name] = {
                    "fields": {
                        "name": retrieval_name,
                        "topic": topic_path,
                        "num_refs": retrieval.get("num_refs"),
                        "reordering": retrieval.get("reordering"),
                        "strategy_reordering": retrieval.get("strategy_reordering"),
                        "retrieval_window": retrieval.get("retrieval_window"),
                        "reordering_metadata": retrieval.get("reordering_metadata"),
                        "fixed_blocks_reordering": retrieval.get("fixed_blocks_reordering"),
                        "previous_blocks": retrieval.get("previous_blocks"),
                        "next_blocks": retrieval.get("next_blocks"),
                        "contingency_for_embedding": retrieval.get("contingency_for_embedding"),
                        "threshold_similarity": retrieval.get("threshold_similarity"),
                        "max_msg_length": retrieval.get("max_msg_length"),
                        "formatters": formatters_value or {},
                        "filters": retrieval.get("filters"),
                    },
                    "meta": {},
                }
                if isinstance(retrieval.get("id"), int):
                    remote_retrievals[retrieval_name] = int(retrieval["id"])

            if imported_topics or imported_formatters or imported_retrievals:
                data_migrations = data_path / "migrations"
                data_migrations.mkdir(parents=True, exist_ok=True)
                data_mig_name = next_migration_name(data_migrations, explicit_name=f"import_{slug}")
                data_mig_path = data_migrations / f"{data_mig_name}.py"

                ops_lines = []
                for topic_key, definition in imported_topics.items():
                    ops_lines.append(
                        f"        migrations.CreateTopic(name={topic_key!r}, "
                        f"fields={definition['fields']!r}, meta={definition['meta']!r}),"
                    )
                for fmt_name, definition in imported_formatters.items():
                    ops_lines.append(
                        f"        migrations.CreateReferenceFormatter(name={fmt_name!r}, "
                        f"fields={definition['fields']!r}),"
                    )
                for ret_name, definition in imported_retrievals.items():
                    ops_lines.append(
                        f"        migrations.CreateRetrieval(name={ret_name!r}, "
                        f"fields={definition['fields']!r}),"
                    )
                mig_body = "\n".join(ops_lines) if ops_lines else ""
                data_mig_path.write_text(
                    "# Generated by CogSol import\nfrom cogsol.db import migrations\n\n"
                    "class Migration(migrations.Migration):\n"
                    "    initial = False\n"
                    "    dependencies = []\n"
                    "    operations = [\n"
                    f"{mig_body}\n"
                    "    ]\n",
                    encoding="utf-8",
                )
                import_messages.append(f"Data migration -> {data_mig_path}")

                data_applied_path = data_migrations / ".applied.json"
                data_applied = (
                    json.loads(data_applied_path.read_text(encoding="utf-8"))
                    if data_applied_path.exists()
                    else []
                )
                if data_mig_name not in data_applied:
                    data_applied.append(data_mig_name)
                data_applied_path.write_text(json.dumps(data_applied, indent=2), encoding="utf-8")

                data_state_path = data_migrations / ".state.json"
                data_state: dict[str, Any] = {
                    "state": {
                        "topics": {},
                        "formatters": {},
                        "retrievals": {},
                        "ingestion_configs": {},
                        "metadata_configs": {},
                    },
                    "remote": {},
                }
                if data_state_path.exists():
                    try:
                        data_state = json.loads(data_state_path.read_text(encoding="utf-8"))
                    except json.JSONDecodeError:
                        pass
                data_state.setdefault("remote", {}).setdefault("topics", {}).update(remote_topics)
                data_state.setdefault("remote", {}).setdefault("formatters", {}).update(
                    remote_formatters
                )
                data_state.setdefault("remote", {}).setdefault("retrievals", {}).update(
                    remote_retrievals
                )

                data_state["state"] = _strip_class_refs(
                    collect_content_definitions(project_path, data_app)
                )
                data_state_path.write_text(json.dumps(data_state, indent=2), encoding="utf-8")

        if import_messages:
            print("Imported:")
            for line in import_messages:
                print(f"  - {line}")

        return 0
