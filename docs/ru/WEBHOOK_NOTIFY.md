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

## Запуск Balbes (чтобы работал `/api/webhooks/notify`)

1. **Переменные** в `.env.prod` (или `.env` для dev) — см. [`.env.example`](../../.env.example):
   - `WEBHOOK_NOTIFY_API_KEY` — длинная случайная строка (обязательно для включения endpoint).
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID` или `NOTIFY_TELEGRAM_CHAT_ID`.
   - `NOTIFY_DELIVERY_CHANNELS=telegram` (по умолчанию).

2. **Поднять web-backend** (слушает порт из `WEB_BACKEND_PORT`, в проде часто `18200`):
   - dev: [`scripts/start_dev.sh`](../../scripts/start_dev.sh) (или вручную из корня репозитория):
     ```bash
     cd services/web-backend
     PYTHONPATH="$(pwd)/../.." uvicorn main:app --host 127.0.0.1 --port "${WEB_BACKEND_PORT:-8200}"
     ```
   - prod: [`scripts/start_prod.sh`](../../scripts/start_prod.sh) или свой systemd — главное, чтобы **`PYTHONPATH` указывал на корень репозитория** (как в скриптах), иначе импорт `shared.*` может не сработать.

3. **Проверка локально**:
   ```bash
   curl -sS http://127.0.0.1:${WEB_BACKEND_PORT:-8200}/health
   curl -sS -X POST "http://127.0.0.1:${WEB_BACKEND_PORT:-8200}/api/webhooks/notify" \
     -H "Authorization: Bearer $WEBHOOK_NOTIFY_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"event_type":"info","service":"test","severity":"low","message":"ping","timestamp":"2026-04-15T12:00:00Z"}'
   ```

Дальше снаружи URL должен быть **HTTPS** (Telegram/мониторинг обычно требуют нормальный TLS на стороне VPS).

## Nginx (reverse proxy на VPS)

Проксируйте на **тот же порт**, на котором слушает uvicorn web-backend (`WEB_BACKEND_PORT`, например `18200`). Важно пробросить заголовки, чтобы rate limit видел реальный IP клиента (`X-Forwarded-For`).

Пример фрагмента `server { ... }`:

```nginx
# Подставьте свой домен и путь к сертификатам Let's Encrypt
server {
    listen 443 ssl http2;
    server_name balbes.example.com;

    ssl_certificate     /etc/letsencrypt/live/balbes.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/balbes.example.com/privkey.pem;

    # Алерты — небольшие JSON; защита от мусора
    client_max_body_size 256k;

    location /api/webhooks/notify {
        proxy_pass http://127.0.0.1:18200;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    # Остальной web-backend (дашборд API, /health, /docs)
    location / {
        proxy_pass http://127.0.0.1:18200;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Порт **`18200`** замените на значение `WEB_BACKEND_PORT` из вашего `.env.prod`. Отдельный `location` для `/api/webhooks/notify` необязателен, если достаточно одного `location /`.

## Настройка на российском сервере (источник алертов)

Идея: с RU-машины слать **HTTPS POST** на ваш VPS, тело JSON как в разделе выше. Ключ не кладите в репозиторий — только в переменные окружения или секрет-хранилище.

### Вариант A: `curl` из cron (простой healthcheck)

Файл `/usr/local/bin/balbes-notify-ping.sh` (права `chmod 750`, владелец root):

```bash
#!/bin/bash
set -euo pipefail
# shellcheck source=/dev/null
. /etc/balbes/notify.env   # WEBHOOK_NOTIFY_API_KEY=...
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
curl -fsS -X POST "https://balbes.example.com/api/webhooks/notify" \
  -H "Authorization: Bearer ${WEBHOOK_NOTIFY_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"event_type\":\"info\",\"service\":\"ru_ping\",\"severity\":\"low\",\"message\":\"RU ping OK\",\"timestamp\":\"${TS}\"}"
```

`/etc/balbes/notify.env`: одна строка `WEBHOOK_NOTIFY_API_KEY=...`, права `chmod 600`.

В crontab: `*/5 * * * * /usr/local/bin/balbes-notify-ping.sh >> /var/log/balbes-notify.log 2>&1`

### Вариант B: Prometheus Alertmanager

В `alertmanager.yml` для receiver типа webhook:

```yaml
receivers:
  - name: balbes-telegram
    webhook_configs:
      - url: 'https://balbes.example.com/api/webhooks/notify'
        http_config:
          bearer_token: 'ВАШ_ТОТ_ЖЕ_КЛЮЧ_ЧТО_В_WEBHOOK_NOTIFY_API_KEY'
        send_resolved: true
```

Тело у Alertmanager будет **другим** (формат алерта), а не `WebhookPayload` Balbes. Нужен либо **адаптер** на RU/VPS, либо отдельный endpoint под Alertmanager. Пока проще: **webhook → маленький скрипт** на RU, который из алерта собирает JSON в формате `event_type`, `service`, `severity`, `message`, `timestamp` и уже его шлёт на Balbes.

### Вариант C: отдельный скрипт на Python (RU)

Храните URL и ключ в `/etc/balbes/notify.env` (`chmod 600`), читайте из приложения и отправляйте `httpx`/`requests.post` на `https://balbes.example.com/api/webhooks/notify`.

### Firewall

- На **VPS Balbes**: разрешить входящий **443** от интернета; **не** открывать порт uvicorn наружу — только через nginx на localhost.
- На **RU-сервере** исходящий HTTPS к домену VPS должен быть разрешён (если есть egress-фильтрация — добавьте destination).

## Связанные документы

- ADR: [`docs/ru/ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md) (ADR-012).
- Переменные: [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md), шаблон [`.env.example`](../../.env.example).
- Деплой: [`docs/ru/DEPLOYMENT.md`](DEPLOYMENT.md).
