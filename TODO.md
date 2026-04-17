# TODO

## В работе

*(пусто — задачи из backlog переходят сюда при начале работы)*

## Запланировано

### Следующие этапы (multi-messenger / webhooks)

- **Единый логический чат и каналы Telegram + MAX** — привязка `logical_chat` к `telegram_chat_id` / `max_chat_id`, fan-out исходящих сообщений агента и системных notify по настройкам агента/чата (не только переменные `NOTIFY_*` в `.env`).
- **MAX Messenger — расширение** — сценарий блогера: чтение summary рабочих чатов через MAX API; общий адаптер исходящих для всех агентов (сейчас: оркестратор через webhook + notify в [`shared/max_api.py`](shared/max_api.py)).
- **Telegram webhook для остальных ботов** — блогер и др.: при необходимости тот же паттерн, что [`services/webhooks_gateway`](services/webhooks_gateway) для оркестратора (`TELEGRAM_BOT_MODE=webhook`).

## Идеи / Backlog

- **Унифицированный обработчик Telegram для всех агентов** — вынести общую логику (голос, сплит длинных сообщений, команды, маршрутизация) в отдельный класс/модуль, чтобы при добавлении нового агента не дублировать код. У каждого агента — конфигурация «какие возможности Telegram включены» (голос, inline-кнопки, зеркалирование и т.д.).
- **Telegram для всех агентов на Webhook** — перевести приём обновлений с long polling на webhook там, где сейчас используется бот (оркестратор, блогер и др.), с единым подходом к URL, секрету и деплою за reverse proxy.

- **Prod: инструменты «показать / править файлы» и рассинхрон с repo + dev** — на проде агент работает с файлами в prod-каталоге; правки и превью там **не появляются** ни в git, ни в dev-окружении. **Рекомендуемая политика:** всё, что должно пережить деплой и быть единым источником правды, — **писать в репозиторий** (авто или явный шаг: `git commit` + `push`, по аналогии с debounced push для `workspace_write`). Черновики и одноразовые эксперименты — **целевой dev-workspace** (или отдельная ветка/PR), без «тихих» правок только на диске прода. Реализовать в коде инструментов единое поведение: флаг окружения, явное предупреждение в ответе агента или маршрутизация записи в dev/repo.

- **Blogger: CRM интеграция** — читать сделки, воронку, статистику из CRM для бизнес-саммари
- **Blogger: анализ звонков** — Whisper → расшифровка звонков с клиентами → саммари → пост в блог
- **Blogger: авто-индексация Cursor** — re-index cursor_chats при добавлении нового файла (fsnotify)
- **Blogger: авто-публикация** — включить `auto_publish: true` для RU/EN каналов после тестирования
- **RabbitMQ интеграция** — использовать RabbitMQ для асинхронной передачи задач между агентами (сейчас in-process callbacks)
- **Веб-интерфейс для агентов** — дашборд с историей задач, токенами, логами (частично реализован в web-backend)
- **Multi-user support** — сейчас один пользователь, но архитектура готова к расширению
- **Голосовой ответ** — TTS для голосовых сообщений (в ответ на голос — голос)
- **Голосовые в Telegram: прогресс и UX** — опциональное первое сообщение в чате «Распознаю голосовое…» (при желании удалять/редактировать после готовности); для очень длинных дорожек — нарезка или поблочная транскрипция Whisper с отображением прогресса; sanity-check, что на одном токене не запущено два long polling
- **Agent marketplace** — регистрировать новых агентов через skills-registry без перезапуска
- **Code review agent** — специализированный агент для code review PR
- **Автоматический деплой** — агент-деплойер: git pull + docker compose up при новых коммитах
- **Токен-бюджет в ответе** — показывать `_Токены: N | model_` в конце ответа в debug mode
- **Автоиндексация кода по git hook** — re-index при `git push` через post-receive hook
- **Инструмент `diff_files`** — показывать diff между двумя файлами без execute_command

---

## Выполнено (архив)

- ✅ **OpenRouter app attribution** — `HTTP-Referer`, `X-OpenRouter-Title` и опционально категории для chat/embeddings/STT (см. [`shared/openrouter_http.py`](shared/openrouter_http.py), `.env.example`).
- ✅ **MAX webhook → оркестратор** — `POST /webhook/max`, `message_created`, фоновый `POST {ORCHESTRATOR_URL}/api/v1/tasks`, ответ в чат через `platform-api.max.ru` (`MAX_BOT_TOKEN`, опционально `MAX_ALLOWED_USER_IDS`).
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
- ✅ **Blogger: скрипты запуска/остановки** — blogger (порт 18105) добавлен в `start_prod.sh`, `stop_prod.sh`, `healthcheck.sh`; исправлен конфликт портов с coder (18103)
- ✅ **Blogger: безопасность бизнес-бота** — `filters.User(owner_tg_id)` на уровне роутинга; незнакомцы получают полное молчание (`_handle_stranger`); добавлен `OWNER_TELEGRAM_ID` с инструкцией в `.env.example`
