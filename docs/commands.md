# CLI Commands Reference

This document provides detailed reference documentation for all CogSol command-line interface (CLI) commands.

## Table of Contents

- [Overview](#overview)
- [Global Commands](#global-commands)
  - [startproject](#startproject)
    - [credentials-setup](#credentials-setup)
    - [logout](#logout)
- [Project Commands](#project-commands)
  - [startagent](#startagent)
  - [starttopic](#starttopic)
  - [makemigrations](#makemigrations)
  - [migrate](#migrate)
  - [ingest](#ingest)
  - [topics](#topics)
  - [importagent](#importagent)
    - [addmcptools](#addmcptools)
    - [editmcptools](#editmcptools)
    - [deletemcptools](#deletemcptools)
  - [chat](#chat)
- [Environment Configuration](#environment-configuration)
- [Exit Codes](#exit-codes)
- [Troubleshooting](#troubleshooting)

---

## Overview

CogSol provides two CLI entry points:

### `cogsol-admin`

Global command available after installing the package. Used for creating new projects.

```bash
cogsol-admin <command> [options]
```

### `manage.py`

Project-specific script generated in each CogSol project. Used for all project operations.

```bash
python manage.py <command> [options]
```

### Getting Help

```bash
# List available commands
cogsol-admin

# Get help for a specific command
python manage.py <command> --help
```

---

## Global Commands

### startproject

Create a new CogSol project with the standard directory structure.

#### Synopsis

```bash
cogsol-admin startproject <name> [directory]
```

#### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Project name (used in settings and documentation) |
| `directory` | No | Target directory. Defaults to `<name>/` in current directory |

#### Generated Structure

```
<project-name>/
├── manage.py               # Project CLI entry point
├── settings.py             # Project configuration
├── README.md               # Project documentation
├── .env.example            # Environment template
├── agents/                 # Agents application
│   ├── __init__.py
│   ├── tools.py            # Shared tool definitions
│   ├── searches.py         # Retrieval tool definitions
│   └── migrations/
│       └── __init__.py
└── data/                   # Data application
    ├── __init__.py
    ├── formatters.py       # Reference formatter definitions
    ├── ingestion.py        # Ingestion configuration definitions
    ├── retrievals.py       # Retrieval configuration definitions
    └── migrations/
        └── __init__.py
```

#### Generated Files

##### `manage.py`

```python
#!/usr/bin/env python
import sys
from pathlib import Path
from cogsol.core.management import execute_from_command_line

def main():
    project_path = Path(__file__).resolve().parent
    execute_from_command_line(sys.argv, project_path=project_path)

if __name__ == "__main__":
    main()
```

##### `settings.py`

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_NAME = "<project-name>"
AGENTS_APP = "agents"
```

##### `agents/tools.py`

Contains a commented `ExampleTool` class demonstrating proper tool implementation.

##### `agents/searches.py`

Contains a commented example retrieval tool definition.

##### `data/formatters.py`

Contains commented examples of reference formatters.

##### `data/ingestion.py`

Contains commented examples of ingestion configs.

##### `data/retrievals.py`

Contains commented examples of retrieval configurations.

##### `.env.example`

Documents optional project-level environment overrides. Tenant credentials are normally configured once with `cogsol-admin credentials-setup`.

#### Example Usage

```bash
# Create project in new directory
cogsol-admin startproject myassistants

# Create project in specific location
cogsol-admin startproject myassistants /path/to/projects/my-ai
```

#### Cookbook Scaffolding

Use cookbook templates/examples directly from GitHub:

```bash
# List templates/examples from the default cookbook repo
cogsol-admin startproject --list-templates
cogsol-admin startproject --list-examples

# Scaffold from a public custom cookbook
cogsol-admin startproject my-agent --from-template subagents --cookbook-repo my-org/my-cookbook

# Scaffold from a private cookbook
cogsol-admin startproject my-agent --from-template internal-agent \
    --cookbook-repo my-org/private-cookbook \
    --github-token $GITHUB_TOKEN
```

| Option | Description |
|--------|-------------|
| `--from-template NAME` | Scaffold from `templates/NAME` |
| `--from-example NAME` | Scaffold from `examples/NAME` |
| `--list-templates` | List available templates in the selected cookbook repo |
| `--list-examples` | List available examples in the selected cookbook repo |
| `--ref REF` | Cookbook git ref (branch, tag, or commit SHA). Default: `main` |
| `--cookbook-repo OWNER/REPO` | Cookbook repository. Default: `cogsol/cogsol-cookbook` |
| `--github-token TOKEN` | GitHub token for private cookbook repositories |

#### Error Conditions

| Error | Cause | Solution |
|-------|-------|----------|
| "Destination is not empty" | Target directory contains files | Choose different directory or empty it |

---

### credentials-setup

Interactively configure tenant credentials for `cogsol-admin` and project commands.

#### Synopsis

```bash
cogsol-admin credentials-setup
```

#### Prompted Fields

- `client_id`
- `client_secret`
- `tenant_api_key`

If you do not have credentials yet, the command points users to:

- https://onboarding.cogsol.ai

The onboarding flow provides credentials required to use CogSol Framework and the CLI.

Credentials are stored in a user-level CLI config file with restricted permissions.

### logout

Delete locally stored CLI credentials.

#### Synopsis

```bash
cogsol-admin logout
```

#### Behavior

- Removes the user-level credentials file.
- Clears credential variables from the current process environment.
- Safe to run when no credentials are stored.

---

## Project Commands

### startagent

Create a new agent package with all required files.

#### Synopsis

```bash
python manage.py startagent <name> [app]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `name` | Yes | - | Agent class name (e.g., `SalesAgent`, `Support`) |
| `app` | No | `agents` | Application directory name |

#### Generated Structure

```
agents/<slug>/
├── __init__.py           # Exports agent class
├── agent.py              # Main agent definition
├── faqs.py               # FAQ definitions
├── fixed.py              # Fixed response definitions
├── lessons.py            # Lesson definitions
└── prompts/
    └── <slug>.md         # System prompt template
```

#### Name Processing

The command processes the agent name:

1. **Class Name**: Ensures name ends with `Agent` (e.g., `Sales` → `SalesAgent`)
2. **Slug**: Converts to lowercase with underscores (e.g., `SalesAgent` → `salesagent`)

#### Generated Files

##### `agent.py`

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts
from ..tools import ExampleTool

class SalesAgent(BaseAgent):
    system_prompt = Prompts.load("salesagent.md")
    generation_config = genconfigs.QA()
    tools = [ExampleTool()]
    max_responses = 5
    max_msg_length = 2048
    max_consecutive_tool_calls = 3
    temperature = 0.3

    class Meta:
        name = "SalesAgent"
        chat_name = "SalesAgent Chat"
```

##### `faqs.py`

```python
from cogsol.tools import BaseFAQ
#
# class GreetingFAQ(BaseFAQ):
#     question = "How do I start?"
#     answer = "Just type your question and I'll help you."
```


##### `fixed.py`

```python
from cogsol.tools import BaseFixedResponse
#
# class FallbackFixed(BaseFixedResponse):
#     key = "fallback"
#     response = "I'm here to help! Could you rephrase that?"
```


##### `lessons.py`

```python
from cogsol.tools import BaseLesson
#
# class ContextLesson(BaseLesson):
#     name = "Context"
#     content = "Keep responses concise and focused on the user's request."
#     context_of_application = "general"
```


##### `prompts/<slug>.md`

```markdown
You are SalesAgent, a helpful agent. Answer clearly and concisely.
```

#### Example Usage

```bash
# Create with auto-suffix
python manage.py startagent Sales          # Creates SalesAgent

# Create with explicit name
python manage.py startagent CustomerSupport  # Creates CustomerSupportAgent

# Create in custom app
python manage.py startagent Sales assistants
```

#### Behavior Notes

- Skips existing files (does not overwrite)
- Creates directory structure automatically
- Imports `ExampleTool` from `tools.py` (uncomment the example tool or replace the import)
- FAQs, fixed responses, and lessons are commented examples by default

---

### starttopic

Create a new topic folder under `data/` for organizing documents.

#### Synopsis

```bash
python manage.py starttopic <name> [--path <parent-path>]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `name` | Yes | - | Topic name (used as folder name) |
| `--path` | No | - | Parent path for nested topics |

#### Generated Structure

```
data/<topic>/
├── __init__.py           # Topic class definition
└── metadata.py           # Metadata configuration definitions
```

#### Name Validation

Topic names must:
- Start with a letter or underscore
- Contain only letters, numbers, and underscores
- Be valid Python identifiers

#### Generated Files

##### `__init__.py`

```python
from cogsol.content import BaseTopic

class DocumentationTopic(BaseTopic):
    """Topic node for organizing documentation documents."""
    name = "documentation"

    class Meta:
        description = "documentation topic - add a description here."
```

##### `metadata.py`

```python
from cogsol.content import BaseMetadataConfig, MetadataType

# Define metadata configurations for this topic.
# Example:
#
# class CategoryMetadata(BaseMetadataConfig):
#     name = "category"
#     type = MetadataType.STRING
#     possible_values = ["General", "Technical", "FAQ"]
#     filtrable = True
#     required = False
#     # If required is True, default_value must be set.
#     # default_value = "General"
```

#### Example Usage

```bash
# Create a root topic
python manage.py starttopic documentation

# Create nested topics
python manage.py starttopic tutorials --path documentation
# Creates: data/documentation/tutorials/

python manage.py starttopic advanced --path documentation/tutorials
# Creates: data/documentation/tutorials/advanced/
```

#### Behavior Notes

- Parent path must exist before creating nested topics
- Topics map to Nodes in the Content API
- Run `makemigrations data` and `migrate data` after creating topics

---

### makemigrations

Generate migration files based on changes to agent, tool, and topic definitions.

#### Synopsis

```bash
python manage.py makemigrations [app] [--name <suffix>]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `app` | No | - | Application to scan for changes (`agents` or `data`, omitted runs both) |
| `--name` | No | Auto-generated | Custom migration name suffix |

#### How It Works

1. **Load Previous State**: Replay all existing migrations to compute state
2. **Collect Current Definitions**: Import and introspect project modules
3. **Compute Diff**: Compare states to identify changes
4. **Generate Migration**: Create Python file with operations

#### Migration File Naming

```
<number>_<name>.py
```

- **number**: 4-digit sequential (e.g., `0001`, `0002`)
- **name**: User-provided or auto-generated (e.g., `initial`, `auto_20240115_1030`)

#### Example Migration File

```python
# Generated by CogSol 0.3.0 on 2026-01-08 10:30
from cogsol.db import migrations

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateAgent(name='SalesAgent', fields={
            'system_prompt': 'You are a helpful sales assistant.',
            'temperature': 0.3,
            'generation_config': 'QA',
            'tools': ['ExampleTool'],
            'faqs': [...],
            'fixed_responses': [...],
            'lessons': [...],
        }, meta={
            'name': 'SalesAgent',
            'chat_name': 'Sales Agent Chat',
        }),
        migrations.CreateTool(name='ExampleTool', fields={
            'name': 'ExampleTool',
            'description': 'Demo tool that echoes the provided text.',
            'parameters': {
                'text': {'description': 'Text to echo', 'type': 'string', 'required': True},
                'count': {'description': 'Times to repeat', 'type': 'integer', 'required': False},
            },
            '__code__': '...',
        }),
    ]
```

#### Example Usage

```bash
# Generate with auto-name
python manage.py makemigrations

# Generate with custom name
python manage.py makemigrations --name add_sales_tools

# Generate for specific app
python manage.py makemigrations myapp --name initial
```

### migrate

Apply pending migrations and synchronize with the remote CogSol API.

#### Synopsis

```bash
python manage.py migrate [app]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `app` | No | - | Application to migrate (`agents` or `data`, omitted runs both) |

#### Required Credentials

Configure credentials once with:

```bash
cogsol-admin credentials-setup
```

Project `.env` values can override the user-level credentials when a project needs a different tenant.

#### How It Works

1. **Load Applied**: Read `.applied.json` to find already-applied migrations
2. **Find Pending**: Compare with migration files to find new ones
3. **Apply Operations**: Execute migration operations to build state
4. **Sync with API**: Push definitions to remote CogSol API
5. **Update Tracking**: Write `.state.json` and `.applied.json`

#### API Operations

For each entity type, the command performs upserts:

| Entity | API Endpoint | Operation |
|--------|--------------|-----------|
| Tools | `POST/PUT /tools/scripts/` | Create or update script |
| Retrieval Tools | `POST/PUT /tools/retrievals/` | Create or update retrieval tool |
| Agents | `POST/PUT /assistants/` | Create or update assistant |
| FAQs | `POST/PUT /assistants/{id}/common_questions/` | Create or update FAQ |
| Fixed Responses | `POST/PUT /assistants/{id}/fixed_questions/` | Create or update fixed |
| Lessons | `POST/PUT /assistants/{id}/lessons/` | Create or update lesson |

For the `data` app, the command syncs with the Content API:

| Entity | API Endpoint | Operation |
|--------|--------------|-----------|
| Topics | `POST/PUT /nodes/` | Create or update node |
| Metadata Configs | `POST/PUT /nodes/{id}/metadata_configs/` | Create or update config |
| Reference Formatters | `POST/PUT /reference_formatters/` | Create or update formatter |
| Ingestion Configs | `POST/PUT /ingestion-configs/` | Create or update ingestion config |
| Retrievals | `POST/PUT /retrievals/` | Create or update retrieval |

#### Rollback Behavior

If API sync fails, the command attempts to rollback:

1. Delete newly created resources (in reverse order)
2. Return error exit code
3. State files remain unchanged

#### State Files

##### `.applied.json`

Tracks applied migrations:

```json
["0001_initial", "0002_add_tool"]
```

##### `.state.json`

Stores state and remote ID mappings:

```json
{
    "state": {...},
    "remote": {
        "agents": {"SalesAgent": 42},
        "tools": {"ExampleTool": 15}
    }
}
```

#### Example Usage

```bash
# Apply all pending migrations
python manage.py migrate

# Apply for specific app
python manage.py migrate agents

# Apply data migrations (Content API)
python manage.py migrate data
```

#### Output Messages

| Message | Meaning |
|---------|---------|
| "No migrations folder found" | Create migrations first |
| "No migrations to apply" | All migrations applied |
| "No pending migrations" | Already up to date |
| "Applying agents.0002..." | Processing migration |
| "Applied N migration(s) and synced" | Success |
| "API error while applying..." | Remote sync failed |

---

### ingest

Upload documents to a topic in the Content API.

#### Synopsis

```bash
python manage.py ingest <topic> <files...> [options]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `topic` | Yes | - | Topic path (e.g., `docs` or `parent/child`) |
| `files` | Yes | - | Files, directories, or glob patterns |

Use slash-separated paths for nested topics during ingestion (for example:
`documentation/tutorials`). For a topic-aligned workflow, place files under
`data/<topic-path>/` and ingest from that matching path (for example:
`./data/documentation/*.pdf` and `./data/documentation/tutorials/*.pdf`).

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--doc-type` | `Text Document` | Document type string |
| `--ingestion-config` | - | Name of ingestion config from `data/ingestion.py` |
| `--pdf-mode` | `both` | PDF parsing: `manual`, `OpenAI`, `both`, `ocr`, `ocr_openai` |
| `--chunking` | `langchain` | Chunking: `langchain`, `ingestor` |
| `--max-size-block` | `1500` | Maximum characters per block |
| `--chunk-overlap` | `0` | Overlap between blocks |
| `--separators` | - | Comma-separated chunk separators |
| `--ocr` | - | Enable OCR parsing |
| `--additional-prompt-instructions` | - | Extra parsing instructions |
| `--assign-paths-as-metadata` | - | Assign file paths as metadata |
| `--dry-run` | - | Preview without uploading |

#### Supported File Types

```
.pdf, .docx, .doc, .txt, .md, .html, .htm,
.pptx, .ppt, .xlsx, .xls, .csv, .json, .xml
```

#### Using Ingestion Configs

Define reusable configurations in `data/ingestion.py`:

```python
from cogsol.content import BaseIngestionConfig, PDFParsingMode, ChunkingMode

class HighQualityConfig(BaseIngestionConfig):
    name = "high_quality"
    pdf_parsing_mode = PDFParsingMode.OCR
    chunking_mode = ChunkingMode.AGENTIC_SPLITTER
    max_size_block = 2000
    chunk_overlap = 100
```

Then use with:

```bash
python manage.py ingest documentation ./data/documentation/ --ingestion-config high_quality
```

#### Example Usage

```bash
# Ingest all PDFs in a directory
python manage.py ingest documentation ./data/documentation/*.pdf

# Ingest into a child topic using parent/child path
python manage.py ingest documentation/tutorials ./data/documentation/tutorials/*.pdf

# Ingest an entire directory recursively
python manage.py ingest documentation ./data/documentation/

# Use custom settings
python manage.py ingest documentation ./data/documentation/reports/ \
    --doc-type "Text Document" \
    --pdf-mode ocr \
    --chunking ingestor \
    --max-size-block 2000

# Preview what would be ingested
python manage.py ingest documentation ./data/documentation/ --dry-run
```

#### Output Messages

| Message | Meaning |
|---------|---------|
| "Found N file(s) to ingest" | Files detected |
| "OK filename -> document_id=X" | Upload successful |
| "ERR filename: error" | Upload failed |
| "Topic 'X' not found" | Topic not migrated |

---

### topics

List topics from the API or local definitions.

#### Synopsis

```bash
python manage.py topics [options]
```

#### Options

| Option | Description |
|--------|-------------|
| `--local` | Show topics from local `data/` definitions |
| `--sync-status` | Compare local definitions with API state |

#### Example Usage

```bash
# List topics from API
python manage.py topics

# List local topic definitions
python manage.py topics --local

# Show sync status
python manage.py topics --sync-status
```

#### Output Format

```
Topics from API:
  documentation (id=1)
    └── tutorials (id=2)
    └── reference (id=3)
  faq (id=4)
```

---

### importagent

Import an existing assistant from the remote CogSol API into local code.

#### Synopsis

```bash
python manage.py importagent <assistant_id> [app]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `assistant_id` | Yes | - | Remote assistant ID (integer) |
| `app` | No | `agents` | Target application |

#### Required Credentials

Configure credentials once with:

```bash
cogsol-admin credentials-setup
```

Project `.env` values can override the user-level credentials when a project needs a different tenant.

#### What Gets Imported

| Remote Resource | Local Destination |
|-----------------|-------------------|
| Assistant config | `<slug>/agent.py` |
| System prompt | `<slug>/prompts/<slug>.md` |
| Script tools | `tools.py` (appended) |
| Retrieval tools | `searches.py` (appended) |
| FAQs | `<slug>/faqs.py` |
| Fixed responses | `<slug>/fixed.py` |
| Lessons | `<slug>/lessons.py` |
| Content topics + metadata | `data/<topic>/__init__.py` + `data/<topic>/metadata.py` |
| Content retrievals | `data/retrievals.py` (appended) |
| Reference formatters | `data/formatters.py` (appended) |
| Data migration state | `data/migrations/.state.json` + migration file |

#### Code Transformation

The command transforms API-style code to class-based code:

**API Style (remote):**
```python
text = params.get('text')
response = text.upper()
```

**Class Style (local):**
```python
class EchoTool(BaseTool):
    @tool_params(text={"description": "Text", "type": "string", "required": True})
    def run(self, chat=None, data=None, secrets=None, log=None, text: str = ""):
        response = text.upper()
        return response
```

#### Example Usage

```bash
# Import assistant #42
python manage.py importagent 42

# Import into custom app
python manage.py importagent 42 myagents
```

#### Output

```
Imported assistant 42 as CustomerSupportAgent in agents/customer_support
```

#### Generated Migration

The command also creates a migration marking the import as applied, preventing duplicate creation on next `migrate`. When retrievals or topics are imported, a data migration is created and marked applied as well.

---

### addmcptools

Interactively register an MCP server, select the desired available MCP tools and link them to your agent.

#### Synopsis

```bash
python manage.py addmcptools
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--app` | `agents` | App folder where `mcp_servers.py` and `mcp_tools.py` are created/updated |
| `--oauth-timeout` | `300` | Max seconds to wait for OAuth completion in browser flow | (Optional)


#### What This Command Does

1. **Collects server configuration**
2. **Discovers tools from the MCP endpoint** (with OAuth-assisted discovery when needed)
3. **Generates/updates local Python definitions**
4. **Publishes mcp server + selected tools to your agent immediately**

#### Authentication Modes

| Auth Type | Use Case | Notes |
|----------|----------|-------|
| `none` | Public MCP server | No credentials required |
| `headers` | API key or static headers | Header values are saved as env vars in `.env` |
| `oauth2` | OAuth 2.1 / MCP server | `client_id` and scopes are optional; `client_secret` is never written to source or `.env` |

#### Generated or Updated Files

| File | Purpose |
|------|---------|
| `<app>/mcp_servers.py` | MCP server classes (`BaseMCPServer`) |
| `<app>/mcp_tools.py` | MCP tool classes (`BaseMCPTool`) linked to selected server |
| `.env` | New non-secret MCP variables (headers, optional OAuth client metadata) |

#### Step-by-Step: Add a New MCP Server

1. Run the command:

```bash
python manage.py addmcptools
```

2. Enter server metadata when prompted:
    - Server name
    - Description (optional)
    - MCP URL
    - Auth mode (`none`, `headers`, or `oauth2`)

3. Provide credentials based on auth mode:
    - `headers`: add one or more headers and values
    - `oauth2`: optionally provide client ID/scopes, optionally client secret (write-only to API)

4. Select tools to import (`all` or comma-separated indices).

5. Review created/updated files:
    - `<app>/mcp_servers.py`
    - `<app>/mcp_tools.py`
    - `.env`

6. Generate and apply migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

7. If OAuth re-authorization is requested, complete the browser flow and re-run
    `addmcptools` if needed.

#### Example Usage and Outputs

```bash
# Default app (agents)
python manage.py addmcptools
.
.
.
follow the options provided from the cli and cotinue the flow

#### Output Highlights

| Message | Meaning |
|---------|---------|
| "Found N tool(s)" | Tool discovery succeeded |
| "Created/Updated MCP server" | Server was published to remote catalog |
| "Synced N MCP tool(s)" | Tool selection was published |
| "Run 'python manage.py makemigrations' followed by 'python manage.py migrate'" | Next step to persist local definitions in your project lifecycle |

---

### editmcptools

Interactively edit an existing MCP server's configuration (name, URL, auth, credentials) and re-select its tools.

#### Synopsis

```bash
python manage.py editmcptools
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--app` | `agents` | App folder where `mcp_servers.py`/`mcp_tools.py` live |
| `--oauth-timeout` | `300` | Max seconds to wait for OAuth completion in browser flow (Optional) |

#### What This Command Does

1. Lists existing MCP servers defined in `<app>/mcp_servers.py` and lets you pick one
2. Re-prompts for server details (name, description, URL, auth type, credentials), pre-filled with current values
3. Reconnects to the MCP server and re-discovers available tools
4. Lets you re-select which tools to keep
5. Replaces the old server/tool class definitions with the updated ones
6. Updates `.env` — renames the credential prefix if the server name changed, adds/updates only the changed variables
7. Publishes the update to the CogSol API (PATCH) and re-syncs tools

#### Generated or Updated Files

| File | Purpose |
|------|---------|
| `<app>/mcp_servers.py` | Old server class replaced with the updated definition |
| `<app>/mcp_tools.py` | Tool classes updated to reference the (possibly renamed) server |
| `.env` | Credential vars renamed/updated as needed |

#### Notes

- If the server name changes, the class name, `.env` prefix, import lines, and `server =` references in tool classes are all updated to match.
- Run `python manage.py makemigrations` followed by `migrate` afterward to persist the change.

---

### deletemcptools

Remove an existing MCP server and its associated tool definitions from the project.

#### Synopsis

```bash
python manage.py deletemcptools
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--app` | `agents` | App folder where `mcp_servers.py`/`mcp_tools.py` live |

#### What This Command Does

1. Lists existing MCP servers defined in `<app>/mcp_servers.py` and lets you pick one
2. Shows the tools that will be removed along with the server, and asks for confirmation
3. Deletes the server from the CogSol API
4. Removes the server class from `mcp_servers.py` and its tool classes from `mcp_tools.py`
5. Removes the related credential variables from `.env`

#### Generated or Updated Files

| File | Purpose |
|------|---------|
| `<app>/mcp_servers.py` | Server class removed |
| `<app>/mcp_tools.py` | Associated tool classes removed |
| `.env` | Credential vars for that server removed |

#### Notes

- Run `python manage.py makemigrations` followed by `migrate` afterward to apply the deletion.

---

### chat

Start an interactive chat session with a deployed agent.

#### Synopsis

```bash
python manage.py chat --agent <identifier> [app]
```

#### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--agent` | Yes | - | Agent name or remote ID |
| `app` | No | `agents` | Application name |

#### Required Credentials

Configure credentials once with:

```bash
cogsol-admin credentials-setup
```

Project `.env` values can override the user-level credentials when a project needs a different tenant.

#### Agent Resolution

The `--agent` value is resolved in order:

1. **Numeric ID**: Used directly as remote assistant ID
2. **Class Name**: Looked up in `.state.json` remote mappings

#### Chat Interface

The command provides a styled terminal interface:

```
    ██████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██╗     
   ██╔════╝██╔═══██╗██╔════╝ ██╔════╝██╔═══██╗██║     
   ██║     ██║   ██║██║  ███╗███████╗██║   ██║██║     
   ██║     ██║   ██║██║   ██║╚════██║██║   ██║██║     
   ╚██████╗╚██████╔╝╚██████╔╝███████║╚██████╔╝███████╗
    ╚═════╝ ╚═════╝  ╚═════╝ ╚══════╝ ╚═════╝ ╚══════╝
    
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🤖  Agent: SalesAgent #42
  📅  January 15, 2024 • 10:30

  ╭─────────────────────────────────────────╮
  │  Commands:                              │
  │    /exit or Ctrl+C  →  Quit chat        │
  │    /new             →  Start a new chat │
  ╰─────────────────────────────────────────╯

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ╭─ Message
  ╰─▶ 
```

#### Chat Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `/exit` | `exit`, `quit`, `:q`, `Ctrl+C` | End chat session |
| `/new` | `new`, `/restart`, `/reset` | Start new conversation |

#### Message Display

- **User messages**: Right-aligned cyan bubbles
- **AI messages**: Left-aligned green bubbles with robot emoji
- **Timestamps**: Shown below each message

#### Example Usage

```bash
# Chat by agent name
python manage.py chat --agent SalesAgent

# Chat by remote ID
python manage.py chat --agent 42

# Chat with custom app
python manage.py chat --agent Support assistants
```

---

## Environment Configuration

Authenticated commands require all three credentials. The recommended setup is:

```bash
cogsol-admin credentials-setup
```

Credential resolution order:

1. Process environment variables
2. Project `.env` file
3. User-level CLI credentials file

Projects can optionally define credentials in a `.env` file for project-level overrides:

```env
COGSOL_ENV=development
# Optional project-level credential overrides:
# COGSOL_API_KEY=your-api-key
# COGSOL_AUTH_CLIENT_ID=your-client-id
# COGSOL_AUTH_SECRET=your-client-secret
```

When credentials are missing, authenticated commands fail fast with:

`Credentials are not configured. Run cogsol-admin credentials-setup first.`

To clear stored credentials:

```bash
cogsol-admin logout
```

---

## Exit Codes

All commands return standard exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (check output for details) |

---

## Troubleshooting

See [docs/troubleshooting.md](troubleshooting.md) for common errors and debug tips.
