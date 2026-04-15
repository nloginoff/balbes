# Входящий webhook мониторинга (`/api/webhooks/notify`)

Внешние системы (например мониторинг на RU-сервере) отправляют **POST** на **web-backend**:

- **URL**: `https://<host>/api/webhooks/notify`
- **Заголовок**: `Authorization: Bearer <WEBHOOK_NOTIFY_API_KEY>`
- **Тело**: JSON с полями `event_type`, `service`, `severity`, `message`, `timestamp`, опционально `details`

Если `WEBHOOK_NOTIFY_API_KEY` не задан, endpoint отвечает **503** (функция отключена).

## Доставка

Логика в [`shared/notify/delivery.py`](../../shared/notify/delivery.py): после валидации JSON сообщение форматируется и отправляется в каналы из **`NOTIFY_DELIVERY_CHANNELS`**:

- `telegram` — нужны `TELEGRAM_BOT_TOKEN` и целевой чат (`NOTIFY_TELEGRAM_CHAT_ID` или личный `TELEGRAM_USER_ID`);
- `max` — нужны `MAX_BOT_TOKEN` и `NOTIFY_MAX_CHAT_ID` (формат API MAX см. официальную документацию).

Ответ **200** содержит `delivery` с идентификаторами сообщений и списком `skipped_channels` / `errors` при частичных сбоях.

## Ограничения

- Лимит запросов: **`NOTIFY_RATE_LIMIT_PER_MINUTE`** на IP (с учётом `X-Forwarded-For` за reverse proxy).
- Длинные тексты для Telegram режутся по лимиту 4096 символов.

## Связанные документы

- ADR: [`docs/ru/ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) (ADR-012).
- Переменные: [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md), шаблон [`.env.example`](../../.env.example).
