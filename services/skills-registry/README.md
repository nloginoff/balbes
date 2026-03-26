# Skills Registry Service

Skills Registry Service управляет каталогом навыков для агентов Balbes.

## Функции

- **Управление навыками**: регистрация, обновление, удаление
- **Семантический поиск**: поиск по описанию через Qdrant embeddings
- **Фильтрация**: по категориям и тегам
- **Статистика**: отслеживание использования и рейтинга
- **Версионирование**: поддержка разных версий одного навыка

## Архитектура

```
├── main.py                      # FastAPI приложение
├── api/
│   ├── skills.py               # CRUD endpoints
│   └── search.py               # Семантический поиск
├── clients/
│   ├── postgres_client.py       # PostgreSQL интеграция
│   └── qdrant_client.py         # Qdrant embeddings
├── models/
│   └── skill.py                # Pydantic модели
└── requirements.txt
```

## API Endpoints

### Управление навыками

#### POST /api/v1/skills
Создать новый навык.

```bash
curl -X POST http://localhost:8101/api/v1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "name": "parse_github",
    "description": "Parse GitHub repository structure",
    "version": "1.0.0",
    "category": "web_parsing",
    "implementation_url": "https://github.com/...",
    "tags": ["github", "parsing", "repositories"],
    "input_schema": {
      "parameters": {"repo_url": {"type": "string"}},
      "required": ["repo_url"]
    },
    "output_schema": {
      "format": "json",
      "description": "Repository structure"
    }
  }'
```

#### GET /api/v1/skills/{skill_id}
Получить навык по ID.

```bash
curl http://localhost:8101/api/v1/skills/{skill_id}
```

#### GET /api/v1/skills
Получить список всех навыков.

```bash
curl "http://localhost:8101/api/v1/skills?limit=50&offset=0"
```

#### GET /api/v1/skills/category/{category}
Получить навыки по категории.

```bash
curl "http://localhost:8101/api/v1/skills/category/web_parsing"
```

### Поиск

#### POST /api/v1/skills/search
Семантический поиск по описанию.

```bash
curl -X POST http://localhost:8101/api/v1/skills/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "parse websites",
    "category": "web_parsing",
    "tags": ["parsing"],
    "limit": 10
  }'
```

#### GET /api/v1/skills/search/quick
Быстрый поиск (GET).

```bash
curl "http://localhost:8101/api/v1/skills/search/quick?q=parsing&limit=5"
```

## Быстрый старт

### 1. Инициализация БД

```bash
# Добавить схему в PostgreSQL
psql -U balbes -d balbes < scripts/init_skills_db.sql
```

### 2. Запуск сервиса

```bash
cd services/skills-registry

# Установить зависимости
pip install -r requirements.txt

# Запустить сервис
python main.py
```

Сервис будет доступен на http://localhost:8101

### 3. Проверка

```bash
# Health check
curl http://localhost:8101/health

# API документация
open http://localhost:8101/docs
```

## Данные навыков

Каждый навык содержит:

```python
{
    "skill_id": "uuid",           # Уникальный ID
    "name": "skill_name",         # Имя (уникальное)
    "description": "...",          # Описание
    "version": "1.0.0",           # Семантическая версия
    "category": "web_parsing",    # Категория
    "tags": ["tag1", "tag2"],     # Теги для фильтрации
    "implementation_url": "url",  # URL реализации
    "input_schema": {...},         # JSON Schema для input
    "output_schema": {...},        # JSON Schema для output
    "estimated_tokens": 1000,     # Примерные токены
    "authors": ["author1"],       # Авторы
    "dependencies": ["beautifulsoup4"],  # Зависимости
    "usage_count": 42,            # Количество использований
    "rating": 4.5,                # Средний рейтинг (0-5)
    "created_at": "2026-03-26T...",
    "updated_at": "2026-03-26T..."
}
```

## Модели данных

### SkillCreateRequest
Запрос на создание навыка.

### SkillResponse
Ответ с полной информацией о навыке.

### SkillSearchRequest
Запрос на поиск.

### SkillSearchResult
Результат поиска с score релевантности.

## Семантический поиск

Skills Registry использует OpenRouter API для генерации embeddings и Qdrant для векторного поиска.

Процесс:
1. Описание навыка (name + description + tags) конвертируется в embedding
2. Embedding индексируется в Qdrant
3. При поиске query-string также конвертируется в embedding
4. Qdrant находит наиболее похожие embeddings (cosine distance)
5. Результаты сортируются по score релевантности

## Окружение

Переменные из `.env`:
- `POSTGRES_*` - подключение к PostgreSQL
- `QDRANT_*` - подключение к Qdrant
- `OPENROUTER_API_KEY` - ключ OpenRouter для embeddings
- `SKILLS_REGISTRY_PORT` - порт сервиса (default: 8101)

## Тестирование

```bash
# Запустить интеграционные тесты
pytest tests/integration/test_skills_registry.py -v

# Запустить с покрытием
pytest tests/integration/test_skills_registry.py --cov
```

## Production

- Docker образ: `services/skills-registry/Dockerfile`
- Комбинированный stack: `docker-compose.prod.yml`
- Логирование: JSON format в `data/logs/`
- Метрики: Prometheus endpoints (опционально)
