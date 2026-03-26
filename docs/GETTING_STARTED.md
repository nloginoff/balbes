# Getting Started

Пошаговое руководство для начала работы с Balbes Multi-Agent System.

---

## Для кого этот документ?

- 👨‍💻 Разработчик, который будет реализовывать систему
- 🤖 AI агент, который будет помогать в разработке
- 📖 Любой, кто хочет понять с чего начать

---

## Документация: С чего начать?

Рекомендуемый порядок чтения:

### 1. Общее понимание (15-20 минут)
1. **README.md** - краткий обзор проекта
2. **TECHNICAL_SPEC.md** - архитектура и концепция
3. **MVP_SCOPE.md** - что входит и не входит в MVP

### 2. Технические детали (30-40 минут)
4. **PROJECT_STRUCTURE.md** - организация файлов
5. **DATA_MODELS.md** - схемы БД и модели
6. **API_SPECIFICATION.md** - все API endpoints

### 3. Разработка (20-30 минут)
7. **AGENTS_GUIDE.md** - как работают агенты
8. **DEVELOPMENT_PLAN.md** - план реализации MVP
9. **CONFIGURATION.md** - все настройки

### 4. Практика (15-20 минут)
10. **EXAMPLES.md** - практические примеры
11. **QUICKSTART.md** - быстрый старт
12. **FAQ.md** - частые вопросы

### Справочные материалы
- **DEPLOYMENT.md** - деплой в production
- **ARCHITECTURE_DECISIONS.md** - почему выбрали те или иные решения

**Итого**: ~1.5-2 часа для полного понимания проекта.

---

## Preparation Checklist

Перед началом разработки убедитесь:

### Инструменты
- [ ] Python 3.13+ установлен
- [ ] Docker и Docker Compose установлены
- [ ] Node.js 18+ установлен (для frontend)
- [ ] Git настроен
- [ ] IDE готова (VS Code/Cursor рекомендуется)

