# Webhooks Gateway

FastAPI service that exposes HTTPS endpoints for channel integrations **without** running them inside the orchestrator process.

## Endpoints

| Path | Purpose |
|------|---------|
| `POST /webhook/telegram` | Telegram Bot API updates when `TELEGRAM_BOT_MODE=webhook` |
| `POST /webhook/max` | [MAX Messenger](https://dev.max.ru/docs-api) platform events (`message_created`, `message_callback`, …) |
| `POST /webhook/notify` | Internal monitoring / alert delivery |
| `GET /health` | Liveness |

Default dev port **8180** (prod often **18180**); see `WEBHOOKS_GATEWAY_PORT` in [`../../shared/config.py`](../../shared/config.py).

## MAX outbound formatting

LLM replies from the orchestrator are sent to MAX with **`format: markdown`** using [`shared/max_format_outbound.py`](../../shared/max_format_outbound.py) and [`send_max_message_markdown_from_model`](../../shared/max_api.py). Full documentation (Russian): [`../../docs/ru/MAX_WEBHOOK.md`](../../docs/ru/MAX_WEBHOOK.md).

Implementation entrypoint: [`routes/max.py`](routes/max.py) (`_max_run_orchestrator_and_reply`).

## Related docs

- Russian: [`../../docs/ru/MAX_WEBHOOK.md`](../../docs/ru/MAX_WEBHOOK.md), [`../../docs/ru/WEBHOOK_NOTIFY.md`](../../docs/ru/WEBHOOK_NOTIFY.md), [`../../docs/ru/CONFIGURATION.md`](../../docs/ru/CONFIGURATION.md)
