# Architecture Decision Records (ADR)

Документ объясняющий ключевые архитектурные решения и их обоснование.

---

## ADR-001: Microservices Architecture

**Решение**: Каждый агент и сервис - независимый процесс/контейнер

**Контекст**:
- Нужна возможность останавливать/запускать агенты независимо
- Планируется до 10 разных агентов
- Требуется простота разработки и отладки

**Альтернативы**:
1. Монолит - все агенты в одном процессе
2. Serverless functions
3. Микросервисы (выбрано)

**Обоснование**:
- ✅ Независимость: падение одного агента не влияет на других
- ✅ Масштабируемость: легко добавлять новых агентов
- ✅ Development: можно работать над одним сервисом не трогая другие
- ✅ Deployment: можно обновлять сервисы по отдельности
- ❌ Complexity: больше moving parts, нужна оркестрация

**Выбор**: Микросервисы, но с разумной степенью декомпозиции (не nano-services).

---

## ADR-002: RabbitMQ vs Redis Streams vs Kafka

**Решение**: RabbitMQ для межагентной коммуникации

**Контекст**:
- Агенты должны общаться асинхронно
- Нужны guaranteed delivery и acknowledgments
- Масштаб: до 10 агентов, не миллионы сообщений

**Альтернативы**:
1. **RabbitMQ**: классика message broker
2. **Redis Streams**: простая очередь на Redis
3. **Kafka**: heavy для event streaming

**Обоснование RabbitMQ**:
- ✅ Надежность: acknowledgments, persistence, retries
- ✅ Routing: exchanges для direct и broadcast
- ✅ Management UI из коробки
- ✅ Проверенное решение
- ✅ Хорошие Python библиотеки (aio-pika)
- ❌ Чуть сложнее чем Redis Streams
- ✅ Достаточно легковесный для VPS

**Почему не Redis Streams**:
- Менее надежный (нет built-in acknowledgments)
- Нужно самим реализовывать retry logic
- Меньше возможностей routing

**Почему не Kafka**:
- Overkill для 10 агентов
- Требует больше ресурсов
- Сложнее настройка

---

## ADR-003: PostgreSQL + Redis + Qdrant (три БД)

**Решение**: Использовать три разных хранилища для разных типов данных

**Контекст**:
- Разные типы данных с разными требованиями
- Нужна быстрая память (TTL) и долговременная (search)
- Структурированные данные (агенты, задачи)

**Обоснование**:

**PostgreSQL** для structured data:
- Агенты, задачи, логи, токен-метрики
- ACID transactions
- Сложные JOIN запросы
- Views для аналитики

**Redis** для fast memory:
- Контекст сессий (TTL)
- История диалогов (TTL)
- Token counters (atomic increments)
- Rate limiting
- Быстрый доступ (<1ms)

**Qdrant** для long-term semantic memory:
- Векторный поиск по прошлому опыту
- Embeddings
- Постоянное хранение
- Не нужны ACID гарантии

**Альтернатива**: Все в одной БД (например, PostgreSQL + pgvector)
- ❌ Медленнее для fast memory (нет TTL из коробки)
- ❌ pgvector медленнее чем Qdrant
- ✅ Проще (меньше moving parts)

**Выбор**: Три БД для оптимальной производительности. Complexity оправдана.

---

## ADR-004: FastAPI для всех HTTP сервисов

**Решение**: FastAPI для Memory Service, Skills Registry, Web Backend

**Контекст**:
- Нужны асинхронные HTTP API
- Желательна автодокументация (OpenAPI)
- Python 3.13

**Альтернативы**:
1. **FastAPI**: современный async framework
2. **Flask**: синхронный, простой
3. **Django**: heavyweight с ORM

**Обоснование FastAPI**:
- ✅ Async/await native support
- ✅ Автоматическая OpenAPI документация
- ✅ Pydantic validation из коробки
- ✅ Высокая производительность
- ✅ Современный, активное развитие
- ✅ WebSocket support
- ❌ Чуть круче learning curve чем Flask

---

## ADR-005: React + shadcn/ui для Frontend

**Решение**: React 18 + TypeScript + shadcn/ui + Tailwind CSS

**Контекст**:
- Нужен красивый и функциональный UI
- Real-time updates
- Light/Dark theme
- Пользователь хочет делать "сразу хорошо"

