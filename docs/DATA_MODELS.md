# Модели данных и схемы баз данных

## Pydantic Models (shared/models.py)

### Agent Models

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import UUID, uuid4

class AgentConfig(BaseModel):
    """Конфигурация агента из YAML файла"""
    agent_id: str
    name: str
    description: str
    llm_settings: Dict[str, Any]
    token_limits: Dict[str, int]
    skills: List[str]
    instructions: str

class AgentState(BaseModel):
    """Текущее состояние агента (хранится в PostgreSQL)"""
    agent_id: str
    name: str
    status: Literal["idle", "working", "error", "paused"]
    current_task_id: Optional[UUID] = None
    current_model: str
    last_activity: datetime
    tokens_used_today: int
    tokens_used_hour: int
    config: Dict[str, Any]  # Текущая конфигурация
```

### Task Models

```python
class Task(BaseModel):
    """Задача для агента"""
    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    description: str  # Описание задачи от пользователя
    status: Literal["pending", "in_progress", "completed", "failed"]
    payload: Dict[str, Any] = {}  # Дополнительные параметры
    result: Optional[Dict[str, Any]] = None  # Результат выполнения
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None
    created_by: str = "user"  # "user" или agent_id

class TaskResult(BaseModel):
    """Результат выполнения задачи"""
    task_id: UUID
    status: Literal["success", "error"]
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tokens_used: int
    duration_ms: int
```

### Message Models

```python
class Message(BaseModel):
    """Сообщение между агентами через RabbitMQ"""
    id: UUID = Field(default_factory=uuid4)
    from_agent: str
    to_agent: str  # agent_id или "broadcast"
    type: Literal["task", "response", "notification", "query", "status"]
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: Optional[UUID] = None  # Для связи запрос-ответ

    # Для сериализации в RabbitMQ
    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        return cls.model_validate_json(json_str)
```

### Memory Models

```python
class MemoryRecord(BaseModel):
    """Запись в долговременной памяти (Qdrant)"""
    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    scope: Literal["personal", "shared"]
    content: str  # Текст для индексации
    metadata: Dict[str, Any] = {}  # Дополнительные данные
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Vector не включен в модель - генерируется в Memory Service

class MemorySearchResult(BaseModel):
    """Результат поиска в памяти"""
    content: str
    score: float  # Similarity score (0-1)
    metadata: Dict[str, Any]
    timestamp: datetime

class ContextData(BaseModel):
    """Данные для быстрой памяти (Redis)"""
    agent_id: str
    key: str
    value: Any
    ttl: int = 3600  # seconds

class ConversationMessage(BaseModel):
    """Сообщение в истории диалога"""
    role: Literal["user", "assistant", "system"]
    content: str
    metadata: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### Log Models

```python
class LogEntry(BaseModel):
    """Лог действия агента"""
    id: Optional[int] = None  # Auto-increment в PostgreSQL
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: str  # skill_executed, llm_call, message_sent, task_started, etc
    parameters: Dict[str, Any] = {}
    result: Optional[Dict[str, Any]] = None
    status: Literal["success", "error"]
    duration_ms: int
    error_message: Optional[str] = None

    # Дополнительный контекст
    task_id: Optional[UUID] = None
    correlation_id: Optional[UUID] = None

class TokenUsage(BaseModel):
    """Использование токенов"""
    id: Optional[int] = None
    agent_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: str  # llm_call, embedding_generation
    provider: str  # openrouter, aitunnel
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    context_size: int  # Сколько было в контексте
    fallback_used: bool = False
    task_id: Optional[UUID] = None
```

### LLM Models

```python
class LLMRequest(BaseModel):
    """Запрос к LLM"""
    messages: List[Dict[str, str]]  # [{"role": "user", "content": "..."}]
    model: Optional[str] = None  # Если None - берется из config агента
    max_tokens: int = 4000
    temperature: float = 0.7
    agent_id: str

class LLMResponse(BaseModel):
    """Ответ от LLM"""
    content: str
    model: str  # Модель которая ответила (может отличаться из-за fallback)
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    fallback_used: bool
    duration_ms: int
```

### Skill Models

