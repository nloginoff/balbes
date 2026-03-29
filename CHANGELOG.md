# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-03-29

### Added
- **XML tool-call parsing** — supports models (MiniMax, etc.) that embed tool calls in XML
  format inside message content instead of using the standard JSON `tool_calls` field.
  Handles both `<prefix:tool_call>` and `<prefix:toolcall>` variants (with or without underscore).
- **Tool-name normalization** (`_normalize_tool_name`) — maps de-underscored tool names that
  some LLMs produce (e.g. `readagentlogs` → `read_agent_logs`, `delegatetoagent` → `delegate_to_agent`)
  for both XML-parsed and standard JSON tool calls.
- **Background task monitoring** (`_bg_monitor_loop`) — Telegram bot polls the orchestrator
  every 5 seconds for background task progress; debug events are streamed to the chat in real
  time and the final result is sent automatically upon task completion.
- **`_ensure_bg_monitors`** — catch-all that starts monitors for any running background tasks
  not yet being tracked (survives bot restarts and missed `background_tasks_started` signals).
- **`/tasks` command** — displays the global task registry (running + recent) with agent,
  status, timing, and automatically starts monitors for any running background tasks.
- **Task registry** (`_task_registry`) — in-memory registry (capped at 50 entries) tracking
  all foreground and background tasks with status, timings, and agent metadata.
- **Background debug buffer** (`_bg_debug_buffer`) — live debug-event queue per background task,
  drained by `poll_bg_task` and streamed to the Telegram chat.
- **`list_agent_tasks` tool** — orchestrator tool allowing the agent to query and display
  the task registry in chat.
- **`delegate_to_agent` tool** — orchestrator can hand off tasks to specialist agents (e.g.
  Coder) in foreground or background mode; result is returned or auto-delivered.
- **`get_agent_result` / `cancel_agent_task` tools** — retrieve or cancel background tasks.
- **Agent delegation with isolated context** — sub-agents receive their own `ToolDispatcher`
  instance with a separate whitelist, preventing privilege escalation.
- **Per-agent `config.yaml`** — each agent workspace may contain `config.yaml` that overrides
  `default_model`, `token_limits`, and `server_commands` with highest priority.
- **`/debug` mode** — per-chat toggle; when on, every LLM round and tool call is sent to the
  chat as an HTML-formatted trace including agent name, model, elapsed time.
- **`/mode` command** — per-chat toggle between `ask` (safe read-only whitelist) and `agent`
  (full development whitelist including git, pytest, pip, docker).
- **`/stop` command** — cancels the active task for the current user and terminates any running
  background monitors.
- **Heartbeat proactive messaging** — background scheduler sends proactive messages based on
  `HEARTBEAT.md` and `MEMORY.md`; runs on free LLM models with a configurable fallback chain
  (free → cheapest paid → error); respects `active_hours_start/end`.
- **Voice message transcription** — `faster-whisper` + LLM grammar correction; transcribed
  text is shown before the agent response.
- **Web search skill** — supports DuckDuckGo (default), Brave, and Tavily with provider
  switching via `providers.yaml`.
- **URL fetch skill** — `httpx` + `html2text`; max 5000 chars, configurable timeout.
- **Activity logging** — per-agent JSONL logs (date-based) tracking every tool call with
  timestamps, duration, success flag, and source (`user` / `heartbeat`). Readable via
  `read_agent_logs` tool.
- **Agent workspace files** — each agent has a workspace directory with `SOUL.md`, `AGENTS.md`,
  `MEMORY.md`, `HEARTBEAT.md`, `TOOLS.md`, `IDENTITY.md`, `config.yaml`. The agent can read
  and write these files, enabling self-modification of instructions and persistent memory.
- **Private memory versioning** — `data/agents/` is a separate private GitHub repository;
  every workspace file write triggers an auto-commit + debounced auto-push (30-second window).
- **Multi-chat session management** — each Telegram chat has its own Redis-backed history,
  name, chosen model, and agent; `/chats` lists all sessions with IDs and switches between them.
