# Memory Service

Memory management service for Balbes Multi-Agent System.

## Features

- **Fast Context Storage** (Redis) - Short-term context with TTL
- **Conversation History** (Redis) - Last 50 messages per agent
- **Semantic Memory** (Qdrant) - Long-term memory with vector search
- **Agent State** (PostgreSQL) - Agent status and configuration
- **Task Tracking** (PostgreSQL) - Task lifecycle and results
- **Action Logs** (PostgreSQL) - Detailed audit trail
- **Token Tracking** (PostgreSQL + Redis) - Usage statistics and budgets
- **Identity** (Redis) - `GET /api/v1/identity/resolve` maps `telegram` / `max` external ids to a stable canonical UUID; legacy per-user Redis keys are renamed on first resolve

## Architecture

```
Memory Service
├── main.py                 # FastAPI application
├── api/                    # API endpoints
│   ├── context.py          # Context endpoints (Redis)
│   ├── history.py          # History endpoints (Redis)
│   ├── memory.py           # Memory endpoints (Qdrant)
│   ├── agents.py           # Agent endpoints (PostgreSQL)
│   ├── tasks.py            # Task endpoints (PostgreSQL)
│   ├── logs.py             # Log endpoints (PostgreSQL)
│   ├── tokens.py           # Token endpoints (PostgreSQL + Redis)
│   └── identity.py         # Canonical user id (telegram / max → UUID)
└── clients/                # Database clients
    ├── redis_client.py     # Redis async client
    ├── qdrant_client.py    # Qdrant async client
    └── postgres_client.py  # PostgreSQL async client
```

## Prerequisites

### Infrastructure (must be running)

```bash
# From project root
make infra-up

# Or manually:
docker-compose -f docker-compose.infra.yml up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- RabbitMQ (port 5672, management UI: 15672)
- Qdrant (port 6333, web UI: 6334)

### Database initialization

```bash
# From project root
python scripts/init_db.py
```

This creates:
- All tables (agents, tasks, action_logs, token_usage)
- Indexes for performance
- Views for statistics
- Initial agent records (orchestrator, coder)

## Installation

```bash
cd services/memory-service

# Create virtual environment (optional)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install shared module (from project root)
cd ../..
pip install -e .
```

## Configuration

Configuration is loaded from `.env` file in project root.

Key settings:
```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=balbes
POSTGRES_USER=balbes
POSTGRES_PASSWORD=your_password

REDIS_HOST=localhost
REDIS_PORT=6379

QDRANT_HOST=localhost
QDRANT_PORT=6333

OPENROUTER_API_KEY=your_key_here  # For embeddings

MEMORY_SERVICE_PORT=8100
LOG_LEVEL=INFO
```

## Running

### Development mode

```bash
cd services/memory-service
python main.py
```

Or with uvicorn directly:

```bash
cd services/memory-service
uvicorn main:app --reload --host 0.0.0.0 --port 8100
```

### Using Makefile (from project root)

```bash
make dev-memory
```

### Production mode

```bash
cd services/memory-service
uvicorn main:app --host 0.0.0.0 --port 8100 --workers 4
```

## API Documentation

Once running, visit:
- **Swagger UI**: http://localhost:8100/docs
- **ReDoc**: http://localhost:8100/redoc
- **Health check**: http://localhost:8100/health

## API Endpoints

### Health
- `GET /health` - Service health check

### Context (Fast Memory)
- `POST /api/v1/context/{agent_id}` - Store context with TTL
- `GET /api/v1/context/{agent_id}/{key}` - Retrieve context
- `DELETE /api/v1/context/{agent_id}/{key}` - Delete context

### History (Conversation)
- `POST /api/v1/history/{agent_id}` - Add message to history
- `GET /api/v1/history/{agent_id}` - Get conversation history
- `DELETE /api/v1/history/{agent_id}` - Clear history

### Memory (Semantic Search)
- `POST /api/v1/memory` - Store memory with vector embedding
- `POST /api/v1/memory/search` - Semantic search across memories
- `DELETE /api/v1/memory/{memory_id}` - Delete memory

### Agents
- `GET /api/v1/agents` - List all agents
- `GET /api/v1/agents/{agent_id}` - Get agent details
- `POST /api/v1/agents` - Create agent
- `PATCH /api/v1/agents/{agent_id}/status` - Update agent status
- `GET /api/v1/agents/{agent_id}/status` - Get detailed status

### Tasks
- `POST /api/v1/tasks` - Create task
- `GET /api/v1/tasks/{task_id}` - Get task details
- `GET /api/v1/tasks` - List tasks (with filters)
- `PATCH /api/v1/tasks/{task_id}` - Update task

### Logs
- `POST /api/v1/logs` - Create log entry
- `GET /api/v1/logs` - Query logs (with filters)

### Tokens
- `POST /api/v1/tokens/record` - Record token usage
- `GET /api/v1/tokens/stats` - Get statistics by period
- `GET /api/v1/tokens/agent/{agent_id}` - Get agent token usage

## Testing

### Unit tests

```bash
# From project root
pytest tests/unit/test_memory_service.py -v
```

### Integration tests

```bash
# Make sure infrastructure is running!
make infra-up

