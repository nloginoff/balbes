# Вложения и vision

## Конфигурация

В [`config/providers.yaml`](../../config/providers.yaml) секция **`vision_models`**: `default_tier` и список **`tiers`** (`cheap` / `medium` / `premium`) с полями `id` (OpenRouter), `display_name`.

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

## Telegram

- Фото и документы (при включённом `vision_command`) уходят в оркестратор с `attachments`.
- Текст без вложений — как раньше, без `attachments`.
