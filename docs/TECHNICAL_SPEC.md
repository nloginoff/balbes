# Техническое задание: Multi-Agent System MVP

## 1. Введение

### 1.1 Цель проекта

Создать модульную систему независимых AI-агентов для автоматизации различных задач (кодинг, контент-менеджмент, исследования) с централизованным управлением через Telegram и веб-интерфейс.

**Ключевое отличие от существующих решений (OpenClaw и др.)**: Минималистичный подход без излишеств, только необходимый функционал с максимальной модульностью.

### 1.2 Концепция

Система состоит из:
- **Основного агента (Orchestrator)** - координатор, принимающий команды от пользователя
- **Специализированных агентов** - автономные сервисы с узкой специализацией
- **Общей инфраструктуры** - память, скиллы, логирование
- **Двух интерфейсов управления** - Telegram (мобильный) и Web UI (детальный)

### 1.3 Глоссарий

| Термин | Описание |
|--------|----------|
| **Агент** | Автономный AI-сервис с LLM, памятью и скиллами |
| **Orchestrator** | Главный агент-координатор, точка входа для пользователя |
| **Скилл** | Атомарная функция/возможность агента (API call, парсинг, файловые операции) |
| **Быстрая память** | Контекст текущей сессии, хранится в Redis с TTL (1-24 часа) |
| **Долговременная память** | Индексированная история и знания в векторной БД (Qdrant) |
| **Scope** | Область видимости памяти: `personal` (только для агента) или `shared` (для всех) |
| **Message Bus** | Асинхронная очередь сообщений между агентами (RabbitMQ) |
| **Provider** | Провайдер LLM API (OpenRouter, AiTunnel) |
| **Fallback** | Переключение на альтернативную модель при недоступности основной |

---

## 2. Архитектура системы

### 2.1 Общая схема

