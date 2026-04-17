# MAX Messenger: токен, webhook и оркестратор

Сервис приёма событий — **[`services/webhooks_gateway`](../../services/webhooks_gateway)**. Путь **`POST /webhook/max`**.

Официальная документация платформы: [Подписка на обновления (POST /subscriptions)](https://dev.max.ru/docs-api/methods/POST/subscriptions), объект [Update](https://dev.max.ru/docs-api/objects/Update).

## Что должно быть запущено

1. **Оркестратор** — обрабатывает задачи (`POST /api/v1/tasks`).
2. **Webhooks gateway** — принимает HTTPS от MAX и в фоне дергает оркестратор.
3. В `.env` задан **`ORCHESTRATOR_URL`**, доступный **из процесса gateway** (часто `http://127.0.0.1:<ORCHESTRATOR_PORT>` на том же хосте).

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `MAX_BOT_TOKEN` | Токен бота (платформа: Чат-боты → Интеграция → Получить токен). Нужен для **исходящих** ответов в MAX (`POST .../messages`). В заголовок передаётся **как есть** (`Authorization: <token>`), без префикса `Bearer` — см. [документацию MAX](https://dev.max.ru/docs-api/methods/POST/messages). |
| `MAX_API_URL` | База API, обычно `https://platform-api.max.ru`. |
| `MAX_WEBHOOK_SECRET` | Секрет, который вы задаёте при **подписке** на webhook (поле `secret` в `POST /subscriptions`). Проверяется заголовок **`X-Max-Bot-Api-Secret`** (как в доке MAX). Дополнительно поддерживается устаревший вариант **`X-Signature`** (HMAC-SHA256 тела). |
| `ORCHESTRATOR_URL` | Базовый URL оркестратора для фонового `POST .../api/v1/tasks`. |
| `WEBHOOKS_GATEWAY_PORT` | Порт gateway (dev **8180**, prod часто **18180**). |
| `MAX_ALLOWED_USER_IDS` | Опционально: через запятую `user_id` MAX; пусто = все пользователи. |

Секрет в API MAX: **5–256 символов**, только `[a-zA-Z0-9_-]` (см. документацию).

## HTTPS и URL webhook

По требованиям MAX:

- URL **только `https://`**, порт **443** (в пути не указывают `:443`).
- Действующий TLS-сертификат от доверенного ЦС, **самоподписанные не подходят**.
- Endpoint должен отвечать **HTTP 200** в течение **30 секунд** (тяжёлая работа у нас в фоне — ответ 200 быстрый).

Итоговый URL для подписки:

```text
https://<ваш-домен>/webhook/max
```

Проксируйте **location** `/webhook/` на `webhooks_gateway`, не на web-backend. Пример nginx — см. [`WEBHOOK_NOTIFY.md`](WEBHOOK_NOTIFY.md) (блок про `location /webhook/`).

## Подписка на события (POST /subscriptions)

Получите **тот же токен**, что и для API бота (`MAX_BOT_TOKEN`), в заголовке `Authorization`.

Пример (подставьте домен и секрет; `secret` должен совпадать с **`MAX_WEBHOOK_SECRET`** в `.env`):

```bash
curl -X POST "https://platform-api.max.ru/subscriptions" \
  -H "Authorization: <MAX_BOT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/webhook/max",
    "update_types": ["message_created", "bot_started"],
    "secret": "your_secret_abc123"
  }'
```

Минимально для диалога с ботом обычно нужен **`message_created`**. После подписки long polling для этого бота отключается (см. доку MAX).

## Проверка без платформы

1. Локально поднять gateway и проверить health:
   ```bash
   curl -sS "http://127.0.0.1:${WEBHOOKS_GATEWAY_PORT:-8180}/health"
   ```
2. Для теста через **HTTPS с туннелем** (ngrok, cloudflared и т.д.) укажите выданный URL в `POST /subscriptions` как `https://....../webhook/max`.

## Поведение приложения

- Входящее **`message_created`** с текстом → пользователь **`max:<user_id>`** в оркестраторе → ответ в MAX через API.
- Если **`MAX_BOT_TOKEN`** не задан, webhook всё равно отвечает `{"ok": true}`, но ответ пользователю не отправится (см. логи gateway).

## См. также

- [`.env.example`](../../.env.example) — все переменные.
- [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md) — обзор конфигурации.
- Код: [`shared/max_inbound.py`](../../shared/max_inbound.py), [`routes/max.py`](../../services/webhooks_gateway/routes/max.py).
