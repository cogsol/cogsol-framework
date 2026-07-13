# CogSol Framework

**Version:** 0.2.1 (Alpha)

CogSol is a lightweight, agent-first Python framework for building, managing, and deploying AI assistants. It provides scaffolding, agent abstractions, and file-based migration utilities for CogSol projects without requiring an external database.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)

---

## Overview

CogSol is designed to provide a Django-like development experience for building AI agents. It uses a code-first approach where you define your agents, tools, and configurations in Python, then use migrations to sync with a remote CogSol API.

### Design Philosophy

- **Code-First**: Define agents and tools as Python classes
- **Migration-Based Deployments**: Track changes via migrations (similar to Django)
- **No Database Required**: Uses JSON files for state tracking
- **API-Synchronized**: Push local definitions to remote CogSol APIs

---

## Key Features

| Feature                | Description                                                              |
| ---------------------- | ------------------------------------------------------------------------ |
| **Agent Definitions**  | Define AI agents as Python classes with configurable attributes          |
| **Tool System**        | Create reusable tools with typed parameters and decorators               |
| **Topics & Documents** | Organize knowledge bases with hierarchical topics and document ingestion |
| **Retrievals**         | Configure semantic search across your document collections               |
| **Migrations**         | Track and version agent/tool/topic changes                               |
| **Remote Sync**        | Push definitions to CogSol Cognitive and Content APIs                    |
| **Interactive Chat**   | Built-in CLI for testing agents                                          |
| **Import/Export**      | Import existing assistants from the API                                  |

---

## Installation

```bash
# Option A: Install from source
git clone <repository-url> cogsol-framework
cd cogsol-framework

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -e .

# Option B: Install from PyPI
pip install cogsol-framework
```

Using a local `.venv` keeps project dependencies isolated and prevents conflicts with global Python packages.

### Requirements

- Python 3.9+

After installation, the `cogsol-admin` command becomes available globally.

---

## Quick Start

```bash
# Scaffold a new project
cogsol-admin startproject myproject
cd myproject

# Configure API credentials and LLM provider
cogsol-admin credentials-setup

# Scaffold a new agent
python manage.py startagent SalesAgent

# Generate migration files from your agent/tool/topic definitions
python manage.py makemigrations

# Apply migrations (sync definitions to the remote CogSol API)

python manage.py migrate
# Configure Your LLM Provider

Add the API key of your preferred LLM provider (OpenAI, Google Gemini, or Anthropic) at [CogSol Platform](https://platform.cogsol.ai/configuration/services).
# Start an interactive chat session with the agent
python manage.py chat --agent SalesAgent
```

For the full walkthrough (topics, document ingestion, LLM provider setup, troubleshooting), see [docs/getting-started.md](docs/getting-started.md).

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

## Documentation

| Doc                                                | Covers                                                                                                |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| [docs/getting-started.md](docs/getting-started.md) | Full step-by-step tutorial: install → project → agent → topics/ingestion → migrations → deploy → chat |
| [docs/commands.md](docs/commands.md)               | Complete CLI reference, including credentials setup                                                   |
| [docs/agents-tools.md](docs/agents-tools.md)       | `BaseAgent`, `BaseTool`, `BaseRetrievalTool`, FAQs/Fixed/Lessons, Topics, Retrievals                  |
| [docs/architecture.md](docs/architecture.md)       | Framework internals: package structure, data flow, state management                                   |
| [docs/api.md](docs/api.md)                         | `CogSolClient` REST API reference (Cognitive & Content APIs)                                          |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common errors and debug tips                                                                          |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

---

## License

Copyright © Cognitive Solutions

---

> **Alpha release:** APIs and features may change between versions.
