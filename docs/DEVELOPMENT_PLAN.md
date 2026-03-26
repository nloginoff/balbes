# План разработки MVP

## Общая оценка

**Примерное время**: 15-20 дней активной разработки
**Сложность**: Medium-High (архитектура с микросервисами)
**Риски**: Token costs, LLM API stability, RabbitMQ complexity

---

## Этап 1: Core Infrastructure (3-5 дней)

### Цель
Создать базовую инфраструктуру и общие компоненты для всех агентов.

### Задачи

#### 1.1 Project Setup (0.5 дня)
- [ ] Создать структуру директорий согласно PROJECT_STRUCTURE.md
- [ ] Настроить `pyproject.toml` с зависимостями
- [ ] Создать `.env.example` с описанием переменных
- [ ] Настроить `.gitignore`
- [ ] Создать `docker-compose.infra.yml`
- [ ] Создать `Makefile` с базовыми командами

**Проверка**:
```bash
make infra-up  # Должно поднять все БД
docker ps      # Все контейнеры running
```

#### 1.2 Pydantic Models (0.5 дня)
- [ ] Создать `shared/models.py`
- [ ] Реализовать все модели из DATA_MODELS.md:
  - AgentConfig, AgentState
  - Task, TaskResult
  - Message
  - MemoryRecord, MemorySearchResult
  - LogEntry, TokenUsage
  - LLMRequest, LLMResponse
  - SkillDefinition, SkillParameter
  - WSEvent
- [ ] Написать unit тесты для моделей

**Проверка**:
```bash
pytest tests/unit/test_models.py -v
```

#### 1.3 RabbitMQ Message Bus (1 день)
- [ ] Создать `shared/message_bus.py`
- [ ] Реализовать `MessageBus` класс:
  - `connect()` - подключение к RabbitMQ
  - `declare_exchanges()` - создание exchanges
  - `declare_queue()` - создание очереди для агента
  - `send_message()` - отправка сообщения
  - `receive_messages()` - получение (async generator)
  - `ack()`, `reject()` - acknowledgments
  - `close()` - graceful shutdown
- [ ] Написать integration тесты

**Проверка**:
```bash
pytest tests/integration/test_message_bus.py -v
# Должен создать exchange, queue, отправить/получить сообщение
```

#### 1.4 Multi-Provider LLM Client (1-2 дня)
- [ ] Создать `shared/llm_client.py`
- [ ] Реализовать `LLMClient` класс:
  - `complete()` - LLM completion с fallback
  - `_call_provider()` - вызов конкретного провайдера
  - `_estimate_cost()` - расчет стоимости
  - `_check_token_budget()` - проверка лимитов
  - `_switch_to_cheap_model()` - переключение модели
  - `_send_alert()` - отправка алертов
- [ ] Реализовать провайдеры:
  - `OpenRouterProvider`
  - `AiTunnelProvider`
- [ ] Создать `config/providers.yaml`
- [ ] Написать unit тесты (с mock API)

**Проверка**:
```bash
# Тест с реальным API (небольшой запрос)
python -c "
from shared.llm_client import LLMClient
client = LLMClient('config/providers.yaml')
response = await client.complete([{'role': 'user', 'content': 'Hi'}], 'test')
print(f'Response: {response.content}, Tokens: {response.total_tokens}')
"
```

#### 1.5 BaseAgent Class (1 день)
- [ ] Создать `shared/base_agent.py`
- [ ] Реализовать `BaseAgent` класс (см. AGENTS_GUIDE.md)
- [ ] Методы для работы с памятью
- [ ] Методы для выполнения скиллов
- [ ] Методы для коммуникации
- [ ] Методы для логирования
- [ ] Lifecycle methods (start, stop)
- [ ] Написать unit тесты

**Проверка**:
```bash
pytest tests/unit/test_base_agent.py -v
```

#### 1.6 PostgreSQL Schema (0.5 дня)
- [ ] Создать `scripts/init_db.py`
- [ ] SQL схема для всех таблиц (см. DATA_MODELS.md)
- [ ] Создание индексов
- [ ] Создание views
- [ ] Тестовый запуск

**Проверка**:
```bash
python scripts/init_db.py
psql -U balbes -d balbes_agents -c "\dt"  # Список таблиц
psql -U balbes -d balbes_agents -c "SELECT COUNT(*) FROM agents"
```

#### 1.7 Logging Setup (0.5 дня)
- [ ] Настроить структурированное логирование (JSON)
- [ ] Ротация логов
- [ ] Уровни логирования
- [ ] Общий формат для всех сервисов

### Критерии приемки Этапа 1

- ✅ Инфраструктура (PostgreSQL, Redis, RabbitMQ, Qdrant) работает
- ✅ Все Pydantic модели определены и протестированы
- ✅ MessageBus отправляет и получает сообщения
- ✅ LLMClient делает запросы к OpenRouter
- ✅ LLMClient fallback работает (можно протестировать с invalid key)
- ✅ BaseAgent класс реализован
- ✅ PostgreSQL схема создана
- ✅ Unit тесты проходят (>80% coverage базовых компонентов)

