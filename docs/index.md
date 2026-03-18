# CogSol Framework Documentation

Welcome to the CogSol Framework documentation. This documentation provides comprehensive guides and references for building AI agents with CogSol.

## Quick Links

| Document | Description |
|----------|-------------|
| [Getting Started](getting-started.md) | Step-by-step tutorial for new users |
| [Architecture](architecture.md) | Deep dive into how CogSol works |
| [CLI Commands](commands.md) | Complete command reference |
| [Agents & Tools](agents-tools.md) | Building agents, tools, and retrieval tools |
| [API Client](api.md) | REST API integration (Cognitive & Content) |

---

## Overview

CogSol is a lightweight, agent-first Python framework for building, managing, and deploying AI assistants. It follows a Django-like development pattern with:

- **Code-First Definitions**: Define agents, tools, and topics as Python classes
- **Two Application Structure**: Separate `agents/` (Cognitive API) and `data/` (Content API)
- **Migration-Based Deployments**: Track changes and sync with remote APIs
- **No Database Required**: Uses JSON files for state management
- **Minimal Dependencies**: Built on Python standard library only

---

## Documentation Structure

### For New Users

1. **[Getting Started](getting-started.md)** - Your first CogSol project
   - Installation
   - Project creation
   - Building your first agent
   - Working with documents and topics
   - Creating migrations
   - Deployment

### For Developers

2. **[Architecture](architecture.md)** - Framework internals
   - Package structure
   - Two-app design (agents + data)
   - Component relationships
   - Data flow
   - State management
   - Extension points

3. **[Agents & Tools](agents-tools.md)** - Building blocks
   - BaseAgent reference
   - BaseTool reference
   - BaseRetrievalTool reference
   - FAQs, Fixed Responses, Lessons
   - Topics and Retrievals
   - Prompts
   - Best practices

### For Operations

4. **[CLI Commands](commands.md)** - Command reference
   - startproject
   - startagent / starttopic
   - makemigrations
   - migrate
   - ingest / topics
   - importagent
   - chat

5. **[API Client](api.md)** - Remote integration
   - CogSolClient usage
   - Cognitive API endpoints
   - Content API endpoints
   - Payloads
   - Error handling

---

## Framework at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Project                             │
├─────────────────────────────────────────────────────────────────┤
│  agents/                        data/                           │
│  ├── tools.py                   ├── formatters.py               │
│  ├── searches.py                ├── ingestion.py                │
│  ├── migrations/                ├── retrievals.py               │
│  └── <agent>/                   ├── migrations/                 │
│      ├── agent.py               └── <topic>/                    │
│      ├── faqs.py                    ├── __init__.py             │
│      ├── fixed.py                   └── metadata.py             │
│      ├── lessons.py                                             │
│      └── prompts/                                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CogSol Framework                           │
├─────────────────────────────────────────────────────────────────┤
│  cogsol/                                                        │
│  ├── agents/           ← Agent abstractions                     │
│  ├── tools/            ← Tool & retrieval tool abstractions     │
│  ├── content/          ← Topic, retrieval, formatter classes    │
│  ├── core/             ← Core functionality                     │
│  └── management/       ← CLI commands                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       CogSol APIs                               │
├─────────────────────────────────────────────────────────────────┤
│  Cognitive API                  Content API                     │
│  ├── /assistants/               ├── /nodes/                     │
│  ├── /tools/scripts/            ├── /retrievals/                │
│  ├── /tools/retrievals/         ├── /documents/                 │
│  └── /chats/                    └── /reference_formatters/      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### Agents

Agents are AI assistants defined as Python classes:

```python
from cogsol.agents import BaseAgent, genconfigs
from cogsol.prompts import Prompts

class SupportAgent(BaseAgent):
    system_prompt = Prompts.load("support.md")
    generation_config = genconfigs.QA()
    tools = [
        DateTool(),    # Script tool: executes Python capability
        DocsSearch(),  # Retrieval tool: searches topic documents
    ]
    temperature = 0.3
    
    class Meta:
        name = "SupportAgent"
        chat_name = "Customer Support"
```

Both tool types are configured in the same `tools` list. Use script tools for actions/calculations and retrieval tools for document search.

### Tools

Tools are Python capabilities that perform actions with custom logic, extending the agent's capabilities::

```python
from cogsol.tools import BaseTool
from datetime import datetime

class DateTool(BaseTool):
    description = "Return the current date in YYYY-MM-DD format"

    def run(self, chat=None, data=None, secrets=None, log=None):
        return datetime.utcnow().strftime("%Y-%m-%d")
```

### Retrieval Tools

Retrieval tools (searches) are specialized for semantic retrieval from topic documents through the Content API:

```python
from cogsol.tools import BaseRetrievalTool
from data.retrievals import ProductDocsRetrieval

class DocsSearch(BaseRetrievalTool):
    name = "docs_search"
    description = "Search product documentation"
    retrieval = ProductDocsRetrieval()
```

### Topics & Documents

Organize document collections with topics:

```python
from cogsol.content import BaseTopic

class ProductDocsTopic(BaseTopic):
    name = "product_docs"
    
    class Meta:
        description = "Product documentation and guides"
```

### Migrations

Track and deploy changes:

```bash
# Detect changes in both agents and data
python manage.py makemigrations

# Deploy to APIs
python manage.py migrate
```

### Interactive Chat

Test your agents:

```bash
python manage.py chat --agent SupportAgent
```

---

## Version

This documentation is for CogSol Framework **v0.2.1**.

---

## Contributing

See the main [README.md](../README.md) for contribution guidelines.

---

## License

Copyright © Cognitive Solutions
