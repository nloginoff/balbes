"""
MAX messenger: slash commands and callback buttons (parity with Telegram).

Uses Memory Service HTTP API and providers.yaml (same as Telegram bot).
"""

from __future__ import annotations

import logging

import httpx

from shared.max_bot_ui import (
    CB_AGENT,
    CB_CHAT,
    CB_MENU,
    CB_MODEL,
    MAX_HELP_TEXT,
    SEP,
    MaxUiReply,
    build_agent_switch_keyboard,
    build_chat_switch_keyboard,
    build_main_menu_keyboard,
    build_model_switch_keyboard,
    inline_keyboard_attachment,
    load_active_models,
    load_agents_list,
    model_display_name,
)

logger = logging.getLogger(__name__)

# Commands we handle locally (do not send to LLM). Unknown /foo → LLM.
_SLASH_HANDLED = frozenset(
    {
        "start",
        "help",
        "chats",
        "model",
        "agents",
        "newchat",
        "rename",
        "clear",
        "status",
    }
)


def should_handle_slash_command(cmd: str) -> bool:
    return cmd.lower() in _SLASH_HANDLED


async def _get_active_chat(client: httpx.AsyncClient, memory_url: str, user_key: str) -> str | None:
    try:
        r = await client.get(f"{memory_url}/api/v1/chats/{user_key}/active")
        if r.status_code == 200:
            return r.json().get("chat_id")
    except Exception as e:
        logger.debug("max active chat: %s", e)
    return None


async def _set_active_chat(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str
) -> bool:
    try:
        r = await client.put(
            f"{memory_url}/api/v1/chats/{user_key}/active",
            params={"chat_id": chat_id},
        )
        return r.status_code == 200
    except Exception as e:
        logger.debug("max set active chat: %s", e)
    return False


async def _get_chats(client: httpx.AsyncClient, memory_url: str, user_key: str) -> list[dict]:
    try:
        r = await client.get(f"{memory_url}/api/v1/chats/{user_key}")
        if r.status_code == 200:
            return r.json().get("chats", [])
    except Exception as e:
        logger.debug("max list chats: %s", e)
    return []


async def _create_chat(
    client: httpx.AsyncClient, memory_url: str, user_key: str, name: str
) -> str | None:
    try:
        r = await client.post(
            f"{memory_url}/api/v1/chats/{user_key}",
            json={"name": name},
        )
        if r.status_code == 200:
            return r.json().get("chat_id")
    except Exception as e:
        logger.debug("max create chat: %s", e)
    return None


async def _rename_chat(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str, name: str
) -> bool:
    try:
        r = await client.put(
            f"{memory_url}/api/v1/chats/{user_key}/{chat_id}/name",
            json={"name": name},
        )
        return r.status_code == 200
    except Exception as e:
        logger.debug("max rename chat: %s", e)
    return False


async def _get_chat_model(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str
) -> str | None:
    try:
        r = await client.get(f"{memory_url}/api/v1/chats/{user_key}/{chat_id}/model")
        if r.status_code == 200:
            return r.json().get("model_id")
    except Exception as e:
        logger.debug("max get model: %s", e)
    return None


async def _set_chat_model(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str, model_id: str
) -> bool:
    try:
        r = await client.put(
            f"{memory_url}/api/v1/chats/{user_key}/{chat_id}/model",
            json={"model_id": model_id},
        )
        return r.status_code == 200
    except Exception as e:
        logger.debug("max set model: %s", e)
    return False


async def _get_chat_agent(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str
) -> str:
    try:
        r = await client.get(f"{memory_url}/api/v1/chats/{user_key}/{chat_id}/agent")
        if r.status_code == 200:
            return str(r.json().get("agent_id") or "balbes")
    except Exception as e:
        logger.debug("max get agent: %s", e)
    return "balbes"


async def _set_chat_agent(
    client: httpx.AsyncClient, memory_url: str, user_key: str, chat_id: str, agent_id: str
) -> bool:
    try:
        r = await client.put(
            f"{memory_url}/api/v1/chats/{user_key}/{chat_id}/agent",
            json={"agent_id": agent_id},
        )
        return r.status_code == 200
    except Exception as e:
        logger.debug("max set agent: %s", e)
    return False


