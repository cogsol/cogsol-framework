# Changelog

All notable changes to the CogSol Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `BaseAgent.attachments`: agents can now declare which file types the chat accepts and which ones reach the model, through the `attachment` specs (`Pdf`, `Image`, `Word`, `Excel`, `Text`, `Markdown`, `Latex`, `Binary` and `Custom`). Each spec takes `accepted` and `send_to_model`, and `Pdf` takes `mode="image"|"text"`. Mapped to the Cognitive `attachment_config` field. Declaring `attachments = []` accepts no attachments.
- `BaseAgent.reasoning_effort` and `BaseAgent.reasoning_summary` to configure reasoning beyond the on/off flag.
- `BaseAgent.websearch_mode`, `BaseAgent.websearch_domains` and `BaseAgent.websearch_location` to configure web search beyond the on/off flag.
- `BaseAgent.asynchronous`, mapped to the Cognitive `async_available` field.
- `BaseAgent.append_to_user_message`, mapped to the Cognitive `add_to_user_message` field.
- `optimizations.SkipAllContent()` and `optimizations.NoOptimization()`, completing the token optimization strategies the Generator recognizes.
- `importagent` now imports every configuration above, including reconstructing `attachments` from the remote `attachment_config`, and declares `streaming`/`realtime` in the generated agent instead of only in the migration state.
- Choice, domain and attachment values are validated locally during `migrate`, with the list of valid values in the error message. Cognitive does not run model validation on these fields, so an invalid configuration used to be persisted silently and never work.

### Changed
- Optional agent configuration is only sent to Cognitive when the agent class declares it. Anything left to the portal now survives a `migrate` instead of being reset to a framework default. The attributes already sent in previous versions keep being sent unconditionally.
- `BaseAgent.user_interactions_window`, `BaseAgent.token_optimization` and `BaseAgent.self_improvement_mode` are now applied. All three were documented but never reached Cognitive, so agents declaring them will see their behaviour change on the next `migrate`: history sent to the model is capped by `user_interactions_window`, past retrieval results are trimmed per `token_optimization`, and `self_improvement_mode` enables matrix mode (`matrix_mode_available`).

### Fixed
- `BaseAgent.reasoning` and `BaseAgent.websearch` had no effect: `migrate` sent them as `reasoning_available` and `websearch_available`, fields that do not exist in Cognitive, so they were silently discarded. They are now sent as `reasoning_enabled` and `web_search_enabled`. **Agents that already declare these flags will actually enable reasoning or web search on the next `migrate`, which changes the cost per message.** `importagent` read the same non-existent fields and never imported them.
- `migrate` no longer wipes `add_to_user_message` and `strategy_to_optimize_tokens`, which were hardcoded to `null` on every run and overwrote whatever was configured in the portal.
- `matrix_mode_available` is no longer derived from `realtime`. They are separate Cognitive features: matrix mode requires FAQ support and is rejected in production, so a `realtime` agent without FAQs failed to migrate. It is now driven by `self_improvement_mode`, and agents relying on the old behaviour stop having matrix mode enabled on the next `migrate`.
- `importagent` no longer writes migration state for attributes the generated agent does not declare, which made the first `makemigrations` after an import report changes that were not there.

---

## [0.3.0] - 2026-07-15

### Added
- MCP server and tool support through `BaseMCPServer`, `BaseMCPTool`, the `addmcptools` command, API client methods, and migration operations. MCP servers support no authentication, header authentication, and OAuth 2.1.
- `cogsol-admin credentials-setup` and `cogsol-admin logout` commands for configuring and clearing tenant credentials stored in the platform-appropriate user configuration directory.
- `cogsol-admin startproject` can now scaffold projects from CogSol Cookbook templates and examples via `--from-template` / `--from-example`, with `--list-templates` / `--list-examples` to browse available entries. Supports overwriting conflicts (`--force`), pinning a branch, tag, or commit (`--ref`), custom cookbook repositories (`--cookbook-repo`), and private repositories (`--github-token`).
- `BaseRetrievalTool.filters`: searches can now declare metadata filters (by metadata config name, `topic/name`, or `BaseMetadataConfig` subclass). `migrate` resolves them to Cognitive filter definitions (`metadata_config_id`, type, possible values, format) and assigns them to the search.
- `editmcptools` and `deletemcptools` commands for editing/removing MCP servers and their tools (updates classes, `.env` vars, and Cognitive without duplications).
- `importagent` now also imports MCP servers/tools, topic metadata configs (`data/<topic>/metadata.py`), and search filters (collapsing date filter triplets into a single metadata reference).
- `BaseAgent.Meta.alias`: assistant alias shown in the chat UI (Cognitive `info` field). `startagent` template now documents all personalization Meta fields.
- `BaseAgent.reasoning` and `BaseAgent.websearch` flags, mapped to the Cognitive `reasoning_available` and `websearch_available` fields.

