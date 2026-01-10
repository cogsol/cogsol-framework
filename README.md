# CogSol Framework

**Version:** 0.2.0 (Alpha)

CogSol is a lightweight, agent-first Python framework for building, managing, and deploying AI assistants. It provides scaffolding, agent abstractions, and file-based migration utilities for CogSol projects without requiring an external database.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [CLI Commands](#cli-commands)
- [Core Concepts](#core-concepts)
  - [Agents](#agents)
  - [Data & Topics](#data--topics)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Contributing](#contributing)

---

## Overview

CogSol is designed to provide a Django-like development experience for building AI agents. It uses a code-first approach where you define your agents, tools, and configurations in Python, then use migrations to sync with a remote CogSol API.

### Design Philosophy

- **Code-First**: Define agents and tools as Python classes
- **Migration-Based Deployments**: Track changes via migrations (similar to Django)
- **No Database Required**: Uses JSON files for state tracking
- **API-Synchronized**: Push local definitions to remote CogSol APIs
- **Lightweight**: Minimal dependencies, uses only Python standard library

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Agent Definitions** | Define AI agents as Python classes with configurable attributes |
| **Tool System** | Create reusable tools with typed parameters and decorators |
| **Topics & Documents** | Organize knowledge bases with hierarchical topics and document ingestion |
| **Retrievals** | Configure semantic search across your document collections |
| **Migrations** | Track and version agent/tool/topic changes |
| **Remote Sync** | Push definitions to CogSol Cognitive and Content APIs |
| **Interactive Chat** | Built-in CLI for testing agents |
| **Import/Export** | Import existing assistants from the API |

---

## Installation

### From Source

```bash
git clone <repository-url>
cd framework
pip install -e .
```

### Requirements

- Python 3.9+
- No external dependencies (uses only Python standard library)

After installation, the `cogsol-admin` command becomes available globally.

---

## Quick Start

### 1. Create a New Project

```bash
cogsol-admin startproject myproject
cd myproject
```

This creates:
```
myproject/
├── manage.py           # Project CLI entry point
├── settings.py         # Project configuration
├── .env.example        # Environment template
├── README.md
├── agents/
│   ├── __init__.py
│   ├── tools.py        # Global tool definitions
│   ├── searches.py     # Retrieval tool definitions
│   └── migrations/
│       └── __init__.py
└── data/
    ├── __init__.py
    ├── formatters.py   # Reference formatters
    ├── ingestion.py    # Ingestion configurations
    ├── retrievals.py   # Retrieval configurations
    └── migrations/
        └── __init__.py
```

### 2. Create an Agent

```bash
python manage.py startagent SalesAgent
```

This creates a complete agent package:
```
agents/salesagent/
├── __init__.py
├── agent.py            # Main agent definition
├── faqs.py             # Frequently asked questions
├── fixed.py            # Fixed responses
├── lessons.py          # Contextual lessons
└── prompts/
    └── salesagent.md   # System prompt
```

### 3. Configure Environment

Copy `.env.example` to `.env` and set your API credentials:

```env
COGSOL_ENV=local
COGSOL_API_BASE=https://api.cogsol.ai/cognitive/
COGSOL_CONTENT_API_BASE=https://api.cogsol.ai/content/
COGSOL_API_TOKEN=your-api-token
```

### 4. Create Migrations

```bash
python manage.py makemigrations
```

### 5. Apply Migrations

```bash
python manage.py migrate
```

### 6. Chat with Your Agent

```bash
python manage.py chat --agent SalesAgent
```

### 7. Add Document Topics (Optional)

```bash
# Create a topic for documents
python manage.py starttopic documentation

# Create nested topics
python manage.py starttopic tutorials --path documentation

# Create migrations for data
python manage.py makemigrations data
python manage.py migrate data

# Ingest documents into a topic
python manage.py ingest documentation ./docs/*.pdf
```

---

## Project Structure

A typical CogSol project has the following structure:

```
myproject/
├── manage.py                    # CLI entry point
├── settings.py                  # Project settings
├── .env                         # Environment variables
├── agents/                      # Agents application
│   ├── __init__.py
│   ├── tools.py                 # Shared tool definitions
│   ├── searches.py              # Retrieval tool definitions
│   ├── migrations/              # Migration files
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   ├── .applied.json        # Applied migrations tracker
│   │   └── .state.json          # Current state and remote IDs
│   └── <agent-slug>/            # Per-agent package
│       ├── __init__.py
│       ├── agent.py             # Agent class definition
│       ├── faqs.py              # FAQ definitions
│       ├── fixed.py             # Fixed response definitions
│       ├── lessons.py           # Lesson definitions
│       └── prompts/
│           └── <slug>.md        # System prompt
└── data/                        # Data application
    ├── __init__.py
    ├── formatters.py            # Reference formatter definitions
    ├── ingestion.py             # Ingestion configuration definitions
    ├── retrievals.py            # Retrieval configuration definitions
    ├── migrations/              # Migration files
    │   ├── __init__.py
    │   ├── 0001_initial.py
    │   ├── .applied.json
    │   └── .state.json
    └── <topic-path>/            # Topic folder (can be nested)
        ├── __init__.py          # Topic class definition
        └── metadata.py          # Metadata configurations
```

---

## CLI Commands

CogSol provides the following management commands:

### `startproject`

Create a new CogSol project.

```bash
cogsol-admin startproject <project-name> [directory]
```

**Arguments:**
- `project-name`: Name of the project
- `directory`: (Optional) Target directory

### `startagent`

Create a new agent package with all required files.

```bash
python manage.py startagent <agent-name> [app]
```

**Arguments:**
- `agent-name`: Agent class name (e.g., `SalesAgent`)
- `app`: (Optional) App name, defaults to `agents`

### `makemigrations`

Generate migration files based on agent/tool/topic changes.

```bash
python manage.py makemigrations [app] [--name <suffix>]
```

**Arguments:**
- `app`: (Optional) App to migrate, `agents` or `data` (when omitted, runs both)
- `--name`: (Optional) Custom migration name suffix

### `migrate`

Apply pending migrations and sync with the CogSol API.

```bash
python manage.py migrate [app]
```

**Arguments:**
- `app`: (Optional) App to migrate, `agents` or `data` (when omitted, runs both)

### `starttopic`

Create a new topic folder under `data/`.

```bash
python manage.py starttopic <topic-name> [--path <parent-path>]
```

**Arguments:**
- `topic-name`: Name of the topic (used as folder name)
- `--path`: (Optional) Parent path for nested topics (e.g., `parent/child`)

**Examples:**
```bash
# Create a root topic
python manage.py starttopic documentation

# Create a nested topic
python manage.py starttopic tutorials --path documentation
# Creates: data/documentation/tutorials/
```

### `ingest`

Ingest documents into a topic.

```bash
python manage.py ingest <topic> <files...> [options]
```

**Arguments:**
- `topic`: Topic path (e.g., `documentation` or `parent/child/topic`)
- `files`: Files, directories, or glob patterns to ingest

**Options:**
- `--doc-type`: Document type (defaults to `Text Document`)
- `--ingestion-config`: Name of an ingestion config from `data/ingestion.py`
- `--pdf-mode`: PDF parsing mode (`manual`, `OpenAI`, `both`, `ocr`, `ocr_openai`)
- `--chunking`: Chunking mode (`langchain`, `ingestor`)
- `--max-size-block`: Maximum characters per block (default: 1500)
- `--chunk-overlap`: Overlap between blocks (default: 0)
- `--separators`: Comma-separated chunk separators
- `--ocr`: Enable OCR parsing
- `--additional-prompt-instructions`: Extra parsing instructions
- `--assign-paths-as-metadata`: Assign file paths as metadata
- `--dry-run`: Show what would be ingested without uploading

**Examples:**
```bash
# Ingest PDF files
python manage.py ingest documentation ./docs/*.pdf

# Ingest with custom config
python manage.py ingest documentation ./docs/ --ingestion-config HighQuality

# Dry run to preview
python manage.py ingest documentation ./data/ --dry-run
```

### `topics`

List topics from the API or local definitions.

```bash
python manage.py topics [options]
```

**Options:**
- `--local`: Show topics from local definitions instead of API
- `--sync-status`: Show synchronization status (local vs API)

### `importagent`

Import an existing assistant from the CogSol API.

```bash
python manage.py importagent <assistant-id> [app]
```

**Arguments:**
- `assistant-id`: Remote assistant ID to import
- `app`: (Optional) App name, defaults to `agents`

### `chat`

Start an interactive chat session with an agent.

```bash
python manage.py chat --agent <agent-name-or-id> [app]
```

**Arguments:**
- `--agent`: Agent name or remote ID (required)
- `app`: (Optional) App name, defaults to `agents`

**Chat Commands:**
- `/exit` or `Ctrl+C`: Exit the chat
- `/new`: Start a new chat session

---

## Core Concepts

### Agents

Agents are the central concept in CogSol. An agent is defined as a Python class that inherits from `BaseAgent`:

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts

class CustomerSupportAgent(BaseAgent):
    # Core configuration
    system_prompt = Prompts.load("support.md")
    generation_config = genconfigs.QA()
    
    # Tools
    tools = [MyTool()]
    pretools = []
    
    # Limits
    max_interactions = 10
    max_msg_length = 2048
    max_consecutive_tool_calls = 5
    temperature = 0.3
    
    # Behaviors
    initial_message = "Hello! How can I help you today?"
    forced_termination_message = "Thank you for chatting!"
    no_information_message = "I don't have information on that topic."
    
    # Features
    streaming = False
    realtime = False
    
    class Meta:
        name = "CustomerSupportAgent"
        chat_name = "Customer Support"
        logo_url = "https://example.com/logo.png"
        primary_color = "#007bff"
```

#### Agent Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `system_prompt` | `Prompt` | The system prompt loaded from a file |
| `generation_config` | `genconfigs.*` | LLM generation configuration |
| `pregeneration_config` | `genconfigs.*` | Pre-tool generation configuration |
| `tools` | `list[BaseTool]` | Tools available to the agent |
| `pretools` | `list[BaseTool]` | Pre-processing tools |
| `temperature` | `float` | LLM temperature (0.0 - 1.0) |
| `max_interactions` | `int` | Maximum conversation turns |
| `user_message_length` | `int` | Maximum user message length |
| `consecutive_tool_calls_limit` | `int` | Max consecutive tool calls |
| `streaming` | `bool` | Enable response streaming |
| `realtime` | `bool` | Enable real-time mode |

### Tools

Tools extend agent capabilities. Define tools in `agents/tools.py`:

```python
from cogsol.tools import BaseTool, tool_params

# class SearchTool(BaseTool):
#     description = "Search for information in the knowledge base."
#     
#     @tool_params(
#         query={"description": "Search query", "type": "string", "required": True},
#         limit={"description": "Max results", "type": "integer", "required": False},
#     )
#     def run(self, chat=None, data=None, secrets=None, log=None, 
#             query: str = "", limit: int = 10):
#         """
#         query: The search query.
#         limit: Maximum number of results.
#         """
#         # Implementation here
#         results = perform_search(query, limit)
#         response = format_results(results)
#         return response
```

Retrieval tools connect agents to Content API retrievals. Define them in `agents/searches.py`:

```python
from cogsol.tools import BaseRetrievalTool
# from data.retrievals import ProductDocsRetrieval
#
# class ProductDocsSearch(BaseRetrievalTool):
#     name = "product_docs_search"
#     description = "Search the product documentation."
#     retrieval = ProductDocsRetrieval
#     parameters = [
#         {"name": "question", "description": "Search query", "type": "string", "required": True}
#     ]
```

#### Tool Parameters

The `@tool_params` decorator defines parameter metadata:

```python
@tool_params(
    param_name={
        "description": "Parameter description",
        "type": "string",      # string, integer, boolean, etc.
        "required": True       # Required or optional
    }
)
```

### FAQs, Fixed Responses, and Lessons

These provide additional context to agents:

#### FAQs (`faqs.py`)

```python
from cogsol.tools import BaseFAQ
#
# class PricingFAQ(BaseFAQ):
#     question = "What are your pricing plans?"
#     answer = "We offer three tiers: Basic ($10/mo), Pro ($25/mo), Enterprise (custom)."
```

#### Fixed Responses (`fixed.py`)

```python
from cogsol.tools import BaseFixedResponse
#
# class ClosingFixed(BaseFixedResponse):
#     key = "goodbye"
#     response = "Thank you for contacting us. Have a great day!"
```

#### Lessons (`lessons.py`)

```python
from cogsol.tools import BaseLesson
#
# class ToneLesson(BaseLesson):
#     name = "Communication Tone"
#     content = "Always maintain a professional yet friendly tone."
#     context_of_application = "general"
```

### Prompts

Prompts are loaded from markdown files:

```python
from cogsol.prompts import Prompts

# In agent definition
system_prompt = Prompts.load("agent.md")
```

The prompt file is resolved relative to the agent's `prompts/` directory.

### Generation Configurations

```python
from cogsol.agents import genconfigs

# Question-Answering mode
generation_config = genconfigs.QA()

# Fast retrieval mode
generation_config = genconfigs.FastRetrieval()
```

### Data & Topics

CogSol provides a complete system for managing document collections and semantic search through the Content API.

#### Topics

Topics are hierarchical containers for organizing documents. Define them in `data/<topic>/`:

```python
# data/documentation/__init__.py
from cogsol.content import BaseTopic
#
# class DocumentationTopic(BaseTopic):
#     name = "documentation"
#
#     class Meta:
#         description = "Product documentation and guides."
```

Topics can be nested by creating subdirectories:

```
data/
├── documentation/
│   ├── __init__.py
│   ├── metadata.py
│   └── tutorials/
│       ├── __init__.py
│       └── metadata.py
```

#### Metadata Configurations

Define custom metadata fields for documents within a topic:

```python
# data/documentation/metadata.py
from cogsol.content import BaseMetadataConfig, MetadataType
#
# class CategoryMetadata(BaseMetadataConfig):
#     name = "category"
#     type = MetadataType.STRING
#     possible_values = ["Guide", "Tutorial", "Reference", "FAQ"]
#     filtrable = True
#     required = False
#
# class VersionMetadata(BaseMetadataConfig):
#     name = "version"
#     type = MetadataType.STRING
#     required = True
#     default_value = "1.0"
```

#### Ingestion Configurations

Define reusable ingestion settings in `data/ingestion.py`:

```python
from cogsol.content import BaseIngestionConfig, PDFParsingMode, ChunkingMode
#
# class HighQualityConfig(BaseIngestionConfig):
#     name = "high_quality"
#     pdf_parsing_mode = PDFParsingMode.OCR
#     chunking_mode = ChunkingMode.AGENTIC_SPLITTER
#     max_size_block = 2000
#     chunk_overlap = 100
#
# class FastConfig(BaseIngestionConfig):
#     name = "fast"
#     pdf_parsing_mode = PDFParsingMode.MANUAL
#     chunking_mode = ChunkingMode.LANGCHAIN
#     max_size_block = 1500
```

Use with the `ingest` command:

```bash
python manage.py ingest documentation ./docs/ --ingestion-config high_quality
```

#### Reference Formatters

Define how document blocks are formatted when referenced:

```python
# data/formatters.py
from cogsol.content import BaseReferenceFormatter
#
# class DetailedFormatter(BaseReferenceFormatter):
#     name = "detailed"
#     description = "Include page and category."
#     expression = "[{name}, p.{page_num}] ({metadata.category})"
#
# class SimpleFormatter(BaseReferenceFormatter):
#     name = "simple"
#     expression = "{name}"
```

#### Retrievals

Configure semantic search across topics:

```python
# data/retrievals.py
from cogsol.content import BaseRetrieval, ReorderingStrategy
# from data.formatters import DetailedFormatter
# from data.documentation.metadata import VersionMetadata
#
# class DocumentationRetrieval(BaseRetrieval):
#     name = "documentation_search"
#     topic = "documentation"
#     num_refs = 10
#     reordering = False
#     strategy_reordering = ReorderingStrategy.NONE
#     formatters = {"Text Document": DetailedFormatter}
#     filters = []
#
# class FilteredRetrieval(BaseRetrieval):
#     name = "v2_docs"
#     topic = "documentation"
#     num_refs = 5
#     filters = [VersionMetadata]
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COGSOL_API_BASE` | Yes | Base URL for the CogSol Cognitive API |
| `COGSOL_CONTENT_API_BASE` | No | Base URL for the CogSol Content API (defaults to `COGSOL_API_BASE`) |
| `COGSOL_API_TOKEN` | Yes | API authentication token |
| `COGSOL_ENV` | No | Environment name (e.g., `local`, `production`) |

### Project Settings (`settings.py`)

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_NAME = "myproject"
AGENTS_APP = "agents"
```

---

## API Reference

For detailed API documentation, see:

- [Architecture Documentation](docs/architecture.md)
- [CLI Commands Reference](docs/commands.md)
- [API Client Reference](docs/api.md)
- [Agents & Tools Reference](docs/agents-tools.md)

---

## License

Copyright © Cognitive Solutions

---

*This is an alpha release. APIs and features may change.*