**Альтернативы**:
1. **React** + shadcn/ui (выбрано)
2. Vue 3 + Element Plus
3. Svelte + SvelteKit

**Обоснование React + shadcn/ui**:
- ✅ Огромная экосистема
- ✅ shadcn/ui - красивые компоненты, кастомизируемые
- ✅ TanStack Query для data fetching (лучшее решение)
- ✅ Много примеров dashboards
- ✅ TypeScript support отличный
- ✅ Tailwind CSS - быстрая стилизация
- ✅ Light/Dark theme легко реализовать
- ❌ Чуть более verbose чем Vue/Svelte

**shadcn/ui vs Material UI / Ant Design**:
- ✅ Копируется в проект (полный контроль)
- ✅ Tailwind-based (единый styling approach)
- ✅ Современный дизайн
- ✅ Меньше bundle size

---

## ADR-006: OpenRouter как Primary Provider

**Решение**: OpenRouter для доступа к multiple LLM models

**Контекст**:
- Нужен доступ к Claude, GPT-4, и fallback models
- Один API для нескольких провайдеров
- Прозрачная ценовая политика

**Альтернативы**:
1. Прямой доступ к каждому провайдеру (OpenAI, Anthropic отдельно)
2. OpenRouter (выбрано)
3. Только один провайдер

**Обоснование**:
- ✅ Единый интерфейс для всех моделей
- ✅ Автоматический fallback внутри OpenRouter
- ✅ Прозрачные цены
- ✅ Доступ к free моделям (Llama)
- ✅ Не нужно управлять множеством API ключей
- ❌ Небольшая наценка (но минимальная)

---

## ADR-007: Qdrant для Vector DB

**Решение**: Qdrant для долговременной памяти с векторным поиском

**Контекст**:
- Нужен семантический поиск по прошлому опыту агентов
- Embeddings для текстов
- Быстрый поиск

**Альтернативы**:
1. **Qdrant** (выбрано)
2. **ChromaDB**: простой, embedded
3. **Weaviate**: feature-rich
4. **PostgreSQL + pgvector**: все в одной БД

**Обоснование Qdrant**:
- ✅ Отличная производительность
- ✅ Простой REST API
- ✅ Python client из коробки
- ✅ Легковесный (можно на том же VPS)
- ✅ Хорошая документация
- ✅ Cosine similarity для embeddings
- ❌ Дополнительный сервис (но оправдано)

**Почему не ChromaDB**:
- Embedded - сложнее масштабировать
- Меньше production-ready

**Почему не pgvector**:
- Медленнее чем специализированная vector DB
- Меньше возможностей оптимизации

---

## ADR-008: Гибридный Docker подход (dev vs prod)

**Решение**:
- Development: только БД в Docker, сервисы локально
- Production: все в Docker

**Контекст**:
- Пользователь скептичен насчет Docker в разработке
- Хочется удобства локальной разработки
- Production должен быть reproducible

**Обоснование**:
- ✅ Dev: быстрая итерация, нативный debugging, hot reload
- ✅ Dev: не нужно пересобирать образы при каждом изменении
- ✅ Prod: изоляция, reproducibility, easy deployment
- ✅ БД в Docker даже в dev: не нужно устанавливать локально
- ✅ Один docker-compose.infra.yml для всех разработчиков
- ❌ Разные окружения dev/prod (но минимальные отличия)

---

## ADR-009: JSON Lines для файловых логов

**Решение**: Структурированные логи в формате JSON Lines (.jsonl)

**Контекст**:
- Нужно парсить логи программно
- Хочется структурированные данные
- Читаемость для человека тоже важна

**Альтернативы**:
1. Plain text logs
2. JSON Lines (выбрано)
3. Binary format (Protobuf)

**Обоснование**:
- ✅ Легко парсить (каждая строка - валидный JSON)
- ✅ Структурированные данные (не нужен regex)
- ✅ Можно читать человеком (jq, cat)
- ✅ Легко фильтровать (grep по полям)
- ✅ Совместимо с ELK stack (если понадобится)
- ❌ Чуть больше места чем plain text (но несущественно)

**Example**:
```bash
cat data/logs/coder.log | jq 'select(.action == "llm_call")'
```

---

## ADR-010: YAML для конфигов, не JSON

**Решение**: Все конфиги в YAML формате

**Контекст**:
- Конфиги должны редактироваться человеком
- Нужны комментарии
- Иерархическая структура