async def run_max_slash_command(
    *,
    command: str,
    rest: str,
    user_key: str,
    memory_url: str,
    orchestrator_url: str,
    client: httpx.AsyncClient,
) -> MaxUiReply:
    cmd = command.lower().strip()

    if cmd == "start":
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            new_id = await _create_chat(client, memory_url, user_key, "Основной чат")
            if new_id:
                await _set_active_chat(client, memory_url, user_key, new_id)
        text = (
            "👋 Привет! Я **Balbes** — интеллектуальный ассистент.\n\n"
            "Пиши задачи и вопросы в чат. Ниже — **меню** (чаты, модель, агенты, статус).\n"
            "Список команд: /help"
        )
        return MaxUiReply(
            text=text,
            attachments=[inline_keyboard_attachment(build_main_menu_keyboard())],
        )

    if cmd == "help":
        return MaxUiReply(
            text=MAX_HELP_TEXT,
            attachments=[inline_keyboard_attachment(build_main_menu_keyboard())],
        )

    if cmd == "status":
        try:
            r = await client.get(f"{orchestrator_url.rstrip('/')}/api/v1/status")
            if r.status_code == 200:
                data = r.json()
                ws = ", ".join(data.get("workspace_files", [])) or "—"
                text = (
                    f"✅ **Статус:** {str(data.get('status', '?')).upper()}\n\n"
                    f"**Сервисы:** Memory `{data.get('services', {}).get('memory_service', '?')}`, "
                    f"Skills `{data.get('services', {}).get('skills_registry', '?')}`\n\n"
                    f"**Workspace:** {ws}\n`{data.get('timestamp', '')}`"
                )
            else:
                text = f"⚠️ HTTP {r.status_code}"
        except Exception as e:
            text = f"❌ Ошибка: `{type(e).__name__}: {e}`"
        return MaxUiReply(text=text)

    if cmd == "chats":
        chats = await _get_chats(client, memory_url, user_key)
        active = await _get_active_chat(client, memory_url, user_key)
        if not chats:
            return MaxUiReply(
                text="У тебя пока нет чатов. Нажми **Новый чат** или отправь /newchat",
                attachments=[inline_keyboard_attachment(build_main_menu_keyboard())],
            )
        lines = ["**Твои чаты:**\n"]
        for i, c in enumerate(chats, 1):
            cid = c.get("chat_id", "")
            name = c.get("name") or "Без названия"
            mid = model_display_name(c.get("model_id"))
            mark = "✅ " if cid == active else f"{i}. "
            lines.append(f"{mark}**{name}** — `{str(cid)[:8]}…` — {mid}")
        body = "\n".join(lines) + "\n\nНажми кнопку, чтобы переключить чат:"
        return MaxUiReply(
            text=body,
            attachments=[inline_keyboard_attachment(build_chat_switch_keyboard(chats, active))],
        )

    if cmd == "newchat":
        name = rest.strip() or "Новый чат"
        new_id = await _create_chat(client, memory_url, user_key, name)
        if new_id:
            await _set_active_chat(client, memory_url, user_key, new_id)
            return MaxUiReply(text=f"✅ Создан и активирован чат **{name}**")
        return MaxUiReply(text="❌ Не удалось создать чат")

    if cmd == "rename":
        if not rest.strip():
            return MaxUiReply(text="Использование: /rename Новое название")
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            return MaxUiReply(text="❌ Нет активного чата")
        if await _rename_chat(client, memory_url, user_key, chat_id, rest.strip()):
            return MaxUiReply(text=f"✅ Чат переименован: **{rest.strip()}**")
        return MaxUiReply(text="❌ Не удалось переименовать")

    if cmd == "clear":
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            return MaxUiReply(text="❌ Нет активного чата")
        try:
            r = await client.delete(f"{memory_url}/api/v1/history/{user_key}/{chat_id}")
            if r.status_code in (200, 204):
                return MaxUiReply(text="✅ История чата очищена")
            return MaxUiReply(text=f"⚠️ Ошибка: HTTP {r.status_code}")
        except Exception as e:
            return MaxUiReply(text=f"❌ `{type(e).__name__}: {e}`")

    if cmd == "model":
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            return MaxUiReply(text="❌ Нет активного чата. Создай: /newchat")
        models = load_active_models()
        if not models:
            return MaxUiReply(text="❌ Список моделей пуст (config/providers.yaml)")
        if rest.strip():
            ok = await _set_chat_model(client, memory_url, user_key, chat_id, rest.strip())
            if ok:
                return MaxUiReply(text=f"✅ Модель чата: **{model_display_name(rest.strip())}**")
            return MaxUiReply(text="❌ Не удалось установить модель")
        current = await _get_chat_model(client, memory_url, user_key, chat_id)
        cur_name = model_display_name(current)
        return MaxUiReply(
            text=f"🤖 **Выбери модель** для текущего чата.\nСейчас: _{cur_name}_",
            attachments=[inline_keyboard_attachment(build_model_switch_keyboard(models))],
        )

    if cmd == "agents":
        chat_id = await _get_active_chat(client, memory_url, user_key)
        agents = load_agents_list()
        cur = "balbes"
        if chat_id:
            cur = await _get_chat_agent(client, memory_url, user_key, chat_id)
        lines = ["**Агенты:**\n"]
        for a in agents:
            mark = "✅ " if a.get("id") == cur else "   "
            emoji = a.get("emoji") or "🤖"
            lines.append(
                f"{mark}{emoji} **{a.get('display_name', a.get('id'))}** — {a.get('description', '')}"
            )
        body = "\n".join(lines) + "\n\nВыбери агента для текущего чата:"
        return MaxUiReply(
            text=body,
            attachments=[inline_keyboard_attachment(build_agent_switch_keyboard(agents, cur))],
        )

    return MaxUiReply(text=f"Неизвестная команда: /{cmd}")


