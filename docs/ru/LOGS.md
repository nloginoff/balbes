# Логи и диагностика: куда смотреть

Цель — не копировать десятки строк в чат с ассистентом: укажи **путь**, **сервис** и **время**; при необходимости приложи **файл** или хвост.

## Логи приложений (prod на этом сервере)

Каталог (после старта через `scripts/start_prod.sh` / `restart_prod.sh`):

| Что | Путь |
|-----|------|
| Все prod-логи (ротация в скриптах) | `logs/prod/*.log` в корне репозитория деплоя (`balbes/` на сервере) |
| Оркестратор | `logs/prod/orchestrator.log` |
| Telegram-бот | `logs/prod/telegram_bot.log` |
| Memory | `logs/prod/memory_service.log` |
| Webhooks gateway | `logs/prod/webhooks_gateway.log` |

Просмотр: `tail -n 200 logs/prod/orchestrator.log` из каталога `balbes/`.

## Логи вызовов инструментов агента (JSONL, не чат)

Оркестратор пишет **вызовы tools** (имя, краткие input/result, длительность), не полный текст LLM-диалога.

| Что | Путь |
|-----|------|
| По агенту и дате | `data/logs/agents/<agent_id>/YYYY-MM-DD.jsonl` |
| Обычно основной бот | `agent_id` в имени папки часто `orchestrator` (каталог workspace) или `balbes` — смотри фактические подкаталоги `data/logs/agents/` |

Поля: `ts`, `tool`, `input`, `result`, `duration_ms`, `ok`, `user`, `chat`. Удобно для вопроса «какой tool дернулся».

## История **переписки** (Redis / Memory)

Сообщения чатов — в **Memory Service (Redis)**, не в `logs/prod/`. API: `GET /api/v1/history/{user_id}/{chat_id}` (см. [CONFIGURATION.md](CONFIGURATION.md) — порты Memory: prod обычно `18100`).

### Экспорт всех чатов в файлы (дамп на диск)

Скрипт: [`scripts/export_memory_chats_to_data_for_agent.py`](../../scripts/export_memory_chats_to_data_for_agent.py). Нужен **Python с зависимостью `redis` из venv репозитория**.

```bash
cd ~/projects/balbes    # или dev
./scripts/export_chats_for_agent.sh
# эквивалентно: .venv/bin/python scripts/export_memory_chats_to_data_for_agent.py
```

Без venv: `ModuleNotFoundError: redis` — создать venv: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'` в корне репо.

По умолчанию пишет в `data_for_agent/<namespace>__<agent>__<chat_id>/{meta.json,history.json}`. Переменные и Redis: `--env-file`, `--redis-url`, см. docstring в скрипте.

## История чата (быстро без дампа)

```bash
# список чатов
curl -sS "http://127.0.0.1:18100/api/v1/chats/$USER_UUID" | jq .

# последние сообщения
curl -sS "http://127.0.0.1:18100/api/v1/history/$USER_UUID/$CHAT_ID?limit=200" | jq .
```

(Порт смени для dev/другой инсталляции.)

## Redis (ключи)

История: sorted set `history:{user_id}:{chat_id}`. Список чатов: hash `chats:{user_id}`. См. `services/memory-service/clients/redis_client.py`.

## Приватный memory-репо (git, не «логи»)

`data/agents/` — отдельный git; снимки: `scripts/backup_memory.sh`. См. [AGENTS_GUIDE.md](AGENTS_GUIDE.md) (версионирование workspace).
