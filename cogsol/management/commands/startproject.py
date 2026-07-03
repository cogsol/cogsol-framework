from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from cogsol.core.cookbook import (
    DEFAULT_REPO,
    CookbookError,
    fetch_cookbook_directory,
    list_cookbook_entries,
    materialize_cookbook,
)
from cogsol.management.base import BaseCommand

_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _is_valid_repo_slug(value: str) -> bool:
    return bool(_REPO_PATTERN.fullmatch(value))


MANAGE_PY = """\
#!/usr/bin/env python
import sys
from pathlib import Path

from cogsol.core.management import execute_from_command_line


def main():
    project_path = Path(__file__).resolve().parent
    execute_from_command_line(sys.argv, project_path=project_path)


if __name__ == "__main__":
    main()
"""

SETTINGS_PY = """\
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_NAME = "{project_name}"
AGENTS_APP = "agents"
"""

TOOLS_PY = """\
from cogsol.tools import BaseTool, tool_params


class ExampleTool(BaseTool):
    description = "Demo tool that echoes the provided text."

    @tool_params(
        text={"description": "Text to echo", "type": "string", "required": True},
        count={"description": "Times to repeat", "type": "integer", "required": False},
    )
    def run(self, chat=None, data=None, secrets=None, log=None, text: str = "", count: int = 1):
        \"\"\"
        text: Text to echo back.
        count: Times to repeat the text.
        \"\"\"
        message = " ".join([text] * max(1, int(count)))
        # chat/data/secrets/log are available per platform docs
        response = message
        return response
"""

SEARCHES_PY = """\
from cogsol.tools import BaseRetrievalTool
# from data.retrievals import ProductDocsRetrieval
#
# class ExampleSearch(BaseRetrievalTool):
#     \"\"\"Retrieval tool that queries a Content API retrieval.\"\"\"
#
#     name = "example_search"
#     description = "Search over the product_docs retrieval."
#     retrieval = ProductDocsRetrieval()
#     parameters = []
"""

LESSONS_PY = """\
from cogsol.tools import BaseLesson
#
# class ExampleLesson(BaseLesson):
#     name = "ExampleLesson"
#     content = "Sample reusable context that is only used when relevant."
"""

FAQS_PY = """\
from cogsol.tools import BaseFAQ
#
# class ExampleFAQ(BaseFAQ):
#     question = "How do I use this project?"
#     answer = "Update agents.py and tools.py with your own logic."
"""

FIXED_RESPONSES_PY = """\
from cogsol.tools import BaseFixedResponse
#
# class ExampleFixedResponse(BaseFixedResponse):
#     key = "fallback"
#     response = "Thanks for trying CogSol!"
"""

MCP_SERVERS_PY = """\
import os

from cogsol.tools import BaseMCPServer
# Define MCP servers here.  Use os.environ for sensitive credentials.
# Run `python manage.py addmcptools` to interactively add a server.
# The server URL is hardcoded — it is sent to the CogSol API on `migrate`
# and served from there; it does not need to live in .env.
#
# --- auth_type="none" (no credentials) ---
# class ExampleMCPServer(BaseMCPServer):
#     name = "example_server"
#     description = "Example MCP server."
#     url = "https://example.com/mcp"
#
# --- auth_type="headers" (API key) ---
# class ExampleMCPServer(BaseMCPServer):
#     name = "example_server"
#     description = "Example MCP server."
#     url = "https://example.com/mcp"
#     headers = {"x-api-key": os.environ.get("MCP_EXAMPLE_SERVER_X_API_KEY", "")}
#
# --- auth_type="oauth2" (OAuth 2.1 / PKCE) ---
# class AtlassianMCPServer(BaseMCPServer):
#     name = "atlassian_server"
#     description = "Atlassian MCP server via OAuth 2.1."
#     auth_type = "oauth2"
#     url = "https://mcp.atlassian.com/mcp"
#     oauth_client_id = os.environ.get("MCP_ATLASSIAN_SERVER_OAUTH_CLIENT_ID", "")
#     oauth_scopes = os.environ.get("MCP_ATLASSIAN_SERVER_OAUTH_SCOPES", "")
#     # oauth_client_secret is NEVER stored here — handled by the CogSol backend
"""

MCP_TOOLS_PY = """\
from cogsol.tools import BaseMCPTool
# Define MCP tools here.  Each tool references a BaseMCPServer subclass.
# Run `python manage.py addmcptools` to interactively select tools.
#
# from agents.mcp_servers import ExampleMCPServer
#
# class ExampleMCPTool(BaseMCPTool):
#     name = "example_tool"
#     description = "An example tool from the MCP server."
#     server = ExampleMCPServer
"""

