# Balbes Multi-Agent System — Roadmap

## v1.0 (текущая итерация — реализовано)

### Telegram Bot
- [x] Мультичат: создание, переключение, переименование (/chats, /newchat, /rename)
- [x] Выбор модели для каждого чата (/model + Inline keyboard)
- [x] Голосовые сообщения: транскрибация Whisper + коррекция через LLM
- [x] Долгосрочная память: /remember, /recall (Qdrant)
- [x] Защита от race condition: per-chat async locks
- [x] Уведомление при недоступности модели с предложением переключиться

### Agent
- [x] Workspace: системный промпт из MD-файлов (AGENTS.md, SOUL.md, USER.md, TOOLS.md, MEMORY.md, IDENTITY.md)
- [x] Агент может читать и писать свои workspace-файлы через tool calls
- [x] Мультичат: история per-chat, модель per-chat
- [x] Адаптивная обрезка истории под контекстное окно модели
- [x] Tool calls: web_search, fetch_url, execute_command, workspace_read/write, rename_chat, save_to_memory
- [x] Fallback цепочка моделей при 429/5xx

### Skills
- [x] web_search: DuckDuckGo (free), Brave, Tavily (disabled, готовы к включению)
- [x] fetch_url: чтение веб-страницы как текст (curl-аналог)
- [x] server_commands: выполнение команд сервера (whitelist mode)
- [x] whisper_transcribe: faster-whisper + коррекция LLM

### Memory (Redis)
- [x] Sorted Set история чатов с TTL 7 дней
- [x] Lazy cleanup мёртвых чатов
- [x] Модель привязана к метаданным чата
- [x] Автоудаление неактивных чатов через Redis TTL


## v1.x (ближайшие улучшения)

- [ ] Webhook вместо polling для Telegram в production
      (`TODO: настроить nginx + certbot, заменить run_polling() на webhook`)
- [ ] `.env.example` обновить: добавить BRAVE_SEARCH_KEY, TAVILY_API_KEY,
      WHISPER_MODEL, WHISPER_LANGUAGE
- [ ] Тесты для новых Redis методов (chat CRUD)
- [ ] Тесты для skills (mock httpx)
- [ ] Оптимизация: переиспользование загруженного providers.yaml (file watcher)


## v2.x (средний горизонт)

- [ ] Семантическое кеширование ответов LLM через Redis Stack
      (экономия 30-40% токенов на повторяющихся запросах)
- [ ] TTS — синтез голосовых ответов агента (edge-tts или OpenAI TTS)
- [ ] Фоновые агенты: задачи по расписанию с автоматическим fallback моделей
      без уведомления пользователя
- [ ] Отдельные Telegram-боты для других пользователей с ограниченным доступом
      (ALLOWED_USER_IDS в конфиге)


## v3.x (долгий горизонт)

- [ ] Multi-tenant: изолированные Qdrant collections на пользователя
- [ ] Docker-изоляция для execute_command (gVisor / rootless Docker)
- [ ] Суммаризация длинных чатов вместо обрезки (LLM-based)
- [ ] Агент-планировщик: декомпозиция сложных задач на подзадачи
- [ ] Интеграция с Calendar / Todoist для напоминаний