**Обоснование YAML**:
- ✅ Человекочитаемый
- ✅ Поддержка комментариев
- ✅ Меньше синтаксиса чем JSON
- ✅ Multi-line strings (для instructions)
- ✅ Python библиотеки (PyYAML, ruamel.yaml)
- ❌ Чуть медленнее парсинг (но не критично для конфигов)

**Почему не JSON**:
- Нет комментариев
- Сложнее читать и редактировать

**Почему не TOML**:
- Менее гибкий для сложных структур
- Python библиотеки хуже

---

## ADR-011: Одна Qdrant коллекция, не отдельные

**Решение**: Одна коллекция `agent_memory` с фильтрацией по agent_id и scope

**Контекст**:
- Память агентов нужно разделять (personal vs shared)
- Но иногда нужен поиск по всей памяти

**Альтернативы**:
1. Отдельная коллекция для каждого агента
2. Одна коллекция с фильтрами (выбрано)

**Обоснование**:
- ✅ Проще управление (одна коллекция)
- ✅ Можно искать в shared памяти легко
- ✅ Меньше overhead
- ✅ Легко добавлять новых агентов (не нужно создавать коллекцию)
- ✅ Индексы по agent_id и scope для быстрой фильтрации
- ❌ Теоретически можно случайно получить данные другого агента (но предотвращается на уровне клиента)

---

## ADR-012: JWT для Web UI, не Session

**Решение**: JWT tokens для аутентификации Web UI

**Контекст**:
- Stateless API предпочтительнее
- Не нужна сложная система пользователей (MVP - один пользователь)

**Альтернативы**:
1. Session-based (cookies + Redis session store)
2. JWT (выбрано)
3. API key в каждом запросе

**Обоснование JWT**:
- ✅ Stateless (не нужно хранить sessions)
- ✅ Работает с CORS
- ✅ Стандартный подход для SPA
- ✅ Можно добавить claims (роли, permissions) в будущем
- ❌ Нельзя отозвать до expiration (но для MVP не критично)

**Процесс**:
1. User вводит WEB_AUTH_TOKEN на login странице
2. Backend проверяет против env variable
3. При успехе генерирует JWT (expires in 24h)
4. Frontend хранит JWT в localStorage
5. Все requests включают `Authorization: Bearer <jwt>`

---

## ADR-013: WebSocket для Real-time, не Polling

**Решение**: WebSocket для real-time updates в Web UI

**Контекст**:
- Dashboard должен показывать live статусы агентов
- Логи должны появляться в real-time
- Alerts должны приходить мгновенно

**Альтернативы**:
1. Server-Sent Events (SSE)
2. Polling (каждые N секунд)
3. WebSocket (выбрано)

**Обоснование WebSocket**:
- ✅ Bidirectional (хотя нужен только server→client, но для будущего полезно)
- ✅ Low latency
- ✅ Native browser support
- ✅ FastAPI WebSocket support из коробки
- ✅ Один connection вместо множества polling requests
- ❌ Чуть сложнее чем SSE
- ✅ Graceful fallback: если WS отключается, можно fallback на polling

**Hybrid approach**: WebSocket primary, polling каждые 10s как fallback.

---

## ADR-014: Coder не делает auto-deploy в MVP

**Решение**: Coder создает код в `/data/coder_output/`, не деплоит автоматически

**Контекст**:
- Безопасность: автогенерированный код может быть опасным
- Quality control: нужна человеческая проверка
- MVP: простота важнее автоматизации

**Обоснование**:
- ✅ Безопасность: пользователь проверяет код перед использованием
- ✅ Простота: не нужна сложная система git branches, CI/CD
- ✅ Гибкость: пользователь решает когда и как деплоить
- ❌ Manual step (но для MVP приемлемо)

**Future**: После MVP можно добавить workflow:
1. Coder создает branch
2. Создает PR
3. User reviews
4. Merge → auto-deploy

---

## ADR-015: Skills как YAML + Python, не Plugin System

**Решение**: Скиллы описываются YAML + реализуются Python функциями

**Контекст**:
- Нужна extensibility (добавление новых скиллов)
- Нужна валидация параметров
- Простота важна для MVP

**Альтернативы**:
1. Plugin system (dynamic loading .py файлов)
2. YAML + Python (выбрано)
3. Code-only (скиллы только как Python функции)

