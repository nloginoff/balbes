# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Оркестратор и зряшнее делегирование в coder** — в [`config/agents/balbes.yaml`](config/agents/balbes.yaml) у `balbes` отключены инструменты `delegate_to_agent`, `get_agent_result`, `cancel_agent_task` (модель гнала сценарии/вложения в coder). В [`shared/agent_tools/registry.py`](shared/agent_tools/registry.py) у `delegate_to_agent` по умолчанию `mode=ask` и уточнено описание; [`data/agents/orchestrator/AGENTS.md`](data/agents/orchestrator/AGENTS.md), [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md).
- **Старый Word .doc (не .docx)** — бинарный формат: извлечение текста через **antiword** / **catdoc** в [`shared/document_extract.py`](shared/document_extract.py); в [`docs/ru/ATTACHMENTS.md`](docs/ru/ATTACHMENTS.md) — установка `antiword` на сервере. MIME `application/msword` → маршрут и синтетическое имя в [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py). `.doc` учтён в «структурированных» суффиксах, чтобы не пытаться читать как сырой UTF-8.
- **Telegram: вложения-документы (ложные отказы по «типу файла»)** — в [`shared/document_extract.py`](shared/document_extract.py): для файлов **без расширения** в имени после неудачного sniff добавлено запасное чтение UTF-8 с проверкой печатных символов; опциональный аргумент **`mime_type`** для подсказок при пустом суффиксе; отдельные сообщения для **пустого текста** и для **бинарного/не текста** (без формулировки «неподдерживаемый тип»); в sniff отказ по **доле** нулевых байт в сэмпле, а не по одному NUL. В [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py): при отсутствии расширения у `document.file_name` синтетическое имя по MIME (`upload.py`, `upload.pl`, `upload.txt`, …) и передача `mime_type` в извлечение текста. [`docs/ru/ATTACHMENTS.md`](docs/ru/ATTACHMENTS.md).
- **Telegram: вложения-документы** — извлечение текста в [`shared/document_extract.py`](shared/document_extract.py): для типов кроме PDF/DOCX/XLSX/XLS используется **определение текста по содержимому** (UTF-8/UTF-16, кириллица, эвристика печатных символов), чтобы не отклонять `.py`, `.pl`, файлы без расширения и прочие текстовые форматы без расширения белого списка. PDF/DOCX/XLS с битым содержимым при возможности откатываются к sniff-тексту.
- **Голос (Whisper): `FileNotFoundError`** — в [`services/orchestrator/skills/whisper_transcribe.py`](services/orchestrator/skills/whisper_transcribe.py) сообщение «установите ffmpeg» показывается только если отсутствует бинарник `ffmpeg`; иные `FileNotFoundError` (кэш модели и т.д.) пробрасываются как есть. [`docs/ru/ATTACHMENTS.md`](docs/ru/ATTACHMENTS.md): пояснение.

### Added
- **Документация `manage_schedule`** — подраздел в [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md) (пути, `agent_id`, уникальность `job_id`, YAML, hot-reload). Расширены **`TOOLS.md`** в workspace оркестратора и coder (в `data/agents/`, коммит через memory-репо): списки файлов с `schedules.yaml` и инструкции по расписаниям.
- **Инструмент `render_solution`** — рендер цельного текстового решения с формулами в одну или несколько PNG **фиксированного размера** (900×1200 px при DPI 120); вложения уходят в поле `outbound_attachments` ответа `POST /api/v1/tasks` и отправляются в Telegram отдельными фото; при делегировании в coder вложения сливаются в ответ оркестратора. Реализация: [`shared/solution_render.py`](shared/solution_render.py), [`shared/agent_tools/registry.py`](shared/agent_tools/registry.py), [`services/orchestrator/agent.py`](services/orchestrator/agent.py), [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py), [`services/coder/api/execute.py`](services/coder/api/execute.py); зависимость **matplotlib**; allowlist **coder** в [`config/providers.yaml`](config/providers.yaml).

### Changed
- **Расписания cron** — вместо одного `config/schedules.yaml` задачи хранятся **по агентам** в `data/agents/<agent_dir>/schedules.yaml` (рядом с MD workspace; для API-агента `balbes` каталог — `orchestrator/`, если нет `balbes/`). Пример и миграция с прежнего одного файла: скопировать из [`config/schedules.example.yaml`](config/schedules.example.yaml) в нужный каталог агента (как и прочие файлы workspace, обычно в memory-репо под `data/agents/`). Telegram-планировщик агрегирует все найденные `schedules.yaml`; в APScheduler id задач — `agent_id:job_id`. `manage_schedule` пишет в файл целевого агента; **`schedules.yaml`** разрешён в `workspace_read` / `workspace_write`. Файлы: [`shared/agent_schedules.py`](shared/agent_schedules.py), [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py), [`shared/agent_tools/registry.py`](shared/agent_tools/registry.py), [`services/orchestrator/workspace.py`](services/orchestrator/workspace.py).

### Fixed
- **Вложения: старый Excel `.xls`** — `openpyxl` читает только `.xlsx` (ZIP); для legacy `.xls` (BIFF) добавлено чтение через **`xlrd`** в [`shared/document_extract.py`](shared/document_extract.py); зависимости: [`pyproject.toml`](pyproject.toml), [`services/orchestrator/requirements.txt`](services/orchestrator/requirements.txt).
- **Вложения: PDF/DOCX/XLSX в Telegram** — в [`services/orchestrator/requirements.txt`](services/orchestrator/requirements.txt) добавлены `PyMuPDF`, `Pillow`, `python-docx`, `openpyxl` (как в корневом [`pyproject.toml`](pyproject.toml)); иначе при чтении документов возникало `No module named 'fitz'` — прод-venv оркестратора/бота ставился только по этому файлу.
- **Vision (OpenRouter): medium tier** — устаревший ID `google/gemini-2.5-flash-preview-05-20` в [`config/providers.yaml`](config/providers.yaml) `vision_models.tiers` заменён на `openrouter/google/gemini-2.5-flash`; иначе OpenRouter отвечал HTTP 400 «not a valid model ID».
- **Делегирование в Coder/Blogger** — в `config/agents/balbes.yaml` убраны устаревшие `delegate_targets` на dev-порты (`8001`/`8105`); базовые URL берутся из `CODER_PORT` / `CODER_SERVICE_URL` и `BLOGGER_*` (как на prod), иначе оркестратор получал `httpx.ConnectError` за миллисекунды. Убран двойной префикс `[Agent coder]:` в ответе `delegate_to_agent` (префикс остаётся только в `ToolDispatcher._do_delegate_to_agent`). В [`config/providers.yaml`](config/providers.yaml) для balbes добавлен явный шаблон `pip install *` на случай несовпадения с `pip install {package}`; [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md), [`docs/en/AGENTS_GUIDE.md`](docs/en/AGENTS_GUIDE.md) — URL делегирования, приоритет `data/agents/balbes/config.yaml` над whitelist, heredoc vs `workspace_write`.

