# CogSol Framework

**Version:** 0.1.0 (Alpha)

CogSol is a lightweight, agent-first Python framework for building, managing, and deploying AI assistants. It provides scaffolding, agent abstractions, and file-based migration utilities for CogSol projects without requiring an external database.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [CLI Commands](#cli-commands)
- [Core Concepts](#core-concepts)
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
| **Migrations** | Track and version agent/tool changes |
| **Remote Sync** | Push definitions to CogSol APIs |
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
└── agents/
    ├── __init__.py
    ├── tools.py        # Global tool definitions
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

Generate migration files based on agent/tool changes.

```bash
python manage.py makemigrations [app] [--name <suffix>]
```

**Arguments:**
- `app`: (Optional) App to migrate, defaults to `agents`
- `--name`: (Optional) Custom migration name suffix

### `migrate`

Apply pending migrations and sync with the CogSol API.

```bash
python manage.py migrate [app]
```

**Arguments:**
- `app`: (Optional) App to migrate, defaults to `agents`

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

class SearchTool(BaseTool):
    description = "Search for information in the knowledge base."
    
    @tool_params(
        query={"description": "Search query", "type": "string", "required": True},
        limit={"description": "Max results", "type": "integer", "required": False},
    )
    def run(self, chat=None, data=None, secrets=None, log=None, 
            query: str = "", limit: int = 10):
        """
        query: The search query.
        limit: Maximum number of results.
        """
        # Implementation here
        results = perform_search(query, limit)
        response = format_results(results)
        return response
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

class PricingFAQ(BaseFAQ):
    question = "What are your pricing plans?"
    answer = "We offer three tiers: Basic ($10/mo), Pro ($25/mo), Enterprise (custom)."
```

#### Fixed Responses (`fixed.py`)

```python
from cogsol.tools import BaseFixedResponse

class ClosingFixed(BaseFixedResponse):
    key = "goodbye"
    response = "Thank you for contacting us. Have a great day!"
```

#### Lessons (`lessons.py`)

```python
from cogsol.tools import BaseLesson

class ToneLesson(BaseLesson):
    name = "Communication Tone"
    content = "Always maintain a professional yet friendly tone."
    context_of_application = "general"
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

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `COGSOL_API_BASE` | Yes | Base URL for the CogSol API |
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