**Checkpoint**: После этого этапа можно создавать агентов на базе BaseAgent.

---

## Этап 2: Memory Service (2-3 дня)

### Цель
Реализовать сервис для работы с памятью агентов (быстрая, долговременная, состояние).

### Задачи

#### 2.1 FastAPI Application (0.5 дня)
- [ ] Создать `services/memory-service/main.py`
- [ ] Настроить FastAPI app
- [ ] Health check endpoint
- [ ] CORS middleware
- [ ] Error handlers
- [ ] Создать `requirements.txt`

#### 2.2 Redis Client (0.5 дня)
- [ ] Создать `services/memory-service/clients/redis_client.py`
- [ ] Реализовать методы:
  - `set_context()`, `get_context()`, `delete_context()`
  - `add_to_history()`, `get_history()`
  - `incr_token_budget()`, `get_token_budget()`
  - `set_alert_flag()`, `check_alert_flag()`
- [ ] Connection pool
- [ ] Написать unit тесты

#### 2.3 Qdrant Client (1 день)
- [ ] Создать `services/memory-service/clients/qdrant_client.py`
- [ ] Создать коллекцию `agent_memory`
- [ ] Реализовать embeddings generation (через OpenRouter)
- [ ] Реализовать методы:
  - `store_memory()` - сохранение с векторизацией
  - `search_memory()` - семантический поиск
  - `delete_memory()` - удаление (для будущего)
- [ ] Создать индексы для фильтрации
- [ ] Написать integration тесты

**Важно**: Кэшировать embeddings для одинаковых запросов (в Redis).

#### 2.4 PostgreSQL Client (0.5 дня)
- [ ] Создать `services/memory-service/clients/postgres_client.py`
- [ ] Реализовать CRUD для:
  - agents table
  - tasks table
  - action_logs table
  - token_usage table
- [ ] Connection pooling (asyncpg)
- [ ] Написать unit тесты

#### 2.5 API Routes (0.5 дня)
- [ ] Создать `services/memory-service/api/routes.py`
- [ ] Реализовать все endpoints из API_SPECIFICATION.md:
  - `/api/v1/context/*`
  - `/api/v1/history/*`
  - `/api/v1/memory/*`
  - `/api/v1/agents/*`
  - `/api/v1/tasks/*`
  - `/api/v1/logs/*`
  - `/api/v1/tokens/*`
- [ ] Валидация с Pydantic
- [ ] Error handling

#### 2.6 Integration Tests (0.5 дня)
- [ ] E2E тесты для Memory Service
- [ ] Тест full flow: store context → retrieve → expire
- [ ] Тест full flow: store memory → search → get results
- [ ] Тест token tracking

### Критерии приемки Этапа 2

- ✅ Memory Service запускается на порту 8100
- ✅ Health check возвращает 200
- ✅ Можно сохранить и получить context из Redis
- ✅ История сохраняется и возвращается корректно
- ✅ Можно сохранить в Qdrant и найти по семантическому запросу
- ✅ PostgreSQL операции работают
- ✅ OpenAPI docs доступны на /docs
- ✅ Integration тесты проходят

**Проверка**:
```bash
# Запуск сервиса
cd services/memory-service && uvicorn main:app --reload

# Тест API
curl http://localhost:8100/health
curl -X POST http://localhost:8100/api/v1/context/test \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": {"x": 1}, "ttl": 60}'

# Integration тесты
pytest tests/integration/test_memory_service.py -v
```

---

## Этап 3: Skills Registry (1-2 дня)

### Цель
Создать регистр скиллов и реализовать базовые скиллы.

### Задачи

#### 3.1 Skills Registry Service (0.5 дня)
- [ ] Создать `services/skills-registry/main.py`
- [ ] Создать `services/skills-registry/registry.py`
- [ ] Реализовать `SkillRegistry` класс:
  - `load_skills()` - загрузка из YAML
  - `register_skill()` - регистрация нового
  - `get_skill()` - получение по имени
  - `list_skills()` - список всех
  - `get_agent_skills()` - скиллы конкретного агента
- [ ] Динамическая загрузка Python модулей
- [ ] Валидация permissions

#### 3.2 Skills API (0.5 дня)
- [ ] Реализовать endpoints из API_SPECIFICATION.md:
  - `GET /api/v1/skills`
  - `GET /api/v1/skills/{name}`
  - `POST /api/v1/skills`
  - `GET /api/v1/agents/{id}/skills`
- [ ] OpenAPI documentation

#### 3.3 Basic Skills Implementation (1 день)
- [ ] `search_web` - поиск в интернете (использовать API, например SerpAPI или DuckDuckGo)
- [ ] `read_file` - чтение файла с валидацией пути
- [ ] `write_file` - запись файла с whitelist проверкой
- [ ] `execute_command` - выполнение с whitelist команд
- [ ] `send_message` - отправка через Message Bus
- [ ] `query_memory` - прокси к Memory Service

