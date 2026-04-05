# Configuration Reference

---

## Environment Variables (`.env.prod`)

### Required

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter API key (`sk-or-v1-...`) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from @BotFather |
| `TELEGRAM_USER_ID` | Allowed Telegram user IDs, comma-separated |
| `WEB_AUTH_TOKEN` | Internal service auth token (any random string) |
| `JWT_SECRET` | JWT signing secret (any random string) |
| `POSTGRES_PASSWORD` | PostgreSQL password |

### Optional — Search

| Variable | Description |
|----------|-------------|
| `TAVILY_API_KEY` | Tavily search API key (`tvly-...`) |
| `YANDEX_SEARCH_KEY` | Yandex Cloud API key (`AQVN...`) for Yandex Search API v2 |
| `YANDEX_FOLDER_ID` | Yandex Cloud folder ID (`b1g...`) — required with the above |
| `BRAVE_SEARCH_KEY` | Brave Search API key |

### Optional — Voice (Telegram)

Voice uses **openai-whisper** locally for short messages and **cloud STT** (OpenRouter multimodal audio and/or Yandex SpeechKit) for longer audio. Full list: `.env.example`.

| Variable | Description | Default |
|----------|-------------|---------|
| `WHISPER_MODEL` | Legacy YAML/docs; local path uses `WHISPER_LOCAL_MODEL` | `large-v3` |
| `WHISPER_LOCAL_MODEL` | openai-whisper model when duration ≤ threshold | `medium` |
| `WHISPER_LOCAL_MAX_DURATION_SECONDS` | If Telegram `voice.duration` ≤ this (seconds), use local Whisper; otherwise cloud | `30` |
| `WHISPER_REMOTE_BACKEND` | `openrouter` · `yandex` · `openrouter_then_yandex` | `openrouter_then_yandex` |
| `WHISPER_OPENROUTER_STT_MODEL` | OpenRouter model with audio input ([models with audio](https://openrouter.ai/models?input_modalities=audio)) | `google/gemini-2.0-flash-001` |
| `WHISPER_OPENROUTER_STT_TIMEOUT_SECONDS` | HTTP timeout for cloud STT via OpenRouter | `300` |
| `WHISPER_YANDEX_STT_TIMEOUT_SECONDS` | HTTP timeout for Yandex SpeechKit | `300` |
| `YANDEX_SPEECH_API_KEY` | Optional SpeechKit key; if unset, `YANDEX_SEARCH_KEY` is used | — |
| `YANDEX_SPEECH_FOLDER_ID` | Optional; if unset, `YANDEX_FOLDER_ID` is used | — |
| `WHISPER_DEVICE` | `cpu` or `cuda` | `cpu` |
| `WHISPER_LANGUAGE` | e.g. `ru`, or empty for auto-detect | `ru` |
| `WHISPER_BEAM_SIZE` / `WHISPER_BEST_OF` / `WHISPER_PATIENCE` | openai-whisper decode quality (local path only) | `10` / `5` / `2.0` |
| `WHISPER_CORRECTION_FALLBACK_MODEL` | Paid OpenRouter model for post-STT text correction (not `:free`) | MiniMax M2.5 |

Requires `ffmpeg` and `pip install openai-whisper`. Optional preload: `ENV=prod python scripts/prefetch_whisper.py`.

### Optional — Infrastructure

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_PASSWORD` | Redis password | *(empty)* |
| `LOG_LEVEL` | Logging level: `DEBUG` / `INFO` / `WARNING` | `INFO` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `RATE_LIMIT_PER_MINUTE` | Requests per minute per user | `60` |

---

## `config/agents/*.yaml` (agent manifests)

Git-safe YAML per logical agent: optional per-mode tool allowlists and **`delegate_targets`** (HTTP base URLs for `delegate_to_agent`).

Example [`config/agents/balbes.yaml`](../../config/agents/balbes.yaml):

```yaml
id: balbes
delegate_targets:
  coder: http://127.0.0.1:8001
  blogger: http://127.0.0.1:8105
```

Inter-service trust: when `DELEGATION_SHARED_SECRET` is set, callers must send header `X-Balbes-Delegation-Key` with that value. If unset, execute endpoints do not require the header (local dev).

Loader: [`shared/agent_manifest.py`](../../shared/agent_manifest.py).

Optional **`telegram:`** block toggles per-agent Telegram UI (voice, command menu, model switch, multi-chat, memory commands, **`debug_command`** (`/debug`: LLM and voice-stage traces for the current chat, stored in Memory) — same flag for the orchestrator bot and the blogger business bot (blogger uses Memory user id prefix `bbot_<telegram_id>`); plus blogger-specific flags such as `posts_commands`, business group capture, etc. See `TelegramFeatureFlags` in the same module. Example: [`config/agents/blogger.yaml`](../../config/agents/blogger.yaml). Slash command registration and menu order for orchestrator vs blogger are defined in [`shared/telegram_app/telegram_command_matrix.py`](../../shared/telegram_app/telegram_command_matrix.py); YAML only selects which flags are on and which handlers exist on the bot class.

---

## `config/providers.yaml`

This is the main configuration file for models, agents, and skills.

### Model Tiers

```yaml
models:
  free:
    - id: stepfun/step-3.5-flash
      name: StepFun Step 3.5 Flash
    - id: minimax/minimax-m2.5:free
      name: MiniMax M2.5 Free
  cheap:
    - id: meta-llama/llama-3.3-70b-instruct
    - id: minimax/minimax-m2.5
  medium:
    - id: moonshot/kimi-k2.5
    - id: google/gemini-flash-1.5
  premium:
    - id: anthropic/claude-sonnet-4-6
    - id: openai/gpt-4o
```

Users switch tiers via `/model` in Telegram.

### Agent Settings

Each agent block controls its behavior:

```yaml
agents:
  orchestrator:
    default_model: minimax/minimax-m2.5:free   # default LLM for this agent
    fallback_enabled: false                     # show error to user on failure
    fallback_chain:
      - minimax/minimax-m2.5
      - meta-llama/llama-3.3-70b-instruct
    token_limits:
      daily: 500000
      hourly: 100000

  coder:
    default_model: minimax/minimax-m2.5:free
    server_commands_ask:                        # allowed commands in /mode ask
      allowed_commands:
        - ls
        - cat
        - grep
        - git status
    server_commands:                            # allowed commands in /mode agent
      allowed_commands:
        - git
        - python
        - grep
        - rg
        - cp
        - mv
        - mkdir
        - bash
        - sh
        - chmod
```

### Heartbeat

```yaml
heartbeat:
  enabled: true
  interval_minutes: 5
  model: minimax/minimax-m2.5:free
  request_delay_seconds: 5     # pause between LLM rounds (prevents rate limits)
  max_tokens: 1000
```

### Web Search

```yaml
skills:
  web_search:
    default_provider: tavily
    providers:
      tavily:
        enabled: true
      yandex:
        enabled: true
        use_deferred: false    # true = async deferred mode
      brave:
        enabled: false
```

---

## Per-Agent Config (`data/agents/{agent}/config.yaml`)

Overrides `providers.yaml` with the highest priority:

```yaml
# data/agents/orchestrator/config.yaml
default_model: moonshot/kimi-k2.5    # use this model regardless of global config
max_tokens: 4000
temperature: 0.7
```

---

## Agent Workspace Files

| File | Purpose |
|------|---------|
| `SOUL.md` | Personality, tone, communication style |
| `AGENTS.md` | Behavioral instructions (sent to LLM as system context) |
| `MEMORY.md` | Important persistent facts — always included in context |
| `HEARTBEAT.md` | Topics for proactive messages |
| `TOOLS.md` | Tool documentation for the agent |
| `IDENTITY.md` | Agent identity details |

Edit any of these files to change agent behavior — changes take effect on the next message.

---

## Execution Modes

Switch modes with `/mode` in Telegram:

| Mode | Description | Command whitelist |
|------|-------------|-------------------|
| `ask` | Safe read-only | `ls`, `cat`, `grep`, `git status`, `diff`, `tree` |
| `agent` | Full dev powers | + `git`, `python`, `cp`, `mv`, `mkdir`, `bash`, etc. |

---

## Tool Reference

| Tool | Modes | Description |
|------|-------|-------------|
| `web_search` | both | Web search (Tavily / Yandex / Brave). Optional `provider` param to force a specific one |
| `fetch_url` | both | Fetch a URL and return text content |
| `execute_command` | both | Run a whitelisted shell command |
| `file_read` | both | Read a file from the project (path-safe) |
| `file_write` | agent | Write/overwrite a file in the project |
| `workspace_read` | both | Read a file from the agent's own workspace |
| `workspace_write` | both | Write a file to the agent workspace (auto-commits to git) |
| `save_to_memory` | both | Save text to Qdrant semantic memory |
| `recall_from_memory` | both | Search Qdrant semantic memory |
| `read_agent_logs` | both | Read JSONL activity logs for a time period |
| `delegate_to_agent` | agent | Delegate a task to another agent (foreground or background) |
| `get_agent_result` | agent | Retrieve result of a completed background task |
| `cancel_agent_task` | agent | Cancel a running background task |
| `list_agent_tasks` | both | Show task registry (running + recent) |
| `rename_chat` | both | Rename the current Telegram chat |

---

*[Русская версия](../ru/CONFIGURATION.md)*
