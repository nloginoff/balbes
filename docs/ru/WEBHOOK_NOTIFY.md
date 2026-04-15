# Входящие webhooks: мониторинг (`POST /webhook/notify`)

Все **входящие** webhooks (Telegram, MAX, мониторинг) обслуживает отдельный сервис **[`services/webhooks_gateway`](../../services/webhooks_gateway)** — **не** web-backend (дашборд).

Сервис слушает порт **`WEBHOOKS_GATEWAY_PORT`** (по умолчанию **8180** в dev, в prod задайте в `.env`, например **18180**).

## Endpoints

| Метод | Путь | Назначение |
|--------|------|------------|
| POST | `/webhook/notify` | Алерты мониторинга |
| POST | `/webhook/telegram` | Обновления Telegram Bot API при `TELEGRAM_BOT_MODE=webhook` |
| POST | `/webhook/max` | Входящие события MAX (подпись `X-Signature`, если задан `MAX_WEBHOOK_SECRET`) |
| GET | `/health` | Проверка живости |

Внешние системы (например мониторинг на RU-сервере) шлют **POST** с телом JSON:

- **Заголовок**: `Authorization: Bearer <WEBHOOK_NOTIFY_API_KEY>`
- **Поля**: `event_type`, `service`, `severity`, `message`, `timestamp`, опционально `details`

Если `WEBHOOK_NOTIFY_API_KEY` не задан, notify отвечает **503**.

## Доставка

Логика в [`shared/notify/delivery.py`](../../shared/notify/delivery.py): после валидации JSON сообщение уходит в каналы **`NOTIFY_DELIVERY_CHANNELS`** (`telegram`, `max`).

## Ограничения

- Лимит запросов: **`NOTIFY_RATE_LIMIT_PER_MINUTE`** на IP (с учётом `X-Forwarded-For` за reverse proxy).
- Длинные тексты для Telegram режутся по лимиту 4096 символов.

## Запуск

1. Переменные — [`.env.example`](../../.env.example): `WEBHOOK_NOTIFY_API_KEY`, `WEBHOOKS_GATEWAY_PORT`, `TELEGRAM_BOT_MODE` (`polling` \| `webhook`), при webhook — `TELEGRAM_WEBHOOK_SECRET`, `MAX_WEBHOOK_SECRET` для входящих MAX.
2. Поднять процесс: [`scripts/start_dev.sh`](../../scripts/start_dev.sh) / [`scripts/start_prod.sh`](../../scripts/start_prod.sh) запускают **webhooks_gateway**; для Telegram в режиме **webhook** процесс **`telegram_bot.py` (polling) не стартует**.

### Prod + systemd: `Connection refused` на порту webhooks

Если сервисы поднимаются через **systemd**, отдельного unit для gateway раньше не было в инструкции: **`balbes-webhooks-gateway`** нужно создать и включить (пример — [`DEPLOYMENT.md`](../../DEPLOYMENT.md), раздел systemd). Пока unit не установлен, [`scripts/start_prod.sh`](../../scripts/start_prod.sh) выведет предупреждение, а `curl` на `127.0.0.1:18180` даст **connection refused**. После установки unit: `sudo systemctl enable --now balbes-webhooks-gateway` и снова `curl …/health`.
3. Проверка:
   ```bash
   curl -sS "http://127.0.0.1:${WEBHOOKS_GATEWAY_PORT:-8180}/health"
   curl -sS -X POST "http://127.0.0.1:${WEBHOOKS_GATEWAY_PORT:-8180}/webhook/notify" \
     -H "Authorization: Bearer $WEBHOOK_NOTIFY_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"event_type":"info","service":"test","severity":"low","message":"ping","timestamp":"2026-04-15T12:00:00Z"}'
   ```

## Nginx

Проксируйте **на порт webhooks-gateway**, не на web-backend. Дашборд (если нужен) — отдельный `upstream` на `WEB_BACKEND_PORT`.

Пример (порты подставьте свои):

```nginx
upstream balbes_webhooks {
    server 127.0.0.1:18180;
}
upstream balbes_dashboard {
    server 127.0.0.1:18200;
}

server {
    listen 443 ssl http2;
    server_name balbes.example.com;
    client_max_body_size 256k;

    location /webhook/ {
        proxy_pass http://balbes_webhooks;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location / {
        proxy_pass http://balbes_dashboard;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Telegram `setWebhook`

После включения `TELEGRAM_BOT_MODE=webhook` зарегистрируйте URL у Telegram (подставьте токен и домен):

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://balbes.example.com/webhook/telegram&secret_token=<TELEGRAM_WEBHOOK_SECRET>
```

Значение `secret_token` должно совпадать с **`TELEGRAM_WEBHOOK_SECRET`** в `.env`.

## Настройка на российском сервере (источник алертов)

Идея: с RU-машины слать **HTTPS POST** на ваш VPS. Ключ не кладите в репозиторий.

### Cron + curl

Файл `/usr/local/bin/balbes-notify-ping.sh`:

```bash
#!/bin/bash
set -euo pipefail
# shellcheck source=/dev/null
. /etc/balbes/notify.env
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
curl -fsS -X POST "https://balbes.example.com/webhook/notify" \
  -H "Authorization: Bearer ${WEBHOOK_NOTIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"info\",\"service\":\"ru_ping\",\"severity\":\"low\",\"message\":\"RU ping OK\",\"timestamp\":\"${TS}\"}"
```

### Alertmanager

Формат тела Alertmanager **не** совпадает с `WebhookPayload` — нужен адаптер или скрипт, собирающий JSON под Balbes.

### Firewall

На VPS наружу только **443**; порты uvicorn — **localhost**.

## Связанные документы

- ADR: [`docs/ru/ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) (ADR-012).
- Переменные: [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md), [`.env.example`](../../.env.example).