# Initialize database
python scripts/init_db.py

# Run Memory Service
cd services/memory-service && python main.py &

# Run tests
pytest tests/integration/test_memory_service.py -v -s
```

## Example Usage

### Python client example

```python
import httpx

BASE_URL = "http://localhost:8100"

async def example():
    async with httpx.AsyncClient() as client:
        # Store context
        response = await client.post(
            f"{BASE_URL}/api/v1/context/my_agent",
            json={
                "key": "current_task",
                "value": {"step": 3, "files": ["main.py"]},
                "ttl": 3600,
            },
        )
        print(response.json())

        # Get context
        response = await client.get(
            f"{BASE_URL}/api/v1/context/my_agent/current_task"
        )
        print(response.json())

        # Store memory
        response = await client.post(
            f"{BASE_URL}/api/v1/memory",
            json={
                "agent_id": "my_agent",
                "content": "Successfully completed task X using approach Y",
                "scope": "personal",
                "metadata": {"task_id": "123", "tags": ["success"]},
            },
        )
        print(response.json())

        # Search memory
        response = await client.post(
            f"{BASE_URL}/api/v1/memory/search",
            json={
                "agent_id": "my_agent",
                "query": "how did I complete tasks",
                "limit": 5,
            },
        )
        print(response.json())
```

### curl examples

```bash
# Health check
curl http://localhost:8100/health

# Set context
curl -X POST http://localhost:8100/api/v1/context/my_agent \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": {"x": 1}, "ttl": 60}'

# Get context
curl http://localhost:8100/api/v1/context/my_agent/test

# Get all agents
curl http://localhost:8100/api/v1/agents

# Get token stats
curl http://localhost:8100/api/v1/tokens/stats?period=today
```

## Troubleshooting

### Service won't start

1. Check infrastructure is running:
   ```bash
   docker ps
   # Should see: postgres, redis, rabbitmq, qdrant
   ```

2. Check database is initialized:
   ```bash
   python scripts/init_db.py
   ```

3. Check logs:
   ```bash
   tail -f data/logs/memory-service.log
   ```

### Redis connection failed

```bash
# Test Redis connection
redis-cli ping
# Should return: PONG

# Check Redis container
docker logs balbes-redis
```

### PostgreSQL connection failed

```bash
# Test PostgreSQL connection
psql -h localhost -U balbes -d balbes -c "SELECT 1"

# Check PostgreSQL container
docker logs balbes-postgres
```

### Qdrant connection failed

```bash
# Check Qdrant is running
curl http://localhost:6333/collections

# Check Qdrant logs
docker logs balbes-qdrant
```

### Embeddings generation failed

Make sure `OPENROUTER_API_KEY` is set in `.env` file. Embeddings are generated via OpenRouter API.

## Performance

- Redis operations: < 10ms
- PostgreSQL queries: < 50ms (with indexes)
- Qdrant search: 100-300ms (includes embedding generation)
- API response time: < 200ms (average)

## Monitoring

Health check endpoint provides status of all connections:

```bash
curl http://localhost:8100/health
```

Response:
```json
{
  "service": "memory-service",
  "status": "healthy",
  "redis": "connected",
  "qdrant": "connected",
  "postgres": "connected"
}
```

## Development

### Adding new endpoints

1. Create router in `api/` directory
2. Import in `main.py`
3. Include router: `app.include_router(router, prefix="/api/v1", tags=["tag"])`
4. Add tests in `tests/integration/`

### Code style

```bash
# Format code
ruff format .

# Lint
ruff check .

# Type check
mypy .
```

## Production Deployment

See [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) for production deployment guide.

Quick start:
```bash
# Build Docker image
docker build -t balbes-memory-service .

# Run container
docker run -d \
  --name memory-service \
  --env-file ../../.env \
  -p 8100:8100 \
  balbes-memory-service
```

## License

Part of Balbes Multi-Agent System.
