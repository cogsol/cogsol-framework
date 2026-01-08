# Changelog

All notable changes to the CogSol Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-01-08

### Added

#### Core Framework
- **BaseAgent** class for defining AI assistants
  - System prompt configuration
  - Tool integration
  - Generation config support
  - Meta class for display settings
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
