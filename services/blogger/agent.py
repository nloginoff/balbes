"""
BloggerAgent — LLM-powered blog post generator.

Reads from three sources (agent chats, Cursor MD files, business messages),
generates posts in RU and EN, creates drafts and sends them for approval.
Also handles evening check-in interviews and business summaries.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import httpx

from .post_queue import PostQueue
from .publisher import TelegramPublisher
from .reader import BusinessChatReader, ChatReader, CursorFileReader

logger = logging.getLogger("blogger.agent")

_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
_WORKSPACE = _PROJECT_ROOT / "data" / "agents" / "blogger"

_DEFAULT_MODEL = "openrouter/minimax/minimax-m2.5:free"
_CHEAP_MODEL = "openrouter/meta-llama/llama-3.1-8b-instruct:free"


def _read_workspace_file(name: str) -> str:
    p = _WORKSPACE / name
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _llm_messages(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


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
    ):
        self.api_key = openrouter_api_key
        self.db = db
        self.queue = post_queue
        self.publisher = publisher
        self.memory_url = memory_url.rstrip("/")
        self.owner_tg_id = owner_tg_id
        self.owner_private_chat_id = owner_private_chat_id or owner_tg_id
        self.model = model or _DEFAULT_MODEL

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

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=120.0)
        return self._http

    def set_memory_url(self, url: str) -> None:
        self._chat_reader = ChatReader(url, self._get_http())

    def set_biz_reader(self, reader: BusinessChatReader) -> None:
        self._biz_reader = reader

    async def _call_llm(self, messages: list[dict], model: str | None = None) -> str:
        """Call OpenRouter LLM. Returns text content."""
        http = self._get_http()
        used_model = model or self.model
        try:
            resp = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/nloginoff/balbes",
                    "X-Title": "Balbes Blogger Agent",
                },
                json={
                    "model": used_model,
                    "messages": messages,
                    "max_tokens": 2048,
                },
                timeout=90.0,
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except Exception as exc:
            logger.error("LLM call failed (%s): %s", used_model, exc)
            return ""

    # =========================================================================
    # Post generation
    # =========================================================================

    async def generate_agent_post(
        self,
        agents: list[str] | None = None,
        cursor_files: int = 2,
        from_hours: int = 48,
    ) -> dict | None:
        """
        Generate a new post from owner's chat history and Cursor files.
        Returns {title, content_ru, content_en, source_refs} or None.

        Args:
            agents:       Ignored (kept for API compatibility). History is read
                          from the owner's Telegram chats via Memory Service.
            cursor_files: Number of most recent Cursor AI markdown files to include.
            from_hours:   How far back to read chat history.
        """
        from_ts = datetime.now(timezone.utc) - timedelta(hours=from_hours)

        sources = []
        source_refs: list[str] = []

        # Owner's chat history (all chats from Memory Service)
        if self._chat_reader:
            msgs = await self._chat_reader.read(
                user_id=str(self.owner_tg_id),
                from_ts=from_ts,
                limit=60,
            )
            if msgs:
                chat_text = "\n".join(
                    f"[{m.get('chat_name', '?')}|{m['role']}]: {m['content'][:400]}"
                    for m in msgs[:60]
                )
                sources.append(f"=== История чатов (последние {from_hours}ч) ===\n{chat_text}")
                source_refs.append(f"chat_history:{from_ts.date().isoformat()}")

        # Cursor files
        cursor_data = self._cursor_reader.read_latest(cursor_files)
        for cf in cursor_data:
            sources.append(f"=== Cursor: {cf['path']} ===\n{cf['content'][:2000]}")
            source_refs.append(f"cursor:{cf['path']}")

        if not sources:
            logger.info("No source material for agent post")
            return None

        identity = _read_workspace_file("IDENTITY.md")
        soul = _read_workspace_file("SOUL.md")

        # Check recent posts for context
        recent = await self.queue.get_published_posts(limit=5)
        recent_titles = "\n".join(f"- {p['title']}" for p in recent if p.get("title"))
        avoid_note = (
            f"\nНедавно опубликованные темы (не повторяй):\n{recent_titles}"
            if recent_titles
            else ""
        )

        system_prompt = (
            f"{identity}\n\n{soul}\n\n"
            "Ты пишешь пост для Telegram-канала от своего имени (агент Балбес).\n"
            "Выбери одну интересную тему из предоставленных материалов и напиши пост.\n"
            f"{avoid_note}\n\n"
            "Ответь строго в формате JSON:\n"
            '{"title": "...", "content_ru": "...", "content_en": "..."}\n'
            "Без markdown-блоков, только чистый JSON."
        )

        user_prompt = "\n\n".join(sources[:5])

        raw = await self._call_llm(_llm_messages(system_prompt, user_prompt))
        return self._parse_post_json(raw, source_refs)

    async def generate_user_post(
        self,
        interview_answers: list[str],
        extra_context: str = "",
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

        raw = await self._call_llm(_llm_messages(system_prompt, user_prompt))
        return self._parse_post_json(raw, ["checkin:interview"])

    def _parse_post_json(self, raw: str, source_refs: list[str]) -> dict | None:
        """Parse LLM JSON response into post dict."""
        raw = raw.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw
        try:
            data = json.loads(raw)
            return {
                "title": data.get("title", ""),
                "content_ru": data.get("content_ru", ""),
                "content_en": data.get("content_en", ""),
                "source_refs": source_refs,
            }
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse post JSON: %s | raw=%s", exc, raw[:200])
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
        Returns post_id or None.
        """
        channels = await self.queue.get_channels()
        if not channels:
            logger.warning("No active blog channels configured")
            return None

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
            model=_CHEAP_MODEL,
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
            model=_CHEAP_MODEL,
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
            model=_CHEAP_MODEL,
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
        """Unique Memory Service user_id for business bot chats (isolated from main bot)."""
        return f"bbot_{owner_id}"

    async def bbot_get_chats(self, owner_id: int) -> list[dict]:
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}"
            )
            return r.json().get("chats", []) if r.is_success else []
        except Exception as exc:
            logger.warning("bbot_get_chats: %s", exc)
            return []

    async def bbot_get_active_chat(self, owner_id: int) -> str:
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/active"
            )
            return r.json().get("chat_id", "default") if r.is_success else "default"
        except Exception as exc:
            logger.warning("bbot_get_active_chat: %s", exc)
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
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/history/{self._bbot_uid(owner_id)}/{chat_id}",
                params={"limit": 40},
            )
            return r.json().get("messages", []) if r.is_success else []
        except Exception as exc:
            logger.warning("bbot_get_history: %s", exc)
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
        try:
            r = await self._get_http().get(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/model"
            )
            return (
                r.json().get("model_id") or self._conversation_model
                if r.is_success
                else self._conversation_model
            )
        except Exception:
            return self._conversation_model

    async def bbot_set_chat_model(self, owner_id: int, chat_id: str, model: str) -> None:
        try:
            await self._get_http().put(
                f"{self.memory_url}/api/v1/chats/{self._bbot_uid(owner_id)}/{chat_id}/model",
                json={"model_id": model},
            )
        except Exception as exc:
            logger.warning("bbot_set_chat_model: %s", exc)

    def set_conversation_model(self, model: str) -> None:
        """Set the default LLM model for new bbot conversations."""
        self._conversation_model = model
        logger.info("Conversation model set to: %s", model)

    async def handle_owner_message(
        self,
        owner_id: int,
        text: str,
        reply_fn,
    ) -> None:
        """
        Handle a free-form message from the owner in private business-bot chat.

        Maintains per-owner conversation history, provides LLM access with
        a set of blogger tools (list drafts, approve/reject, create post, etc.).
        Calls reply_fn(text) to send a response back.
        """
        # ── system prompt ────────────────────────────────────────────────────
        identity = _read_workspace_file("IDENTITY.md")
        soul = _read_workspace_file("SOUL.md")
        system = (
            f"{identity}\n\n{soul}\n\n"
            "Ты общаешься с владельцем проекта в приватном чате.\n"
            "Отвечай кратко, по делу, на русском языке.\n"
            "Если нужно — используй доступные инструменты."
        )

        # ── tool definitions ─────────────────────────────────────────────────
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "list_drafts",
                    "description": "Показать список постов в черновиках (статус draft/pending).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["draft", "pending", "approved", "published", "rejected"],
                                "description": "Фильтр по статусу. По умолчанию draft.",
                            }
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "approve_post",
                    "description": "Одобрить пост для публикации по его ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"post_id": {"type": "string", "description": "UUID поста"}},
                        "required": ["post_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reject_post",
                    "description": "Отклонить пост по его ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"post_id": {"type": "string", "description": "UUID поста"}},
                        "required": ["post_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_post_from_idea",
                    "description": (
                        "Сгенерировать и сохранить пост-черновик из идеи/темы от владельца."
                        " Пост будет отправлен на согласование."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "idea": {
                                "type": "string",
                                "description": "Тема или идея для поста (от лица владельца)",
                            },
                            "post_type": {
                                "type": "string",
                                "enum": ["user", "agent"],
                                "description": "user — от имени Николая, agent — от имени Балбеса",
                            },
                        },
                        "required": ["idea"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_post_now",
                    "description": "Немедленно сгенерировать новый пост по последним чатам и файлам.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_business_summary",
                    "description": "Сгенерировать саммари по бизнес-чатам за последние 24 часа.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_published_posts",
                    "description": "Показать последние опубликованные посты.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Количество постов (по умолчанию 5)",
                            }
                        },
                    },
                },
            },
        ]

        # ── history management ───────────────────────────────────────────────
        history = self._owner_history.setdefault(owner_id, [])
        history.append({"role": "user", "content": text})
        # keep last 30 messages to avoid blowing context
        if len(history) > 30:
            history[:] = history[-30:]

        # ── agentic tool-call loop (max 5 rounds) ────────────────────────────
        MAX_ROUNDS = 5
        for _round in range(MAX_ROUNDS):
            messages = [{"role": "system", "content": system}] + history

            http = self._get_http()
            try:
                resp = await http.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://github.com/nloginoff/balbes",
                        "X-Title": "Balbes Blogger Agent",
                    },
                    json={
                        "model": self._conversation_model.removeprefix("openrouter/"),
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": "auto",
                        "max_tokens": 1500,
                        "temperature": 0.7,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("handle_owner_message LLM error: %s", exc)
                await reply_fn("⚠️ Ошибка при обращении к LLM. Попробуй ещё раз.")
                return

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "stop")

            # ── text response ─────────────────────────────────────────────
            if finish_reason != "tool_calls" or not msg.get("tool_calls"):
                answer = msg.get("content") or ""
                if answer:
                    history.append({"role": "assistant", "content": answer})
                    await reply_fn(answer)
                return

            # ── tool calls ────────────────────────────────────────────────
            history.append(msg)  # assistant message with tool_calls

            for tc in msg.get("tool_calls", []):
                fn_name = tc.get("function", {}).get("name", "")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}

                tool_result = await self._dispatch_conversation_tool(fn_name, args)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": str(tool_result),
                    }
                )

        # fallback if we exhausted rounds
        await reply_fn("Не смог завершить задачу за отведённое количество шагов.")

    async def _dispatch_conversation_tool(self, name: str, args: dict) -> str:
        """Execute a conversation tool and return string result."""
        try:
            if name == "list_drafts":
                status = args.get("status", "draft")
                posts = await self.queue.list_posts(status=status, limit=10)
                if not posts:
                    return f"Нет постов со статусом '{status}'."
                lines = [f"Посты ({status}):"]
                for p in posts:
                    lines.append(
                        f"• [{p.get('id', '')[:8]}] {p.get('title', '(без названия)')} "
                        f"— {p.get('post_type', '')} ({p.get('status', '')})"
                    )
                return "\n".join(lines)

            elif name == "approve_post":
                post_id = args.get("post_id", "")
                ok = await self.queue.approve(post_id)
                return (
                    f"Пост {post_id[:8]} одобрен."
                    if ok
                    else f"Не удалось одобрить пост {post_id[:8]}."
                )

            elif name == "reject_post":
                post_id = args.get("post_id", "")
                ok = await self.queue.reject(post_id)
                return (
                    f"Пост {post_id[:8]} отклонён."
                    if ok
                    else f"Не удалось отклонить пост {post_id[:8]}."
                )

            elif name == "create_post_from_idea":
                idea = args.get("idea", "")
                post_type = args.get("post_type", "user")
                system = (
                    "Ты — AI-блогер Балбес. Напиши пост на основе идеи от владельца.\n"
                    "Ответь строго в JSON:\n"
                    '{"title": "...", "content_ru": "...", "content_en": "..."}\n'
                    "Без markdown-блоков."
                )
                raw = await self._call_llm(
                    _llm_messages(system, f"Идея для поста:\n{idea}"),
                    model=self._conversation_model,
                )
                parsed = self._parse_post_json(raw, [f"owner_idea: {idea[:60]}"])
                if not parsed:
                    return "Не удалось сгенерировать пост из идеи."
                parsed["post_type"] = post_type
                draft_id = await self.create_and_send_draft(parsed, post_type=post_type)
                return f"Черновик создан и отправлен на согласование. ID: {draft_id[:8] if draft_id else '?'}"

            elif name == "generate_post_now":
                post = await self.generate_agent_post()
                if not post:
                    return "Не нашлось новых материалов для генерации поста."
                draft_id = await self.create_and_send_draft(post, post_type="agent")
                return f"Пост сгенерирован и отправлен на согласование. ID: {draft_id[:8] if draft_id else '?'}"

            elif name == "get_business_summary":
                summary = await self.generate_business_summary()
                return summary or "Недостаточно бизнес-сообщений для саммари."

            elif name == "get_published_posts":
                limit = args.get("limit", 5)
                posts = await self.queue.get_published_posts(limit=limit)
                if not posts:
                    return "Нет опубликованных постов."
                lines = [f"Последние {len(posts)} опубликованных постов:"]
                for p in posts:
                    ts = p.get("published_at", "")
                    lines.append(f"• {p.get('title', '(без названия)')} — {ts}")
                return "\n".join(lines)

            else:
                return f"Неизвестный инструмент: {name}"

        except Exception as exc:
            logger.error("_dispatch_conversation_tool %s error: %s", name, exc)
            return f"Ошибка при выполнении {name}: {exc}"

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
