from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, cast

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.env import load_dotenv
from cogsol.core.loader import _extract_tool_params, collect_definitions
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
        if not api_base:
            print("COGSOL_API_BASE is required in .env to import.")
            return 1

        client = CogSolClient(api_base, token=api_token)
        try:
            assistant = client.get_assistant(assistant_id)
            faqs = client.list_common_questions(assistant_id) or []
            fixed = client.list_fixed_responses(assistant_id) or []
            lessons = client.list_lessons(assistant_id) or []
        except CogSolAPIError as exc:
            print(f"API error: {exc}")
            return 1

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

        # Tools import
        tools_ids = assistant.get("tools") or []
        pretools_ids = assistant.get("pretools") or []
        scripts: list[dict[str, Any]] = []
        scripts_by_id: dict[int, dict[str, Any]] = {}
        for tool_id in tools_ids + pretools_ids:
            try:
                script = client.get_script(tool_id)
                scripts.append(script)
                scripts_by_id[int(tool_id)] = script
            except CogSolAPIError as exc:
                print(f"Warning: could not import tool {tool_id}: {exc}")

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

        # Update tools list in agent.py
        def class_name_for_script(script_id: int) -> Optional[str]:
            script = scripts_by_id.get(int(script_id))
            if not script:
                return None
            base_name = _safe_class_name(script.get("name") or "Tool", "Imported")
            return base_name if base_name.endswith("Tool") else base_name + "Tool"

        tool_class_names = [n for n in (class_name_for_script(sid) for sid in tools_ids) if n]
        pretool_class_names = [n for n in (class_name_for_script(sid) for sid in pretools_ids) if n]

        agent_source = (agent_dir / "agent.py").read_text(encoding="utf-8")
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

        agent_fields = {
            "name": class_name[:-5] if class_name.endswith("Agent") else class_name,
            "system_prompt": f"{slug}.md",
            "generation_config": assistant.get("generation_config"),
            "pregeneration_config": assistant.get("generation_config_pretools"),
            "temperature": assistant.get("temperature"),
            "max_responses": assistant.get("max_responses"),
            "max_msg_length": assistant.get("max_msg_length"),
            "max_consecutive_tool_calls": assistant.get("max_consecutive_tool_calls"),
            "streaming": assistant.get("streaming_available"),
            "realtime": assistant.get("realtime_available"),
            "tools": [s.get("name") for s in scripts if s.get("id") in tools_ids],
            "pretools": [s.get("name") for s in scripts if s.get("id") in pretools_ids],
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

        ops_lines = tool_ops + [
            f"        migrations.CreateAgent(name={class_name!r}, fields={agent_fields!r}, meta={meta!r}),"
        ]
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

        applied_path = migrations_path / ".applied.json"
        applied = (
            json.loads(applied_path.read_text(encoding="utf-8")) if applied_path.exists() else []
        )
        if migration_name not in applied:
            applied.append(migration_name)
        applied_path.write_text(json.dumps(applied, indent=2), encoding="utf-8")

        state_path = migrations_path / ".state.json"
        state: dict[str, Any] = {
            "state": {"agents": {}, "tools": {}, "faqs": {}, "fixed_responses": {}, "lessons": {}},
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

        # Populate local state snapshot directly from project code
        state["state"] = collect_definitions(project_path, app)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        print(f"Imported assistant {assistant_id} as {class_name} in {agent_dir}")
        return 0
