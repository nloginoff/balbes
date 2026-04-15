# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Сервис `services/webhooks_gateway`** — отдельный FastAPI от дашборда: `POST /webhook/telegram` (PTB webhook при `TELEGRAM_BOT_MODE=webhook`), `POST /webhook/max` (проверка `MAX_WEBHOOK_SECRET`), `POST /api/webhooks/notify` и `/webhook/notify` (перенесено с web-backend). Порт `WEBHOOKS_GATEWAY_PORT`. При `TELEGRAM_BOT_MODE=webhook` процесс `telegram_bot.py` polling не запускается ([`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py)). [`shared/max_inbound.py`](shared/max_inbound.py).
- **Документация notify**: [`docs/ru/WEBHOOK_NOTIFY.md`](docs/ru/WEBHOOK_NOTIFY.md) — запуск, nginx, настройка источника на RU-сервере; в [`TODO.md`](TODO.md) добавлен блок «Следующие этапы (multi-messenger / webhooks)».
- **Мониторинг: входящий webhook** — `POST /api/webhooks/notify` на web-backend (`Authorization: Bearer WEBHOOK_NOTIFY_API_KEY`), лимит запросов по IP (`NOTIFY_RATE_LIMIT_PER_MINUTE`), доставка в Telegram (HTML с экранированием) и опционально в MAX API при настроенных `MAX_BOT_TOKEN` + `NOTIFY_MAX_CHAT_ID`. Код: [`shared/notify/`](shared/notify/), [`services/web-backend/api/notify.py`](services/web-backend/api/notify.py). Скрипты запуска web-backend задают `PYTHONPATH` к корню репозитория.
- Скрипт **`scripts/export_memory_chats_to_data_for_agent.py`** (+ обёртка **`scripts/export_chats_for_agent.sh`**) — выгрузка всех чатов Memory из Redis в `data_for_agent/` у корня деплоя, папки `{memory_user_id}__{agent_id}__{chat_id}/`. Документация: [`docs/ru/DEPLOYMENT.md`](docs/ru/DEPLOYMENT.md) (раздел Redis).
- **Единая матрица slash-команд Telegram** — [`shared/telegram_app/telegram_command_matrix.py`](shared/telegram_app/telegram_command_matrix.py): порядок меню и регистрация обработчиков для оркестратора и бизнес-бота блогера по `TelegramFeatureFlags` и [`config/agents/*.yaml`](config/agents/balbes.yaml).
- **Memory namespace для Telegram-агентов** — [`shared/telegram_app/memory_namespace.py`](shared/telegram_app/memory_namespace.py): канонический ключ `{agent_id}_{telegram_user_id}`; для блогера запись в `blogger_<id>`, чтение с fallback на legacy `bbot_<id>`. Класс `TelegramMemoryNamespace` для подключения новых сервисов без дублирования формулы `user_id`.
- **Паритет команд блогера** с оркестратором (через те же флаги `telegram:`): status, tasks, agents, mode, remember, recall, heartbeat и др.; `/debug` для блогера с настройками чата в Memory.
- **Telegram UI по манифесту** — `TelegramFeatureFlags` в [`shared/agent_manifest.py`](shared/agent_manifest.py), блок `telegram:` в [`config/agents/balbes.yaml`](config/agents/balbes.yaml) / [`config/agents/blogger.yaml`](config/agents/blogger.yaml). Оркестраторский бот и бизнес-бот блогера регистрируют команды и хендлеры по флагам; общие [`shared/telegram_app/text.py`](shared/telegram_app/text.py) и [`shared/telegram_app/voice.py`](shared/telegram_app/voice.py) для текста и STT.
- **Единая архитектура делегирования** — `delegate_to_agent` вызывает только HTTP `POST /api/v1/agent/execute` (Coder и Blogger); общий контракт [`shared/agent_execute_contract.py`](shared/agent_execute_contract.py), опциональный заголовок `X-Balbes-Delegation-Key` при заданном `DELEGATION_SHARED_SECRET`. Манифест оркестратора [`config/agents/balbes.yaml`](config/agents/balbes.yaml): `delegate_targets` и пер-режимные allowlist инструментов через [`shared/agent_manifest.py`](shared/agent_manifest.py).
- **Blogger execute API** — [`services/blogger/api/execute.py`](services/blogger/api/execute.py) и метод `BloggerAgent.execute_delegate_task()` для ответов по делегированию.
- **Telegram UI оркестратора** — реализация перенесена в [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py); [`services/orchestrator/telegram_bot.py`](services/orchestrator/telegram_bot.py) остаётся точкой входа (`python -m services.orchestrator.telegram_bot`).
- Пример второго бота: [`scripts/run_second_orchestrator_bot.example.sh`](scripts/run_second_orchestrator_bot.example.sh).
- **Гибридная транскрипция голоса (Telegram)** — короткие сообщения: локально **openai-whisper** (`WHISPER_LOCAL_MODEL`, по умолчанию `medium`); длинные или без `duration`: облако — **OpenRouter** (multimodal `input_audio`) и/или **Yandex SpeechKit** (`WHISPER_REMOTE_BACKEND`: `openrouter` · `yandex` · `openrouter_then_yandex`). Новые модули `whisper_remote_stt.py`, расширен `shared/config` и `.env.example`; в режиме `/debug` в чат выводится выбранный STT-путь.