### Changed
- Authenticated CLI commands now load credentials from the project `.env` and then the user-level credential store, and fail fast with setup guidance when required credentials are missing.
- Default Cognitive and Content API URLs now use the authenticated CogSol endpoints instead of falling back to legacy unauthenticated endpoints.
- `credentials-setup` now validates connectivity with both Cognitive and Content APIs after saving credentials and provides hints for common authentication and server errors.
- MCP server updates now use partial `PATCH` requests so omitted fields, including existing secrets, remain unchanged.

### Fixed
- `startproject --from-template/--from-example` no longer fails for entries pushed to the cookbook repo after the tarball was cached: on "not found" the cache is refreshed once and the fetch retried (branch/tag refs only — SHA refs are immutable). The error message now includes `repo@ref` and lists the available entries of that kind.
- `makemigrations`/`migrate` no longer fail when tool code imports packages that only exist in the Cognitive runtime (e.g. `django`): missing third-party imports are stubbed during definition collection with a warning. Project-local import errors still fail loudly.
- Agent personalization colors are now written with the camelCase keys the chat frontend actually reads (`nameColor`, `primaryColor`, `secondaryColor`, `borderColor`) instead of unused snake_case keys, and `info` is populated from `Meta.alias` instead of always being `None`.
- `importagent` now imports the assistant's personalization (alias/`info` and colors) into the generated `Meta`, accepting both camelCase and legacy snake_case color keys.
- `migrate` no longer wipes filters assigned to a search in the portal: the retrieval tool payload now always includes the `filters` resolved from the class definition.
- `importagent` handles MCP `server` references returned as strings or nested dicts, and no longer skips generating classes when the template file contains commented-out examples with the same class name.
- OAuth client-credentials authentication now builds the scope from the environment-specific application ID instead of the client ID.
- `importagent` now preserves the assistant's `initial_message`, `forced_termination_message`, and `no_information_message` fields.
- Generated `ProductDocsRetrieval` examples and project scaffolds now reference the `ProductDocsTopic` class instead of using an invalid string topic value.
- Tool script generation no longer drops the first import or statement from `run()` methods decorated with `@tool_params`.
- Re-running `addmcptools` without entering new header values no longer overwrites secrets stored in Azure Key Vault with empty values.
- MCP tool IDs are now resolved reliably from the different backend response shapes and assigned to assistants during migration.
- Retrieval tools now resolve migrated retrieval IDs when their `retrieval` field contains a `BaseRetrieval` instance as well as when it contains a class.
- Missing-credential errors in `chat`, `importagent`, `migrate`, and `CogSolClient` now identify the required settings and direct users to the onboarding flow.

### Documentation
- Clarified the distinction between script tools and retrieval tools, the end-to-end retrieval workflow, and the requirement to explicitly register both kinds of tools in an agent's `tools` list.
- Added documentation for MCP server lifecycle commands, MCP API client operations, and a dedicated troubleshooting guide.
- Updated credential onboarding, project-level credential overrides, virtual-environment setup, and PyPI installation instructions.
- Added nested-topic ingestion examples and corrected ingest file paths to use topic-aligned `data/<topic-path>/` locations.

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
| 0.3.0 | 2026-07-15 | MCP integration, persistent CLI credentials, Cookbook scaffolding, retrieval filters, and import/migration improvements |
| 0.2.1 | 2026-03-11 | Auth updates, migration robustness fixes, and documentation improvements |
| 0.2.0 | 2026-01-26 | Content API integration, data app, retrieval tools |
| 0.1.0 | 2026-01-08 | Initial alpha release |

---

## Migration Notes

### Upgrading from 0.2.1

1. Update the package:
   ```bash
   pip install --upgrade cogsol
   ```

2. Configure tenant credentials in the user-level credential store:
   ```bash
   cogsol-admin credentials-setup
   ```
   Project `.env` values override stored credentials. In `COGSOL_ENV=local`, only `COGSOL_API_KEY` is required; other environments require `COGSOL_API_KEY`, `COGSOL_AUTH_CLIENT_ID`, and `COGSOL_AUTH_SECRET`.

3. Review and apply migrations so new MCP, retrieval-filter, metadata, and agent fields are synchronized:
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