**Обоснование**:
- ✅ Декларативность: YAML описывает интерфейс
- ✅ Валидация: параметры проверяются перед выполнением
- ✅ Documentation: YAML служит документацией
- ✅ Простота: Python функции с четкой сигнатурой
- ✅ Hot reload: можно перезагружать скиллы без перезапуска
- ❌ Boilerplate: нужно поддерживать YAML + Python в sync

**Alternative considered**: Декораторы Python (@skill)
- Меньше boilerplate но сложнее валидация
- YAML подход более explicit и safe

---

## ADR-016: Token Budget per Agent, не Global

**Решение**: Каждый агент имеет свой токен-лимит

**Контекст**:
- Разные агенты используют токены по-разному
- Нужен контроль расходов
- Один "жадный" агент не должен блокировать других

**Обоснование**:
- ✅ Fairness: каждый агент имеет свою квоту
- ✅ Контроль: можно дать Coder больше, Orchestrator меньше
- ✅ Alerts: понятно какой агент тратит много
- ✅ Гибкость: можно менять лимиты per agent
- ❌ Complexity: нужно отслеживать для каждого

**Implementation**:
- Redis counters: `token_budget:{agent_id}:daily`
- Сбрасываются в 00:00 UTC
- Проверяются перед каждым LLM call

---

## ADR-017: Coder создает pytest тесты, всегда

**Решение**: Каждый скилл от Coder должен иметь минимум 3 pytest теста

**Контекст**:
- Качество кода важно
- Автогенерированный код может быть багованным
- Тесты помогают Coder понять что код работает

**Обоснование**:
- ✅ Quality: тесты гарантируют базовую работоспособность
- ✅ Confidence: если тесты прошли, код вероятно рабочий
- ✅ Learning: Coder учится на провалах тестов
- ✅ Documentation: тесты показывают как использовать скилл
- ❌ Tokens: генерация тестов тратит токены (но оправдано)

**Minimum tests**:
1. Success case (happy path)
2. Error handling (invalid params)
3. Edge case

---

## ADR-018: Базовые инструкции + персональные

**Решение**: `base_instructions.yaml` общие + `instructions` в каждом agent config

**Контекст**:
- Есть правила общие для всех (логирование, безопасность)
- Есть специфика каждого агента

**Обоснование**:
- ✅ DRY: не дублировать общие правила
- ✅ Гибкость: каждый агент может переопределить
- ✅ Maintainability: изменить base_instructions один раз
- ✅ Clarity: явное разделение общего и специфичного

**Loading order**:
1. Load base_instructions.yaml
2. Load agent-specific instructions
3. Concatenate: base + specific
4. Pass to LLM as system prompt

---

## ADR-019: Scope: personal vs shared для памяти

**Решение**: Два scope для памяти - personal (только агент) и shared (все агенты)

**Контекст**:
- Некоторая информация полезна только агенту (его опыт)
- Некоторая информация полезна всем (общие факты)

**Обоснование**:
- ✅ Privacy: агент не видит чужую personal память
- ✅ Sharing: можно делиться знаниями через shared
- ✅ Control: агент решает что сделать shared
- ✅ Search efficiency: поиск в personal быстрее (меньше данных)

**Examples**:
- **Personal**: "Я создал скилл X используя библиотеку Y"
- **Shared**: "Библиотека BeautifulSoup хороша для парсинга HTML"

---

## ADR-020: Retry с Exponential Backoff

**Решение**: При ошибке retry с exponential backoff (1s, 3s, 9s)

**Контекст**:
- LLM API может временно не отвечать
- Rate limits могут срабатывать

**Альтернативы**:
1. Fixed delay (1s, 1s, 1s)
2. Linear backoff (1s, 2s, 3s)
3. Exponential backoff (1s, 3s, 9s) - выбрано

**Обоснование**:
- ✅ Exponential: лучше для rate limits (даем API время восстановиться)
- ✅ 3 попытки: баланс между persistence и avoiding waste
- ✅ Max 3 retries: после этого fallback или fail
- ✅ Экономия токенов: не спамим API бесконечно

---

## ADR-021: Orchestrator как единственный Telegram bot

**Эволюция (2026-04):** целевое состояние — **один переиспользуемый модуль** Telegram (handlers, STT, security), но **отдельный бот и процесс на каждый инстанс агента** с собственным токеном и конфигом. Детали и миграция: **ADR-032**. До перехода на multi-bot описанное ниже остаётся режимом «один деплой — один бот».

