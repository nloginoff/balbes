# TODO

## В работе

*(пусто — задачи из backlog переходят сюда при начале работы)*

## Запланировано

### Задача 5: Семантический поиск по коду
**Приоритет:** Высокий
**Описание:** Индексировать кодовую базу по файлам в Qdrant (`code_index` collection).
Агент получает инструменты `code_search(query, limit)` и `index_codebase(path, force)`.
Обновление индекса — вручную через инструмент + автоматически по расписанию (каждые N минут).

**Файлы:**
- Новый `services/orchestrator/skills/code_indexer.py`
- `services/orchestrator/tools.py` — добавить `code_search`, `index_codebase`
- `config/providers.yaml` — добавить schedule для re-index

---

### Задача 6: Суммаризация истории через LLM
**Приоритет:** Высокий
**Описание:** Когда `build_messages_for_llm` обнаруживает, что история близка к лимиту контекста,
вместо тихого удаления старых сообщений — суммаризировать их через дешёвую LLM (llama-3.1-8b).
Суммаризация сохраняется в Redis и переиспользуется.

**Файлы:**
- `services/orchestrator/agent.py` — `build_messages_for_llm`, добавить `_summarize_history_chunk`
- `config/providers.yaml` — добавить `memory.history_strategy: "summarize"`

---

## Идеи / Backlog

- **RabbitMQ интеграция** — использовать RabbitMQ для асинхронной передачи задач между агентами (сейчас in-process callbacks)
- **Веб-интерфейс для агентов** — дашборд с историей задач, токенами, логами (частично реализован в web-backend)
- **Multi-user support** — сейчас один пользователь, но архитектура готова к расширению
- **Голосовой ответ** — TTS для голосовых сообщений (в ответ на голос — голос)
- **Scheduled tasks UI** — управление расписанием через Telegram команды (/schedule list/add/remove)
- **Agent marketplace** — регистрировать новых агентов через skills-registry без перезапуска
- **Code review agent** — специализированный агент для code review PR
- **Автоматический деплой** — агент-деплойер: git pull + docker compose up при новых коммитах
- **Алерты по метрикам** — мониторинг сервисов и отправка уведомлений при проблемах
- **Экспорт истории** — /export для выгрузки чата в markdown/json

---

## Выполнено (архив)

- ✅ `file_patch` инструмент для точечных правок файлов
- ✅ Persist task registry в Redis (восстановление после перезапуска)
- ✅ Streaming progress в Telegram (без debug mode)
- ✅ Фикс `AttributeError: 'NoneType'.strip()` в нескольких местах
- ✅ MAX_TOOL_CALL_ROUNDS увеличен с 5 до 15
- ✅ `file_read` и `file_write` задокументированы в TOOLS.md кодера
- ✅ Heartbeat/error сообщения сохраняются в историю чата (задача 1)
- ✅ Сплиттер длинных сообщений `_split_message` (задача 2)
- ✅ `/stop` всегда отправляет сигнал остановки агентам (задача 3)
- ✅ `recall_from_memory` доступен агентам (задача 8)
- ✅ LLM timeout настраивается через providers.yaml (задача 7)
- ✅ ReadTimeout graceful degradation в Telegram (задача 7)
- ✅ Rate limiting на вызовы инструментов в ToolDispatcher (задача 9)
- ✅ Учёт токенов из LLM-ответов, fire-and-forget запись в memory service (задача 10)
