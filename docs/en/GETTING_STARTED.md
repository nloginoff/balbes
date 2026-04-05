# Getting Started

This guide will get you from zero to a running Balbes instance in about 15 minutes.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| Linux server | VPS or local machine (Ubuntu 22.04+ recommended) |
| Python 3.13 | `pyenv` recommended |
| Docker + Docker Compose | For infrastructure services |
| Telegram bot token | Create via [@BotFather](https://t.me/botfather) |
| OpenRouter API key | Sign up at [openrouter.ai](https://openrouter.ai) — has a free tier |
| Your Telegram user ID | Get it from [@userinfobot](https://t.me/userinfobot) |

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/your-username/balbes.git
cd balbes
```

---

## Step 2 — Create your environment file

```bash
cp .env.example .env.prod
```

Open `.env.prod` and fill in the required values:

```bash
# Required
OPENROUTER_API_KEY=sk-or-v1-...
TELEGRAM_BOT_TOKEN=123456789:AAF...
TELEGRAM_USER_ID=YOUR_TELEGRAM_USER_ID   # comma-separated for multiple users

# Security (generate random strings)
WEB_AUTH_TOKEN=change-me-to-random-string
JWT_SECRET=change-me-to-another-random-string

# Database
POSTGRES_PASSWORD=your-secure-password

# Voice transcription (optional but recommended)
# Short voice → local openai-whisper; long → OpenRouter / Yandex (see .env.example)
WHISPER_LOCAL_MODEL=medium
WHISPER_LOCAL_MAX_DURATION_SECONDS=30
WHISPER_REMOTE_BACKEND=openrouter_then_yandex
WHISPER_OPENROUTER_STT_MODEL=google/gemini-2.0-flash-001
WHISPER_DEVICE=cpu
```

Optional search providers (at least one recommended):

```bash
TAVILY_API_KEY=tvly-...          # https://tavily.com — free tier available
YANDEX_SEARCH_KEY=AQVN...       # Yandex Cloud API key (starts with AQVN)
YANDEX_FOLDER_ID=b1g...         # Yandex Cloud folder ID
BRAVE_SEARCH_KEY=...             # https://api.search.brave.com
```

---

## Step 3 — Start infrastructure

```bash
docker compose -f docker-compose.prod.yml up -d
```

This starts PostgreSQL, Redis, Qdrant, and RabbitMQ. Check they're running:

```bash
docker compose -f docker-compose.prod.yml ps
```

---

## Step 4 — Set up Python environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r services/orchestrator/requirements.txt
```

---

## Step 5 — Start services

```bash
bash scripts/start_prod.sh
```

Check that services started:

```bash
bash scripts/healthcheck.sh prod
```

Logs:

```bash
tail -f logs/prod/orchestrator.log
tail -f logs/prod/telegram_bot.log
```

---

## Step 6 — Open Telegram

Find your bot and send `/start`. You should see a welcome message.

Try:
- `/help` — see all commands
- `/model` — pick a model (start with `free` tier)
- `/debug` — enable debug trace to see exactly what the agent is doing
- Ask anything in natural language

---

## Configuring Agents

Each agent has its own workspace in `data/agents/{agent_id}/`:

```
data/agents/orchestrator/
├── SOUL.md          ← Personality and communication style
├── AGENTS.md        ← Behavioral instructions (what the LLM sees)
├── MEMORY.md        ← Always-available context (important facts)
├── HEARTBEAT.md     ← Topics for proactive messages
└── config.yaml      ← Model/limit overrides (highest priority)
```

Edit these files to customize your agent's behavior, then the changes take effect on the next message.

### Quick personality tweak

Open `data/agents/orchestrator/SOUL.md` and describe the character you want. The agent will adjust its tone and style on the next conversation.

### Heartbeat topics

Edit `data/agents/orchestrator/HEARTBEAT.md` and list things you want the agent to proactively message you about — project updates, reminders, interesting web searches, etc.

---

## Enable Agent Mode (for Coder)

By default the system runs in `/mode ask` — read-only safe mode. To let the Coder agent write files and run commands:

```
/mode agent
```

Switch back any time:

```
/mode ask
```

See the full list of allowed commands per mode in [`docs/ru/CONFIGURATION.md`](../ru/CONFIGURATION.md) (Russian) or `config/providers.yaml`.

---

## Workspace Versioning (optional)

To automatically backup agent workspace files to a private git repo:

```bash
bash scripts/setup_memory_repo.sh
```

This creates a private GitHub repo and configures auto-commit+push on every workspace write.

---

## Updating

```bash
git pull
bash scripts/restart_prod.sh
```

---

## Troubleshooting

**Bot doesn't respond**
- Check `logs/prod/telegram_bot.log` for errors
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_USER_ID` in `.env.prod`
- Make sure your Telegram user ID is in the allowed list

**"Rate limit" errors with free models**
- Free OpenRouter models have strict rate limits
- The heartbeat delay (`request_delay_seconds` in `providers.yaml`) helps reduce this
- Switch to `cheap` tier for more headroom: `/model`

**Yandex search returns 403**
- The new Yandex Search API v2 requires `YANDEX_FOLDER_ID` (Yandex Cloud folder ID)
- Get it at [console.yandex.cloud](https://console.yandex.cloud) → Resource Manager

**Voice messages not working**
- Install `ffmpeg`: `sudo apt install ffmpeg`
- Install local STT: `pip install openai-whisper` (in the same venv as the orchestrator)
- In `.env.prod`: `OPENROUTER_API_KEY` (cloud STT + correction); for Yandex-only or fallback, `YANDEX_SEARCH_KEY` + `YANDEX_FOLDER_ID` (or `YANDEX_SPEECH_*`)
- Tune routing: `WHISPER_LOCAL_MAX_DURATION_SECONDS`, `WHISPER_REMOTE_BACKEND`, `WHISPER_OPENROUTER_STT_MODEL`

---

*[Русская версия](../ru/GETTING_STARTED.md)*
