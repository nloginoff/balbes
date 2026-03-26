# Memory Service - Quick Start Guide

## Подготовка (5 минут)

### 1. Исправить Docker permissions

```bash
# Добавить себя в группу docker
sudo usermod -aG docker $USER

# Применить изменения (выберите один из вариантов):
# Вариант A: Перезайти в систему
# Вариант B: Выполнить
newgrp docker

# Проверить
docker ps  # Должно работать без sudo
```

### 2. Запустить инфраструктуру

```bash
cd /home/balbes/projects/dev

# Запустить все БД (PostgreSQL, Redis, RabbitMQ, Qdrant)
make infra-up

# Проверить что все запустилось
docker compose -f docker-compose.infra.yml ps

# Должны увидеть 4 контейнера со статусом "Up" и "healthy"
```

### 3. Инициализировать базу данных

```bash
# Создать схему и таблицы
python scripts/init_db.py

# Должно вывести:
# ✅ Created table: agents
# ✅ Created table: tasks
# ✅ Created table: action_logs
# ✅ Created table: token_usage
# ✅ Seeded agent: orchestrator
# ✅ Seeded agent: coder
```

### 4. Установить зависимости

```bash
# Установить shared module (если еще не установлен)
pip install -e .

# Установить зависимости Memory Service
cd services/memory-service
pip install -r requirements.txt
```

### 5. Настроить API ключ для embeddings

```bash
# Открыть .env в корне проекта
nano .env  # или любой редактор

# Убедиться что установлен OPENROUTER_API_KEY
# (нужен для генерации embeddings в Qdrant)
OPENROUTER_API_KEY=sk-or-v1-...

# Сохранить и закрыть
```

---

## Запуск (30 секунд)

```bash
# Из директории services/memory-service
python main.py

# Или из корня проекта:
make dev-memory
```

Вы должны увидеть:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Starting Memory Service...
INFO:     Connecting to Redis...
INFO:     Redis connection established
INFO:     Connecting to Qdrant...
INFO:     Connected to Qdrant (1 collections)
INFO:     Collection 'agent_memory' already exists
INFO:     Connecting to PostgreSQL...
INFO:     PostgreSQL connection pool established
INFO:     All database connections established
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8100
```

---

## Быстрая проверка (1 минута)

### Тест 1: Health check

```bash
curl http://localhost:8100/health
```

Ожидается:
```json
{
  "service": "memory-service",
  "status": "healthy",
  "redis": "connected",
  "qdrant": "connected",
  "postgres": "connected",
  "timestamp": "2026-03-26T..."
}
```

### Тест 2: Get agents

```bash
curl http://localhost:8100/api/v1/agents
```

Должно вернуть orchestrator и coder агентов.

### Тест 3: OpenAPI docs

Откройте в браузере: **http://localhost:8100/docs**

Попробуйте любой endpoint через Swagger UI.

---

## Полное тестирование (5 минут)

```bash
# Из корня проекта
pytest tests/integration/test_memory_service.py -v -s

# Должны пройти все тесты (10+)
```

---

## Примеры использования

### Context (Fast Memory)

```bash
# Set context
curl -X POST http://localhost:8100/api/v1/context/my_agent \
  -H "Content-Type: application/json" \
  -d '{"key": "current_task", "value": {"step": 3, "files": ["main.py"]}, "ttl": 3600}'

# Get context
curl http://localhost:8100/api/v1/context/my_agent/current_task
```

### History

```bash
# Add message
curl -X POST http://localhost:8100/api/v1/history/my_agent \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Create a skill", "metadata": {}}'

# Get history
curl http://localhost:8100/api/v1/history/my_agent
```

### Semantic Memory

```bash
# Store memory
curl -X POST http://localhost:8100/api/v1/memory \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my_agent",
    "content": "I successfully parsed HackerNews using BeautifulSoup",
    "scope": "personal",
    "metadata": {"skill": "parse_hackernews"}
  }'

# Search (semantic)
curl -X POST http://localhost:8100/api/v1/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my_agent",
    "query": "how did I scrape websites",
    "limit": 5
  }'
```

---

## Troubleshooting

### Сервис не запускается

**Проблема**: `Redis connection failed`
```bash
# Проверить Redis
docker ps | grep redis
redis-cli ping  # Должно вернуть PONG
```

**Проблема**: `PostgreSQL connection failed`
```bash
# Проверить PostgreSQL
docker ps | grep postgres
psql -h localhost -U balbes -d balbes -c "SELECT 1"
```

**Проблема**: `Qdrant connection failed`
```bash
# Проверить Qdrant
docker ps | grep qdrant
curl http://localhost:6333/collections
```

### Embeddings не работают

**Проблема**: `OpenRouter API error`

Убедитесь что в `.env` установлен `OPENROUTER_API_KEY`:
```bash
grep OPENROUTER_API_KEY .env
```

### Import errors

**Проблема**: `ModuleNotFoundError: No module named 'shared'`

Установите shared module:
```bash
cd /home/balbes/projects/dev
pip install -e .
```

---

## Готово!

Memory Service готов к использованию! 🎉

Следующий шаг: **Этап 3 - Skills Registry**

---

**Документация**:
- Полная документация: `README.md`
- Завершение этапа: `STAGE2_COMPLETE.md`
- API спецификация: `../../docs/API_SPECIFICATION.md`
