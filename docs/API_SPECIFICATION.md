# API Specification

## Memory Service API

**Base URL**: `http://localhost:8100` (dev) / `http://memory-service:8100` (prod)

### Health Check

```http
GET /health
Response: 200 OK
{
  "status": "healthy",
  "redis": "connected",
  "postgres": "connected",
  "qdrant": "connected"
}
```

### Context (Fast Memory - Redis)

#### Set Context

```http
POST /api/v1/context/{agent_id}
Content-Type: application/json

Body:
{
  "key": "current_task_context",
  "value": {"files": ["main.py", "utils.py"], "step": 3},
  "ttl": 3600
}

Response: 200 OK
{
  "status": "ok",
  "key": "current_task_context",
  "expires_at": "2026-03-26T16:30:00Z"
}
```

#### Get Context

```http
GET /api/v1/context/{agent_id}/{key}

Response: 200 OK
{
  "key": "current_task_context",
  "value": {"files": ["main.py", "utils.py"], "step": 3},
  "ttl_remaining": 2850
}

Response: 404 Not Found (если ключ не найден или expired)
{
  "detail": "Key not found or expired"
}
```

#### Delete Context

```http
DELETE /api/v1/context/{agent_id}/{key}

Response: 200 OK
{
  "status": "deleted"
}
```

### History (Conversation)

#### Add to History

```http
POST /api/v1/history/{agent_id}
Content-Type: application/json

Body:
{
  "role": "user",
  "content": "Create a skill for parsing",
  "metadata": {"task_id": "abc-123"}
}

Response: 200 OK
{
  "status": "ok",
  "history_length": 15
}
```

#### Get History

```http
GET /api/v1/history/{agent_id}?limit=50

Response: 200 OK
{
  "messages": [
    {
      "role": "assistant",
      "content": "I'll create the skill...",
      "metadata": {"task_id": "abc-123"},
      "timestamp": "2026-03-26T15:30:00Z"
    },
    {
      "role": "user",
      "content": "Create a skill for parsing",
      "metadata": {},
      "timestamp": "2026-03-26T15:29:45Z"
    }
  ],
  "total": 2
}
```

### Long-term Memory (Qdrant)

#### Store Memory

```http
POST /api/v1/memory
Content-Type: application/json

Body:
{
  "agent_id": "coder",
  "content": "Successfully created skill parse_hackernews. Used BeautifulSoup for parsing. Tests passed on first try.",
  "scope": "personal",
  "metadata": {
    "task_id": "abc-123",
    "skill_name": "parse_hackernews",
    "tags": ["skill", "parsing", "beautifulsoup"],
    "success": true,
    "tokens_used": 5234
  }
}

Response: 201 Created
{
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "stored"
}
```

#### Search Memory

```http
POST /api/v1/memory/search
Content-Type: application/json

Body:
{
  "agent_id": "coder",
  "query": "how did I parse websites before",
  "scope": "personal",
  "limit": 5
}

Response: 200 OK
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "content": "Successfully created skill parse_hackernews...",
      "score": 0.89,
      "metadata": {
        "task_id": "abc-123",
        "skill_name": "parse_hackernews",
        "tags": ["skill", "parsing"]
      },
      "timestamp": "2026-03-26T15:32:00Z"
    }
  ],
  "total": 1
}
```

### Agent State (PostgreSQL)

#### Get All Agents

```http
GET /api/v1/agents

Response: 200 OK
{
  "agents": [
    {
      "agent_id": "orchestrator",
      "name": "Orchestrator",
      "status": "idle",
      "current_task_id": null,
      "current_model": "anthropic/claude-3.5-sonnet",
      "last_activity": "2026-03-26T15:35:00Z",
      "tokens_used_today": 5234,
      "tokens_used_hour": 1234
    },
    {
      "agent_id": "coder",
      "name": "Coder Agent",
      "status": "working",
      "current_task_id": "abc-123",
      "current_model": "anthropic/claude-3.5-sonnet",
      "last_activity": "2026-03-26T15:35:02Z",
      "tokens_used_today": 12450,
      "tokens_used_hour": 3200
    }
  ]
}
```

