from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

from cogsol.core.api import CogSolAPIError, CogSolClient
from cogsol.core.constants import (
    get_cognitive_api_base_url,
    get_content_api_base_url,
)
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


def _search_filter_names(tool: dict[str, Any]) -> list[str]:
    """Collapse the Cognitive ``filters`` list into unique metadata names.

    Date filters are stored as three entries (name, name_start, name_end) —
    group them by metadata_config_id (or stripped base name) and keep one.
    """
    names: list[str] = []
    seen: set[str] = set()
    for f in tool.get("filters") or []:
        if not isinstance(f, dict):
            continue
        fname = str(f.get("name") or "").strip()
        if not fname:
            continue
        base = fname
        for suffix in ("_start", "_end"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        cfg_id = f.get("metadata_config_id")
        key = f"id:{cfg_id}" if cfg_id is not None else f"name:{base}"
        if key in seen:
            continue
        seen.add(key)
        names.append(base)
    return names


def _retrieval_tool_class_from_api(tool: dict[str, Any], retrieval_name: str | None) -> str:
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
    filter_names = _search_filter_names(tool)
    filters_line = f"\n    filters = {filter_names!r}" if filter_names else ""

    template = f"""
class {class_name}(BaseRetrievalTool):
    \"\"\"Retrieval tool imported from CogSol API.\"\"\"

    name = {name!r}
    description = {description!r}
    retrieval = {retrieval_value!r}
    parameters = {params!r}{filters_line}
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


def _has_class_def(source: str, class_name: str) -> bool:
    """True if *source* contains a real (non-commented) top-level class definition.

    A plain substring check would also match commented-out template examples
    (e.g. ``# class AtlassianMCPServer(BaseMCPServer):``).
    """
    return re.search(rf"^class\s+{re.escape(class_name)}\b", source, re.MULTILINE) is not None


def _mcp_server_class_name(server: dict[str, Any]) -> str:
    name = server.get("name") or "MCPServer"
    base = _safe_class_name(name, "MCPServer")
    return base if base.endswith("MCPServer") else base + "MCPServer"


def _mcp_tool_class_name_from_data(tool: dict[str, Any]) -> str:
    name = tool.get("name") or "MCPTool"
    base = _safe_class_name(name, "MCPTool")
    return base if base.endswith("MCPTool") else base + "MCPTool"


def _mcp_env_key(server_name: str, suffix: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", server_name).strip("_").upper()
    suf = re.sub(r"[^a-zA-Z0-9]+", "_", suffix).strip("_").upper()
    return f"MCP_{base}_{suf}"


def _mcp_server_class_from_api(server: dict[str, Any]) -> str:
    """Generate a BaseMCPServer subclass from API data.

    Header values are stored in Key Vault and not returned by the API,
    so the generated class references env vars that the user must fill in.
    """
    name = server.get("name") or "MCPServer"
    cls_name = _mcp_server_class_name(server)
    description = server.get("description") or ""
    url = server.get("url") or ""
    auth_type = server.get("auth_type") or "none"

    if auth_type == "headers":
        header_keys = list((server.get("headers") or {}).keys())
        header_attr_lines: list[str] = []
        for hk in header_keys:
            env_key = _mcp_env_key(name, hk)
            header_attr_lines.append(f"        {hk!r}: os.environ.get({env_key!r}, ''),")
        headers_block = (
            "{\n" + "\n".join(header_attr_lines) + "\n    }" if header_attr_lines else "{}"
        )
        body = (
            f"    name = {name!r}\n"
            f"    description = {description!r}\n"
            f"    url = {url!r}\n"
            f"    headers = {headers_block}"
        )
        imports_prefix = "import os\n\nfrom cogsol.tools import BaseMCPServer\n\n\n"
    elif auth_type == "oauth2":
        oauth_config = server.get("oauth_config") or {}
        client_id = oauth_config.get("client_id") or ""
        scopes = oauth_config.get("scopes") or ""
        cid_env = _mcp_env_key(name, "OAUTH_CLIENT_ID")
        scopes_env = _mcp_env_key(name, "OAUTH_SCOPES")
        body_lines = [
            f"    name = {name!r}",
            f"    description = {description!r}",
            '    auth_type = "oauth2"',
            f"    url = {url!r}",
        ]
        if client_id:
            body_lines.append(f"    oauth_client_id = os.environ.get({cid_env!r}, '')")
        if scopes:
            body_lines.append(f"    oauth_scopes = os.environ.get({scopes_env!r}, '')")
        body = "\n".join(body_lines)
        imports_prefix = "import os\n\nfrom cogsol.tools import BaseMCPServer\n\n\n"
    else:
        body = (
            f"    name = {name!r}\n"
            f"    description = {description!r}\n"
            '    auth_type = "none"\n'
            f"    url = {url!r}"
        )
        imports_prefix = "from cogsol.tools import BaseMCPServer\n\n\n"

    return (
        f"{imports_prefix}class {cls_name}(BaseMCPServer):\n"
        f'    """MCP server definition (imported from CogSol API)."""\n\n'
        f"{body}\n"
    )


def _mcp_tool_class_from_api(tool: dict[str, Any], server_cls_name: str) -> str:
    name = tool.get("name") or "tool"
    cls_name = _mcp_tool_class_name_from_data(tool)
    description = tool.get("description") or ""
    return (
        f"class {cls_name}(BaseMCPTool):\n"
        f'    """MCP tool definition (imported from CogSol API)."""\n\n'
        f"    name = {name!r}\n"
        f"    description = {description!r}\n"
        f"    server = {server_cls_name}\n"
    )


def _mcp_server_env_placeholders(server: dict[str, Any]) -> dict[str, str]:
    """Return env vars that need to be set for this server (with empty placeholder values)."""
    name = server.get("name") or "MCPServer"
    auth_type = server.get("auth_type") or "none"
    placeholders: dict[str, str] = {}
    if auth_type == "headers":
        for hk in (server.get("headers") or {}).keys():
            placeholders[_mcp_env_key(name, hk)] = ""
    elif auth_type == "oauth2":
        oauth_config = server.get("oauth_config") or {}
        if oauth_config.get("client_id"):
            placeholders[_mcp_env_key(name, "OAUTH_CLIENT_ID")] = oauth_config["client_id"]
        placeholders[_mcp_env_key(name, "OAUTH_SCOPES")] = oauth_config.get("scopes") or ""
    return placeholders


class Command(BaseCommand):
    help = "Import an existing CogSol assistant into the local project."

    def add_arguments(self, parser):
        parser.add_argument(
            "assistant_id", type=int, help="Assistant ID to import from CogSol API."
        )
        parser.add_argument("app", nargs="?", default="agents", help="App name. Default: agents.")

    def handle(self, project_path: Path | None, **options: Any) -> int:
        assert project_path is not None, "project_path is required"
        if not self.ensure_credentials_configured(project_path):
            return 1

        assistant_id = cast(int, options.get("assistant_id"))
        app = str(options.get("app") or "agents")

        import os

        api_base = get_cognitive_api_base_url()
        api_key = os.environ.get("COGSOL_API_KEY")
        content_base = get_content_api_base_url() or api_base

        client = CogSolClient(api_base, api_key=api_key, content_base_url=content_base)
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

        # Personalization: the portal stores camelCase color keys; older
        # framework-migrated assistants may have snake_case leftovers.
        assistant_colors = assistant.get("colors") or {}
        if not isinstance(assistant_colors, dict):
            assistant_colors = {}

        def _color(camel: str, snake: str) -> Any:
            return assistant_colors.get(camel) or assistant_colors.get(snake) or None

        meta_lines = [
            f"        name = {class_name!r}",
            f"        chat_name = {agent_desc!r}",
        ]
        if assistant.get("info"):
            meta_lines.append(f"        alias = {assistant.get('info')!r}")
        meta_lines.append(f"        logo_url = {assistant.get('logo')!r}")
        personalization = {
            "assistant_name_color": _color("nameColor", "assistant_name_color"),
            "primary_color": _color("primaryColor", "primary_color"),
            "secondary_color": _color("secondaryColor", "secondary_color"),
            "border_color": _color("borderColor", "border_color"),
        }
        for meta_attr, color_value in personalization.items():
            if color_value:
                meta_lines.append(f"        {meta_attr} = {color_value!r}")
        meta_block = "\n".join(meta_lines)

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
    initial_message = {assistant.get("initial_message")!r}
    forced_termination_message = {assistant.get("end_message")!r}
    no_information_message = {assistant.get("not_info_message")!r}

    class Meta:
{meta_block}
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
        retrieval_cache: dict[int, str | None] = {}
        mcp_tools: list[dict[str, Any]] = []
        mcp_tools_by_id: dict[int, dict[str, Any]] = {}
        mcp_servers_cache: dict[int, dict[str, Any]] = {}

        def _resolve_retrieval_name(retrieval_id: int | None) -> str | None:
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
                except CogSolAPIError:
                    try:
                        mcp_tool = client.get_mcp_tool(tool_id)
                        if isinstance(mcp_tool, dict):
                            server_ref = mcp_tool.get("server") or mcp_tool.get("server_id")
                            # server may be a nested dict {"id": N, ...} instead of a bare int
                            if isinstance(server_ref, dict):
                                server_ref = server_ref.get("id")
                            try:
                                server_ref_int = int(server_ref) if server_ref is not None else None
                            except (TypeError, ValueError):
                                server_ref_int = None
                            if server_ref_int is not None and server_ref_int not in mcp_servers_cache:
                                try:
                                    mcp_servers_cache[server_ref_int] = client.get_mcp_server(
                                        server_ref_int
                                    )
                                except CogSolAPIError:
                                    mcp_servers_cache[server_ref_int] = {}
                            mcp_tools.append(mcp_tool)
                            mcp_tools_by_id[int(tool_id)] = mcp_tool
                    except CogSolAPIError as exc3:
                        print(f"  Warning: could not import tool {tool_id}: {exc3}")

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

        # -- MCP servers and tools --
        has_mcp_tools = False
        mcp_servers_file = project_path / app / "mcp_servers.py"
        mcp_tools_file = project_path / app / "mcp_tools.py"

        # Group MCP tools by their server id.
        # server may be a bare int, a string, or a nested dict {"id": N, ...}.
        mcp_server_tool_map: dict[int, list[dict[str, Any]]] = {}
        for mt in mcp_tools:
            server_ref = mt.get("server") or mt.get("server_id")
            if isinstance(server_ref, dict):
                server_ref = server_ref.get("id")
            try:
                server_ref_int = int(server_ref) if server_ref is not None else None
            except (TypeError, ValueError):
                server_ref_int = None
            if server_ref_int is not None:
                mcp_server_tool_map.setdefault(server_ref_int, []).append(mt)

        env_path = project_path / ".env"
        env_placeholders_needed: dict[str, str] = {}

        for server_id, s_tools in mcp_server_tool_map.items():
            server_data = mcp_servers_cache.get(server_id) or {}
            # If the server fetch failed, build a minimal stub from what we know.
            if not server_data:
                first_tool = s_tools[0] if s_tools else {}
                inferred_name = (
                    first_tool.get("server_name")
                    or first_tool.get("mcp_server_name")
                    or f"MCPServer{server_id}"
                )
                server_data = {"id": server_id, "name": inferred_name}
                print(
                    f"  Warning: could not fetch MCP server {server_id} from API; "
                    f"generating stub class '{inferred_name}'."
                )
            srv_cls_name = _mcp_server_class_name(server_data)

            # Write/append server class.
            server_code = _mcp_server_class_from_api(server_data)
            if mcp_servers_file.exists():
                existing_srv = mcp_servers_file.read_text(encoding="utf-8")
                if not _has_class_def(existing_srv, srv_cls_name):
                    class_only = (
                        "\n\n"
                        + "\n".join(
                            ln
                            for ln in server_code.splitlines()
                            if not ln.startswith("import ") and not ln.startswith("from ")
                        ).strip()
                        + "\n"
                    )
                    _write_file(mcp_servers_file, existing_srv.rstrip() + class_only)
                    import_messages.append(f"MCP server: {srv_cls_name} -> {mcp_servers_file}")
            else:
                _write_file(mcp_servers_file, server_code)
                import_messages.append(f"MCP server: {srv_cls_name} -> {mcp_servers_file}")

            # Write/append tool classes.
            import_line = f"from {app}.mcp_servers import {srv_cls_name}"
            if mcp_tools_file.exists():
                existing_tools = mcp_tools_file.read_text(encoding="utf-8")
                if import_line not in existing_tools:
                    existing_tools = existing_tools.rstrip() + f"\n{import_line}\n"
                for mt in s_tools:
                    tool_cls_name = _mcp_tool_class_name_from_data(mt)
                    if not _has_class_def(existing_tools, tool_cls_name):
                        tool_block = "\n\n" + _mcp_tool_class_from_api(mt, srv_cls_name).strip() + "\n"
                        existing_tools = existing_tools.rstrip() + tool_block
                        import_messages.append(
                            f"MCP tool: {tool_cls_name} -> {mcp_tools_file}"
                        )
                _write_file(mcp_tools_file, existing_tools)
            else:
                header = (
                    "from cogsol.tools import BaseMCPTool\n\n"
                    f"{import_line}\n"
                )
                blocks = "\n\n".join(
                    _mcp_tool_class_from_api(mt, srv_cls_name).strip() for mt in s_tools
                )
                _write_file(mcp_tools_file, header + "\n\n" + blocks + "\n")
                for mt in s_tools:
                    import_messages.append(
                        f"MCP tool: {_mcp_tool_class_name_from_data(mt)} -> {mcp_tools_file}"
                    )

            # Collect env-var placeholders.
            env_placeholders_needed.update(_mcp_server_env_placeholders(server_data))

        # Write placeholder env vars (empty values to signal what must be configured).
        if env_placeholders_needed:
            env_lines: list[str] = []
            if env_path.exists():
                env_lines = env_path.read_text(encoding="utf-8").splitlines()
            existing_env_keys = {
                ln.split("=", 1)[0].strip()
                for ln in env_lines
                if "=" in ln and not ln.strip().startswith("#")
            }
            new_vars = {k: v for k, v in env_placeholders_needed.items() if k not in existing_env_keys}
            if new_vars:
                env_lines.append("")
                env_lines.append("# MCP credentials (imported - fill in values)")
                env_lines.extend(f"{k}={v}" for k, v in new_vars.items())
                _write_file(env_path, "\n".join(env_lines) + "\n")
                print(
                    f"  Added {len(new_vars)} MCP credential placeholder(s) to .env — "
                    "fill in the values before running migrate."
                )

        if mcp_tools:
            has_mcp_tools = True

        # Update tools list in agent.py
        def class_name_for_script(script_id: int) -> str | None:
            script = scripts_by_id.get(int(script_id))
            if not script:
                return None
            base_name = _safe_class_name(script.get("name") or "Tool", "Imported")
            return base_name if base_name.endswith("Tool") else base_name + "Tool"

        def class_name_for_retrieval_tool(tool_id: int) -> str | None:
            tool = retrieval_tools_by_id.get(int(tool_id))
            if not tool:
                return None
            return _retrieval_tool_class_name(tool)

        def class_name_for_mcp_tool(tool_id: int) -> str | None:
            mt = mcp_tools_by_id.get(int(tool_id))
            if not mt:
                return None
            return _mcp_tool_class_name_from_data(mt)

        def _tool_class_for_id(tool_id: int) -> str | None:
            return (
                class_name_for_script(tool_id)
                or class_name_for_retrieval_tool(tool_id)
                or class_name_for_mcp_tool(tool_id)
            )

        tool_class_names = [n for n in (_tool_class_for_id(sid) for sid in tools_ids) if n]
        pretool_class_names = [n for n in (_tool_class_for_id(sid) for sid in pretools_ids) if n]

        agent_source = (agent_dir / "agent.py").read_text(encoding="utf-8")
        if has_retrieval_tools and "from ..searches import *" not in agent_source:
            agent_source = agent_source.replace(
                "from ..tools import *",
                "from ..tools import *\nfrom ..searches import *",
            )
        if has_mcp_tools and "from ..mcp_tools import *" not in agent_source:
            agent_source = agent_source.replace(
                "from ..tools import *",
                "from ..tools import *\nfrom ..mcp_tools import *",
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
                "filters": _search_filter_names(tool),
                "retrieval": tool.get("_retrieval_name") or None,
                "show_tool_message": bool(tool.get("show_tool_message", False)),
                "show_assistant_message": bool(tool.get("show_assistant_message", False)),
                "edit_available": bool(tool.get("edit_available", True)),
                "answer": bool(tool.get("answer", True)),
            }
            retrieval_tool_ops.append(
                f"        migrations.CreateRetrievalTool(name={tname!r}, fields={fields!r}),"
            )

        def _tool_name_for_id(tool_id: int) -> str | None:
            script = scripts_by_id.get(int(tool_id))
            if script:
                return script.get("name")
            rtool = retrieval_tools_by_id.get(int(tool_id))
            if rtool:
                return rtool.get("name")
            mt = mcp_tools_by_id.get(int(tool_id))
            if mt:
                return mt.get("name")
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
            "initial_message": assistant.get("initial_message"),
            "forced_termination_message": assistant.get("end_message"),
            "no_information_message": assistant.get("not_info_message"),
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
        if assistant.get("info"):
            meta["alias"] = assistant.get("info")
        for meta_attr, color_value in personalization.items():
            if color_value:
                meta[meta_attr] = color_value

        mcp_server_ops: list[str] = []
        mcp_tool_ops: list[str] = []
        for server_id, s_tools in mcp_server_tool_map.items():
            server_data = mcp_servers_cache.get(server_id) or {}
            if not server_data:
                continue
            sname = server_data.get("name") or f"mcp_server_{server_id}"
            srv_fields = {
                "name": sname,
                "description": server_data.get("description") or "",
                "url": server_data.get("url") or "",
                "auth_type": server_data.get("auth_type") or "none",
            }
            mcp_server_ops.append(
                f"        migrations.CreateMCPServer(name={sname!r}, fields={srv_fields!r}),"
            )
            for mt in s_tools:
                tname = mt.get("name") or f"mcp_tool_{mt.get('id')}"
                t_fields = {
                    "name": tname,
                    "description": mt.get("description") or "",
                    "server": sname,
                }
                mcp_tool_ops.append(
                    f"        migrations.CreateMCPTool(name={tname!r}, fields={t_fields!r}),"
                )

        ops_lines = (
            tool_ops
            + retrieval_tool_ops
            + mcp_server_ops
            + mcp_tool_ops
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

        for server_id, s_tools in mcp_server_tool_map.items():
            server_data = mcp_servers_cache.get(server_id) or {}
            if not server_data:
                continue
            sname = server_data.get("name") or f"mcp_server_{server_id}"
            state.setdefault("remote", {}).setdefault("mcp_servers", {})[sname] = server_id
            srv_cls = _mcp_server_class_name(server_data)
            state["remote"]["mcp_servers"][srv_cls] = server_id
            for mt in s_tools:
                tname = mt.get("name") or mt.get("id")
                state.setdefault("remote", {}).setdefault("mcp_tools", {})[tname] = mt.get("id")
                tool_cls = _mcp_tool_class_name_from_data(mt)
                state["remote"]["mcp_tools"][tool_cls] = mt.get("id")

        # Populate local state snapshot directly from project code
        try:
            state["state"] = collect_definitions(project_path, app)
        except Exception as exc:
            print(
                f"  Warning: could not build full state snapshot ({exc}). "
                "The import succeeded but .state.json local state may be incomplete. "
                "Re-import any agents that reference undefined classes."
            )
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

            def _node_parent_id(node: dict[str, Any]) -> int | None:
                parent = node.get("parent")
                if isinstance(parent, dict):
                    return parent.get("id")
                if isinstance(parent, int):
                    return parent
                return None

            def _node_chain(node_id: int) -> list[dict[str, Any]]:
                chain: list[dict[str, Any]] = []
                current: int | None = node_id
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
            imported_metadata_cfgs: dict[str, dict[str, Any]] = {}
            remote_topics: dict[str, int] = {}
            remote_formatters: dict[str, int] = {}
            remote_retrievals: dict[str, int] = {}
            remote_metadata_cfgs: dict[str, int] = {}
            formatter_class_names: dict[int, str] = {}
            metadata_nodes_done: set[int] = set()
            metadata_type_names = {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "DATE", "URL"}

            def _import_node_metadata_configs(
                node: dict[str, Any], node_path: str, module_dir: Path
            ) -> None:
                """Fetch a node's metadata configs and generate data/<topic>/metadata.py."""
                node_id = node.get("id")
                if not isinstance(node_id, int) or node_id in metadata_nodes_done:
                    return
                metadata_nodes_done.add(node_id)
                try:
                    payload = client.list_metadata_configs(node_id)
                except CogSolAPIError as exc:
                    print(f"  Warning: could not list metadata configs for node {node_id}: {exc}")
                    return
                if isinstance(payload, dict):
                    items = payload.get("results") or payload.get("metadata_configs") or []
                elif isinstance(payload, list):
                    items = payload
                else:
                    items = []

                metadata_file = module_dir / "metadata.py"
                for cfg in items:
                    if not isinstance(cfg, dict) or not cfg.get("name"):
                        continue
                    # Skip configs inherited from an ancestor node.
                    root_node_id = cfg.get("root_node_id")
                    if isinstance(root_node_id, int) and root_node_id != node_id:
                        continue
                    cfg_name = str(cfg["name"])
                    cfg_type = str(cfg.get("type") or "STRING").upper()
                    type_expr = (
                        f"MetadataType.{cfg_type}"
                        if cfg_type in metadata_type_names
                        else repr(cfg.get("type"))
                    )
                    cls_base = _safe_class_name(cfg_name, "Metadata")
                    cls_name = (
                        cls_base if cls_base.endswith("Metadata") else cls_base + "Metadata"
                    )
                    lines = [
                        f"class {cls_name}(BaseMetadataConfig):",
                        f"    name = {cfg_name!r}",
                        f"    type = {type_expr}",
                    ]
                    if cfg.get("possible_values"):
                        lines.append(f"    possible_values = {list(cfg['possible_values'])!r}")
                    if cfg.get("default_value") is not None:
                        lines.append(f"    default_value = {cfg.get('default_value')!r}")
                    if cfg.get("format"):
                        lines.append(f"    format = {cfg.get('format')!r}")
                    if cfg.get("filtrable"):
                        lines.append("    filtrable = True")
                    if cfg.get("required"):
                        lines.append("    required = True")
                    if cfg.get("in_embedding"):
                        lines.append("    in_embedding = True")
                    if cfg.get("in_retrieval") is False:
                        lines.append("    in_retrieval = False")

                    _ensure_import(
                        metadata_file,
                        "from cogsol.content import BaseMetadataConfig, MetadataType",
                    )
                    if _append_block(
                        metadata_file,
                        "\n".join(lines),
                        f"class {cls_name}(BaseMetadataConfig):",
                    ):
                        import_messages.append(
                            f"Metadata config: {node_path}/{cfg_name} -> {metadata_file}"
                        )

                    cfg_key = f"{node_path}/{cfg_name}"
                    imported_metadata_cfgs[cfg_key] = {
                        "fields": {
                            "name": cfg_name,
                            "type": cfg_type,
                            "possible_values": list(cfg.get("possible_values") or []),
                            "default_value": cfg.get("default_value"),
                            "format": cfg.get("format"),
                            "filtrable": bool(cfg.get("filtrable", False)),
                            "required": bool(cfg.get("required", False)),
                            "in_embedding": bool(cfg.get("in_embedding", False)),
                            "in_retrieval": bool(cfg.get("in_retrieval", True)),
                        },
                        "topic": node_path,
                    }
                    if isinstance(cfg.get("id"), int):
                        remote_metadata_cfgs[cfg_key] = int(cfg["id"])

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
                            _import_node_metadata_configs(node, node_path, module_dir)

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

            if (
                imported_topics
                or imported_formatters
                or imported_retrievals
                or imported_metadata_cfgs
            ):
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
                for cfg_key, definition in imported_metadata_cfgs.items():
                    ops_lines.append(
                        f"        migrations.CreateMetadataConfig(name={cfg_key!r}, "
                        f"fields={definition['fields']!r}, topic={definition['topic']!r}),"
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
                data_state.setdefault("remote", {}).setdefault("metadata_configs", {}).update(
                    remote_metadata_cfgs
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
