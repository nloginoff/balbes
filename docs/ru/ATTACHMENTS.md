# Вложения и vision

## Конфигурация

В [`config/providers.yaml`](../../config/providers.yaml) секция **`vision_models`**: `default_tier`, **`timeout_seconds`** (HTTP-таймаут запроса к OpenRouter для мультимодальных вызовов; по умолчанию в коде 300 с, в YAML обычно 300), и список **`tiers`** (`cheap` / `medium` / `premium`) с полями `id` (OpenRouter), `display_name`.

При ответе OpenRouter **504** / **5xx** оркестратор **последовательно пробует остальные модели из `tiers`** (порядок как в YAML): сначала выбранный tier пользователя, затем следующие — без отдельной настройки `fallback_chain`.

## Глобальный tier пользователя

Хранится в Memory Service (Redis `vision_tier:{canonical_user_id}`), API:

- `GET /api/v1/users/{user_id}/vision-tier`
- `PUT /api/v1/users/{user_id}/vision-tier` с телом `{"tier": "cheap"}`

В Telegram: команда **`/vision`** и inline-кнопки (флаг манифеста `telegram.vision_command`).

## Оркестратор: `POST /api/v1/tasks`

Запрос только в формате **JSON** (`Content-Type: application/json`).

Дополнительные поля:

| Поле | Описание |
|------|----------|
| `attachments` | Массив вложений (см. ниже) |
| `vision_tier` | Один раз для запроса: `cheap` \| `medium` \| `premium`; если не задан — из Memory, иначе `default_tier` из YAML |

### Элементы `attachments`

- **`{"kind": "image", "data_url": "data:image/jpeg;base64,..."}`** — или поля `mime_type` + `base64` вместо `data_url`.
- **`{"kind": "file_text", "filename": "x.txt", "text": "..."}`** — уже извлечённый текст (PDF/DOCX/XLSX/текст обрабатываются на стороне клиента, например Telegram-бота).

Пайплайн: при наличии изображений выполняется один вызов **vision-модели** (без инструментов), затем основной агент с инструментами получает расширенный `description`. Токены vision суммируются в `token_usage` ответа.

Если стабильно приходят **504** или **The operation was aborted**, уменьшите размер изображения (бот режет по `max_side` в [`shared/user_media.py`](../../shared/user_media.py)), увеличьте **`vision_models.timeout_seconds`**, или переключите tier через **`/vision`** (другая модель в цепочке).

## Telegram

- Фото и документы (при включённом `vision_command`) уходят в оркестратор с `attachments`.
- Текст без вложений — как раньше, без `attachments`.
- **Документы (текст):** извлечение в [`shared/document_extract.py`](../../shared/document_extract.py). PDF/DOCX/XLSX/XLS — по формату; **остальные** файлы (в т.ч. с неизвестным расширением или без него) сначала проверяются **по содержимому** (UTF-8/UTF-16/кириллические кодировки, эвристика «печатных» символов). Так в контекст попадают исходники `.py`, `.pl`, конфиги и произвольный текст без расширения — без постоянного расширения белого списка расширений.

## Голос (Whisper)

Локальный путь использует **ffmpeg**. Если в логах не «ffmpeg not found», а `FileNotFoundError` с другим путём — это не отсутствие ffmpeg, а другая проблема (кэш модели Whisper и т.д.); см. [`services/orchestrator/skills/whisper_transcribe.py`](../../services/orchestrator/skills/whisper_transcribe.py).