#### Get Agent Status

```http
GET /api/v1/agents/{agent_id}/status

Response: 200 OK
{
  "agent_id": "coder",
  "name": "Coder Agent",
  "status": "working",
  "current_task": {
    "id": "abc-123",
    "description": "Create skill for parsing HackerNews",
    "started_at": "2026-03-26T15:30:00Z",
    "progress": "Running tests..."
  },
  "tokens": {
    "today": 12450,
    "today_limit": 100000,
    "hour": 3200,
    "hour_limit": 15000,
    "percentage_used": 12.45
  },
  "last_activity": "2026-03-26T15:35:02Z"
}
```

### Tasks

#### Create Task

```http
POST /api/v1/tasks
Content-Type: application/json

Body:
{
  "agent_id": "coder",
  "description": "Create skill for parsing HackerNews",
  "payload": {
    "requirements": "Use requests and BeautifulSoup",
    "priority": "normal"
  },
  "created_by": "orchestrator"
}

Response: 201 Created
{
  "task_id": "abc-123",
  "status": "pending",
  "created_at": "2026-03-26T15:30:00Z"
}
```

#### Get Task

```http
GET /api/v1/tasks/{task_id}

Response: 200 OK
{
  "id": "abc-123",
  "agent_id": "coder",
  "description": "Create skill for parsing HackerNews",
  "status": "completed",
  "result": {
    "skill_name": "parse_hackernews",
    "output_path": "/data/coder_output/skills/parse_hackernews",
    "tests_passed": true
  },
  "created_at": "2026-03-26T15:30:00Z",
  "started_at": "2026-03-26T15:30:05Z",
  "completed_at": "2026-03-26T15:32:10Z",
  "duration_ms": 125000,
  "tokens_used": 5234
}
```

#### List Tasks

```http
GET /api/v1/tasks?agent_id=coder&status=completed&limit=10&offset=0

Response: 200 OK
{
  "tasks": [...],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

### Logs

#### Query Logs

```http
GET /api/v1/logs?agent_id=coder&action=llm_call&limit=100&offset=0

