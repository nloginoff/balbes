# Структура проекта

## Общая структура

```
balbes/
├── .env.example                    # Пример конфигурации окружения
├── .gitignore                      # Git ignore файл
├── .pre-commit-config.yaml         # Pre-commit hooks
├── .python-version                 # Версия Python для проекта
├── Makefile                        # Команды для dev/prod
├── README.md                       # Основная документация
├── pyproject.toml                  # Конфигурация Python проекта
│
├── docker-compose.infra.yml        # Docker для БД (development)
├── docker-compose.prod.yml         # Docker для всех сервисов (production)
├── nginx.conf                      # Nginx конфигурация для production
│
├── services/                       # Все микросервисы
│   ├── orchestrator/
│   ├── coder/
│   ├── memory-service/
│   ├── skills-registry/
│   └── web/
│
├── shared/                         # Общий код для всех сервисов
│   ├── base_agent.py
│   ├── llm_client.py
│   ├── message_bus.py
│   ├── models.py
│   └── skills/
│
├── config/                         # Конфигурационные файлы
│   ├── providers.yaml
│   ├── base_instructions.yaml
│   ├── agents/
│   └── skills/
│
├── data/                           # Данные (в .gitignore)
│   ├── logs/
│   ├── coder_output/
│   └── postgres/
│
├── scripts/                        # Утилиты и скрипты
│   ├── init_db.py
│   ├── seed_skills.py
│   └── create_agent.py
│
├── tests/                          # Тесты
│   ├── test_base_agent.py
│   ├── test_llm_client.py
│   └── integration/
│
└── docs/                           # Документация
    ├── TECHNICAL_SPEC.md
    ├── MVP_SCOPE.md
    ├── PROJECT_STRUCTURE.md (этот файл)
    ├── DATA_MODELS.md
    ├── API_SPECIFICATION.md
    ├── AGENTS_GUIDE.md
    ├── DEVELOPMENT_PLAN.md
    ├── DEPLOYMENT.md
    └── CONFIGURATION.md
```

---

## Детальная структура сервисов

### services/orchestrator/

```
orchestrator/
├── main.py                     # Entry point, запуск сервиса
├── agent.py                    # OrchestratorAgent класс
├── telegram_bot.py             # Telegram bot handlers
├── handlers/                   # Command handlers
│   ├── __init__.py
│   ├── status.py               # /status handler
│   ├── task.py                 # /task handler
│   ├── tokens.py               # /tokens handler
│   └── logs.py                 # /logs handler
├── requirements.txt            # Зависимости
├── Dockerfile                  # Для production
└── README.md                   # Документация сервиса
```

**Ответственность**:
- Прием команд от пользователя (Telegram)
- Создание задач для других агентов
- Мониторинг статуса агентов
- Отправка уведомлений пользователю
- Обработка запросов от Web UI

---

### services/coder/

```
coder/
├── main.py                     # Entry point
├── agent.py                    # CoderAgent класс
├── prompts/                    # Промпты для генерации кода
│   ├── create_skill.txt        # System prompt для создания скилла
│   └── fix_tests.txt           # Prompt для исправления тестов
├── templates/                  # Шаблоны для генерации
│   ├── skill_yaml.j2           # Jinja2 шаблон YAML
│   ├── skill_impl.j2           # Шаблон реализации
│   └── skill_test.j2           # Шаблон тестов
├── requirements.txt
├── Dockerfile
└── README.md
```

**Ответственность**:
- Создание новых Python скиллов по описанию
- Генерация кода + YAML + тесты
- Запуск pytest
- Retry при провале тестов (до 3 раз)
- Сохранение результата в `/data/coder_output/`

**Выходные данные**:
```
/data/coder_output/skills/
└── {skill_name}/
    ├── skill.yaml              # Описание скилла
    ├── implementation.py       # Код скилла
    ├── test_implementation.py  # Pytest тесты
    ├── README.md               # Документация
    └── requirements.txt        # Дополнительные зависимости (если нужны)
```

---

### services/memory-service/

```
memory-service/
├── main.py                     # FastAPI app
├── api/
│   ├── __init__.py
│   ├── routes.py               # API endpoints
│   ├── models.py               # Pydantic models для API
│   └── dependencies.py         # FastAPI dependencies
├── clients/
│   ├── __init__.py
│   ├── redis_client.py         # Redis wrapper
│   ├── qdrant_client.py        # Qdrant wrapper
│   └── postgres_client.py      # PostgreSQL wrapper
├── services/
│   ├── __init__.py
│   ├── context.py              # Context memory logic
│   ├── longterm.py             # Long-term memory logic
│   └── embeddings.py           # Embeddings generation
├── requirements.txt
├── Dockerfile
└── README.md
```

