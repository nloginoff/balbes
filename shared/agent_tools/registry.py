"""
Shared tool registry for all agents (OpenAI function-calling schemas + ToolDispatcher).

Dispatches tool calls to skill implementations; logging via AgentActivityLogger.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

# Repository root: shared/agent_tools/registry.py -> parents[2]
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# Maximum chars returned by file_read (prevents huge files swamping the context)
_FILE_READ_MAX_CHARS = 30_000

logger = logging.getLogger("shared.agent_tools")

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

AVAILABLE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for current information. "
                "Use when the user asks about recent events, facts you're unsure about, "
                "or explicitly requests a search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in natural language",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                    "provider": {
                        "type": "string",
                        "description": (
                            "Force a specific search provider: tavily | yandex | brave. "
                            "If omitted, uses the active default from config."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Retrieve and read the text content of a web page. "
                "Use when the user shares a URL or when a search result needs to be read in full."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL of the page to fetch",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": (
                "Execute a whitelisted server command and return its output. "
                "Use for server status checks: disk space, memory, Docker containers, "
                "running services. Only whitelisted commands are allowed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute (must be in whitelist)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_read",
            "description": (
                "Read one of the agent's own workspace files. "
                "Available files: AGENTS.md, SOUL.md, USER.md, MEMORY.md, TOOLS.md, IDENTITY.md, "
                "HEARTBEAT.md, schedules.yaml (cron jobs for this agent)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename to read, e.g. 'MEMORY.md'",
                    },
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "workspace_write",
            "description": (
                "Overwrite a workspace file with new content. "
                "Always read the file first, then write the complete updated version. "
                "Writable files: AGENTS.md, SOUL.md, USER.md, MEMORY.md, IDENTITY.md, HEARTBEAT.md, "
                "schedules.yaml (YAML; same schema as manage_schedule)"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": "Filename to write, e.g. 'MEMORY.md'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete new content of the file",
                    },
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_chat",
            "description": (
                "Set a descriptive name for the current chat session (3-5 words). "
                "Use when the user requests a rename or after summarizing a conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "New chat name (short, 3-5 words)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": (
                "Store important information in long-term memory (Qdrant). "
                "The text will be rephrased into a concise fact before saving. "
                "Use when the user says 'remember this' or the info is clearly important."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Information to remember",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_from_memory",
            "description": (
                "Search long-term memory (Qdrant) for stored facts and notes. "
                "Use when the user asks about something previously remembered, "
                "or when you need to recall past context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_search",
            "description": (
                "Search the project codebase semantically. Returns matching files with previews. "
                "Use when you need to find code by meaning, e.g. 'where is auth handled', "
                "'find the database connection code', 'LLM call implementation'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of the code you're looking for",
                    },
                    "path_filter": {
                        "type": "string",
                        "description": "Optional: filter results to paths containing this string",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "index_codebase",
            "description": (
                "Re-index the project codebase for semantic search. "
                "Use when you suspect the index is stale or after large changes. "
                "Returns indexing statistics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional: sub-path to index (default: entire project)",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Force re-index all files, even if unchanged (default: false)",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_to_agent",
            "description": (
                "Delegate a task to a specialist sub-agent and return their response. "
                "Use 'coder' for code, files, tests, git. "
                "Use 'blogger' for drafts, posts, channel content, blog summaries. "
                "Provide a complete, self-contained task — the sub-agent has NO chat history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Target agent: 'coder' (dev) or 'blogger' (blog)",
                        "enum": ["coder", "blogger"],
                    },
                    "task": {
                        "type": "string",
                        "description": (
                            "Complete, standalone task description. Include file paths, "
                            "language / framework, expected output format, and any "
                            "constraints (e.g. 'do not change the public API')."
                        ),
                    },
                    "mode": {
                        "type": "string",
                        "description": (
                            "'agent' = can run commands, write files, use git (default). "
                            "'ask' = safe info commands only, no writes."
                        ),
                        "enum": ["agent", "ask"],
                        "default": "agent",
                    },
                    "background": {
                        "type": "boolean",
                        "description": (
                            "If true, run the task in the background and return immediately. "
                            "Use when the task is long-running and the user should not wait. "
                            "Retrieve the result later with get_agent_result(agent_id). "
                            "Default: false (synchronous, wait for result)."
                        ),
                        "default": False,
                    },
                },
                "required": ["agent_id", "task"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agent_tasks",
            "description": (
                "Show the list of all recent tasks across all agents — "
                "running, completed, cancelled, or failed. "
                "Use when the user asks what is currently happening, "
                "what agents are doing, or wants a project status overview."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max tasks to return (default 10, max 30)",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_result",
            "description": (
                "Retrieve the result of a background agent task. "
                "Returns the result text if completed, 'running' if still in progress, "
                "or null if no task was started. Always call this before telling the "
                "user the coder is done with a background task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent whose result to retrieve, e.g. 'coder'",
                        "enum": ["coder"],
                    },
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_agent_task",
            "description": (
                "Cancel a running background task for a specific agent. "
                "Use when the user says 'stop the coder', 'cancel coder task', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Agent whose task to cancel, e.g. 'coder'",
                        "enum": ["coder"],
                    },
                },
                "required": ["agent_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_agent_logs",
            "description": (
                "Read the agent's activity logs — all tool and skill calls with timestamps. "
                "Use when the user asks to show logs, activity, history of commands for a day or period."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": (
                            "Specific day: 'today', 'yesterday', or 'YYYY-MM-DD'. "
                            "Omit to use today."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Start of date range 'YYYY-MM-DD' (use with end_date).",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "End of date range 'YYYY-MM-DD' (inclusive).",
                    },
                    "tool_filter": {
                        "type": "string",
                        "description": (
                            "Optional: show only this tool name (e.g. web_search). "
                            "Omit the parameter entirely when not filtering — do not pass null, "
                            "empty string, or the word 'null'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (default 50, max 200). Use a number, not a string.",
                        "default": 50,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": (
                "Read a project file by path and return its contents. "
                "Supports optional line range (offset/limit) for large files. "
                "Path must be relative to the project root or absolute within it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root, e.g. 'services/orchestrator/agent.py'",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "First line to return (1-based). Omit to start from beginning.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to return (default 200).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": (
                "Write (create or overwrite) a project file with the given content. "
                "Path must be relative to the project root or absolute within it. "
                "Forbidden: .env files, credential files, private key files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root, e.g. 'services/orchestrator/agent.py'",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete new content of the file.",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_patch",
            "description": (
                "Replace an exact string in a project file (targeted edit). "
                "Finds the FIRST occurrence of old_string and replaces it with new_string. "
                "Fails if old_string is not found or appears more than once. "
                "Prefer this over file_write for editing large files — only send the changed block."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root or absolute within it.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": (
                            "Exact text to find and replace. Must be unique in the file. "
                            "Include enough surrounding lines for uniqueness."
                        ),
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text (can be empty string to delete).",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "manage_todo",
            "description": (
                "Read or update the project TODO.md backlog. "
                "Use 'read' to show current tasks; 'add' to append a new item to a section; "
                "'done' to mark an item as completed (moves it to Выполнено). "
                "Always use this tool when the user asks to add, update, or check the TODO list."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "add", "done"],
                        "description": "'read' — return full TODO.md; 'add' — append item; 'done' — mark item done",
                    },
                    "section": {
                        "type": "string",
                        "enum": ["В работе", "Запланировано", "Идеи"],
                        "description": "Target section for 'add' action",
                    },
                    "item": {
                        "type": "string",
                        "description": "Item text to add (for 'add') or substring to match for 'done'",
                    },
                },
                "required": ["action"],
            },
        },
    },
    # ── Blogger tools ────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_chat_history",
            "description": (
                "Read recent chat history with system agents (balbes, coder) from memory service. "
                "Use to gather material for blog posts. Available only for blogger agent."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agents": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of agent IDs to read history from (e.g. ['balbes', 'coder']).",
                    },
                    "from_ts": {
                        "type": "string",
                        "description": "ISO 8601 timestamp — read messages after this time.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages to return (default: 100).",
                    },
                },
                "required": ["agents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cursor_file",
            "description": (
                "Read a Markdown file exported from Cursor AI session. "
                "Use to extract context from coding sessions for blog posts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the Markdown file (relative to project root or absolute).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cursor_files",
            "description": "List Markdown files in the cursor_chats directory, newest first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory to scan (default: data/cursor_chats).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_business_chats",
            "description": (
                "Read anonymized messages from registered business Telegram groups. "
                "Messages are pre-anonymized — no real names or sensitive data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of business_chats DB IDs to read from. Omit for all.",
                    },
                    "from_ts": {
                        "type": "string",
                        "description": "ISO 8601 timestamp — read messages after this time.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max messages (default: 200).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_business_summary",
            "description": (
                "Generate an LLM summary of business chat activity for the given period. "
                "Returns a structured digest of topics, decisions, and issues. "
                "Sent privately to the owner — not published."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Business chat IDs to summarize. Omit for all.",
                    },
                    "period_hours": {
                        "type": "integer",
                        "description": "Summarize messages from the last N hours (default: 24).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_draft",
            "description": (
                "Create a blog post draft and send it to the owner for approval. "
                "Always provide both content_ru and content_en. "
                "post_type='agent' → RU+EN channels; post_type='user' → personal blog (always requires approval)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content_ru": {
                        "type": "string",
                        "description": "Post text in Russian.",
                    },
                    "content_en": {
                        "type": "string",
                        "description": "Post text in English.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Post title or headline.",
                    },
                    "post_type": {
                        "type": "string",
                        "enum": ["agent", "user"],
                        "description": "agent = from AI perspective (RU+EN); user = from owner perspective (personal).",
                    },
                    "source_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of source references (e.g. 'cursor:session.md', 'chat:2026-04-04').",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Internal notes about this draft.",
                    },
                },
                "required": ["content_ru", "content_en"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_drafts",
            "description": "List blog post drafts with optional status filter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [
                            "draft",
                            "pending_approval",
                            "approved",
                            "scheduled",
                            "published",
                            "rejected",
                        ],
                        "description": "Filter by status. Omit to list all.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_published_posts",
            "description": "Get recent published posts for context — use to avoid repeating topics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent posts to return (default: 10).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_post",
            "description": "Schedule an approved post for publishing at a specific time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "post_id": {
                        "type": "string",
                        "description": "UUID of the approved post.",
                    },
                    "publish_at": {
                        "type": "string",
                        "description": "ISO 8601 datetime for publishing (e.g. '2026-04-05T10:00:00Z').",
                    },
                },
                "required": ["post_id", "publish_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_business_role",
            "description": "Map a Telegram user_id to a role label for anonymization in a specific business group.",
            "parameters": {
                "type": "object",
                "properties": {
                    "group_id": {
                        "type": "string",
                        "description": "Telegram group ID (e.g. '-1001234567890').",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "Telegram user_id to map.",
                    },
                    "role": {
                        "type": "string",
                        "description": "Role label (e.g. 'менеджер', 'разработчик', 'клиент').",
                    },
                },
                "required": ["group_id", "user_id", "role"],
            },
        },
    },
    # ── End blogger tools ────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "manage_schedule",
            "description": (
                "Manage scheduled tasks (cron/interval jobs). "
                "Jobs are stored per agent in data/agents/<agent>/schedules.yaml (like workspace files). "
                "Use list/add/remove/enable/disable. Changes take effect within ~30 seconds without a restart."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add", "remove", "enable", "disable"],
                        "description": (
                            "list — show all scheduled jobs; "
                            "add — create a new job (requires job_id, trigger, prompt); "
                            "remove — delete a job by job_id; "
                            "enable/disable — toggle a job on or off."
                        ),
                    },
                    "job_id": {
                        "type": "string",
                        "description": "Unique job identifier (snake_case). Required for add/remove/enable/disable.",
                    },
                    "trigger": {
                        "type": "string",
                        "enum": ["cron", "interval"],
                        "description": "Trigger type. 'cron' = at specific time; 'interval' = every N minutes/hours.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Task description sent to the agent when the job fires. Required for 'add'.",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": (
                            "Which agent's schedules.yaml to edit (default: current task agent). "
                            "Must match the job's agent. For list, all agents are shown."
                        ),
                    },
                    "hour": {
                        "type": "integer",
                        "description": "Hour (0–23) for cron trigger.",
                    },
                    "minute": {
                        "type": "integer",
                        "description": "Minute (0–59) for cron trigger (default: 0).",
                    },
                    "day_of_week": {
                        "type": "string",
                        "description": "Days for cron trigger: mon,tue,wed,thu,fri,sat,sun (or * for every day).",
                    },
                    "minutes": {
                        "type": "integer",
                        "description": "Repeat every N minutes (interval trigger).",
                    },
                    "hours": {
                        "type": "integer",
                        "description": "Repeat every N hours (interval trigger).",
                    },
                    "debug": {
                        "type": "boolean",
                        "description": "Send debug trace when this job runs (default: false).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_solution",
            "description": (
                "Render a complete written solution (text + formulas) as one or more fixed-size PNG "
                "pages for comfortable reading in chat. Pass the entire solution in one call — do not "
                "split into many tool calls per formula. Use when the user needs readable math in "
                "messengers; plain copyable text can still be given in the normal assistant reply."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "Full solution text: steps, explanations, and LaTeX-style formulas "
                            "($...$ or lines with \\frac, ^, _). Cyrillic and plain text are supported."
                        ),
                    },
                },
                "required": ["content"],
            },
        },
    },
]


def tool_name_from_schema(tool: dict[str, Any]) -> str:
    return str(tool.get("function", {}).get("name", ""))


def filter_tools_by_allowlist(
    full: list[dict[str, Any]], allowlist: set[str] | None
) -> list[dict[str, Any]]:
    """allowlist None = full catalog. Empty set = no tools."""
    if allowlist is None:
        return full
    if not allowlist:
        return []
    return [t for t in full if tool_name_from_schema(t) in allowlist]


def resolve_tools_for_agent(
    agent_id: str,
    providers_config: dict[str, Any] | None,
    full_catalog: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Return tool schemas for an agent using optional tools_allowlist in providers.yaml.
    Missing or null allowlist means all tools from full_catalog.
    """
    catalog = full_catalog if full_catalog is not None else AVAILABLE_TOOLS
    if providers_config:
        for a in providers_config.get("agents", []) or []:
            if a.get("id") == agent_id:
                raw = a.get("tools_allowlist")
                if raw is None:
                    return catalog
                if not isinstance(raw, list):
                    return catalog
                allow = {str(x) for x in raw}
                return filter_tools_by_allowlist(catalog, allow)
    return catalog