Response: 200 OK
{
  "logs": [
    {
      "id": 12345,
      "agent_id": "coder",
      "timestamp": "2026-03-26T15:30:05Z",
      "action": "llm_call",
      "parameters": {"model": "claude-3.5-sonnet", "messages": [...]},
      "result": {"tokens": 1456},
      "status": "success",
      "duration_ms": 2500,
      "task_id": "abc-123"
    }
  ],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

### Token Statistics

#### Get Token Stats

```http
GET /api/v1/tokens/stats?period=today

Response: 200 OK
{
  "period": "today",
  "by_agent": [
    {
      "agent_id": "coder",
      "total_tokens": 12450,
      "total_cost": 0.23,
      "num_calls": 15,
      "models_used": ["claude-3.5-sonnet", "gpt-4-turbo"]
    },
    {
      "agent_id": "orchestrator",
      "total_tokens": 5234,
      "total_cost": 0.11,
      "num_calls": 8,
      "models_used": ["claude-3.5-sonnet"]
    }
  ],
  "total_tokens": 17684,
  "total_cost": 0.34,
  "chart_data": [
    {"hour": "00:00", "tokens": 0},
    {"hour": "01:00", "tokens": 0},
    ...
    {"hour": "15:00", "tokens": 8234},
    {"hour": "16:00", "tokens": 3450}
  ]
}
```

---

## Skills Registry API

**Base URL**: `http://localhost:8101` (dev) / `http://skills-registry:8101` (prod)

### List All Skills

```http
GET /api/v1/skills

Response: 200 OK
{
  "skills": [
    {
      "name": "search_web",
      "description": "Search the web using a search API",
      "version": "1.0.0",
      "parameters": [...],
      "permissions": ["network", "api_call"],
      "tags": ["search", "web"]
    },
    ...
  ],
  "total": 6
}
```

### Get Skill Details

```http
GET /api/v1/skills/{skill_name}

Response: 200 OK
{
  "name": "search_web",
  "description": "Search the web using a search API",
  "version": "1.0.0",
  "author": "system",
  "created_at": "2026-03-26T10:00:00Z",
  "parameters": [
    {
      "name": "query",
      "type": "string",
      "required": true,
      "description": "Search query"
    },
    {
      "name": "num_results",
      "type": "integer",
      "required": false,
      "default": 5
    }
  ],
  "returns": {
    "type": "list",
    "description": "List of search results"
  },
  "implementation": "shared/skills/search_web.py",
  "permissions": ["network", "api_call"],
  "constraints": {
    "timeout": 30,
    "max_retries": 3
  },
  "tags": ["search", "web"]
}
```

### Register New Skill

```http
POST /api/v1/skills
Content-Type: application/json

Body:
{
  "name": "parse_hackernews",
  "description": "Parse HackerNews front page",
  "version": "1.0.0",
  "author": "coder",
  "parameters": [...],
  "returns": {...},
  "implementation": "data/coder_output/skills/parse_hackernews/implementation.py",
  "permissions": ["network"],
  "constraints": {"timeout": 30},
  "tags": ["parsing", "hackernews"]
}

Response: 201 Created
{
  "status": "registered",
  "skill_name": "parse_hackernews"
}
```

### Get Skills for Agent

```http
GET /api/v1/agents/{agent_id}/skills

Response: 200 OK
{
  "agent_id": "coder",
  "skills": [
    {"name": "read_file", "description": "..."},
    {"name": "write_file", "description": "..."},
    ...
  ]
}
```

---

## Web Backend API

**Base URL**: `http://localhost:8200` (dev) / `http://web-backend:8200` (prod)

### Authentication

#### Login

```http
POST /api/auth/login
Content-Type: application/json

Body:
{
  "token": "your-secret-token"
}

Response: 200 OK
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400
}

Response: 401 Unauthorized
{
  "detail": "Invalid token"
}
```

**Использование**:
```http
Все защищенные endpoints требуют заголовок:
Authorization: Bearer <access_token>
```

### Agents

#### List Agents

```http
GET /api/agents
Authorization: Bearer <token>

Response: 200 OK
{
  "agents": [
    {
      "agent_id": "orchestrator",
      "name": "Orchestrator",
      "status": "idle",
      "current_task": null,
      "tokens_today": 5234,
      "last_activity": "2026-03-26T15:35:00Z"
    },
    {
      "agent_id": "coder",
      "name": "Coder Agent",
      "status": "working",
      "current_task": {
        "id": "abc-123",
        "description": "Create skill...",
        "started_at": "2026-03-26T15:30:00Z"
      },
      "tokens_today": 12450,
      "last_activity": "2026-03-26T15:35:02Z"
    }
  ]
}
```

#### Get Agent Details

```http
GET /api/agents/{agent_id}
Authorization: Bearer <token>

Response: 200 OK
{
  "agent_id": "coder",
  "name": "Coder Agent",
  "description": "Agent for writing Python code and skills",
  "status": "working",
  "current_task": {...},
  "skills": [
    {"name": "read_file", "description": "..."},
    ...
  ],
  "tokens": {
    "today": 12450,
    "today_limit": 100000,
    "today_percentage": 12.45,
    "hour": 3200,
    "hour_limit": 15000,
    "hour_percentage": 21.33,
    "cost_today": 0.23
  },
  "config": {
    "current_model": "anthropic/claude-3.5-sonnet",
    "fallback_models": [...]
  },
  "last_activity": "2026-03-26T15:35:02Z",
  "uptime_seconds": 9234
}
```

#### Create Task for Agent

```http
POST /api/agents/{agent_id}/task
Authorization: Bearer <token>
Content-Type: application/json

Body:
{
  "description": "Create skill for parsing HackerNews",
  "priority": "normal"
}

Response: 201 Created
{
  "task_id": "abc-123",
  "status": "pending",
  "created_at": "2026-03-26T15:30:00Z",
  "message": "Task created and sent to agent"
}
```

#### Stop Agent Task

```http
POST /api/agents/{agent_id}/stop
Authorization: Bearer <token>

Response: 200 OK
{
  "status": "stopped",
  "message": "Agent task stopped"
}
```

#### Change Agent Model

```http
POST /api/agents/{agent_id}/model
Authorization: Bearer <token>
Content-Type: application/json

Body:
{
  "model": "openrouter/openai/gpt-4-turbo"
}

Response: 200 OK
{
  "status": "updated",
  "old_model": "anthropic/claude-3.5-sonnet",
  "new_model": "openai/gpt-4-turbo"
}
```

### Logs

#### Query Logs

```http
GET /api/logs?agent_id=coder&action=llm_call&status=success&limit=100&offset=0&from=2026-03-26T00:00:00Z&to=2026-03-26T23:59:59Z
Authorization: Bearer <token>

Query Parameters:
  - agent_id: string (optional, filter by agent)
  - action: string (optional, filter by action type)
  - status: string (optional, "success" or "error")
  - task_id: uuid (optional, filter by task)
  - limit: integer (default 100, max 1000)
  - offset: integer (default 0)
  - from: ISO datetime (optional, start time)
  - to: ISO datetime (optional, end time)

Response: 200 OK
{
  "logs": [
    {
      "id": 12345,
      "agent_id": "coder",
      "timestamp": "2026-03-26T15:30:05Z",
      "action": "llm_call",
      "parameters": {
        "model": "claude-3.5-sonnet",
        "max_tokens": 8000
      },
      "result": {
        "tokens": 1456,
        "cost": 0.02
      },
      "status": "success",
      "duration_ms": 2500,
      "task_id": "abc-123"
    },
    ...
  ],
  "total": 150,
  "limit": 100,
  "offset": 0
}
```

### Tokens

#### Get Token Statistics

```http
GET /api/tokens/stats?period=today
Authorization: Bearer <token>

Query Parameters:
  - period: "today" | "yesterday" | "this_week" | "this_month"
  - agent_id: string (optional, filter by agent)

Response: 200 OK
{
  "period": "today",
  "date": "2026-03-26",
  "by_agent": [
    {
      "agent_id": "coder",
      "total_tokens": 12450,
      "total_cost": 0.23,
      "num_calls": 15,
      "models_used": {
        "anthropic/claude-3.5-sonnet": {
          "calls": 14,
          "tokens": 12200,
          "cost": 0.22
        },
        "openai/gpt-4-turbo": {
          "calls": 1,
          "tokens": 250,
          "cost": 0.01
        }
      },
      "limit_daily": 100000,
      "percentage": 12.45
    },
    {
      "agent_id": "orchestrator",
      "total_tokens": 5234,
      "total_cost": 0.11,
      "num_calls": 8,
      "models_used": {...},
      "limit_daily": 100000,
      "percentage": 5.23
    }
  ],
  "total_tokens": 17684,
  "total_cost": 0.34,
  "chart_data": [
    {"hour": "00:00", "tokens": 0, "cost": 0},
    {"hour": "01:00", "tokens": 0, "cost": 0},
    ...
    {"hour": "15:00", "tokens": 8234, "cost": 0.15},
    {"hour": "16:00", "tokens": 3450, "cost": 0.06}
  ]
}
```

### Chat

#### Send Message to Agent

```http
POST /api/chat/message
Authorization: Bearer <token>
Content-Type: application/json

Body:
{
  "agent_id": "coder",
  "message": "Create a skill for parsing HackerNews"
}

Response: 200 OK
{
  "message_id": "def-456",
  "status": "sent",
  "agent_response": "I'll create that skill. Starting now..."
}
```

#### Get Chat History

```http
GET /api/chat/history?agent_id=coder&limit=50
Authorization: Bearer <token>

Response: 200 OK
{
  "messages": [
    {
      "id": "def-456",
      "from": "user",
      "to": "coder",
      "content": "Create a skill for parsing HackerNews",
      "timestamp": "2026-03-26T15:30:00Z"
    },
    {
      "id": "def-457",
      "from": "coder",
      "to": "user",
      "content": "I'll create that skill. Starting now...",
      "timestamp": "2026-03-26T15:30:02Z"
    }
  ]
}
```

---

## WebSocket API

**URL**: `ws://localhost:8200/ws` (dev) / `wss://your-domain.com/ws` (prod)

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8200/ws?token=<access_token>');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleEvent(data);
};
```

### Event Types

#### agent_status_changed

```json
{
  "type": "agent_status_changed",
  "data": {
    "agent_id": "coder",
    "old_status": "idle",
    "new_status": "working",
    "task_id": "abc-123"
  },
  "timestamp": "2026-03-26T15:30:00Z"
}
```

#### new_log_entry

```json
{
  "type": "new_log_entry",
  "data": {
    "agent_id": "coder",
    "action": "skill_executed",
    "skill": "write_file",
    "status": "success",
    "duration_ms": 45
  },
  "timestamp": "2026-03-26T15:30:05Z"
}
```

#### task_created

```json
{
  "type": "task_created",
  "data": {
    "task_id": "abc-123",
    "agent_id": "coder",
    "description": "Create skill...",
    "created_by": "user"
  },
  "timestamp": "2026-03-26T15:30:00Z"
}
```

#### task_completed

```json
{
  "type": "task_completed",
  "data": {
    "task_id": "abc-123",
    "agent_id": "coder",
    "status": "completed",
    "duration_ms": 125000,
    "summary": "Created skill parse_hackernews successfully"
  },
  "timestamp": "2026-03-26T15:32:10Z"
}
```

#### token_alert

```json
{
  "type": "token_alert",
  "data": {
    "agent_id": "coder",
    "level": "warning",
    "percentage": 85,
    "tokens_used": 85000,
    "limit": 100000,
    "message": "Agent approaching daily token limit (85%)"
  },
  "timestamp": "2026-03-26T15:35:00Z"
}
```

#### error

```json
{
  "type": "error",
  "data": {
    "agent_id": "coder",
    "error_type": "TaskExecutionError",
    "message": "Failed to create skill after 3 retries",
    "task_id": "abc-123"
  },
  "timestamp": "2026-03-26T15:35:00Z"
}
```

---

## RabbitMQ Message Protocol

### Exchanges

```python
# Direct exchange для целевых сообщений
EXCHANGE_DIRECT = "agents.direct"  # type: "direct"