**API порт**: 8100

**Ответственность**:
- Управление быстрой памятью (Redis)
- Управление долговременной памятью (Qdrant)
- Хранение состояния агентов (PostgreSQL)
- Генерация embeddings для векторного поиска
- Предоставление API для агентов

---

### services/skills-registry/

```
skills-registry/
├── main.py                     # FastAPI app
├── registry.py                 # SkillRegistry класс
├── loader.py                   # Загрузка скиллов из YAML
├── validator.py                # Валидация скиллов
├── executor.py                 # Выполнение скиллов (опционально)
├── requirements.txt
├── Dockerfile
└── README.md
```

**API порт**: 8101

**Ответственность**:
- Загрузка базовых скиллов из `config/skills/`
- Регистрация новых скиллов (от Coder)
- Валидация скиллов (параметры, permissions)
- Предоставление информации о скиллах через API
- Hot reload скиллов (dev mode)

---

### services/web/

```
web/
├── backend/
│   ├── main.py                 # FastAPI app
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py             # Аутентификация
│   │   ├── agents.py           # /api/agents endpoints
│   │   ├── logs.py             # /api/logs endpoints
│   │   ├── tokens.py           # /api/tokens endpoints
│   │   └── chat.py             # /api/chat endpoints
│   ├── websocket.py            # WebSocket handler
│   ├── dependencies.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
│
└── frontend/
    ├── src/
    │   ├── main.tsx            # Entry point
    │   ├── App.tsx             # Root component
    │   ├── pages/
    │   │   ├── LoginPage.tsx
    │   │   ├── Dashboard.tsx
    │   │   ├── AgentDetail.tsx
    │   │   ├── Chat.tsx
    │   │   └── TokensPage.tsx
    │   ├── components/
    │   │   ├── AgentCard.tsx
    │   │   ├── LogViewer.tsx
    │   │   ├── ChatInterface.tsx
    │   │   ├── TokenChart.tsx
    │   │   ├── ThemeToggle.tsx
    │   │   └── ui/             # shadcn/ui components
    │   ├── hooks/
    │   │   ├── useWebSocket.ts
    │   │   ├── useAgents.ts
    │   │   ├── useAuth.ts
    │   │   └── useTheme.ts
    │   ├── store/
    │   │   ├── authStore.ts
    │   │   └── themeStore.ts
    │   ├── api/
    │   │   └── client.ts       # API client с TanStack Query
    │   ├── types/
    │   │   └── index.ts        # TypeScript types
    │   └── lib/
    │       └── utils.ts        # Утилиты
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── Dockerfile
    ├── nginx.conf              # Nginx для frontend в production
    └── README.md
```

**Backend порт**: 8200
**Frontend dev port**: 5173
**Frontend prod**: через Nginx

---

## shared/ - Общий код

```
shared/
├── __init__.py
├── base_agent.py               # BaseAgent класс
├── llm_client.py               # Multi-provider LLM client
├── message_bus.py              # RabbitMQ wrapper
├── models.py                   # Все Pydantic модели
├── utils.py                    # Общие утилиты
├── exceptions.py               # Кастомные исключения
│
└── skills/                     # Реализации базовых скиллов
    ├── __init__.py
    ├── search_web.py
    ├── file_operations.py      # read_file, write_file
    ├── execute.py              # execute_command
    ├── messaging.py            # send_message
    └── memory_ops.py           # query_memory
```

**Назначение**: Код, который используется несколькими сервисами. Импортируется как модуль.

**Важно**: При изменении кода в `shared/` нужно перезапускать все зависимые сервисы.

---

## config/ - Конфигурация

```
config/
├── providers.yaml              # LLM providers и модели
├── base_instructions.yaml      # Общие инструкции для агентов
│
├── agents/                     # Конфигурации агентов
│   ├── orchestrator.yaml       # Orchestrator config
│   └── coder.yaml              # Coder config
│
└── skills/                     # Описания базовых скиллов (YAML)
    ├── search_web.yaml
    ├── read_file.yaml
    ├── write_file.yaml
    ├── execute_command.yaml
    ├── send_message.yaml
    └── query_memory.yaml
```

**Формат**: YAML для читаемости и легкого редактирования

**Загрузка**: При старте сервисов, с возможностью hot reload в dev mode

---

## data/ - Данные (.gitignore)

