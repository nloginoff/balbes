"""
Tool registry for the Orchestrator Agent.

Defines OpenAI function-calling compatible tool schemas and
dispatches tool calls to the appropriate skill implementations.
Every tool call is automatically logged via AgentActivityLogger.
"""

import logging
import time
from pathlib import Path
from typing import Any

# Project root — two levels up from services/orchestrator/
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
# Maximum chars returned by file_read (prevents huge files swamping the context)
_FILE_READ_MAX_CHARS = 30_000

logger = logging.getLogger("orchestrator.tools")

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
                "Available files: AGENTS.md, SOUL.md, USER.md, MEMORY.md, TOOLS.md, IDENTITY.md"
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
                "Writable files: AGENTS.md, SOUL.md, USER.md, MEMORY.md, IDENTITY.md"
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
            "name": "delegate_to_agent",
            "description": (
                "Delegate a task to a specialist sub-agent and return their response. "
                "Use the 'coder' agent for: writing / editing / debugging code, "
                "creating project files, running scripts or tests, git operations "
                "(add, commit, push, pull), and any development work. "
                "Provide a complete, self-contained task description — the sub-agent "
                "has NO access to the current conversation history, so include all "
                "necessary context: file paths, tech stack, what to do and why."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Target agent. Currently available: 'coder'",
                        "enum": ["coder"],
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
                            "Show only calls to this tool: web_search | fetch_url | "
                            "execute_command | workspace_read | workspace_write | "
                            "rename_chat | save_to_memory"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return (default 50, max 200).",
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
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


# Minimal tool set for heartbeat runs — workspace_read only.
# Keeps token usage low so the free model doesn't hit rate limits.
HEARTBEAT_TOOLS: list[dict[str, Any]] = [
    t for t in AVAILABLE_TOOLS if t["function"]["name"] == "workspace_read"
]

# Tool set for delegated (sub-agent) runs — everything except delegate_to_agent.
# Prevents infinite delegation loops: a sub-agent cannot re-delegate.
AGENT_TOOLS: list[dict[str, Any]] = [
    t for t in AVAILABLE_TOOLS if t["function"]["name"] != "delegate_to_agent"
]


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
        content = self.workspace.read_file(args["filename"])
        if not content:
            return f"File '{args['filename']}' not found or empty."
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
        entries = self._logger.read_logs(
            date=args.get("date"),
            start_date=args.get("start_date"),
            end_date=args.get("end_date"),
            tool_filter=args.get("tool_filter"),
            limit=min(int(args.get("limit", 50)), 200),
        )
        # Build title
        if args.get("date"):
            title = f"Логи за {args['date']}"
        elif args.get("start_date") or args.get("end_date"):
            sd = args.get("start_date", "начало")
            ed = args.get("end_date", "сегодня")
            title = f"Логи {sd} — {ed}"
        else:
            title = "Логи за сегодня"
        if args.get("tool_filter"):
            title += f" (фильтр: {args['tool_filter']})"

        available = self._logger.list_log_dates()
        result = self._logger.format_for_chat(entries, title=title)
        if available:
            result += f"\n\n_Доступные даты: {', '.join(available[:10])}_"
        return result


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
    return str(args)[:80]


def _summarize_result(result: str) -> str:
    result = result.strip()
    if not result:
        return "(empty)"
    # First line only, truncated
    first_line = result.split("\n")[0]
    if len(first_line) > 80:
        return first_line[:77] + "..."
    return first_line