```python
class SkillParameter(BaseModel):
    """Параметр скилла"""
    name: str
    type: str  # string, integer, boolean, dict, list
    required: bool = True
    description: str = ""
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None

class SkillDefinition(BaseModel):
    """Определение скилла из YAML"""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "system"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    parameters: List[SkillParameter]
    returns: Dict[str, Any]  # {type: "dict", description: "..."}

    implementation: str  # Путь к Python модулю
    permissions: List[str]  # ["read", "write", "network", "execute"]
    constraints: Dict[str, Any] = {}  # timeout, allowed_paths, etc
    tags: List[str] = []

class SkillExecution(BaseModel):
    """Запрос на выполнение скилла"""
    skill_name: str
    parameters: Dict[str, Any]
    agent_id: str
    task_id: Optional[UUID] = None

class SkillResult(BaseModel):
    """Результат выполнения скилла"""
    skill_name: str
    status: Literal["success", "error"]
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: int
```

---

## PostgreSQL Schema

### Таблица: agents

```sql
CREATE TABLE agents (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'idle',
    current_task_id UUID REFERENCES tasks(id),
    current_model VARCHAR(100) NOT NULL,
    config JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMP NOT NULL DEFAULT NOW(),
    tokens_used_today INTEGER NOT NULL DEFAULT 0,
    tokens_used_hour INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT status_check CHECK (status IN ('idle', 'working', 'error', 'paused'))
);

CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_agents_last_activity ON agents(last_activity);
```

### Таблица: tasks

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(50) NOT NULL REFERENCES agents(id),
    description TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    payload JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_by VARCHAR(50) NOT NULL,

    CONSTRAINT status_check CHECK (status IN ('pending', 'in_progress', 'completed', 'failed'))
);

CREATE INDEX idx_tasks_agent_id ON tasks(agent_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);
CREATE INDEX idx_tasks_agent_status ON tasks(agent_id, status);
```

### Таблица: action_logs

```sql
CREATE TABLE action_logs (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    action VARCHAR(100) NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    status VARCHAR(20) NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    task_id UUID REFERENCES tasks(id),
    correlation_id UUID,

    CONSTRAINT status_check CHECK (status IN ('success', 'error'))
);

CREATE INDEX idx_action_logs_agent_id ON action_logs(agent_id);
CREATE INDEX idx_action_logs_timestamp ON action_logs(timestamp DESC);
CREATE INDEX idx_action_logs_agent_time ON action_logs(agent_id, timestamp DESC);
CREATE INDEX idx_action_logs_task_id ON action_logs(task_id);
```

### Таблица: token_usage

```sql
CREATE TABLE token_usage (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    action VARCHAR(50) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    cost_usd DECIMAL(10, 6) NOT NULL,
    context_size INTEGER NOT NULL,
    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    task_id UUID REFERENCES tasks(id)
);

CREATE INDEX idx_token_usage_agent_id ON token_usage(agent_id);
CREATE INDEX idx_token_usage_timestamp ON token_usage(timestamp DESC);
CREATE INDEX idx_token_usage_agent_time ON token_usage(agent_id, timestamp DESC);

-- Для быстрых агрегаций
CREATE INDEX idx_token_usage_agent_date ON token_usage(agent_id, DATE(timestamp));
```

### Views для удобства

```sql
-- Токены по агентам за сегодня
CREATE VIEW v_tokens_today AS
SELECT
    agent_id,
    SUM(total_tokens) as total_tokens,
    SUM(cost_usd) as total_cost,
    COUNT(*) as num_calls,
    MAX(timestamp) as last_call
FROM token_usage
WHERE DATE(timestamp) = CURRENT_DATE
GROUP BY agent_id;

-- Токены по агентам за текущий час
CREATE VIEW v_tokens_current_hour AS
SELECT
    agent_id,
    SUM(total_tokens) as total_tokens,
    SUM(cost_usd) as total_cost
FROM token_usage
WHERE timestamp >= DATE_TRUNC('hour', NOW())
GROUP BY agent_id;