```
data/
├── logs/                       # Логи сервисов (JSON lines)
│   ├── orchestrator.log
│   ├── coder.log
│   ├── memory-service.log
│   ├── skills-registry.log
│   └── web-backend.log
│
├── coder_output/               # Результаты работы Coder
│   └── skills/
│       ├── parse_hackernews/
│       └── ...
│
├── postgres/                   # PostgreSQL data (Docker volume)
├── redis/                      # Redis data (Docker volume)
├── rabbitmq/                   # RabbitMQ data (Docker volume)
└── qdrant/                     # Qdrant data (Docker volume)
```

**Важно**: Вся директория `data/` в `.gitignore` (кроме структуры директорий)

---

## scripts/ - Утилиты

```
scripts/
├── init_db.py                  # Инициализация PostgreSQL (создание таблиц)
├── seed_skills.py              # Загрузка базовых скиллов в registry
├── create_agent.py             # Скрипт для создания нового агента
├── backup_db.sh                # Backup PostgreSQL
└── cleanup_logs.py             # Очистка старых логов
```

**Использование**:
```bash
# При первом запуске
python scripts/init_db.py
python scripts/seed_skills.py

# При создании нового агента
python scripts/create_agent.py --name "researcher" --type "researcher"
```

---

## tests/ - Тесты

```
tests/
├── conftest.py                 # Pytest fixtures
│
├── unit/                       # Unit тесты
│   ├── test_base_agent.py
│   ├── test_llm_client.py
│   ├── test_message_bus.py
│   ├── test_models.py
│   └── test_skills/
│       ├── test_search_web.py
│       └── test_file_operations.py
│
├── integration/                # Integration тесты
│   ├── test_memory_service.py
│   ├── test_skills_registry.py
│   └── test_orchestrator_coder.py
│
└── e2e/                        # End-to-end тесты
    └── test_full_workflow.py   # Задача через Telegram → результат
```

---

## docs/ - Документация

```
docs/
├── TECHNICAL_SPEC.md           # Техническое задание (архитектура, концепция)
├── MVP_SCOPE.md                # Детальный scope MVP
├── PROJECT_STRUCTURE.md        # Этот файл
├── DATA_MODELS.md              # Pydantic модели, схемы БД
├── API_SPECIFICATION.md        # Все API endpoints
├── AGENTS_GUIDE.md             # Описание каждого агента
├── DEVELOPMENT_PLAN.md         # План разработки MVP
├── DEPLOYMENT.md               # Инструкции по деплою
├── CONFIGURATION.md            # Все конфиги и переменные окружения
└── ARCHITECTURE_DECISIONS.md   # Почему выбрали те или иные решения
```

---

## Соглашения по именованию

