"""
BloggerAgent — LLM-powered blog post generator.

Reads from three sources (agent chats, Cursor MD files, business messages),
generates posts in RU and EN, creates drafts and sends them for approval.
Also handles evening check-in interviews and business summaries.
"""

import html
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx

from shared.agent_manifest import resolve_tools_for_agent_with_manifest
from shared.agent_tools.registry import ToolDispatcher, build_subagent_tools
from shared.config import get_settings
from shared.openrouter_http import openrouter_json_headers
from shared.telegram_app.memory_namespace import blogger_memory_user_ids_try_order, memory_user_id
from shared.utils import get_providers_config

from .post_queue import PostQueue
from .publisher import TelegramPublisher
from .reader import BusinessChatReader, ChatReader, CursorFileReader

logger = logging.getLogger("blogger.agent")

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
_WORKSPACE = _PROJECT_ROOT / "data" / "agents" / "blogger"
# Shipped defaults (git-tracked). ``data/agents/blogger/`` (often memory sub-repo) overrides per file.
_BBOT_DEFAULTS = Path(__file__).parent / "bbot_bootstrap"

_DEFAULT_MODEL = "openrouter/moonshotai/kimi-k2.5"
_CHEAP_MODEL = "openrouter/meta-llama/llama-3.3-70b-instruct"
# Batch dev-blog writers repeat the same sources per topic — cap input so the model still has room for RU+EN JSON.
_DEV_BLOG_WRITER_INPUT_MAX = 12000


def _clip_dev_blog_material(text: str, max_chars: int = _DEV_BLOG_WRITER_INPUT_MAX) -> str:
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return (
        t[:max_chars]
        + "\n\n[… исходный материал обрезан по длине; опирайся на то, что выше …]"
    )


def _json_object_slice(s: str) -> str:
    """Best-effort extract of a single JSON object from model output (prose before/after)."""
    s = (s or "").strip()
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j <= i:
        return ""
    return s[i : j + 1]


def _read_workspace_file(name: str) -> str:
    p = _WORKSPACE / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_workspace_or_bootstrap(name: str) -> str:
    """Prefer ``data/agents/blogger/``, else ``bbot_bootstrap/`` in the service package."""
    for base in (_WORKSPACE, _BBOT_DEFAULTS):
        p = base / name
        if p.exists():
            try:
                t = p.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except OSError as exc:
                logger.warning("read %s: %s", p, exc)
    return ""


def _blogger_dev_blog_config() -> dict:
    """``blogger.dev_blog`` in providers; ``enabled: false`` restores legacy one-shot generation."""
    root = (get_providers_config() or {}).get("blogger") or {}
    raw = root.get("dev_blog")
    if not isinstance(raw, dict):
        raw = {}
    if raw.get("enabled") is False:
        return {"enabled": False}
    merged: dict = {
        "enabled": True,
        "include_bbot_thread": True,
        "from_hours": 48,
        "max_posts_per_run": 3,
        "batch_topics": True,
        "cursor_files": 2,
        "dedup_titles_limit": 50,
    }
    for k, v in raw.items():
        if v is not None:
            merged[k] = v
    if "source_agent_ids" not in raw:
        merged["source_agent_ids"] = list(root.get("source_agents") or ["balbes", "coder"])
    return merged


def _dev_agent_ids_for_read(
    request_agents: list[str] | None, dev_cfg: dict, dev_disabled: bool
) -> set[str] | None:
    if dev_disabled or not dev_cfg.get("enabled", True):
        return None
    ids = list(dev_cfg.get("source_agent_ids") or [])
    if len(ids) == 0:
        return None
    if request_agents is not None and len(request_agents) > 0:
        ids = list(request_agents)
    alias = {"orchestrator": "balbes"}
    out: set[str] = set()
    for x in ids:
        s = (x or "").strip().lower()
        if not s:
            continue
        s = alias.get(s, s)
        out.add(s)
    return out or None


