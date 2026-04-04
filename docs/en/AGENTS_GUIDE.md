# Agents Guide

---

## Overview

Balbes has three active agents that work together:

| Agent | Role | Port |
|-------|------|------|
| **Orchestrator** | Main agent — handles all Telegram interactions, delegates tasks | 18102 |
| **Coder** | Development agent — reads/writes code, runs commands, works in background | 18103 |
| **Blogger** | Content agent — generates blog posts, monitors business chats, publishes to Telegram channels | 18105 |

The Orchestrator receives every message. For coding tasks it delegates to Coder; for content generation it delegates to the Blogger service via REST API.

---

## Orchestrator Agent

The Orchestrator is the entry point for everything. It:

- Receives and processes all Telegram messages
- Decides what to do — answer directly, use a tool, or delegate
- Manages multi-chat state (each chat has its own history, model, and agent)
- Runs the Heartbeat loop
- Monitors background tasks and relays results to Telegram

### Workspace

```
data/agents/orchestrator/
├── SOUL.md        ← Personality and communication style
├── AGENTS.md      ← Full behavioral instructions
├── MEMORY.md      ← Always-loaded important context
├── HEARTBEAT.md   ← Topics for proactive messages
├── TOOLS.md       ← Tool documentation
├── IDENTITY.md    ← Identity details
└── config.yaml    ← Model/limit overrides
```

### Customizing behavior

Edit `AGENTS.md` to change how the Orchestrator behaves. This file is loaded as part of the system prompt. For example:

- Add a section "Always respond in Russian" to force Russian responses
- Describe your project so the agent has context by default
- Set specific rules about when to delegate vs handle directly

Edit `MEMORY.md` to give the agent persistent facts it should always know:

```markdown
# Memory

- Main project: ~/projects/balbes (prod), ~/projects/dev (dev)
- Production server: 89.125.73.64
- Deploy process: dev → git push → balbes git pull → restart_prod.sh
- Preferred search: Tavily, fallback to Yandex
```

---

## Coder Agent

The Coder is specialized for software development. It receives delegated tasks from the Orchestrator and can:

- Read any file in the project (`file_read`)
- Write and modify files (`file_write`)
- Run shell commands from the whitelist (`execute_command`)
- Execute git, grep, rg, diff, tree, bash scripts
- Auto-commit file changes to git

### Running in background

When the Orchestrator delegates with `background=true`, the Coder runs asynchronously:

1. Orchestrator sends the task and immediately returns to you
2. Coder agent starts working
3. Every 5 seconds, the background monitor polls for debug events
4. Live trace is streamed to your Telegram chat as the Coder works
5. When done, the final result is sent automatically

You can monitor with `/tasks` or stop with `/stop`.

### Delegation example

If you ask the Orchestrator: *"Refactor the web_search skill to add a new provider"*, it will:

1. Understand this is a coding task
2. Call `delegate_to_agent("coder", task="...", background=true)`
3. You see: *"✅ Task delegated to Coder (background). I'll notify you when done."*
4. Coder reads the relevant files, writes changes, optionally runs tests
5. You receive: *"✅ Coder finished: [summary of what was done]"*

---

## Heartbeat

The Heartbeat runs every 5 minutes using a free LLM model. It reads `HEARTBEAT.md` and `MEMORY.md` and decides whether to send a proactive message.

### Configure heartbeat topics

Edit `data/agents/orchestrator/HEARTBEAT.md`:

```markdown
# Heartbeat Topics

- Check if any background tasks have completed
- Remind me about the current sprint goal: "ship Yandex search integration"
- Suggest an improvement to the project architecture if you have an idea
- Share a relevant news article about AI or software development
```

The agent will send messages only when it has something worth saying — it won't spam.

### Trigger manually

```
/heartbeat
```

---

## Memory System

### Short-term: Redis

- Chat history: last 7 days per chat
- Sessions and per-chat flags (current model, agent, mode)
- Auto-deleted after inactivity

### Long-term: Qdrant

Semantic vector search. Use via Telegram:

```
/remember the production server IP is 89.125.73.64
/recall what's the server IP?
```

Or via the agent tools `save_to_memory` and `recall_from_memory`.

