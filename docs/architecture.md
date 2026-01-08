# CogSol Framework Architecture

This document provides a comprehensive overview of the CogSol framework's internal architecture, explaining how the components work together.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Package Structure](#package-structure)
- [Component Deep Dive](#component-deep-dive)
- [Data Flow](#data-flow)
- [State Management](#state-management)
- [Extension Points](#extension-points)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CogSol Framework                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────────────────┐  │
│  │   CLI Layer   │────>│  Core Layer   │────>│      API Layer            │  │
│  │               │     │               │     │                           │  │
│  │ cogsol-admin  │     │ loader.py     │     │  CogSolClient             │  │
│  │ manage.py     │     │ migrations.py │     │  REST API calls           │  │
│  │ commands/*    │     │ management.py │     │                           │  │
│  └───────────────┘     └───────────────┘     └───────────────────────────┘  │
│         │                     │                           │                 │
│         ▼                     ▼                           ▼                 │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────────────────┐  │
│  │  Agent Layer  │     │ Migration DB  │     │    Remote CogSol API      │  │
│  │               │     │               │     │                           │  │
│  │ BaseAgent     │     │ .applied.json │     │  /assistants/             │  │
│  │ BaseTool      │     │ .state.json   │     │  /tools/scripts/          │  │
│  │ Prompts       │     │ *.py files    │     │  /chats/                  │  │
│  └───────────────┘     └───────────────┘     └───────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **CLI Layer** | Command-line interface and user interaction | `cogsol_admin.py`, `commands/*.py` |
| **Core Layer** | Business logic, module loading, state management | `loader.py`, `migrations.py`, `management.py` |
| **Agent Layer** | Agent and tool abstractions | `agents/__init__.py`, `tools/__init__.py` |
| **API Layer** | Communication with CogSol remote APIs | `api.py` |
| **Migration DB** | Local state persistence (JSON files) | `.applied.json`, `.state.json` |

---

## Package Structure

```
cogsol/
├── __init__.py              # Package entry, version info
├── prompts.py               # Prompt loading utilities
│
├── agents/                  # Agent abstractions
│   └── __init__.py          # BaseAgent, genconfigs, optimizations
│
├── tools/                   # Tool abstractions
│   └── __init__.py          # BaseTool, BaseFAQ, etc.
│
├── core/                    # Core functionality
│   ├── __init__.py
│   ├── api.py               # CogSolClient for API communication
│   ├── env.py               # Environment variable loading
│   ├── loader.py            # Module introspection and definition collection
│   ├── management.py        # Command dispatcher
│   └── migrations.py        # Migration state management
│
├── db/                      # Migration primitives
│   ├── __init__.py
│   └── migrations.py        # Migration operations (Create, Alter, Delete)
│
├── management/              # Management command infrastructure
│   ├── __init__.py
│   ├── base.py              # BaseCommand class
│   └── commands/            # Individual commands
│       ├── __init__.py
│       ├── chat.py          # Interactive chat command
│       ├── importagent.py   # Import from API command
│       ├── makemigrations.py # Generate migrations command
│       ├── migrate.py       # Apply migrations command
│       ├── startagent.py    # Create agent scaffold command
│       └── startproject.py  # Create project scaffold command
│
└── bin/                     # Entry points
    ├── __init__.py
    └── cogsol_admin.py      # Global CLI entry point
```

---

## Component Deep Dive

### 1. CLI Entry Points

#### `cogsol-admin` (bin/cogsol_admin.py)

The global command-line tool for creating new projects:

```python
def main() -> int:
    return execute_from_command_line(sys.argv)
```

This delegates to `core/management.py` which dispatches to the appropriate command.

#### `manage.py` (per-project)

Project-specific CLI that provides `project_path` context:

```python
def main():
    project_path = Path(__file__).resolve().parent
    execute_from_command_line(sys.argv, project_path=project_path)
```

### 2. Command Dispatcher (core/management.py)

Routes commands to their implementations:

```python
def _command_registry() -> dict[str, str]:
    return {
        "startproject": "cogsol.management.commands.startproject",
        "startagent": "cogsol.management.commands.startagent",
        "importagent": "cogsol.management.commands.importagent",
        "makemigrations": "cogsol.management.commands.makemigrations",
        "migrate": "cogsol.management.commands.migrate",
        "chat": "cogsol.management.commands.chat",
    }

def execute_from_command_line(argv=None, project_path=None) -> int:
    # 1. Parse command name from argv
    # 2. Load command module dynamically
    # 3. Instantiate and run command
    # 4. Pass project_path for context
```

### 3. Base Command (management/base.py)

All commands inherit from `BaseCommand`:

```python
class BaseCommand:
    requires_project: bool = True  # Most commands need project context
    help: str = ""
    
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add command-specific arguments."""
        pass
    
    def handle(self, project_path: Path | None, **options: Any) -> int:
        """Execute the command. Return 0 for success."""
        raise NotImplementedError
```

### 4. Module Loader (core/loader.py)

Responsible for introspecting project code and extracting definitions:

```python
def collect_definitions(project_path: Path, app_name: str = "agents"):
    """
    Import project modules and return structured definitions.
    
    Returns:
        {
            "agents": {
                "AgentClassName": {
                    "fields": {...},
                    "meta": {...}
                }
            },
            "tools": {
                "ToolName": {
                    "fields": {...},
                    "meta": {...}
                }
            }
        }
    """
```

Key functions:

| Function | Purpose |
|----------|---------|
| `collect_definitions()` | Extract serializable definitions from code |
| `collect_classes()` | Return actual class objects (for runtime use) |
| `serialize_value()` | Convert Python objects to JSON-safe values |
| `_extract_tool_params()` | Extract tool parameter metadata from signatures |
| `_import_module()` | Dynamically import project modules |

### 5. Migration System

The migration system tracks changes to agents and tools:

#### Migration Operations (db/migrations.py)

```python
class CreateAgent(CreateDefinition):
    """Create a new agent in state."""
    entity = "agents"

class CreateTool(CreateDefinition):
    """Create a new tool in state."""
    entity = "tools"

class AlterField:
    """Modify a field value."""
    model_name: str
    name: str
    value: Any
    entity: str  # "agents", "tools", etc.
    scope: str   # "fields" or "meta"

class DeleteDefinition:
    """Remove an entity from state."""
    name: str
    entity: str
```

#### Migration State Management (core/migrations.py)

```python
def state_from_migrations(migrations_path: Path) -> dict[str, Any]:
    """Replay all migrations to compute current state."""

def diff_states(previous: dict, current: dict) -> list[Any]:
    """Compare states and generate operations for changes."""

def iter_migration_files(migrations_path: Path) -> Iterable[Path]:
    """List migration files in order."""
```

#### Migration File Format

Generated migration files follow this structure:

```python
# Generated by CogSol 0.1.0 on 2024-01-15 10:30
from cogsol.db import migrations

class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateAgent(
            name='CustomerSupportAgent',
            fields={...},
            meta={...}
        ),
        migrations.CreateTool(
            name='SearchTool',
            fields={...}
        ),
    ]
```

### 6. API Client (core/api.py)

Communicates with the remote CogSol API:

```python
@dataclass
class CogSolClient:
    base_url: str
    token: Optional[str] = None
    
    # Core request method
    def request(self, method: str, path: str, payload: Optional[dict] = None) -> Any
    
    # Resource operations
    def upsert_assistant(self, *, remote_id: Optional[int], payload: dict) -> int
    def upsert_script(self, *, remote_id: Optional[int], payload: dict) -> int
    def upsert_common_question(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    def upsert_fixed_response(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    def upsert_lesson(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    
    # Chat operations
    def create_chat(self, assistant_id: int, message: Optional[str] = None) -> Any
    def send_message(self, chat_id: int, message: str) -> Any
    def get_chat(self, chat_id: int) -> Any
    
    # Delete operations
    def delete_assistant(self, assistant_id: int) -> None
    def delete_script(self, script_id: int) -> None
    # ... etc.
```

### 7. Agent Abstractions (agents/__init__.py)

```python
class BaseAgent:
    """Base class for all CogSol agents."""
    
    # Prompt configuration
    system_prompt: Any = None
    initial_message: Optional[str] = None
    forced_termination_message: Optional[str] = None
    no_information_message: Optional[str] = None
    
    # Generation configuration
    pregeneration_config: Any = None
    generation_config: Any = None
    temperature: Optional[float] = None
    
    # Tools
    pretools: list[Any] = []
    tools: list[Any] = []
    
    # Limits
    max_interactions: Optional[int] = None
    user_message_length: Optional[int] = None
    consecutive_tool_calls_limit: Optional[int] = None
    
    # Features
    streaming: bool = False
    realtime: bool = False
    
    # Related content
    lessons: list[Any] = []
    faqs: list[Any] = []
    fixed_responses: list[Any] = []
    
    class Meta:
        name: Optional[str] = None
        chat_name: Optional[str] = None
        logo_url: Optional[str] = None
        # Color configuration
        assistant_name_color: Optional[str] = None
        primary_color: Optional[str] = None
        secondary_color: Optional[str] = None
        border_color: Optional[str] = None
    
    @classmethod
    def definition(cls) -> dict[str, Any]:
        """Extract class attributes for migration tooling."""
```

### 8. Tool Abstractions (tools/__init__.py)

```python
class BaseTool:
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: dict[str, Any] = {}
    
    def run(self, *args, **kwargs) -> Any:
        """Override to implement tool logic."""
        raise NotImplementedError

class BaseFAQ:
    question: Optional[str] = None
    answer: Optional[str] = None

class BaseFixedResponse:
    key: Optional[str] = None
    response: Optional[str] = None

class BaseLesson:
    name: Optional[str] = None
    content: Optional[str] = None

def tool_params(**params):
    """Decorator to attach parameter metadata to run()."""
    def decorator(func):
        setattr(func, "__tool_params__", params)
        return func
    return decorator
```

---

## Data Flow

### 1. Creating Migrations (makemigrations)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Project Code   │───>│ collect_defs()  │───>│ Current State   │
│  (*.py files)   │    │ (loader.py)     │    │ (in-memory)     │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                       ┌─────────────────┐             │
                       │ Previous State  │<────────────┤
                       │ (from .py migs) │             │
                       └────────┬────────┘             │
                                │                      │
                                ▼                      ▼
                       ┌─────────────────────────────────┐
                       │        diff_states()            │
                       │ Compare & Generate Operations   │
                       └────────────────┬────────────────┘
                                        │
                                        ▼
                       ┌─────────────────────────────────┐
                       │    New Migration File           │
                       │    (0002_auto_*.py)             │
                       └─────────────────────────────────┘
```

### 2. Applying Migrations (migrate)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Migration Files │───>│ apply_ops()     │───>│ Final State     │
│ (*.py files)    │    │ (db/migrations) │    │ (in-memory)     │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                       ┌─────────────────┐             │
                       │ collect_classes │<────────────┤
                       │ (loader.py)     │             │
                       └────────┬────────┘             │
                                │                      │
                                ▼                      ▼
                       ┌─────────────────────────────────┐
                       │       _sync_with_api()          │
                       │  Upsert to Remote CogSol API    │
                       └────────────────┬────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                   ┌─────────┐   ┌─────────────┐   ┌─────────┐
                   │ .state  │   │ .applied    │   │ Remote  │
                   │  .json  │   │   .json     │   │   API   │
                   └─────────┘   └─────────────┘   └─────────┘
```

### 3. Chat Interaction (chat)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  User Input     │───>│ CogSolClient    │───>│ Remote API      │
│  (terminal)     │    │ send_message()  │    │ /chats/{id}/    │
└─────────────────┘    └─────────────────┘    └────────┬────────┘
                                                       │
                                                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Display        │<───│ Format Message  │<───│ AI Response     │
│  (styled)       │    │ (chat.py)       │    │ (JSON)          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

## State Management

### State Files

The framework maintains two JSON files in `agents/migrations/`:

#### `.applied.json`

Tracks which migrations have been applied:

```json
[
    "0001_initial",
    "0002_auto_20240115_1030",
    "0003_add_tool"
]
```

#### `.state.json`

Stores current state and remote ID mappings:

```json
{
    "state": {
        "agents": {
            "CustomerSupportAgent": {
                "fields": {
                    "system_prompt": "support.md",
                    "temperature": 0.3,
                    "tools": ["SearchTool"],
                    ...
                },
                "meta": {
                    "name": "CustomerSupportAgent",
                    "chat_name": "Customer Support"
                }
            }
        },
        "tools": {
            "SearchTool": {
                "fields": {
                    "name": "SearchTool",
                    "description": "Search the knowledge base",
                    "parameters": {...},
                    "__code__": "..."
                },
                "meta": {}
            }
        },
        "faqs": {},
        "fixed_responses": {},
        "lessons": {}
    },
    "remote": {
        "agents": {
            "CustomerSupportAgent": 42
        },
        "tools": {
            "SearchTool": 15
        },
        "faqs": {},
        "fixed_responses": {},
        "lessons": {}
    }
}
```

### State Consistency

The migration system ensures consistency through:

1. **Idempotent Operations**: Operations can be safely re-applied
2. **Rollback on Failure**: API sync failures trigger rollback of created resources
3. **Remote ID Tracking**: Local names are mapped to remote IDs for updates

---

## Extension Points

### Adding New Commands

1. Create a new file in `cogsol/management/commands/`:

```python
from cogsol.management.base import BaseCommand

class Command(BaseCommand):
    help = "Description of your command"
    requires_project = True  # or False
    
    def add_arguments(self, parser):
        parser.add_argument("--option", help="An option")
    
    def handle(self, project_path, **options):
        # Implementation
        return 0  # Exit code
```

2. Register in `core/management.py`:

```python
def _command_registry():
    return {
        # ... existing commands
        "mycommand": "cogsol.management.commands.mycommand",
    }
```

### Adding New Tool Types

Extend `BaseTool` with custom behavior:

```python
class BaseAPITool(BaseTool):
    """Tool that makes external API calls."""
    
    api_url: Optional[str] = None
    headers: dict[str, str] = {}
    
    def call_api(self, endpoint: str, data: dict) -> dict:
        # Common API calling logic
        pass
```

### Custom Generation Configs

Add new configs in `agents/__init__.py`:

```python
class genconfigs:
    class QA(_ConfigBase):
        def __init__(self, **kwargs):
            super().__init__("qa")
            self.params = kwargs
    
    class Creative(_ConfigBase):
        def __init__(self, **kwargs):
            super().__init__("creative")
            self.params = kwargs
```

**Important:** This should be aligned with available genconfigs in CogSol API (Generator API).