-- Статистика задач по агентам
CREATE VIEW v_task_stats AS
SELECT
    agent_id,
    COUNT(*) FILTER (WHERE status = 'completed') as completed,
    COUNT(*) FILTER (WHERE status = 'failed') as failed,
    COUNT(*) FILTER (WHERE status IN ('pending', 'in_progress')) as active,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (WHERE status = 'completed') as avg_duration_seconds
FROM tasks
GROUP BY agent_id;
```

---

## Redis Data Structures

### Keys Pattern

```
context:{agent_id}:{key}              - Hash или String
history:{agent_id}                    - List (LPUSH/LRANGE)
token_budget:{agent_id}:daily         - String (counter)
token_budget:{agent_id}:hourly        - String (counter)
token_alert_sent:{agent_id}:daily     - String (flag)
agent_state:{agent_id}                - Hash
rate_limit:{agent_id}:{action}        - String (counter)
```

### Примеры использования

```python
# Context
await redis.set("context:coder:current_files", json.dumps([...]), ex=3600)
value = await redis.get("context:coder:current_files")

# History (последние 50 сообщений)
await redis.lpush("history:coder", json.dumps(message))
await redis.ltrim("history:coder", 0, 49)
await redis.expire("history:coder", 86400)  # 24 часа
messages = await redis.lrange("history:coder", 0, -1)

# Token budget
await redis.incr("token_budget:coder:daily", amount=tokens)
await redis.expire("token_budget:coder:daily", seconds_until_midnight)
current = int(await redis.get("token_budget:coder:daily") or 0)

# Rate limiting
key = f"rate_limit:coder:llm_call"
count = await redis.incr(key)
if count == 1:
    await redis.expire(key, 60)  # 60 секунд окно
if count > 10:  # Максимум 10 вызовов в минуту
    raise RateLimitExceeded()
```

### TTL (Time To Live)

```python
context:*                  - 3600s (1 час) или custom
history:*                  - 86400s (24 часа)
token_budget:*:daily       - до 00:00 UTC следующего дня
token_budget:*:hourly      - до следующего часа
token_alert_sent:*:daily   - до 00:00 UTC следующего дня
rate_limit:*               - 60s (окно для rate limiting)
```

---

## Qdrant Collection

### Collection: agent_memory

```python
# Конфигурация коллекции
{
    "vectors": {
        "size": 1536,  # OpenAI text-embedding-3-small
        "distance": "Cosine"
    }
}

# Payload schema
{
    "agent_id": "coder",           # keyword (индексируется)
    "scope": "personal",           # keyword (индексируется)
    "content": "Created skill...", # text (не индексируется, но хранится)
    "timestamp": "2026-03-26T15:30:00Z",  # datetime
    "metadata": {
        "task_id": "uuid",
        "tags": ["skill", "parsing"],
        "success": true,
        "tokens_used": 1234
    }
}
```

### Индексы

```python
# Создание коллекции с индексами
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

