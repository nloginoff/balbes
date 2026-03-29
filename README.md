# Balbes Multi-Agent System

Продакшн-готовая мульти-агентная AI-система с Telegram-ботом, долгосрочной памятью, делегированием задач между агентами и автономным выполнением кода.

**Версия**: 0.3.0 | **Статус**: 🟢 Production Ready | **Лицензия**: MIT

---

## Что умеет система

- **Telegram-бот** — управление через команды и меню; каждый чат имеет свою историю, модель и агента
- **Мульти-агентная оркестрация** — Оркестратор делегирует задачи агенту Coder в фон; получает и показывает результаты автоматически
- **Голосовые сообщения** — транскрибация через `faster-whisper` + исправление через LLM
- **Инструменты агента** — поиск в интернете (DuckDuckGo/Brave/Tavily), загрузка URL, выполнение команд на сервере (по вайтлисту), чтение/запись файлов
- **Heartbeat** — проактивные сообщения на основе `HEARTBEAT.md` и `MEMORY.md`, каждые 5 минут на бесплатной модели
- **Долгосрочная память** — семантическое хранилище в Qdrant (по запросу)
- **Быстрая память** — Redis: история чата 7 дней, авто-удаление неактивных чатов
- **Версионирование памяти агентов** — приватный GitHub-репо для `data/agents/`, авто-коммит + авто-пуш при каждой записи
- **Дебаг-трейс** — `/debug` показывает каждый LLM-вызов и вызов инструмента в чат (HTML)
- **Режимы выполнения** — `/mode ask` (безопасный вайтлист) / `/mode agent` (полный dev-вайтлист)
- **Контроль доступа** — только авторизованные `TELEGRAM_USER_ID`

---

## Быстрый старт

### Разработка (dev)

```bash
cd /home/balbes/projects/dev

# Первый запуск
source .venv/bin/activate
pip install -r services/orchestrator/requirements.txt

# Инфраструктура (Redis, Qdrant, RabbitMQ, PostgreSQL)
docker-compose -f docker-compose.dev.yml up -d

# Запуск сервисов
./scripts/start_dev.sh
```

### Продакшн

```bash
# На сервере (папка ~/projects/balbes)
git pull
bash scripts/restart_prod.sh

# Проверка здоровья
bash scripts/healthcheck.sh prod
```

Логи продакшна:
```bash
tail -f ~/projects/balbes/logs/prod/orchestrator.log
tail -f ~/projects/balbes/logs/prod/telegram_bot.log
```

---

## Структура проекта

```
dev/
├── config/
│   └── providers.yaml          # Модели, агенты, heartbeat, skills, whisper
│
├── data/
│   ├── agents/                 # Workspace каждого агента (отдельный git-репо)
│   │   ├── orchestrator/
│   │   │   ├── SOUL.md         # Характер агента
│   │   │   ├── AGENTS.md       # Инструкции по поведению
│   │   │   ├── MEMORY.md       # Постоянная важная память
│   │   │   ├── HEARTBEAT.md    # Список для проактивных сообщений
│   │   │   ├── TOOLS.md        # Документация по инструментам
│   │   │   ├── IDENTITY.md     # Личность и стиль
│   │   │   └── config.yaml     # Переопределение модели/лимитов (высший приоритет)
│   │   └── coder/
│   │       └── ...
│   └── logs/
│       └── agent_activity/     # JSONL-логи активности агентов (по датам)
│
├── services/
│   ├── orchestrator/           # Главный агент + Telegram-бот (порт 18102)
│   │   ├── agent.py            # OrchestratorAgent, делегирование, XML parsing
│   │   ├── telegram_bot.py     # Команды, мониторинг фоновых задач
│   │   ├── tools.py            # ToolDispatcher, схемы инструментов
│   │   └── api/tasks.py        # FastAPI: /api/v1/tasks, /api/v1/tasks/bg/events
│   ├── skills-registry/        # Реестр скиллов (порт 18101)
│   ├── coder/                  # Агент-кодер (порт 18103)
│   ├── memory-service/         # Память / история (порт 18100)
│   └── web-backend/            # API-шлюз (порт 18200)
│
├── scripts/
│   ├── start_prod.sh           # Запуск продакшна (uvicorn --workers 1)
│   ├── restart_prod.sh         # Перезапуск с проверкой здоровья
│   ├── healthcheck.sh          # Проверка всех 10 компонентов
│   └── setup_memory_repo.sh    # Инициализация приватного Git-репо для data/agents/
│
└── docker-compose.prod.yml     # PostgreSQL, Redis, Qdrant, RabbitMQ
```

---

## Telegram-команды

| Команда | Описание |
|---------|----------|
| `/start` | Начать работу |
| `/help` | Справка |
| `/agents` | Список агентов / переключить агента |
| `/chats` | Список чатов / переключить чат (показывает ID, агент, модель) |
| `/newchat` | Создать новый чат |
| `/rename` | Переименовать текущий чат |
| `/model` | Выбрать модель для чата (по тирам: free/cheap/medium/premium) |
| `/clear` | Очистить историю чата |
| `/remember` | Сохранить в долгосрочную память (Qdrant) |
| `/recall` | Найти в долгосрочной памяти |
| `/heartbeat` | Запустить проверку heartbeat немедленно |
| `/debug` | Включить/выключить трейс действий агента в чат |
| `/mode` | Переключить режим: `ask` (безопасный) / `agent` (разработка) |
| `/tasks` | Реестр задач: текущие и завершённые |
| `/stop` | Остановить текущее действие агента |
| `/status` | Статус системы |

