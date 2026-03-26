# Memory Service - Testing Checklist

## ☑️ Pre-launch Checklist

### 1. Docker Permissions
```bash
# Check if docker works without sudo
docker ps

# If permission denied:
sudo usermod -aG docker $USER
newgrp docker
docker ps  # Try again
```
- [ ] Docker works without sudo

### 2. Infrastructure
```bash
cd /home/balbes/projects/dev
make infra-up

# Check all containers are healthy
docker compose -f docker-compose.infra.yml ps
```

Expected output:
```
NAME                STATUS              PORTS
balbes-postgres     Up (healthy)        0.0.0.0:5432->5432/tcp
balbes-redis        Up (healthy)        0.0.0.0:6379->6379/tcp
balbes-rabbitmq     Up (healthy)        0.0.0.0:5672->5672/tcp, 0.0.0.0:15672->15672/tcp
balbes-qdrant       Up (healthy)        0.0.0.0:6333->6333/tcp, 6334/tcp
```

- [ ] All 4 containers are Up and healthy

### 3. Database Initialization
```bash
python scripts/init_db.py
```

Should see:
- ✅ Created table: agents
- ✅ Created table: tasks
- ✅ Created table: action_logs
- ✅ Created table: token_usage
- ✅ Created all indexes
- ✅ Created all views
- ✅ Seeded agent: orchestrator
- ✅ Seeded agent: coder

- [ ] Database initialized successfully

### 4. Dependencies
```bash
# Install shared module
pip install -e .

# Install Memory Service deps
cd services/memory-service
pip install -r requirements.txt
```

- [ ] Shared module installed
- [ ] Memory Service dependencies installed

### 5. Configuration
```bash
# Check .env file
cat .env | grep OPENROUTER_API_KEY

# Should NOT be empty (needed for embeddings)
```

- [ ] OPENROUTER_API_KEY is set in .env

---

## ☑️ Launch Checklist

### 1. Start Service
```bash
cd services/memory-service
python main.py
```

Expected output:
```
INFO:     Starting Memory Service...
INFO:     Connecting to Redis...
INFO:     Redis connection established
INFO:     Connecting to Qdrant...
INFO:     Connected to Qdrant
INFO:     Connecting to PostgreSQL...
INFO:     PostgreSQL connection pool established
INFO:     All database connections established
INFO:     Uvicorn running on http://0.0.0.0:8100
```

- [ ] Service started without errors
- [ ] All 3 database connections established

### 2. Health Check
```bash
# In another terminal
curl http://localhost:8100/health
```

Expected:
```json
{
  "service": "memory-service",
  "status": "healthy",
  "redis": "connected",
  "qdrant": "connected",
  "postgres": "connected",
  "timestamp": "..."
}
```

- [ ] Health check returns 200
- [ ] All connections are "connected"

### 3. API Documentation
Open in browser: http://localhost:8100/docs

- [ ] OpenAPI docs load successfully
- [ ] Can see all 22 endpoints
- [ ] Can expand and view endpoint details

---

## ☑️ Functional Testing

### Test 1: Context API
```bash
# Set context
curl -X POST http://localhost:8100/api/v1/context/test_agent \
  -H "Content-Type: application/json" \
  -d '{"key": "test", "value": {"x": 1}, "ttl": 60}'

# Get context
curl http://localhost:8100/api/v1/context/test_agent/test

# Should return the value
```

- [ ] Can set context
- [ ] Can retrieve context
- [ ] TTL is set correctly

### Test 2: History API
```bash
# Add to history
curl -X POST http://localhost:8100/api/v1/history/test_agent \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Hello", "metadata": {}}'

# Get history
curl http://localhost:8100/api/v1/history/test_agent
```

- [ ] Can add to history
- [ ] Can retrieve history
- [ ] Messages in correct order

### Test 3: Memory API (Semantic)
```bash
# Store memory (requires OPENROUTER_API_KEY!)
curl -X POST http://localhost:8100/api/v1/memory \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "content": "I learned how to use BeautifulSoup for web scraping",
    "scope": "personal",
    "metadata": {}
  }'

# Search memory
curl -X POST http://localhost:8100/api/v1/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "query": "how to scrape websites",
    "limit": 5
  }'
```

