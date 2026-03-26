# Quick Start Guide

Быстрый старт для разработки после настройки проекта.

---

## Первый запуск (5 минут)

### 1. Клонировать и настроить

```bash
cd /home/balbes/projects/dev

# Создать .env
cp .env.example .env
nano .env

# Заполнить минимум:
# - OPENROUTER_API_KEY
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_USER_ID
# - WEB_AUTH_TOKEN
# - POSTGRES_PASSWORD
```

### 2. Поднять инфраструктуру

```bash
make infra-up

# Проверка (все должны быть Up и healthy)
docker-compose -f docker-compose.infra.yml ps
```

### 3. Инициализировать базы

```bash
make db-init    # Создать PostgreSQL таблицы
make db-seed    # Загрузить базовые скиллы
```

### 4. Запустить сервисы

Открыть 6 терминалов (или использовать tmux):

```bash
# Terminal 1
make dev-memory

# Terminal 2
make dev-skills

# Terminal 3
make dev-orch

# Terminal 4
make dev-coder

# Terminal 5
make dev-web

# Terminal 6
make dev-frontend
```

### 5. Проверка

**Telegram**: Отправить `/start` боту → должен ответить

**Web UI**: Открыть http://localhost:5173 → залогиниться

✅ **Готово!** Система работает.

---

## Первая задача для Coder

```
Telegram:
/task @coder создай скилл для парсинга HackerNews. Должен возвращать топ-10 постов с заголовками и ссылками. Используй requests и beautifulsoup4.

Ожидать ~2 минуты

Результат:
✅ Скилл создан в /data/coder_output/skills/parse_hackernews/
```

---

## Ежедневный workflow

### Утро

```bash
# Проверить что инфраструктура работает
docker compose -f docker-compose.infra.yml ps

# Если нет - поднять
make infra-up

# Обновить код (если работаете в команде)
git pull

# Запустить сервисы (или они уже running)
```

### Разработка новой фичи

```bash
# Создать ветку
git checkout -b feature/my-feature

# Работать с кодом
# ... edit files ...

# Тестировать
pytest tests/test_my_feature.py -v

# Проверить качество
ruff check .
ruff format .

# Commit
git add .
git commit -m "feat: add my feature"

# Push
git push origin feature/my-feature
```

### Вечер

```bash
# Проверить что все работает
make test

# Остановить сервисы (если нужно)
# Ctrl+C в каждом терминале

# Или оставить running для фоновой работы
```

---

## Common Tasks

### Проверить статус системы

**Telegram**: `/status`

**CLI**:
```bash
./scripts/healthcheck.sh
```

**Web UI**: Dashboard page

### Посмотреть логи

**Telegram**: `/logs @agent 10`

**CLI**:
```bash
# Real-time
tail -f data/logs/coder.log | jq '.'

# Фильтр по action
cat data/logs/coder.log | jq 'select(.action == "llm_call")'

# Последние ошибки
cat data/logs/*.log | jq 'select(.status == "error")' | tail -10
```

**Web UI**: Agent Detail → Activity Log

### Создать задачу для агента

**Telegram**: `/task @agent описание`

**Web UI**: Chat page

**API** (для скриптов):
```bash
TOKEN="your-jwt-token"

curl -X POST http://localhost:8200/api/agents/coder/task \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Create skill for parsing GitHub trending",
    "priority": "normal"
  }'
```

### Проверить использование токенов

**Telegram**: `/tokens`

**CLI**:
```bash
psql -h localhost -U balbes -d balbes_agents -c "
SELECT * FROM v_tokens_today;
"
```

**Web UI**: Tokens page

### Сменить модель агента

**Telegram**: `/model @agent provider/model`

**Web UI**: Agent Detail → Change Model button

**CLI**:
```bash
psql -h localhost -U balbes -d balbes_agents -c "
UPDATE agents
SET current_model = 'openai/gpt-4-turbo'
WHERE id = 'coder';
"

# Потом restart агента
```

---

## Development Tips

### Hot Reload

**Backend** (FastAPI):
```bash
# uvicorn --reload автоматически перезагружает при изменениях
# Изменения в коде → сохранить → сервис автоматически reloads
```

