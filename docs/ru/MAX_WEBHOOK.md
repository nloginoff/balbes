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
| `MEMORY_SERVICE_URL` / `MEMORY_SERVICE_PORT` | База Memory Service для slash-команд и кнопок (`/chats`, `/model`, …); в gateway используется `memory_service_url` из [`shared/config.py`](../../shared/config.py). |
| `WEBHOOKS_GATEWAY_PORT` | Порт gateway (dev **8180**, prod часто **18180**). |
| `MAX_ALLOWED_USER_IDS` | Whitelist: через запятую числовые `user_id` MAX; **пусто = любой пользователь**. Для закрытого бота задайте список (как `TELEGRAM_ALLOWED_USERS`). |

### Нет ответа бота в MAX

1. **В логах gateway** (`logs/prod/webhooks-gateway.log` или stdout uvicorn) должны появляться строки вроде `MAX webhook: schedule LLM` после `POST /webhook/max`. Если есть только `GET /health` — **события MAX не доходят** до этого хоста: проверьте подписку `POST /subscriptions`, URL `https://…/webhook/max`, прокси/nginx и TLS.
2. **`MAX_WEBHOOK_SECRET`** задан, а в подписке другой секрет → ответ **403**, MAX не доставит обработку.
3. **`MAX_ALLOWED_USER_IDS`** — ваш `user_id` должен быть в списке (или список пустой).
4. Исходящее **`POST /messages`**: идентификатор чата не должен обрабатываться через «truthiness» (`0` — валидное значение в некоторых сценариях); см. исправление в [`shared/max_api.py`](../../shared/max_api.py). В реальных webhook для диалога у `recipient` бывают и `chat_id`, и `user_id`; последний часто указывает на **бота**, а ответ нужно слать пользователю — разбор в [`shared/max_webhook.py`](../../shared/max_webhook.py) `extract_max_reply_targets` (при отсутствии `chat_id` берётся `sender.user_id` человека). Для `message_callback` добавлен запасной target по `callback.user.user_id`.

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
    "update_types": ["message_created", "bot_started", "message_callback"],
    "secret": "your_secret_abc123"
  }'
```

Для диалога с ботом нужны **`message_created`** (текст) и **`message_callback`** (нажатия на inline-кнопки вроде «Чаты», «Модель»). **`bot_started`** — по желанию. После подписки long polling для этого бота отключается (см. доку MAX).

Если подписка была создана **до** появления кнопок, выполните **`scripts/max_subscriptions.py apply --delete-first`** с актуальными `update_types` (по умолчанию в скрипте уже есть `message_callback`).

### Список, удаление, смена секрета

Официальные методы:

- **[GET /subscriptions](https://dev.max.ru/docs-api/methods/GET/subscriptions)** — список активных подписок;
- **[DELETE /subscriptions](https://dev.max.ru/docs-api/methods/DELETE/subscriptions)** — отписка по параметру `url` (тот же HTTPS URL webhook).

При **смене секрета** в `.env` (`MAX_WEBHOOK_SECRET`) платформа не «обновляет» секрет автоматически: надёжный порядок — **удалить** подписку по старому URL (`DELETE ?url=...`), затем снова **`POST /subscriptions`** с новым `secret` (или использовать скрипт ниже с `--delete-first`).

В репозитории есть скрипт **[`scripts/max_subscriptions.py`](../../scripts/max_subscriptions.py)** (только стандартная библиотека Python):

```bash
cd /path/to/balbes   # или dev
# Список подписок (нужны MAX_BOT_TOKEN и MAX_API_URL в .env.prod)
ENV=prod python scripts/max_subscriptions.py list

# Явный путь к env
python scripts/max_subscriptions.py list --env-file /path/to/.env.prod

# Удалить подписку (перед сменой URL/секрета)
python scripts/max_subscriptions.py delete --url "https://your-domain.com/webhook/max"

# Создать подписку и проверить, что URL появился в GET /subscriptions
python scripts/max_subscriptions.py apply \
  --url "https://your-domain.com/webhook/max" \
  --secret-from-env \
  --delete-first
```

Флаг **`--delete-first`** сначала вызывает `DELETE` для того же `url`, затем `POST` и **проверку** через `GET` (если вашего URL нет в списке — скрипт завершится с кодом ошибки).

## Проверка без платформы

1. Локально поднять gateway и проверить health:
   ```bash
   curl -sS "http://127.0.0.1:${WEBHOOKS_GATEWAY_PORT:-8180}/health"
   ```
2. Для теста через **HTTPS с туннелем** (ngrok, cloudflared и т.д.) укажите выданный URL в `POST /subscriptions` как `https://....../webhook/max`.

