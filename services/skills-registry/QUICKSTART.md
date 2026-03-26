# Skills Registry - Quick Start Guide

Быстрый гайд для запуска и тестирования Skills Registry Service.

## Шаг 1: Инициализация БД

```bash
cd /home/balbes/projects/dev

# Убедитесь, что инфраструктура запущена
docker compose -f docker-compose.infra.yml up -d

# Инициализируем БД (создаст все таблицы, включая skills)
source .venv/bin/activate
python scripts/init_db.py
```

Вывод должен включать:
```
✅ Created table: skills
✅ Created skills indexes
✅ Created view: v_trending_skills
✅ Created view: v_top_rated_skills
```

## Шаг 2: Установка зависимостей

```bash
cd services/skills-registry

# Зависимости уже в основном установлены (.venv)
# Но если нужны специфичные:
pip install -r requirements.txt
```

## Шаг 3: Запуск Services

```bash
# Terminal 1: Memory Service (если еще не запущен)
cd services/memory-service
python main.py
# Должен быть на http://localhost:8100

# Terminal 2: Skills Registry
cd services/skills-registry
python main.py
# Будет на http://localhost:8101
```

Проверка:
```bash
curl http://localhost:8101/health | jq
```

Ответ:
```json
{
  "service": "skills-registry",
  "status": "healthy",
  "postgres": "connected",
  "qdrant": "connected"
}
```

## Шаг 4: Создание первого скилла

```bash
curl -X POST http://localhost:8101/api/v1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "parse_github",
    "description": "Parse GitHub repository structure and extract metadata",
    "version": "1.0.0",
    "category": "web_parsing",
    "implementation_url": "https://github.com/example/parse_github",
    "tags": ["github", "parsing", "repositories", "api"],
    "input_schema": {
      "parameters": {"repo_url": {"type": "string"}},
      "required": ["repo_url"],
      "examples": {"repo_url": "https://github.com/user/repo"}
    },
    "output_schema": {
      "format": "json",
      "description": "Repository metadata with files and structure",
      "example": {"name": "repo", "stars": 100, "files": []}
    },
    "estimated_tokens": 2000,
    "authors": ["dev"],
    "dependencies": ["requests", "beautifulsoup4"]
  }' | jq
```

Ответ:
```json
{
  "skill_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "created",
  "name": "parse_github"
}
```

## Шаг 5: Проверка списка скиллов

```bash
curl http://localhost:8101/api/v1/skills | jq
```

Ответ:
```json
{
  "skills": [
    {
      "skill_id": "550e8400-...",
      "name": "parse_github",
      "description": "Parse GitHub repository structure...",
      "category": "web_parsing",
      "tags": ["github", "parsing", ...],
      "created_at": "2026-03-26T...",
      "usage_count": 0,
      "rating": 0.0
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

## Шаг 6: Создание еще скиллов

```bash
# Skill 2: Web Scraping
curl -X POST http://localhost:8101/api/v1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "scrape_website",
    "description": "Scrape web content with CSS selectors",
    "version": "1.0.0",
    "category": "web_parsing",
    "implementation_url": "https://github.com/example/scrape_website",
    "tags": ["web", "scraping", "html", "css"],
    "input_schema": {
      "parameters": {"url": {"type": "string"}, "selector": {"type": "string"}},
      "required": ["url", "selector"]
    },
    "output_schema": {
      "format": "json",
      "description": "Extracted HTML elements"
    },
    "estimated_tokens": 1500,
    "authors": ["dev"],
    "dependencies": ["beautifulsoup4", "requests"]
  }' | jq

# Skill 3: Data Processing
curl -X POST http://localhost:8101/api/v1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "process_csv",
    "description": "Process and analyze CSV files",
    "version": "1.0.0",
    "category": "data_processing",
    "implementation_url": "https://github.com/example/process_csv",
    "tags": ["csv", "data", "analysis", "pandas"],
    "input_schema": {
      "parameters": {"csv_url": {"type": "string"}, "operation": {"type": "string"}},
      "required": ["csv_url"]
    },
    "output_schema": {
      "format": "json",
      "description": "Processed data"
    },
    "estimated_tokens": 1000,
    "authors": ["dev"],
    "dependencies": ["pandas", "requests"]
  }' | jq
```

## Шаг 7: Семантический поиск

```bash
# Поиск по описанию
curl -X POST http://localhost:8101/api/v1/skills/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "extract data from websites",
    "limit": 10
  }' | jq

# Поиск с фильтрацией по категории
curl -X POST http://localhost:8101/api/v1/skills/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "parsing",
    "category": "web_parsing",
    "limit": 5
  }' | jq

# Быстрый поиск
curl "http://localhost:8101/api/v1/skills/search/quick?q=web+parsing&limit=5" | jq
```

## Шаг 8: Фильтрация по категории

```bash
# Получить все скиллы категории web_parsing
curl "http://localhost:8101/api/v1/skills/category/web_parsing" | jq

# Получить все скиллы категории data_processing
curl "http://localhost:8101/api/v1/skills/category/data_processing" | jq
```

## Шаг 9: API Documentation

```bash
# Автоматическая документация Swagger UI
open http://localhost:8101/docs

# ReDoc документация
open http://localhost:8101/redoc
```

## Шаг 10: Проверка интеграции с Memory Service

```bash
# Память об использованном скилле
curl -X POST http://localhost:8100/api/v1/memory \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "coder",
    "content": "I used parse_github skill to extract repository structure from https://github.com/torvalds/linux",
    "memory_type": "skill_usage",
    "importance": 0.9,
    "metadata": {"skill_name": "parse_github", "skill_id": "550e8400-..."}
  }' | jq

# Поиск в памяти
curl -X POST http://localhost:8100/api/v1/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "coder",
    "query": "github parsing skills I have used",
    "limit": 5
  }' | jq
```

## Troubleshooting

### Ошибка: "OpenRouter API key not configured"
```bash
# Проверьте .env
grep OPENROUTER_API_KEY /home/balbes/projects/dev/.env

# Если пусто, добавьте ключ:
echo "OPENROUTER_API_KEY=sk-or-v1-..." >> .env
```

### Ошибка: "Database connection failed"
```bash
# Проверьте PostgreSQL
docker exec balbes-postgres psql -U balbes -d balbes -c "SELECT 1"

# Проверьте таблицу skills
docker exec balbes-postgres psql -U balbes -d balbes -c "SELECT * FROM skills LIMIT 1"
```

### Ошибка: "Qdrant client not connected"
```bash
# Проверьте Qdrant
curl http://localhost:6333/health | jq
```

## Дальнейшие шаги

1. **Написать интеграционные тесты** (`tests/integration/test_skills_registry.py`)
2. **Создать базовые скиллы** (6 скиллов для MVP)
3. **Интегрировать с Orchestrator** (Этап 4)
4. **Добавить рейтинг и обратную связь** от агентов

## Полезные команды

```bash
# Просмотр всех скиллов в PostgreSQL
docker exec balbes-postgres psql -U balbes -d balbes -c "SELECT skill_id, name, category, usage_count FROM skills;"

# Просмотр коллекций в Qdrant
curl http://localhost:6333/collections | jq

# Очистка всех скиллов (BE CAREFUL!)
docker exec balbes-postgres psql -U balbes -d balbes -c "DELETE FROM skills;"
```

---

**Статус**: Skills Registry готов к использованию! ✅