**Frontend** (Vite):
```bash
# npm run dev с HMR (Hot Module Replacement)
# Изменения в React коде → браузер автоматически обновляется
```

**Shared code**: При изменении `shared/` нужно restart все зависимые сервисы.

### Debugging

**Python**:
```python
# Добавить breakpoint
import pdb; pdb.set_trace()

# Или
breakpoint()

# В VS Code/Cursor можно использовать debugger с launch.json
```

**React**:
```javascript
// Browser DevTools
console.log(data);
debugger;  // Breakpoint

// React DevTools extension
```

### Testing

```bash
# Все тесты
make test

# Конкретный файл
pytest tests/unit/test_base_agent.py -v

# Конкретный тест
pytest tests/unit/test_base_agent.py::test_execute_skill -v

# С coverage
pytest --cov=shared --cov-report=html
open htmlcov/index.html
```

### Code Quality

```bash
# Проверка
ruff check .

# Автофикс
ruff check --fix .

# Форматирование
ruff format .

# Pre-commit (все hooks)
pre-commit run --all-files
```

---

## Useful Commands Cheatsheet

### Docker

```bash
# Статус всех контейнеров
docker ps

# Логи
docker compose logs -f <service>

# Exec в контейнер
docker compose exec <service> sh

# Restart
docker compose restart <service>

# Rebuild
docker compose build <service>

# Проверка ресурсов
docker stats
```

### Database

```bash
# PostgreSQL
psql -h localhost -U balbes -d balbes_agents

# Redis
redis-cli
> KEYS *
> GET context:coder:current_task_state

# RabbitMQ Management
open http://localhost:15672
# guest / guest

# Qdrant Dashboard
open http://localhost:6333/dashboard
```

### Git

```bash
# Статус
git status

# Создать ветку
git checkout -b feature/name

# Commit
git add .
git commit -m "feat: description"

# Push
git push origin feature/name

# Switch back to main
git checkout main
```

### Python

```bash
# Activate venv
source .venv/bin/activate

# Install deps
pip install -e .[dev]

# Run script
python scripts/init_db.py

# Interactive shell
python
>>> from shared.models import Task
>>> task = Task(agent_id="test", description="test")
>>> print(task)
```

---

## Troubleshooting Quick Fixes

### Port already in use

```bash
# Найти процесс
lsof -i :8100

# Kill процесс
kill -9 <PID>

# Или изменить порт в .env
```

### Cannot connect to database

```bash
# Проверить что container running
docker ps | grep postgres

# Проверить logs
docker logs balbes-postgres

# Restart
docker compose restart postgres

# Подождать healthy
docker compose ps postgres
```

### Import errors

```bash
# Переустановить в editable mode
pip install -e .

# Проверить PYTHONPATH
echo $PYTHONPATH

# Добавить если нужно
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

### Tests fail

```bash
# Проверить что БД поднята
make infra-up

# Очистить cache
make clean

# Запустить снова
pytest -v
```

---

## Next Steps

После того как система запущена:

1. **Прочитать документацию**:
   - [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - архитектура
   - [AGENTS_GUIDE.md](AGENTS_GUIDE.md) - как работают агенты
   - [EXAMPLES.md](EXAMPLES.md) - практические примеры

2. **Попробовать создать скилл**:
   - Отправить задачу Coder через Telegram
   - Наблюдать процесс в Web UI
   - Проверить результат

3. **Изучить код**:
   - `shared/base_agent.py` - базовая логика агента
   - `shared/llm_client.py` - как работает multi-provider
   - `services/coder/agent.py` - пример специализированного агента

4. **Начать разработку**:
   - Следовать [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)
   - Или работать над конкретной задачей/фичей

---

## Resources

- **OpenRouter**: https://openrouter.ai/docs
- **FastAPI**: https://fastapi.tiangolo.com/
- **React**: https://react.dev/
- **shadcn/ui**: https://ui.shadcn.com/
- **RabbitMQ**: https://www.rabbitmq.com/documentation.html
- **Qdrant**: https://qdrant.tech/documentation/
- **python-telegram-bot**: https://docs.python-telegram-bot.org/

---

## Support

Вопросы и проблемы: создавайте GitHub Issues

Happy coding! 🚀
