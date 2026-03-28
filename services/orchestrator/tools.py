"""
Tool registry for the Orchestrator Agent.

Defines OpenAI function-calling compatible tool schemas and
dispatches tool calls to the appropriate skill implementations.
"""

import logging
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
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------


class ToolDispatcher:
    """
    Dispatches tool call requests to the appropriate skill implementation.
    Instantiated once per agent instance.
    """

    def __init__(
        self,
        workspace=None,
        http_client=None,
        providers_config=None,
    ):
        self.workspace = workspace
        self.http_client = http_client
        self.providers_config = providers_config

        # Lazy-loaded skill instances
        self._web_search = None
        self._server_commands = None

    async def dispatch(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> str:
        """
        Execute a tool and return its result as a string.
        context may contain: user_id, chat_id, memory_service_url, openrouter_api_key
        """
        context = context or {}

        try:
            if tool_name == "web_search":
                return await self._do_web_search(tool_args)

            if tool_name == "fetch_url":
                return await self._do_fetch_url(tool_args)

            if tool_name == "execute_command":
                return await self._do_execute_command(tool_args, context)

            if tool_name == "workspace_read":
                return self._do_workspace_read(tool_args)

            if tool_name == "workspace_write":
                return self._do_workspace_write(tool_args)

            if tool_name == "rename_chat":
                return await self._do_rename_chat(tool_args, context)

            if tool_name == "save_to_memory":
                return await self._do_save_to_memory(tool_args, context)

            return f"Unknown tool: {tool_name}"

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"

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