Для каждого скилла:
- [ ] Python implementation в `shared/skills/{skill}.py`
- [ ] YAML описание в `config/skills/{skill}.yaml`
- [ ] Pytest тесты

#### 3.4 Seed Script (0.5 дня)
- [ ] Создать `scripts/seed_skills.py`
- [ ] Загрузка базовых скиллов в registry при старте
- [ ] Проверка что все скиллы загрузились корректно

### Критерии приемки Этапа 3

- ✅ Skills Registry запускается на порту 8101
- ✅ Все 6 базовых скиллов загружены
- ✅ API возвращает список скиллов
- ✅ Можно зарегистрировать новый скилл
- ✅ Скиллы можно выполнить (функции работают)
- ✅ Валидация параметров работает
- ✅ Тесты всех скиллов проходят

**Проверка**:
```bash
# Запуск
cd services/skills-registry && uvicorn main:app --reload

# Тест API
curl http://localhost:8101/api/v1/skills
curl http://localhost:8101/api/v1/skills/search_web

# Seed скиллов
python scripts/seed_skills.py

# Тесты скиллов
pytest tests/unit/test_skills/ -v
```

---

## Этап 4: Orchestrator Agent (2-3 дня)

### Цель
Создать главного агента с Telegram ботом для управления системой.

### Задачи

#### 4.1 Orchestrator Agent Class (1 день)
- [ ] Создать `services/orchestrator/agent.py`
- [ ] Класс `OrchestratorAgent(BaseAgent)`
- [ ] Реализовать `execute_task()`:
  - Анализ запроса
  - Определение целевого агента
  - Создание задачи
  - Отправка через Message Bus
- [ ] Обработка ответов от агентов
- [ ] Логика coordination (если нужно)

#### 4.2 Telegram Bot (1 день)
- [ ] Создать `services/orchestrator/telegram_bot.py`
- [ ] Настроить `python-telegram-bot`
- [ ] Реализовать handlers для команд:
  - `/start` - приветствие
  - `/status` - статус агентов
  - `/task` - создание задачи
  - `/stop` - остановка задачи
  - `/model` - смена модели
  - `/tokens` - статистика
  - `/logs` - просмотр логов
  - `/help` - справка
- [ ] Проверка user_id (только владелец)
- [ ] Форматирование сообщений (markdown, эмодзи)
- [ ] Обработка ошибок

#### 4.3 Notification System (0.5 дня)
- [ ] Отправка уведомлений в Telegram:
  - Task completed
  - Task failed
  - Token alerts
  - Agent errors
  - Model fallback
- [ ] Форматированные сообщения

#### 4.4 Main Entry Point (0.5 дня)
- [ ] Создать `services/orchestrator/main.py`
- [ ] Запуск Orchestrator agent
- [ ] Запуск Telegram bot
- [ ] Graceful shutdown handler (SIGINT, SIGTERM)
- [ ] Создать Dockerfile

### Критерии приемки Этапа 4

- ✅ Orchestrator запускается и подключается к RabbitMQ
- ✅ Telegram бот отвечает на команды
- ✅ `/start` возвращает приветствие
- ✅ `/status` показывает список агентов (пока только orchestrator)
- ✅ `/task` создает задачу в PostgreSQL
- ✅ `/tokens` показывает статистику (пока только orchestrator)
- ✅ Все команды логируются
- ✅ User ID проверяется (чужой user не может пользоваться)

**Проверка**:
```bash
# Запуск (с реальным TELEGRAM_BOT_TOKEN)
cd services/orchestrator && python main.py

# В Telegram:
/start
/status
/tokens

# Проверка логов
tail -f data/logs/orchestrator.log
```

**Checkpoint**: После этого этапа можно управлять системой через Telegram.

---

## Этап 5: Coder Agent (2-3 дня)

### Цель
Создать агента для написания Python скиллов.

### Задачи

#### 5.1 Coder Agent Class (1 день)
- [ ] Создать `services/coder/agent.py`
- [ ] Класс `CoderAgent(BaseAgent)`
- [ ] Реализовать `execute_task()` - main workflow
- [ ] Методы:
  - `_analyze_requirements()` - анализ что нужно сделать
  - `_generate_skill()` - генерация кода скилла
  - `_generate_yaml()` - генерация YAML описания
  - `_generate_tests()` - генерация pytest тестов
  - `_run_tests()` - запуск pytest
  - `_fix_skill()` - исправление на основе ошибок тестов
  - `_save_skill_files()` - сохранение всех файлов

#### 5.2 Prompts и Templates (0.5 дня)
- [ ] Создать `services/coder/prompts/create_skill.txt`
- [ ] Создать `services/coder/prompts/fix_tests.txt`
- [ ] Создать Jinja2 templates (опционально):
  - `services/coder/templates/skill_yaml.j2`
  - `services/coder/templates/skill_test.j2`
  - `services/coder/templates/README.j2`