# Fanout exchange для broadcast
EXCHANGE_BROADCAST = "agents.broadcast"  # type: "fanout"
```

### Queues

```python
# Очередь для каждого агента
QUEUE_PATTERN = "{agent_id}.tasks"

# Examples:
# - orchestrator.tasks
# - coder.tasks
```

### Routing

```python
# Direct message
routing_key = target_agent_id  # Например, "coder"
exchange = "agents.direct"

# Broadcast message
routing_key = ""  # Не используется для fanout
exchange = "agents.broadcast"
```

### Message Format (JSON)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "from_agent": "orchestrator",
  "to_agent": "coder",
  "type": "task",
  "payload": {
    "task_id": "abc-123",
    "description": "Create skill for parsing HackerNews",
    "requirements": "Use requests and BeautifulSoup"
  },
  "timestamp": "2026-03-26T15:30:00Z",
  "correlation_id": "abc-123"
}
```

### Message Types

| Type | Description | Example Payload |
|------|-------------|-----------------|
| `task` | Новая задача для агента | `{task_id, description}` |
| `response` | Ответ на предыдущее сообщение | `{correlation_id, result}` |
| `notification` | Уведомление (не требует ответа) | `{message, level}` |
| `query` | Запрос информации | `{query, params}` |
| `status` | Обновление статуса | `{status, current_task}` |

