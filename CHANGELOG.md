# Changelog

All notable changes to the CogSol Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Changed
- `cogsol-admin startproject` cookbook source/auth configuration is now explicit via CLI flags (`--cookbook-repo`, `--github-token`) instead of relying on `.env` cookbook variables.

---

## [0.2.1] - 2026-03-11

### Added
- Optional Azure AD B2C client-credentials authentication in `CogSolClient` (`COGSOL_AUTH_CLIENT_ID`, `COGSOL_AUTH_SECRET`) with automatic bearer token acquisition.

### Changed
- API key configuration standardized on `COGSOL_API_KEY` (replacing `COGSOL_API_TOKEN`) across framework helpers and CLI commands.
- `CogSolClient` now sends `Authorization: Bearer <token>` when configured and retries once on `401` after refreshing credentials.
- API base URL resolution is now centralized through shared helpers with support for `COGSOL_ENV`, `COGSOL_API_BASE`, and `COGSOL_CONTENT_API_BASE`.
- When auth credentials are not configured, framework commands and clients fall back to legacy cognitive/content API base URLs.
- `startagent` now validates derived slugs and class names from the provided agent name, and generated templates no longer append a redundant `Chat` suffix to `chat_name`.
- Tool parameter sync now preserves `items` metadata for array-type parameters.
- `startproject` template `.env.example` now includes API key and optional auth credential placeholders.
- Runtime dependencies now include `msal` and `PyJWT`.

### Fixed
- Migration operation ordering for agents app dependencies to avoid first-run failures (agent entities are created before lessons/FAQs/fixed responses).
- `startproject` scaffold now includes an active `ExampleTool` implementation to match default project flow.
- Migration tool payload sync now preserves configurable flags such as `show_tool_message`, `show_assistant_message`, and `edit_available` instead of hardcoding them.
- Migration finalization now performs rollback of partially created API objects when sync fails.
- Tool migration sync now reads code from migration state/files more reliably, preserving helper methods, double quotes, and multiline helper/run signatures.
- Chat banner alignment/output rendering in terminal sessions.

### Documentation
- Environment variable and authentication docs updated to use `COGSOL_API_KEY` and optional Azure AD B2C credentials.
- Removed outdated "no external dependencies" statements from README.
- Added nested-topic ingestion examples and corrected ingest file paths to use topic-aligned `data/<topic-path>/` locations in docs.
- Clarified in README topic examples that `documentation` is only a sample topic name and not required.
- Retrieval-tool examples now instantiate retrieval definitions (e.g., `ProductDocsRetrieval()`) to avoid runtime confusion from class references.
- Setup guides now explicitly document creating and activating a local `.venv` before installing dependencies.
- Installation instructions now make the clone directory explicit in setup examples.

---

## [0.2.0] - 2026-01-26

### Added

#### Content API Integration (NEW!)
- **`data/` application** for managing document collections via Content API
  - Topics (nodes), metadata configs, formatters, retrievals
  - Hierarchical topic organization with nested folders
- **BaseTopic** class for defining document containers
- **BaseMetadataConfig** class for custom metadata fields
- **BaseReferenceFormatter** class for block reference formatting
- **BaseIngestionConfig** class for document processing settings
- **BaseRetrieval** class for semantic search configuration
- **BaseRetrieval.run** helper for executing retrieval queries
- **BaseRetrievalTool** class for connecting agents to Content API retrievals

#### New CLI Commands
- `starttopic` - Create new topic folders under `data/`
  - Support for nested topics with `--path` option
- `ingest` - Upload documents to topics
  - Support for PDFs, DOCX, TXT, MD, HTML, and more
  - Ingestion configuration presets
  - Dry-run mode for previewing uploads
  - Optional filename pattern filtering for directory ingestion
- `topics` - List topics from API or local definitions
  - `--local` flag for local definitions
  - `--sync-status` flag for comparison

#### Enhanced Migration System
- New operations: `CreateTopic`, `CreateMetadataConfig`, `CreateReferenceFormatter`, `CreateIngestionConfig`, `CreateRetrieval`, `CreateRetrievalTool`
- Support for `data` app migrations alongside `agents` app
- Running `makemigrations` and `migrate` without app name now processes both apps
- Incremental sync: only touched entities are synced to API