### Added
- **Вложения и vision** — `vision_models` в [`config/providers.yaml`](config/providers.yaml); Memory `GET/PUT /api/v1/users/{id}/vision-tier`; оркестратор: предобработка `attachments` (изображения через vision LLM, текст файлов в контексте), суммирование токенов vision в `token_usage`; API **`POST /api/v1/tasks` только с JSON-телом** (`TaskCreateRequest`: `description`, опционально `attachments`, `vision_tier`). Telegram: **`/vision`**, фото и документы → [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py); MAX/web-backend/blogger переведены на `json=`. Документы: [`docs/ru/ATTACHMENTS.md`](docs/ru/ATTACHMENTS.md), правки в [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md).
- **Документация MAX (исходящая разметка)** — расширены [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md) (поток данных, таблицы модулей и UI vs LLM, зеркало, ограничения); обновлены корневые [`README.md`](README.md), [`README.ru.md`](README.ru.md), индексы [`docs/ru/README.md`](docs/ru/README.md), [`docs/en/README.md`](docs/en/README.md); добавлен [`services/webhooks_gateway/README.md`](services/webhooks_gateway/README.md).
- **MAX: исходящая разметка для ответов LLM и зеркала** — текст от оркестратора прогоняется через `model_text_to_max_markdown` (по смыслу как Telegram HTML, но вывод в синтаксис MAX: `++` подчёркивание, лимит 4000, разбиение без разрыва fenced-блоков), `POST /messages` с `format: markdown`; при ошибке отправки — повтор того же фрагмента plain без `format`. Исправлено: продолжения длинного сообщения больше не теряют `format`. [`shared/max_format_outbound.py`](shared/max_format_outbound.py), [`shared/max_api.py`](shared/max_api.py), [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py); тесты [`tests/unit/test_max_format_outbound.py`](tests/unit/test_max_format_outbound.py), [`tests/unit/test_max_api.py`](tests/unit/test_max_api.py); документы [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md), [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md).
- **Скрипт `scripts/max_send_test.py`** — отправка одного тестового сообщения через MAX platform-api (`POST /messages`) для проверки токена на сервере; `--user-id` / `--chat-id` или `NOTIFY_MAX_USER_ID` / `NOTIFY_MAX_CHAT_ID` из env. [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md).
- **Скрипт `scripts/telegram_html_smoke.py`** — быстрая проверка конвертера в Telegram HTML (в т.ч. `||**_…_**||`) без отправки в API. [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md).
- **Диагностика Telegram HTML** — при отправке ответа агента и при зеркалировании в Telegram пишутся структурированные логи: префикс ``telegram_html_outbound`` (чанк, длины, utf16, успех или ``BadRequest`` с текстом API и HTML-телом), для зеркала — ``mirror: telegram``. Упрощает поиск причин plain fallback. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).