#### 5.3 Testing Logic (0.5 дня)
- [ ] Запуск pytest в subprocess
- [ ] Парсинг результатов (passed/failed)
- [ ] Извлечение ошибок для retry
- [ ] Timeout handling

#### 5.4 Main Entry Point (0.5 дня)
- [ ] Создать `services/coder/main.py`
- [ ] Запуск Coder agent
- [ ] Подписка на RabbitMQ очередь `coder.tasks`
- [ ] Graceful shutdown
- [ ] Dockerfile

#### 5.5 Integration (0.5 дня)
- [ ] Интеграция Orchestrator ↔ Coder
- [ ] Тест: задача через Orchestrator → Coder выполняет → результат обратно

### Критерии приемки Этапа 5

- ✅ Coder запускается и подключается к RabbitMQ
- ✅ Coder получает задачи из очереди
- ✅ Coder создает скилл (код + YAML + тесты)
- ✅ Coder запускает pytest
- ✅ Retry логика работает (можно протестировать с намеренно плохим кодом)
- ✅ Результат сохраняется в `/data/coder_output/`
- ✅ Уведомление отправляется Orchestrator
- ✅ Все действия логируются

**Проверка (End-to-End тест)**:
```bash
# 1. Запустить все сервисы
make infra-up
cd services/memory-service && python main.py &  # Terminal 1
cd services/skills-registry && python main.py & # Terminal 2
cd services/orchestrator && python main.py &    # Terminal 3
cd services/coder && python main.py &           # Terminal 4

# 2. В Telegram:
/task @coder создай скилл для парсинга HackerNews. Должен возвращать топ-10 постов с заголовками и ссылками. Используй requests и beautifulsoup4.

# 3. Ждем результат (~2 минуты)

# 4. Проверяем вывод:
ls -la data/coder_output/skills/parse_hackernews/
cat data/coder_output/skills/parse_hackernews/skill.yaml
cat data/coder_output/skills/parse_hackernews/README.md

# 5. Проверяем что тесты прошли:
grep "test_" data/logs/coder.log | grep "success"
```

**Checkpoint**: После этого этапа система функционально работает! Можно создавать скиллы через Telegram.

---

## Этап 6: Web UI Backend (1-2 дня)

### Цель
Создать API для веб-интерфейса с WebSocket поддержкой.

### Задачи

#### 6.1 FastAPI Application (0.5 дня)
- [ ] Создать `services/web/backend/main.py`
- [ ] Настроить FastAPI с CORS
- [ ] JWT authentication middleware
- [ ] Error handlers
- [ ] Dependencies injection

#### 6.2 Authentication (0.5 дня)
- [ ] Endpoint `/api/auth/login` (Bearer token → JWT)
- [ ] JWT generation и validation
- [ ] Dependency для защищенных endpoints

#### 6.3 API Routes (0.5 дня)
- [ ] `api/agents.py` - endpoints для агентов
- [ ] `api/logs.py` - endpoints для логов
- [ ] `api/tokens.py` - endpoints для токен-статистики
- [ ] `api/chat.py` - endpoints для чата
- [ ] Интеграция с Memory Service (proxy запросы)
- [ ] Интеграция с RabbitMQ (для отправки задач)

#### 6.4 WebSocket (1 день)
- [ ] Создать `services/web/backend/websocket.py`
- [ ] WebSocket endpoint `/ws`
- [ ] Connection manager (поддержка multiple connections)
- [ ] Authentication для WebSocket
- [ ] Подписка на события:
  - Изменения статуса агентов
  - Новые логи
  - Token alerts
  - Task events
- [ ] Broadcast events всем подключенным клиентам
- [ ] Heartbeat (ping/pong)

#### 6.5 Event Listener (0.5 дня)
- [ ] Подписка на RabbitMQ broadcast exchange
- [ ] Получение событий от агентов
- [ ] Преобразование в WSEvent
- [ ] Отправка через WebSocket
- [ ] Также проверка PostgreSQL на изменения (polling каждые 2s для backup)

### Критерии приемки Этапа 6

- ✅ Web Backend запускается на порту 8200
- ✅ `/api/auth/login` возвращает JWT
- ✅ Защищенные endpoints требуют Authorization header
- ✅ `/api/agents` возвращает список агентов
- ✅ `/api/logs` возвращает логи с фильтрацией
- ✅ `/api/tokens/stats` возвращает статистику
- ✅ WebSocket подключение работает
- ✅ WebSocket получает real-time события
- ✅ OpenAPI docs доступны