### Changed
- **Мониторинг notify** перенесён с web-backend на [`services/webhooks_gateway`](services/webhooks_gateway); дашборд больше не содержит `POST /api/webhooks/notify`.

### Fixed
- **Heartbeat** — при `source=heartbeat` пустой ответ LLM не подменяется на пользовательское сообщение «модель вернула пустой ответ» ([`services/orchestrator/agent.py`](services/orchestrator/agent.py)); для обычных задач текст подсказки без изменений. Доставка в Telegram: подавление `HEARTBEAT_OK` с внешними кавычками/обёртками ([`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py)).

### Changed
- Экспорт чатов Memory: каталоги `{memory_user_id}__{agent_id}__{chat_id}/` (видно `blogger_<tg>` vs числовой id); лог namespace блогера; загрузка env и подсказки Redis — [`docs/ru/DEPLOYMENT.md`](docs/ru/DEPLOYMENT.md).
- Документация: [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md) — секция Blogger (Memory `blogger_*`, матрица команд); [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md) / [`docs/en/CONFIGURATION.md`](docs/en/CONFIGURATION.md) — `memory_namespace`, `/debug` для блогера; [`docs/en/AGENTS_GUIDE.md`](docs/en/AGENTS_GUIDE.md) — namespaces.
- Документация (CONFIGURATION, GETTING_STARTED, README): описание голоса приведено к openai-whisper + облачный STT вместо устаревших упоминаний faster-whisper.

## [0.5.0] - 2026-04-04

### Added
- **`recall_from_memory(query, limit)`** — инструмент семантического поиска в долгосрочной памяти Qdrant; добавлен в `AVAILABLE_TOOLS` и реализован через `/api/v1/memory/search`.
- **`code_search(query, path_filter, limit)`** — семантический поиск по кодовой базе проекта (файловый уровень). Индексирует `.py`, `.ts`, `.yaml`, `.md` и другие расширения в Qdrant коллекцию `code_index`.
- **`index_codebase(path, force)`** — ручная переиндексация файлов проекта. Пропускает неизменённые файлы по `mtime`; `force=True` переиндексирует всё.
- **`manage_todo(action, section, item)`** — инструмент для чтения и обновления `TODO.md`: `read` (показать), `add` (добавить пункт), `done` (отметить выполненным).
- **`file_patch(path, old_string, new_string)`** — точечная замена строки в файле вместо полной перезаписи (добавлено в предыдущем сезоне, задокументировано здесь).
- **`_split_message(text, limit=4096)`** — автоматическое разбиение длинных сообщений Telegram на части по 4096 символов с учётом переносов строк. Применяется ко всем путям отправки (debug trace, результат задачи, bg monitor, heartbeat).
- **Rate limiting** — `ToolDispatcher._call_counts` и `_RATE_LIMITS` ограничивают число вызовов каждого инструмента за одну задачу (web_search: 10, fetch_url: 15, execute_command: 30, остальные: 20). `reset_call_counts()` вызывается в начале каждой задачи.
- **Учёт токенов** — `_call_llm()` теперь возвращает `usage_dict`; токены накапливаются через все раунды `_run_llm_with_tools`. По завершении задачи данные записываются fire-and-forget через `/api/v1/tokens/record`.
- **LLM саммаризация истории** — `_maybe_summarize_history()` при `memory.history_strategy: "summarize"` вызывает дешёвую LLM для краткого пересказа старых сообщений. Саммари кэшируется в Redis на 7 дней (ключ `balbes:history_summary:{user_id}:{chat_id}`).
- **`CodeIndexer`** — новый модуль `services/orchestrator/skills/code_indexer.py` с классом `CodeIndexer`; использует OpenRouter embeddings + Qdrant `AsyncQdrantClient`.
- **`_save_message_to_history()`** в `TelegramBot` — heartbeat-сообщения и ошибки теперь сохраняются в активный чат пользователя через memory service.

### Changed
- **`/stop`** теперь всегда отправляет cancel-сигнал оркестратору (`_cancel_orchestrator_task()`) до проверки наличия активных задач — останавливает как foreground, так и background задачи агентов.
- **LLM timeout** читается из `config/providers.yaml → providers.openrouter.timeout` (поднят с 60 до 120 секунд) и применяется явно в каждом вызове `_call_llm()`.
- **`_run_llm_with_tools()`** возвращает `tuple[str, str, dict]` — добавлен `total_usage` (накопленные токены).
- **`build_messages_for_llm()`** принимает опциональный `history_summary: str | None`; если задан, вставляется как системное сообщение перед обрезанными записями истории.
- **Прогресс в Telegram** (agent mode, debug off): показывает компактный индикатор `⚙️ Работаю… раунд N | tool1 · tool2`, редактируемый на месте.

### Fixed
- **`httpx.ReadTimeout`** при POST `/api/v1/tasks` теперь обрабатывается gracefully: показывается «⏳ Задача выполняется дольше 120 с» вместо падения с ошибкой.
- Все пути отправки сообщений в Telegram обёрнуты в `_split_message` — `BadRequest: Message is too long` больше не возникает.

## [0.4.0] - 2026-03-30

### Added
- **Yandex Search API v2** — migrated from legacy XML API (user+key in URL, IP whitelist required)
  to new Yandex Cloud REST API (`searchapi.api.cloud.yandex.net`). Authentication via
  `Authorization: Api-Key` header. Supports both sync (`/v2/web/search`) and async deferred
  (`/v2/web/searchAsync` + operations polling) modes. Response `rawData` (base64 XML) decoded
  and parsed by the existing XML parser.
- **`YANDEX_FOLDER_ID`** config field — required for Yandex Search API v2 (Yandex Cloud folder ID).
- **`file_read` / `file_write` tools** — Coder and Orchestrator agents can now read and write
  project files directly, with path-traversal protection and forbidden-file-type blocklist.
- **`web_search` provider parameter** — agents can explicitly request a search provider via
  the `provider` tool argument (e.g. `provider=yandex`); the used provider is shown in the
  debug trace as `[tavily] 5 result(s):`.
- **Heartbeat inter-round delay** — configurable `request_delay_seconds` (default 5s) between
  LLM rounds in heartbeat runs to avoid rate-limit errors on free OpenRouter models.
- **Coder agent full dev capabilities** — expanded `execute_command` whitelist in `agent` mode
  to include `grep`, `rg`, `cp`, `mv`, `mkdir`, `touch`, `diff`, `tree`, `which`, `bash`, `sh`,
  `chmod`; added `file_read`/`file_write` tools and updated `AGENTS.md` documentation.

### Changed
- `web_search.py`: `search()` now returns `tuple[list[SearchResult], str]` — results plus provider name used.
- `web_search.py`: DuckDuckGo provider removed; Tavily set as default provider.

### Fixed
- `tools.py`: `_do_web_search` — fixed `'SearchResult' object is not subscriptable` by switching from
  dict-style access to dataclass attribute access (`r.title`, `r.url`, `r.snippet`).

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