## Поведение приложения

- Пользователь в оркестраторе: **`max:<user_id>`** (как в Telegram, но с префиксом канала).
- **Slash-команды** (`/start`, `/help`, `/chats`, `/model`, `/agents`, `/newchat`, `/rename`, `/clear`, `/status`) обрабатываются так же, как в Telegram: запрос **не** уходит в LLM, а дергается Memory Service (список чатов, модель, агент и т.д.).
- **Меню-кнопки** под сообщением (inline keyboard) — callback `message_callback`; при нажатии отправляется ответ на callback ([`POST /answers`](https://dev.max.ru/docs-api/methods/POST/answers)) и новое сообщение с результатом. Реализация: [`routes/max_chat.py`](../../services/webhooks_gateway/routes/max_chat.py), разметка в [`shared/max_bot_ui.py`](../../shared/max_bot_ui.py).
- **«Печатает»**: перед долгим ответом вызывается [`POST /chats/{chatId}/actions`](https://dev.max.ru/docs-api/methods/POST/chats/-chatId-/actions) с `typing_on` (если известен `chat_id`).
- Обычный текст (не команда) → фоновый **`POST /api/v1/tasks`** → ответ в MAX (`POST /messages`).
- Если **`MAX_BOT_TOKEN`** не задан, webhook всё равно отвечает `{"ok": true}`, но ответ пользователю не отправится (см. логи gateway).

## Исходящие сообщения MAX: разметка и доставка

Платформа MAX в теле [`NewMessageBody`](https://dev.max.ru/docs-api/objects/NewMessageBody) принимает поле **`format`**: **`markdown`** или **`html`**. Без него текст отображается как обычный. Лимит поля **`text`**: до **4000 символов** (в коде — `len()` строки Python; тип «кодовых единиц» в официальной доке для MAX не уточнён, при расхождениях с API смотрите логи ответа).

Ниже описан путь **ответов от LLM** (оркестратор) и **зеркалирования** в MAX. Он **отличается** от пути slash-команд и inline-меню (см. подраздел **UI-ответы и ответ LLM** ниже).

### Краткая схема потока

1. Пользователь пишет в MAX → [`POST /webhook/max`](../../services/webhooks_gateway/routes/max.py) → `POST /api/v1/tasks` оркестратору.
2. Текст ответа (`result.output`) — «как от модели» (markdown-подобный plain, блоки кода, списки).
3. [`model_text_to_max_markdown`](../../shared/max_format_outbound.py) внутренне использует тот же этап «нормализации», что и Telegram ([`model_text_to_telegram_html`](../../shared/telegram_app/format_outbound.py)), затем переводит подмножество HTML в **синтаксис MAX Markdown** (`++` подчёркивание, `~~` зачёркивание, `[текст](url)` и т.д.).
4. [`raw_chunks_for_max_markdown`](../../shared/max_format_outbound.py) режет **исходный** текст на части так, чтобы после шага 3 длина каждой части не превышала 4000; при необходимости ищется разрез в окне середины сегмента, с учётом границ fenced-блоков ``` (вспомогательные функции из того же конвейера, что и для Telegram).
5. [`send_max_message_markdown_from_model`](../../shared/max_api.py) для каждой части вызывает [`send_max_message`](../../shared/max_api.py) с **`text_format="markdown"`** (в JSON уходит **`format": "markdown"`**).
6. Если отправка с разметкой **падает с исключением** (в т.ч. HTTP ≥ 400 от платформы), для **той же** части текста выполняется повтор **без** `format`, с текстом из [`max_markdown_to_plain`](../../shared/max_format_outbound.py).

### Справочник по файлам

| Файл | Роль |
|------|------|
| [`shared/max_format_outbound.py`](../../shared/max_format_outbound.py) | `model_text_to_max_markdown`, `telegram_html_to_max_markdown`, `raw_chunks_for_max_markdown`, `max_markdown_to_plain` |
| [`shared/max_api.py`](../../shared/max_api.py) | `send_max_message`, `send_max_message_markdown_from_model`, `send_max_message_text`, `split_max_text`, нормализация токена и query-параметров |
| [`services/webhooks_gateway/routes/max.py`](../../services/webhooks_gateway/routes/max.py) | Webhook `POST /webhook/max`, вызов оркестратора, первичная доставка ответа |
| [`shared/outbound/mirror.py`](../../shared/outbound/mirror.py) | Зеркалирование ответа агента во второй канал (в т.ч. MAX) |
| [`shared/max_bot_ui.py`](../../shared/max_bot_ui.py) | Ответы UI без `max_format_outbound` (см. таблицу ниже) |
| [`shared/notify/delivery.py`](../../shared/notify/delivery.py) | Notify в MAX без форматированного конвейера |

### Таблица: Telegram vs MAX (исходящие от агента)

| Возможность | Telegram (исходящие) | MAX (исходящие LLM / зеркало) |
|-------------|----------------------|-------------------------------|
| Жирный / курсив / зачёркнутое | HTML `<b>`, `<i>`, `<s>` | `**`, `*`, `~~` ([дока MAX](https://dev.max.ru/docs-api)) |
| Подчёркивание | HTML `<u>` | `++текст++` |
| Inline-код, блок кода | `` `<code>` ``, `<pre>` `` | `` ` `` и fenced ``` (через HTML-пайплайн → MAX) |
| Ссылки | `<a href>` | `[текст](url)` |
| Спойлер `||…||` | `<tg-spoiler>` | содержимое без спойлер-тега (аналога в доке MAX нет) |
| Цитата `> …` | `<blockquote>` | строки с префиксом `> `; сложные вложенные цитаты могут отображаться грубо |

### UI-ответы и ответ LLM

| Путь | Код | Разметка |
|------|-----|----------|
| Slash-команды, нажатия кнопок меню | [`_max_send_ui_reply`](../../services/webhooks_gateway/routes/max.py) + [`MaxUiReply`](../../shared/max_bot_ui.py) | Уже задаётся **`text_format`** (часто `markdown`) и при необходимости **attachments** (inline keyboard); **не** через `max_format_outbound`. |
| Долгий ответ оркестратора после сообщения пользователя | [`_max_run_orchestrator_and_reply`](../../services/webhooks_gateway/routes/max.py) | **Только** [`send_max_message_markdown_from_model`](../../shared/max_api.py). |
| Зеркало в MAX при активном диалоге в другом канале | [`mirror_agent_text_to_secondaries`](../../shared/outbound/mirror.py) | Тот же [`send_max_message_markdown_from_model`](../../shared/max_api.py). |
| Алерты мониторинга / notify | [`shared/notify/delivery.py`](../../shared/notify/delivery.py) | **Plain**, [`send_max_message_text`](../../shared/max_api.py) — без конвейера markdown. |

Стиль экранирования в UI и в LLM-конвейере стараются **не конфликтовать**: оба используют в итоге официальный markdown MAX для исходящих с форматированием.

### Многочастные сообщения (`split_max_text`)

Если один фрагмент после конвертации всё ещё длиннее 4000 символов, [`send_max_message`](../../shared/max_api.py) разбивает его на несколько `POST /messages`. Для **всех** таких частей с текстом сохраняется **`format: markdown`**; **`attachments`** при необходимости передаются **только в первом** запросе (как и раньше). Раньше при `i > 0` поле `format` ошибочно сбрасывалось — это исправлено.

### Зеркалирование (`AGENT_REPLY_MIRROR_*`)

При включённом зеркале и совпадении активного Memory-чата тексты от агента дублируются во второй мессенджер. Ветка MAX больше **не** обрезает разметку в plain: используется тот же pipeline, что и для основного ответа в MAX. Подробнее — [`IDENTITY_AND_OPENROUTER_USER.md`](IDENTITY_AND_OPENROUTER_USER.md), [`CONFIGURATION.md`](CONFIGURATION.md) (переменные `AGENT_REPLY_MIRROR_*`).

### Ограничения и диагностика

- **Поддержка конструкций в клиенте MAX** (блочный markdown, вложенные списки, все нюансы fenced) без теста на реальном приложении не гарантируется — при странном отображении смотрите ответ API и при необходимости fallback на plain в логах (`MAX markdown send failed, trying plain: …`).
- **Спойлеры Telegram** в MAX не имеют документированного эквивалента — текст выводится читаемо, но без скрытия.
- Если «пропала разметка» только **со второго куска** длинного сообщения — проверьте версию кода: в актуальной ветке `format` на продолжениях не удаляется.

## См. также

- [`.env.example`](../../.env.example) — все переменные.
- [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md) — обзор конфигурации.
- Код: [`shared/max_inbound.py`](../../shared/max_inbound.py), [`routes/max.py`](../../services/webhooks_gateway/routes/max.py).
