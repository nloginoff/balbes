# TODO

## В работе

*(пусто — задачи из backlog переходят сюда при начале работы)*

## Запланировано

*(пусто — всё из первоначального backlog выполнено)*

## Идеи / Backlog

- **Blogger: CRM интеграция** — читать сделки, воронку, статистику из CRM для бизнес-саммари
- **Blogger: анализ звонков** — Whisper → расшифровка звонков с клиентами → саммари → пост в блог
- **Blogger: авто-индексация Cursor** — re-index cursor_chats при добавлении нового файла (fsnotify)
- **Blogger: авто-публикация** — включить `auto_publish: true` для RU/EN каналов после тестирования
- **RabbitMQ интеграция** — использовать RabbitMQ для асинхронной передачи задач между агентами (сейчас in-process callbacks)
- **Веб-интерфейс для агентов** — дашборд с историей задач, токенами, логами (частично реализован в web-backend)
- **Multi-user support** — сейчас один пользователь, но архитектура готова к расширению
- **Голосовой ответ** — TTS для голосовых сообщений (в ответ на голос — голос)
- **Agent marketplace** — регистрировать новых агентов через skills-registry без перезапуска
- **Code review agent** — специализированный агент для code review PR
- **Автоматический деплой** — агент-деплойер: git pull + docker compose up при новых коммитах
- **Токен-бюджет в ответе** — показывать `_Токены: N | model_` в конце ответа в debug mode
- **Автоиндексация кода по git hook** — re-index при `git push` через post-receive hook
- **Инструмент `diff_files`** — показывать diff между двумя файлами без execute_command

---

## Выполнено (архив)

- ✅ `file_patch` инструмент для точечных правок файлов
- ✅ Persist task registry в Redis (восстановление после перезапуска)
- ✅ Streaming progress в Telegram (без debug mode)
- ✅ Фикс `AttributeError: 'NoneType'.strip()` в нескольких местах
- ✅ MAX_TOOL_CALL_ROUNDS увеличен с 5 до 15
- ✅ `file_read` и `file_write` задокументированы в TOOLS.md кодера
- ✅ Heartbeat/error сообщения сохраняются в историю чата
- ✅ Сплиттер длинных сообщений `_split_message` — лимит 4096 символов Telegram
- ✅ `/stop` всегда отправляет cancel-сигнал агентам (foreground + background)
- ✅ `recall_from_memory(query, limit)` доступен агентам через AVAILABLE_TOOLS
- ✅ LLM timeout настраивается через `providers.yaml → openrouter.timeout` (поднят до 120с)
- ✅ ReadTimeout graceful degradation в Telegram (⏳ вместо падения)
- ✅ Rate limiting на вызовы инструментов — `ToolDispatcher._call_counts`, `reset_call_counts()`
- ✅ Учёт токенов из LLM-ответов — fire-and-forget запись через `/api/v1/tokens/record`
- ✅ `code_search(query)` + `index_codebase()` — файловая индексация в Qdrant `code_index`
- ✅ `_maybe_summarize_history()` — LLM суммаризация при переполнении контекста (`history_strategy: summarize`)
- ✅ `manage_todo(action, section, item)` — агенты могут читать и обновлять TODO.md
- ✅ **Blogger agent service** — `services/blogger/`: агент-блогер, бизнес-бот (тихий наблюдатель + DM check-in), очередь постов, approval flow через inline-кнопки, вечерний check-in 20:00, бизнес-саммари, публикация в 3 Telegram-канала (RU/EN/personal)
