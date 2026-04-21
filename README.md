# Balbes — Your AI Team, Living in Telegram

> *What if your personal AI assistant could write code, search the web, remember everything, and proactively message you — all from a simple Telegram chat?*

**Balbes** is a self-hosted multi-agent AI system built around a Telegram bot. Inspired by the philosophy of [OpenClaw](https://github.com/openclaw), it brings a team of specialized AI agents to your fingertips — no browser, no subscriptions, no walled gardens.

The **Coder agent** acts as your personal [Cursor AI](https://cursor.sh) — it reads your codebase, writes code, runs commands, commits changes, and iterates — all via Telegram messages. You describe what you want, it builds it.

**Version**: 0.5.0 | **Status**: 🟢 Production Running | **License**: MIT

---

## Why Balbes?

Most AI assistants are stateless chat windows. Balbes is different:

- **It remembers** — semantic long-term memory in Qdrant + 7-day chat history in Redis
- **It acts** — not just answers, but executes commands, reads/writes files, searches the web
- **It delegates** — the Orchestrator agent hands off coding tasks to the Coder agent in the background
- **It reaches out** — the Heartbeat system makes the agent proactively message you with updates, ideas, or reminders
- **It blogs** — the Blogger agent reads your chats, monitors your business groups, and publishes posts to Telegram channels
- **It runs on your server** — your data, your models, your rules

---

## What Makes It Special

### 🤖 Coder Agent — Cursor AI in Your Telegram

Forget switching between apps. The Coder agent is a full coding assistant that can:

- Read any file in your project (`file_read`)
- Write and modify files (`file_write`)
- Run `git`, `grep`, `rg`, `diff`, `tree`, shell scripts
- Commit changes to git automatically
- Work in the background while you do other things — you get notified when it's done

Give it a task like *"refactor the web_search skill to support a new provider"* and go have coffee.

### 🧠 Long-Term Memory

The agent remembers what you taught it. Semantic search over your notes, decisions, and context — powered by Qdrant. Use `/remember` to save anything, `/recall` to retrieve it.

### 🔍 Web Search

Multi-provider search with automatic fallback:
- **Tavily** — AI-optimized search results
- **Yandex Search API v2** — Russian-language search via Yandex Cloud
- **Brave** — privacy-first alternative

Switch providers on the fly: just say *"search via yandex: ..."*

### 🎙️ Voice Messages

Send a voice note, get a text response. Hybrid STT: local **openai-whisper** for short audio, OpenRouter and/or Yandex SpeechKit for longer; optional LLM post-correction via OpenRouter.

### 💓 Heartbeat

The agent doesn't wait to be asked. Based on your `HEARTBEAT.md` file, it proactively sends you messages — project updates, reminders, interesting finds. Runs on a free model to save costs.

### 📰 Blogger Agent — Your AI Chronicler

A standalone microservice that turns your work into public content:

- **Reads** your Telegram chat history and Cursor AI markdown exports
- **Generates** blog posts from its own perspective ("AI-blogger Balbes") in Russian and English
- **Writes** personal posts from your perspective (plans, results, business updates) for your private blog
- **Monitors** business Telegram groups — silently collects messages, anonymizes them, generates daily business summaries
- **Evening check-in** at 20:00 — asks what you accomplished, generates a personal blog post draft
- **Approval workflow** — inline ✅/✏️/❌ buttons in Telegram before any post goes live
- **Publishing queue** — spreads posts across the day (1–3 per day), respects daily quota
- **Security** — business bot only responds to your Telegram account; strangers are silently ignored

### 🔧 Full Control via Telegram

No Web UI needed. Everything — switching models, managing chats, reading logs, controlling agents — happens in one Telegram conversation.

> **Web UI status**: A web frontend is in active development, but honestly, the developer doesn't feel the need for it. Everything works beautifully through the Telegram bot, and that's the point. The web interface will ship eventually for those who want it.

---

## Feature Overview

| Feature | Description |
|---------|-------------|
| Multi-agent orchestration | Orchestrator delegates tasks to Coder in foreground or background |
| Per-chat model selection | Each chat can use a different LLM (free → premium tiers) |
| Background task monitoring | Live debug trace streamed to your Telegram as the agent works |
| Workspace versioning | Agent workspace files auto-committed to a private git repo |
| Mode switching | `/mode ask` (safe read-only) / `/mode agent` (full dev powers) |
| Voice transcription | openai-whisper (short) + OpenRouter / Yandex STT (long) + optional LLM correction |
| Token limits | Per-agent daily/hourly token budgets with automatic fallback |
| Multi-chat | Multiple named conversations, each with own history and settings |
| Blogger agent | AI-driven blog post generation from chats, Cursor exports, and voice check-ins |
| Business chat monitoring | Silent bot in employee Telegram groups — anonymizes messages, daily summaries |
| Post approval flow | Inline ✅/✏️/❌ buttons in Telegram, edit instructions via LLM revision |
| Publishing queue | Scheduled post release (1–3/day) across 3 channels (RU, EN, personal) |
| MAX Messenger (optional) | Same orchestrator and memory via [`POST /webhook/max`](docs/ru/MAX_WEBHOOK.md); LLM replies use **MAX Markdown** (`format: markdown`) with plain fallback |

---

### MAX Messenger (optional channel)

Balbes can talk to users on [**MAX Messenger**](https://max.ru) (Russian platform) in parallel with Telegram: a dedicated **webhooks gateway** receives HTTPS events, calls the orchestrator (`POST /api/v1/tasks`), and sends replies with `POST .../messages`. Outbound assistant text is formatted for the MAX Markdown flavor (bold, italics, underline `++`, links, code fences) — see the full **[MAX webhook & formatting guide (RU)](docs/ru/MAX_WEBHOOK.md)**. Slash commands, `/link` pairing with Telegram, and optional **mirroring** of agent replies to the linked account are documented there and in [`docs/ru/IDENTITY_AND_OPENROUTER_USER.md`](docs/ru/IDENTITY_AND_OPENROUTER_USER.md).

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Get started |
| `/help` | Show help |
| `/agents` | List agents / switch active agent |
| `/chats` | List chats / switch chat |
| `/newchat` | Create a new named conversation |
| `/rename` | Rename current chat |
| `/model` | Pick a model (free / cheap / medium / premium) |
| `/clear` | Clear chat history |
| `/remember` | Save something to long-term memory (Qdrant) |
| `/recall` | Search long-term memory |
| `/heartbeat` | Trigger a heartbeat check right now |
| `/debug` | Toggle live debug trace (every LLM call + tool call shown in chat) |
| `/mode` | Switch between `ask` and `agent` modes |
| `/tasks` | View current and completed background tasks |
| `/stop` | Stop the current agent action |
| `/status` | System health status |

---

## Architecture

**Ingress:** the main user-facing **Telegram** bot runs inside the orchestrator (or PTB webhook mode via **`services/webhooks_gateway`**). **MAX** events always use the same gateway (`POST /webhook/max`). See [`services/webhooks_gateway/README.md`](services/webhooks_gateway/README.md).

```
┌──────────────────────────────────────────────┐
│           Main Telegram Bot                  │
│  commands · per-user lock · bg monitor loop  │
│  blog approval callbacks (✅/✏️/❌)          │
└────────────────────┬─────────────────────────┘
                     │ HTTP
┌────────────────────▼─────────────────────────┐
│         Orchestrator (FastAPI :18102)        │
│  ├── OrchestratorAgent                       │
│  ├── ToolDispatcher                          │
│  │     web_search · fetch_url               │
│  │     execute_command · file_read/write     │
│  │     workspace_read/write · memory tools  │
│  │     delegate_to_agent · task management  │
│  │     blogger tools (read/create/schedule) │
│  ├── AgentWorkspace (MD files + git)         │
│  └── Heartbeat loop (proactive messages)     │
└──────────┬───────────────┬───────────────────┘
           │               │ HTTP
     ┌─────▼──────┐  ┌─────▼────────────────────────────────┐
     │   Redis    │  │    Coder Agent (FastAPI :18103)      │
     │  history   │  │  Delegated tasks · file I/O · git    │
     │  sessions  │  │  grep · diff · shell · full dev ops  │
     └─────┬──────┘  └──────────────────────────────────────┘
           │
     ┌─────▼──────┐
     │   Qdrant   │
     │  semantic  │
     │  memory    │
     └────────────┘

┌──────────────────────────────────────────────┐
│     Blogger Service (FastAPI :18105)         │
│  ├── BloggerAgent (LLM post generation)      │
│  ├── PostQueue (PostgreSQL draft/approve)    │
│  ├── TelegramPublisher (3 channels)          │
│  ├── BusinessBot (silent group monitor)      │
│  │     ├── Anonymizes employee messages      │
│  │     └── Evening check-in DMs to owner    │
│  └── APScheduler                            │
│        ├── 20:00 — evening check-in         │
│        └── hourly — publish queue           │
└──────────────────────────────────────────────┘
```

### Background Task Flow

```
You → Orchestrator → delegate_to_agent(coder, background=true)
                            │
                     Coder Agent works...
                            │ (every 5s)
                     bg_monitor_loop ← polls /api/v1/tasks/bg/events
                            │
                     Telegram: live trace + final result ✅
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.13 |
| Agent framework | FastAPI + asyncio (custom) |
| LLM gateway | [OpenRouter](https://openrouter.ai) (all major models) |
| Telegram | python-telegram-bot v22+ |
| Fast memory | Redis (chat history, sessions, flags) |
| Long-term memory | Qdrant (semantic vector search) |
| Database | PostgreSQL |
| Voice transcription | openai-whisper + ffmpeg; cloud STT optional |
| Search | Tavily · Yandex Search API v2 · Brave |
| Infrastructure | Docker Compose |
| Code quality | ruff · pre-commit |

---

## Model Tiers

Pick the right model for each task:

| Tier | Use Case | Examples |
|------|----------|---------|
| `free` | Default, heartbeat, light tasks | StepFun Step 3.5 Flash, MiniMax M2.5:free |
| `cheap` | Everyday tasks, fallback | Llama 3.3 70B, MiniMax M2.5 |
| `medium` | Complex reasoning | Kimi K2.5, Gemini Flash |
| `premium` | Critical tasks, best quality | Claude Sonnet, GPT-4o |

---

## Quick Start

### Prerequisites

- Linux server (VPS or local)
- Docker + Docker Compose
- Python 3.13
- Telegram bot token ([@BotFather](https://t.me/botfather))
- [OpenRouter](https://openrouter.ai) API key

### 1. Clone and configure

```bash
git clone https://github.com/your-username/balbes.git
cd balbes
cp .env.example .env.prod
```

Edit `.env.prod`:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_USER_ID=YOUR_TELEGRAM_USER_ID  # get it from @userinfobot
WEB_AUTH_TOKEN=any-random-secret
JWT_SECRET=any-random-secret
POSTGRES_PASSWORD=your-password
```

Optional (for web search):

```bash
TAVILY_API_KEY=tvly-...         # https://tavily.com
YANDEX_SEARCH_KEY=AQVN...       # Yandex Cloud API key
YANDEX_FOLDER_ID=b1g...         # Yandex Cloud folder ID
BRAVE_SEARCH_KEY=...            # https://api.search.brave.com
```

Optional (for Blogger agent):

```bash
OWNER_TELEGRAM_ID=123456789     # Your Telegram user_id (@userinfobot)
BUSINESS_BOT_TOKEN=...          # Separate bot for business group monitoring
BLOGGER_CHANNEL_RU=-1001...     # Russian-language channel ID
BLOGGER_CHANNEL_EN=-1001...     # English-language channel ID
BLOGGER_CHANNEL_PERSONAL=-1001... # Personal blog channel ID
BLOGGER_SERVICE_PORT=18105
```

### 2. Start infrastructure

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 3. Start services

```bash
bash scripts/start_prod.sh
```

### 4. Open Telegram and send `/start`

---

## Project Structure

```
balbes/
├── config/
│   └── providers.yaml          # Models, agents, skills, heartbeat, blogger config
├── data/
│   ├── agents/                 # Per-agent workspace (versioned in private git)
│   │   ├── orchestrator/
│   │   │   ├── SOUL.md         # Agent personality
│   │   │   ├── AGENTS.md       # Behavior instructions
│   │   │   ├── MEMORY.md       # Persistent important context
│   │   │   ├── HEARTBEAT.md    # Topics for proactive messages
│   │   │   └── config.yaml     # Per-agent overrides (highest priority)
│   │   ├── coder/
│   │   └── blogger/
│   │       ├── IDENTITY.md     # AI-blogger persona
│   │       ├── SOUL.md         # Writing style guide
│   │       ├── INTERVIEW_PROMPTS.md  # Evening check-in questions
│   │       └── config.yaml
│   └── cursor_chats/           # Drop Cursor AI markdown exports here
├── services/
│   ├── webhooks_gateway/       # HTTPS: Telegram webhook, MAX webhook, /webhook/notify
│   ├── orchestrator/           # Main agent + Telegram bot (port 18102)
│   │   ├── agent.py
│   │   ├── telegram_bot.py
│   │   ├── tools.py
│   │   └── skills/             # web_search, server_commands, ...
│   ├── coder/                  # Coder agent (port 18103)
│   ├── blogger/                # Blogger agent service (port 18105)
│   │   ├── agent.py            # LLM post generation
│   │   ├── business_bot.py     # Silent group monitor + owner DMs
│   │   ├── post_queue.py       # PostgreSQL draft/approve/publish
│   │   ├── publisher.py        # Telegram channel publisher
│   │   ├── reader.py           # Chat history, Cursor files, DB reader
│   │   ├── anonymizer.py       # Business message anonymization
│   │   └── api/posts.py        # REST endpoints
│   └── memory-service/         # Memory + history (port 18100)
├── shared/
│   └── config.py               # Pydantic settings
├── scripts/
│   ├── start_prod.sh
│   ├── stop_prod.sh
│   ├── restart_prod.sh
│   └── healthcheck.sh
└── docker-compose.prod.yml
```

---

## Configuration

All agent behavior is controlled through:

- **`config/providers.yaml`** — models, tiers, per-agent settings, skill configs, heartbeat
- **`data/agents/{agent}/config.yaml`** — per-agent overrides (highest priority)
- **`data/agents/{agent}/AGENTS.md`** — behavioral instructions fed to the LLM
- **`data/agents/{agent}/MEMORY.md`** — persistent context the agent always carries
- **`.env.prod`** — secrets and infrastructure settings

See [`docs/en/CONFIGURATION.md`](docs/en/CONFIGURATION.md) for full reference.

---

## Acknowledgements

Inspired by [OpenClaw](https://github.com/openclaw) — the idea that AI tools should be modular, agent-based, and actually useful without constant hand-holding.

---

## License

MIT — see [LICENSE](LICENSE)

**Built with ❤️ and a lot of Telegram messages**

---

## Documentation

| | English | Русский |
|--|---------|---------|
| Getting Started | [docs/en/GETTING_STARTED.md](docs/en/GETTING_STARTED.md) | [docs/ru/GETTING_STARTED.md](docs/ru/GETTING_STARTED.md) |
| Configuration | [docs/en/CONFIGURATION.md](docs/en/CONFIGURATION.md) | [docs/ru/CONFIGURATION.md](docs/ru/CONFIGURATION.md) |
| Agents Guide | [docs/en/AGENTS_GUIDE.md](docs/en/AGENTS_GUIDE.md) | [docs/ru/AGENTS_GUIDE.md](docs/ru/AGENTS_GUIDE.md) |
| Deployment | [docs/en/DEPLOYMENT.md](docs/en/DEPLOYMENT.md) | [docs/ru/DEPLOYMENT.md](docs/ru/DEPLOYMENT.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) | — |
| MAX Messenger | — | [docs/ru/MAX_WEBHOOK.md](docs/ru/MAX_WEBHOOK.md) (webhook, Markdown outbound) |

*[README на русском](README.ru.md)*