- **Access control** — only whitelisted `TELEGRAM_USER_ID` values can interact with the bot;
  unauthorized users receive a rejection message.
- **Model tiers** (`free` / `cheap` / `medium` / `premium`) — structured in `providers.yaml`;
  `free` is the default; `medium` and `premium` require explicit user selection.
- **Per-agent model configuration** — each agent in `providers.yaml` and `config.yaml` may set
  `default_model`, `fallback_enabled`, `fallback_chain`, and `token_limits`.
- **Detailed error messages** — on LLM failure the exact HTTP status, provider error body, and
  exception type are relayed to the user; `fallback_enabled: false` (default) means failures are
  shown immediately, not silently retried.
- **Host timezone propagation** — Docker containers mount `/etc/localtime` and `/etc/timezone`
  from the host; Python services use `datetime.now().astimezone()` — no hard-coded timezone.
- **`LLMUnavailableError`** — dedicated exception for LLM failures; `execute_task` catches it
  and returns `status: "failed"` so heartbeat does not forward error text as a normal message.
- **`uvicorn --workers 1`** — orchestrator is forced to single worker to prevent in-memory
  task registry and debug buffer fragmentation across processes.

### Changed
- `_run_llm_with_tools` now accepts an explicit `dispatcher` parameter for isolated sub-agent
  execution; always attaches debug collector to the dispatcher when `debug_events` is provided.
- `execute_task` snapshots `_background_tasks` before/after the LLM loop to detect newly
  started background delegations and include them in the result.
- `poll_bg_task` no longer pops the result — monitor reads it without consuming; `get_agent_result`
  remains responsible for consuming so "Нет результатов" no longer appears after auto-delivery.
- Background task monitor suppresses the internal fallback text ("Не смог обработать запрос…")
  from being shown as a task result; adds `(результат в логах)` note instead.
- Debug trace output switched from MarkdownV2 to HTML (`parse_mode="HTML"`) for robust handling
  of all special characters in LLM responses and tool outputs.
- Agent debug events now include the agent name tag (`[orchestrator]`, `[coder]`) for clarity
  during delegation.
- Coder agent uses its own configured `default_model` (Kimi K2.5) when delegated — does not
  inherit the Orchestrator's active chat model.
- Git commands for Coder agent whitelist use `git -C {path}` pattern instead of `cd && git`.
- `AGENTS.md` and `TOOLS.md` workspace files separated: operational instructions in `AGENTS.md`,
  tool documentation in `TOOLS.md`.

### Fixed
- XML regex now uses backreference (`<\1>`) matching any `<prefix:tag>` wrapper — fixes
  `<minimax:toolcall>` variant (without underscore) being silently ignored.
- Tool-name de-underscoring (`readagentlogs`, `delegatetoagent`, etc.) no longer causes
  "unknown tool" errors with MiniMax models.
- Heartbeat no longer sends "Не смог обработать запрос" or `LLMUnavailableError` text to the
  user chat on model failures.
- `can't find end of the entity` Telegram `BadRequest` errors eliminated by switching to HTML
  parse mode for dynamic content.
- `/tasks` command no longer shows "Нет задач в реестре" when a background task is running
  (fixed by `--workers 1` and `_ensure_bg_monitors`).

## [0.2.0] - 2026-03-28

### Added
- Telegram bot integration with `python-telegram-bot`: polling, per-user concurrency lock,
  global middleware for access control, `ApplicationHandlerStop` for unauthorized users.
- Multi-chat session management in Redis: per-chat history (7-day TTL with lazy cleanup),
  chat name, model, agent assignment. Commands: `/chats`, `/newchat`, `/rename`.
- Agent switching via `/agents` inline keyboard; each chat remembers its assigned agent.
- Model selection per chat via `/model` inline keyboard with tier-based display.
- Orchestrator `OrchestratorAgent` class: `execute_task`, `_run_llm_with_tools`, tool dispatch
  loop, workspace file management, multi-provider LLM calls.