---

## Инструменты агента

| Инструмент | Режим | Описание |
|-----------|-------|----------|
| `web_search` | ask + agent | Поиск (DuckDuckGo / Brave / Tavily) |
| `fetch_url` | ask + agent | Загрузить страницу и вернуть текст |
| `execute_command` | ask + agent | Команда из вайтлиста (ask — информационный, agent — dev) |
| `workspace_read` | ask + agent | Читать файл из workspace агента |
| `workspace_write` | ask + agent | Писать файл в workspace (авто-коммит в git) |
| `rename_chat` | ask + agent | Переименовать текущий чат |
| `save_to_memory` | ask + agent | Сохранить в Qdrant (семантическая память) |
| `read_agent_logs` | ask + agent | Прочитать JSONL-логи активности за период |
| `delegate_to_agent` | agent | Делегировать задачу агенту (foreground / background) |
| `get_agent_result` | agent | Получить результат завершённой фоновой задачи |
| `cancel_agent_task` | agent | Отменить фоновую задачу |
| `list_agent_tasks` | ask + agent | Показать реестр задач |

---

## Архитектура

```
┌───────────────────────────────────────────┐
│            Telegram Bot                   │
│  polling · команды · per-user lock        │
│  /debug trace · bg monitor loop           │
└──────────────────┬────────────────────────┘
                   │ HTTP
┌──────────────────▼────────────────────────┐
│         Orchestrator (FastAPI)             │
│  OrchestratorAgent                        │
│  ├── _run_llm_with_tools (loop)           │
│  ├── ToolDispatcher                       │
│  ├── AgentWorkspace (MD files + git)      │
│  ├── _task_registry (in-memory)           │
│  ├── _bg_debug_buffer (streaming)         │
│  └── delegate_to_agent → Coder            │
└───────┬──────────────────────────┬────────┘
        │                          │
┌───────▼──────┐        ┌──────────▼──────┐
│  Redis       │        │  Qdrant          │
│  Chat history│        │  Long-term memory│
│  Sessions    │        │  Embeddings      │
│  Debug flags │        └─────────────────┘
└──────────────┘
```

### Делегирование задач

```
Пользователь → Оркестратор → delegate_to_agent(coder, background=true)
                                      │
                               Coder Agent (собственная модель, вайтлист)
                                      │  каждые 5 сек
                               bg_monitor_loop ← poll /api/v1/tasks/bg/events
                                      │
                               Telegram: дебаг-трейс (live) + финальный результат
```

---

## Конфигурация LLM (providers.yaml)

### Тиры моделей

| Тир | Использование | Примеры |
|-----|--------------|---------|
| `free` | Дефолт, heartbeat, первый fallback | StepFun Step 3.5 Flash, MiniMax M2.5:free |
| `cheap` | Автоматический fallback | Llama 3.1 8B, Llama 3.3 70B, MiniMax M2.5 |
| `medium` | Только явный выбор | Kimi K2.5, Gemini 3 Flash |
| `premium` | Только явный выбор | Claude Sonnet 4.6, GLM-5 Turbo, GPT-5.4 |

### Настройки агентов

Каждый агент в `providers.yaml` и `data/agents/{agent}/config.yaml` может переопределить:
- `default_model` — модель по умолчанию для делегированных задач
- `fallback_enabled` — false по умолчанию (ошибка показывается пользователю)
- `fallback_chain` — цепочка при `fallback_enabled: true`
- `token_limits` — дневной/часовой лимит токенов
- `server_commands_ask` / `server_commands` — вайтлист команд по режиму

---

## Технологический стек

**Backend**: Python 3.13, FastAPI, uvicorn (workers=1)
**LLM**: OpenRouter API (OpenAI-совместимый формат), multi-model
**Telegram**: python-telegram-bot v22+
**Память быстрая**: Redis (история, сессии, флаги)
**Память долгосрочная**: Qdrant (семантический поиск)
**База данных**: PostgreSQL
**Транскрипция**: faster-whisper + ffmpeg
**Инфраструктура**: Docker Compose, bash-скрипты
**Git**: pre-commit (ruff format/check), автокоммит workspace

---

## Переменные окружения (.env.prod)

```bash
OPENROUTER_API_KEY=sk-or-v1-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_USER_ID=125996595          # Разрешённые user ID через запятую
WEB_AUTH_TOKEN=...
JWT_SECRET=...
POSTGRES_PASSWORD=...
REDIS_PASSWORD=
BRAVE_SEARCH_KEY=                   # Опционально
TAVILY_API_KEY=                     # Опционально
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
```

---

## Документация

- **[CHANGELOG.md](CHANGELOG.md)** — история версий
- **[docs/AGENTS_GUIDE.md](docs/AGENTS_GUIDE.md)** — руководство по агентам
- **[docs/CONFIGURATION.md](docs/CONFIGURATION.md)** — полная конфигурация
- **[docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md)** — архитектурные решения
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — деплой в продакшн
- **[TODO.md](TODO.md)** — план развития

---

## Деплой: dev → prod

```bash
# На dev-машине
cd /home/balbes/projects/dev
git add . && git commit -m "..." && git push

# На prod-сервере (папка ~/projects/balbes)
git pull && bash scripts/restart_prod.sh
```