### Python
- **Модули/пакеты**: snake_case (`base_agent.py`, `memory_service/`)
- **Классы**: PascalCase (`BaseAgent`, `LLMClient`)
- **Функции/методы**: snake_case (`execute_skill`, `send_message`)
- **Константы**: UPPER_SNAKE_CASE (`MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Private**: префикс `_` (`_internal_method`)

### Files
- **Документация**: UPPER_SNAKE_CASE.md (`TECHNICAL_SPEC.md`)
- **Конфиги**: snake_case.yaml (`base_instructions.yaml`)
- **Скрипты**: snake_case.py (`init_db.py`)

### Docker
- **Сервисы**: kebab-case (`memory-service`, `skills-registry`)
- **Images**: `balbes/{service}:tag` (`balbes/orchestrator:latest`)

### API
- **Endpoints**: kebab-case (`/api/agents`, `/api/token-usage`)
- **Query params**: snake_case (`agent_id`, `limit`)
- **JSON keys**: snake_case (`agent_id`, `created_at`)

---

## Размеры и лимиты

### Файлы и директории
- Max log file size: 100MB (потом ротация)
- Max coder output per skill: 10MB
- Max skills in registry: 1000

### База данных
- PostgreSQL max connections: 100
- Redis max memory: 2GB
- Qdrant collection size: unlimited (зависит от диска)

### Retention policies
- Logs в PostgreSQL: 30 дней
- Log files: 7 дней (ротация)
- Context в Redis: 24 часа TTL
- Long-term memory в Qdrant: permanent (ручная очистка если нужно)

---

## Порты сервисов

### Development (localhost)
```
5432  - PostgreSQL
6379  - Redis
5672  - RabbitMQ (AMQP)
15672 - RabbitMQ Management UI
6333  - Qdrant HTTP
6334  - Qdrant gRPC

8000  - Orchestrator (HTTP API для внутреннего использования)
8001  - Coder (HTTP API)
8100  - Memory Service
8101  - Skills Registry
8200  - Web Backend (API + WebSocket)
5173  - Web Frontend (Vite dev server)
```

### Production (Docker network)
```
Внешние (через Nginx):
80    - HTTP
443   - HTTPS (если настроен SSL)

Внутренние (Docker network):
- Сервисы общаются по именам (memory-service:8100)
- БД недоступны снаружи
```

---

## Environment Variables

Переменные окружения определены в `.env` файле:

### Обязательные
```bash
# LLM Providers
OPENROUTER_API_KEY=sk-or-...
AITUNNEL_API_KEY=...

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_USER_ID=123456789

# Web UI Auth
WEB_AUTH_TOKEN=your-secret-token-here
```

### Опциональные (с defaults)
```bash
# Databases
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=balbes_agents
POSTGRES_USER=balbes
POSTGRES_PASSWORD=your_password

REDIS_HOST=localhost
REDIS_PORT=6379

QDRANT_HOST=localhost
QDRANT_PORT=6333

RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Logging
LOG_LEVEL=INFO
LOG_DIR=./data/logs

# Token limits (defaults)
DEFAULT_DAILY_TOKEN_LIMIT=100000
DEFAULT_HOURLY_TOKEN_LIMIT=15000
```

Подробнее см. [CONFIGURATION.md](CONFIGURATION.md)

---

## Git стратегия

### Ветки
```
main          - production-ready код
develop       - активная разработка MVP
feature/*     - фичи (feature/coder-agent)
bugfix/*      - исправления
docs/*        - документация
```

### .gitignore
```
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
.venv/
venv/
*.egg-info/
.pytest_cache/
.ruff_cache/

# Data
data/
!data/.gitkeep
*.log

# Environment
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Node (frontend)
node_modules/
dist/
build/

# Docker
*.pid
```

---

## Зависимости между сервисами

```
orchestrator
  ├── depends on: memory-service, skills-registry, rabbitmq
  └── используется: telegram-bot-api

coder
  ├── depends on: memory-service, skills-registry, rabbitmq
  └── создает: skills в /data/coder_output/

memory-service
  ├── depends on: postgres, redis, qdrant
  └── используется: всеми агентами

skills-registry
  ├── depends on: config/skills/
  └── используется: всеми агентами

web-backend
  ├── depends on: memory-service, rabbitmq
  └── предоставляет: API для frontend

web-frontend
  └── depends on: web-backend
```

**Порядок запуска**:
1. Инфраструктура (postgres, redis, rabbitmq, qdrant)
2. Memory Service
3. Skills Registry
4. Агенты (orchestrator, coder)
5. Web Backend
6. Web Frontend

---

## Volumes (Docker)

### Development
```yaml
volumes:
  # Code (для hot reload)
  - ./services/orchestrator:/app
  - ./shared:/app/shared

  # Data (persistence)
  - ./data/postgres:/var/lib/postgresql/data
  - ./data/redis:/data
  - ./data/rabbitmq:/var/lib/rabbitmq
  - ./data/qdrant:/qdrant/storage
```

### Production
```yaml
volumes:
  # Только data (код внутри образов)
  - ./data/postgres:/var/lib/postgresql/data
  - ./data/redis:/data
  - ./data/rabbitmq:/var/lib/rabbitmq
  - ./data/qdrant:/qdrant/storage
  - ./data/coder_output:/app/output
  - ./data/logs:/app/logs
```

---

## Полезные команды

См. `Makefile` для всех доступных команд:

```bash
# Development
make infra-up           # Поднять БД
make infra-down         # Остановить БД
make dev-orch           # Запустить Orchestrator
make dev-coder          # Запустить Coder
make dev-memory         # Запустить Memory Service
make dev-skills         # Запустить Skills Registry
make dev-web            # Запустить Web Backend

# Production
make prod-up            # Поднять все сервисы
make prod-down          # Остановить все
make prod-logs          # Показать логи
make prod-restart       # Перезапустить

# Database
make db-init            # Инициализировать БД
make db-backup          # Backup PostgreSQL
make db-restore         # Restore из backup

# Testing
make test               # Все тесты
make test-unit          # Unit тесты
make test-integration   # Integration тесты

# Cleanup
make clean              # Очистить временные файлы
make clean-logs         # Очистить старые логи
```

---

## Следующие шаги

1. Прочитать [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - общая концепция
2. Изучить [DATA_MODELS.md](DATA_MODELS.md) - структуры данных
3. Следовать [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) - план реализации
4. При деплое использовать [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Контакты и поддержка

Проект разрабатывается: balbes
Вопросы: через GitHub Issues (когда настроим)
