"""
Orchestrator Agent — главный координирующий агент системы.

Возможности:
- Мультичат: каждый чат имеет свою историю и модель (через Redis)
- Workspace: системный промпт загружается из MD-файлов (OpenClaw-style)
- Tool calls: web_search, fetch_url, execute_command, workspace_read/write,
              rename_chat, save_to_memory
- Адаптивная обрезка истории под контекстное окно выбранной модели
- Fallback по цепочке моделей при 429/5xx
"""

import asyncio
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import redis.asyncio as aioredis
import tiktoken
from agent_logger import AgentActivityLogger
from tools import AGENT_TOOLS, AVAILABLE_TOOLS, HEARTBEAT_TOOLS, ToolDispatcher, get_tools_for_mode
from workspace import AgentWorkspace


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM API is unreachable or returns a non-retryable error."""


class _LiveDebugList(list):
    """A list that mirrors every append() to a secondary live-streaming buffer.

    Used to give the Telegram bot live access to debug events while a foreground
    task is still running — without disrupting the final debug_events collection.
    """

    def __init__(self, live_buf: list) -> None:
        super().__init__()
        self._live: list = live_buf

    def append(self, event: Any) -> None:  # type: ignore[override]
        super().append(event)
        self._live.append(event)


from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.agent")

MAX_TOOL_CALL_ROUNDS = 15  # prevent infinite tool-call loops

# Redis key helpers for persisted task registry
_REDIS_TASK_PREFIX = "balbes:task:"
_REDIS_TASK_INDEX = "balbes:task_ids"
_REDIS_TASK_TTL = 86400  # 24 h


def _count_tokens(text: str) -> int:
    """Approximate token count using cl100k_base encoding."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


from shared.utils import get_providers_config  # noqa: E402  (after local imports)


def get_context_window(model_id: str) -> int:
    """Return context window size for a model from providers.yaml."""
    cfg = get_providers_config()
    for m in cfg.get("active_models", []):
        if m.get("id") == model_id:
            return m.get("context_window", 8192)
    # Fallback defaults by name hints
    if "claude" in model_id:
        return 200000
    if "gpt-4" in model_id:
        return 128000
    return 8192


def build_messages_for_llm(
    system_prompt: str,
    history: list[dict[str, Any]],
    user_input: str,
    model_id: str,
    history_summary: str | None = None,
) -> list[dict[str, Any]]:
    """
    Build the messages array for LLM, adaptively trimming history to fit context window.
    Preserves the most recent messages.

    If history_summary is provided (a pre-built LLM summary of older messages), it is
    injected as a system message right after the main system prompt, replacing the
    trimmed portion of history.
    """
    cfg = get_providers_config().get("memory", {})
    trim_threshold = cfg.get("trim_threshold", 0.85)
    max_msgs = cfg.get("max_messages_in_context", 50)
    reserve = cfg.get("system_prompt_reserve", 500)

    context_window = get_context_window(model_id)
    used = _count_tokens(system_prompt) + _count_tokens(user_input) + reserve
    if history_summary:
        used += _count_tokens(history_summary) + 50  # reserve for summary message wrapper
    available = int(context_window * trim_threshold) - used

    # Take messages from the end, fitting into available tokens
    trimmed: list[dict[str, Any]] = []
    for msg in reversed(history[-max_msgs:]):
        msg_tokens = _count_tokens(msg.get("content", ""))
        if available - msg_tokens < 0:
            break
        trimmed.insert(0, msg)
        available -= msg_tokens

    messages = [{"role": "system", "content": system_prompt}]
    if history_summary:
        messages.append(
            {
                "role": "system",
                "content": f"Краткое содержание предыдущего диалога:\n{history_summary}",
            }
        )
    for m in trimmed:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages


def _would_trim_history(
    system_prompt: str,
    history: list[dict[str, Any]],
    user_input: str,
    model_id: str,
) -> bool:
    """Return True if build_messages_for_llm would drop any history messages."""
    cfg = get_providers_config().get("memory", {})
    trim_threshold = cfg.get("trim_threshold", 0.85)
    max_msgs = cfg.get("max_messages_in_context", 50)
    reserve = cfg.get("system_prompt_reserve", 500)

    context_window = get_context_window(model_id)
    used = _count_tokens(system_prompt) + _count_tokens(user_input) + reserve
    available = int(context_window * trim_threshold) - used

    trimmed_count = 0
    for msg in reversed(history[-max_msgs:]):
        msg_tokens = _count_tokens(msg.get("content", ""))
        if available - msg_tokens < 0:
            break
        trimmed_count += 1
        available -= msg_tokens

    return trimmed_count < min(len(history), max_msgs)


# Matches any namespaced XML wrapper: <prefix:anytag>...</prefix:anytag>
# Uses backreference so the closing tag must match the opening tag.
# Handles both <model:tool_call> and <model:toolcall> variants (namespaced, XML invoke format).
_XML_TOOL_CALL_RE = re.compile(
    r"<([a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+)>(.*?)</\1>",
    re.DOTALL,
)

# Handles plain <tool_call>{...}</tool_call> with JSON content.
# Used by many OSS models (Qwen, Llama-instruct, arcee-ai, trinity-mini, etc.).
_PLAIN_TOOL_CALL_RE = re.compile(
    r"<tool_calls?>\s*(\{.*?\})\s*</tool_calls?>",
    re.DOTALL,
)

# Canonical tool name lookup by normalized (no-underscore lowercase) key.
# Some models (minimax) strip underscores from tool names in XML.
_TOOL_NAME_CANONICAL: dict[str, str] = {
    "websearch": "web_search",
    "fetchurl": "fetch_url",
    "executecommand": "execute_command",
    "workspaceread": "workspace_read",
    "workspacewrite": "workspace_write",
    "renamechat": "rename_chat",
    "savetomemory": "save_to_memory",
    "delegatetoagent": "delegate_to_agent",
    "getagentresult": "get_agent_result",
    "cancelagenttask": "cancel_agent_task",
    "listagentasks": "list_agent_tasks",
    "listagettasks": "list_agent_tasks",
    "listmakenttasks": "list_agent_tasks",
    "readagentlogs": "read_agent_logs",
    "fileread": "file_read",
    "filewrite": "file_write",
    "manageschedule": "manage_schedule",
    "scheduletask": "manage_schedule",
}