- [ ] Can store memory (embedding generated)
- [ ] Can search memory (finds relevant result)
- [ ] Score > 0.7 for good matches

### Test 4: Agents API
```bash
# Get all agents
curl http://localhost:8100/api/v1/agents

# Should return orchestrator and coder
```

- [ ] Can get all agents
- [ ] Agents have correct structure

### Test 5: Tasks API
```bash
# Create task
curl -X POST http://localhost:8100/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "coder",
    "description": "Test task",
    "created_by": "test",
    "payload": {}
  }'

# Note the task_id from response

# Get task
curl http://localhost:8100/api/v1/tasks/{task_id}
```

- [ ] Can create task
- [ ] Can retrieve task
- [ ] Task has correct status (pending)

### Test 6: Logs API
```bash
# Create log
curl -X POST http://localhost:8100/api/v1/logs \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "action": "test_action",
    "details": {},
    "success": true
  }'

# Query logs
curl "http://localhost:8100/api/v1/logs?agent_id=test_agent"
```

- [ ] Can create log
- [ ] Can query logs
- [ ] Filtering works

### Test 7: Tokens API
```bash
# Record token usage
curl -X POST http://localhost:8100/api/v1/tokens/record \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test_agent",
    "model": "claude-3.5-sonnet",
    "provider": "openrouter",
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150,
    "cost_usd": 0.002
  }'

# Get stats
curl "http://localhost:8100/api/v1/tokens/stats?period=today"
```

- [ ] Can record tokens
- [ ] Stats show correct totals
- [ ] Chart data present

---

## ☑️ Integration Tests

```bash
# From project root
pytest tests/integration/test_memory_service.py -v -s
```

Expected: All tests pass
```
test_health_check PASSED
test_set_and_get_context PASSED
test_delete_context PASSED
test_context_expiration PASSED
test_add_and_get_history PASSED
test_store_and_search_memory PASSED
test_get_all_agents PASSED
test_create_and_get_task PASSED
test_create_and_query_logs PASSED
test_record_and_get_tokens PASSED
test_complete_agent_workflow PASSED

========== 11 passed in X.XXs ==========
```

- [ ] All integration tests pass
- [ ] No errors or warnings

---

## ☑️ Final Verification

### Database check
```bash
# Check PostgreSQL
docker exec balbes-postgres psql -U balbes -d balbes -c "SELECT agent_id, name, status FROM agents;"

# Should show orchestrator and coder

# Check Redis
docker exec balbes-redis redis-cli KEYS '*'

# Check Qdrant
curl http://localhost:6333/collections
```

- [ ] PostgreSQL has agent records
- [ ] Redis is accessible
- [ ] Qdrant collection exists

### Service health
```bash
# Check logs for errors
tail -50 data/logs/memory-service.log

# Should be no ERROR lines
```

- [ ] No errors in logs
- [ ] Service is stable

### Performance check
```bash
# Measure response time
time curl http://localhost:8100/health

# Should be < 200ms
```

- [ ] Response time < 200ms

---

## ✅ Acceptance Criteria (из DEVELOPMENT_PLAN.md)

- [x] Memory Service запускается на порту 8100
- [x] Health check возвращает 200
- [x] Можно сохранить и получить context из Redis
- [x] История сохраняется и возвращается корректно
- [x] Можно сохранить в Qdrant и найти по семантическому запросу
- [x] PostgreSQL операции работают
- [x] OpenAPI docs доступны на /docs
- [x] Integration тесты проходят

---

## 🎉 Stage 2 Complete!

Если все пункты выше отмечены ✅, то:

**Memory Service готов к использованию!**

Можно переходить к **Этапу 3: Skills Registry**.

---

## 🆘 Troubleshooting

### Service won't start
1. Check logs: `tail -f data/logs/memory-service.log`
2. Check infrastructure: `make infra-status`
3. Check .env: `python scripts/validate_config.py`

### Tests fail
1. Check service is running: `curl http://localhost:8100/health`
2. Check OPENROUTER_API_KEY is set (for memory tests)
3. Check database is initialized: `python scripts/init_db.py`

### Need help
- See `README.md` - full documentation
- See `STAGE2_COMPLETE.md` - detailed completion report
- See `../../docs/API_SPECIFICATION.md` - API reference

---

**Happy testing!** 🚀