**Проверка**:
```bash
# Запуск
cd services/web/backend && uvicorn main:app --reload

# Тест authentication
curl -X POST http://localhost:8200/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"token": "your-secret-token"}'

# Получить JWT, затем:
TOKEN="eyJhbGc..."
curl http://localhost:8200/api/agents \
  -H "Authorization: Bearer $TOKEN"

# WebSocket (в браузере console):
const ws = new WebSocket('ws://localhost:8200/ws?token=' + TOKEN);
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

---

## Этап 7: Web UI Frontend (3-4 дня)

### Цель
Создать красивый и функциональный веб-интерфейс для мониторинга и управления.

### Задачи

#### 7.1 Project Setup (0.5 дня)
- [ ] Создать React app с Vite + TypeScript
- [ ] Установить зависимости:
  - React Router, Zustand, TanStack Query
  - shadcn/ui, Tailwind CSS
  - Recharts, sonner
- [ ] Настроить `vite.config.ts`
- [ ] Настроить `tailwind.config.js`
- [ ] Создать базовую структуру (см. PROJECT_STRUCTURE.md)

#### 7.2 shadcn/ui Setup (0.5 дня)
- [ ] Инициализировать shadcn/ui
- [ ] Добавить компоненты:
  - Button, Card, Badge, Input
  - Select, Tabs, Table
  - Dialog, Toast (sonner)
  - Switch (для theme toggle)
- [ ] Настроить темы (light/dark) в Tailwind config

#### 7.3 Core Components (0.5 дня)
- [ ] `src/api/client.ts` - API client с TanStack Query
- [ ] `src/hooks/useWebSocket.ts` - WebSocket hook
- [ ] `src/hooks/useAuth.ts` - Authentication hook
- [ ] `src/hooks/useTheme.ts` - Theme toggle hook
- [ ] `src/store/authStore.ts` - Zustand store для auth
- [ ] `src/store/themeStore.ts` - Zustand store для theme
- [ ] `src/types/index.ts` - TypeScript types

#### 7.4 Authentication (0.5 дня)
- [ ] `LoginPage.tsx` - страница логина
- [ ] Protected routes wrapper
- [ ] Token storage (localStorage)
- [ ] Auto-logout при 401

#### 7.5 Dashboard Page (1 день)
- [ ] `src/pages/Dashboard.tsx`
- [ ] Компоненты:
  - `AgentCard.tsx` - карточка агента (статус, токены, current task)
  - `RecentActivity.tsx` - лента последних событий
  - `TokensSummary.tsx` - общая статистика токенов
- [ ] Real-time updates через WebSocket
- [ ] Автообновление данных (polling каждые 10s как fallback)

#### 7.6 Agent Detail Page (0.5 дня)
- [ ] `src/pages/AgentDetail.tsx`
- [ ] Информация об агенте
- [ ] Список скиллов
- [ ] `LogViewer.tsx` - компонент для логов:
  - Фильтрация (action, status)
  - Пагинация
  - Auto-scroll при new logs
- [ ] Токен-статистика агента

#### 7.7 Chat Page (0.5 дня)
- [ ] `src/pages/Chat.tsx`
- [ ] `ChatInterface.tsx` component:
  - Выбор агента (dropdown)
  - История сообщений
  - Поле ввода
  - Отправка команд через API
- [ ] Сохранение истории чата (localStorage)

#### 7.8 Tokens Page (0.5 дня)
- [ ] `src/pages/TokensPage.tsx`
- [ ] `TokenChart.tsx` - график токенов:
  - Bar chart по часам
  - Recharts library
- [ ] Таблица по агентам
- [ ] Фильтр по периоду (today, yesterday, this week)

#### 7.9 Layout и Navigation (0.5 дня)
- [ ] Main layout с sidebar
- [ ] Navigation menu
- [ ] Header с user info и theme toggle
- [ ] Адаптивный дизайн (responsive)
- [ ] Loading states
- [ ] Error boundaries

#### 7.10 Polish и UX (0.5 дня)
- [ ] Toast notifications для событий
- [ ] Loading spinners
- [ ] Empty states (когда нет данных)
- [ ] Error messages
- [ ] Animations (subtle transitions)
- [ ] Accessibility (keyboard navigation)

### Критерии приемки Этапа 7

- ✅ Frontend собирается без ошибок
- ✅ Можно залогиниться с токеном
- ✅ Dashboard показывает агентов
- ✅ Real-time updates работают (WebSocket)
- ✅ Можно отправить задачу через Chat
- ✅ Логи отображаются с фильтрацией
- ✅ График токенов рисуется корректно
- ✅ Light/Dark theme переключаются
- ✅ UI адаптивный (работает на tablet)
- ✅ Нет console errors
- ✅ UI выглядит профессионально

**Проверка**:
```bash
# Development
cd services/web/frontend
npm install
npm run dev
# Открыть http://localhost:5173