### API ключи
- [ ] OpenRouter API key получен (https://openrouter.ai/)
- [ ] AiTunnel API key получен (или другой fallback)
- [ ] Telegram bot создан (@BotFather)
- [ ] Telegram user ID получен (@userinfobot)

### Доступы
- [ ] VPS доступен (для финального деплоя)
- [ ] SSH ключи настроены
- [ ] Domain/IP известен (для Web UI)

### Знания
- [ ] Базовое понимание asyncio (Python)
- [ ] Базовое понимание FastAPI
- [ ] Базовое понимание React (для frontend)
- [ ] Базовое понимание Docker
- [ ] Базовое понимание PostgreSQL

---

## Quick Setup (10 минут)

```bash
# 1. Перейти в проект
cd /home/balbes/projects/dev

# 2. Создать структуру
bash scripts/create_structure.sh

# 3. Скопировать примеры конфигов
cp config/providers.yaml.example config/providers.yaml
cp config/base_instructions.yaml.example config/base_instructions.yaml

# 4. Создать .env
cp .env.example .env

# ВАЖНО: Заполнить .env реальными значениями:
nano .env
# - OPENROUTER_API_KEY
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_USER_ID
# - WEB_AUTH_TOKEN (сгенерировать случайный: openssl rand -hex 32)
# - JWT_SECRET (сгенерировать случайный: openssl rand -hex 32)
# - POSTGRES_PASSWORD (сгенерировать: openssl rand -hex 16)

# 5. Валидация
python scripts/validate_config.py

# 6. Setup (инфраструктура + БД)
make setup

# 7. Готово! Теперь можно начинать разработку
```

---

## Архитектура в трех предложениях

1. **Агенты** - автономные AI сервисы, которые получают задачи, думают (LLM), выполняют действия (скиллы), и сообщают результаты.

2. **Инфраструктура** - RabbitMQ для коммуникации, PostgreSQL для данных, Redis для быстрой памяти, Qdrant для семантического поиска.

3. **Интерфейсы** - Telegram (быстрый доступ из любого места) и Web UI (детальный мониторинг и управление).

---

## Development Flow

### Этап 1: Core (первые 5 дней)

**Цель**: Создать базовую инфраструктуру

**Что делать**:
1. Реализовать Pydantic models (`shared/models.py`)
2. Реализовать MessageBus (`shared/message_bus.py`)
3. Реализовать LLMClient (`shared/llm_client.py`)
4. Реализовать BaseAgent (`shared/base_agent.py`)
5. Создать PostgreSQL schema (`scripts/init_db.py`)

**Критерий готовности**: Все unit тесты проходят

**Следующий шаг**: Этап 2 (Memory Service)

### Этап 2-3: Services (3-4 дня)

**Цель**: Сервисы для памяти и скиллов

**Что делать**:
1. Memory Service с API
2. Skills Registry с базовыми скиллами
3. Integration тесты

**Критерий готовности**: API работают, скиллы выполняются

**Следующий шаг**: Этап 4-5 (Агенты)

### Этап 4-5: Agents (4-5 дней)

**Цель**: Orchestrator и Coder агенты

**Что делать**:
1. Orchestrator с Telegram ботом
2. Coder с генерацией скиллов
3. E2E тесты

**Критерий готовности**: Можно создать скилл через Telegram

**Следующий шаг**: Этап 6-7 (Web UI)

### Этап 6-7: Web UI (3-4 дня)

**Цель**: Красивый веб-интерфейс

**Что делать**:
1. Backend API + WebSocket
2. React frontend
3. Integration

**Критерий готовности**: UI работает, real-time updates приходят

**Следующий шаг**: Этап 8-9 (Testing & Deploy)

### Этап 8-10: Final (3-4 дня)

**Цель**: Тестирование и деплой

**Что делать**:
1. E2E тесты всей системы
2. Bug fixes
3. Production deployment на VPS
4. Final testing

**Критерий готовности**: Система работает в production!

**Итого**: ~18-20 дней до MVP

---

## First Task: Hello World

После настройки базовой инфраструктуры, первая задача:

**Создать простейшего агента "Hello World"**:

```python
# services/hello/agent.py

from shared.base_agent import BaseAgent
from shared.models import Task, TaskResult

class HelloAgent(BaseAgent):
    async def execute_task(self, task: Task) -> TaskResult:
        """Simply echoes the task description"""

        await self.log_action("task_started", {"task_id": str(task.id)})

        # Simple LLM call
        response = await self.llm_complete([
            {"role": "user", "content": f"Say hello and repeat: {task.description}"}
        ])

        await self.log_action("task_completed", {
            "task_id": str(task.id),
            "response": response.content
        })

        return TaskResult(
            task_id=task.id,
            status="success",
            data={"response": response.content},
            tokens_used=response.total_tokens,
            duration_ms=response.duration_ms
        )
```

**Тест**:
```python
# Direct test без Telegram
import asyncio

async def test():
    agent = HelloAgent()
    await agent.start()

    task = Task(agent_id="hello", description="test message")
    result = await agent.execute_task(task)

    print(f"Result: {result}")

    await agent.stop()

asyncio.run(test())
```

Если это работает - инфраструктура готова! Можно переходить к реальным агентам.

---

## Daily Development Routine

### Начало дня

```bash
# 1. Pull последние изменения (если команда)
git pull

# 2. Активировать venv
source .venv/bin/activate

# 3. Проверить инфраструктуру
make infra-status

# 4. Если не running - поднять
make infra-up

# 5. Запустить сервисы которые нужны
# Обычно в разных терминалах:
make dev-memory
make dev-skills
# etc
```

### В течение дня

```bash
# Работа с кодом
# ... edit files ...

# Тестирование изменений
pytest tests/test_my_changes.py -v

# Проверка качества
ruff check .

# Commit
git add .
git commit -m "feat: my changes"
```

### Конец дня

```bash
# Запустить все тесты
make test

# Push changes
git push

# Остановить сервисы (или оставить на ночь)
# Ctrl+C в терминалах

# Оставить только инфраструктуру running
# (PostgreSQL, Redis, RabbitMQ, Qdrant)
```

---

## Key Files for Development

Во время разработки часто открываются:

### Core
- `shared/base_agent.py` - базовый класс агента
- `shared/llm_client.py` - LLM клиент
- `shared/message_bus.py` - RabbitMQ wrapper
- `shared/models.py` - все модели данных
- `shared/config.py` - конфигурация

### Configs
- `.env` - environment variables
- `config/providers.yaml` - LLM провайдеры
- `config/base_instructions.yaml` - общие инструкции
- `config/agents/*.yaml` - конфиги агентов

### Development
- `Makefile` - все команды
- `docker-compose.infra.yml` - БД для dev
- `pyproject.toml` - зависимости

### Documentation
- `docs/DEVELOPMENT_PLAN.md` - план и checklist
- `docs/API_SPECIFICATION.md` - справка по API
- `docs/EXAMPLES.md` - примеры кода

---

## Recommended IDE Setup

### VS Code / Cursor

**Extensions**:
- Python
- Pylance
- Ruff
- Docker
- YAML
- PostgreSQL
- ES7+ React/Redux snippets
- Tailwind CSS IntelliSense

**Settings** (.vscode/settings.json):
```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.enabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    ".pytest_cache": true,
    ".ruff_cache": true
  }
}
```

### Terminal Setup

Рекомендуется tmux или iTerm2 с split panes:

```
┌─────────────┬─────────────┬─────────────┐
│             │             │             │
│  Memory     │  Skills     │  Orch       │
│  Service    │  Registry   │             │
│             │             │             │
├─────────────┼─────────────┼─────────────┤
│             │             │             │
│  Coder      │  Web        │  Frontend   │
│             │  Backend    │             │
│             │             │             │
└─────────────┴─────────────┴─────────────┘
```

**Tmux setup**:
```bash
# Create session
tmux new -s balbes

# Split windows (Ctrl+B then %)
# Navigate (Ctrl+B then arrow keys)
# Detach (Ctrl+B then D)
# Attach back: tmux attach -t balbes
```

---

## Common Pitfalls

### 1. Забыли активировать venv

**Symptom**: `ModuleNotFoundError`

**Fix**:
```bash
source .venv/bin/activate
```

### 2. .env не заполнен

**Symptom**: `ValidationError` при загрузке Settings

**Fix**:
```bash
cp .env.example .env
nano .env  # Fill in real values
```

### 3. Инфраструктура не поднята

**Symptom**: Connection refused errors

**Fix**:
```bash
make infra-up
make infra-status  # Check all are healthy
```

### 4. Порты заняты

**Symptom**: "Port already in use"

**Fix**:
```bash
# Find process
lsof -i :8100

# Kill it
kill -9 <PID>

# Or change port in .env
```

### 5. Import errors

**Symptom**: `ImportError: cannot import shared`

**Fix**:
```bash
# Install in editable mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

---

## Development Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Development Cycle                         │
└─────────────────────────────────────────────────────────────┘

    Start Day
        ↓
    Pull latest code
        ↓
    Start infrastructure (make infra-up)
        ↓
    Start services (make dev-*)
        ↓
    ┌─────────────────────────┐
    │  Development Loop       │
    │                         │
    │  1. Write code         │
    │  2. Test (pytest)      │
    │  3. Fix bugs           │
    │  4. Repeat             │
    └─────────────────────────┘
        ↓
    Run full tests (make test)
        ↓
    Quality check (ruff, mypy)
        ↓
    Commit changes
        ↓
    Push to git
        ↓
    End Day
```

---

## Key Concepts to Understand

### 1. Async/Await
Все I/O операции асинхронные. Нужно понимать:
- `async def` для async функций
- `await` для async вызовов
- `asyncio.gather()` для параллельных операций
- Event loop и non-blocking I/O

**Ресурс**: https://docs.python.org/3/library/asyncio.html

### 2. Pydantic Models
Для валидации и type safety:
- Автоматическая валидация входных данных
- Type hints
- Serialization/deserialization (JSON)
- Settings management

**Ресурс**: https://docs.pydantic.dev/

### 3. FastAPI
Для создания API:
- Async endpoints
- Dependency injection
- Автоматическая OpenAPI docs
- WebSocket support

**Ресурс**: https://fastapi.tiangolo.com/

### 4. RabbitMQ
Для межагентной коммуникации:
- Exchanges (direct, fanout)
- Queues
- Routing keys
- Acknowledgments

**Ресурс**: https://www.rabbitmq.com/tutorials/tutorial-one-python.html

### 5. React + TypeScript
Для Web UI:
- Component-based architecture
- Hooks (useState, useEffect)
- State management (Zustand)
- Data fetching (TanStack Query)

**Ресурс**: https://react.dev/, https://ui.shadcn.com/

---

## Testing Strategy

### Unit Tests
**Что тестировать**:
- Pydantic models
- Utility functions
- Individual skills
- BaseAgent methods (mocked dependencies)

**Как**:
```bash
pytest tests/unit -v
```

### Integration Tests
**Что тестировать**:
- Memory Service API
- Skills Registry API
- Agent ↔ Service interactions
- Database operations

**Как**:
```bash
# Требует running infrastructure
make infra-up
pytest tests/integration -v
```

### E2E Tests
**Что тестировать**:
- Full workflow: Telegram → Orchestrator → Coder → Result
- Fallback mechanisms
- Token limit handling

**Как**:
```bash
# Requires all services running
pytest tests/e2e -v
```

---

## Debugging Tips

### Логи - ваш лучший друг

```bash
# Real-time logs
tail -f data/logs/coder.log | jq '.'

# Filter by action
cat data/logs/coder.log | jq 'select(.action == "llm_call")'

# Find errors
grep -r "ERROR" data/logs/*.log

# Last 20 errors
cat data/logs/*.log | jq 'select(.status == "error")' | tail -20
```

### Debugging Python

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or
breakpoint()

# Or use IDE debugger with launch.json
```

### Debugging RabbitMQ

```bash
# Management UI
open http://localhost:15672  # guest/guest

# Check queues
docker exec balbes-rabbitmq rabbitmqctl list_queues

# Check bindings
docker exec balbes-rabbitmq rabbitmqctl list_bindings
```

### Debugging Database

```bash
# PostgreSQL
make db-shell

# Redis
docker exec -it balbes-redis redis-cli
> KEYS *
> GET key

# Qdrant
curl http://localhost:6333/collections
```

---

## Resources

### Documentation
- All docs in `docs/` folder
- Start with QUICKSTART.md

### Examples
- Practical examples in EXAMPLES.md
- Code templates in each service README

### External
- [FastAPI docs](https://fastapi.tiangolo.com/)
- [Pydantic docs](https://docs.pydantic.dev/)
- [RabbitMQ tutorials](https://www.rabbitmq.com/getstarted.html)
- [React docs](https://react.dev/)
- [OpenRouter docs](https://openrouter.ai/docs)

---

## Next Steps

После прочтения этого документа:

1. **Setup environment**: Следовать Quick Setup выше
2. **Read architecture**: TECHNICAL_SPEC.md и PROJECT_STRUCTURE.md
3. **Start coding**: Следовать DEVELOPMENT_PLAN.md Этап 1
4. **Ask questions**: Использовать FAQ.md и EXAMPLES.md

**Готовы начать?** → См. DEVELOPMENT_PLAN.md для детального плана! 🚀