**Решение**: Только Orchestrator имеет Telegram bot, другие агенты через него

**Контекст**:
- Пользователь хочет единую точку входа
- Множество ботов будет confusion

**Альтернативы**:
1. Каждый агент - свой бот
2. Один бот (Orchestrator) - выбрано

**Обоснование**:
- ✅ Единый интерфейс для пользователя
- ✅ Orchestrator координирует все
- ✅ Проще управление (один bot token)
- ✅ Меньше confusion (не нужно помнить какой бот для чего)
- ❌ Single point of failure (но Orchestrator критичен в любом случае)

**Implementation**: Команды вида `/task @agent` маршрутизируются через Orchestrator.

---

## ADR-022: Constraints в skill definition

**Решение**: Каждый скилл имеет constraints (timeout, allowed_paths, whitelist)

**Контекст**:
- Безопасность: не все агенты должны иметь полный доступ
- Resource management: нужны timeouts
- Flexibility: разные скиллы - разные ограничения

**Обоснование**:
- ✅ Security: whitelist предотвращает опасные операции
- ✅ Resource control: timeout предотвращает зависание
- ✅ Explicit: ограничения видны в YAML
- ✅ Granular: можно настроить per skill
- ❌ Boilerplate: нужно указывать для каждого скилла

**Examples**:
```yaml
constraints:
  timeout: 30
  allowed_paths: ["/data/coder_output/**"]
  allowed_commands: ["pytest", "python"]
  max_retries: 3
  rate_limit: 10  # per minute
```

---

## ADR-023: Skills Registry как отдельный сервис

**Решение**: Skills Registry - отдельный микросервис, не embedded

**Контекст**:
- Скиллы используются всеми агентами
- Нужна централизованная регистрация
- Coder будет добавлять новые скиллы

**Альтернативы**:
1. Embedded в каждом агенте (каждый загружает скиллы сам)
2. Централизованный сервис (выбрано)

**Обоснование**:
- ✅ Single source of truth для скиллов
- ✅ Легко добавлять новые (Coder регистрирует через API)
- ✅ Валидация в одном месте
- ✅ Все агенты видят одинаковый набор скиллов
- ✅ Hot reload скиллов без перезапуска агентов
- ❌ Дополнительный сервис (но оправдано)
- ❌ Network hop для выполнения (но несущественный overhead)

---

## ADR-024: Task timeout 10 минут

**Решение**: Максимальное время выполнения задачи - 10 минут

**Контекст**:
- Задачи не должны выполняться бесконечно
- Coder создание скилла занимает ~1-3 минуты обычно
- Нужен запас на сложные задачи

**Обоснование**:
- ✅ 10 минут достаточно для большинства задач
- ✅ Предотвращает зависания
- ✅ Экономия токенов (не тратим на зависшие задачи)
- ✅ User experience: понятно что что-то не так если > 10 минут

**Actions при timeout**:
1. Отменить задачу
2. Логировать timeout
3. Уведомить пользователя
4. Установить agent status в "error"

**Override**: Можно увеличить per task если нужно (в payload).

---

## ADR-025: Embeddings через OpenRouter API

**Решение**: Генерировать embeddings через OpenRouter (text-embedding-3-small)

**Контекст**:
- Нужны embeddings для Qdrant
- Хочется качественные embeddings
- Стоимость должна быть разумной

**Альтернативы**:
1. OpenRouter API (выбрано)
2. Локальная модель (sentence-transformers)
3. Anthropic Voyage API

**Обоснование OpenRouter**:
- ✅ Качество: OpenAI embeddings хорошие
- ✅ Цена: $0.0001 / 1K tokens (очень дешево)
- ✅ Простота: один API для всего (LLM + embeddings)
- ✅ Dimensions: 1536 (оптимально для Qdrant)
- ❌ Dependency на external API (но с кэшированием в Redis)

**Optimization**: Кэшировать embeddings в Redis для частых запросов.

---

## ADR-026: Light + Dark theme с первого дня

**Решение**: Поддержка обеих тем с переключателем

**Контекст**:
- Пользователь любит светлую тему
- Многие предпочитают темную
- shadcn/ui поддерживает из коробки