def _normalize_tool_name(name: str) -> str:
    """Return canonical tool name; corrects de-underscored variants from some LLMs."""
    return _TOOL_NAME_CANONICAL.get(name.replace("_", "").lower(), name)


def _make_tool_call(raw_name: str, args: Any) -> dict:
    """Build a single OpenAI-style tool_call dict from a raw name and args."""
    name = _normalize_tool_name(raw_name)
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
    return {
        "id": f"call_{uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args or {}, ensure_ascii=False),
        },
    }


def _parse_embedded_tool_calls(content: str) -> tuple[list[dict], bool]:
    """
    Parse non-standard tool calls that some models embed in message text.

    Supported formats:
      1. Namespaced XML invoke:
           <model:tool_call><invoke name="fn"><parameter name="k">v</parameter></invoke></model:tool_call>
      2. JSON inside <tool_call> tags (Qwen, Llama, arcee, etc.):
           <tool_call>{"name": "workspace_read", "arguments": {"filename": "HEARTBEAT.md"}}</tool_call>
      3. Bare JSON — entire message content is a single tool-call JSON object:
           {"name": "workspace_read", "arguments": {"filename": "HEARTBEAT.md"}}
           {"type": "function", "name": "read_agent_logs", "parameters": {...}}

    Returns (list_of_tool_calls, content_consumed_entirely).
    content_consumed_entirely is True for format 3 so the caller can blank content_text.
    """
    tool_calls: list[dict] = []

    # --- Format 1: namespaced XML invoke (minimax, etc.) ---
    for _tag, block in _XML_TOOL_CALL_RE.findall(content):
        try:
            root = ET.fromstring(f"<root>{block}</root>")
        except ET.ParseError:
            continue
        for invoke in root.findall("invoke"):
            raw_name = invoke.get("name", "").strip()
            if not raw_name:
                continue
            params: dict[str, Any] = {
                _normalize_tool_name(p.get("name", "").strip()): (p.text or "").strip()
                for p in invoke.findall("parameter")
                if p.get("name", "").strip()
            }
            tool_calls.append(_make_tool_call(raw_name, params))

    # --- Format 2: <tool_call>{json}</tool_call> ---
    for json_str in _PLAIN_TOOL_CALL_RE.findall(content):
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue
        raw_name = data.get("name", "").strip()
        if raw_name:
            args = data.get("arguments", data.get("parameters", {}))
            tool_calls.append(_make_tool_call(raw_name, args))

    if tool_calls:
        return tool_calls, False

    # --- Format 3: bare JSON object as entire message (no wrapper tags) ---
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            raw_name = data.get("name", "").strip()
            if raw_name:
                args = data.get("arguments", data.get("parameters", {}))
                return [_make_tool_call(raw_name, args)], True
        except json.JSONDecodeError:
            pass

    return [], False


# Keep old name as alias so existing call-sites don't break.
def _parse_xml_tool_calls(content: str) -> list[dict] | None:
    calls, _ = _parse_embedded_tool_calls(content)
    return calls or None


