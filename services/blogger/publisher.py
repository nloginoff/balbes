"""
Telegram channel publisher for blog posts.

Sends posts to configured Telegram channels using the main bot token
(the same bot must be added as admin to all channels).
"""

import logging

import httpx

logger = logging.getLogger("blogger.publisher")

_TG_API = "https://api.telegram.org/bot{token}/{method}"
_MAX_MESSAGE_LEN = 4096


def _split_text(text: str, limit: int = _MAX_MESSAGE_LEN) -> list[str]:
    """Split text into chunks not exceeding limit, splitting at newlines where possible."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


class TelegramPublisher:
    """
    Publishes posts to Telegram channels and sends draft approval previews via DM.
    Channel posts use the main TELEGRAM_BOT_TOKEN (bot must be channel admin).
    When BUSINESS_BOT_TOKEN is set, draft previews with approve/edit/reject buttons
    go through the business bot; otherwise the main bot is used.
    """

    def __init__(
        self,
        main_bot_token: str,
        business_bot_token: str | None,
        http: httpx.AsyncClient,
    ):
        self.main_token = main_bot_token
        self.business_token = business_bot_token
        self.http = http

    @property
    def approvals_use_business_bot(self) -> bool:
        """If True, draft approval DMs and inline buttons are sent via business bot; else main bot."""
        return bool(self.business_token)

    async def _send(
        self,
        token: str,
        chat_id: str | int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: dict | None = None,
    ) -> dict | None:
        """Send a single Telegram message."""
        url = _TG_API.format(token=token, method="sendMessage")
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = await self.http.post(url, json=payload, timeout=15.0)
            data = resp.json()
            if not data.get("ok"):
                logger.error("Telegram sendMessage error: %s", data)
                return None
            return data.get("result")
        except Exception as exc:
            logger.error("TelegramPublisher._send error: %s", exc)
            return None

    async def _edit_message(
        self,
        token: str,
        chat_id: str | int,
        message_id: int,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: dict | None = None,
    ) -> bool:
        url = _TG_API.format(token=token, method="editMessageText")
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            resp = await self.http.post(url, json=payload, timeout=15.0)
            return resp.json().get("ok", False)
        except Exception as exc:
            logger.error("TelegramPublisher._edit error: %s", exc)
            return False

    async def _delete_message(self, token: str, chat_id: str | int, message_id: int) -> bool:
        url = _TG_API.format(token=token, method="deleteMessage")
        try:
            resp = await self.http.post(
                url, json={"chat_id": chat_id, "message_id": message_id}, timeout=10.0
            )
            return resp.json().get("ok", False)
        except Exception as exc:
            logger.error("TelegramPublisher._delete error: %s", exc)
            return False

    async def publish_to_channel(self, channel_id: str, text: str) -> bool:
        """
        Publish text to a Telegram channel.
        Splits long messages automatically.
        Returns True on success.
        """
        chunks = _split_text(text)
        success = True
        for chunk in chunks:
            result = await self._send(self.main_token, channel_id, chunk)
            if result is None:
                success = False
        return success

    async def send_approval_preview(
        self,
        owner_chat_id: str | int,
        post_id: str,
        title: str,
        content_ru: str,
        content_en: str,
        channel_label: str,
        source_refs: list[str],
        use_business_bot: bool = False,
    ) -> int | None:
        """
        Send draft preview to the owner with inline approval buttons.
        Returns Telegram message_id for later editing, or None on failure.

        use_business_bot=True sends via business bot (for personal channel posts).
        """
        token = (
            self.business_token if (use_business_bot and self.business_token) else self.main_token
        )

        sources_str = ", ".join(source_refs[:5]) if source_refs else "нет источников"
        preview = f"✍️ *Черновик поста [{channel_label}]*\n\n📌 {title}\n\n{content_ru[:1500]}"
        if content_en:
            preview += f"\n\n---\n🌍 *EN version:*\n{content_en[:1000]}"
        preview += f"\n\n_Источники: {sources_str}_"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Опубликовать", "callback_data": f"blog_approve:{post_id}"},
                    {"text": "✏️ Исправить", "callback_data": f"blog_edit:{post_id}"},
                    {"text": "❌ Отклонить", "callback_data": f"blog_reject:{post_id}"},
                ]
            ]
        }

        result = await self._send(token, owner_chat_id, preview, reply_markup=keyboard)
        if result:
            return result.get("message_id")
        return None

    async def update_approval_message(
        self,
        owner_chat_id: str | int,
        message_id: int,
        post_id: str,
        title: str,
        content_ru: str,
        content_en: str,
        channel_label: str,
        source_refs: list[str],
        use_business_bot: bool = False,
    ) -> bool:
        """Update an existing approval preview message (after revision)."""
        token = (
            self.business_token if (use_business_bot and self.business_token) else self.main_token
        )

        sources_str = ", ".join(source_refs[:5]) if source_refs else "нет источников"
        preview = (
            f"✍️ *Черновик поста (исправленный) [{channel_label}]*\n\n"
            f"📌 {title}\n\n"
            f"{content_ru[:1500]}"
        )
        if content_en:
            preview += f"\n\n---\n🌍 *EN version:*\n{content_en[:1000]}"
        preview += f"\n\n_Источники: {sources_str}_"

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ Опубликовать", "callback_data": f"blog_approve:{post_id}"},
                    {"text": "✏️ Исправить ещё", "callback_data": f"blog_edit:{post_id}"},
                    {"text": "❌ Отклонить", "callback_data": f"blog_reject:{post_id}"},
                ]
            ]
        }
        return await self._edit_message(
            token, owner_chat_id, message_id, preview, reply_markup=keyboard
        )

    async def send_business_summary(
        self,
        owner_chat_id: str | int,
        summary: str,
    ) -> bool:
        """Send business summary to owner via business bot."""
        token = self.business_token or self.main_token
        text = f"📊 *Бизнес-саммари за день*\n\n{summary}"
        chunks = _split_text(text)
        for chunk in chunks:
            result = await self._send(token, owner_chat_id, chunk)
            if result is None:
                return False
        return True

    async def send_checkin_questions(
        self,
        owner_chat_id: str | int,
        questions: str,
    ) -> int | None:
        """Send evening check-in questions. Returns message_id."""
        token = self.business_token or self.main_token
        text = f"🌙 *Вечерний check-in*\n\n{questions}"
        result = await self._send(token, owner_chat_id, text)
        return result.get("message_id") if result else None

    async def send_dm(
        self,
        owner_chat_id: str | int,
        text: str,
        use_business_bot: bool = True,
    ) -> int | None:
        """Send a plain DM to the owner."""
        token = (
            self.business_token if (use_business_bot and self.business_token) else self.main_token
        )
        chunks = _split_text(text)
        last_id = None
        for chunk in chunks:
            result = await self._send(token, owner_chat_id, chunk)
            if result:
                last_id = result.get("message_id")
        return last_id