**Обоснование**:
- ✅ User preference: каждый выбирает что нравится
- ✅ Modern: большинство приложений имеют theme toggle
- ✅ Easy: shadcn/ui делает это trivial (5 минут)
- ✅ Professional: выглядит более polished
- ❌ Minimal extra work: но того стоит

**Implementation**:
- Zustand store для theme state
- localStorage для persistence
- Tailwind dark: classes
- Toggle button в header

---

## ADR-027: Базовые скиллы в shared/, не в registry service

**Решение**: Реализации скиллов в `shared/skills/`, YAML описания в `config/skills/`

**Контекст**:
- Скиллы должны быть доступны для разработки/тестирования
- Нужна возможность импортировать их напрямую
- Skills Registry только регистрирует и вызывает

**Обоснование**:
- ✅ Reusability: можно импортировать в тестах
- ✅ Development: легко разрабатывать и тестировать
- ✅ Versioning: в git вместе с кодом
- ✅ Separation: YAML (interface) отдельно от .py (implementation)

**Structure**:
```
shared/skills/search_web.py        <- Implementation
config/skills/search_web.yaml      <- Interface definition
```

---

## ADR-028: UTF-8 везде

**Решение**: Все файлы, БД, API - UTF-8 encoding

**Контекст**:
- Международная поддержка
- Эмодзи в Telegram
- Кириллица в командах

**Обоснование**:
- ✅ Unicode support: эмодзи, кириллица, любые языки
- ✅ Standard: UTF-8 - де-факто стандарт
- ✅ JSON: native UTF-8
- ✅ PostgreSQL: UTF-8 по умолчанию

**Проверка**:
```python
# Python файлы
# -*- coding: utf-8 -*-  # Необязательно в Python 3, но для ясности

# PostgreSQL
CREATE DATABASE balbes_agents ENCODING 'UTF8';
```

---

## ADR-029: Async/await везде

**Решение**: Все I/O операции асинхронные (asyncio)

**Контекст**:
- Python 3.13 с отличной asyncio поддержкой
- Много I/O: API calls, DB queries, file operations
- Хотим высокую производительность

**Обоснование**:
- ✅ Performance: не блокируем на I/O
- ✅ Scalability: можем обрабатывать много запросов
- ✅ Modern: async - современный подход в Python
- ✅ Libraries: FastAPI, aiohttp, aio-pika, asyncpg - все async
- ❌ Complexity: async код чуть сложнее
- ❌ Learning curve: но для опытного разработчика не проблема

**Rule**: Все функции выполняющие I/O должны быть `async def`.

---

## ADR-030: Не использовать ORM для PostgreSQL

**Решение**: Прямые SQL запросы через asyncpg, не SQLAlchemy ORM

**Контекст**:
- Простые CRUD операции
- Не нужны сложные relationships
- Хотим контроль и производительность

**Альтернативы**:
1. SQLAlchemy ORM
2. Tortoise ORM
3. Raw SQL с asyncpg (выбрано)

**Обоснование**:
- ✅ Performance: raw SQL быстрее
- ✅ Simplicity: нет ORM magic
- ✅ Control: полный контроль над запросами
- ✅ Lightweight: меньше зависимостей
- ❌ Boilerplate: нужно писать SQL руками
- ❌ Migrations: нужна своя система (но для MVP простые скрипты)

**Компромисс**: Можно использовать SQLAlchemy Core (не ORM) для query building если станет неудобно.

---

## ADR-031: Docker multi-stage builds

**Решение**: Использовать multi-stage builds для оптимизации размера images

**Контекст**:
- Production images должны быть легковесными
- Dev dependencies не нужны в prod

**Example**:
```dockerfile
# Stage 1: Builder
FROM python:3.13-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.13-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
CMD ["python", "main.py"]
```

**Обоснование**:
- ✅ Меньше размер final image (на 30-50%)
- ✅ Быстрее pull и deploy
- ✅ Безопаснее (меньше attack surface)

---

## ADR-032: Единый runtime агента, shared skills/tools и multi-bot

**Решение**: Разделить «движок агента» (одинаковый код), «инстанс агента» (процесс + порт + workspace + секреты) и «общий инструментарий» (skills + tools в репозитории). Telegram — **библиотечный модуль**, а не копипаста в каждом сервисе; при необходимости несколько процессов с разными токенами используют **один и тот же** модуль.