#### API Client Enhancements
- **Content API support** via separate `content_base_url` parameter
- `COGSOL_CONTENT_API_BASE` environment variable
- New methods for nodes, metadata configs, formatters, retrievals
- Multipart file upload support for document ingestion
- Bulk document upload capability

#### Project Structure Changes
- `startproject` now creates both `agents/` and `data/` folders
- New `agents/searches.py` for retrieval tool definitions
- New `data/formatters.py`, `data/ingestion.py`, `data/retrievals.py`
- Updated `.env.example` with `COGSOL_CONTENT_API_BASE`

### Changed
- `makemigrations` now accepts optional app argument (defaults to both)
- `migrate` now accepts optional app argument (defaults to both)
- `importagent` now imports retrieval tools and their related Content API entities
- Agent templates use commented examples (easier to customize)
- Tool templates use commented examples

### Fixed
- FAQ, fixed response, and lesson changes now tracked separately from agent
- Module reloading for reliable definition collection
- Prompt text loaded and stored in migration state
- Loader now detects definitions in submodules and surfaces import failures during collection
- Align chunking mode value with API ("ingestor")
- Chat command now shows assistant initial_message without duplicating it
- Tool code transformation now preserves helper methods for self-contained scripts

---

## [0.1.0] - 2026-01-08

### Added

#### Core Framework
- **BaseAgent** class for defining AI assistants
  - System prompt configuration
  - Tool integration
  - Generation config support
  - Meta class for display settings
- **BaseAgent.run/reset** helpers for direct chat API usage
- **BaseTool** class for extending agent capabilities
  - `@tool_params` decorator for parameter metadata
  - Support for `chat`, `data`, `secrets`, `log` runtime arguments
- **BaseFAQ** for frequently asked questions
- **BaseFixedResponse** for predefined responses
- **BaseLesson** for contextual lessons

#### CLI Commands
- `startproject` - Create new CogSol project skeleton
- `startagent` - Generate agent package with all files
- `makemigrations` - Detect and record changes
- `migrate` - Apply migrations and sync with API
- `importagent` - Import existing assistant from API
- `chat` - Interactive terminal chat interface

#### Migration System
- File-based migrations (no database required)
- Operations: `CreateAgent`, `CreateTool`, `AlterField`, `DeleteDefinition`
- State tracking via JSON files (`.applied.json`, `.state.json`)
- Automatic diff detection

#### API Client
- `CogSolClient` for REST API communication
- CRUD operations for assistants, tools, FAQs, fixed responses, lessons
- Chat session management
- Error handling with `CogSolAPIError`

#### Developer Experience
- Django-like project structure
- Code-first agent definitions
- Prompts loaded from Markdown files
- Minimal dependencies (stdlib only)
- Colored terminal output for chat

### Technical Details
- Python 3.9+ required
- No external dependencies
- Entry point: `cogsol-admin`
- Per-project management via `manage.py`

---

## Version History Summary

| Version | Date | Description |
|---------|------|-------------|
| Unreleased | - | - |
| 0.2.1 | 2026-03-11 | Auth updates, migration robustness fixes, and documentation improvements |
| 0.2.0 | 2026-01-26 | Content API integration, data app, retrieval tools |
| 0.1.0 | 2026-01-08 | Initial alpha release |

---

## Migration Notes

### From Earlier Versions

This is the initial release. No migration from earlier versions is required.

### Upgrading

When upgrading between versions:

1. Update the package:
   ```bash
   pip install --upgrade cogsol
   ```

2. Check for breaking changes in this changelog

3. Run migrations if schema changed:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

---

## Deprecation Policy

- Features marked as deprecated will be removed in the next major version
- Deprecation warnings will be issued at least one minor version before removal
- Breaking changes are only allowed in major version increments

---

## Reporting Issues

Please report issues on the project repository:
- Include CogSol version (`python -c "import cogsol; print(cogsol.__version__)"`)
- Include Python version (`python --version`)
- Include full error traceback
- Include steps to reproduce
