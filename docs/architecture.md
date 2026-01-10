# CogSol Framework Architecture

This document provides a comprehensive overview of the CogSol framework's internal architecture, explaining how the components work together.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [Package Structure](#package-structure)
- [Two-Application Design](#two-application-design)
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
│  │ manage.py     │     │ migrations.py │     │  - Cognitive API          │  │
│  │ commands/*    │     │ management.py │     │  - Content API            │  │
│  └───────────────┘     └───────────────┘     └───────────────────────────┘  │
│         │                     │                           │                 │
│         ▼                     ▼                           ▼                 │
│  ┌───────────────┐     ┌───────────────┐     ┌───────────────────────────┐  │
│  │  Agent Layer  │     │ Migration DB  │     │    Remote CogSol APIs     │  │
│  │               │     │               │     │                           │  │
│  │ BaseAgent     │     │ .applied.json │     │  Cognitive API:           │  │
│  │ BaseTool      │     │ .state.json   │     │  - /assistants/           │  │
│  │ BaseRetrieval │     │ *.py files    │     │  - /tools/scripts/        │  │
│  │ BaseTopic     │     │               │     │  - /tools/retrievals/     │  │
│  │ Prompts       │     │               │     │                           │  │
│  └───────────────┘     └───────────────┘     │  Content API:             │  │
│                                              │  - /nodes/                │  │
│                                              │  - /retrievals/           │  │
│                                              │  - /documents/            │  │
│                                              │  - /reference_formatters/ │  │
│                                              └───────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Purpose | Key Files |
|-------|---------|-----------|
| **CLI Layer** | Command-line interface and user interaction | `cogsol_admin.py`, `commands/*.py` |
| **Core Layer** | Business logic, module loading, state management | `loader.py`, `migrations.py`, `management.py` |
| **Agent Layer** | Agent, tool, and content abstractions | `agents/__init__.py`, `tools/__init__.py`, `content/__init__.py` |
| **API Layer** | Communication with CogSol Cognitive and Content APIs | `api.py` |
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
│   └── __init__.py          # BaseTool, BaseFAQ, BaseRetrievalTool, etc.
│
├── content/                 # Content API abstractions
│   └── __init__.py          # BaseTopic, BaseRetrieval, BaseReferenceFormatter, etc.
│
├── core/                    # Core functionality
│   ├── __init__.py
│   ├── api.py               # CogSolClient for Cognitive & Content API
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
│       ├── ingest.py        # Document ingestion command
│       ├── makemigrations.py # Generate migrations command
│       ├── migrate.py       # Apply migrations command
│       ├── startagent.py    # Create agent scaffold command
│       ├── startproject.py  # Create project scaffold command
│       ├── starttopic.py    # Create topic scaffold command
│       └── topics.py        # List topics command
│
└── bin/                     # Entry points
    ├── __init__.py
    └── cogsol_admin.py      # Global CLI entry point
```

---

## Two-Application Design

CogSol uses a **two-application architecture** that separates agent logic from document management:

```
your_project/
├── agents/                  # Cognitive API entities
│   ├── tools.py             # Custom tool definitions
│   ├── searches.py          # Retrieval tool definitions
│   ├── migrations/          # Agent/tool migrations
│   └── <agent>/             # Per-agent packages
│       ├── agent.py
│       ├── faqs.py
│       ├── fixed.py
│       ├── lessons.py
│       └── prompts/
│
└── data/                    # Content API entities
    ├── formatters.py        # Reference formatter definitions
    ├── ingestion.py         # Ingestion configuration definitions
    ├── retrievals.py        # Retrieval configuration definitions
    ├── migrations/          # Topic/retrieval migrations
    └── <topic>/             # Per-topic folders (can be nested)
        ├── __init__.py      # Topic definition
        └── metadata.py      # Metadata configurations
```

### Why Two Applications?

| Application | API | Purpose |
|-------------|-----|---------|
| `agents/` | Cognitive API | AI assistants, tools, FAQs, lessons, fixed responses |
| `data/` | Content API | Document organization, semantic search, retrievals |

This separation:
- Allows independent versioning of agent logic and document structure
- Enables different teams to manage agents vs content
- Provides clear boundaries between AI behavior and knowledge base

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
        "starttopic": "cogsol.management.commands.starttopic",
        "topics": "cogsol.management.commands.topics",
        "ingest": "cogsol.management.commands.ingest",
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
            "tools": {...},
            "retrieval_tools": {...},
            "faqs": {...},
            "fixed_responses": {...},
            "lessons": {...}
        }
    """

def collect_content_definitions(project_path: Path, app_name: str = "data"):
    """
    Import data/ modules and return structured content definitions.
    
    Returns:
        {
            "topics": {...},
            "formatters": {...},
            "ingestion_configs": {...},
            "retrievals": {...},
            "metadata_configs": {...}
        }
    """
```

Key functions:

| Function | Purpose |
|----------|---------|
| `collect_definitions()` | Extract agent/tool definitions from `agents/` |
| `collect_content_definitions()` | Extract topic/retrieval definitions from `data/` |
| `collect_classes()` | Return actual class objects (for runtime use) |
| `collect_content_classes()` | Return actual content class objects |
| `serialize_value()` | Convert Python objects to JSON-safe values |
| `_extract_tool_params()` | Extract tool parameter metadata from signatures |
| `_import_module()` | Dynamically import project modules |

### 5. Migration System

The migration system tracks changes to agents, tools, topics, and retrievals:

#### Migration Operations (db/migrations.py)

```python
# Cognitive API operations
class CreateAgent(CreateDefinition):
    """Create a new agent in state."""
    entity = "agents"

class CreateTool(CreateDefinition):
    """Create a new tool in state."""
    entity = "tools"

class CreateRetrievalTool(CreateDefinition):
    """Create a new retrieval tool in state."""
    entity = "retrieval_tools"

# Content API operations
class CreateTopic(CreateDefinition):
    """Create a new topic (node) in state."""
    entity = "topics"

class CreateMetadataConfig(CreateDefinition):
    """Create a metadata configuration for a topic."""
    entity = "metadata_configs"

class CreateReferenceFormatter(CreateDefinition):
    """Create a reference formatter in state."""
    entity = "formatters"

class CreateRetrieval(CreateDefinition):
    """Create a retrieval configuration in state."""
    entity = "retrievals"

class AlterField:
    """Modify a field value."""
    model_name: str
    name: str
    value: Any
    entity: str  # "agents", "tools", "topics", etc.
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

def diff_states(previous: dict, current: dict, app: str = "agents") -> list[Any]:
    """Compare states and generate operations for changes.
    
    Args:
        app: Either "agents" (Cognitive API) or "data" (Content API)
    """

def iter_migration_files(migrations_path: Path) -> Iterable[Path]:
    """List migration files in order."""
```

#### Migration File Format

Generated migration files follow this structure:

```python
# Generated by CogSol 0.2.0 on 2026-01-08 10:30
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

Communicates with both the Cognitive API and Content API:

```python
@dataclass
class CogSolClient:
    base_url: str                          # Cognitive API base URL
    token: Optional[str] = None
    content_base_url: Optional[str] = None # Content API base URL
    
    # Core request method
    def request(self, method: str, path: str, payload: Optional[dict] = None,
                use_content_api: bool = False) -> Any
    
    # Multipart file upload (for document ingestion)
    def request_multipart(self, method: str, path: str, fields: dict,
                          files: dict[str, Path], use_content_api: bool = False) -> Any
    
    # Cognitive API - Assistants
    def upsert_assistant(self, *, remote_id: Optional[int], payload: dict) -> int
    def upsert_script(self, *, remote_id: Optional[int], payload: dict) -> int
    def upsert_retrieval_tool(self, *, remote_id: Optional[int], payload: dict) -> int
    def upsert_common_question(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    def upsert_fixed_response(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    def upsert_lesson(self, *, assistant_id: int, remote_id: Optional[int], payload: dict) -> int
    
    # Cognitive API - Chat
    def create_chat(self, assistant_id: int, message: Optional[str] = None) -> Any
    def send_message(self, chat_id: int, message: str) -> Any
    def get_chat(self, chat_id: int) -> Any
    
    # Content API - Nodes (Topics)
    def list_nodes(self, page: int = 1, page_size: int = 100) -> Any
    def get_node(self, node_id: int) -> Any
    def upsert_node(self, *, remote_id: Optional[int], payload: dict) -> int
    def delete_node(self, node_id: int) -> None
    
    # Content API - Retrievals
    def list_retrievals(self) -> Any
    def upsert_retrieval(self, *, remote_id: Optional[int], payload: dict) -> int
    def retrieve_similar_blocks(self, retrieval_id: int, question: str) -> Any
    
    # Content API - Documents
    def upload_document(self, *, file_path: Path, name: str, node_id: int, ...) -> int
    def upload_documents_bulk(self, *, file_paths: list[Path], node_id: int, ...) -> list[int]
    
    # Content API - Reference Formatters
    def upsert_reference_formatter(self, *, remote_id: Optional[int], payload: dict) -> int
    
    # Content API - Metadata Configs
    def create_metadata_config(self, *, node_id: int, payload: dict) -> int
    def update_metadata_config(self, config_id: int, payload: dict) -> Any
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

class BaseRetrievalTool:
    """Tool that queries Content API retrievals."""
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: list[dict[str, Any]] = []
    retrieval: Optional[type] = None  # Reference to a BaseRetrieval class
    show_tool_message: bool = False
    show_assistant_message: bool = False
    edit_available: bool = True
    answer: bool = True

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

### 9. Content Abstractions (content/__init__.py)

```python
class BaseTopic:
    """Represents a node in the Content API."""
    name: Optional[str] = None
    delete_orphaned_metadata: bool = False

    class Meta:
        description: Optional[str] = None

class BaseMetadataConfig:
    """Metadata field configuration for a topic."""
    name: Optional[str] = None
    type: MetadataType = MetadataType.STRING
    possible_values: list[str] = []
    default_value: Optional[str] = None
    format: Optional[str] = None
    filtrable: bool = False
    required: bool = False
    in_embedding: bool = False
    in_retrieval: bool = True

class BaseReferenceFormatter:
    """Formats document block references."""
    name: Optional[str] = None
    description: Optional[str] = ""
    expression: Optional[str] = None

class BaseIngestionConfig:
    """Configuration for document processing."""
    name: Optional[str] = None
    default_topic: Optional[type] = None
    pdf_parsing_mode: PDFParsingMode = PDFParsingMode.BOTH
    chunking_mode: ChunkingMode = ChunkingMode.LANGCHAIN
    max_size_block: int = 1500
    chunk_overlap: int = 0
    separators: list[str] = []
    ocr: bool = False
    additional_prompt_instructions: str = ""
    assign_paths_as_metadata: bool = False

class BaseRetrieval:
    """Semantic search configuration."""
    name: Optional[str] = None
    topic: Optional[type] = None
    num_refs: int = 10
    max_msg_length: int = 570
    reordering: bool = False
    strategy_reordering: Optional[ReorderingStrategy] = None
    retrieval_window: int = 20
    reordering_metadata: Optional[str] = None
    fixed_blocks_reordering: int = 3
    previous_blocks: float = 0
    next_blocks: float = 0
    contingency_for_embedding: bool = True
    threshold_similarity: float = 0.75
    formatters: dict[str, type] = {}
    filters: list[type] = []
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

The framework maintains two JSON files in each app's `migrations/` folder:

#### `agents/migrations/.applied.json`

Tracks which migrations have been applied:

```json
[
    "0001_initial",
    "0002_auto_20240115_1030",
    "0003_add_tool"
]
```

#### `agents/migrations/.state.json`

Stores current state and remote ID mappings:

```json
{
    "state": {
        "agents": {
            "CustomerSupportAgent": {
                "fields": {
                    "system_prompt": "You are a helpful assistant...",
                    "temperature": 0.3,
                    "tools": ["SearchTool", "DocsSearch"]
                },
                "meta": {
                    "name": "CustomerSupportAgent",
                    "chat_name": "Customer Support"
                }
            }
        },
        "tools": {
            "SearchTool": {
                "fields": {...}
            }
        },
        "retrieval_tools": {
            "DocsSearch": {
                "fields": {
                    "name": "docs_search",
                    "retrieval": "product_docs_search"
                }
            }
        },
        "faqs": {},
        "fixed_responses": {},
        "lessons": {}
    },
    "remote": {
        "agents": {"CustomerSupportAgent": 42},
        "tools": {"SearchTool": 15},
        "retrieval_tools": {"DocsSearch": 23}
    }
}
```

#### `data/migrations/.state.json`

Stores Content API state and remote ID mappings:

```json
{
    "state": {
        "topics": {
            "product_docs": {
                "fields": {"name": "product_docs"},
                "meta": {"description": "Product documentation"}
            },
            "product_docs/tutorials": {
                "fields": {"name": "tutorials"},
                "meta": {}
            }
        },
        "formatters": {
            "detailed_formatter": {
                "fields": {
                    "name": "detailed_formatter",
                    "expression": "[{name}, p.{page_num}]"
                }
            }
        },
        "retrievals": {
            "product_docs_search": {
                "fields": {
                    "name": "product_docs_search",
                    "topic": "product_docs",
                    "num_refs": 10
                }
            }
        },
        "ingestion_configs": {},
        "metadata_configs": {}
    },
    "remote": {
        "topics": {"product_docs": 1, "product_docs/tutorials": 2},
        "formatters": {"detailed_formatter": 5},
        "retrievals": {"product_docs_search": 10}
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