def _parse_topics_planner_json(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    topics = data.get("topics")
    if not isinstance(topics, list):
        return []
    out: list[dict] = []
    for t in topics:
        if not isinstance(t, dict):
            continue
        tid = (t.get("topic_id") or t.get("id") or "").strip()
        label = (t.get("label") or t.get("title") or "").strip()
        if tid and label:
            out.append({"topic_id": tid, "label": label})
    return out


def _load_bbot_system_prompt_merged() -> str:
    """
    Same bootstrap file order as ``AgentWorkspace``; each file: prefer ``data/agents/blogger``,
    else ``bbot_bootstrap/`` in the service package.
    """
    from services.orchestrator.workspace import BOOTSTRAP_FILES, MAX_FILE_CHARS, MAX_TOTAL_CHARS

    parts: list[str] = []
    total_chars = 0
    for filename in BOOTSTRAP_FILES:
        text = ""
        for base in (_WORKSPACE, _BBOT_DEFAULTS):
            path = base / filename
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("bbot bootstrap: %s: %s", path, exc)
                text = ""
            if text:
                break
        if not text:
            continue
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n\n[... truncated ...]"
        if total_chars + len(text) > MAX_TOTAL_CHARS:
            logger.warning("bbot bootstrap: total char cap, stopping at %s", filename)
            break
        parts.append(text)
        total_chars += len(text)
    if parts:
        return "\n\n---\n\n".join(parts)
    from services.orchestrator.workspace import AgentWorkspace

    return AgentWorkspace("blogger").load().system_prompt


def _llm_messages(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _normalize_openrouter_model_id(model: str) -> str:
    """OpenRouter chat/completions expects `vendor/model`, not `openrouter/vendor/model`."""
    m = (model or "").strip()
    while m.startswith("openrouter/"):
        m = m[11:]
    return m


class BloggerAgent:
    """
    Generates blog posts, handles check-in interviews, and manages approvals.
    """

    def __init__(
        self,
        openrouter_api_key: str,
        db: asyncpg.Pool,
        post_queue: PostQueue,
        publisher: TelegramPublisher,
        memory_url: str,
        owner_tg_id: int,
        owner_private_chat_id: int | None = None,
        model: str | None = None,
        cheap_model: str | None = None,
    ):
        self.api_key = openrouter_api_key
        self.db = db
        self.queue = post_queue
        self.publisher = publisher
        self.memory_url = memory_url.rstrip("/")
        self.owner_tg_id = owner_tg_id
        self.owner_private_chat_id = owner_private_chat_id or owner_tg_id
        self.model = model or _DEFAULT_MODEL
        self.cheap_model = cheap_model or _CHEAP_MODEL

        self._http: httpx.AsyncClient | None = None
        self._chat_reader: ChatReader | None = None
        self._cursor_reader = CursorFileReader()
        self._biz_reader: BusinessChatReader | None = None

        # Pending check-in interview state
        self._checkin_questions: list[str] = []

        # Default model for new bbot chats (overridden per-chat via memory service)
        self._conversation_model: str = model or _DEFAULT_MODEL

        # business_bot reference (set after construction)
        self.business_bot = None

        # Shared tool dispatcher (same registry as orchestrator; workspace = data/agents/blogger)
        self._tool_dispatcher: ToolDispatcher | None = None
        self._blogger_agent_workspace: object | None = None
        self._bbot_system_prompt_cache: str | None = None

        # Last failure reason for generate_agent_post (for Telegram error messages)
        self._last_post_gen_error: str = ""

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=120.0)
        return self._http

    def set_memory_url(self, url: str) -> None:
        self._chat_reader = ChatReader(url, self._get_http())

    def set_biz_reader(self, reader: BusinessChatReader) -> None:
        self._biz_reader = reader

    def _blogger_workspace(self):
        """Single ``data/agents/blogger`` workspace (tools + LLM system prompt)."""
        if self._blogger_agent_workspace is None:
            from services.orchestrator.workspace import AgentWorkspace

            self._blogger_agent_workspace = AgentWorkspace("blogger")
        return self._blogger_agent_workspace

    def _get_bbot_system_prompt(self) -> str:
        """
        Bootstrap like ``AgentWorkspace``; ``data/agents/blogger`` overrides shipped
        ``services/blogger/bbot_bootstrap`` per file. Cached per process; restart to reload.
        """
        if self._bbot_system_prompt_cache is not None:
            return self._bbot_system_prompt_cache
        self._bbot_system_prompt_cache = _load_bbot_system_prompt_merged()
        return self._bbot_system_prompt_cache

    def _get_tool_dispatcher(self) -> ToolDispatcher:
        if self._tool_dispatcher is None:
            self._tool_dispatcher = ToolDispatcher(
                workspace=self._blogger_workspace(),
                http_client=self._get_http(),
                providers_config=get_providers_config(),
            )
        return self._tool_dispatcher

    async def _call_llm(
        self, messages: list[dict], model: str | None = None, *, max_tokens: int = 2048
    ) -> str:
        """Call OpenRouter LLM. Returns text content."""
        http = self._get_http()
        used_model = _normalize_openrouter_model_id(model or self.model)
        try:
            resp = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=openrouter_json_headers(get_settings(), api_key=self.api_key),
                json={
                    "model": used_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
                timeout=90.0,
            )
            data = resp.json()
            if resp.status_code != 200 or "choices" not in data:
                err = data.get("error", data)
                logger.error("LLM error (%s) HTTP %s: %s", used_model, resp.status_code, err)
                return ""
            return data["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            logger.error("LLM call failed (%s): %s", used_model, exc)
            return ""

    # =========================================================================
    # Post generation
    # =========================================================================

    async def _bbot_thread_snippet_for_post(self) -> tuple[str, list[str]]:
        """Recent lines from the owner's active business-bot chat (Memory user_id ``blogger_<tg_id>``, legacy ``bbot_<tg_id>``).

        Orchestrator history uses plain ``<tg_id>``; DM with this bot is stored separately — without
        this block, «пост из этого чата» saw nothing useful.
        """
        try:
            cid = await self.bbot_get_active_chat(self.owner_tg_id)
            if not cid:
                return "", []
            hist = await self.bbot_get_history(self.owner_tg_id, cid)
            if not hist:
                return "", []
            lines: list[str] = []
            for m in hist[-45:]:
                role = m.get("role", "?")
                if role not in ("user", "assistant"):
                    continue
                content = (m.get("content") or "")[:350]
                if content.strip():
                    lines.append(f"[{role}]: {content}")
            if not lines:
                return "", []
            block = "=== Текущий чат с бизнес-ботом (этот диалог в Telegram) ===\n" + "\n".join(
                lines
            )
            return block, [f"bbot_dm:{cid[:8]}"]
        except Exception as exc:
            logger.warning("bbot_thread_snippet_for_post: %s", exc)
            return "", []

    async def _gather_post_sources(
        self,
        from_ts: datetime,
        from_hours: int,
        cursor_files: int,
        include_bbot: bool,
        agent_ids: set[str] | None,
    ) -> tuple[list[str], list[str]]:
        """Returns (source blocks, source_refs)."""
        sources: list[str] = []
        source_refs: list[str] = []
        if include_bbot:
            bbot_block, bbot_refs = await self._bbot_thread_snippet_for_post()
            if bbot_block:
                sources.append(bbot_block)
                source_refs.extend(bbot_refs)
                logger.info("generate_agent_post: added bbot thread snippet, refs=%s", bbot_refs)
        if self._chat_reader:
            msgs = await self._chat_reader.read(
                user_id=str(self.owner_tg_id),
                from_ts=from_ts,
                limit=40,
                agent_ids=agent_ids,
            )
            if msgs:
                chat_text = "\n".join(
                    f"[{m.get('chat_name', '?')}|{m['role']}]: {m['content'][:250]}"
                    for m in msgs[:30]
                )
                label_hours = f" (последние {from_hours}ч)" if from_hours else ""
                sources.append(f"=== История чатов{label_hours} ===\n{chat_text}")
                source_refs.append(f"chat_history:{from_ts.date().isoformat()}")
                logger.info(
                    "generate_agent_post: using %d messages from chat history (filtered=%s)",
                    len(msgs[:30]),
                    agent_ids,
                )
        for cf in self._cursor_reader.read_latest(cursor_files):
            sources.append(f"=== Cursor: {cf['path']} ===\n{cf['content'][:1500]}")
            source_refs.append(f"cursor:{cf['path']}")
        return sources, source_refs

    async def _plan_dev_blog_topics(
        self,
        user_material: str,
        avoid_titles: list[str],
        max_topics: int,
        model: str,
    ) -> list[dict]:
        avoid_block = ""
        if avoid_titles:
            avoid_block = "\n\nУже использованные заголовки (не дублируй тему):\n" + "\n".join(
                f"- {t[:200]}" for t in avoid_titles[:40]
            )
        system = (
            "Ты планировщик публичных dev-постов про продукт Balbes. "
            f"По материалам ниже перечисли до {max_topics} разных завершённых или чётко сформулированных тем. "
            "Пропусти пустой шум. Ответь только JSON, без markdown:\n"
            '{"topics": [{"topic_id": "kebab-case-id", "label": "короткая метка на русском"}]}'
        )
        user = f"{user_material}{avoid_block}"
        raw = await self._call_llm(_llm_messages(system, user), model=model, max_tokens=1024)
        if not raw.strip() and _normalize_openrouter_model_id(
            model
        ) != _normalize_openrouter_model_id(self.cheap_model):
            raw = await self._call_llm(
                _llm_messages(system, user), model=self.cheap_model, max_tokens=1024
            )
        topics = _parse_topics_planner_json(raw)
        return topics[:max_topics] if topics else []

    def _dev_blog_system_prompt(
        self,
        identity: str,
        soul: str,
        post_dev: str,
        avoid_titles: str,
        single_topic: dict | None,
    ) -> str:
        topic_block = ""
        if single_topic:
            topic_block = (
                f"\n\nСфокусируйся только на одной линии:\n"
                f"— topic_id: {single_topic['topic_id']}\n"
                f"— {single_topic['label']}\n"
                "Сделай уникальный заголовок; не повторяй уже существующие из списка выше."
            )
        return (
            f"{identity}\n\n{soul}\n\n{post_dev}\n\n"
            "Ты пишешь пост для публичного Telegram-канала от имени агента Балбес (про разработку Balbes).\n"
            "Пиши по делу, без выдуманных фактов: опирайся на переданные материалы."
            f"{avoid_titles}{topic_block}\n\n"
            "Ответь строго JSON (без обёртки ```, один объект):\n"
            '{"title": "...", "content_ru": "...", "content_en": "...", "notes": ""}\n'
            "Поле notes — опционально: кратко, если отдельно нужна служебная пометка; "
            "для сценария «со слов хозяина» укажи в notes что пост отражает формулировки владельца."
        )

    async def _write_one_agent_post_json(
        self,
        user_prompt: str,
        base_refs: list[str],
        topic: dict | None,
        avoid_list: str,
        identity: str,
        soul: str,
        post_dev: str,
        model: str,
    ) -> dict | None:
        up = _clip_dev_blog_material(user_prompt)
        refs = list(base_refs)
        if topic:
            refs.append(f"dev_blog:topic:{topic['topic_id']}")
        system = self._dev_blog_system_prompt(
            identity, soul, post_dev, avoid_list, single_topic=topic
        )
        primary = model or self.model
        cheap = self.cheap_model
        use_max = 4096
        pn = _normalize_openrouter_model_id

        async def do_call(m: str) -> str:
            return await self._call_llm(
                _llm_messages(system, up), model=m, max_tokens=use_max
            )

        raw = await do_call(primary)
        parsed = self._parse_post_json(raw, refs)
        if parsed:
            return parsed
        if pn(primary) == pn(cheap):
            if raw.strip():
                logger.warning(
                    "dev_blog writer: unparseable JSON, no alt model (primary==cheap) | %s", raw[:300]
                )
            return None
        raw2 = await do_call(cheap)
        parsed2 = self._parse_post_json(raw2, refs)
        if not parsed2 and (raw.strip() or raw2.strip()):
            logger.warning(
                "dev_blog writer: unparseable | primary=%s | tail=%s",
                raw[:220],
                raw2[:220],
            )
        return parsed2

    async def generate_agent_post(
        self,
        agents: list[str] | None = None,
        cursor_files: int = 2,
        from_hours: int = 48,
        model: str | None = None,
    ) -> list[dict]:
        """
        Generate one or more agent posts from Memory chats (optionally filtered by agent_id),
        Cursor exports, and optionally the bbot DM thread.

        Returns a list of dicts ``{title, content_ru, content_en, source_refs, notes?}`` — empty
        if nothing could be generated. When ``blogger.dev_blog.enabled`` is false, behavior
        matches the legacy single-post path (up to one dict in the list).
        """
        dev_cfg = _blogger_dev_blog_config()
        dev_disabled = dev_cfg.get("enabled") is False
        if dev_disabled:
            eff_cursor, eff_hours = cursor_files, from_hours
            agent_ids = None
            include_bbot = True
            batch = False
        else:
            eff_cursor = int(dev_cfg.get("cursor_files", cursor_files))
            eff_hours = int(dev_cfg.get("from_hours", from_hours))
            agent_ids = _dev_agent_ids_for_read(agents, dev_cfg, dev_disabled=False)
            include_bbot = bool(dev_cfg.get("include_bbot_thread", False))
            batch = bool(dev_cfg.get("batch_topics", True))

        from_ts = datetime.now(timezone.utc) - timedelta(hours=eff_hours)

        self._last_post_gen_error = ""

        sources, source_refs = await self._gather_post_sources(
            from_ts, eff_hours, eff_cursor, include_bbot, agent_ids
        )
        if (
            not sources
            and not dev_disabled
            and not include_bbot
        ):
            logger.info(
                "generate_agent_post: no sources with include_bbot_thread=false, retrying with bbot thread"
            )
            sources, source_refs = await self._gather_post_sources(
                from_ts, eff_hours, eff_cursor, True, agent_ids
            )

        if not sources:
            logger.info("No source material for agent post")
            self._last_post_gen_error = (
                "Нет материалов: ни переписки с бизнес-ботом, ни чатов Memory (по фильтру dev_blog), "
                "ни Cursor-файлов. Проверь MEMORY_SERVICE_URL и TELEGRAM_USER_ID. "
                "Если пишешь только в этом боте — убедись, что в чате есть реплики, или включи "
                "`blogger.dev_blog.include_bbot_thread: true`, или ослабь фильтр `source_agent_ids`."
            )
            return []

        identity = _read_workspace_or_bootstrap("IDENTITY.md")
        soul = _read_workspace_or_bootstrap("SOUL.md")
        post_dev = _read_workspace_or_bootstrap("POST_DEV_AGENT.md")

        dedup_limit = int(dev_cfg.get("dedup_titles_limit", 50) if not dev_disabled else 50)
        avoid_titles = await self.queue.get_recent_titles_for_dedup(
            post_type="agent", limit=dedup_limit
        )
        avoid_list = (
            "\n\nНедавние заголовки в очереди и в канале (не дублируй тему и формулировки):\n"
            + "\n".join(f"- {t[:220]}" for t in avoid_titles[:30])
            if avoid_titles
            else ""
        )

        user_material = "\n\n".join(sources[:8])
        primary = model or self.model
        out_posts: list[dict] = []

        if dev_disabled or not batch:
            avoid_for_llm = avoid_list
            if dev_disabled:
                recent_pub = await self.queue.get_published_posts(5)
                pub_lines = "\n".join(f"- {p['title']}" for p in recent_pub if p.get("title"))
                if pub_lines:
                    avoid_for_llm = f"\n\nНедавно опубликованные темы (не повторяй):\n{pub_lines}"
            if dev_disabled and not (post_dev or "").strip():
                system_prompt = (
                    f"{identity}\n\n{soul}\n\n"
                    "Ты пишешь пост для Telegram-канала от своего имени (агент Балбес).\n"
                    "Выбери одну интересную тему из предоставленных материалов и напиши пост.\n"
                    f"{avoid_for_llm}\n\n"
                    "Ответь строго в формате JSON:\n"
                    '{"title": "...", "content_ru": "...", "content_en": "..."}\n'
                    "Без markdown-блоков, только чистый JSON."
                )
            else:
                system_prompt = self._dev_blog_system_prompt(
                    identity, soul, post_dev, avoid_for_llm, single_topic=None
                )
            raw = await self._call_llm(_llm_messages(system_prompt, user_material), model=primary)
            if not raw.strip() and _normalize_openrouter_model_id(
                primary
            ) != _normalize_openrouter_model_id(self.cheap_model):
                raw = await self._call_llm(
                    _llm_messages(system_prompt, user_material), model=self.cheap_model
                )
            if not raw.strip():
                self._last_post_gen_error = "Модель не вернула текст (проверь OPENROUTER_API_KEY, лимиты или модель в /model)."
                return []
            one = self._parse_post_json(raw, source_refs)
            if not one:
                self._last_post_gen_error = (
                    "Модель вернула ответ не в формате JSON. Попробуй ещё раз или смени модель."
                )
                return []
            return [one]

        max_n = int(dev_cfg.get("max_posts_per_run", 3))
        topics = await self._plan_dev_blog_topics(user_material, avoid_titles, max_n, primary)
        if not topics:
            one = await self._write_one_agent_post_json(
                user_material,
                source_refs,
                None,
                avoid_list,
                identity,
                soul,
                post_dev,
                primary,
            )
            if not one:
                self._last_post_gen_error = (
                    "Планировщик не выделил тем, а черновик по полному материалу не удался. "
                    "Попробуй сменить модель или сузить окно `from_hours`."
                )
                return []
            return [one]

        for t in topics:
            w = await self._write_one_agent_post_json(
                user_material,
                source_refs,
                t,
                avoid_list,
                identity,
                soul,
                post_dev,
                primary,
            )
            if w:
                out_posts.append(w)
        if not out_posts:
            logger.warning(
                "generate_agent_post: batch writers returned nothing for %d topics, fallback to single post",
                len(topics),
            )
            one = await self._write_one_agent_post_json(
                user_material,
                source_refs,
                None,
                avoid_list,
                identity,
                soul,
                post_dev,
                primary,
            )
            if one:
                return [one]
            self._last_post_gen_error = (
                "Планировщик выделил темы, но написать посты не вышло (модель вернула пустой ответ "
                "или невалидный JSON). Попробуй другую модель в /model или отключи пакет тем: "
                "`blogger.dev_blog.batch_topics: false`."
            )
            return []
        return out_posts

    async def generate_user_post(
        self,
        interview_answers: list[str],
        extra_context: str = "",
        model: str | None = None,
    ) -> dict | None:
        """
        Generate a personal blog post (from user perspective) based on check-in answers.
        Returns {title, content_ru, source_refs} or None.
        """
        if not interview_answers:
            return None

        soul = _read_workspace_file("SOUL.md")
        answers_text = "\n".join(f"- {a}" for a in interview_answers)

        system_prompt = (
            f"{soul}\n\n"
            "Ты пишешь пост для личного блога Николая (не от имени ИИ, а от имени человека-предпринимателя).\n"
            "Пост должен быть личным, конкретным, без корпоративного пафоса.\n"
            "Никаких имён сотрудников, никаких коммерческих деталей.\n\n"
            "Ответь строго в формате JSON:\n"
            '{"title": "...", "content_ru": "...", "content_en": "..."}\n'
            "Без markdown-блоков, только чистый JSON."
        )

        user_prompt = f"Ответы на вечерние вопросы:\n{answers_text}" + (
            f"\n\nДополнительный контекст:\n{extra_context}" if extra_context else ""
        )

        raw = await self._call_llm(_llm_messages(system_prompt, user_prompt), model=model)
        return self._parse_post_json(raw, ["checkin:interview"])

    def _parse_post_json(self, raw: str, source_refs: list[str]) -> dict | None:
        """Parse LLM JSON response into post dict."""
        cleaned = (raw or "").strip()
        # Strip markdown code block if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned
        for candidate in (cleaned, _json_object_slice(cleaned)):
            if not (candidate or "").strip():
                continue
            try:
                data = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            n = data.get("notes", "")
            return {
                "title": data.get("title", ""),
                "content_ru": data.get("content_ru", ""),
                "content_en": data.get("content_en", ""),
                "source_refs": list(source_refs),
                "notes": n if isinstance(n, str) else "",
            }
        logger.error("Failed to parse post JSON | raw=%s", cleaned[:400])
        return None

    # =========================================================================
    # Draft creation & approval
    # =========================================================================

    async def create_and_send_draft(
        self,
        post: dict,
        post_type: str = "agent",
    ) -> str | None:
        """
        Save draft to DB and send approval preview to owner.
        Returns post_id or None only if DB insert fails.

        ``blog_channels`` rows are targets for publishing; drafts must persist even when
        none are configured yet.
        """
        post_id = await self.queue.create_draft(
            content_ru=post["content_ru"],
            content_en=post.get("content_en", ""),
            post_type=post_type,
            source_refs=post.get("source_refs", []),
            notes=post.get("notes", ""),
            title=post.get("title", ""),
        )

        # Determine channel label and whether to use business bot
        if post_type == "user":
            channel_label = "личный блог"
            use_biz_bot = True
        else:
            channel_label = "RU-канал + EN-канал"
            use_biz_bot = False

        channels = await self.queue.get_channels()
        if not channels:
            logger.warning(
                "No blog_channels in DB — draft %s saved; configure channels to publish",
                post_id[:8],
            )

        msg_id = await self.publisher.send_approval_preview(
            owner_chat_id=self.owner_private_chat_id,
            post_id=post_id,
            title=post.get("title", "Без заголовка"),
            content_ru=post["content_ru"],
            content_en=post.get("content_en", ""),
            channel_label=channel_label,
            source_refs=post.get("source_refs", []),
            use_business_bot=use_biz_bot,
        )

        if msg_id:
            await self.queue.set_approval_message_id(post_id, msg_id)
            logger.info("Sent approval preview for post %s (msg_id=%s)", post_id, msg_id)
        else:
            logger.warning("Failed to send approval preview for post %s", post_id)

        return post_id

    # =========================================================================
    # Business summary
    # =========================================================================

    async def generate_business_summary(
        self,
        period_hours: int = 24,
        min_messages: int = 10,
    ) -> str | None:
        """
        Generate a business summary from the last N hours of business messages.
        Returns summary text or None if not enough data.
        """
        if not self._biz_reader:
            return None

        from_ts = datetime.now(timezone.utc) - timedelta(hours=period_hours)
        messages = await self._biz_reader.read(from_ts=from_ts, limit=300)

        if len(messages) < min_messages:
            logger.info("Not enough business messages for summary (%d)", len(messages))
            return None

        msgs_text = "\n".join(
            f"[{m.get('chat_name', '?')}] "
            + (f"{m['anon_sender']}: " if m.get("anon_sender") else "")
            + m["content"][:200]
            for m in messages[:150]
        )

        system = (
            "Ты анализируешь обезличенные сообщения из рабочих чатов бизнеса.\n"
            "Напиши краткий саммари (5-10 пунктов) о том, что происходит в бизнесе:\n"
            "- Основные темы обсуждений\n"
            "- Проблемы и решения\n"
            "- Важные решения или события\n"
            "Пиши по-русски, кратко и по делу. Не упоминай имена.\n"
            "Только для внутреннего использования владельца — не для публикации."
        )
        summary = await self._call_llm(
            _llm_messages(system, f"Сообщения за последние {period_hours}ч:\n\n{msgs_text}"),
            model=self.cheap_model,
        )
        return summary.strip() if summary else None

    # =========================================================================
    # Evening check-in
    # =========================================================================

    async def run_evening_checkin(self) -> None:
        """
        Orchestrate the evening check-in:
        1. Generate business summary and send to owner
        2. Send interview questions
        3. Wait for reply (handled by handle_checkin_reply)
        """
        # Business summary
        summary = await self.generate_business_summary()
        if summary:
            await self.publisher.send_business_summary(self.owner_private_chat_id, summary)
            logger.info("Sent business summary to owner")

        # Evening questions
        prompts_text = _read_workspace_file("INTERVIEW_PROMPTS.md")
        system = (
            "Ты — агент-блогер Балбес. Выбери 2-3 вечерних вопроса для check-in.\n"
            "Вопросы должны быть краткими, дружелюбными, без пафоса.\n"
            "Ответь только текстом вопросов, без лишних объяснений."
        )
        questions_text = await self._call_llm(
            _llm_messages(system, prompts_text),
            model=self.cheap_model,
        )

        if not questions_text:
            questions_text = "Как прошёл день? Что удалось сделать?"

        self._checkin_questions = [questions_text]

        if self.business_bot:
            self.business_bot.set_waiting_checkin(self.owner_tg_id, True)

        await self.publisher.send_checkin_questions(self.owner_private_chat_id, questions_text)
        logger.info("Sent evening check-in questions")

    async def handle_checkin_reply(self, owner_id: int, reply_text: str) -> None:
        """
        Called when owner replies to check-in questions.
        Saves interview, evaluates if post-worthy, creates draft if yes.
        """
        # Save to DB
        await self.db.execute(
            """
            INSERT INTO blog_interviews (user_id, interview_type, questions, answers, date)
            VALUES ($1, 'evening', $2::jsonb, $3::jsonb, CURRENT_DATE)
            """,
            str(owner_id),
            json.dumps(self._checkin_questions, ensure_ascii=False),
            json.dumps([reply_text], ensure_ascii=False),
        )

        # Evaluate post worthiness
        system = (
            "Оцени, есть ли в ответе материал для поста в личный блог.\n"
            "Ответь строго: YES или NO.\n"
            "YES — если есть конкретные итоги, решения, наблюдения, планы.\n"
            "NO — если ответ слишком короткий, общий или не содержит ничего интересного."
        )
        verdict = await self._call_llm(
            _llm_messages(system, reply_text),
            model=self.cheap_model,
        )

        if "YES" in (verdict or "").upper():
            post = await self.generate_user_post(interview_answers=[reply_text])
            if post:
                await self.create_and_send_draft(post, post_type="user")
                logger.info("Created personal blog draft from check-in reply")
            else:
                await self.publisher.send_dm(
                    self.owner_private_chat_id,
                    "Не смог сгенерировать пост. Попробуй завтра или задай тему явно.",
                )
        else:
            await self.publisher.send_dm(
                self.owner_private_chat_id,
                "Спасибо! Записал. Сегодня пост не генерирую — маловато материала.",
            )

    # =========================================================================
    # Edit handling
    # =========================================================================

    async def handle_edit_instruction(self, owner_id: int, post_id: str, instruction: str) -> None:
        """
        Revise a post based on owner's edit instruction and re-send for approval.
        """
        post = await self.queue.get_post(post_id)
        if not post:
            await self.publisher.send_dm(self.owner_private_chat_id, f"Пост {post_id} не найден.")
            return

        content = post.get("content") or {}
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                content = {}

        old_ru = content.get("ru", "")
        old_en = content.get("en", "")

        system = (
            "Исправь пост согласно указаниям редактора.\n"
            "Сохрани стиль и общую структуру, только внеси нужные правки.\n"
            "Ответь строго в формате JSON:\n"
            '{"title": "...", "content_ru": "...", "content_en": "..."}\n'
            "Без markdown-блоков, только чистый JSON."
        )
        user = (
            f"Текущий пост (RU):\n{old_ru}\n\n"
            f"Текущий пост (EN):\n{old_en}\n\n"
            f"Указания по правке:\n{instruction}"
        )

        raw = await self._call_llm(_llm_messages(system, user))
        revised = self._parse_post_json(raw, post.get("source_refs") or [])

        if not revised:
            await self.publisher.send_dm(
                self.owner_private_chat_id,
                "Не смог переписать пост. Попробуй ещё раз.",
            )
            return

        await self.queue.update_content(
            post_id,
            content_ru=revised["content_ru"],
            content_en=revised["content_en"],
            title=revised.get("title", ""),
        )

        use_biz = post.get("post_type") == "user"
        msg_id = post.get("approval_message_id")
        channel_label = "личный блог" if use_biz else "RU-канал + EN-канал"

        if msg_id:
            await self.publisher.update_approval_message(
                owner_chat_id=self.owner_private_chat_id,
                message_id=int(msg_id),
                post_id=post_id,
                title=revised.get("title", ""),
                content_ru=revised["content_ru"],
                content_en=revised["content_en"],
                channel_label=channel_label,
                source_refs=revised.get("source_refs", []),
                use_business_bot=use_biz,
            )
        else:
            new_msg_id = await self.publisher.send_approval_preview(
                owner_chat_id=self.owner_private_chat_id,
                post_id=post_id,
                title=revised.get("title", ""),
                content_ru=revised["content_ru"],
                content_en=revised["content_en"],
                channel_label=channel_label,
                source_refs=revised.get("source_refs", []),
                use_business_bot=use_biz,
            )
            if new_msg_id:
                await self.queue.set_approval_message_id(post_id, new_msg_id)

    # ── Memory-Service backed multi-chat helpers ─────────────────────────────

    def _bbot_uid(self, owner_id: int) -> str:
        """Memory `user_id` for blogger agent: ``blogger_<telegram_id>`` (see shared.telegram_app.memory_namespace)."""
        return memory_user_id("blogger", owner_id)

    async def bbot_get_chats(self, owner_id: int) -> list[dict]:
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(f"{self.memory_url}/api/v1/chats/{uid}")
                if r.is_success:
                    chats = r.json().get("chats", []) or []
                    if chats:
                        return chats
            except Exception as exc:
                logger.warning("bbot_get_chats uid=%s: %s", uid, exc)
        return []

    async def bbot_get_active_chat(self, owner_id: int) -> str:
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(f"{self.memory_url}/api/v1/chats/{uid}/active")
                if r.is_success:
                    cid = r.json().get("chat_id", "default")
                    if cid != "default":
                        return cid
            except Exception as exc:
                logger.warning("bbot_get_active_chat uid=%s: %s", uid, exc)
        return "default"

    async def bbot_set_active_chat(self, owner_id: int, chat_id: str) -> None:
        try:
            await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/active",
                params={"chat_id": chat_id},
            )
        except Exception as exc:
            logger.warning("bbot_set_active_chat: %s", exc)

    async def bbot_create_chat(self, owner_id: int, name: str) -> str:
        try:
            r = await self._get_http().post(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}",
                json={"name": name},
            )
            return r.json().get("chat_id", "default") if r.is_success else "default"
        except Exception as exc:
            logger.warning("bbot_create_chat: %s", exc)
            return "default"

    async def bbot_rename_chat(self, owner_id: int, chat_id: str, name: str) -> None:
        try:
            await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/name",
                json={"name": name},
            )
        except Exception as exc:
            logger.warning("bbot_rename_chat: %s", exc)

    async def bbot_clear_history(self, owner_id: int, chat_id: str) -> None:
        try:
            await self._get_http().delete(
                f"{self.memory_url}/api/v1/history/{self._bbot_uid(owner_id)}/{chat_id}"
            )
        except Exception as exc:
            logger.warning("bbot_clear_history: %s", exc)

    async def bbot_get_history(self, owner_id: int, chat_id: str) -> list[dict]:
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(
                    f"{self.memory_url}/api/v1/history/{uid}/{chat_id}",
                    params={"limit": 40},
                )
                if r.is_success:
                    messages = r.json().get("messages", []) or []
                    if messages:
                        return messages
            except Exception as exc:
                logger.warning("bbot_get_history uid=%s: %s", uid, exc)
        return []

    async def bbot_save_message(self, owner_id: int, chat_id: str, role: str, content: str) -> None:
        try:
            await self._get_http().post(
                f"{self.memory_url}/api/v1/history/{self._bbot_uid(owner_id)}/{chat_id}",
                json={"role": role, "content": content},
            )
        except Exception as exc:
            logger.warning("bbot_save_message: %s", exc)

    async def bbot_get_chat_model(self, owner_id: int, chat_id: str) -> str:
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(
                    f"{self.memory_url}/api/v1/chats/{uid}/{chat_id}/model"
                )
                if r.is_success:
                    mid = r.json().get("model_id")
                    if mid:
                        return mid
            except Exception:
                pass
        return self._conversation_model

    async def bbot_set_chat_model(self, owner_id: int, chat_id: str, model: str) -> None:
        try:
            await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/model",
                json={"model_id": model},
            )
        except Exception as exc:
            logger.warning("bbot_set_chat_model: %s", exc)

    async def bbot_get_chat_settings(self, owner_id: int, chat_id: str) -> dict:
        """Return {debug: bool, mode: str} for a bbot chat (Memory Service)."""
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(
                    f"{self.memory_url}/api/v1/chats/{uid}/{chat_id}/settings"
                )
                if r.status_code == 200:
                    return r.json()
            except Exception as exc:
                logger.debug("bbot_get_chat_settings uid=%s: %s", uid, exc)
        return {"debug": False, "mode": "ask"}

    async def bbot_set_chat_settings(self, owner_id: int, chat_id: str, **kwargs) -> bool:
        """Update per-chat settings (debug=, mode=) for bbot namespace."""
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/settings",
                json={k: v for k, v in kwargs.items() if v is not None},
            )
            return r.status_code == 200
        except Exception as exc:
            logger.debug("bbot_set_chat_settings: %s", exc)
        return False

    async def bbot_get_chat_agent(self, owner_id: int, chat_id: str) -> str:
        for uid in blogger_memory_user_ids_try_order(owner_id):
            try:
                r = await self._get_http().get(
                    f"{self.memory_url}/api/v1/chats/{uid}/{chat_id}/agent"
                )
                if r.status_code == 200:
                    return r.json().get("agent_id", "balbes")
            except Exception as exc:
                logger.warning("bbot_get_chat_agent uid=%s: %s", uid, exc)
        return "balbes"

    async def bbot_set_chat_agent(self, owner_id: int, chat_id: str, agent_id: str) -> bool:
        try:
            r = await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/agent",
                json={"agent_id": agent_id},
            )
            return r.status_code == 200
        except Exception as exc:
            logger.warning("bbot_set_chat_agent: %s", exc)
        return False

    def set_conversation_model(self, model: str) -> None:
        """Set the default LLM model for new bbot conversations."""
        self._conversation_model = model
        logger.info("Conversation model set to: %s", model)

    def _bbot_trace_enabled(self, memory_debug_flag: bool) -> bool:
        """Per-chat /debug, env BLOGGER_TELEGRAM_DEBUG_TRACE, or blogger.telegram_debug_trace in YAML."""
        if memory_debug_flag:
            return True
        try:
            if get_settings().blogger_telegram_debug_trace:
                return True
        except Exception:
            pass
        try:
            cfg = get_providers_config() or {}
            return bool((cfg.get("blogger") or {}).get("telegram_debug_trace", False))
        except Exception:
            return False

    async def _bbot_trace_line(
        self,
        debug_reply: Callable[[str], Awaitable[None]] | None,
        line: str,
    ) -> None:
        """Trace to Telegram (``debug_reply``) or to logs if reply is None (e.g. HTTP delegate)."""
        if debug_reply is not None:
            await debug_reply(line)
        else:
            plain = re.sub(r"<[^>]+>", " ", line)
            logger.info("bbot trace: %s", plain[:3000])

    async def _run_unified_tool_loop(
        self,
        *,
        system: str,
        working: list[dict],
        model: str,
        owner_id: int,
        chat_id: str,
        reply_fn,
        debug_reply: Callable[[str], Awaitable[None]] | None,
        debug_on: bool,
        persist_bbot_assistant: bool,
        max_rounds: int = 8,
    ) -> None:
        """
        OpenRouter multi-round loop + shared ToolDispatcher (registry + allowlist
        for agent id ``blogger`` in providers.yaml), same contract as OrchestratorAgent.
        """
        if not (self.api_key or "").strip():
            await reply_fn("⚠️ Не задан OPENROUTER_API_KEY — LLM недоступен.")
            return

        settings = get_settings()
        resolved = resolve_tools_for_agent_with_manifest("blogger", "agent", get_providers_config())
        tools = build_subagent_tools(resolved)
        if not tools:
            await reply_fn("⚠️ Нет инструментов для агента blogger (проверь config/providers.yaml).")
            return

        dispatcher = self._get_tool_dispatcher()
        dispatcher.reset_call_counts()

        http = self._get_http()
        headers = openrouter_json_headers(settings, api_key=self.api_key)
        model_id = _normalize_openrouter_model_id(model)

        tool_context: dict = {
            "user_id": str(owner_id),
            "chat_id": chat_id,
            "agent_id": "blogger",
            "memory_service_url": settings.memory_service_url,
            "openrouter_api_key": settings.openrouter_api_key,
            "blogger_service_port": settings.blogger_service_port,
            "coder_service_port": getattr(settings, "coder_service_port", 8104),
            "orchestrator_port": settings.orchestrator_port,
            "mode": "agent",
            "source": "blogger_service",
            "model_id": model,
        }

        trace = bool(debug_on)
        if trace:
            await self._bbot_trace_line(
                debug_reply,
                f"🧩 <b>bbot trace on</b> · tools={len(tools)} · <code>agent_id=blogger</code>",
            )
            logger.info(
                "blogger bbot trace: tools=%d owner_id=%s chat_id=%s", len(tools), owner_id, chat_id
            )

        for _round in range(max_rounds):
            if len(working) > 28:
                working = working[-28:]

            messages = [{"role": "system", "content": system}] + working

            if trace:
                await self._bbot_trace_line(
                    debug_reply,
                    f"⚙️ <b>LLM</b> раунд {_round + 1}/{max_rounds} → "
                    f"<code>{html.escape(model_id)}</code> · msg={len(messages)}",
                )

            payload_tools = {
                "model": model_id,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "max_tokens": 1500,
                "temperature": 0.7,
            }
            payload_plain = {
                "model": model_id,
                "messages": messages,
                "max_tokens": 1500,
                "temperature": 0.7,
            }

            retried_without_tools = False
            try:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload_tools,
                    timeout=120.0,
                )
                if resp.status_code != 200:
                    try:
                        err_json = resp.json()
                        detail = err_json.get("error", err_json)
                    except Exception:
                        detail = resp.text[:1500]
                    logger.error(
                        "OpenRouter (tools) HTTP %s model=%s: %s",
                        resp.status_code,
                        model_id,
                        detail,
                    )
                    if trace:
                        await self._bbot_trace_line(
                            debug_reply,
                            f"↩️ <b>retry</b> без tools (первый ответ HTTP {resp.status_code})",
                        )
                    retried_without_tools = True
                    resp = await http.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=payload_plain,
                        timeout=120.0,
                    )
                    if resp.status_code != 200:
                        try:
                            err_json = resp.json()
                            detail2 = err_json.get("error", err_json)
                        except Exception:
                            detail2 = resp.text[:800]
                        logger.error(
                            "OpenRouter (plain) HTTP %s model=%s: %s",
                            resp.status_code,
                            model_id,
                            detail2,
                        )
                        short = str(detail2)[:350]
                        await reply_fn(
                            f"⚠️ OpenRouter: HTTP {resp.status_code}\n{short}\n\n"
                            "Проверь ключ, квоту или выбери другую модель: /model"
                        )
                        return

                data = resp.json()
                if "choices" not in data or not data["choices"]:
                    logger.error("OpenRouter returned no choices: %s", data)
                    await reply_fn("⚠️ Пустой ответ от модели. Попробуй /model и другую модель.")
                    return
            except Exception as exc:
                logger.exception("blogger unified tool loop LLM error: %s", exc)
                await reply_fn(f"⚠️ Сеть/LLM: {exc!s:.200}")
                return

            if trace:
                usage = data.get("usage") or {}
                if isinstance(usage, dict) and any(
                    usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")
                ):
                    pt = usage.get("prompt_tokens", "?")
                    ct = usage.get("completion_tokens", "?")
                    tt = usage.get("total_tokens", "?")
                    await self._bbot_trace_line(
                        debug_reply,
                        f"📊 <b>usage</b> prompt={pt} completion={ct} total={tt}",
                    )
                else:
                    await self._bbot_trace_line(
                        debug_reply,
                        "📊 <b>usage</b> (нет в ответе)",
                    )

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            if trace:
                n_tc = len(msg.get("tool_calls") or [])
                await self._bbot_trace_line(
                    debug_reply,
                    f"✳️ <b>finish</b> <code>{html.escape(str(finish_reason))}</code> · "
                    f"tool_calls={n_tc}"
                    + (f" · plain_retry={retried_without_tools}" if retried_without_tools else ""),
                )
                logger.info(
                    "blogger bbot round %s finish=%s tool_calls=%s",
                    _round + 1,
                    finish_reason,
                    n_tc,
                )

            if finish_reason != "tool_calls" or not msg.get("tool_calls"):
                answer = msg.get("content") or ""
                if answer:
                    working.append({"role": "assistant", "content": answer})
                    if persist_bbot_assistant:
                        await self.bbot_save_message(owner_id, chat_id, "assistant", answer)
                    await reply_fn(answer)
                return

            working.append(msg)

            for tc in msg.get("tool_calls", []):
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except Exception:
                    args = {}

                if trace:
                    arg_preview = html.escape(json.dumps(args, ensure_ascii=False)[:600])
                    await self._bbot_trace_line(
                        debug_reply,
                        f"🔧 <b>{html.escape(fn_name)}</b> <code>{arg_preview}</code>",
                    )

                tool_result = await dispatcher.dispatch(fn_name, args, tool_context)
                if trace:
                    tr = str(tool_result)
                    max_prev = 2000
                    if len(tr) > max_prev:
                        tr = tr[:max_prev] + "…"
                    safe = html.escape(tr, quote=True)
                    await self._bbot_trace_line(
                        debug_reply,
                        f"📤 <b>→ {html.escape(fn_name)}</b>\n<pre>{safe}</pre>",
                    )
                    logger.info(
                        "blogger bbot tool_done name=%s result_len=%s",
                        fn_name,
                        len(str(tool_result)),
                    )
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": str(tool_result),
                    }
                )

        await reply_fn("Не смог завершить задачу за отведённое количество шагов.")

    async def handle_owner_message(
        self,
        owner_id: int,
        text: str,
        reply_fn,
        debug_reply: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        """
        Private business-bot chat: same registry + ToolDispatcher as orchestrator
        (``tools_allowlist`` for agent ``blogger`` in providers.yaml).
        """
        system = self._get_bbot_system_prompt()

        chat_id = await self.bbot_get_active_chat(owner_id)
        model = await self.bbot_get_chat_model(owner_id, chat_id)
        settings = await self.bbot_get_chat_settings(owner_id, chat_id)
        debug_on = self._bbot_trace_enabled(bool(settings.get("debug", False)))

        await self.bbot_save_message(owner_id, chat_id, "user", text)

        stored = await self.bbot_get_history(owner_id, chat_id)
        working: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in stored
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]

        await self._run_unified_tool_loop(
            system=system,
            working=working,
            model=model,
            owner_id=owner_id,
            chat_id=chat_id,
            reply_fn=reply_fn,
            debug_reply=debug_reply,
            debug_on=debug_on,
            persist_bbot_assistant=True,
        )

    async def execute_delegate_task(self, task: str, user_id: str = "unknown") -> str:
        """
        HTTP delegate (POST /api/v1/agent/execute): same tool loop as the business bot.
        """
        try:
            uid = int(str(user_id).strip()) if str(user_id).strip().isdigit() else self.owner_tg_id
        except (ValueError, TypeError):
            uid = self.owner_tg_id
        chat_id = await self.bbot_get_active_chat(uid) or "default"
        model = await self.bbot_get_chat_model(uid, chat_id)
        system = self._get_bbot_system_prompt()
        working: list[dict] = [{"role": "user", "content": task}]
        parts: list[str] = []

        async def _collect(t: str) -> None:
            parts.append(t)

        await self._run_unified_tool_loop(
            system=system,
            working=working,
            model=model,
            owner_id=uid,
            chat_id=chat_id,
            reply_fn=_collect,
            debug_reply=None,
            debug_on=self._bbot_trace_enabled(False),
            persist_bbot_assistant=False,
        )
        return "\n\n".join(parts).strip() or "(пустой ответ модели)"

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
