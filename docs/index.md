# CogSol Framework Documentation

Welcome to the CogSol Framework documentation. This documentation provides comprehensive guides and references for building AI agents with CogSol.

## Quick Links

| Document | Description |
|----------|-------------|
| [Getting Started](getting-started.md) | Step-by-step tutorial for new users |
| [Architecture](architecture.md) | Deep dive into how CogSol works |
| [CLI Commands](commands.md) | Complete command reference |
| [Agents & Tools](agents-tools.md) | Building agents and tools |
| [API Client](api.md) | REST API integration |

---

## Overview

CogSol is a lightweight, agent-first Python framework for building, managing, and deploying AI assistants. It follows a Django-like development pattern with:

- **Code-First Definitions**: Define agents and tools as Python classes
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
   - Creating migrations
   - Deployment

### For Developers

2. **[Architecture](architecture.md)** - Framework internals
   - Package structure
   - Component relationships
   - Data flow
   - State management
   - Extension points

3. **[Agents & Tools](agents-tools.md)** - Building blocks
   - BaseAgent reference
   - BaseTool reference
   - FAQs, Fixed Responses, Lessons
   - Prompts
   - Best practices

### For Operations

4. **[CLI Commands](commands.md)** - Command reference
   - startproject
   - startagent
   - makemigrations
   - migrate
   - importagent
   - chat

5. **[API Client](api.md)** - Remote integration
   - CogSolClient usage
   - API endpoints
   - Payloads
   - Error handling

---

## Framework at a Glance

```
┌─────────────────────────────────────────────────────────────────┐
│                        Your Project                             │
├─────────────────────────────────────────────────────────────────┤
│  agents/                                                        │
│  ├── tools.py          ← Shared tools                          │
│  ├── migrations/       ← Change tracking                        │
│  └── <agent>/          ← Per-agent packages                     │
│      ├── agent.py      ← Agent definition                       │
│      ├── faqs.py       ← FAQs                                   │
│      ├── fixed.py      ← Fixed responses                        │
│      ├── lessons.py    ← Lessons                                │
│      └── prompts/      ← System prompts                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CogSol Framework                           │
├─────────────────────────────────────────────────────────────────┤
│  cogsol/                                                        │
│  ├── agents/           ← Agent abstractions                     │
│  ├── tools/            ← Tool abstractions                      │
│  ├── core/             ← Core functionality                     │
│  └── management/       ← CLI commands                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       CogSol API                                │
├─────────────────────────────────────────────────────────────────┤
│  /assistants/          ← Agent definitions                      │
│  /tools/scripts/       ← Tool implementations                   │
│  /chats/               ← Conversations                          │
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
    tools = [SearchTool(), OrderTool()]
    temperature = 0.3
    
    class Meta:
        name = "SupportAgent"
        chat_name = "Customer Support"
```

### Tools

Tools extend agent capabilities:

```python
from cogsol.tools import BaseTool, tool_params

class SearchTool(BaseTool):
    description = "Search the knowledge base"
    
    @tool_params(query={"description": "Search query", "type": "string", "required": True})
    def run(self, chat=None, data=None, secrets=None, log=None, query: str = ""):
        results = perform_search(query)
        return format_results(results)
```

### Migrations

Track and deploy changes:

```bash
# Detect changes
python manage.py makemigrations

# Deploy to API
python manage.py migrate
```

### Interactive Chat

Test your agents:

```bash
python manage.py chat --agent SupportAgent
```

---

## Version

This documentation is for CogSol Framework **v0.1.0** (Alpha).

---

## Contributing

See the main [README.md](../README.md) for contribution guidelines.

---

## License

Copyright © Cognitive Solutions