---

## Workspace Versioning

If `setup_memory_repo.sh` was run, every write to `data/agents/*/` is auto-committed and pushed to a private GitHub repo. This gives you:

- Full history of agent workspace changes
- Easy rollback if the agent writes something wrong
- Backup of `MEMORY.md`, `HEARTBEAT.md`, and other workspace files

---

## Blogger Agent

The Blogger is a standalone FastAPI service that turns your work into public content. It runs independently from the Orchestrator and is controlled via REST API and Telegram callbacks.

### What it does

- **Reads** Telegram chat history (via Memory API) and Cursor AI markdown exports from `data/cursor_chats/`
- **Generates** posts in Russian and English from its own perspective ("AI-blogger Balbes")
- **Generates** personal blog posts from the owner's perspective, based on evening check-in interviews
- **Monitors** business Telegram groups silently — anonymizes messages, stores them, generates daily summaries
- **Evening check-in** at 20:00 — sends questions to the owner, processes the reply, creates a personal post draft
- **Manages** a publishing queue — 1–3 posts per day, respects daily quota
- **Approval workflow** — every post goes through ✅ Approve / ✏️ Edit / ❌ Reject before publishing

### Workspace

```
data/agents/blogger/
├── IDENTITY.md         ← Blogger persona ("Балбес" for public, "Nikolai" for personal)
├── SOUL.md             ← Writing style, post structure, topics, prohibitions
├── INTERVIEW_PROMPTS.md ← Evening check-in question templates
├── MEMORY.md           ← Accumulated project and business context
└── config.yaml         ← LLM model, token limits
```

### Business Bot (silent observer)

A separate Telegram bot (`BUSINESS_BOT_TOKEN`) runs inside the Blogger service with dual role:

1. **In group chats** — silently collects and anonymizes employee messages (stored in `business_messages` table)
2. **In private chat with owner** — handles evening check-in replies and post edit instructions

**Security**: the bot only responds to the owner's `OWNER_TELEGRAM_ID`. All other private messages are silently ignored — the bot does not reveal its existence to strangers.

**Anonymization strategies:**
| Strategy | Result |
|----------|--------|
| `initials` | "А.И." (first letter of name + last name) |
| `roles` | "Менеджер", "Разработчик" (from role_map) |
| `full` | Full name kept (use only for trusted chats) |

### Setup

1. Create a new bot via [@BotFather](https://t.me/botfather) → set `BUSINESS_BOT_TOKEN` in `.env.prod`
2. Set `OWNER_TELEGRAM_ID` to your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot))
3. Add the bot to your business Telegram groups as a member (not admin)
4. Send `/start` to the bot in private chat
5. Register groups: `/register_business_chat <group_id> <name> [initials|roles|full]`

### Available Orchestrator tools

The Orchestrator can interact with the Blogger via these tools:

| Tool | Description |
|------|-------------|
| `read_chat_history` | Read recent Telegram chat history |
| `read_cursor_file` | Read a specific Cursor AI markdown export |
| `list_cursor_files` | List available Cursor AI exports |
| `read_business_chats` | Get anonymized business messages |
| `get_business_summary` | Generate LLM summary of business chats |
| `create_draft` | Create a new blog post draft |
| `list_drafts` | List posts by status |
| `get_published_posts` | Get recently published posts |
| `schedule_post` | Schedule a post for specific time |
| `set_business_role` | Set anonymization role for a user |

### Post approval flow

```
BloggerAgent generates post
         │
         ▼
Approval message sent to owner (Telegram)
  [✅ Publish] [✏️ Edit] [❌ Reject]
         │
    ┌────┴────────────┐
  ✅ Approve       ✏️ Edit
  post → queue    owner sends instructions
                  LLM revises post
                  preview updated
```

---

## Adding a New Agent

1. Create a new directory `data/agents/{agent_id}/` with the standard workspace files
2. Add an agent entry to `config/providers.yaml` under `agents:`
3. Register the agent's service in `docker-compose.prod.yml`
4. The Orchestrator can then `delegate_to_agent("{agent_id}", ...)` to it

---

*[Русская версия](../ru/AGENTS_GUIDE.md)*
