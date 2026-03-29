"""
Tool registry for the Orchestrator Agent.

Defines OpenAI function-calling compatible tool schemas and
dispatches tool calls to the appropriate skill implementations.
Every tool call is automatically logged via AgentActivityLogger.
"""

import logging
import time
from typing import Any

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
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


# Minimal tool set for heartbeat runs — workspace_read only.
# Keeps token usage low so the free model doesn't hit rate limits.
HEARTBEAT_TOOLS: list[dict[str, Any]] = [
    t for t in AVAILABLE_TOOLS if t["function"]["name"] == "workspace_read"
]


def get_tools_for_mode(mode: str) -> list[dict[str, Any]]:
    """
    Return the list of available tool schemas for the given execution mode.

    - "agent" (default): all tools enabled
    - "ask": read-only — execute_command and workspace_write are removed.
      The agent can search, read files and workspace, but cannot run server
      commands or modify files.
    """
    if mode == "ask":
        blocked = {"execute_command", "workspace_write"}
        return [t for t in AVAILABLE_TOOLS if t["function"]["name"] not in blocked]
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
    ):
        self.workspace = workspace
        self.http_client = http_client
        self.providers_config = providers_config
        self._logger = activity_logger  # AgentActivityLogger | None
        self._debug_collector: list[dict] | None = None  # set per-task when debug=True

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

        # Emit "tool started" debug event
        if self._debug_collector is not None:
            self._debug_collector.append(
                {
                    "type": "tool_start",
                    "name": tool_name,
                    "summary": _summarize_input(tool_name, tool_args),
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

            elif tool_name == "read_agent_logs":
                result = self._do_read_agent_logs(tool_args)

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
        results = await self._web_search.search(
            query=args["query"],
            max_results=args.get("max_results", 5),
        )
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. **{r['title']}**\n   {r['url']}\n   {r['snippet']}")
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
        return f"query='{q[:60]}' max={n}"
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
