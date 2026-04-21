"""Mirror sends only when target channel's active Memory chat matches (unit, mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_mirror_skips_when_memory_chat_id_empty() -> None:
    from shared.outbound import mirror as m

    settings = SimpleNamespace(
        agent_reply_mirror_enabled=True,
        agent_reply_mirror_providers="telegram,max",
        agent_reply_mirror_presence_ttl_seconds=3600,
        max_bot_token="t",
        max_api_url="https://x",
        telegram_bot_token="tg",
    )
    with patch.object(m, "list_identity_peers", new_callable=AsyncMock) as lp:
        await m.mirror_agent_text_to_secondaries(
            settings=settings,
            client=AsyncMock(),
            memory_url="http://m",
            canonical_user_id="u1",
            source_channel="telegram",
            memory_chat_id="",
            text="hi",
            telegram_bot=None,
        )
        lp.assert_not_called()


@pytest.mark.asyncio
async def test_mirror_skips_when_target_active_differs() -> None:
    from shared.outbound import mirror as m

    settings = SimpleNamespace(
        agent_reply_mirror_enabled=True,
        agent_reply_mirror_providers="max",
        agent_reply_mirror_presence_ttl_seconds=3600,
        max_bot_token="t",
        max_api_url="https://x",
        telegram_bot_token="tg",
    )

    async def peers(*_a, **_k):
        return {"peers": [{"provider": "max", "external_id": "99"}]}

    with (
        patch.object(m, "list_identity_peers", side_effect=peers),
        patch.object(m, "channel_presence_active", new_callable=AsyncMock, return_value=True),
        patch.object(
            m, "get_active_chat_scoped", new_callable=AsyncMock, return_value="other-chat"
        ),
        patch.object(m, "send_max_message_markdown_from_model", new_callable=AsyncMock) as sm,
    ):
        await m.mirror_agent_text_to_secondaries(
            settings=settings,
            client=AsyncMock(),
            memory_url="http://m",
            canonical_user_id="u1",
            source_channel="telegram",
            memory_chat_id="chat-a",
            text="hi",
            telegram_bot=None,
        )
        sm.assert_not_called()
