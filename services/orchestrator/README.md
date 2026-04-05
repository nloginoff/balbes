"""
Orchestrator Service - README and Documentation
"""

# Orchestrator Agent Service

The **Orchestrator** is the central coordination hub of the Balbes Multi-Agent System. It orchestrates task execution across multiple services and manages user interactions.

## Features

### 🎯 Core Functionality

- **Task Orchestration**: Receive user requests, find relevant skills, execute them
- **Memory Integration**: Maintain user context and task history via Memory Service
- **Skill Selection**: Semantic search across Skills Registry to find best matching skill
- **Real-time Notifications**: Push updates about task progress and completion
- **Telegram Integration**: Native Telegram bot for direct user interaction

### 🔧 Architecture

```
┌─────────────────────────────────────────────────────┐
│         Orchestrator Agent (Port 8102)              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐    ┌──────────────────┐          │
│  │ Telegram Bot │    │ Task Processor   │          │
│  └──────────────┘    └──────────────────┘          │
│         │                    │                      │
│         └────────┬───────────┘                      │
│                  │                                  │
│        ┌─────────┴──────────┐                      │
│        │                    │                      │
│   ┌─────────┐          ┌─────────────┐            │
│   │ Memory  │          │ Notification│            │
│   │Service  │          │ System      │            │
│   └─────────┘          └─────────────┘            │
│        │                    │                      │
│   ┌────┴────────────────────┴─────┐               │
│   │    Skills Registry             │               │
│   │   (Semantic Search)            │               │
│   └────────────────────────────────┘               │
│                                                    │
└─────────────────────────────────────────────────────┘
```

### 📊 Components

1. **OrchestratorAgent** (`agent.py`)
   - Coordinates task execution
   - Integrates with Memory Service
   - Queries Skills Registry
   - Manages context and results

2. **TelegramBot** (`telegram_bot.py` → реализация в `shared/telegram_app/balbes_bot.py`)
   - `/start` - Initialize conversation
   - `/help` - Show commands
   - `/status` - Check service status
   - `/clear` - Clear conversation history
   - Message handling for task submission

3. **NotificationService** (`notifications.py`)
   - Task lifecycle notifications
   - Skill execution updates
   - System alerts
   - Notification history and preferences

4. **API Endpoints** (`api/`)
   - Task management
   - Notification management
   - Status and health checks

## Quick Start

### 1. Setup

```bash
cd /home/balbes/projects/dev/services/orchestrator

# Create virtual environment (if not already done globally)
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Update `.env` in project root:

```env
# Orchestrator Service
ORCHESTRATOR_PORT=8102
LOG_LEVEL=INFO

# Telegram Bot (optional)
TELEGRAM_BOT_TOKEN=your_token_here

# Dependent services
MEMORY_SERVICE_PORT=8100
SKILLS_REGISTRY_PORT=8101
```

### 3. Run Orchestrator Service

```bash
# From project root
python -m services.orchestrator.main
```

The service will start on `http://localhost:8102`

### 4. Run Telegram Bot (Optional)

```bash
# In a separate terminal
python -m services.orchestrator.telegram_bot
```

## API Endpoints

### Task Management

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "user_id": "123456",
  "description": "What are the latest AI trends?"
}

Response:
{
  "task_id": "uuid",
  "status": "success",
  "result": {...},
  "skill_used": "SearchSkill",
  "duration_ms": 1234
}
```

### Notifications

```http
GET /api/v1/notifications/history?user_id=123&limit=10
```

```http
PUT /api/v1/notifications/{notification_id}/read
```

```http
DELETE /api/v1/notifications/user/{user_id}
```

### Status

```http
GET /health
GET /api/v1/status
```

## Usage Examples

### Python Client

```python
import httpx
import asyncio

async def submit_task():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8102/api/v1/tasks",
            json={
                "user_id": "user_123",
                "description": "Summarize Python best practices"
            }
        )
        result = response.json()
        print(f"Task completed: {result['status']}")
        print(f"Skill used: {result['skill_used']}")
        print(f"Result: {result['result']}")

