# TODO / бэклог

## Референс-фото + промпт → дорисовка / вариации (логотип, пример)

**Статус:** не реализовано (идеи на будущее). Краткое название: *User reference images*.

**Цель:** пользователь загружает изображения (скетч, фото, логотип компании, style reference), затем в диалоге даёт текстовый промпт (дорисовать, сменить фон, «в стиле этого лого», вариации, mockup). Нужен пайплайн: референс(ы) + текст → модель (img2img / image+text-to-image, по возможностям OpenRouter), ответ в чате как вложение, как у `generate_image`.

### Checklist (при реализации)

- [ ] Проверить OpenRouter / allowlist: какие image-модели принимают входное изображение (img2img / multimodal gen) и формат `messages`.
- [ ] Спека: `generate_image` + refs или отдельный tool; поля, лимиты, TTL в Memory.
- [ ] UX в Telegram: референс = последнее фото / команда / reply-to; прокидывание в `task` + `attachments`.
- [ ] Прокинуть ref (`image` ids / base64) в `tool_context` и `_do_generate_image` (или новый путь).
- [ ] Документация в AGENTS_GUIDE: когда вызывать инструмент; не обещать картинку без реального API.

### Уже есть в проекте

- **Vision:** изображения в `attachments` на задаче, `vision_models` в [`config/providers.yaml`](../../config/providers.yaml), оркестратор в [`services/orchestrator/agent.py`](../../services/orchestrator/agent.py).
- **`generate_image`:** текст → PNG, [`shared/image_generation.py`](../../shared/image_generation.py), [`shared/agent_tools/registry.py`](../../shared/agent_tools/registry.py), `/imagemodel` в боте.

**Пока нет:** передача входного изображения в генератор как conditioning; отдельный UX «референс к следующему запросу».

### Возможные направления

1. Расширить `generate_image`: `prompt` + опционально `image_ref` (URL / base64 / id вложения / Redis), сборка `messages` по докам выбранной модели.
2. Сессия «референс»: флаг/команда «запомнить последнее фото N минут»; Redis по `user_id`.
3. Несколько референсов: список id в `tool_context` или в теле `POST /api/v1/tasks`.

### Нефункциональные требования

- Лимиты: размер файла, число референсов, TTL.
- Конфиденциальность: где храним байты.
- AGENTS: явные правила вызова инструмента.

### Код для ориентира

- [`shared/image_generation.py`](../../shared/image_generation.py)
- [`shared/agent_tools/registry.py`](../../shared/agent_tools/registry.py)
- [`shared/telegram_app/balbes_bot.py`](../../shared/telegram_app/balbes_bot.py)
- [`services/orchestrator/api/tasks.py`](../../services/orchestrator/api/tasks.py) — `attachments`, `image_generation_model_id`

### Критерий готовности

1. Картинка, загруженная пользователем, доступна следующему (или N-му) шагу с промптом.
2. Модель получает и текст, и пиксели (в рамках API).
3. Результат в чате как фото, с токен-учётом и allowlist как у `generate_image`.

---

*Перенесено из плана Cursor: `user_reference_images_todo_33038281`.*