# Production build
npm run build
npm run preview
```

**Manual testing checklist**:
- [ ] Login с корректным токеном работает
- [ ] Login с некорректным токеном отклоняется
- [ ] Dashboard показывает правильные данные
- [ ] WebSocket обновления появляются в real-time
- [ ] Можно переключить тему (light/dark)
- [ ] Можно отправить задачу через Chat
- [ ] Логи загружаются с пагинацией
- [ ] График токенов показывает данные
- [ ] На tablet UI выглядит нормально

---

## Этап 8: Integration & Testing (2-3 дня)

### Цель
Протестировать всю систему end-to-end, исправить баги, написать документацию.

### Задачи

#### 8.1 End-to-End Tests (1 день)

**Test 1: Full workflow через Telegram**
- [ ] Запустить все сервисы
- [ ] Отправить `/task @coder` через Telegram
- [ ] Проверить что Coder получил задачу
- [ ] Дождаться завершения
- [ ] Проверить результат в `/data/coder_output/`
- [ ] Проверить уведомление в Telegram
- [ ] Проверить логи в PostgreSQL

**Test 2: Full workflow через Web UI**
- [ ] Залогиниться в Web UI
- [ ] Отправить задачу через Chat
- [ ] Наблюдать real-time updates в Dashboard
- [ ] Проверить логи в Agent Detail
- [ ] Проверить статистику токенов

**Test 3: Fallback механизм**
- [ ] Временно использовать invalid API key для primary model
- [ ] Отправить задачу
- [ ] Проверить что fallback сработал
- [ ] Проверить уведомление в Telegram
- [ ] Проверить лог в PostgreSQL

**Test 4: Token limit**
- [ ] Временно установить очень низкий limit (например, 100 tokens)
- [ ] Отправить задачу
- [ ] Проверить что переключилось на cheap model
- [ ] Проверить alert в Telegram
- [ ] Восстановить normal limit

**Test 5: Параллельные задачи**
- [ ] Отправить 2-3 задачи подряд
- [ ] Проверить что они встали в очередь
- [ ] Проверить что выполняются по очереди (Coder может только одну за раз)

**Test 6: Error handling**
- [ ] Задача с невозможным требованием (чтобы тесты провалились 3 раза)
- [ ] Проверить retry логику
- [ ] Проверить error notification
- [ ] Проверить лог ошибки

#### 8.2 Bug Fixes (0.5-1 день)
- [ ] Собрать все найденные баги
- [ ] Приоритизировать (critical, major, minor)
- [ ] Исправить critical и major
- [ ] Minor записать в backlog для post-MVP

#### 8.3 Performance Testing (0.5 дня)
- [ ] Тест response time API endpoints
- [ ] Тест WebSocket latency
- [ ] Тест task processing time
- [ ] Проверка использования памяти сервисами
- [ ] Оптимизация если нужно

#### 8.4 Documentation (1 день)
- [ ] Убедиться что все документы актуальны
- [ ] Добавить примеры в каждый doc
- [ ] Создать архитектурные диаграммы (если нужно)
- [ ] Финальная вычитка всех docs
- [ ] Создать CHANGELOG.md

#### 8.5 Code Quality (0.5 дня)
- [ ] Ruff проверка всего кода
- [ ] Исправление линтер-ошибок
- [ ] Добавить docstrings где отсутствуют
- [ ] Проверить type hints coverage
- [ ] Pre-commit hooks финальная проверка

### Критерии приемки Этапа 8

- ✅ Все E2E тесты проходят
- ✅ Тест fallback работает
- ✅ Тест token limit работает
- ✅ Нет critical багов
- ✅ API response time < 200ms
- ✅ WebSocket latency < 100ms
- ✅ Документация актуальна и полна
- ✅ Ruff проверка проходит
- ✅ README.md с Quick Start инструкциями

**Final Test Scenario**:
```
Пользователь: /task @coder создай скилл для парсинга курса Bitcoin с coinmarketcap.com

Ожидаемый результат:
1. Telegram: "✅ Задача создана"
2. Web UI Dashboard: статус coder → "working"
3. Через ~2 минуты:
   - Telegram: "✅ @coder завершил задачу..."
   - Web UI: toast notification "Task completed"
   - файл создан в /data/coder_output/skills/parse_bitcoin_price/
   - тесты прошли