asyncio.run(submit_task())
```

### cURL

```bash
curl -X POST http://localhost:8102/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "description": "What are Python decorators?"
  }'
```

### Telegram Bot

```
/start
Hello! I'm Balbes. What would you like me to help with?

You: Summarize machine learning basics
Bot: ⏳ Processing your request...
Bot: ✅ Task Completed
    📌 Task: Summarize machine learning basics
    🎯 Skill Used: SummarizationSkill
    📊 Result: Machine learning is...
    ⏱️ Duration: 2345ms

/status
✅ Orchestrator Status: ONLINE
🔗 Services:
- Memory Service: http://localhost:8100
- Skills Registry: http://localhost:8101
⏰ Timestamp: 2024-03-26T10:30:00Z
```

## Testing

Run integration tests:

```bash
# From project root
pytest tests/integration/test_orchestrator.py -v

# With output
pytest tests/integration/test_orchestrator.py -v -s

# Specific test
pytest tests/integration/test_orchestrator.py::test_agent_initialization -v
```

## Service Integration

### Memory Service Connection

The Orchestrator integrates with Memory Service for:

- **Context Retrieval** (`GET /api/v1/context/{user_id}`)
  - Get user conversation history
  - Retrieve saved preferences
  - Access long-term memory

- **Task Storage** (`POST /api/v1/memory`)
  - Save task results
  - Store execution logs
  - Maintain semantic memory

### Skills Registry Connection

The Orchestrator uses Skills Registry for:

- **Skill Search** (`POST /api/v1/skills/search`)
  - Find relevant skills for task
  - Get skill metadata
  - Rank by relevance

- **Skill Retrieval** (`GET /api/v1/skills/{skill_id}`)
  - Get full skill details
  - Load input/output schemas
  - Access implementation

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY services/orchestrator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/orchestrator/ ./
COPY shared/ ../shared/
COPY .env ../

EXPOSE 8102

CMD ["python", "-m", "main"]
```

### Docker Compose

```yaml
services:
  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8102:8102"
    environment:
      - LOG_LEVEL=INFO
      - ORCHESTRATOR_PORT=8102
    depends_on:
      - memory-service
      - skills-registry
    networks:
      - balbes_network
```

## Troubleshooting

### Service Connection Issues

```
ConnectionError: Failed to connect to Memory Service
→ Ensure Memory Service is running on port 8100
→ Check network connectivity between services
```

### Task Execution Failures

```
No relevant skills found
→ Check Skills Registry has at least one skill
→ Verify skill embeddings are properly indexed
```

### Telegram Bot Not Responding

```
Bot token not configured
→ Add TELEGRAM_BOT_TOKEN to .env
→ Restart bot process
```

## Development

### Adding New Notification Types

```python
# In notifications.py
class NotificationType(str, Enum):
    NEW_TYPE = "new_type"

async def notify_new_type(self, user_id, **kwargs):
    notification = Notification(
        user_id=user_id,
        notification_type=NotificationType.NEW_TYPE,
        title="Custom Title",
        message="Custom message",
        data={"custom": "data"}
    )
    await self.send_notification(notification)
```

### Extending Telegram Bot

```python
# In telegram_bot.py
async def cmd_custom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Custom command"""
    await update.message.reply_text("Response")

# In _setup_handlers()
self.app.add_handler(CommandHandler("custom", self.cmd_custom))
```

### Custom Task Processors

```python
# Extend OrchestratorAgent.execute_task
async def execute_task_custom(self, **kwargs):
    # Custom logic here
    return result
```

## Performance Metrics

Expected response times:

- Health check: `<10ms`
- Task execution: `100-3000ms` (depends on skill complexity)
- Notification creation: `<50ms`
- Skill search: `200-500ms`

## Next Steps

- [ ] Implement task queuing with RabbitMQ
- [ ] Add WebSocket support for real-time updates
- [ ] Multi-language support for Telegram bot
- [ ] Advanced user preference management
- [ ] Analytics dashboard

## Support

For issues or questions:
1. Check logs: `tail -f logs/orchestrator.log`
2. Review integration tests
3. Check service health endpoints
4. Verify .env configuration