# Data folder templates for Content API
DATA_FORMATTERS_PY = """\
from cogsol.content import BaseReferenceFormatter
#
# class DefaultFormatter(BaseReferenceFormatter):
#     \"\"\"Default reference formatter for document blocks.\"\"\"
#
#     name = "default_formatter"
#     description = "Basic document reference with name and page."
#     expression = "[{name}, p.{page_num}]"
"""

DATA_INGESTION_PY = """\
from cogsol.content import BaseIngestionConfig, PDFParsingMode, ChunkingMode
#
# class DefaultIngestionConfig(BaseIngestionConfig):
#     \"\"\"Default ingestion configuration for documents.\"\"\"
#
#     name = "default_ingestion"
#     pdf_parsing_mode = PDFParsingMode.BOTH
#     chunking_mode = ChunkingMode.LANGCHAIN
#     max_size_block = 1500
#     chunk_overlap = 0
#     separators = []
#     ocr = False
#     additional_prompt_instructions = ""
#     assign_paths_as_metadata = False
"""

DATA_RETRIEVALS_PY = """\
from cogsol.content import BaseRetrieval, ReorderingStrategy
# from data.product_docs import ProductDocsTopic
#
# class ProductDocsRetrieval(BaseRetrieval):
#     \"\"\"Sample retrieval configuration.\"\"\"
#
#     name = "product_docs_search"
#     topic = ProductDocsTopic
#     num_refs = 10
#     reordering = False
#     strategy_reordering = ReorderingStrategy.NONE
#     formatters = {}
#     filters = []
"""

README = """\
# {project_name}

Generated by `cogsol-admin startproject`.

## Agents (Cognitive API)
- Create agents with `python manage.py startagent MyAgent` (per-agent folders under `agents/`).
- Define reusable tools in `agents/tools.py` and import them in each agent.
- Define retrieval tools in `agents/searches.py` to query Content API retrievals.
- Add MCP servers/tools with `python manage.py addmcptools` or define in `agents/mcp_servers.py` and `agents/mcp_tools.py`.

## Data (Content API)
- Create topics with `python manage.py starttopic my_topic` (nested folders under `data/`).
- Use `--path parent/child` for nested topics.
- Ingest documents with `python manage.py ingest my_topic path/to/files`.
- List topics with `python manage.py topics`.

## Migrations
- Configure credentials once with `cogsol-admin credentials-setup`.
- Run `python manage.py makemigrations` to capture changes.
- Run `python manage.py migrate` to sync with CogSol APIs.
"""