4. Статистика токенов обновилась везде
5. Все логи записались
```

**Checkpoint**: MVP полностью готов к деплою!

---

## Этап 9: Production Deployment (1-2 дня)

### Цель
Развернуть систему на VPS в production режиме.

### Задачи

#### 9.1 VPS Preparation (0.5 дня)
- [ ] Подключиться к VPS
- [ ] Установить Docker и Docker Compose
- [ ] Настроить firewall (открыть 80, 443, закрыть остальное)
- [ ] Создать пользователя для приложения (не root)
- [ ] Настроить SSH ключи

#### 9.2 Dockerfiles (1 день)
- [ ] Dockerfile для каждого сервиса:
  - `services/orchestrator/Dockerfile`
  - `services/coder/Dockerfile`
  - `services/memory-service/Dockerfile`
  - `services/skills-registry/Dockerfile`
  - `services/web/backend/Dockerfile`
  - `services/web/frontend/Dockerfile`
- [ ] Multi-stage builds для оптимизации размера
- [ ] Health checks в Dockerfile

#### 9.3 Docker Compose Production (0.5 дня)
- [ ] Создать `docker-compose.prod.yml` (см. DEPLOYMENT.md)
- [ ] Настроить networks
- [ ] Настроить volumes
- [ ] Настроить restart policies
- [ ] Настроить health checks
- [ ] Настроить resource limits (memory, CPU)

#### 9.4 Nginx Setup (0.5 дня)
- [ ] Создать `nginx.conf`
- [ ] Reverse proxy для frontend
- [ ] Reverse proxy для backend API
- [ ] WebSocket proxy настройка
- [ ] SSL/TLS сертификат (Let's Encrypt) - опционально для MVP
- [ ] Gzip compression
- [ ] Кэширование статики

#### 9.5 Deployment (0.5 дня)
- [ ] Создать `.env` на VPS с production значениями
- [ ] Build Docker images
- [ ] Запустить `docker-compose up -d`
- [ ] Проверить health checks
- [ ] Инициализировать БД (`init_db.py`)
- [ ] Загрузить базовые скиллы (`seed_skills.py`)
- [ ] Проверить логи всех сервисов

#### 9.6 Systemd Service (опционально, 0.5 дня)
- [ ] Создать systemd unit для автозапуска при перезагрузке
- [ ] Тестировать reboot сервера

#### 9.7 Backup Setup (0.5 дня)
- [ ] Скрипт backup PostgreSQL (cron job)
- [ ] Скрипт backup Qdrant data
- [ ] Retention policy (7 дней для БД)
- [ ] Тестовый restore

#### 9.8 Monitoring Setup (0.5 дня)
- [ ] Проверка логов: все пишутся корректно
- [ ] Простой health check скрипт (curl endpoints)
- [ ] Uptime monitor (например, через free service)

### Критерии приемки Этапа 9

- ✅ Все сервисы running на VPS
- ✅ Health checks всех сервисов healthy
- ✅ Telegram бот отвечает
- ✅ Web UI доступен через домен/IP
- ✅ Можно создать задачу через Telegram
- ✅ Можно создать задачу через Web UI
- ✅ Real-time updates работают
- ✅ Логи пишутся корректно
- ✅ PostgreSQL backup настроен
- ✅ Система переживает reboot сервера (если настроен systemd)

**Проверка на VPS**:
```bash
# SSH на VPS
ssh user@your-vps-ip

# Проверка сервисов
cd /path/to/balbes
docker-compose -f docker-compose.prod.yml ps

# Все должны быть Up и healthy
# Проверка логов
docker-compose -f docker-compose.prod.yml logs -f orchestrator

# Проверка через Telegram
# /start в боте

# Проверка Web UI
# https://your-domain.com
```

**Checkpoint**: MVP в production! Можно использовать.

---

## Этап 10: Final Testing & Handoff (1 день)

### Цель
Финальное тестирование в production, документация для пользователя.

### Задачи

#### 10.1 Production Testing (0.5 дня)
- [ ] Реальная задача для Coder (создать полезный скилл)
- [ ] Мониторинг токенов в течение дня
- [ ] Проверка stability (работает без перезапусков)
- [ ] Проверка all alerts работают

#### 10.2 User Documentation (0.5 дня)
- [ ] Обновить README.md с production URLs
- [ ] Примеры команд Telegram
- [ ] Screenshots Web UI (опционально)
- [ ] FAQ секция
- [ ] Troubleshooting guide

### Критерии приемки Этапа 10

- ✅ Система работает в production минимум 24 часа без критических ошибок
- ✅ Coder успешно создал минимум 1 реальный скилл
- ✅ Токены используются в пределах бюджета
- ✅ Все уведомления приходят корректно
- ✅ Документация полная и актуальная

---

## Timeline Summary

```
Week 1:
├── Day 1-2: Этап 1 (Core Infrastructure)
├── Day 3-4: Этап 2 (Memory Service)
└── Day 5:   Этап 3 (Skills Registry)

Week 2:
├── Day 6-7: Этап 4 (Orchestrator + Telegram)
└── Day 8-9: Этап 5 (Coder Agent)

Week 3:
├── Day 10:    Этап 6 (Web Backend)
├── Day 11-13: Этап 7 (Web Frontend)
└── Day 14-15: Этап 8 (Integration & Testing)

Week 4:
├── Day 16-17: Этап 9 (Production Deployment)
└── Day 18:    Этап 10 (Final Testing)