def build_heartbeat_tools(
    resolved: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Minimal tool set for heartbeat — workspace_read only."""
    src = resolved if resolved is not None else AVAILABLE_TOOLS
    return [t for t in src if tool_name_from_schema(t) == "workspace_read"]


def build_subagent_tools(resolved: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Sub-agents cannot call delegate_to_agent (prevents infinite delegation)."""
    src = resolved if resolved is not None else AVAILABLE_TOOLS
    return [t for t in src if tool_name_from_schema(t) != "delegate_to_agent"]


# Default subsets over full catalog (backward compatibility).
HEARTBEAT_TOOLS: list[dict[str, Any]] = build_heartbeat_tools()
AGENT_TOOLS: list[dict[str, Any]] = build_subagent_tools()


def normalize_read_agent_logs_args(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Coerce LLM / client quirks: string 'null', quoted numbers, empty strings.

    MAX and other clients sometimes send tool_filter='null' or limit='10'.
    """

    def _str_or_none(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            if isinstance(v, float) and not v.is_integer():
                return str(v)
            return str(int(v))
        s = str(v).strip()
        if not s or s.lower() in ("null", "none", "undefined", "n/a", "[]", "{}"):
            return None
        return s

    def _limit(v: Any) -> int:
        if v is None:
            return 50
        if isinstance(v, bool):
            return 50
        try:
            if isinstance(v, str):
                t = v.strip().lower()
                if not t or t in ("null", "none", "undefined"):
                    return 50
                return max(1, min(int(t), 200))
            return max(1, min(int(v), 200))
        except (TypeError, ValueError):
            return 50

    return {
        "date": _str_or_none(raw.get("date")),
        "start_date": _str_or_none(raw.get("start_date")),
        "end_date": _str_or_none(raw.get("end_date")),
        "tool_filter": _str_or_none(raw.get("tool_filter")),
        "limit": _limit(raw.get("limit")),
    }


def get_tools_for_mode(mode: str) -> list[dict[str, Any]]:
    """
    Return the list of available tool schemas for the given execution mode.

    Both modes expose the same set of tools. The difference is enforced at the
    command-whitelist level inside ServerCommandSkill:

    - "agent": full development whitelist (git, python, pytest, make, …)
    - "ask":   restricted whitelist — safe info commands only (date, find, df,
               docker ps, ls, cat, …).  workspace_write is still available so
               the agent can update its own MEMORY.md / AGENTS.md files.
    """
    return AVAILABLE_TOOLS


class ToolDispatcher:
    """
    Dispatches tool call requests to the appropriate skill implementation.
    Instantiated once per agent instance.
    Every call is automatically logged via AgentActivityLogger.
    """

    def __init__(
        self,
        workspace=None,
        http_client=None,
        providers_config=None,
        activity_logger=None,
        delegate_callback=None,
        background_runner=None,
        get_result_callback=None,
        cancel_callback=None,
        list_tasks_callback=None,
    ):
        self.workspace = workspace
        self.http_client = http_client
        self.providers_config = providers_config
        self._logger = activity_logger  # AgentActivityLogger | None
        self._debug_collector: list[dict] | None = None  # set per-task when debug=True
        # async (agent_id, task, context, mode) -> str  — synchronous delegation
        self._delegate_callback = delegate_callback
        # async (agent_id, task, context, mode, notify_cb) -> key  — background delegation
        self._background_runner = background_runner
        # (agent_id, user_id) -> dict | None  — retrieve background result
        self._get_result_callback = get_result_callback
        # (agent_id, user_id) -> str  — cancel background task
        self._cancel_callback = cancel_callback
        # (user_id, limit) -> list[dict]  — task registry listing
        self._list_tasks_callback = list_tasks_callback

        # Lazy-loaded skill instances
        self._web_search = None
        self._server_commands = None

        # Per-task call counters for rate limiting
        self._call_counts: dict[str, int] = {}
        # Images / files produced by tools for outbound delivery (Telegram, MAX, web)
        self._outbound_attachments: list[dict[str, Any]] = []

    # Per-task rate limits (max calls per tool per task)
    _RATE_LIMITS: dict[str, int] = {
        "web_search": 10,
        "fetch_url": 15,
        "execute_command": 30,
        "file_read": 40,
        "file_write": 20,
        "file_patch": 20,
        "workspace_read": 40,
        "workspace_write": 20,
        "render_solution": 3,
    }
    _DEFAULT_RATE_LIMIT = 20

    def reset_call_counts(self) -> None:
        """Reset per-tool call counters. Call at the start of each new task."""
        self._call_counts.clear()
        self._outbound_attachments.clear()

    def take_outbound_attachments(self) -> list[dict[str, Any]]:
        """Return and clear pending outbound images/files for this task."""
        out = list(self._outbound_attachments)
        self._outbound_attachments.clear()
        return out

    def extend_outbound_attachments(self, items: list[dict[str, Any]]) -> None:
        """Merge attachments from a sub-agent HTTP response (e.g. coder delegation)."""
        for it in items:
            if isinstance(it, dict) and it.get("kind") == "image" and it.get("base64"):
                self._outbound_attachments.append(dict(it))

    def set_debug_collector(self, collector: list[dict] | None) -> None:
        """Attach (or detach) a debug event list for the current task."""
        self._debug_collector = collector

    async def dispatch(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Execute a tool and return its result as a string.
        context may contain: user_id, chat_id, memory_service_url, openrouter_api_key, source
        """
        context = context or {}
        t0 = time.monotonic()
        success = True
        result = ""

        # Rate limit check
        limit = self._RATE_LIMITS.get(tool_name, self._DEFAULT_RATE_LIMIT)
        call_count = self._call_counts.get(tool_name, 0)
        if call_count >= limit:
            return (
                f"Error: инструмент '{tool_name}' вызван {call_count} раз за одну задачу. "
                f"Лимит: {limit}. Подведи итог по текущим данным."
            )
        self._call_counts[tool_name] = call_count + 1

        # Emit "tool started" debug event (include agent_id for delegation visibility)
        if self._debug_collector is not None:
            self._debug_collector.append(
                {
                    "type": "tool_start",
                    "name": tool_name,
                    "summary": _summarize_input(tool_name, tool_args),
                    "agent": context.get("agent_id", ""),
                }
            )

        try:
            if tool_name == "web_search":
                result = await self._do_web_search(tool_args)

            elif tool_name == "fetch_url":
                result = await self._do_fetch_url(tool_args)

            elif tool_name == "execute_command":
                result = await self._do_execute_command(tool_args, context)

            elif tool_name == "workspace_read":
                result = self._do_workspace_read(tool_args)

            elif tool_name == "workspace_write":
                result = self._do_workspace_write(tool_args)

            elif tool_name == "rename_chat":
                result = await self._do_rename_chat(tool_args, context)

            elif tool_name == "save_to_memory":
                result = await self._do_save_to_memory(tool_args, context)

            elif tool_name == "recall_from_memory":
                result = await self._do_recall_from_memory(tool_args, context)

            elif tool_name == "code_search":
                result = await self._do_code_search(tool_args, context)

            elif tool_name == "index_codebase":
                result = await self._do_index_codebase(tool_args, context)

            elif tool_name == "delegate_to_agent":
                result = await self._do_delegate_to_agent(tool_args, context)

            elif tool_name == "get_agent_result":
                result = self._do_get_agent_result(tool_args, context)

            elif tool_name == "cancel_agent_task":
                result = self._do_cancel_agent_task(tool_args, context)

            elif tool_name == "list_agent_tasks":
                result = self._do_list_agent_tasks(tool_args, context)

            elif tool_name == "read_agent_logs":
                result = self._do_read_agent_logs(tool_args)

            elif tool_name == "file_read":
                result = self._do_file_read(tool_args)

            elif tool_name == "file_write":
                result = self._do_file_write(tool_args)

            elif tool_name == "file_patch":
                result = self._do_file_patch(tool_args)

            elif tool_name == "manage_todo":
                result = self._do_manage_todo(tool_args)

            elif tool_name == "manage_schedule":
                result = self._do_manage_schedule(tool_args, context)

            elif tool_name == "render_solution":
                result = await self._do_render_solution(tool_args)

            # ── Blogger tools (only meaningful when agent_id == "blogger") ──
            elif tool_name == "read_chat_history":
                result = await self._do_read_chat_history(tool_args, context)

            elif tool_name == "read_cursor_file":
                result = self._do_read_cursor_file(tool_args)

            elif tool_name == "list_cursor_files":
                result = self._do_list_cursor_files(tool_args)

            elif tool_name == "read_business_chats":
                result = await self._do_read_business_chats(tool_args, context)

            elif tool_name == "get_business_summary":
                result = await self._do_get_business_summary(tool_args, context)

            elif tool_name == "create_draft":
                result = await self._do_create_draft(tool_args, context)

            elif tool_name == "list_drafts":
                result = await self._do_list_drafts(tool_args, context)

            elif tool_name == "get_published_posts":
                result = await self._do_get_published_posts(tool_args, context)

            elif tool_name == "schedule_post":
                result = await self._do_schedule_post(tool_args, context)

            elif tool_name == "set_business_role":
                result = await self._do_set_business_role(tool_args, context)

            else:
                result = f"Unknown tool: {tool_name}"
                success = False

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            result = f"Error executing {tool_name}: {str(e)}"
            success = False

        finally:
            duration_ms = (time.monotonic() - t0) * 1000
            self._log(tool_name, tool_args, result, duration_ms, success, context)

            # Emit "tool done" debug event
            if self._debug_collector is not None:
                self._debug_collector.append(
                    {
                        "type": "tool_done",
                        "name": tool_name,
                        "ok": success,
                        "summary": _summarize_result(result),
                        "ms": round(duration_ms),
                        "agent": context.get("agent_id", ""),
                    }
                )

        return result

    def _log(
        self,
        tool_name: str,
        tool_args: dict,
        result: str,
        duration_ms: float,
        success: bool,
        context: dict,
    ) -> None:
        """Write one entry to the daily activity log."""
        if not self._logger:
            return
        # Don't log read_agent_logs calls (would be recursive noise)
        if tool_name == "read_agent_logs":
            return

        input_summary = _summarize_input(tool_name, tool_args)
        result_summary = _summarize_result(result)

        self._logger.log_tool_call(
            tool_name=tool_name,
            input_summary=input_summary,
            result_summary=result_summary,
            duration_ms=duration_ms,
            success=success,
            user_id=context.get("user_id", ""),
            chat_id=context.get("chat_id", ""),
            source=context.get("source", "user"),
        )

    async def _do_web_search(self, args: dict[str, Any]) -> str:
        from skills.web_search import WebSearchSkill

        if self._web_search is None:
            self._web_search = WebSearchSkill(http_client=self.http_client)
        results, provider_used = await self._web_search.search(
            query=args["query"],
            max_results=args.get("max_results", 5),
            provider_override=args.get("provider"),
        )
        if not results:
            return f"[{provider_used}] No results found."
        lines = [f"[{provider_used}] {len(results)} result(s):"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r.title}**\n   {r.url}\n   {r.snippet}")
        return "\n\n".join(lines)

    async def _do_fetch_url(self, args: dict[str, Any]) -> str:
        from skills.fetch_url import fetch_url

        return await fetch_url(url=args["url"], http_client=self.http_client)

    async def _do_execute_command(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        from skills.server_commands import ServerCommandSkill

        if self._server_commands is None:
            self._server_commands = ServerCommandSkill()
        result = await self._server_commands.execute(
            command=args["command"],
            user_id=context.get("user_id", "unknown"),
            chat_id=context.get("chat_id", "unknown"),
            agent_id=context.get("agent_id"),
            mode=context.get("mode", "agent"),
        )
        output = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        exit_code = result.get("exit_code", 0)
        parts = []
        if output:
            parts.append(output)
        if stderr:
            parts.append(f"[stderr]: {stderr}")
        if exit_code != 0:
            parts.append(f"[exit code: {exit_code}]")
        return "\n".join(parts) if parts else "(no output)"

    def _do_workspace_read(self, args: dict[str, Any]) -> str:
        if not self.workspace:
            return "Workspace not available."
        filename = args.get("filename") or args.get("file") or args.get("path") or args.get("name")
        if not filename:
            available = (
                "AGENTS.md, SOUL.md, MEMORY.md, HEARTBEAT.md, TOOLS.md, IDENTITY.md, schedules.yaml"
            )
            return (
                "Error: 'filename' parameter is required. "
                f"Available files: {available}. "
                "Example: workspace_read(filename='HEARTBEAT.md')"
            )
        content = self.workspace.read_file(filename)
        if not content:
            return f"File '{filename}' not found or empty."
        return content

    def _do_workspace_write(self, args: dict[str, Any]) -> str:
        if not self.workspace:
            return "Workspace not available."
        success = self.workspace.write_file(args["filename"], args["content"])
        if success:
            return f"File '{args['filename']}' updated successfully."
        return f"Failed to write '{args['filename']}'. File may not be writable."

    def _do_file_read(self, args: dict[str, Any]) -> str:
        """Read an arbitrary project file (within project root)."""
        raw_path = args.get("path", "")
        if not raw_path:
            return "Error: 'path' parameter is required."
        try:
            p = Path(raw_path)
            resolved = (_PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
            if not str(resolved).startswith(str(_PROJECT_ROOT)):
                return f"Access denied: path '{raw_path}' is outside project root."
            if not resolved.exists():
                return f"File not found: {raw_path}"
            if not resolved.is_file():
                return f"Not a file: {raw_path}"
        except Exception as e:
            return f"Invalid path '{raw_path}': {e}"

        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading '{raw_path}': {e}"

        lines = text.splitlines(keepends=True)
        total = len(lines)

        offset = max(1, int(args.get("offset") or 1))
        limit = int(args.get("limit") or 200)
        chunk = lines[offset - 1 : offset - 1 + limit]

        numbered = "".join(f"{offset + i:6}|{line}" for i, line in enumerate(chunk))

        # Trim if result is too large
        if len(numbered) > _FILE_READ_MAX_CHARS:
            numbered = numbered[:_FILE_READ_MAX_CHARS] + "\n[... truncated ...]"

        header = (
            f"--- {raw_path} (lines {offset}-{min(offset + limit - 1, total)} of {total}) ---\n"
        )
        return header + numbered

    def _do_file_write(self, args: dict[str, Any]) -> str:
        """Write an arbitrary project file (within project root, not .env / keys)."""
        raw_path = args.get("path", "")
        content = args.get("content", "")
        if not raw_path:
            return "Error: 'path' parameter is required."

        # Forbidden patterns
        forbidden = (".env", ".key", ".pem", ".p12", "secret", "credential", "password")
        name_lower = Path(raw_path).name.lower()
        if any(name_lower.startswith(pat) or name_lower.endswith(pat) for pat in forbidden):
            return f"Write denied: '{raw_path}' matches a forbidden filename pattern."

        try:
            p = Path(raw_path)
            resolved = (_PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
            if not str(resolved).startswith(str(_PROJECT_ROOT)):
                return f"Access denied: path '{raw_path}' is outside project root."
        except Exception as e:
            return f"Invalid path '{raw_path}': {e}"

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            rel = resolved.relative_to(_PROJECT_ROOT)
            return f"Written {len(content)} chars to {rel} ({len(content.splitlines())} lines)."
        except Exception as e:
            return f"Error writing '{raw_path}': {e}"

    def _do_file_patch(self, args: dict[str, Any]) -> str:
        """Replace an exact string in a project file (targeted edit)."""
        raw_path = args.get("path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        if not raw_path:
            return "Error: 'path' parameter is required."
        if not old_string:
            return "Error: 'old_string' parameter is required."

        forbidden = (".env", ".key", ".pem", ".p12", "secret", "credential", "password")
        name_lower = Path(raw_path).name.lower()
        if any(name_lower.startswith(pat) or name_lower.endswith(pat) for pat in forbidden):
            return f"Write denied: '{raw_path}' matches a forbidden filename pattern."

        try:
            p = Path(raw_path)
            resolved = (_PROJECT_ROOT / p).resolve() if not p.is_absolute() else p.resolve()
            if not str(resolved).startswith(str(_PROJECT_ROOT)):
                return f"Access denied: path '{raw_path}' is outside project root."
            if not resolved.exists():
                return f"File not found: {raw_path}"
            if not resolved.is_file():
                return f"Not a file: {raw_path}"
        except Exception as e:
            return f"Invalid path '{raw_path}': {e}"

        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading '{raw_path}': {e}"

        count = content.count(old_string)
        if count == 0:
            # Show a snippet near the expected location to help the model debug
            first_line = old_string.splitlines()[0][:60] if old_string else ""
            hint = f" (first line of old_string: {first_line!r})" if first_line else ""
            return (
                f"Error: old_string not found in {raw_path}{hint}. "
                "Check that the text matches exactly, including whitespace and indentation."
            )
        if count > 1:
            return (
                f"Error: old_string appears {count} times in {raw_path} — it must be unique. "
                "Add more surrounding lines to make it unambiguous."
            )

        new_content = content.replace(old_string, new_string, 1)
        try:
            resolved.write_text(new_content, encoding="utf-8")
            rel = resolved.relative_to(_PROJECT_ROOT)
            lines_before = content.count("\n") + 1
            lines_after = new_content.count("\n") + 1
            delta = lines_after - lines_before
            sign = "+" if delta >= 0 else ""
            return f"Patched {rel}: {lines_before} → {lines_after} lines ({sign}{delta})."
        except Exception as e:
            return f"Error writing '{raw_path}': {e}"

    async def _do_rename_chat(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        user_id = context.get("user_id")
        chat_id = context.get("chat_id")
        memory_url = context.get("memory_service_url")
        if not all([user_id, chat_id, memory_url, self.http_client]):
            return "Cannot rename chat: missing context."
        try:
            await self.http_client.put(
                f"{memory_url}/api/v1/chats/{user_id}/{chat_id}/name",
                json={"name": args["name"]},
            )
            return f"Chat renamed to: {args['name']}"
        except Exception as e:
            return f"Failed to rename chat: {e}"

    async def _do_save_to_memory(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        memory_url = context.get("memory_service_url")
        user_id = context.get("user_id", "orchestrator")
        if not all([memory_url, self.http_client]):
            return "Cannot save to memory: missing context."
        try:
            await self.http_client.post(
                f"{memory_url}/api/v1/memory",
                json={
                    "agent_id": user_id,
                    "content": args["text"],
                    "memory_type": "user_memory",
                    "importance": 0.9,
                    "metadata": {"source": "user_request"},
                },
            )
            return f"Saved to long-term memory: {args['text'][:80]}..."
        except Exception as e:
            return f"Failed to save to memory: {e}"

    async def _do_recall_from_memory(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        memory_url = context.get("memory_service_url")
        user_id = context.get("user_id", "orchestrator")
        if not all([memory_url, self.http_client]):
            return "Cannot search memory: missing context."
        query = args.get("query", "").strip()
        limit = int(args.get("limit", 5))
        if not query:
            return "Cannot search memory: query is required."
        try:
            resp = await self.http_client.post(
                f"{memory_url}/api/v1/memory/search",
                json={"query": query, "agent_id": user_id, "limit": limit},
            )
            if resp.status_code != 200:
                return f"Memory search failed: HTTP {resp.status_code}"
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return "Ничего не найдено в долгосрочной памяти."
            lines = []
            for i, r in enumerate(results, 1):
                content = r.get("content", "")
                score = r.get("score", 0)
                lines.append(f"{i}. [{score:.2f}] {content}")
            return "\n".join(lines)
        except Exception as e:
            return f"Failed to search memory: {e}"

    def _get_code_indexer(self, context: dict[str, Any]):
        """Lazy-load the CodeIndexer, reusing across calls."""
        from skills.code_indexer import CodeIndexer

        from shared.config import get_settings

        s = get_settings()
        uid = context.get("user_id")
        uid_str = uid if isinstance(uid, str) else ""
        prev = getattr(self, "_code_indexer_user_id", None)
        if not hasattr(self, "_code_indexer") or self._code_indexer is None or prev != uid_str:
            self._code_indexer = CodeIndexer(
                openrouter_api_key=context.get("openrouter_api_key") or s.openrouter_api_key or "",
                qdrant_host=s.qdrant_host,
                qdrant_port=s.qdrant_port,
                openrouter_user_end_id=uid_str or None,
            )
            self._code_indexer_user_id = uid_str
        return self._code_indexer

    async def _do_code_search(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        query = args.get("query", "").strip()
        if not query:
            return "Error: query is required for code_search."
        path_filter = args.get("path_filter") or None
        limit = min(int(args.get("limit", 5)), 10)
        try:
            indexer = self._get_code_indexer(context)
            results = await indexer.search(query=query, path_filter=path_filter, limit=limit)
            if not results:
                return "Ничего не найдено в индексе кодовой базы. Возможно, нужно запустить index_codebase."
            lines = []
            for r in results:
                lines.append(
                    f"[{r['score']:.2f}] {r['path']} ({r['lines']} lines)\n  {r['preview']}"
                )
            return "\n\n".join(lines)
        except Exception as e:
            return f"Code search failed: {e}"

    async def _do_index_codebase(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        raw_path = args.get("path")
        force = bool(args.get("force", False))
        try:
            indexer = self._get_code_indexer(context)
            from pathlib import Path as _Path

            path = _Path(raw_path).resolve() if raw_path else None
            stats = await indexer.index_path(path=path, force=force)
            return (
                f"✅ Индексация завершена: {stats['indexed']} файлов проиндексировано, "
                f"{stats['skipped']} пропущено, {stats['errors']} ошибок "
                f"(всего найдено: {stats['total_files']})"
            )
        except Exception as e:
            return f"Indexing failed: {e}"

    async def _do_delegate_to_agent(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        if not self._delegate_callback and not self._background_runner:
            return "Delegation is not available (sub-agents cannot delegate further)."

        agent_id = args.get("agent_id", "coder")
        task = args.get("task", "").strip()
        mode = args.get("mode", "agent")
        background = bool(args.get("background", False))

        if not task:
            return "Delegation failed: no task description provided."

        if background:
            if not self._background_runner:
                return "Background delegation not available."
            try:
                key = await self._background_runner(
                    agent_id=agent_id,
                    task=task,
                    context=context,
                    mode=mode,
                    notify_callback=None,
                )
                return (
                    f"✅ Задача передана агенту '{agent_id}' (фоновый режим, ключ: {key}). "
                    "Используй get_agent_result для получения результата когда агент завершит работу."
                )
            except Exception as e:
                return f"Ошибка запуска фоновой задачи для '{agent_id}': {type(e).__name__}: {e}"

        # Synchronous delegation
        if not self._delegate_callback:
            return "Synchronous delegation not available."
        try:
            result = await self._delegate_callback(
                agent_id=agent_id,
                task=task,
                context=context,
                mode=mode,
            )
            return f"[Agent {agent_id}]:\n{result}"
        except Exception as e:
            logger.error(f"Delegation to {agent_id} failed: {e}", exc_info=True)
            return f"Delegation to '{agent_id}' failed: {type(e).__name__}: {e}"

    def _do_get_agent_result(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        if not self._get_result_callback:
            return "get_agent_result not available."
        agent_id = args.get("agent_id", "coder")
        user_id = context.get("user_id", "unknown")
        res = self._get_result_callback(agent_id, user_id)
        if res is None:
            return f"Нет результатов от агента '{agent_id}'. Задача не была запущена или результат уже был прочитан."
        status = res.get("status", "unknown")
        if status == "running":
            return f"Агент '{agent_id}' всё ещё работает над задачей. Попробуй позже."
        result_text = res.get("result", "")
        ts = res.get("timestamp", "")
        return f"[Agent {agent_id}] ({status}, {ts}):\n{result_text}"

    def _do_cancel_agent_task(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        if not self._cancel_callback:
            return "cancel_agent_task not available."
        agent_id = args.get("agent_id", "coder")
        user_id = context.get("user_id", "unknown")
        return self._cancel_callback(agent_id, user_id)

    def _do_list_agent_tasks(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        if not self._list_tasks_callback:
            return "list_agent_tasks not available."
        user_id = context.get("user_id")
        limit = min(int(args.get("limit", 10)), 30)
        tasks = self._list_tasks_callback(user_id=user_id, limit=limit)
        if not tasks:
            return "Нет задач в реестре."
        STATUS_ICON = {
            "running": "⏳",
            "completed": "✅",
            "cancelled": "🚫",
            "error": "❌",
        }
        lines = [f"📋 Задачи ({len(tasks)}):"]
        for t in tasks:
            icon = STATUS_ICON.get(t.get("status", ""), "❓")
            bg = " [bg]" if t.get("background") else ""
            dur = f" ({t['duration_ms']}ms)" if t.get("duration_ms") else ""
            started = t.get("started_at", "")[:16].replace("T", " ")
            desc = t.get("description", "")[:80]
            lines.append(f"{icon} [{t.get('agent_id', '?')}]{bg} {started}{dur}\n   {desc}")
        return "\n".join(lines)

    def _do_read_agent_logs(self, args: dict[str, Any]) -> str:
        if not self._logger:
            return "Activity logging is not configured."
        norm = normalize_read_agent_logs_args(args)
        try:
            entries = self._logger.read_logs(
                date=norm["date"],
                start_date=norm["start_date"],
                end_date=norm["end_date"],
                tool_filter=norm["tool_filter"],
                limit=norm["limit"],
            )
        except ValueError as e:
            return (
                f"Некорректные параметры даты для read_agent_logs: {e}. "
                "Используйте YYYY-MM-DD, today или yesterday; для одного дня достаточно поля date."
            )
        # Build title
        if norm.get("date"):
            title = f"Логи за {norm['date']}"
        elif norm.get("start_date") or norm.get("end_date"):
            sd = norm.get("start_date") or "начало"
            ed = norm.get("end_date") or "сегодня"
            title = f"Логи {sd} — {ed}"
        else:
            title = "Логи за сегодня"
        if norm.get("tool_filter"):
            title += f" (фильтр: {norm['tool_filter']})"

        available = self._logger.list_log_dates()
        result = self._logger.format_for_chat(entries, title=title)
        if available:
            result += f"\n\n_Доступные даты: {', '.join(available[:10])}_"
        return result

    # ------------------------------------------------------------------
    # Schedule management (per-agent data/agents/<id>/schedules.yaml)
    # ------------------------------------------------------------------

    def _do_manage_todo(self, args: dict[str, Any]) -> str:
        """Read or update the project TODO.md."""
        action = args.get("action", "read")
        todo_path = _PROJECT_ROOT / "TODO.md"

        if action == "read":
            if not todo_path.exists():
                return "TODO.md не найден."
            return todo_path.read_text(encoding="utf-8")

        if action == "add":
            section = args.get("section", "Идеи").strip()
            item = (args.get("item") or "").strip()
            if not item:
                return "Error: поле 'item' обязательно для action='add'."
            if not todo_path.exists():
                return "TODO.md не найден."

            content = todo_path.read_text(encoding="utf-8")
            header = f"## {section}"
            idx = content.find(header)
            if idx == -1:
                return f"Error: секция '{section}' не найдена в TODO.md."

            # Find the end of the section header line, then insert after blank line
            after_header = content.find("\n", idx) + 1
            # Insert the new item as a bullet point after the header line
            new_item = f"- {item}\n"
            # Find insertion point: right after the header line (skip one blank line if present)
            insert_at = after_header
            if content[insert_at : insert_at + 1] == "\n":
                insert_at += 1  # skip blank line after header

            new_content = content[:insert_at] + new_item + content[insert_at:]
            todo_path.write_text(new_content, encoding="utf-8")
            return f"✅ Добавлено в раздел «{section}»: {item}"

        if action == "done":
            item_query = (args.get("item") or "").strip()
            if not item_query:
                return "Error: поле 'item' обязательно для action='done'."
            if not todo_path.exists():
                return "TODO.md не найден."

            content = todo_path.read_text(encoding="utf-8")
            lines = content.splitlines(keepends=True)

            # Find matching line(s) — case-insensitive substring match
            matched: list[int] = []
            for i, line in enumerate(lines):
                if item_query.lower() in line.lower() and line.strip().startswith("-"):
                    matched.append(i)

            if not matched:
                return f"Error: строка с текстом '{item_query}' не найдена в TODO.md."
            if len(matched) > 1:
                snippets = [lines[i].strip() for i in matched[:5]]
                return f"Найдено {len(matched)} строк — уточни запрос:\n" + "\n".join(
                    f"  {s}" for s in snippets
                )

            # Remove from current position
            done_line = lines.pop(matched[0]).rstrip("\n").rstrip()
            # Strip leading "- " to get clean text
            done_text = done_line.lstrip("- ").strip()

            # Find/create "## Выполнено" section
            done_header = "## Выполнено"
            new_content = "".join(lines)
            if done_header not in new_content:
                new_content = new_content.rstrip("\n") + f"\n\n{done_header}\n\n"

            # Append into Выполнено
            done_idx = new_content.find(done_header) + len(done_header)
            insert_done_at = new_content.find("\n", done_idx) + 1
            if new_content[insert_done_at : insert_done_at + 1] == "\n":
                insert_done_at += 1
            new_content = (
                new_content[:insert_done_at] + f"- ✅ {done_text}\n" + new_content[insert_done_at:]
            )
            todo_path.write_text(new_content, encoding="utf-8")
            return f"✅ Отмечено как выполнено: {done_text}"

        return f"Error: неизвестное действие '{action}'. Допустимые: read, add, done."

    def _schedule_tool_target_agent(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        explicit = (args.get("agent_id") or "").strip()
        if explicit:
            return explicit
        return (context.get("agent_id") or "balbes") or "balbes"

    def _do_manage_schedule(
        self, args: dict[str, Any], context: dict[str, Any] | None = None
    ) -> str:
        from shared.agent_schedules import (
            load_all_jobs_flat,
            load_yaml_for_agent,
            save_yaml_for_agent,
        )

        context = context or {}
        action = args.get("action", "").strip().lower()

        if action == "list":
            flat = load_all_jobs_flat()
            if not flat:
                return "Расписание пустое — нет файлов data/agents/*/schedules.yaml с задачами."
            lines = ["Запланированные задачи (по всем агентам):\n"]
            for aid, j in flat:
                status = "✅" if j.get("enabled", False) else "⏸"
                jid = j.get("id", "?")
                trigger = j.get("trigger", "?")
                prompt_preview = str(j.get("prompt", ""))[:80].replace("\n", " ")

                if trigger == "cron":
                    dow = j.get("day_of_week", "*")
                    h = j.get("hour", "*")
                    m = j.get("minute", 0)
                    try:
                        schedule_str = f"cron {dow} {h}:{int(m):02d}"
                    except (TypeError, ValueError):
                        schedule_str = f"cron {dow} {h}:{m}"
                elif trigger == "interval":
                    parts = []
                    if j.get("hours"):
                        parts.append(f"{j['hours']}ч")
                    if j.get("minutes"):
                        parts.append(f"{j['minutes']}мин")
                    schedule_str = f"каждые {' '.join(parts)}" if parts else "interval"
                else:
                    schedule_str = trigger

                lines.append(f"{status} [{aid}] {jid} — {schedule_str}\n   {prompt_preview}")
            return "\n".join(lines)

        target = self._schedule_tool_target_agent(args, context)

        if action == "add":
            job_id = (args.get("job_id") or "").strip()
            trigger = (args.get("trigger") or "").strip()
            prompt = (args.get("prompt") or "").strip()
            if not job_id:
                return "Ошибка: укажи job_id (уникальный идентификатор задачи внутри этого агента)."
            if not trigger:
                return "Ошибка: укажи trigger — 'cron' или 'interval'."
            if not prompt:
                return "Ошибка: укажи prompt — что агент должен сделать."

            data = load_yaml_for_agent(target)
            jobs: list = data.setdefault("jobs", [])

            if any(isinstance(j, dict) and j.get("id") == job_id for j in jobs):
                return (
                    f"Ошибка: у агента '{target}' уже есть задача id='{job_id}'. "
                    "Используй enable/disable или remove."
                )

            new_job: dict[str, Any] = {
                "id": job_id,
                "enabled": True,
                "trigger": trigger,
                "agent_id": target,
                "user_id": str(args.get("user_id", "0")),
                "prompt": prompt,
                "debug": bool(args.get("debug", False)),
            }
            if trigger == "cron":
                for field in ("year", "month", "day", "day_of_week", "hour", "minute", "second"):
                    if args.get(field) is not None:
                        new_job[field] = args[field]
                if "minute" not in new_job:
                    new_job["minute"] = 0
            elif trigger == "interval":
                for field in ("weeks", "days", "hours", "minutes", "seconds"):
                    if args.get(field) is not None:
                        new_job[field] = args[field]

            jobs.append(new_job)
            save_yaml_for_agent(target, data)
            return (
                f"Задача '{job_id}' добавлена для агента '{target}' и включена.\n"
                f"Файл: data/agents/.../schedules.yaml (каталог как у workspace этого агента).\n"
                "Планировщик применит изменения в течение ~30 секунд."
            )

        elif action == "remove":
            job_id = (args.get("job_id") or "").strip()
            if not job_id:
                return "Ошибка: укажи job_id задачи для удаления."
            data = load_yaml_for_agent(target)
            jobs = data.get("jobs") or []
            before = len(jobs)
            data["jobs"] = [j for j in jobs if isinstance(j, dict) and j.get("id") != job_id]
            if len(data["jobs"]) == before:
                return f"Задача '{job_id}' не найдена у агента '{target}'. См. list."
            save_yaml_for_agent(target, data)
            return (
                f"Задача '{job_id}' удалена (агент '{target}'). "
                "Планировщик обновится в течение ~30 секунд."
            )

        elif action in ("enable", "disable"):
            job_id = (args.get("job_id") or "").strip()
            if not job_id:
                return f"Ошибка: укажи job_id задачи для {action}."
            data = load_yaml_for_agent(target)
            jobs = data.get("jobs") or []
            found = False
            for j in jobs:
                if isinstance(j, dict) and j.get("id") == job_id:
                    j["enabled"] = action == "enable"
                    found = True
                    break
            if not found:
                return f"Задача '{job_id}' не найдена у агента '{target}'."
            save_yaml_for_agent(target, data)
            word = "включена" if action == "enable" else "выключена"
            return (
                f"Задача '{job_id}' ({target}) {word}. Планировщик обновится в течение ~30 секунд."
            )

        else:
            return f"Неизвестное действие '{action}'. Доступно: list, add, remove, enable, disable."

    async def _do_render_solution(self, args: dict[str, Any]) -> str:
        """Render full solution to fixed-size PNG page(s); queue for outbound delivery."""
        content = (args.get("content") or "").strip()
        if not content:
            return "Error: content is empty."
        from shared.solution_render import render_solution_pages

        try:
            pages = await asyncio.to_thread(render_solution_pages, content)
        except ValueError as e:
            return f"Ошибка рендера: {e}"
        except Exception as e:
            logger.warning("render_solution failed: %s", e, exc_info=True)
            return f"Ошибка рендера: {type(e).__name__}: {e}"

        if not pages:
            return "Рендер не дал изображений."

        n = len(pages)
        for i, png in enumerate(pages):
            cap = f"Решение (стр. {i + 1}/{n})" if n > 1 else "Решение"
            self._append_outbound_png(png, cap)
        return (
            f"Сформировано изображение решения: {n} стр. "
            f"({n} фиксированных страниц). Оно будет отправлено в чат отдельным сообщением."
        )

    def _append_outbound_png(self, png_bytes: bytes, caption: str) -> None:
        import base64

        self._outbound_attachments.append(
            {
                "kind": "image",
                "mime_type": "image/png",
                "base64": base64.b64encode(png_bytes).decode("ascii"),
                "caption": (caption or "")[:1024],
            }
        )

    # =========================================================================
    # Blogger tools implementation
    # =========================================================================

    async def _do_read_chat_history(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Read owner's chat history from memory service (all chats, all agents)."""
        from datetime import datetime

        from_ts_str = args.get("from_ts")
        limit = int(args.get("limit") or 60)
        memory_url = context.get("memory_service_url") or "http://localhost:8100"
        user_id = context.get("user_id", "")

        if not user_id:
            return "Ошибка: не задан user_id в контексте."

        from_ts = None
        if from_ts_str:
            try:
                from_ts = datetime.fromisoformat(from_ts_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        # Step 1: list all chats for this user
        try:
            chats_resp = await self.http_client.get(
                f"{memory_url}/api/v1/chats/{user_id}", timeout=10.0
            )
            chats = chats_resp.json().get("chats", []) if chats_resp.status_code == 200 else []
        except Exception as exc:
            return f"Ошибка при получении списка чатов: {exc}"

        if not chats:
            return "Нет чатов для этого пользователя."

        # Step 2: read history from each chat
        results: list[str] = []
        for chat in chats:
            chat_id = chat.get("chat_id") or chat.get("id", "")
            chat_name = chat.get("name", chat_id)
            if not chat_id:
                continue
            try:
                resp = await self.http_client.get(
                    f"{memory_url}/api/v1/history/{user_id}/{chat_id}",
                    params={"limit": limit},
                    timeout=15.0,
                )
                if resp.status_code != 200:
                    continue
                messages = resp.json().get("messages", [])
                for m in messages:
                    ts_str = m.get("timestamp") or m.get("created_at", "")
                    if from_ts and ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < from_ts:
                                continue
                        except ValueError:
                            pass
                    role = m.get("role", "")
                    content = (m.get("content") or "")[:400]
                    results.append(f"[{chat_name}|{role}] {content}")
            except Exception as exc:
                results.append(f"[{chat_name}] Error: {exc}")

        if not results:
            return "Нет сообщений за указанный период."
        return f"Найдено {len(results)} сообщений из {len(chats)} чатов:\n\n" + "\n".join(
            results[:80]
        )

    def _do_read_cursor_file(self, args: dict[str, Any]) -> str:
        """Read a Cursor AI Markdown export file."""
        path = (args.get("path") or "").strip()
        if not path:
            return "Error: укажи path к файлу."
        from pathlib import Path

        p = Path(path)
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        if not p.exists():
            return f"Файл не найден: {path}"
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return f"=== {path} ===\n{content[:8000]}"
        except Exception as exc:
            return f"Error reading {path}: {exc}"

    def _do_list_cursor_files(self, args: dict[str, Any]) -> str:
        """List Markdown files in cursor_chats directory."""
        from pathlib import Path

        directory = args.get("directory") or "data/cursor_chats"
        d = Path(directory)
        if not d.is_absolute():
            d = _PROJECT_ROOT / d
        if not d.exists():
            return f"Директория не найдена: {directory}"
        files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return "Нет файлов в директории."
        lines = [f"Найдено {len(files)} файлов:"]
        for f in files[:20]:
            size = f.stat().st_size
            rel = f.relative_to(_PROJECT_ROOT)
            lines.append(f"  {rel} ({size} bytes)")
        return "\n".join(lines)

    async def _do_read_business_chats(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Read anonymized business messages from PostgreSQL."""
        from_ts_str = args.get("from_ts")
        limit = int(args.get("limit") or 200)

        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        try:
            params: dict = {"limit": limit}
            if from_ts_str:
                params["from_ts"] = from_ts_str
            resp = await self.http_client.get(
                f"{blogger_url}/api/v1/business-messages",
                params=params,
                timeout=15.0,
            )
            if resp.status_code == 200:
                messages = resp.json().get("messages", [])
                if not messages:
                    return "Нет бизнес-сообщений за указанный период."
                lines = [f"Найдено {len(messages)} сообщений из бизнес-чатов:"]
                for m in messages[:100]:
                    sender = m.get("anon_sender") or ""
                    chat_name = m.get("chat_name", "?")
                    content = m.get("content", "")[:200]
                    prefix = f"[{chat_name}] {sender}: " if sender else f"[{chat_name}] "
                    lines.append(prefix + content)
                return "\n".join(lines)
            return f"Blogger service error: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Error reading business chats: {exc}"

    async def _do_get_business_summary(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Generate LLM summary of business chats via blogger service."""
        period_hours = int(args.get("period_hours") or 24)
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        try:
            resp = await self.http_client.post(
                f"{blogger_url}/api/v1/business-summary",
                json={"period_hours": period_hours, "chat_ids": args.get("chat_ids")},
                timeout=60.0,
            )
            if resp.status_code == 200:
                return resp.json().get("summary") or "Саммари не удалось сгенерировать."
            return f"Blogger service error: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Error getting business summary: {exc}"

    async def _do_create_draft(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Create a blog post draft and send for approval via blogger service."""
        content_ru = (args.get("content_ru") or "").strip()
        content_en = (args.get("content_en") or "").strip()
        if not content_ru:
            return "Error: content_ru is required."
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        payload = {
            "content_ru": content_ru,
            "content_en": content_en,
            "title": args.get("title") or "",
            "post_type": args.get("post_type") or "agent",
            "source_refs": args.get("source_refs") or [],
            "notes": args.get("notes") or "",
        }
        try:
            resp = await self.http_client.post(
                f"{blogger_url}/api/v1/posts/create",
                json=payload,
                timeout=30.0,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                post_id = data.get("post_id", "?")
                return f"✅ Черновик создан (ID: {post_id}). Отправлен владельцу на согласование."
            return f"Blogger service error: HTTP {resp.status_code} — {resp.text[:200]}"
        except Exception as exc:
            return f"Error creating draft: {exc}"

    async def _do_list_drafts(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """List blog post drafts."""
        status = args.get("status")
        limit = int(args.get("limit") or 20)
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        params: dict = {"limit": limit}
        if status:
            params["status"] = status
        try:
            resp = await self.http_client.get(
                f"{blogger_url}/api/v1/posts/",
                params=params,
                timeout=15.0,
            )
            if resp.status_code == 200:
                posts = resp.json().get("posts", [])
                if not posts:
                    return "Нет черновиков."
                lines = [f"Найдено {len(posts)} постов:"]
                for p in posts:
                    title = p.get("title") or "(без заголовка)"
                    st = p.get("status", "?")
                    created = p.get("created_at", "")[:10]
                    lines.append(f"  [{st}] {title} ({created}) — ID: {p.get('id', '?')}")
                return "\n".join(lines)
            return f"Error: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Error listing drafts: {exc}"

    async def _do_get_published_posts(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Get recent published posts for context."""
        limit = int(args.get("limit") or 10)
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        try:
            resp = await self.http_client.get(
                f"{blogger_url}/api/v1/posts/",
                params={"status": "published", "limit": limit},
                timeout=15.0,
            )
            if resp.status_code == 200:
                posts = resp.json().get("posts", [])
                if not posts:
                    return "Ещё нет опубликованных постов."
                lines = [f"Последние {len(posts)} опубликованных постов:"]
                for p in posts:
                    title = p.get("title") or "(без заголовка)"
                    pub = p.get("published_at", "")[:10]
                    lines.append(f"  {title} ({pub})")
                return "\n".join(lines)
            return f"Error: HTTP {resp.status_code}"
        except Exception as exc:
            return f"Error: {exc}"

    async def _do_schedule_post(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Schedule a post for publishing."""
        post_id = (args.get("post_id") or "").strip()
        publish_at = (args.get("publish_at") or "").strip()
        if not post_id or not publish_at:
            return "Error: укажи post_id и publish_at."
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        try:
            resp = await self.http_client.post(
                f"{blogger_url}/api/v1/posts/{post_id}/schedule",
                json={"publish_at": publish_at},
                timeout=15.0,
            )
            if resp.status_code == 200:
                return f"✅ Пост {post_id} запланирован на {publish_at}."
            return f"Error: HTTP {resp.status_code} — {resp.text[:200]}"
        except Exception as exc:
            return f"Error: {exc}"

    async def _do_set_business_role(self, args: dict[str, Any], context: dict[str, Any]) -> str:
        """Set anonymization role mapping for a business chat."""
        group_id = (args.get("group_id") or "").strip()
        user_id = (args.get("user_id") or "").strip()
        role = (args.get("role") or "").strip()
        if not group_id or not user_id or not role:
            return "Error: укажи group_id, user_id и role."
        blogger_url = f"http://localhost:{context.get('blogger_service_port', 8105)}"
        try:
            resp = await self.http_client.post(
                f"{blogger_url}/api/v1/business-chats/set-role",
                json={"group_id": group_id, "user_id": user_id, "role": role},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return f"✅ Роль установлена: user {user_id} → '{role}' в группе {group_id}."
            return f"Error: HTTP {resp.status_code} — {resp.text[:200]}"
        except Exception as exc:
            return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Input / result summary helpers (for compact log lines)
# ---------------------------------------------------------------------------


def _summarize_input(tool_name: str, args: dict) -> str:
    if tool_name == "web_search":
        q = args.get("query", "")
        n = args.get("max_results", 5)
        p = args.get("provider", "")
        provider_str = f" via={p}" if p else ""
        return f"query='{q[:60]}' max={n}{provider_str}"
    if tool_name == "fetch_url":
        return f"url='{args.get('url', '')[:80]}'"
    if tool_name == "execute_command":
        return f"cmd='{args.get('command', '')[:80]}'"
    if tool_name == "workspace_read":
        return f"file='{args.get('filename', '')}'"
    if tool_name == "workspace_write":
        content_len = len(args.get("content", ""))
        return f"file='{args.get('filename', '')}' len={content_len}"
    if tool_name == "rename_chat":
        return f"name='{args.get('name', '')[:40]}'"
    if tool_name == "save_to_memory":
        return f"text='{args.get('text', '')[:60]}'"
    if tool_name == "delegate_to_agent":
        agent = args.get("agent_id", "?")
        task_preview = args.get("task", "")[:60]
        mode = args.get("mode", "agent")
        bg = " [bg]" if args.get("background") else ""
        return f"agent='{agent}' mode='{mode}'{bg} task='{task_preview}'"
    if tool_name == "get_agent_result":
        return f"agent='{args.get('agent_id', '?')}'"
    if tool_name == "cancel_agent_task":
        return f"agent='{args.get('agent_id', '?')}'"
    if tool_name == "list_agent_tasks":
        return f"limit={args.get('limit', 10)}"
    if tool_name == "manage_schedule":
        action = args.get("action", "?")
        jid = args.get("job_id", "")
        aid = args.get("agent_id", "")
        return (
            f"action={action}"
            + (f" agent_id='{aid}'" if aid else "")
            + (f" job_id='{jid}'" if jid else "")
        )
    if tool_name == "render_solution":
        return f"content_len={len(args.get('content') or '')}"
    return str(args)[:80]


def _summarize_result(result: str | None) -> str:
    result = (result or "").strip()
    if not result:
        return "(empty)"
    # First line only, truncated
    first_line = result.split("\n")[0]
    if len(first_line) > 80:
        return first_line[:77] + "..."
    return first_line