class Command(BaseCommand):
    requires_project = False
    help = "Create a new CogSol project skeleton."

    def add_arguments(self, parser):
        parser.add_argument(
            "name",
            nargs="?",
            default=None,
            help="Project name (also used as directory name).",
        )
        parser.add_argument(
            "directory",
            nargs="?",
            help="Optional destination directory. Defaults to the project name.",
        )

        source_group = parser.add_mutually_exclusive_group()
        source_group.add_argument(
            "--from-template",
            metavar="NAME",
            help="Scaffold from a cookbook template (templates/<NAME>).",
        )
        source_group.add_argument(
            "--from-example",
            metavar="NAME",
            help="Scaffold from a cookbook example (examples/<NAME>).",
        )
        source_group.add_argument(
            "--list-templates",
            action="store_true",
            default=False,
            help="List available cookbook templates.",
        )
        source_group.add_argument(
            "--list-examples",
            action="store_true",
            default=False,
            help="List available cookbook examples.",
        )

        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Overwrite existing files on conflict.",
        )
        parser.add_argument(
            "--ref",
            default="main",
            help="Cookbook git ref (branch, tag, or commit SHA). Default: main.",
        )
        parser.add_argument(
            "--cookbook-repo",
            metavar="OWNER/REPO",
            default=DEFAULT_REPO,
            help=("Cookbook repository in OWNER/REPO format. " f"Default: {DEFAULT_REPO}."),
        )
        parser.add_argument(
            "--github-token",
            default=None,
            help="GitHub token for private cookbook repositories.",
        )

    def handle(self, project_path: Path | None, **options: Any) -> int:
        ref = options.get("ref", "main")
        repo = str(options.get("cookbook_repo") or DEFAULT_REPO).strip()
        github_token = options.get("github_token")
        github_token = str(github_token).strip() if github_token else None

        if not _is_valid_repo_slug(repo):
            print("Error: --cookbook-repo must be in OWNER/REPO format.")
            return 1

        # --- List templates/examples ---
        if options.get("list_templates") or options.get("list_examples"):
            kind = "templates" if options.get("list_templates") else "examples"
            try:
                entries = list_cookbook_entries(
                    kind,
                    ref=ref,
                    repo=repo,
                    github_token=github_token,
                )
            except CookbookError as exc:
                print(f"Error: {exc}")
                return 1
            if not entries:
                print(f"No {kind} found in the cookbook (repo={repo}, ref={ref}).")
                return 0
            print(f"Available {kind} (repo={repo}, ref={ref}):")
            for entry in entries:
                print(f"  - {entry}")
            return 0

        # --- Validate name ---
        name = options.get("name")
        if not name:
            print("Error: project name is required.")
            return 1
        name = str(name)

        directory = options.get("directory")
        target_dir = Path(directory or name).resolve()
        force = bool(options.get("force"))

        # --- Scaffold from cookbook template/example ---
        from_template = options.get("from_template")
        from_example = options.get("from_example")

        if from_template or from_example:
            kind = "templates" if from_template else "examples"
            entry_name = str(from_template or from_example)

            if target_dir.exists() and any(target_dir.iterdir()) and not force:
                print(f"Destination {target_dir} is not empty (use --force to overwrite).")
                return 1

            try:
                source_dir = fetch_cookbook_directory(
                    kind,
                    entry_name,
                    ref=ref,
                    repo=repo,
                    github_token=github_token,
                )
                materialize_cookbook(source_dir, target_dir, force=force)
            except CookbookError as exc:
                print(f"Error: {exc}")
                if "not found" in str(exc):
                    try:
                        entries = list_cookbook_entries(
                            kind, ref=ref, repo=repo, github_token=github_token
                        )
                    except CookbookError:
                        entries = []
                    if entries:
                        print(f"Available {kind} in {repo}@{ref}:")
                        for entry in entries:
                            print(f"  - {entry}")
                return 1

            # Add default .env.example if the cookbook entry does not provide one
            env_example = target_dir / ".env.example"
            if not env_example.exists():
                env_example.write_text(
                    "COGSOL_ENV=development\n"
                    "#COGSOL_API_KEY=your-api-key\n"
                    "# Optional: Azure AD B2C client credentials for JWT\n"
                    "# If not provided, the Auth will be skipped\n"
                    "# COGSOL_AUTH_CLIENT_ID=you-client-id\n"
                    "# COGSOL_AUTH_SECRET=your-secret\n",
                    encoding="utf-8",
                )

            print(
                f"Created CogSol project '{name}' from {repo}:{kind}/{entry_name} at {target_dir}"
            )
            return 0

        # --- Default: generate from built-in templates ---
        if target_dir.exists() and any(target_dir.iterdir()):
            print(f"Destination {target_dir} is not empty.")
            return 1

        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "agents").mkdir(parents=True, exist_ok=True)
        (target_dir / "agents" / "migrations").mkdir(parents=True, exist_ok=True)
        (target_dir / "data").mkdir(parents=True, exist_ok=True)
        (target_dir / "data" / "migrations").mkdir(parents=True, exist_ok=True)

        files = {
            "manage.py": MANAGE_PY,
            "settings.py": SETTINGS_PY.format(project_name=name),
            "agents/__init__.py": "",
            "agents/tools.py": TOOLS_PY,
            "agents/searches.py": SEARCHES_PY,
            "agents/mcp_servers.py": MCP_SERVERS_PY,
            "agents/mcp_tools.py": MCP_TOOLS_PY,
            "agents/migrations/__init__.py": "",
            "data/__init__.py": "",
            "data/formatters.py": DATA_FORMATTERS_PY,
            "data/ingestion.py": DATA_INGESTION_PY,
            "data/retrievals.py": DATA_RETRIEVALS_PY,
            "data/migrations/__init__.py": "",
            "README.md": README.format(project_name=name),
            ".env.example": "COGSOL_ENV=development\n# Configure global credentials once:\n#   cogsol-admin credentials-setup\n#\n# Optional project-level overrides (take precedence over global config):\n# COGSOL_API_KEY=your-tenant-api-key\n# COGSOL_AUTH_CLIENT_ID=your-client-id\n# COGSOL_AUTH_SECRET=your-client-secret\n",
        }

        for relative_path, content in files.items():
            target_file = target_dir / relative_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(textwrap.dedent(content), encoding="utf-8")

        print(f"Created CogSol project '{name}' at {target_dir}")
        return 0
