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

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
import tiktoken
from agent_logger import AgentActivityLogger
from tools import AVAILABLE_TOOLS, ToolDispatcher, get_tools_for_mode
from workspace import AgentWorkspace

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.agent")

MAX_TOOL_CALL_ROUNDS = 5  # prevent infinite tool-call loops


def _count_tokens(text: str) -> int:
    """Approximate token count using cl100k_base encoding."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def _load_providers_config() -> dict[str, Any]:
    """Load providers.yaml once. Returns empty dict on failure."""
    try:
        from pathlib import Path

        import yaml

        cfg_path = Path(__file__).parent.parent.parent / "config" / "providers.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load providers.yaml: {e}")
    return {}


_providers_config: dict[str, Any] = {}


def get_providers_config() -> dict[str, Any]:
    global _providers_config
    if not _providers_config:
        _providers_config = _load_providers_config()
    return _providers_config


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
) -> list[dict[str, Any]]:
    """
    Build the messages array for LLM, adaptively trimming history to fit context window.
    Preserves the most recent messages.
    """
    cfg = get_providers_config().get("memory", {})
    trim_threshold = cfg.get("trim_threshold", 0.85)
    max_msgs = cfg.get("max_messages_in_context", 50)
    reserve = cfg.get("system_prompt_reserve", 500)

    context_window = get_context_window(model_id)
    used = _count_tokens(system_prompt) + _count_tokens(user_input) + reserve
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
    for m in trimmed:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})
    return messages


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

        # Workspace cache: agent_id → AgentWorkspace (lazy-loaded per agent)
        self._workspaces: dict[str, AgentWorkspace] = {}

        # Activity logger cache: agent_id → AgentActivityLogger
        self._loggers: dict[str, AgentActivityLogger] = {}

        # Per-user cancellation flags (set by /stop, cleared at task start)
        self._cancel_flags: dict[str, bool] = {}

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
        """Initialize HTTP client, load default workspace, warm up tools."""
        self.http_client = httpx.AsyncClient(timeout=60.0)

        # Eagerly load the default orchestrator workspace
        ws = self._get_workspace(self.agent_id)
        activity_log = self._get_activity_logger(self.agent_id)

        # Initialize tool dispatcher with default workspace and logger
        self.tool_dispatcher = ToolDispatcher(
            workspace=ws,
            http_client=self.http_client,
            providers_config=get_providers_config(),
            activity_logger=activity_log,
        )

        logger.info("Orchestrator Agent initialized")

    async def close(self) -> None:
        if self.http_client:
            await self.http_client.aclose()
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

        try:
            # Resolve chat_id
            if chat_id is None:
                chat_id = await self._get_or_create_chat(user_id)

            logger.info(
                f"[{task_id}] user={user_id} chat={chat_id} agent={effective_agent_id}: "
                f"{description[:60]}..."
            )

            # Load chat history
            history = await self._get_chat_history(user_id, chat_id)

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

            # Build messages array (with adaptive trim)
            messages = build_messages_for_llm(
                system_prompt=system_prompt,
                history=history,
                user_input=description,
                model_id=model_id,
            )

            # Save user message to history
            await self._save_to_history(user_id, chat_id, "user", description)

            ctx = context or {}
            debug: bool = ctx.get("debug", False)
            mode: str = ctx.get("mode", "agent")

            # Attach debug collector to tool dispatcher for this task
            debug_events: list[dict] = []
            if self.tool_dispatcher:
                self.tool_dispatcher.set_debug_collector(debug_events if debug else None)

            # Run LLM with tool call loop
            response_text, model_used = await self._run_llm_with_tools(
                messages=messages,
                model_id=model_id,
                user_id=user_id,
                chat_id=chat_id,
                task_id=task_id,
                source=ctx.get("source", "user"),
                agent_id=effective_agent_id,
                debug_events=debug_events if debug else None,
                mode=mode,
            )

            # Detach debug collector
            if self.tool_dispatcher:
                self.tool_dispatcher.set_debug_collector(None)

            # Save assistant response to history
            await self._save_to_history(user_id, chat_id, "assistant", response_text)

            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            logger.info(f"[{task_id}] Done in {duration_ms:.0f}ms using {model_used}")

            result: dict[str, Any] = {
                "task_id": task_id,
                "status": "success",
                "result": {"output": response_text},
                "skill_used": "direct_llm_chat",
                "model_used": model_used,
                "chat_id": chat_id,
                "duration_ms": duration_ms,
            }
            if debug and debug_events:
                result["debug_events"] = debug_events
            return result

        except Exception as e:
            logger.error(f"[{task_id}] Task failed: {e}", exc_info=True)
            duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            err_detail = str(e) or "(нет описания)"
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
    ) -> tuple[str, str]:
        """
        Call LLM and handle tool calls in a loop until a final text response.
        Returns (response_text, model_id_used).

        debug_events: if provided, LLM round events are appended here
        mode: "agent" = all tools; "ask" = execute_command + workspace_write blocked
        """
        model_used = model_id
        tool_context = {
            "user_id": user_id,
            "chat_id": chat_id,
            "agent_id": agent_id or self.agent_id,
            "memory_service_url": self.memory_service_url,
            "openrouter_api_key": settings.openrouter_api_key,
            "source": source,
        }
        available_tools = get_tools_for_mode(mode)

        for round_num in range(MAX_TOOL_CALL_ROUNDS):
            # Check if user issued /stop between rounds
            if self._is_cancelled(user_id):
                logger.info(f"[{task_id}] Task cancelled by user (round {round_num})")
                return "✋ Выполнение остановлено по команде /stop", model_used

            # Debug: record LLM round
            if debug_events is not None:
                debug_events.append(
                    {
                        "type": "llm",
                        "round": round_num + 1,
                        "model": self._to_openrouter_id(model_id),
                    }
                )

            response_data, model_used, llm_error = await self._call_llm(
                messages=messages,
                model_id=model_id,
                with_tools=True,
                agent_id=agent_id,
                available_tools=available_tools,
            )

            if response_data is None:
                err_msg = f"❌ Модель недоступна\n`{llm_error}`"
                return err_msg, model_used

            choice = response_data.get("choices", [{}])[0]
            message = choice.get("message", {})
            tool_calls = message.get("tool_calls")

            if not tool_calls:
                # Final text response
                return message.get("content", "").strip() or self._fallback_text(), model_used

            # Process tool calls
            messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})

            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                try:
                    args_raw = tc.get("function", {}).get("arguments", "{}")
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {}

                # Check cancel before each tool call
                if self._is_cancelled(user_id):
                    logger.info(f"[{task_id}] Task cancelled before tool {tool_name}")
                    return "✋ Выполнение остановлено по команде /stop", model_used

                logger.info(f"[{task_id}] Tool call: {tool_name}({list(args.keys())})")

                result = await self.tool_dispatcher.dispatch(
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
        response_data, model_used, llm_error = await self._call_llm(
            messages=messages,
            model_id=model_id,
            with_tools=False,
            agent_id=agent_id,
            available_tools=available_tools,
        )
        if response_data:
            text = (
                response_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            )
            return text or self._fallback_text(), model_used
        return f"❌ Модель недоступна\n`{llm_error}`", model_used

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        model_id: str,
        with_tools: bool = True,
        agent_id: str | None = None,
        available_tools: list[dict] | None = None,
    ) -> tuple[dict[str, Any] | None, str, str]:
        """
        Call LLM API, optionally trying a fallback chain.

        Returns (response_json, model_id_used, error_message).
          - On success: (data, candidate, "")
          - On failure: (None, model_id, human-readable error from API)
        """
        if not self.http_client or not settings.openrouter_api_key:
            return None, model_id, "API key not configured"

        candidates = self._get_model_candidates(model_id, agent_id=agent_id)
        last_error = "No response from API"

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
                )

                if response.status_code == 200:
                    return response.json(), candidate, ""

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

        return None, model_id, last_error

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

    @staticmethod
    def _fallback_text() -> str:
        return "Не смог обработать запрос. Попробуй переформулировать или уточни задачу."

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