class OrchestratorAgent:
    """
    Orchestrator Agent — coordinates the whole Balbes system.

    Key features:
    - Per-chat history and model selection
    - Workspace-based system prompt (MD files)
    - LLM tool calls with multi-round execution loop
    - Adaptive history trimming
    - Model fallback chain
    """

    def __init__(self):
        self.agent_id = "orchestrator"
        self.memory_service_url = f"http://localhost:{settings.memory_service_port}"
        self.skills_registry_url = f"http://localhost:{settings.skills_registry_port}"
        self.http_client: httpx.AsyncClient | None = None
        self._redis: aioredis.Redis | None = None

        # Workspace cache: agent_id → AgentWorkspace (lazy-loaded per agent)
        self._workspaces: dict[str, AgentWorkspace] = {}

        # Activity logger cache: agent_id → AgentActivityLogger
        self._loggers: dict[str, AgentActivityLogger] = {}

        # Per-user cancellation flags (set by /stop, cleared at task start)
        self._cancel_flags: dict[str, bool] = {}

        # Background task registry: key = f"{user_id}:{agent_id}"
        self._background_tasks: dict[str, asyncio.Task] = {}
        # Completed background task results waiting to be read
        self._background_results: dict[str, dict[str, Any]] = {}

        # Global task registry — metadata for all tasks (foreground + background)
        # key = task_id; capped at _TASK_REGISTRY_MAX per user to avoid memory growth
        self._task_registry: dict[str, dict[str, Any]] = {}
        self._TASK_REGISTRY_MAX = 50  # total entries kept

        # Live debug event buffer for background tasks: key = f"{user_id}:{agent_id}"
        # Events are appended by the sub-agent's _run_llm_with_tools; drained by poll_bg_task.
        self._bg_debug_buffer: dict[str, list[dict[str, Any]]] = {}

        # Live debug buffer for FOREGROUND tasks: key = f"{user_id}:{agent_id}:fg"
        # Filled via _LiveDebugList; drained by drain_fg_debug().
        # Allows the Telegram bot to stream trace events while the task is still running.
        self._fg_debug_buffer: dict[str, list[dict[str, Any]]] = {}

        # Tool dispatcher
        self.tool_dispatcher: ToolDispatcher | None = None

    def _get_workspace(self, agent_id: str) -> AgentWorkspace:
        """Return cached workspace for agent, loading on first access."""
        if agent_id not in self._workspaces:
            ws = AgentWorkspace(agent_id)
            try:
                ws.load()
                logger.info(f"Workspace loaded for agent '{agent_id}'")
            except Exception as e:
                logger.warning(f"Workspace load failed for '{agent_id}' (using defaults): {e}")
            self._workspaces[agent_id] = ws
        return self._workspaces[agent_id]

    def _get_activity_logger(self, agent_id: str) -> AgentActivityLogger:
        """Return cached activity logger for agent, creating on first access."""
        if agent_id not in self._loggers:
            self._loggers[agent_id] = AgentActivityLogger(agent_id)
        return self._loggers[agent_id]

    def cancel_task(self, user_id: str) -> None:
        """Signal that the current task for user_id should be cancelled."""
        self._cancel_flags[user_id] = True
        logger.info(f"Cancel flag set for user {user_id}")

    def _is_cancelled(self, user_id: str) -> bool:
        return self._cancel_flags.get(user_id, False)

    def _clear_cancel(self, user_id: str) -> None:
        self._cancel_flags.pop(user_id, None)

    async def connect(self) -> None:
        """Initialize HTTP client, Redis, load default workspace, warm up tools."""
        self.http_client = httpx.AsyncClient(timeout=60.0)

        # Connect to Redis and restore persisted task registry
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=3,
            )
            await self._redis.ping()
            await self._restore_task_registry()
            logger.info("Redis connected — task registry restored")
        except Exception as e:
            logger.warning(f"Redis unavailable, task registry will be in-memory only: {e}")
            self._redis = None

        # Eagerly load the default orchestrator workspace
        ws = self._get_workspace(self.agent_id)
        activity_log = self._get_activity_logger(self.agent_id)

        # Initialize tool dispatcher with default workspace and logger
        self.tool_dispatcher = ToolDispatcher(
            workspace=ws,
            http_client=self.http_client,
            providers_config=get_providers_config(),
            activity_logger=activity_log,
            delegate_callback=self._delegate_task,
            background_runner=self.run_agent_background,
            get_result_callback=self.get_background_result,
            cancel_callback=self.cancel_agent_background_tasks,
            list_tasks_callback=self.list_tasks,
        )

        logger.info("Orchestrator Agent initialized")

    async def close(self) -> None:
        if self.http_client:
            await self.http_client.aclose()
        if self._redis:
            await self._redis.aclose()
        logger.info("Orchestrator Agent closed")

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    async def execute_task(
        self,
        description: str,
        user_id: str,
        chat_id: str | None = None,
        agent_id: str | None = None,
        model_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a user task within a specific chat context.

        Args:
            description: User's message / task
            user_id: Telegram user_id (string)
            chat_id: Chat session ID. If None, uses/creates default chat.
            agent_id: Agent to use (orchestrator | coder | ...). Defaults to 'orchestrator'.
            model_id: Override model for this task. If None, uses the chat's configured model.
                      Pass explicitly for heartbeat (free model) or tests.
            context: Extra context dict (unused externally, kept for compat)
        """
        task_id = str(uuid4())
        start_time = datetime.now(timezone.utc)
        effective_agent_id = agent_id or self.agent_id

        # Clear any previous cancel flag for this user at the start of each new task
        self._clear_cancel(user_id)

        # Reset per-tool call counters for rate limiting
        if self.tool_dispatcher:
            self.tool_dispatcher.reset_call_counts()

        ctx = context or {}
        source_early: str = ctx.get("source", "user")
        if source_early != "heartbeat":
            self._register_task(
                task_id=task_id,
                agent_id=effective_agent_id,
                user_id=user_id,
                description=description,
                source=source_early,
                is_background=False,
            )

        try:
            ctx = context or {}
            source: str = ctx.get("source", "user")
            is_heartbeat: bool = source == "heartbeat"

            # Resolve chat_id
            if chat_id is None:
                chat_id = await self._get_or_create_chat(user_id)

            logger.info(
                f"[{task_id}] user={user_id} chat={chat_id} agent={effective_agent_id}"
                f"{' [heartbeat]' if is_heartbeat else ''}: {description[:60]}..."
            )

            # Heartbeat: skip full chat history to keep token count minimal.
            # It only needs its workspace files (HEARTBEAT.md, MEMORY.md).
            history = [] if is_heartbeat else await self._get_chat_history(user_id, chat_id)

            # Model: use the explicit override if provided, otherwise the chat's configured model
            if model_id is None:
                model_id = await self._get_model_for_chat(user_id, chat_id)

            # Load workspace and activity logger for the selected agent (cached)
            workspace = self._get_workspace(effective_agent_id)
            system_prompt = workspace.config.system_prompt
            activity_log = self._get_activity_logger(effective_agent_id)

            # Swap dispatcher's workspace and logger to match the active agent
            if self.tool_dispatcher:
                self.tool_dispatcher.workspace = workspace
                self.tool_dispatcher._logger = activity_log

            # Optionally summarize old history if context window would be exceeded
            history_summary: str | None = None
            if not is_heartbeat:
                history_summary = await self._maybe_summarize_history(
                    user_id=user_id,
                    chat_id=chat_id,
                    history=history,
                    system_prompt=system_prompt,
                    user_input=description,
                    model_id=model_id,
                )

            # Build messages array (with adaptive trim)
            messages = build_messages_for_llm(
                system_prompt=system_prompt,
                history=history,
                user_input=description,
                model_id=model_id,
                history_summary=history_summary,
            )

            # Save user message to history (skip for heartbeat — don't pollute user history)
            if not is_heartbeat:
                await self._save_to_history(user_id, chat_id, "user", description)

            debug: bool = ctx.get("debug", False)
            mode: str = ctx.get("mode", "agent")

            # For heartbeat: read inter-round delay from config (guards against rate limits)
            between_rounds_delay: float = 0.0
            if is_heartbeat:
                hb_cfg = get_providers_config().get("heartbeat", {})
                between_rounds_delay = float(hb_cfg.get("request_delay_seconds", 0))

            # Attach debug collector to tool dispatcher for this task.
            # Always populate _fg_debug_buffer for foreground tasks (not heartbeat) so:
            #   debug=True  → bot streams full debug trace
            #   debug=False → bot streams compact progress status (tool names only)
            fg_debug_key = f"{user_id}:{effective_agent_id}:fg"
            if not is_heartbeat:
                live_buf: list[dict[str, Any]] = []
                self._fg_debug_buffer[fg_debug_key] = live_buf
                debug_events: list[dict] = _LiveDebugList(live_buf)
            else:
                debug_events = []
            if self.tool_dispatcher:
                self.tool_dispatcher.set_debug_collector(debug_events if not is_heartbeat else None)

            # Snapshot background task keys before LLM run to detect new delegations
            _bg_keys_before = set(self._background_tasks.keys())

            # Run LLM with tool call loop
            response_text, model_used, token_usage = await self._run_llm_with_tools(
                messages=messages,
                model_id=model_id,
                user_id=user_id,
                chat_id=chat_id,
                task_id=task_id,
                source=source,
                agent_id=effective_agent_id,
                debug_events=debug_events if debug else None,
                mode=mode,
                # Heartbeat uses only workspace_read — all other tools add tokens with no benefit
                override_tools=HEARTBEAT_TOOLS if is_heartbeat else None,
                between_rounds_delay=between_rounds_delay,
            )

            # Detect newly started background tasks during this execution
            _bg_keys_after = set(self._background_tasks.keys())
            _new_bg_keys = _bg_keys_after - _bg_keys_before
            background_tasks_started = [
                {"agent_id": k.split(":", 1)[1], "key": k}
                for k in _new_bg_keys
                if ":" in k and k.split(":", 1)[0] == user_id
            ]

            # Detach debug collector and clean up fg live buffer
            if self.tool_dispatcher:
                self.tool_dispatcher.set_debug_collector(None)
            self._fg_debug_buffer.pop(fg_debug_key, None)

            # Save assistant response to history (skip for heartbeat)
            if not is_heartbeat:
                await self._save_to_history(user_id, chat_id, "assistant", response_text)

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.info(f"[{task_id}] Done in {duration_ms:.0f}ms using {model_used}")
            self._finish_task(task_id, "completed")

            # Fire-and-forget token usage recording (non-blocking)
            if token_usage.get("total_tokens", 0) > 0:
                asyncio.create_task(
                    self._record_token_usage(
                        agent_id=effective_agent_id,
                        model=model_used,
                        usage=token_usage,
                        task_id=task_id,
                    )
                )

            result: dict[str, Any] = {
                "task_id": task_id,
                "status": "success",
                "result": {"output": response_text},
                "skill_used": "direct_llm_chat",
                "model_used": model_used,
                "chat_id": chat_id,
                "duration_ms": duration_ms,
                "token_usage": token_usage,
            }
            if background_tasks_started:
                result["background_tasks_started"] = background_tasks_started
            if debug and debug_events:
                result["debug_events"] = debug_events
            return result

        except LLMUnavailableError as e:
            logger.warning(f"[{task_id}] LLM unavailable: {e}")
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self._fg_debug_buffer.pop(f"{user_id}:{effective_agent_id}:fg", None)
            self._finish_task(task_id, "error")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"❌ Модель недоступна\n`{e}`",
                "chat_id": chat_id,
                "duration_ms": duration_ms,
            }

        except Exception as e:
            logger.error(f"[{task_id}] Task failed: {e}", exc_info=True)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            err_detail = str(e) or "(нет описания)"
            self._fg_debug_buffer.pop(f"{user_id}:{effective_agent_id}:fg", None)
            self._finish_task(task_id, "error")
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"{type(e).__name__}: {err_detail}",
                "chat_id": chat_id,
                "duration_ms": duration_ms,
            }

    # -------------------------------------------------------------------------
    # LLM call with tool call loop
    # -------------------------------------------------------------------------

    async def _run_llm_with_tools(
        self,
        messages: list[dict[str, Any]],
        model_id: str,
        user_id: str,
        chat_id: str,
        task_id: str,
        source: str = "user",
        agent_id: str | None = None,
        debug_events: list[dict] | None = None,
        mode: str = "agent",
        override_tools: list[dict] | None = None,
        dispatcher: "ToolDispatcher | None" = None,
        between_rounds_delay: float = 0.0,
    ) -> tuple[str, str, dict[str, int]]:
        """
        Call LLM and handle tool calls in a loop until a final text response.
        Returns (response_text, model_id_used, total_usage).

        dispatcher: if provided, use this instead of self.tool_dispatcher.
                    Pass explicitly for sub-agent calls to avoid state conflicts
                    when background tasks run concurrently.
        debug_events: if provided, LLM round events are appended here
        mode: "agent" = all tools; "ask" = safe commands only (whitelist-level)
        override_tools: if set, use exactly these tools instead of mode-based selection
                        (used for heartbeat to pass only workspace_read)
        """
        effective_dispatcher = dispatcher or self.tool_dispatcher
        # Attach debug collector to dispatcher so tool events (tool_start/tool_done)
        # are also captured — important for background task streaming.
        if debug_events is not None and effective_dispatcher:
            effective_dispatcher.set_debug_collector(debug_events)
        model_used = model_id
        total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        tool_context = {
            "user_id": user_id,
            "chat_id": chat_id,
            "agent_id": agent_id or self.agent_id,
            "memory_service_url": self.memory_service_url,
            "openrouter_api_key": settings.openrouter_api_key,
            "source": source,
            "mode": mode,
            "model_id": model_id,  # used by delegate_to_agent to preserve model choice
        }
        available_tools = override_tools if override_tools is not None else get_tools_for_mode(mode)

        for round_num in range(MAX_TOOL_CALL_ROUNDS):
            # Delay between rounds (e.g. heartbeat uses free models with strict rate limits)
            if round_num > 0 and between_rounds_delay > 0:
                logger.debug(
                    f"[{task_id}] Waiting {between_rounds_delay}s before round {round_num + 1} (rate limit guard)"
                )
                await asyncio.sleep(between_rounds_delay)

            # Check if user issued /stop between rounds
            if self._is_cancelled(user_id):
                logger.info(f"[{task_id}] Task cancelled by user (round {round_num})")
                return "✋ Выполнение остановлено по команде /stop", model_used, total_usage

            # Debug: record LLM round (include agent so delegated calls are distinguishable)
            if debug_events is not None:
                debug_events.append(
                    {
                        "type": "llm",
                        "round": round_num + 1,
                        "model": self._to_openrouter_id(model_id),
                        "agent": agent_id or self.agent_id,
                    }
                )

            response_data, model_used, llm_error, round_usage = await self._call_llm(
                messages=messages,
                model_id=model_id,
                with_tools=True,
                agent_id=agent_id,
                available_tools=available_tools,
            )

            # Accumulate token usage across rounds
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                total_usage[k] = total_usage.get(k, 0) + round_usage.get(k, 0)

            if response_data is None:
                raise LLMUnavailableError(llm_error)

            choice = response_data.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls")

            # Fallback: some models embed tool calls in message text instead of tool_calls field.
            # Handles: namespaced XML, <tool_call>{json}</tool_call>, and bare JSON objects.
            content_text: str = message.get("content") or ""
            if not tool_calls and content_text:
                tool_calls, content_consumed = _parse_embedded_tool_calls(content_text)
                if tool_calls:
                    logger.debug(
                        f"[{task_id}] Parsed {len(tool_calls)} embedded tool call(s) from message content"
                    )
                    if content_consumed:
                        # Entire content was a bare JSON tool call — blank it out
                        content_text = ""
                    else:
                        # Strip tag-wrapped markup only
                        content_text = _XML_TOOL_CALL_RE.sub("", content_text)
                        content_text = _PLAIN_TOOL_CALL_RE.sub("", content_text).strip()

            if not tool_calls:
                # Final text response
                if not content_text:
                    logger.warning(
                        f"[{task_id}] Model returned empty content with no tool calls"
                        f" (round={round_num + 1}, model={model_used},"
                        f" finish_reason={choice.get('finish_reason', '?')})"
                    )
                return content_text or self._fallback_text(model_used), model_used, total_usage

            # Process tool calls
            messages.append(
                {
                    "role": "assistant",
                    "content": content_text or None,
                    "tool_calls": tool_calls,
                }
            )

            for tc in tool_calls:
                tool_name = _normalize_tool_name(tc.get("function", {}).get("name", ""))
                try:
                    args_raw = tc.get("function", {}).get("arguments", "{}")
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {}

                # Check cancel before each tool call
                if self._is_cancelled(user_id):
                    logger.info(f"[{task_id}] Task cancelled before tool {tool_name}")
                    return "✋ Выполнение остановлено по команде /stop", model_used, total_usage

                logger.info(f"[{task_id}] Tool call: {tool_name}({list(args.keys())})")

                result = await effective_dispatcher.dispatch(
                    tool_name=tool_name,
                    tool_args=args,
                    context=tool_context,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": str(result),
                    }
                )

            logger.debug(f"[{task_id}] Tool round {round_num + 1} complete, continuing LLM")

        # Exceeded rounds — get final response without tools
        logger.warning(
            f"[{task_id}] Exceeded {MAX_TOOL_CALL_ROUNDS} tool-call rounds,"
            f" requesting final response without tools (model={model_id})"
        )
        response_data, model_used, llm_error, final_usage = await self._call_llm(
            messages=messages,
            model_id=model_id,
            with_tools=False,
            agent_id=agent_id,
            available_tools=available_tools,
        )
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total_usage[k] = total_usage.get(k, 0) + final_usage.get(k, 0)
        if response_data:
            text = (
                response_data.get("choices", [{}])[0].get("message", {}).get("content") or ""
            ).strip()
            if not text:
                logger.warning(
                    f"[{task_id}] Final no-tools response also empty (model={model_used})"
                )
            return text or self._fallback_text(model_used), model_used, total_usage
        raise LLMUnavailableError(llm_error)

    def _make_sub_dispatcher(
        self,
        agent_id: str,
        parent_debug_collector: list[dict] | None = None,
    ) -> "ToolDispatcher":
        """Create an isolated ToolDispatcher for a sub-agent (no delegate_callback)."""
        sub_workspace = self._get_workspace(agent_id)
        sub_logger = self._get_activity_logger(agent_id)
        d = ToolDispatcher(
            workspace=sub_workspace,
            http_client=self.http_client,
            providers_config=get_providers_config(),
            activity_logger=sub_logger,
            delegate_callback=None,
        )
        if parent_debug_collector is not None:
            d.set_debug_collector(parent_debug_collector)
        return d

    def _resolve_agent_model(self, agent_id: str, fallback: str) -> str:
        """
        Resolve the model for a sub-agent in priority order:
          1. Agent's workspace config.yaml → default_model
          2. Global providers.yaml → agents[id].default_model
          3. fallback (caller's active model)
        """
        ws_cfg = self._get_workspace(agent_id).read_config_dict()
        if ws_cfg.get("default_model"):
            return ws_cfg["default_model"]
        for a in get_providers_config().get("agents", []):
            if a.get("id") == agent_id and a.get("default_model"):
                return a["default_model"]
        return fallback

    async def _delegate_task(
        self,
        agent_id: str,
        task: str,
        context: dict[str, Any],
        mode: str = "agent",
    ) -> str:
        """
        Synchronous delegation — blocks until the sub-agent finishes.
        Uses an isolated ToolDispatcher so concurrent background calls are safe.
        """
        model_id = self._resolve_agent_model(
            agent_id, context.get("model_id") or settings.default_chat_model
        )
        parent_debug = self.tool_dispatcher._debug_collector if self.tool_dispatcher else None
        sub_dispatcher = self._make_sub_dispatcher(agent_id, parent_debug_collector=parent_debug)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._get_workspace(agent_id).config.system_prompt},
            {"role": "user", "content": task},
        ]
        logger.info(f"Delegating to '{agent_id}' (mode={mode}, model={model_id}): {task[:60]}…")
        response_text, _, _usage = await self._run_llm_with_tools(
            messages=messages,
            model_id=model_id,
            user_id=context.get("user_id", "unknown"),
            chat_id=context.get("chat_id", "default"),
            task_id=f"sub-{agent_id}-{uuid4().hex[:8]}",
            source=context.get("source", "user"),
            agent_id=agent_id,
            debug_events=sub_dispatcher._debug_collector,
            mode=mode,
            override_tools=AGENT_TOOLS,
            dispatcher=sub_dispatcher,
        )
        return response_text

    async def run_agent_background(
        self,
        agent_id: str,
        task: str,
        context: dict[str, Any],
        mode: str = "agent",
        notify_callback: Callable | None = None,
    ) -> str:
        """
        Start a background asyncio Task for a sub-agent. Returns immediately.
        Result is stored in _background_results; notify_callback fires on completion.
        """
        user_id = context.get("user_id", "unknown")
        key = f"{user_id}:{agent_id}"

        existing = self._background_tasks.get(key)
        if existing and not existing.done():
            existing.cancel()
            logger.info(f"Cancelled previous background task for {key}")

        model_id = self._resolve_agent_model(
            agent_id, context.get("model_id") or settings.default_chat_model
        )
        sub_dispatcher = self._make_sub_dispatcher(agent_id)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._get_workspace(agent_id).config.system_prompt},
            {"role": "user", "content": task},
        ]
        task_id = f"bg-{agent_id}-{uuid4().hex[:8]}"

        # Shared debug buffer: events are appended by _run_llm_with_tools and
        # drained periodically by the bot's background monitor via poll_bg_task().
        bg_debug: list[dict[str, Any]] = []

        async def _run_bg() -> None:
            status, result_text = "completed", ""
            try:
                result_text, _, _bg_usage = await self._run_llm_with_tools(
                    messages=messages,
                    model_id=model_id,
                    user_id=user_id,
                    chat_id=context.get("chat_id", "default"),
                    task_id=task_id,
                    source=context.get("source", "user"),
                    agent_id=agent_id,
                    mode=mode,
                    override_tools=AGENT_TOOLS,
                    dispatcher=sub_dispatcher,
                    debug_events=bg_debug,
                )
            except asyncio.CancelledError:
                status, result_text = "cancelled", "Задача отменена."
                logger.info(f"Background task {task_id} cancelled")
            except LLMUnavailableError as e:
                status, result_text = "error", f"❌ Модель недоступна: {e}"
                logger.warning(f"Background task {task_id} LLM error: {e}")
            except Exception as e:
                status = "error"
                result_text = f"❌ Ошибка: {type(e).__name__}: {e}"
                logger.error(f"Background task {task_id} failed: {e}", exc_info=True)

            self._finish_task(task_id, status)
            self._background_results[key] = {
                "agent_id": agent_id,
                "status": status,
                "result": result_text,
                "timestamp": datetime.now().astimezone().isoformat(),
                "task_id": task_id,
            }
            if notify_callback:
                try:
                    await notify_callback(user_id, agent_id, status, result_text)
                except Exception as e:
                    logger.warning(f"Background notify callback failed: {e}")

        self._bg_debug_buffer[key] = bg_debug
        self._register_task(
            task_id=task_id,
            agent_id=agent_id,
            user_id=user_id,
            description=task,
            source=context.get("source", "user"),
            is_background=True,
        )
        bg = asyncio.create_task(_run_bg(), name=task_id)
        self._background_tasks[key] = bg
        logger.info(f"Started background task {task_id} for '{agent_id}', user={user_id}")
        return key

    def _register_task(
        self,
        task_id: str,
        agent_id: str,
        user_id: str,
        description: str,
        source: str = "user",
        is_background: bool = False,
    ) -> None:
        """Record a task in the global registry and persist to Redis."""
        # Evict oldest entries if we exceed the cap
        if len(self._task_registry) >= self._TASK_REGISTRY_MAX:
            oldest_key = next(iter(self._task_registry))
            del self._task_registry[oldest_key]

        entry: dict[str, Any] = {
            "task_id": task_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "description": description[:120],
            "status": "running",
            "source": source,
            "background": is_background,
            "started_at": datetime.now().astimezone().isoformat(),
            "finished_at": None,
            "duration_ms": None,
        }
        self._task_registry[task_id] = entry
        asyncio.create_task(self._redis_save_task(task_id, entry))

    def _finish_task(self, task_id: str, status: str = "completed") -> None:
        """Mark a task as finished in the registry and update Redis."""
        if task_id not in self._task_registry:
            return
        entry = self._task_registry[task_id]
        entry["status"] = status
        entry["finished_at"] = datetime.now().astimezone().isoformat()
        try:
            started = datetime.fromisoformat(entry["started_at"])
            entry["duration_ms"] = int(
                (datetime.now().astimezone() - started).total_seconds() * 1000
            )
        except Exception:
            pass
        asyncio.create_task(self._redis_save_task(task_id, entry))

    async def _redis_save_task(self, task_id: str, entry: dict[str, Any]) -> None:
        """Persist a single task entry to Redis (fire-and-forget)."""
        if not self._redis:
            return
        try:
            key = f"{_REDIS_TASK_PREFIX}{task_id}"
            await self._redis.setex(key, _REDIS_TASK_TTL, json.dumps(entry))
            # Keep ordered index: push to front, trim to 2× cap
            await self._redis.lpush(_REDIS_TASK_INDEX, task_id)
            await self._redis.ltrim(_REDIS_TASK_INDEX, 0, self._TASK_REGISTRY_MAX * 2 - 1)
        except Exception as e:
            logger.debug(f"Redis task persist failed: {e}")

    async def _restore_task_registry(self) -> None:
        """Load recent task entries from Redis into in-memory registry on startup."""
        if not self._redis:
            return
        try:
            task_ids = await self._redis.lrange(_REDIS_TASK_INDEX, 0, self._TASK_REGISTRY_MAX - 1)
            loaded = 0
            for tid in reversed(task_ids):  # oldest-first so dict order is chronological
                key = f"{_REDIS_TASK_PREFIX}{tid}"
                raw = await self._redis.get(key)
                if raw:
                    try:
                        self._task_registry[tid] = json.loads(raw)
                        loaded += 1
                    except Exception:
                        pass
            logger.info(f"Restored {loaded} tasks from Redis")
        except Exception as e:
            logger.warning(f"Failed to restore task registry from Redis: {e}")

    def list_tasks(self, user_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """
        Return recent tasks, newest first.
        If user_id given, filter to that user; otherwise return all.
        Running background tasks always appear first.
        """
        entries = list(self._task_registry.values())
        if user_id:
            entries = [e for e in entries if e.get("user_id") == user_id]

        # Running tasks first, then finished sorted by started_at descending
        running = [e for e in entries if e.get("status") == "running"]
        finished = [e for e in entries if e.get("status") != "running"]
        finished.sort(key=lambda e: e.get("started_at", ""), reverse=True)
        return (running + finished)[:limit]

    def drain_bg_debug(self, key: str) -> list[dict[str, Any]]:
        """Return and clear accumulated debug events for a background task."""
        buf = self._bg_debug_buffer.get(key)
        if not buf:
            return []
        events = buf[:]
        buf.clear()
        return events

    def drain_fg_debug(self, user_id: str, agent_id: str) -> dict[str, Any]:
        """
        Return and clear live debug events for a foreground task.
        Returns {"events": [...], "running": bool}
        running=True means the task is still executing (buffer still registered).
        """
        key = f"{user_id}:{agent_id}:fg"
        buf = self._fg_debug_buffer.get(key)
        running = key in self._fg_debug_buffer
        if not buf:
            return {"events": [], "running": running}
        events = buf[:]
        buf.clear()
        return {"events": events, "running": running}

    def poll_bg_task(
        self, user_id: str, agent_id: str, consume_result: bool = False
    ) -> dict[str, Any]:
        """
        Poll the current state of a background task.
        Returns: {status, events (drained), result (if finished), finished_at}

        The result is NEVER popped here — the monitor only reads it.
        get_background_result() (used by the orchestrator tool) is responsible
        for consuming it when the user explicitly asks via get_agent_result.
        The consume_result parameter is kept for API compatibility but ignored.
        """
        key = f"{user_id}:{agent_id}"

        # Determine live status
        bg_task = self._background_tasks.get(key)
        if bg_task and not bg_task.done():
            status = "running"
        elif key in self._background_results:
            status = self._background_results[key].get("status", "completed")
        else:
            # No record at all — either never started or already consumed
            task_entry = next(
                (
                    e
                    for e in self._task_registry.values()
                    if e.get("user_id") == user_id
                    and e.get("agent_id") == agent_id
                    and e.get("background")
                ),
                None,
            )
            status = task_entry.get("status", "unknown") if task_entry else "unknown"

        events = self.drain_bg_debug(key)

        result_text: str | None = None
        finished_at: str | None = None
        if status != "running":
            # Always just peek — never pop here so get_agent_result still works
            bg_res = self._background_results.get(key)
            if bg_res:
                result_text = bg_res.get("result")
                finished_at = bg_res.get("timestamp")

        return {
            "status": status,
            "events": events,
            "result": result_text,
            "finished_at": finished_at,
        }

    def cancel_agent_background_tasks(self, agent_id: str, user_id: str) -> str:
        """Cancel any running background task for agent_id + user_id."""
        key = f"{user_id}:{agent_id}"
        task = self._background_tasks.get(key)
        if task and not task.done():
            task.cancel()
            return f"Фоновая задача агента '{agent_id}' отменена."
        return f"Активных фоновых задач агента '{agent_id}' не найдено."

    def get_background_result(self, agent_id: str, user_id: str) -> dict[str, Any] | None:
        """Return (and clear) completed background result, or status if still running."""
        key = f"{user_id}:{agent_id}"
        task = self._background_tasks.get(key)
        if task and not task.done():
            return {"agent_id": agent_id, "status": "running", "result": None}
        return self._background_results.pop(key, None)

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        model_id: str,
        with_tools: bool = True,
        agent_id: str | None = None,
        available_tools: list[dict] | None = None,
    ) -> tuple[dict[str, Any] | None, str, str, dict[str, int]]:
        """
        Call LLM API, optionally trying a fallback chain.

        Returns (response_json, model_id_used, error_message, usage_dict).
          - On success: (data, candidate, "", {prompt_tokens, completion_tokens, total_tokens})
          - On failure: (None, model_id, human-readable error from API, {})
        """
        if not self.http_client or not settings.openrouter_api_key:
            return None, model_id, "API key not configured", {}

        candidates = self._get_model_candidates(model_id, agent_id=agent_id)
        last_error = "No response from API"

        cfg = get_providers_config()
        llm_timeout = float(cfg.get("providers", {}).get("openrouter", {}).get("timeout", 60))

        for candidate in candidates:
            openrouter_model = self._to_openrouter_id(candidate)
            try:
                payload: dict[str, Any] = {
                    "model": openrouter_model,
                    "messages": messages,
                    "temperature": 0.4,
                }
                if with_tools and self.tool_dispatcher:
                    tools_list = available_tools if available_tools is not None else AVAILABLE_TOOLS
                    payload["tools"] = tools_list
                    payload["tool_choice"] = "auto"

                response = await self.http_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=llm_timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    usage = data.get("usage") or {}
                    usage_dict = {
                        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
                        "completion_tokens": int(usage.get("completion_tokens", 0)),
                        "total_tokens": int(usage.get("total_tokens", 0)),
                    }
                    return data, candidate, "", usage_dict

                # Extract the actual error message from the API response
                last_error = self._extract_api_error(response, candidate)
                logger.warning(f"LLM error on {candidate}: {last_error}")

                # Retriable errors — try next candidate if fallback enabled
                if response.status_code in (429, 500, 502, 503, 504):
                    continue

                # Non-retriable error — stop immediately
                break

            except Exception as e:
                last_error = f"{type(e).__name__}: {e or '(no detail)'}"
                logger.warning(f"LLM call failed on {candidate}: {last_error}")
                continue

        return None, model_id, last_error, {}

    @staticmethod
    def _extract_api_error(response, model_id: str) -> str:
        """Parse a human-readable error from an OpenRouter error response."""
        status = response.status_code
        try:
            body = response.json()
            err = body.get("error", {})
            msg = err.get("message") or err.get("msg") or body.get("message") or response.text[:300]
        except Exception:
            msg = response.text[:300] or "(empty response)"
        return f"HTTP {status} ({model_id}): {msg}"

    # -------------------------------------------------------------------------
    # Model helpers
    # -------------------------------------------------------------------------

    async def _get_model_for_chat(self, user_id: str, chat_id: str) -> str:
        """Get model assigned to this chat, falling back to default."""
        try:
            resp = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/chats/{user_id}/{chat_id}/model"
            )
            if resp.status_code == 200:
                model_id = resp.json().get("model_id")
                if model_id:
                    return model_id
        except Exception as e:
            logger.debug(f"Failed to get chat model: {e}")

        # Fallback: first in active_models or settings default
        cfg = get_providers_config()
        active = cfg.get("active_models", [])
        if active:
            return active[0]["id"]
        return settings.default_chat_model

    def _get_model_candidates(
        self, primary_model_id: str, agent_id: str | None = None
    ) -> list[str]:
        """
        Return ordered list of models to try.

        If the agent has fallback_enabled: false (default) → returns only
        [primary_model_id]. The caller will surface the error directly to the user.

        If fallback_enabled: true → builds chain from per-agent fallback_chain
        (or global default_fallback_chain), then appends CHAT_FALLBACK_MODELS env.
        """
        cfg = get_providers_config()

        # Find agent config
        agent_cfg: dict = {}
        if agent_id:
            for a in cfg.get("agents", []):
                if a.get("id") == agent_id:
                    agent_cfg = a
                    break

        # Fallback disabled by default — only try the primary model
        if not agent_cfg.get("fallback_enabled", False):
            return [primary_model_id]

        # Fallback enabled: build chain
        chain = agent_cfg.get("fallback_chain") or [
            e.get("model") for e in cfg.get("default_fallback_chain", [])
        ]
        candidates: list[str] = []
        for m in [primary_model_id] + chain:
            if m and m not in candidates:
                candidates.append(m)

        # Also add env-defined fallbacks
        env_fallbacks = os.getenv("CHAT_FALLBACK_MODELS", "").strip()
        if env_fallbacks:
            for m in env_fallbacks.split(","):
                m = m.strip()
                if m and m not in candidates:
                    candidates.append(m)

        return candidates or [settings.default_chat_model]

    @staticmethod
    def _to_openrouter_id(model_id: str) -> str:
        """Strip 'openrouter/' prefix for OpenRouter API."""
        prefix = "openrouter/"
        return model_id[len(prefix) :] if model_id.startswith(prefix) else model_id

    # -------------------------------------------------------------------------
    # Chat / history helpers
    # -------------------------------------------------------------------------

    async def _get_or_create_chat(self, user_id: str) -> str:
        """Return active chat_id, creating one if needed."""
        try:
            resp = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/chats/{user_id}/active"
            )
            if resp.status_code == 200:
                return resp.json().get("chat_id", "default")
        except Exception as e:
            logger.debug(f"Failed to get active chat: {e}")
        return "default"

    async def _get_chat_history(self, user_id: str, chat_id: str) -> list[dict[str, Any]]:
        """Fetch chat history from Memory Service."""
        try:
            resp = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/history/{user_id}/{chat_id}",
                params={"limit": 100},
            )
            if resp.status_code == 200:
                return resp.json().get("messages", [])
        except Exception as e:
            logger.debug(f"Failed to get chat history: {e}")
        return []

    async def _save_to_history(self, user_id: str, chat_id: str, role: str, content: str) -> None:
        """Save a message to chat history."""
        try:
            await self.http_client.post(
                f"{self.memory_service_url}/api/v1/history/{user_id}/{chat_id}",
                json={"role": role, "content": content},
            )
        except Exception as e:
            logger.debug(f"Failed to save history: {e}")

    async def _get_history_summary(self, user_id: str, chat_id: str) -> str | None:
        """Retrieve previously computed history summary from Redis."""
        if not self._redis:
            return None
        key = f"balbes:history_summary:{user_id}:{chat_id}"
        try:
            val = await self._redis.get(key)
            return val.decode() if val else None
        except Exception as e:
            logger.debug(f"Failed to get history summary: {e}")
            return None

    async def _save_history_summary(self, user_id: str, chat_id: str, summary: str) -> None:
        """Store history summary in Redis (7 day TTL)."""
        if not self._redis:
            return
        key = f"balbes:history_summary:{user_id}:{chat_id}"
        try:
            await self._redis.set(key, summary.encode(), ex=604800)
        except Exception as e:
            logger.debug(f"Failed to save history summary: {e}")

    async def _maybe_summarize_history(
        self,
        user_id: str,
        chat_id: str,
        history: list[dict[str, Any]],
        system_prompt: str,
        user_input: str,
        model_id: str,
    ) -> str | None:
        """
        If history would be trimmed and history_strategy=summarize, call cheap LLM
        to summarize old messages and return the summary string.
        Otherwise return None.
        """
        cfg = get_providers_config().get("memory", {})
        if cfg.get("history_strategy") != "summarize":
            return None

        if not _would_trim_history(system_prompt, history, user_input, model_id):
            return None

        # Use cached summary if available
        cached = await self._get_history_summary(user_id, chat_id)
        if cached:
            return cached

        # Pick cheap model for summarization
        summary_model = cfg.get("summary_model") or "meta-llama/llama-3.1-8b-instruct:free"

        # Take first half of history as the "old" part to summarize
        old_msgs = history[: len(history) // 2]
        if not old_msgs:
            return None

        conv_text = "\n".join(
            f"{m['role'].upper()}: {m.get('content', '')[:300]}" for m in old_msgs
        )
        summarize_messages = [
            {
                "role": "system",
                "content": "Ты — ассистент для суммаризации диалогов. Сделай краткое содержание (5-10 предложений) следующего разговора. Пиши на том же языке что разговор.",
            },
            {"role": "user", "content": f"Разговор для суммаризации:\n\n{conv_text}"},
        ]

        try:
            response_data, _, _, _ = await self._call_llm(
                messages=summarize_messages,
                model_id=summary_model,
                with_tools=False,
                agent_id=None,
                available_tools=None,
            )
            if response_data:
                summary = (
                    response_data.get("choices", [{}])[0].get("message", {}).get("content") or ""
                ).strip()
                if summary:
                    await self._save_history_summary(user_id, chat_id, summary)
                    logger.info(f"History summarized for {user_id}/{chat_id}: {len(summary)} chars")
                    return summary
        except Exception as e:
            logger.warning(f"History summarization failed: {e}")

        return None

    async def _record_token_usage(
        self, agent_id: str, model: str, usage: dict[str, int], task_id: str
    ) -> None:
        """Fire-and-forget: record token usage to memory service."""
        try:
            await self.http_client.post(
                f"{self.memory_service_url}/api/v1/tokens/record",
                json={
                    "agent_id": agent_id,
                    "model": model,
                    "provider": "openrouter",
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "cost_usd": 0.0,
                    "task_id": task_id,
                    "fallback_used": False,
                    "cached": False,
                },
                timeout=5.0,
            )
        except Exception as e:
            logger.debug(f"Failed to record token usage: {e}")

    @staticmethod
    def _fallback_text(model_id: str = "") -> str:
        model_hint = f" (модель: `{model_id}`)" if model_id else ""
        return (
            f"⚠️ Модель вернула пустой ответ{model_hint}. "
            "Попробуй переформулировать запрос, сменить модель (/model) или повторить попытку."
        )

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    async def get_agent_status(self) -> dict[str, Any]:
        loaded_workspaces = {aid: ws.list_files() for aid, ws in self._workspaces.items()}
        if self.agent_id not in loaded_workspaces:
            loaded_workspaces[self.agent_id] = []
        log_dates = {aid: al.list_log_dates()[:7] for aid, al in self._loggers.items()}
        return {
            "agent_id": self.agent_id,
            "status": "online",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "workspace_files": loaded_workspaces.get(self.agent_id, []),
            "workspaces": loaded_workspaces,
            "activity_logs": log_dates,
            "services": {
                "memory_service": self.memory_service_url,
                "skills_registry": self.skills_registry_url,
            },
        }