### Acknowledgments

```python
# Агент должен подтвердить получение сообщения
channel.basic_ack(delivery_tag=method.delivery_tag)

# Если агент не может обработать - reject с requeue
channel.basic_reject(delivery_tag=method.delivery_tag, requeue=True)
```

---

## Skills Execution Protocol

### Request Flow

```
1. Agent → Skills Registry: "execute skill X with params Y"
2. Registry → validates parameters
3. Registry → checks permissions
4. Registry → loads implementation module
5. Registry → executes function
6. Registry → returns result
```

### Skill Function Signature

```python
# Каждый скилл - это async функция с такой сигнатурой:

async def skill_function(
    context: SkillContext,  # Контекст выполнения
    **params  # Параметры из YAML
) -> Any:
    """Docstring"""
    # Implementation
    return result

class SkillContext:
    """Контекст доступный скиллу"""
    agent_id: str
    task_id: Optional[UUID]
    logger: Logger

    # Для скиллов с network permission
    http_client: Optional[httpx.AsyncClient] = None

    # Для скиллов с execute permission
    max_execution_time: int = 30
```

### Example: write_file skill

```python
# shared/skills/file_operations.py

async def write_file(
    context: SkillContext,
    path: str,
    content: str
) -> dict:
    """
    Write content to a file.

    Args:
        path: File path (must be in allowed paths)
        content: Content to write

    Returns:
        {"status": "success", "path": path, "size": bytes_written}

    Raises:
        PermissionError: If path not in allowed paths
        IOError: If write fails
    """
    # Validate path
    if not validate_path(path):
        raise PermissionError(f"Path not allowed: {path}")

    # Write file
    abs_path = os.path.abspath(path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, 'w', encoding='utf-8') as f:
        f.write(content)

    size = len(content.encode('utf-8'))

    context.logger.info(f"Wrote {size} bytes to {path}")

    return {
        "status": "success",
        "path": abs_path,
        "size": size
    }
```