client.create_collection(
    collection_name="agent_memory",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# Создание payload индексов для быстрой фильтрации
client.create_payload_index(
    collection_name="agent_memory",
    field_name="agent_id",
    field_schema=PayloadSchemaType.KEYWORD,
)

client.create_payload_index(
    collection_name="agent_memory",
    field_name="scope",
    field_schema=PayloadSchemaType.KEYWORD,
)
```

### Queries примеры

```python
# Поиск в personal памяти агента
results = client.search(
    collection_name="agent_memory",
    query_vector=embedding,
    query_filter={
        "must": [
            {"key": "agent_id", "match": {"value": "coder"}},
            {"key": "scope", "match": {"value": "personal"}}
        ]
    },
    limit=5
)

# Поиск в shared памяти
results = client.search(
    collection_name="agent_memory",
    query_vector=embedding,
    query_filter={
        "must": [
            {"key": "scope", "match": {"value": "shared"}}
        ]
    },
    limit=5
)
```

---

## Provider и Model Configs

### ProviderConfig (из config/providers.yaml)

```python
class ModelInfo(BaseModel):
    """Информация о модели"""
    id: str  # "anthropic/claude-3.5-sonnet"
    cost_per_1k_tokens: float
    context_window: int
    capabilities: List[str]  # ["code", "reasoning", "long_context"]

class ProviderConfig(BaseModel):
    """Конфигурация провайдера"""
    api_key: str
    base_url: str
    timeout: int = 60
    models: List[ModelInfo]

class FallbackChainItem(BaseModel):
    """Элемент цепочки fallback"""
    provider: str
    model: str

class ProvidersConfig(BaseModel):
    """Общая конфигурация провайдеров"""
    providers: Dict[str, ProviderConfig]
    fallback_chain: List[FallbackChainItem]
    cheap_models: List[str]  # Для переключения при превышении лимита
    token_limits: Dict[str, int]
    notifications: Dict[str, Any]
```

---

## WebSocket Events

### Event Types

```python
class WSEvent(BaseModel):
    """WebSocket событие для frontend"""
    type: Literal[
        "agent_status_changed",
        "new_log_entry",
        "task_created",
        "task_completed",
        "token_alert",
        "error"
    ]
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Примеры событий:

# Agent status changed
{
    "type": "agent_status_changed",
    "data": {
        "agent_id": "coder",
        "old_status": "idle",
        "new_status": "working",
        "task_id": "uuid"
    }
}

# New log entry
{
    "type": "new_log_entry",
    "data": {
        "agent_id": "coder",
        "action": "skill_executed",
        "status": "success",
        "summary": "Executed write_file"
    }
}

# Token alert
{
    "type": "token_alert",
    "data": {
        "agent_id": "coder",
        "level": "warning",  # warning или critical
        "percentage": 85,
        "tokens_used": 85000,
        "limit": 100000,
        "message": "Agent approaching daily token limit"
    }
}

# Task completed
{
    "type": "task_completed",
    "data": {
        "task_id": "uuid",
        "agent_id": "coder",
        "status": "completed",
        "summary": "Created skill parse_hackernews"
    }
}
```

---

## File Formats

### Skill YAML Format

```yaml
name: parse_website
description: Парсинг HTML страницы и извлечение данных
version: "1.0.0"
author: "coder"
created_at: "2026-03-26T15:00:00Z"

parameters:
  - name: url
    type: string
    required: true
    description: URL страницы для парсинга

  - name: selectors
    type: dict
    required: false
    description: CSS селекторы для извлечения данных
    default: {}

returns:
  type: dict
  description: Извлеченные данные с ключами из selectors

implementation: skills/parse_website.py

permissions:
  - network
  - api_call

constraints:
  timeout: 30
  max_retries: 3
  allowed_domains:
    - "*.com"
    - "*.org"

tags:
  - parsing
  - web
  - scraping
```

### Agent Config YAML Format

```yaml
# config/agents/coder.yaml
agent_id: coder
name: "Coder Agent"
description: "Агент для написания Python кода и скиллов"

llm_settings:
  primary_model: "openrouter/anthropic/claude-3.5-sonnet"
  fallback_models:
    - "openrouter/openai/gpt-4-turbo"
    - "aitunnel/gpt-4-turbo"
  max_tokens: 8000
  temperature: 0.3  # Низкая для детерминизма в коде

token_limits:
  daily: 100000
  hourly: 15000

skills:
  - read_file
  - write_file
  - execute_command
  - search_web
  - query_memory
  - send_message

instructions: |
  Ты - агент-программист на Python.

  Твоя задача: создавать качественные Python скиллы по описанию пользователя.

  Workflow создания скилла:
  1. Проанализируй требования
  2. Найди в памяти похожие примеры (query_memory)
  3. Создай код скилла с type hints и docstrings
  4. Создай YAML описание
  5. Создай pytest тесты (минимум 3 теста)
  6. Запусти тесты (execute_command: "pytest")
  7. Если не прошли - исправь (максимум 3 попытки)
  8. Сохрани все в /data/coder_output/skills/{skill_name}/
  9. Сохрани результат в память для будущих задач
  10. Сообщи Orchestrator о завершении

  Правила:
  - Всегда используй type hints
  - Пиши docstrings (Google style)
  - Код должен быть PEP 8 compliant
  - Обрабатывай ошибки gracefully
  - Не используй deprecated библиотеки
  - Проверяй что write_file пишет только в разрешенные пути
```

---

## Log File Format (JSON Lines)

```jsonl
{"timestamp": "2026-03-26T15:30:01.123Z", "level": "INFO", "agent_id": "coder", "action": "task_received", "task_id": "abc-123", "description": "Create skill parse_hackernews"}
{"timestamp": "2026-03-26T15:30:02.456Z", "level": "INFO", "agent_id": "coder", "action": "skill_executed", "skill": "query_memory", "params": {"query": "parsing examples"}, "status": "success", "duration_ms": 234}
{"timestamp": "2026-03-26T15:30:05.789Z", "level": "INFO", "agent_id": "coder", "action": "llm_call", "model": "claude-3.5-sonnet", "tokens": 1456, "cost": 0.02, "duration_ms": 2500}
{"timestamp": "2026-03-26T15:32:10.012Z", "level": "INFO", "agent_id": "coder", "action": "task_completed", "task_id": "abc-123", "status": "success", "total_tokens": 5234, "duration_ms": 128889}
```

**Парсинг**: Каждая строка - валидный JSON, можно обрабатывать построчно

---

## Data Size Estimates (для планирования)

### PostgreSQL

```
tasks: ~1KB per record
  - 1000 задач = 1MB
  - 100K задач = 100MB

action_logs: ~500 bytes per record
  - 10K логов/день = 5MB/день
  - 30 дней retention = 150MB

token_usage: ~200 bytes per record
  - ~100 записей/день на агента (зависит от активности)
  - 2 агента * 100 * 30 дней = 6000 записей = 1.2MB

Total за 30 дней: ~200-500MB (комфортно для VPS)
```

### Redis

```
history:{agent_id}: 50 сообщений * 1KB = 50KB per agent
context:{agent_id}:*: ~10 ключей * 5KB = 50KB per agent
token_budget:*: ~4 ключа * 10 bytes = 40 bytes per agent

Total для 10 агентов: ~1MB (минимально)
```

### Qdrant

```
Embedding: 1536 floats * 4 bytes = 6KB
Payload: ~1KB
Total per record: ~7KB

1000 записей = 7MB
10K записей = 70MB
100K записей = 700MB

Growth: ~100-200 записей/день → 700KB-1.4MB/день
За год: ~250-500MB (приемлемо)
```

### Logs (files)

```
JSON log: ~300 bytes per line
Active agent: ~1000 действий/день = 300KB/день
Rotation: каждые 100MB или 7 дней

2 агента * 300KB * 7 дней = ~4MB (до ротации)
```

**Итого для MVP на VPS**: ~1-2GB для данных (комфортно на любом VPS)

---

## Data Flow Examples

### Example 1: Создание задачи через Telegram

```
1. User → Telegram: "/task @coder создай скилл для парсинга HackerNews"

2. Telegram Bot → Orchestrator Agent:
   Message {
     from: "telegram_user",
     to: "orchestrator",
     type: "command",
     payload: {command: "task", args: {...}}
   }

3. Orchestrator → PostgreSQL:
   INSERT INTO tasks (agent_id='coder', description='...')
   → task_id = "abc-123"

4. Orchestrator → RabbitMQ:
   Message {
     from: "orchestrator",
     to: "coder",
     type: "task",
     payload: {task_id: "abc-123", description: "..."},
     correlation_id: "abc-123"
   }

5. Coder получает из RabbitMQ → начинает работу

6. Coder → PostgreSQL:
   UPDATE tasks SET status='in_progress', started_at=NOW()
   INSERT INTO action_logs (action='task_started', ...)

7. Coder → LLMClient → OpenRouter API

8. LLMClient → PostgreSQL:
   INSERT INTO token_usage (agent_id='coder', tokens=1456, ...)

9. Coder → Skills Registry: query_memory

10. Coder → write_file (implementation.py, skill.yaml, tests)

11. Coder → execute_command("pytest")

12. Coder → PostgreSQL:
    UPDATE tasks SET status='completed', result={...}

13. Coder → RabbitMQ:
    Message {
      from: "coder",
      to: "orchestrator",
      type: "response",
      payload: {task_id: "abc-123", status: "completed"},
      correlation_id: "abc-123"
    }

14. Orchestrator → Telegram:
    "✅ @coder завершил задачу: создан скилл parse_hackernews"

15. Orchestrator → WebSocket → Web UI:
    Event {type: "task_completed", data: {...}}
```

---

## Backup Strategy

### PostgreSQL
```bash
# Daily backup (cron job)
pg_dump -U balbes balbes_agents > backup_$(date +%Y%m%d).sql
# Retention: 7 дней

# Restore
psql -U balbes balbes_agents < backup_20260326.sql
```

### Qdrant
```bash
# Snapshot (через API или просто копирование volume)
docker cp balbes-qdrant:/qdrant/storage ./backups/qdrant_$(date +%Y%m%d)
# Retention: 7 дней
```

### Redis
```bash
# RDB snapshots (автоматически с appendonly yes)
# Копирование dump.rdb
cp data/redis/dump.rdb backups/redis_$(date +%Y%m%d).rdb
# Retention: 3 дня (fast memory - не критично)
```

### Coder Output
```bash
# Архивация созданных скиллов
tar -czf backups/coder_output_$(date +%Y%m%d).tar.gz data/coder_output/
# Retention: 30 дней
```

---

## Naming Conventions

### Agent IDs
- Format: `{type}` для синглтонов или `{type}_{number}` для множественных
- Examples: `orchestrator`, `coder`, `blogger_01`, `blogger_02`
- Правила: lowercase, snake_case, уникальные

### Task IDs
- Format: UUID v4
- Example: `550e8400-e29b-41d4-a716-446655440000`

### Skill Names
- Format: lowercase, snake_case, описательные
- Examples: `parse_website`, `search_web`, `send_telegram_message`
- Правила: глагол + существительное, понятные

### Log Actions
- Format: lowercase, snake_case, {noun}_{verb_past}
- Examples: `task_started`, `skill_executed`, `message_sent`, `llm_call`

### Config Files
- Format: lowercase, snake_case
- Examples: `base_instructions.yaml`, `providers.yaml`

---

## Dependencies Management

### Python (pyproject.toml)

```toml
[project]
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.2.0",
    "httpx>=0.27.0",
    "aio-pika>=9.4.0",
    "python-telegram-bot>=21.0",
    "psycopg[binary]>=3.1.0",
    "redis>=5.0.0",
    "qdrant-client>=1.8.0",
    "pyyaml>=6.0",
    "tiktoken>=0.6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "pre-commit>=3.8.0",
    "ruff>=0.6.0",
]
```

### Node.js (frontend package.json)

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.22.0",
    "zustand": "^4.5.0",
    "@tanstack/react-query": "^5.28.0",
    "recharts": "^2.12.0",
    "sonner": "^1.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

---

## Security Considerations

### Sensitive Data

**НЕ коммитить в git**:
- `.env` файлы с реальными ключами
- `data/` директория (логи, БД, output)
- API keys и токены
- Backup файлы

**Коммитить**:
- `.env.example` с примерами
- Структуру директорий (`data/.gitkeep`)
- Конфиги без секретов

### File Paths Security

```python
# В скилле write_file
ALLOWED_PATHS = [
    "/data/coder_output/**",
    "/tmp/**"
]

def validate_path(path: str) -> bool:
    """Проверка что путь разрешен"""
    abs_path = os.path.abspath(path)
    return any(fnmatch.fnmatch(abs_path, pattern) for pattern in ALLOWED_PATHS)
```

### Command Execution Security

```python
# В скилле execute_command
ALLOWED_COMMANDS = [
    "pytest",
    "python",
    "ls",
    "cat",
    "grep",
    "head",
    "tail"
]

def validate_command(command: str) -> bool:
    """Проверка что команда в whitelist"""
    cmd_name = command.split()[0]
    return cmd_name in ALLOWED_COMMANDS
```

---

## Migration Strategy

При изменении схемы БД:

```python
# scripts/migrations/001_initial_schema.sql
# scripts/migrations/002_add_correlation_id.sql
# ...

# scripts/migrate.py
def run_migrations():
    """Применяет непримененные миграции"""
    # Читает версию из БД
    # Применяет миграции по порядку
    # Обновляет версию
```

Пока для MVP: простая инициализация через `init_db.py`. Миграции - в будущем.