**Контекст**:
- Нужно много агентов (оркестратор, блогер №1/2, кодер, …) без размножения логики и без ручного переноса правок.
- У каждого агента — свой Telegram-бот (свой API key), свои инструкции (MD), свои права (какие skills/tools в ask vs agent mode).
- Секреты не должны попадать в git; повторяемое поведение (голос, команды) — в shared skills, а не в «кастомном коде бота».

**Целевая модель (слои)**:

1. **Agent runtime (один код)** — FastAPI + цикл LLM + `ToolDispatcher` + загрузка workspace. Параметризация через env: `AGENT_ID`, URL memory/skills-registry, порт HTTP. Реализация сейчас сосредоточена в `services/orchestrator/`; цель — вынести обобщаемое ядро в `shared/` или пакет `agent_runtime`, чтобы новый сервис был тонким `main.py` + Dockerfile.
2. **Инстанс агента** — отдельный контейнер/процесс на каждый `agent_id`, свой `WORKSPACE_ROOT` (часто `data/agents/{id}/` из приватного memory-репо), свой `.env` или Docker secrets (Telegram token, whitelist user id, опционально ключи каналов).
3. **Манифест без секретов (в git)** — например `config/agents/{id}.yaml` или `agents/{id}/manifest.yaml`: списки `skills_allowlist`, `tools_allowlist`, флаги режимов (`ask` / `agent` / `dev`), лимиты. Секреты только через env.
4. **Shared skills и tools** — общий каталог в репозитории + Skills Registry как HTTP-сервис (ADR-023); эксклюзивные скиллы — отдельный путь вроде `skills/local/{agent_id}/` или поле `exclusive_to: [agent_id]` в YAML скилла.
5. **Telegram** — один модуль (выделить из `services/orchestrator/telegram_bot.py`): класс принимает `token`, ссылки на HTTP API своего runtime (`base_url`), опционально `bot_label`. Несколько ботов = несколько процессов **или** потоки с одним кодом, разные `TELEGRAM_BOT_TOKEN`. Центральный «шлюз на всех ботов» не обязателен до масштаба, где не хочется N polling-соединений.

**Coder** — уже отдельный микросервис (`services/coder/`). Оркестратор не должен содержать дублирующую LLM-логику кодера; только HTTP-вызовы к Coder API. Это закрепить в деплое и документации.

**Делегирование между агентами (следующий шаг)**:
- Транспорт уже предполагается через RabbitMQ (ADR-002) или прямые HTTP вызовы между сервисами.
- В манифесте: `trusted_delegate_from: [agent_id]` и/или привязка к Telegram user id бота-сервиса.
- Пользовательский сценарий «напиши другому боту текстом» может оставаться на уровне LLM (инструмент `delegate_to_agent`) без отдельного бинарного протокола на первом этапе.

**Альтернативы**:
1. Копировать `telegram_bot.py` в каждый сервис — ❌ дублирование.
2. Один глобальный Telegram-шлюз, маршрутизация по `bot_id` — ✅ при очень многих ботах; ❌ лишняя сложность сейчас.

**Обоснование**:
- ✅ Один раз правите STT/команды/безопасность — все инстансы получают обновление.
- ✅ Новый агент = папка workspace + манифест + новый сервис в compose + секреты вне git.
- ✅ Разные блогеры переиспользуют одни и те же «черновики/очередь» скиллы, меняется только SOUL/AGENTS и права.

**Связь с ADR-021**: ADR-021 описывает исторический режим «один бот на систему». ADR-032 — целевой режим «один модуль Telegram, много ботов/процессов».

---

## Lessons Learned (будут добавляться)

Этот раздел будет заполняться по мере разработки.

### Lesson 1: (TBD)

### Lesson 2: (TBD)

---

## Future Decisions to Make

Вопросы для обсуждения в будущем:

1. **CI/CD**: GitHub Actions, GitLab CI, или self-hosted?
2. **Monitoring**: Prometheus + Grafana или более простое решение?
3. **Distributed tracing**: Нужно ли (Jaeger, Zipkin)?
4. **Service mesh**: Istio/Linkerd или оставить простым?
5. **Multi-region**: Нужна ли репликация на разные серверы?
6. **Kubernetes**: Переходить или Docker Compose достаточно?

---

## References

Эти решения основаны на:
- Best practices для микросервисов
- Опыт с FastAPI и async Python
- Production patterns для AI agents
- Constraints MVP (простота, быстрота разработки)
- User requirements (модульность, наблюдаемость, token control)