### Fixed
- **Vision: HTTP 504 через OpenRouter (Gemini и др.)** — для мультимодальных вызовов задан отдельный таймаут **`vision_models.timeout_seconds`** в [`config/providers.yaml`](config/providers.yaml); при 504/5xx оркестратор перебирает **остальные `id` из `vision_models.tiers`** после выбранного tier. [`shared/vision_models.py`](shared/vision_models.py), [`services/orchestrator/agent.py`](services/orchestrator/agent.py); [`docs/ru/ATTACHMENTS.md`](docs/ru/ATTACHMENTS.md).
- **MAX: ответ уходил не тому peer / не находился target** — в реальных webhook у `recipient` в диалоге часто **два** поля: `chat_id` (диалог) и `user_id` (часто **бот**). При отсутствии `chat_id` старый код брал `recipient.user_id` и мог вызывать `POST /messages?user_id=<id_бота>`. Теперь: вложенный `recipient.chat.chat_id`; если выбираем только `user_id`, для сообщений от человека используется **`sender.user_id`** (человек), когда он отличается от `recipient.user_id`. В `send_max_message` при передаче обоих параметров оставляется только `chat_id`. Для **callback** при пустом target — fallback на `callback.user.user_id`. [`shared/max_webhook.py`](shared/max_webhook.py), [`shared/max_api.py`](shared/max_api.py), [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`tests/unit/test_max_reply_targets.py`](tests/unit/test_max_reply_targets.py), [`tests/unit/test_max_api.py`](tests/unit/test_max_api.py), [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md).
- **Telegram HTML: `||спойлер||` с markdown внутри (`**_жирный курсив_**`, `***…***`)** — спойлер выделялся до разбора `**`/`_`, текст оставался сырым. Тело `||…||` теперь прогоняется через ``model_text_to_telegram_html`` при рендере (аналогично blockquote). [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: спойлер `||… https://…||` ломался** — голый URL матчился как `https://…[^\s<]+` и захватывал закрывающие ``||``, спойлер не применялся. Хвостовые ``|`` срезаются в ``_safe_href_trim`` (как пунктуация у ссылки). **Цитата `>`: `**жирный**` внутри оставался сырым markdown** — тело blockquote сохранялось до markdown-lite; теперь прогон через ``model_text_to_telegram_html`` (как для остального сообщения). [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: при `BadRequest` plain fallback без сырого markdown** — если Telegram отклоняет сгенерированный HTML, повторная отправка без `parse_mode` использует текст из `telegram_rejected_html_to_plain` (теги сняты, ссылки из `<a href>`), а не исходный чанк модели с литералами `**` / `_`. Тест [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py) `test_send_reply_html_fallback_on_badrequest`, `test_telegram_rejected_html_to_plain_strips_tags_keeps_text`.
- **MAX: исходящее сообщение с `chat_id=0` падало** — в `send_max_message` проверка «ровно один из chat_id / user_id» использовала `bool(chat_id)`, из‑за чего `0` считался «пустым» и выбрасывался `ValueError`; ответ в MAX не отправлялся. Проверка переведена на `is not None`. [`shared/max_api.py`](shared/max_api.py), [`tests/unit/test_max_api.py`](tests/unit/test_max_api.py), [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md).
- **Telegram HTML: голые URL и строка `print(...)`** — в тексте «как от модели» ссылки вида `https://…` и `(https://…/)` становятся кликабельными `<a href>`; хвосты `).` не попадают в `href`; одиночная строка `print("…")` оборачивается в inline-code. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: `*_курсив_*` и `***_жирный курсив_***` оставляли сырые `*` и `_`** — парный `_курсив_` обрабатывался после `*` и `***`, внутри `<i>` оставались буквальные подчёркивания. Порядок: сначала `__жирный__` и `_курсив_`, затем `***`, `**`, `*`; после рендера схлопывание вложенных `<i><i>` / `<b><b>`. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: лимит 4096 по UTF-16, не по `len()`** — длинные ответы с эмодзи проходили проверку «длина HTML ≤ 4096» по числу символов Python, тогда как Bot API считает **UTF-16 code units** (большинство эмодзи = 2). Сообщение отклонялось (`BadRequest` / слишком длинное), срабатывал fallback на plain — казалось, что «не работает ничего кроме жирного и кода». Разбиение `raw_chunks_for_telegram_html` переведено на `telegram_message_text_units`. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: «работают только жирный и блок кода»** — грубое разбиение длинного ответа по 4096 символов сырого текста часто резало `*курсив*`, `` `код` ``, `||спойлер||` и содержимое ``` пополам: конвертер выдавал битый Markdown/HTML, Telegram отвечал `BadRequest`, срабатывал fallback на plain без разметки. Введено `split_raw_coarse_for_telegram`: приоритет `\\n\\n` / `\\n` / `. ` / пробел, окно поиска назад до 3500 символов, перенос разреза перед ``` если он попадал внутрь блока. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), тест [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: цитата в шаблоне `MD: > …`** — строка не начиналась с `>`, символ экранировался (`&gt;`), blockquote не применялся. Распознавание: `>…`, `MD:/HTML: >…`, опционально `[n] ` в начале строки. Добавлены `***жирный курсив***` → `<b><i>…</i></b>`, золотой тест фрагмента «тест №3», расширен лог при `BadRequest` (префикс тела сообщения). [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: разметка пропадала** — сырой текст резался по 4096 символов, после экранирования (`&amp;`, `&lt;`, теги) сообщение превышало лимит API, срабатывал fallback на plain. Добавлено разбиение `raw_chunks_for_telegram_html` так, чтобы длина текста после `model_text_to_telegram_html` не превышала 4096. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py).
- **Telegram HTML: «ломалась» вся разметка кроме `**bold**`** — конвертер экранировал весь текст до разметки, поэтому ответы модели с `<b>`, `<i>` превращались в `&lt;b&gt;` и отображались как текст; не поддерживались `__bold__`, `*курсив*`, `_курсив_`, `||спойлер||`, `[текст](url)`, `> цитата`, `### заголовок`. Расширен `model_text_to_telegram_html`: markdown-lite, простые пары разрешённых тегов и `<spoiler>` → `<tg-spoiler>`. Вложенный HTML без изменений не разбирается. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Telegram HTML: вложенные теги и плейсхолдеры** — при `<b><i>…</i></b>` внешний тег хранил внутренний плейсхолдер; подстановка шла по порядку 0,1 и ломала разметку (видимые `PH00000` / сырой текст). Финальный рендер заменён на рекурсивное раскрытие плейсхолдеров. Добавлены `~~зачёркнутое~~` → `<s>`, `<a href='…'>`, fallback на plain только при `telegram.error.BadRequest`, отправка с `ParseMode.HTML`. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py).

### Changed
- **Ответы агента в Telegram (HTML)** — основной ответ оркестратора, фоновый монитор и зеркалирование во второй канал отправляются с `parse_mode="HTML"`: `model_text_to_telegram_html` экранирует произвольный текст и преобразует inline-код в обратных кавычках, пары `**жирный**` и fenced-блоки ``` в допустимые теги Telegram; при ошибке отправки тот же фрагмент уходит без разметки. Ранее использовавшийся legacy Markdown для этих путей отключён. [`shared/telegram_app/format_outbound.py`](shared/telegram_app/format_outbound.py), [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py), тесты [`tests/unit/test_format_outbound.py`](tests/unit/test_format_outbound.py).
- **Активный чат по каналам (Telegram / MAX)** — после связки аккаунтов отдельные указатели `active_chat:{canonical}:telegram` и `:max`; API `GET/PUT /chats/.../active?channel=`. Зеркалирование ответа во второй мессенджер только если там активен **тот же** `chat_id`. [`services/memory-service/clients/redis_client.py`](services/memory-service/clients/redis_client.py), [`services/memory-service/api/history.py`](services/memory-service/api/history.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py), [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py), [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`routes/max_chat.py`](services/webhooks_gateway/routes/max_chat.py).

### Added
- **Allowlist целей зеркалирования** — `AGENT_REPLY_MIRROR_PROVIDERS` (по умолчанию `telegram,max`; пустая строка = не дублировать в связанные каналы). [`shared/config.py`](shared/config.py), [`shared/outbound/mirror.py`](shared/outbound/mirror.py).
- **Зеркалирование ответов агента Telegram ↔ MAX** — после связки аккаунтов дублирование текста во второй канал при активном **presence** (входящие сообщения обновляют окно TTL); Redis `identity:peers:{uuid}`, `channel_presence:{uuid}`; Memory API `GET /api/v1/identity/peers`, `POST /api/v1/identity/presence/touch`, `GET /api/v1/identity/presence/active`; конфиг `AGENT_REPLY_MIRROR_ENABLED`, `AGENT_REPLY_MIRROR_PRESENCE_TTL_SECONDS`. Интеграция: [`shared/outbound/mirror.py`](shared/outbound/mirror.py), [`shared/identity_client.py`](shared/identity_client.py), [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py).

### Fixed
- **Webhooks Gateway не поднимался после зеркалирования** — циклический импорт: `shared.outbound.mirror` → `telegram_app.text` подгружал пакет `telegram_app`, чей `__init__.py` тянул `balbes_bot`, который снова импортировал `mirror`. Экспорт `BalbesTelegramBot` / `run_bot` сделан ленивым (`__getattr__`). [`shared/telegram_app/__init__.py`](shared/telegram_app/__init__.py).
- **Notify в MAX** — доставка через **`NOTIFY_MAX_USER_ID`** (POST `/messages?user_id=`), т.к. для личных сообщений API отличает `user_id` от `chat_id`; прежний вариант только с `NOTIFY_MAX_CHAT_ID` мог не доставлять в личку. [`shared/notify/delivery.py`](shared/notify/delivery.py), [`shared/config.py`](shared/config.py) (`NOTIFY_MAX_USER_ID`).

### Changed
- **Документация notify / MAX** — в [`docs/ru/WEBHOOK_NOTIFY.md`](docs/ru/WEBHOOK_NOTIFY.md) уточнены `NOTIFY_DELIVERY_CHANNELS`, `NOTIFY_MAX_CHAT_ID`, `MAX_ALLOWED_USER_IDS`; в [`.env.prod.example`](.env.prod.example) добавлены комментарии к `MAX_ALLOWED_USER_IDS` и `NOTIFY_MAX_CHAT_ID`.

### Added
- **Скрипт `scripts/diagnose_telegram_stack.sh`** — проверка health Memory/Orchestrator/Webhooks Gateway, вывод `getWebhookInfo` (URL webhook, `last_error_message`), хвост `logs/<env>/webhooks-gateway.log` и `journalctl` для `balbes-webhooks-gateway`. См. таблицу скриптов в [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md).
- **Одноразовый код при привязке аккаунтов Telegram ↔ MAX** — `POST /api/v1/identity/pairing/create`, `POST /api/v1/identity/pairing/redeem`; Redis `identity:pair:{CODE}`; при redeem стирается история **вторичного** канала (namespace старого id), затем привязка к `canonical_user_id` инициатора. Команды: Telegram `/link max` + ввод кода в MAX `/link КОД`; MAX `/link telegram` + ввод кода в Telegram `/link КОД`. Документация: [`docs/ru/IDENTITY_AND_OPENROUTER_USER.md`](docs/ru/IDENTITY_AND_OPENROUTER_USER.md).
- **Канонический `user_id` (UUID)** — единый идентификатор пользователя для Memory, оркестратора и поля OpenRouter `user` (биллинг/аналитика). Memory Service: `GET /api/v1/identity/resolve?provider=telegram|max&external_id=...` → `{ canonical_user_id, created }`; Redis `identity:link:{provider}:{external_id}`; при первом резолве переименование legacy-ключей `chats:*`, `history:*`, `agent_session:*` с `telegram` decimal id или `max:<id>` на новый UUID ([`services/memory-service/api/identity.py`](services/memory-service/api/identity.py), [`clients/redis_client.py`](services/memory-service/clients/redis_client.py)). Клиент: [`shared/identity_client.py`](shared/identity_client.py). Telegram и MAX вызывают резолв перед обращениями к Memory и `POST /api/v1/tasks`; оркестратор передаёт `user` в chat completions ([`services/orchestrator/agent.py`](services/orchestrator/agent.py)).
- **`POST /api/v1/identity/link`** — привязка второго канала к выбранному `canonical_user_id` (слияние Telegram и MAX); опционально `IDENTITY_LINK_SECRET` / `X-Balbes-Identity-Link-Secret`. Конфликт, если у обеих сторон уже есть данные чатов.
- **OpenRouter `user` расширенно** — эмбеддинги Memory/skills-registry и вызовы без пользовательской сессии используют `OPENROUTER_SERVICE_USER` (по умолчанию `balbes-service`); облачный STT и LLM-коррекция голоса получают канонический UUID; инструменты `code_search` / `index_codebase` — UUID из контекста задачи. Документация: [`docs/ru/IDENTITY_AND_OPENROUTER_USER.md`](docs/ru/IDENTITY_AND_OPENROUTER_USER.md).

### Changed
- **Telegram `BalbesTelegramBot`** — запросы к оркестратору идут на **`ORCHESTRATOR_URL`** / [`settings.orchestrator_url`](shared/config.py), как у webhooks-gateway для MAX, а не на жёстко заданный `http://localhost:{orchestrator_port}`.
- **Дефолтная LLM (OpenRouter)** — дефолт чата: **`meta-llama/llama-3.3-70b-instruct`** (дешёвая платная tier, не free): [`shared/config.py`](shared/config.py) `default_chat_model`, первый пункт `active_models`, `default_fallback_chain` / `cheap_models`, у агента **balbes** `default_model` и обновлённая `fallback_chain` (MiniMax → free → Llama 3.1 8B). Heartbeat остаётся на **`minimax/minimax-m2.5:free`**. Ранее цепочки были переведены с исчезнувшего `stepfun/step-3.5-flash:free` на **`minimax/minimax-m2.5:free`**; **balbes** с `fallback_enabled: true` и повтором при **HTTP 404** — [`services/orchestrator/agent.py`](services/orchestrator/agent.py). Сиды [`scripts/init_db.py`](scripts/init_db.py): orchestrator → Llama 3.3 70B, coder/blogger → Kimi. [`services/blogger/agent.py`](services/blogger/agent.py): `_CHEAP_MODEL` без ошибочного суффикса `:free`.

### Added
- **Скрипт `scripts/max_subscriptions.py`** — `list` (GET /subscriptions), `delete` (DELETE по `url`), `apply` (POST + проверка списка; опция `--delete-first` при смене секрета). Документация: [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md).

### Added
- **MAX UX (как в Telegram)** — slash-команды `/start`, `/help`, `/chats`, `/model`, `/agents`, `/newchat`, `/rename`, `/clear`, `/status` обрабатываются через Memory Service (без LLM); inline-кнопки меню и переключение чата/модели/агента через `message_callback` + [`POST /answers`](https://dev.max.ru/docs-api/methods/POST/answers); индикатор набора через [`POST /chats/{id}/actions`](https://dev.max.ru/docs-api/methods/POST/chats/-chatId-/actions) `typing_on`. Код: [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`routes/max_chat.py`](services/webhooks_gateway/routes/max_chat.py), [`shared/max_bot_ui.py`](shared/max_bot_ui.py), [`shared/max_api.py`](shared/max_api.py). Подписка: добавьте **`message_callback`** в `update_types` и при необходимости выполните `scripts/max_subscriptions.py apply --delete-first` — см. [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md).

### Fixed
- **`read_agent_logs`** — нормализация аргументов от LLM/MAX: строки `null`/`none`, пустые поля, `limit` как строка; `tool_filter: "null"` больше не ищет несуществующий инструмент; понятные сообщения при неверной дате. [`shared/agent_tools/registry.py`](shared/agent_tools/registry.py), [`services/orchestrator/agent_logger.py`](services/orchestrator/agent_logger.py); тесты [`tests/unit/test_read_agent_logs_args.py`](tests/unit/test_read_agent_logs_args.py).
- **MAX → оркестратор** — для `httpx` заданы отдельные `connect`/`read`/`pool` таймауты (длинный read = `task_timeout_seconds + 120`), чтобы реже получать обрыв «Server disconnected without sending a response». [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py).
- **MAX webhook** — подробные логи на ранних выходах (не `message_created`, whitelist `MAX_ALLOWED_USER_IDS`, нет цели ответа, пустой текст, нет токена) и при постановке фона ответа; разбор `recipient.chat_id` через `_to_int` с предупреждением при невалидном значении. [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py), [`shared/max_webhook.py`](shared/max_webhook.py).
- **MAX исходящие сообщения** — заголовок `Authorization` для `platform-api.max.ru` без префикса `Bearer` (как в официальном curl); иначе API отвечал `401` / `No access token`. [`shared/max_api.py`](shared/max_api.py) (`normalize_max_access_token`).
- **MAX webhook** — проверка входящих запросов по официальному заголовку **`X-Max-Bot-Api-Secret`** (как при подписке `POST /subscriptions` на platform-api.max.ru); прежний **`X-Signature`** (HMAC) оставлен для совместимости. Документация: [`docs/ru/MAX_WEBHOOK.md`](docs/ru/MAX_WEBHOOK.md).

### Added
- **OpenRouter app attribution** — общие заголовки `HTTP-Referer`, `X-OpenRouter-Title` / `X-Title` (и опционально `X-OpenRouter-Categories`) для всех запросов к `openrouter.ai` через [`shared/openrouter_http.py`](shared/openrouter_http.py); переменные `OPENROUTER_HTTP_REFERER`, `OPENROUTER_APP_TITLE`, `OPENROUTER_CATEGORIES` в [`shared/config.py`](shared/config.py).
- **MAX мессенджер** — разбор `message_created` в [`services/webhooks_gateway/routes/max.py`](services/webhooks_gateway/routes/max.py): фоновый вызов оркестратора (`ORCHESTRATOR_URL`), ответ через [`shared/max_api.py`](shared/max_api.py) (`POST /messages` с query `chat_id` / `user_id`); whitelist `MAX_ALLOWED_USER_IDS`. Notify-доставка MAX переведена на тот же клиент.

### Changed
- **`ORCHESTRATOR_URL` в окружении** — для MAX/webhooks gateway оркестратор должен быть доступен по HTTP: в локальный **`dev/.env`** добавлена строка `ORCHESTRATOR_URL=http://localhost:8102` рядом с `ORCHESTRATOR_PORT` (сам `.env` в `.gitignore`); шаблоны **`dev/.env.dev`**, **`dev/.env.prod`**, **`balbes/.env.prod.example`** уже содержат переменную; в **[`balbes/.env.example`](../balbes/.env.example)** добавлено для паритета.
- **Конфигурация**: `jwt_secret` в [`shared/config.py`](shared/config.py) принимает **`JWT_SECRET` или `JWT_SECRET_KEY`**; [`scripts/start_prod.sh`](scripts/start_prod.sh) требует наличие хотя бы одного. **`.env.prod.example`**, шаблон **`dev/.env.prod`** и **`balbes/.env.prod`** дополнены блоком webhooks и `BLOGGER_SERVICE_URL` (вместо устаревшего `BLOGGER_URL`). [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md) — ссылка на `.env.prod.example`.
- **Мониторинг notify** — только `POST /webhook/notify` на [`services/webhooks_gateway`](services/webhooks_gateway); путь `POST /api/webhooks/notify` удалён; дашборд без endpoint мониторинга.
- **Prod + systemd**: [`scripts/start_prod.sh`](scripts/start_prod.sh) запускает **`balbes-webhooks-gateway`**, если установлен unit; иначе — предупреждение в логе. Пример unit и `enable` — [`DEPLOYMENT.md`](DEPLOYMENT.md). [`scripts/stop_prod.sh`](scripts/stop_prod.sh): остановка gateway и порт **18180** в fallback. [`docs/ru/WEBHOOK_NOTIFY.md`](docs/ru/WEBHOOK_NOTIFY.md) — пояснение про `Connection refused` без unit.

### Added
- **Сервис `services/webhooks_gateway`** — отдельный FastAPI от дашборда: `POST /webhook/telegram` (PTB webhook при `TELEGRAM_BOT_MODE=webhook`), `POST /webhook/max` (проверка `MAX_WEBHOOK_SECRET`), `POST /webhook/notify` (перенесено с web-backend). Порт `WEBHOOKS_GATEWAY_PORT`. При `TELEGRAM_BOT_MODE=webhook` процесс `telegram_bot.py` polling не запускается ([`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py)). [`shared/max_inbound.py`](shared/max_inbound.py).
- **Документация notify**: [`docs/ru/WEBHOOK_NOTIFY.md`](docs/ru/WEBHOOK_NOTIFY.md) — запуск, nginx, настройка источника на RU-сервере; в [`TODO.md`](TODO.md) добавлен блок «Следующие этапы (multi-messenger / webhooks)».
- **Мониторинг: входящий webhook** — `Authorization: Bearer WEBHOOK_NOTIFY_API_KEY`, лимит по IP (`NOTIFY_RATE_LIMIT_PER_MINUTE`), доставка в Telegram (HTML) и опционально MAX. Код: [`shared/notify/`](shared/notify/).
- Скрипт **`scripts/export_memory_chats_to_data_for_agent.py`** (+ обёртка **`scripts/export_chats_for_agent.sh`**) — выгрузка всех чатов Memory из Redis в `data_for_agent/` у корня деплоя, папки `{memory_user_id}__{agent_id}__{chat_id}/`. Документация: [`docs/ru/DEPLOYMENT.md`](docs/ru/DEPLOYMENT.md) (раздел Redis).
- **Единая матрица slash-команд Telegram** — [`shared/telegram_app/telegram_command_matrix.py`](shared/telegram_app/telegram_command_matrix.py): порядок меню и регистрация обработчиков для оркестратора и бизнес-бота блогера по `TelegramFeatureFlags` и [`config/agents/*.yaml`](config/agents/balbes.yaml).
- **Memory namespace для Telegram-агентов** — [`shared/telegram_app/memory_namespace.py`](shared/telegram_app/memory_namespace.py): канонический ключ `{agent_id}_{telegram_user_id}`; для блогера запись в `blogger_<id>`, чтение с fallback на legacy `bbot_<id>`. Класс `TelegramMemoryNamespace` для подключения новых сервисов без дублирования формулы `user_id`.
- **Паритет команд блогера** с оркестратором (через те же флаги `telegram:`): status, tasks, agents, mode, remember, recall, heartbeat и др.; `/debug` для блогера с настройками чата в Memory.
- **Telegram UI по манифесту** — `TelegramFeatureFlags` в [`shared/agent_manifest.py`](shared/agent_manifest.py), блок `telegram:` в [`config/agents/balbes.yaml`](config/agents/balbes.yaml) / [`config/agents/blogger.yaml`](config/agents/blogger.yaml). Оркестраторский бот и бизнес-бот блогера регистрируют команды и хендлеры по флагам; общие [`shared/telegram_app/text.py`](shared/telegram_app/text.py) и [`shared/telegram_app/voice.py`](shared/telegram_app/voice.py) для текста и STT.
- **Единая архитектура делегирования** — `delegate_to_agent` вызывает только HTTP `POST /api/v1/agent/execute` (Coder и Blogger); общий контракт [`shared/agent_execute_contract.py`](shared/agent_execute_contract.py), опциональный заголовок `X-Balbes-Delegation-Key` при заданном `DELEGATION_SHARED_SECRET`. Манифест оркестратора [`config/agents/balbes.yaml`](config/agents/balbes.yaml): `delegate_targets` и пер-режимные allowlist инструментов через [`shared/agent_manifest.py`](shared/agent_manifest.py).
- **Blogger execute API** — [`services/blogger/api/execute.py`](services/blogger/api/execute.py) и метод `BloggerAgent.execute_delegate_task()` для ответов по делегированию.
- **Telegram UI оркестратора** — реализация перенесена в [`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py); [`services/orchestrator/telegram_bot.py`](services/orchestrator/telegram_bot.py) остаётся точкой входа (`python -m services.orchestrator.telegram_bot`).
- Пример второго бота: [`scripts/run_second_orchestrator_bot.example.sh`](scripts/run_second_orchestrator_bot.example.sh).
- **Гибридная транскрипция голоса (Telegram)** — короткие сообщения: локально **openai-whisper** (`WHISPER_LOCAL_MODEL`, по умолчанию `medium`); длинные или без `duration`: облако — **OpenRouter** (multimodal `input_audio`) и/или **Yandex SpeechKit** (`WHISPER_REMOTE_BACKEND`: `openrouter` · `yandex` · `openrouter_then_yandex`). Новые модули `whisper_remote_stt.py`, расширен `shared/config` и `.env.example`; в режиме `/debug` в чат выводится выбранный STT-путь.

### Fixed
- **Heartbeat** — при `source=heartbeat` пустой ответ LLM не подменяется на пользовательское сообщение «модель вернула пустой ответ» ([`services/orchestrator/agent.py`](services/orchestrator/agent.py)); для обычных задач текст подсказки без изменений. Доставка в Telegram: подавление `HEARTBEAT_OK` с внешними кавычками/обёртками ([`shared/telegram_app/balbes_bot.py`](shared/telegram_app/balbes_bot.py)).

### Changed
- Экспорт чатов Memory: каталоги `{memory_user_id}__{agent_id}__{chat_id}/` (видно `blogger_<tg>` vs числовой id); лог namespace блогера; загрузка env и подсказки Redis — [`docs/ru/DEPLOYMENT.md`](docs/ru/DEPLOYMENT.md).
- Документация: [`docs/ru/AGENTS_GUIDE.md`](docs/ru/AGENTS_GUIDE.md) — секция Blogger (Memory `blogger_*`, матрица команд); [`docs/ru/CONFIGURATION.md`](docs/ru/CONFIGURATION.md) / [`docs/en/CONFIGURATION.md`](docs/en/CONFIGURATION.md) — `memory_namespace`, `/debug` для блогера; [`docs/en/AGENTS_GUIDE.md`](docs/en/AGENTS_GUIDE.md) — namespaces.
- Документация (CONFIGURATION, GETTING_STARTED, README): описание голоса приведено к openai-whisper + облачный STT вместо устаревших упоминаний faster-whisper.

## [0.5.0] - 2026-04-04

### Added
- **`recall_from_memory(query, limit)`** — инструмент семантического поиска в долгосрочной памяти Qdrant; добавлен в `AVAILABLE_TOOLS` и реализован через `/api/v1/memory/search`.
- **`code_search(query, path_filter, limit)`** — семантический поиск по кодовой базе проекта (файловый уровень). Индексирует `.py`, `.ts`, `.yaml`, `.md` и другие расширения в Qdrant коллекцию `code_index`.
- **`index_codebase(path, force)`** — ручная переиндексация файлов проекта. Пропускает неизменённые файлы по `mtime`; `force=True` переиндексирует всё.
- **`manage_todo(action, section, item)`** — инструмент для чтения и обновления `TODO.md`: `read` (показать), `add` (добавить пункт), `done` (отметить выполненным).
- **`file_patch(path, old_string, new_string)`** — точечная замена строки в файле вместо полной перезаписи (добавлено в предыдущем сезоне, задокументировано здесь).
- **`_split_message(text, limit=4096)`** — автоматическое разбиение длинных сообщений Telegram на части по 4096 символов с учётом переносов строк. Применяется ко всем путям отправки (debug trace, результат задачи, bg monitor, heartbeat).
- **Rate limiting** — `ToolDispatcher._call_counts` и `_RATE_LIMITS` ограничивают число вызовов каждого инструмента за одну задачу (web_search: 10, fetch_url: 15, execute_command: 30, остальные: 20). `reset_call_counts()` вызывается в начале каждой задачи.
- **Учёт токенов** — `_call_llm()` теперь возвращает `usage_dict`; токены накапливаются через все раунды `_run_llm_with_tools`. По завершении задачи данные записываются fire-and-forget через `/api/v1/tokens/record`.
- **LLM саммаризация истории** — `_maybe_summarize_history()` при `memory.history_strategy: "summarize"` вызывает дешёвую LLM для краткого пересказа старых сообщений. Саммари кэшируется в Redis на 7 дней (ключ `balbes:history_summary:{user_id}:{chat_id}`).
- **`CodeIndexer`** — новый модуль `services/orchestrator/skills/code_indexer.py` с классом `CodeIndexer`; использует OpenRouter embeddings + Qdrant `AsyncQdrantClient`.
- **`_save_message_to_history()`** в `TelegramBot` — heartbeat-сообщения и ошибки теперь сохраняются в активный чат пользователя через memory service.

### Changed
- **`/stop`** теперь всегда отправляет cancel-сигнал оркестратору (`_cancel_orchestrator_task()`) до проверки наличия активных задач — останавливает как foreground, так и background задачи агентов.
- **LLM timeout** читается из `config/providers.yaml → providers.openrouter.timeout` (поднят с 60 до 120 секунд) и применяется явно в каждом вызове `_call_llm()`.
- **`_run_llm_with_tools()`** возвращает `tuple[str, str, dict]` — добавлен `total_usage` (накопленные токены).
- **`build_messages_for_llm()`** принимает опциональный `history_summary: str | None`; если задан, вставляется как системное сообщение перед обрезанными записями истории.
- **Прогресс в Telegram** (agent mode, debug off): показывает компактный индикатор `⚙️ Работаю… раунд N | tool1 · tool2`, редактируемый на месте.

### Fixed
- **`httpx.ReadTimeout`** при POST `/api/v1/tasks` теперь обрабатывается gracefully: показывается «⏳ Задача выполняется дольше 120 с» вместо падения с ошибкой.
- Все пути отправки сообщений в Telegram обёрнуты в `_split_message` — `BadRequest: Message is too long` больше не возникает.

## [0.4.0] - 2026-03-30

### Added
- **Yandex Search API v2** — migrated from legacy XML API (user+key in URL, IP whitelist required)
  to new Yandex Cloud REST API (`searchapi.api.cloud.yandex.net`). Authentication via
  `Authorization: Api-Key` header. Supports both sync (`/v2/web/search`) and async deferred
  (`/v2/web/searchAsync` + operations polling) modes. Response `rawData` (base64 XML) decoded
  and parsed by the existing XML parser.
- **`YANDEX_FOLDER_ID`** config field — required for Yandex Search API v2 (Yandex Cloud folder ID).
- **`file_read` / `file_write` tools** — Coder and Orchestrator agents can now read and write
  project files directly, with path-traversal protection and forbidden-file-type blocklist.
- **`web_search` provider parameter** — agents can explicitly request a search provider via
  the `provider` tool argument (e.g. `provider=yandex`); the used provider is shown in the
  debug trace as `[tavily] 5 result(s):`.
- **Heartbeat inter-round delay** — configurable `request_delay_seconds` (default 5s) between
  LLM rounds in heartbeat runs to avoid rate-limit errors on free OpenRouter models.
- **Coder agent full dev capabilities** — expanded `execute_command` whitelist in `agent` mode
  to include `grep`, `rg`, `cp`, `mv`, `mkdir`, `touch`, `diff`, `tree`, `which`, `bash`, `sh`,
  `chmod`; added `file_read`/`file_write` tools and updated `AGENTS.md` documentation.

### Changed
- `web_search.py`: `search()` now returns `tuple[list[SearchResult], str]` — results plus provider name used.
- `web_search.py`: DuckDuckGo provider removed; Tavily set as default provider.

### Fixed
- `tools.py`: `_do_web_search` — fixed `'SearchResult' object is not subscriptable` by switching from
  dict-style access to dataclass attribute access (`r.title`, `r.url`, `r.snippet`).

## [0.3.0] - 2026-03-29

### Added
- **XML tool-call parsing** — supports models (MiniMax, etc.) that embed tool calls in XML
  format inside message content instead of using the standard JSON `tool_calls` field.
  Handles both `<prefix:tool_call>` and `<prefix:toolcall>` variants (with or without underscore).
- **Tool-name normalization** (`_normalize_tool_name`) — maps de-underscored tool names that
  some LLMs produce (e.g. `readagentlogs` → `read_agent_logs`, `delegatetoagent` → `delegate_to_agent`)
  for both XML-parsed and standard JSON tool calls.
- **Background task monitoring** (`_bg_monitor_loop`) — Telegram bot polls the orchestrator
  every 5 seconds for background task progress; debug events are streamed to the chat in real
  time and the final result is sent automatically upon task completion.
- **`_ensure_bg_monitors`** — catch-all that starts monitors for any running background tasks
  not yet being tracked (survives bot restarts and missed `background_tasks_started` signals).
- **`/tasks` command** — displays the global task registry (running + recent) with agent,
  status, timing, and automatically starts monitors for any running background tasks.
- **Task registry** (`_task_registry`) — in-memory registry (capped at 50 entries) tracking
  all foreground and background tasks with status, timings, and agent metadata.
- **Background debug buffer** (`_bg_debug_buffer`) — live debug-event queue per background task,
  drained by `poll_bg_task` and streamed to the Telegram chat.
- **`list_agent_tasks` tool** — orchestrator tool allowing the agent to query and display
  the task registry in chat.
- **`delegate_to_agent` tool** — orchestrator can hand off tasks to specialist agents (e.g.
  Coder) in foreground or background mode; result is returned or auto-delivered.
- **`get_agent_result` / `cancel_agent_task` tools** — retrieve or cancel background tasks.
- **Agent delegation with isolated context** — sub-agents receive their own `ToolDispatcher`
  instance with a separate whitelist, preventing privilege escalation.
- **Per-agent `config.yaml`** — each agent workspace may contain `config.yaml` that overrides
  `default_model`, `token_limits`, and `server_commands` with highest priority.
- **`/debug` mode** — per-chat toggle; when on, every LLM round and tool call is sent to the
  chat as an HTML-formatted trace including agent name, model, elapsed time.
- **`/mode` command** — per-chat toggle between `ask` (safe read-only whitelist) and `agent`
  (full development whitelist including git, pytest, pip, docker).
- **`/stop` command** — cancels the active task for the current user and terminates any running
  background monitors.
- **Heartbeat proactive messaging** — background scheduler sends proactive messages based on
  `HEARTBEAT.md` and `MEMORY.md`; runs on free LLM models with a configurable fallback chain
  (free → cheapest paid → error); respects `active_hours_start/end`.
- **Voice message transcription** — `faster-whisper` + LLM grammar correction; transcribed
  text is shown before the agent response.
- **Web search skill** — supports DuckDuckGo (default), Brave, and Tavily with provider
  switching via `providers.yaml`.
- **URL fetch skill** — `httpx` + `html2text`; max 5000 chars, configurable timeout.
- **Activity logging** — per-agent JSONL logs (date-based) tracking every tool call with
  timestamps, duration, success flag, and source (`user` / `heartbeat`). Readable via
  `read_agent_logs` tool.
- **Agent workspace files** — each agent has a workspace directory with `SOUL.md`, `AGENTS.md`,
  `MEMORY.md`, `HEARTBEAT.md`, `TOOLS.md`, `IDENTITY.md`, `config.yaml`. The agent can read
  and write these files, enabling self-modification of instructions and persistent memory.
- **Private memory versioning** — `data/agents/` is a separate private GitHub repository;
  every workspace file write triggers an auto-commit + debounced auto-push (30-second window).
- **Multi-chat session management** — each Telegram chat has its own Redis-backed history,
  name, chosen model, and agent; `/chats` lists all sessions with IDs and switches between them.
- **Access control** — only whitelisted `TELEGRAM_USER_ID` values can interact with the bot;
  unauthorized users receive a rejection message.
- **Model tiers** (`free` / `cheap` / `medium` / `premium`) — structured in `providers.yaml`;
  `free` is the default; `medium` and `premium` require explicit user selection.
- **Per-agent model configuration** — each agent in `providers.yaml` and `config.yaml` may set
  `default_model`, `fallback_enabled`, `fallback_chain`, and `token_limits`.
- **Detailed error messages** — on LLM failure the exact HTTP status, provider error body, and
  exception type are relayed to the user; `fallback_enabled: false` (default) means failures are
  shown immediately, not silently retried.
- **Host timezone propagation** — Docker containers mount `/etc/localtime` and `/etc/timezone`
  from the host; Python services use `datetime.now().astimezone()` — no hard-coded timezone.
- **`LLMUnavailableError`** — dedicated exception for LLM failures; `execute_task` catches it
  and returns `status: "failed"` so heartbeat does not forward error text as a normal message.
- **`uvicorn --workers 1`** — orchestrator is forced to single worker to prevent in-memory
  task registry and debug buffer fragmentation across processes.

### Changed
- `_run_llm_with_tools` now accepts an explicit `dispatcher` parameter for isolated sub-agent
  execution; always attaches debug collector to the dispatcher when `debug_events` is provided.
- `execute_task` snapshots `_background_tasks` before/after the LLM loop to detect newly
  started background delegations and include them in the result.
- `poll_bg_task` no longer pops the result — monitor reads it without consuming; `get_agent_result`
  remains responsible for consuming so "Нет результатов" no longer appears after auto-delivery.
- Background task monitor suppresses the internal fallback text ("Не смог обработать запрос…")
  from being shown as a task result; adds `(результат в логах)` note instead.
- Debug trace output switched from MarkdownV2 to HTML (`parse_mode="HTML"`) for robust handling
  of all special characters in LLM responses and tool outputs.
- Agent debug events now include the agent name tag (`[orchestrator]`, `[coder]`) for clarity
  during delegation.
- Coder agent uses its own configured `default_model` (Kimi K2.5) when delegated — does not
  inherit the Orchestrator's active chat model.
- Git commands for Coder agent whitelist use `git -C {path}` pattern instead of `cd && git`.
- `AGENTS.md` and `TOOLS.md` workspace files separated: operational instructions in `AGENTS.md`,
  tool documentation in `TOOLS.md`.

### Fixed
- XML regex now uses backreference (`<\1>`) matching any `<prefix:tag>` wrapper — fixes
  `<minimax:toolcall>` variant (without underscore) being silently ignored.
- Tool-name de-underscoring (`readagentlogs`, `delegatetoagent`, etc.) no longer causes
  "unknown tool" errors with MiniMax models.
- Heartbeat no longer sends "Не смог обработать запрос" or `LLMUnavailableError` text to the
  user chat on model failures.
- `can't find end of the entity` Telegram `BadRequest` errors eliminated by switching to HTML
  parse mode for dynamic content.
- `/tasks` command no longer shows "Нет задач в реестре" when a background task is running
  (fixed by `--workers 1` and `_ensure_bg_monitors`).

## [0.2.0] - 2026-03-28

### Added
- Telegram bot integration with `python-telegram-bot`: polling, per-user concurrency lock,
  global middleware for access control, `ApplicationHandlerStop` for unauthorized users.
- Multi-chat session management in Redis: per-chat history (7-day TTL with lazy cleanup),
  chat name, model, agent assignment. Commands: `/chats`, `/newchat`, `/rename`.
- Agent switching via `/agents` inline keyboard; each chat remembers its assigned agent.
- Model selection per chat via `/model` inline keyboard with tier-based display.
- Orchestrator `OrchestratorAgent` class: `execute_task`, `_run_llm_with_tools`, tool dispatch
  loop, workspace file management, multi-provider LLM calls.
- `AgentWorkspace` — loads and caches MD workspace files; auto-commit+push to private Git repo
  on every write via `WorkspaceVersioning`.
- `ToolDispatcher` — registers and dispatches tools: `web_search`, `fetch_url`,
  `execute_command`, `workspace_read`, `workspace_write`, `rename_chat`, `save_to_memory`,
  `read_agent_logs`.
- `providers.yaml` — central config for providers, models, tiers, per-agent settings,
  heartbeat, whisper, skills, and memory strategy.
- `AgentLogger` — per-agent JSONL activity log files in `data/logs/agent_activity/`.
- Long-term memory in Qdrant: `save_to_memory` / `recall_from_memory` tools (explicit only).
- Voice transcription: `faster-whisper` + ffmpeg + LLM correction pass.
- `setup_memory_repo.sh` — initializes the private memory Git repo (handles empty remote).
- FastAPI orchestrator API: `POST /api/v1/tasks`, `GET /api/v1/tasks`, health endpoint.
- Health-check script updated to detect `telegram_bot.py` process by name.

### Changed
- `qdrant-client` version relaxed to `>=1.7.0` for Python 3.13 compatibility.
- `python-telegram-bot` concurrent updates set via `Application.builder().concurrent_updates(False)`.
- `data/agents/` excluded from main `.gitignore` and tracked in the separate memory repo.

### Fixed
- `ModuleNotFoundError: No module named 'apt_pkg'` — use `.venv/bin/pip` instead of system pip.
- `fatal: ambiguous argument 'HEAD'` in `setup_memory_repo.sh` for empty remote repos.
- `/chats` MarkdownV2 `BadRequest` — all dynamic text escaped via `_escape_md2()`.

## [0.1.0-mvp] - 2026-03-27

### Added
- Multi-environment runtime model (`dev`/`test`/`prod`) with isolated ports and data paths on one server.
- Dedicated run scripts for each environment and cross-environment status checks.
- Release readiness documentation:
  - `RELEASE_CHECKLIST.md`
  - updated runbook guidance in `DEPLOYMENT.md`, `README.md`, `PROJECT_GUIDE.md`, `TODO.md`

### Changed
- Production app ports moved to `18100..18200` and infra ports to isolated `15xxx/16xxx` ranges.
- Health checks updated to support explicit `dev|test|prod` modes and auto-detection.
- Stop/start scripts hardened to use explicit compose files and path-safe project root resolution.
- Python runtime baseline aligned to Python 3.13 in deployment docs and operational flow.

### Fixed
- Skills workflow integration test made deterministic against semantic-search indexing lag.
- Production startup/stop scripts fixed for user-level logging and PID tracking.
- Qdrant local production client mode fixed for HTTP operation (`https=False`) to avoid SSL mismatch.
- Python compatibility issues around `datetime.UTC` usage corrected.

### Security
- Production environment requirements reinforced in docs (`WEB_AUTH_TOKEN`, JWT secrets, non-default secrets).

## [0.1.0] - 2026-03-26

### Added
- Initial project structure
- Documentation:
  - Technical specification
  - MVP scope definition
  - Project structure
  - Data models and DB schemas
  - API specification
  - Agents guide
  - Development plan
  - Deployment guide
  - Architecture decisions
  - Configuration guide
  - Examples and use cases
- Environment configuration (.env.example)
- README with project overview

### Notes
- This is the planning phase
- Development starts after this
- MVP target: 15-20 days

---

## Release Notes Template (for future releases)

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New features
- New agents
- New skills

### Changed
- Modified existing functionality
- Updated dependencies
- Configuration changes

### Fixed
- Bug fixes
- Performance improvements

### Deprecated
- Features marked for removal

### Removed
- Removed features

### Security
- Security updates and fixes
```

---

## Version Numbering

**Format**: MAJOR.MINOR.PATCH

- **MAJOR**: Incompatible API changes
- **MINOR**: New functionality (backward-compatible)
- **PATCH**: Bug fixes (backward-compatible)

**Examples**:
- `0.1.0` - Initial MVP
- `0.2.0` - Added Blogger agent
- `0.2.1` - Fixed token tracking bug
- `1.0.0` - First stable release