Reserve: Day 19-20 для непредвиденных сложностей
```

**Total**: ~18-20 дней

---

## Risks & Mitigation

### Risk 1: LLM API нестабильность
**Вероятность**: Medium
**Влияние**: High
**Митигация**: Fallback система должна быть очень надежной. Тестировать с разными сценариями ошибок.

### Risk 2: RabbitMQ сложность
**Вероятность**: Medium
**Влияние**: Medium
**Митигация**: Хорошо изучить примеры, использовать простую топологию, тщательно тестировать acknowledgments.

### Risk 3: Token costs превышение
**Вероятность**: Low-Medium
**Влияние**: High
**Митигация**: Жесткие лимиты с начала, алерты при 80%, автопереключение на cheap models.

### Risk 4: Coder генерирует плохой код
**Вероятность**: High (в начале)
**Влияние**: Medium
**Митигация**: Обязательные тесты, retry логика, накопление примеров в памяти для улучшения.

### Risk 5: Сложности с React/TypeScript
**Вероятность**: Low (если есть опыт) / Medium (если нет)
**Влияние**: Medium
**Митигация**: Использовать shadcn/ui examples, хорошие типы, TanStack Query для упрощения.

### Risk 6: Deployment проблемы
**Вероятность**: Medium
**Влияние**: Low
**Митигация**: Тщательно тестировать Docker Compose локально перед деплоем на VPS.

---

## Development Workflow

### Daily Routine

```bash
# Утро: обновление и проверка
git pull
make infra-up
make test

# Разработка новой фичи
git checkout -b feature/new-feature
# ... код ...
pytest tests/test_new_feature.py
git add .
git commit -m "feat: implement new feature"

# Вечер: проверка качества
ruff check .
ruff format .
pre-commit run --all-files
git push
```

### Code Review Checklist

Перед merge в develop:
- [ ] Тесты написаны и проходят
- [ ] Docstrings добавлены
- [ ] Type hints везде
- [ ] Ruff проверка прошла
- [ ] Нет TODO в коде (или записаны как issues)
- [ ] Логирование добавлено где нужно
- [ ] Обновлена документация (если нужно)

---

## Post-MVP Tasks (Backlog)

### High Priority
1. **Blogger Agent** - создать детальное ТЗ и реализовать
2. **Memory management UI** - просмотр и редактирование памяти агентов
3. **Advanced Coder** - git integration, auto-deploy с подтверждением
4. **CI/CD** - GitHub Actions для тестов и деплоя

### Medium Priority
1. **Agent взаимодействие** - агенты могут запрашивать помощь друг у друга
2. **Skill marketplace** - публикация и sharing скиллов
3. **Advanced commands** - более сложные команды в Telegram
4. **Scheduled tasks** - задачи по расписанию (cron-like)

### Low Priority
1. **Prometheus + Grafana** - advanced monitoring
2. **GraphQL API** - альтернатива REST
3. **Mobile app** - нативное приложение (или просто PWA)
4. **Multi-user support** - несколько пользователей с ролями

---

## Success Metrics для MVP

### После 1 недели использования:
- ✅ Система работает без перезапусков
- ✅ Coder создал минимум 2 полезных скилла
- ✅ Токены < $10/день
- ✅ Fallback сработал минимум 1 раз (доказывает устойчивость)
- ✅ Web UI используется ежедневно

### После 2 недель:
- ✅ Coder создал 5+ скиллов
- ✅ Токены стабильно в бюджете
- ✅ Никаких critical багов
- ✅ 0 data loss (логи, память, задачи сохраняются)
- ✅ Готовность к добавлению нового агента (Blogger)

### После 1 месяца:
- ✅ Система работает автономно (minimal manual intervention)
- ✅ Накоплена полезная память (50+ записей)
- ✅ Coder создал 10+ скиллов
- ✅ ROI positive (time saved > development time)

---

## Готовность к разработке

Перед началом убедитесь что:

- ✅ Все документы прочитаны и понятны
- ✅ VPS доступен (для финального деплоя)
- ✅ API ключи получены:
  - OpenRouter API key
  - AiTunnel API key (или другой fallback)
  - Telegram Bot token
- ✅ Выбран domain/IP для Web UI
- ✅ Git repository настроен
- ✅ Development окружение готово:
  - Python 3.13+ установлен
  - Docker установлен
  - Node.js установлен (для frontend)
  - IDE настроена (VSCode/Cursor)

---

## Начало разработки

**Команда для старта**:

```bash
# 1. Убедиться что в текущей директории правильный проект
pwd  # /home/balbes/projects/dev

# 2. Создать структуру
mkdir -p services/{orchestrator,coder,memory-service,skills-registry,web/backend,web/frontend}
mkdir -p shared/skills
mkdir -p config/{agents,skills}
mkdir -p data/{logs,coder_output,postgres,redis,rabbitmq,qdrant}
mkdir -p scripts
mkdir -p tests/{unit,integration,e2e}

# 3. Создать .env
cp .env.example .env
# Заполнить ключи

# 4. Начать с Этапа 1, задача 1.1
# См. DEVELOPMENT_PLAN.md - Этап 1

# 5. Коммитить progress регулярно
git add .
git commit -m "feat: project structure setup"
```

Удачи! 🚀
