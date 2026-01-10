# CLI Commands Reference

This document provides detailed reference documentation for all CogSol command-line interface (CLI) commands.

## Table of Contents

- [Overview](#overview)
- [Global Commands](#global-commands)
  - [startproject](#startproject)
- [Project Commands](#project-commands)
  - [startagent](#startagent)
  - [starttopic](#starttopic)
  - [makemigrations](#makemigrations)
  - [migrate](#migrate)
  - [ingest](#ingest)
  - [topics](#topics)
  - [importagent](#importagent)
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

```env
COGSOL_ENV=local
COGSOL_API_BASE=http://localhost:8000
COGSOL_CONTENT_API_BASE=http://localhost:8001
# Optional: COGSOL_API_TOKEN=your-token
```

#### Example Usage

```bash
# Create project in new directory
cogsol-admin startproject myassistants

# Create project in specific location
cogsol-admin startproject myassistants /path/to/projects/my-ai
```

#### Error Conditions

| Error | Cause | Solution |
|-------|-------|----------|
| "Destination is not empty" | Target directory contains files | Choose different directory or empty it |

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
# Generated by CogSol 0.2.0 on 2026-01-08 10:30
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

#### Required Environment Variables

```env
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/  # Required
COGSOL_CONTENT_API_BASE=https://api.cogsol.ai/content/  # Required for data app
COGSOL_API_TOKEN=your-token              # Optional, but recommended
```

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

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--doc-type` | `Text Document` | Document type string |
| `--ingestion-config` | - | Name of ingestion config from `data/ingestion.py` |
| `--pdf-mode` | `both` | PDF parsing: `manual`, `OpenAI`, `both`, `ocr`, `ocr_openai` |
| `--chunking` | `langchain` | Chunking: `langchain`, `agentic` |
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
python manage.py ingest documentation ./docs/ --ingestion-config high_quality
```

#### Example Usage

```bash
# Ingest all PDFs in a directory
python manage.py ingest documentation ./docs/*.pdf

# Ingest an entire directory recursively
python manage.py ingest documentation ./docs/

# Use custom settings
python manage.py ingest documentation ./reports/ \
    --doc-type "Text Document" \
    --pdf-mode ocr \
    --chunking agentic \
    --max-size-block 2000

# Preview what would be ingested
python manage.py ingest documentation ./docs/ --dry-run
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

#### Required Environment Variables

```env
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/  # Required
COGSOL_API_TOKEN=your-token              # Optional
COGSOL_CONTENT_API_BASE=https://api.cogsol.ai/content/  # Required if importing retrievals
```

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

#### Required Environment Variables

```env
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/  # Required
COGSOL_API_TOKEN=your-token              # Optional
```

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

### `.env` File

Create a `.env` file in your project root:

```env
# Required for migrate and chat commands
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/
COGSOL_CONTENT_API_BASE=https://api.cogsol.ai/content/

# Optional: API authentication token
COGSOL_API_TOKEN=sk-your-api-token

# Optional: Environment identifier
COGSOL_ENV=production
```

### Environment Loading

The framework loads `.env` automatically using a minimal built-in loader (no external dependencies):

```python
# cogsol/core/env.py
def load_dotenv(dotenv_path: Path) -> None:
    """
    Minimal .env loader.
    Supports KEY=VALUE lines, ignores blanks and comments.
    """
```

### Variable Reference

| Variable | Required For | Description |
|----------|--------------|-------------|
| `COGSOL_API_BASE` | `migrate`, `chat`, `importagent` | Base URL for CogSol API |
| `COGSOL_CONTENT_API_BASE` | `migrate`, `ingest`, `topics`, `importagent` | Base URL for the Content API (defaults to `COGSOL_API_BASE`) |
| `COGSOL_API_TOKEN` | - | API authentication (via `x-api-key` header) |
| `COGSOL_ENV` | - | Environment name (informational) |

---

## Exit Codes

All commands return standard exit codes:

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (check output for details) |

---

## Troubleshooting

### Common Issues

#### "A command is required"

```bash
# Wrong
cogsol-admin

# Right
cogsol-admin startproject myproject
```

#### "Must be run from inside a CogSol project"

Ensure you're in a directory with `manage.py`:

```bash
cd myproject
python manage.py makemigrations
```

#### "COGSOL_API_BASE is required"

Create or update your `.env` file:

```bash
echo "COGSOL_API_BASE=https://api.cogsol.ai/cognitive/" >> .env
```

#### "Could not resolve agent"

1. Run `migrate` first to sync and get remote IDs
2. Check `.state.json` for the correct agent name
3. Use the numeric ID directly: `--agent 42`

#### "Error while importing definitions"

Check for Python syntax errors in your agent/tool code:

```bash
python -c "from agents.myagent.agent import *"
```

#### "API error: 401 Unauthorized"

Add or update your API token:

```env
COGSOL_API_TOKEN=your-valid-token
```

### Debug Tips

1. **Check state files**: Look at `agents/migrations/.state.json` for current mappings
2. **Review migrations**: Open `agents/migrations/*.py` to see generated operations
3. **Test imports**: Verify your code imports correctly before making migrations
4. **API connectivity**: Test with `curl $COGSOL_API_BASE/health`