```
┌─────────────────────────────────────────────────────────────┐
│                         User Layer                          │
│                                                               │
│   [Telegram Client] ←──→ [Orchestrator] ←──→ [Web Browser]  │
│                                │                              │
└────────────────────────────────┼──────────────────────────────┘
                                 │
┌────────────────────────────────┼──────────────────────────────┐
│                    Application Layer                          │
│                                 │                              │
│                        [Message Bus - RabbitMQ]              │
│                                 │                              │
│              ┌──────────────────┼───────────────┐             │
│              ↓                  ↓               ↓             │
│      [Orchestrator]      [Coder Agent]   [Agent N...]        │
│              ↓                  ↓               ↓             │
└──────────────┼──────────────────┼───────────────┼─────────────┘
               │                  │               │
┌──────────────┼──────────────────┼───────────────┼─────────────┐
│                      Services Layer                           │
│              ↓                  ↓               ↓             │
│      [Memory Service]   [Skills Registry]  [Web Backend]     │
│              │                  │               │             │
│              ↓                  ↓               ↓             │
└──────────────┼──────────────────┼───────────────┼─────────────┘
               │                  │               │
┌──────────────┼──────────────────┼───────────────┼─────────────┐
│                       Storage Layer                           │
│              ↓                  ↓               ↓             │
│         [PostgreSQL]        [Redis]        [Qdrant]          │
│     (state, logs, tokens) (fast memory)  (long-term memory)  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 2.2 Принципы архитектуры

1. **Модульность**: Каждый агент - независимый сервис
2. **Асинхронность**: Все коммуникации асинхронные (RabbitMQ, asyncio)
3. **Отказоустойчивость**: Падение одного агента не влияет на других
4. **Наблюдаемость**: Все действия логируются с детальными метриками
5. **Масштабируемость**: Легко добавлять новых агентов (до 10 в текущем scope)

### 2.3 Независимые сервисы

Каждый сервис:
- Запускается как отдельный процесс/контейнер
- Имеет собственные зависимости (requirements.txt)
- Общается через RabbitMQ (агенты) или HTTP API (сервисы)
- Может быть остановлен/запущен независимо
- Имеет собственный лог файл
- Имеет health check endpoint

**Список сервисов MVP**:
1. `orchestrator` - основной агент + Telegram bot
2. `coder` - агент-кодер
3. `memory-service` - сервис памяти (Redis + Qdrant + PostgreSQL)
4. `skills-registry` - регистр и управление скиллами
5. `web-backend` - API и WebSocket для UI
6. `web-frontend` - React приложение

---

## 3. Технический стек

### 3.1 Backend (Python)
- **Python**: 3.13+
- **Framework**: FastAPI (async, автодокументация, производительность)
- **Async**: asyncio + aiohttp
- **Message Queue**: RabbitMQ + aio-pika
- **Telegram**: python-telegram-bot (async)
- **LLM Client**: httpx (async HTTP)

### 3.2 Databases
- **PostgreSQL 16**: структурированные данные (агенты, задачи, логи, токен-метрики)
- **Redis 7**: быстрая память, кэш, rate limiting, counters
- **Qdrant**: векторная БД для семантического поиска в памяти

### 3.3 Frontend
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite (быстрая сборка)
- **UI Library**: shadcn/ui + Tailwind CSS (современный, кастомизируемый)
- **State Management**: Zustand (легковесный, простой API)
- **Data Fetching**: TanStack Query (react-query) (кэширование, auto-refetch)
- **Routing**: React Router v6
- **Charts**: Recharts (для графиков токенов)
- **WebSocket**: native WebSocket API
- **Notifications**: sonner (toast notifications)
- **Theme**: Light/Dark mode с переключателем

### 3.4 Infrastructure
- **Containerization**: Docker + Docker Compose
- **Reverse Proxy**: Nginx
- **Process Management**: Docker restart policies

### 3.5 LLM Providers
- **Primary**: OpenRouter (доступ к Claude, GPT-4, Llama, etc)
- **Fallback**: AiTunnel
- **Free tier**: OpenRouter free models (Llama 3.1 8B)

---

## 4. Ключевые компоненты

### 4.1 BaseAgent

Базовый класс для всех агентов, обеспечивающий:
- Интеграцию с LLM (через multi-provider client)
- Работу с памятью (быстрая + долговременная)
- Выполнение скиллов
- Коммуникацию через Message Bus
- Логирование всех действий
- Токен-трекинг

### 4.2 Multi-Provider LLM Client

Ключевые возможности:
- Поддержка нескольких провайдеров (OpenRouter, AiTunnel)
- Автоматический fallback при недоступности модели
- Токен-бюджетирование (daily/hourly limits)
- Автоматическое переключение на дешевую модель при превышении лимита
- Детальное логирование (модель, токены, стоимость)
- Алерты в Telegram при важных событиях

### 4.3 Memory System

**Три типа хранилищ**:

1. **Redis** (быстрая память):
   - Контекст текущей сессии
   - История диалога (последние N сообщений)
   - Счетчики токенов
   - TTL: 1-24 часа

2. **Qdrant** (долговременная память):
   - Индексированная история задач и результатов
   - Семантический поиск по прошлому опыту
   - Embeddings через OpenRouter API
   - Постоянное хранение

3. **PostgreSQL** (структурированные данные):
   - Состояние агентов
   - Очередь задач
   - Логи действий
   - Метрики токенов

### 4.4 Skills Registry

- Централизованный регистр всех скиллов
- Загрузка из YAML файлов
- Динамическая регистрация новых скиллов
- Валидация параметров и permissions
- API для получения информации о скиллах

### 4.5 Message Bus (RabbitMQ)

- Асинхронная коммуникация между агентами
- Direct messages (агент → агент)
- Broadcast messages (агент → все)
- Reliable delivery с acknowledgments
- Correlation ID для связи запрос-ответ

---

## 5. Интерфейсы управления

### 5.1 Telegram Bot

**Назначение**: Быстрый доступ к агентам из любого места

**Основные команды**:
- `/start` - приветствие и справка
- `/status` - статус всех агентов
- `/task @agent <описание>` - создать задачу
- `/stop @agent` - остановить задачу
- `/model @agent <model>` - сменить модель
- `/tokens` - статистика токенов
- `/logs @agent [N]` - последние логи
- `/help` - полная справка

**Уведомления**:
- Завершение задач
- Ошибки агентов
- Превышение токен-лимитов (80% и 100%)
- Fallback на другую модель

### 5.2 Web UI

**Назначение**: Детальный мониторинг и управление

**Основные страницы**:
1. **Dashboard** - обзор всех агентов, recent activity, токены
2. **Agent Detail** - детальная информация об агенте, логи, скиллы
3. **Chat** - отправка команд агентам
4. **Tokens** - детальная статистика использования и стоимости

**Особенности**:
- Real-time обновления через WebSocket
- Light/Dark theme с переключателем
- Адаптивный дизайн (desktop/tablet/mobile)
- Аутентификация по Bearer token

---

## 6. Безопасность

### 6.1 Аутентификация
- **Telegram**: проверка user_id (только владелец)
- **Web UI**: Bearer token в HTTP headers
- **API keys**: хранение в environment variables
- **Секреты**: не коммитятся в git (.env в .gitignore)

### 6.2 Изоляция
- **File operations**: whitelist разрешенных путей
- **Command execution**: whitelist разрешенных команд
- **Permissions**: проверка перед выполнением скилла
- **Network**: агенты не имеют прямого доступа к базам (через сервисы)

### 6.3 Rate Limiting
- Лимиты на LLM calls (daily/hourly per agent)
- Лимиты на API endpoints (веб UI)
- Таймауты на выполнение задач (10 минут)

---

## 7. Мониторинг и логирование

### 7.1 Что логируется

**Действия агентов**:
- Timestamp
- Agent ID
- Action type (skill_executed, llm_call, message_sent, etc)
- Параметры
- Результат
- Статус (success/error)
- Duration (ms)

**Использование токенов**:
- Agent ID
- Provider и модель
- Prompt/completion/total tokens
- Стоимость (USD)
- Размер контекста

**Сообщения между агентами**:
- From/to agent
- Message type
- Payload size
- Correlation ID

### 7.2 Хранение логов

- **Файлы**: `/data/logs/{agent_id}.log` (структурированный JSON)
- **PostgreSQL**: таблицы `action_logs` и `token_usage`
- **Retention**: 30 дней в БД, ротация файлов

### 7.3 Метрики для мониторинга

- Токены по агентам (hourly/daily)
- Стоимость по агентам
- Количество задач (pending/completed/failed)
- Success rate агентов
- Среднее время выполнения задач
- Частота использования fallback

---

## 8. Non-Functional Requirements

### 8.1 Производительность
- Response time Web UI: < 200ms (API calls)
- Response time Telegram bot: < 3s
- Task processing: начало в течение 5s после создания
- WebSocket latency: < 100ms

### 8.2 Надежность
- Uptime: 99% (допускается простой для обновлений)
- Graceful shutdown: все задачи завершаются или сохраняются
- Auto-restart: сервисы перезапускаются при падении (Docker restart policy)

### 8.3 Масштабируемость
- Поддержка до 10 агентов одновременно
- До 100 задач в очереди
- До 1M записей в логах (с ротацией)

### 8.4 Maintainability
- Документированный код (docstrings)
- Type hints везде
- Unit тесты для базовых компонентов
- Структурированные конфиги (YAML)

---

## 9. Ограничения MVP

**Функциональные ограничения**:
- Только 2 агента (Orchestrator + Coder)
- Базовый набор команд Telegram
- Простой Coder без автодеплоя
- Нет Blogger агента (отдельное ТЗ)
- Нет графов взаимодействий в UI
- Нет Prometheus/Grafana

**Технические ограничения**:
- Single VPS deployment (не distributed)
- Нет Kubernetes
- Нет CI/CD pipeline
- Базовая обработка ошибок (без advanced retry strategies)

---

## 10. Следующие этапы (после MVP)

1. **Blogger Agent** - отдельное детальное ТЗ
2. **Advanced Coder** - автотесты, git integration, auto-deploy
3. **UI Enhancements** - графы взаимодействий, advanced analytics
4. **More Agents** - researcher, analyst, etc
5. **Advanced Monitoring** - Prometheus, Grafana, alerting
6. **CI/CD** - автоматическое тестирование и деплой

---

## Связанные документы

- [MVP Scope](MVP_SCOPE.md) - детальный список что входит и не входит в MVP
- [Project Structure](PROJECT_STRUCTURE.md) - организация файлов и директорий
- [Data Models](DATA_MODELS.md) - схемы БД и Pydantic модели
- [API Specification](API_SPECIFICATION.md) - все endpoints
- [Agents Guide](AGENTS_GUIDE.md) - детальное описание каждого агента
- [Development Plan](DEVELOPMENT_PLAN.md) - этапы разработки
- [Deployment](DEPLOYMENT.md) - инструкции по развертыванию
- [Configuration](CONFIGURATION.md) - все конфигурационные файлы