- `AgentWorkspace` — loads and caches MD workspace files; auto-commit+push to private Git repo
  on every write via `WorkspaceVersioning`.
- `ToolDispatcher` — registers and dispatches tools: `web_search`, `fetch_url`,
  `execute_command`, `workspace_read`, `workspace_write`, `rename_chat`, `save_to_memory`,
  `read_agent_logs`.
- `providers.yaml` — central config for providers, models, tiers, per-agent settings,
  heartbeat, whisper, skills, and memory strategy.
- `AgentLogger` — per-agent JSONL activity log files in `data/logs/agent_activity/`.
- Long-term memory in Qdrant: `save_to_memory` / `recall_from_memory` tools (explicit only).
- Voice transcription: `faster-whisper` + ffmpeg + LLM correction pass.
- `setup_memory_repo.sh` — initializes the private memory Git repo (handles empty remote).
- FastAPI orchestrator API: `POST /api/v1/tasks`, `GET /api/v1/tasks`, health endpoint.
- Health-check script updated to detect `telegram_bot.py` process by name.

### Changed
- `qdrant-client` version relaxed to `>=1.7.0` for Python 3.13 compatibility.
- `python-telegram-bot` concurrent updates set via `Application.builder().concurrent_updates(False)`.
- `data/agents/` excluded from main `.gitignore` and tracked in the separate memory repo.

### Fixed
- `ModuleNotFoundError: No module named 'apt_pkg'` — use `.venv/bin/pip` instead of system pip.
- `fatal: ambiguous argument 'HEAD'` in `setup_memory_repo.sh` for empty remote repos.
- `/chats` MarkdownV2 `BadRequest` — all dynamic text escaped via `_escape_md2()`.

## [0.1.0-mvp] - 2026-03-27

### Added
- Multi-environment runtime model (`dev`/`test`/`prod`) with isolated ports and data paths on one server.
- Dedicated run scripts for each environment and cross-environment status checks.
- Release readiness documentation:
  - `RELEASE_CHECKLIST.md`
  - updated runbook guidance in `DEPLOYMENT.md`, `README.md`, `PROJECT_GUIDE.md`, `TODO.md`

### Changed
- Production app ports moved to `18100..18200` and infra ports to isolated `15xxx/16xxx` ranges.
- Health checks updated to support explicit `dev|test|prod` modes and auto-detection.
- Stop/start scripts hardened to use explicit compose files and path-safe project root resolution.
- Python runtime baseline aligned to Python 3.13 in deployment docs and operational flow.

### Fixed
- Skills workflow integration test made deterministic against semantic-search indexing lag.
- Production startup/stop scripts fixed for user-level logging and PID tracking.
- Qdrant local production client mode fixed for HTTP operation (`https=False`) to avoid SSL mismatch.
- Python compatibility issues around `datetime.UTC` usage corrected.

### Security
- Production environment requirements reinforced in docs (`WEB_AUTH_TOKEN`, JWT secrets, non-default secrets).

## [0.1.0] - 2026-03-26

### Added
- Initial project structure
- Documentation:
  - Technical specification
  - MVP scope definition
  - Project structure
  - Data models and DB schemas
  - API specification
  - Agents guide
  - Development plan
  - Deployment guide
  - Architecture decisions
  - Configuration guide
  - Examples and use cases
- Environment configuration (.env.example)
- README with project overview

### Notes
- This is the planning phase
- Development starts after this
- MVP target: 15-20 days

---

## Release Notes Template (for future releases)

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features
- New agents
- New skills

### Changed
- Modified existing functionality
- Updated dependencies
- Configuration changes

### Fixed
- Bug fixes
- Performance improvements

### Deprecated
- Features marked for removal

### Removed
- Removed features

### Security
- Security updates and fixes
```

---

## Version Numbering

**Format**: MAJOR.MINOR.PATCH

- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

**Examples**:
- `0.1.0` - Initial MVP
- `0.2.0` - Added Blogger agent
- `0.2.1` - Fixed token tracking bug
- `1.0.0` - First stable release