async def run_max_callback(
    *,
    payload: str,
    user_key: str,
    memory_url: str,
    orchestrator_url: str,
    client: httpx.AsyncClient,
) -> MaxUiReply:
    """Handle inline button payload (callback)."""
    p = (payload or "").strip()
    if not p:
        return MaxUiReply(text="Пустой callback")

    if p.startswith(CB_MENU + SEP):
        sub = p.split(SEP, 1)[1].lower()
        if sub == "chats":
            return await run_max_slash_command(
                command="chats",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )
        if sub == "model":
            return await run_max_slash_command(
                command="model",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )
        if sub == "agents":
            return await run_max_slash_command(
                command="agents",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )
        if sub == "status":
            return await run_max_slash_command(
                command="status",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )
        if sub == "help":
            return await run_max_slash_command(
                command="help",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )
        if sub == "newchat":
            return await run_max_slash_command(
                command="newchat",
                rest="",
                user_key=user_key,
                memory_url=memory_url,
                orchestrator_url=orchestrator_url,
                client=client,
            )

    if p.startswith(CB_CHAT + SEP):
        chat_id = p.split(SEP, 1)[1].strip()
        if chat_id and await _set_active_chat(client, memory_url, user_key, chat_id):
            return MaxUiReply(text=f"✅ Активный чат переключён на `{chat_id[:8]}…`")
        return MaxUiReply(text="❌ Не удалось переключить чат")

    if p.startswith(CB_MODEL + SEP):
        idx_raw = p.split(SEP, 1)[1].strip()
        try:
            idx = int(idx_raw)
        except ValueError:
            return MaxUiReply(text="❌ Некорректный выбор модели")
        models = load_active_models()
        if idx < 0 or idx >= len(models):
            return MaxUiReply(text="❌ Индекс модели вне списка")
        mid = str(models[idx].get("id") or "")
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            return MaxUiReply(text="❌ Нет активного чата")
        if await _set_chat_model(client, memory_url, user_key, chat_id, mid):
            return MaxUiReply(text=f"✅ Модель: **{model_display_name(mid)}**")
        return MaxUiReply(text="❌ Не удалось установить модель")

    if p.startswith(CB_AGENT + SEP):
        idx_raw = p.split(SEP, 1)[1].strip()
        try:
            idx = int(idx_raw)
        except ValueError:
            return MaxUiReply(text="❌ Некорректный выбор агента")
        agents = load_agents_list()
        if idx < 0 or idx >= len(agents):
            return MaxUiReply(text="❌ Индекс агента вне списка")
        aid = str(agents[idx].get("id") or "")
        chat_id = await _get_active_chat(client, memory_url, user_key)
        if not chat_id:
            return MaxUiReply(text="❌ Нет активного чата")
        if await _set_chat_agent(client, memory_url, user_key, chat_id, aid):
            return MaxUiReply(text=f"✅ Агент чата: **{aid}**")
        return MaxUiReply(text="❌ Не удалось установить агента")

    return MaxUiReply(text=f"Неизвестный callback: `{p[:80]}`")