---

## Error Responses

Все API следуют единому формату ошибок:

```json
{
  "detail": "Human readable error message",
  "error_code": "SPECIFIC_ERROR_CODE",
  "timestamp": "2026-03-26T15:30:00Z",
  "request_id": "req-12345"
}
```

### HTTP Status Codes

| Code | Meaning | When to use |
|------|---------|-------------|
| 200 | OK | Успешный запрос |
| 201 | Created | Ресурс создан (task, memory) |
| 400 | Bad Request | Невалидные параметры |
| 401 | Unauthorized | Невалидный token |
| 403 | Forbidden | Недостаточно permissions |
| 404 | Not Found | Ресурс не найден |
| 409 | Conflict | Конфликт (например, skill уже существует) |
| 422 | Unprocessable Entity | Валидация Pydantic не прошла |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Ошибка сервера |
| 503 | Service Unavailable | Сервис недоступен |

### Error Codes

```
AUTH_INVALID_TOKEN
AUTH_TOKEN_EXPIRED
AGENT_NOT_FOUND
AGENT_BUSY
TASK_NOT_FOUND
TASK_ALREADY_COMPLETED
SKILL_NOT_FOUND
SKILL_INVALID_PARAMS
SKILL_PERMISSION_DENIED
MEMORY_STORE_FAILED
TOKEN_LIMIT_EXCEEDED
RATE_LIMIT_EXCEEDED
LLM_API_ERROR
```

---

## Rate Limiting

### Web API Rate Limits

```
Per IP:
  - 100 requests per minute
  - 1000 requests per hour

Per authenticated user:
  - 300 requests per minute
  - 3000 requests per hour

Response при превышении:
429 Too Many Requests
{
  "detail": "Rate limit exceeded",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 60
}
```

### Agent LLM Rate Limits

```python
# В конфиге провайдера
rate_limits:
  llm_calls_per_minute: 10
  llm_calls_per_hour: 100
  embeddings_per_minute: 20
```

---

## Pagination

Все list endpoints поддерживают пагинацию:

```http
GET /api/logs?limit=100&offset=0

Response:
{
  "data": [...],
  "total": 1500,
  "limit": 100,
  "offset": 0,
  "has_more": true,
  "next_offset": 100
}
```

---

## Versioning

API версионируется через URL:
- Current: `/api/v1/...`
- Future: `/api/v2/...`

При breaking changes создается новая версия, старая поддерживается минимум 3 месяца.

---

## API Documentation

Все FastAPI сервисы автоматически генерируют OpenAPI документацию:

```
Memory Service:     http://localhost:8100/docs
Skills Registry:    http://localhost:8101/docs
Web Backend:        http://localhost:8200/docs
```

В production docs можно отключить или защитить паролем.
