# Frequently Asked Questions (FAQ)

## Общие вопросы

### В чем разница между этой системой и OpenClaw?

**Balbes Multi-Agent System**:
- Минималистичный подход, только нужный функционал
- Модульная архитектура (микросервисы)
- Фокус на token economy (строгий контроль расходов)
- Два интерфейса: Telegram (быстрый доступ) + Web UI (детальный мониторинг)
- Написан с нуля под конкретные нужны

**OpenClaw**:
- Более feature-rich
- Больше готовых возможностей из коробки
- Может быть избыточным для простых use cases

### Сколько это будет стоить в эксплуатации?

**Примерная оценка (при активном использовании)**:

LLM API (основные расходы):
- Coder: 5-10 задач в день = 50-100K tokens = $0.75-$1.50
- Orchestrator: координация = 10-20K tokens = $0.15-$0.30
- Embeddings: 50 записей в день = 5K tokens = $0.0005
- **Итого LLM**: ~$1-2 в день при активной работе

VPS (фиксированные):
- 4GB RAM, 2 CPU, 40GB SSD = ~$15-25/месяц

**Total**: ~$45-85/месяц

**Экономия**:
- Используйте cheap models когда возможно
- Fallback на free models (Llama 3.1)
- Token limits предотвращают расходы

### Можно ли использовать локальные LLM модели?

Да, можно добавить provider для локальных моделей:
- Ollama
- LM Studio
- vLLM

Это снизит costs до $0, но:
- ❌ Нужен мощный GPU
- ❌ Качество может быть ниже
- ❌ Больше latency для инференса

Для MVP используем OpenRouter (проще), потом можно добавить локальные.

### Безопасно ли давать агентам доступ к VPS?

В MVP агенты имеют **ограниченный доступ**:

**Coder**:
- Может писать только в `/data/coder_output/`
- Может запускать только whitelist команды (pytest, python, ls)
- Не имеет доступа к системным файлам
- Не может делать sudo

**Orchestrator**:
- Только координирует, не выполняет опасные операции

**В будущем** (advanced Coder):
- Git operations в isolated environment
- Code review перед применением
- Sandboxed execution

### Что если агент создаст вредоносный код?

**Защиты в MVP**:
1. Coder сохраняет код в `/data/coder_output/` (не выполняется автоматически)
2. Вы проверяете код перед использованием
3. Tесты должны пройти (базовая проверка работоспособности)
4. Whitelist разрешенных операций

**В будущем**:
- Статический анализ кода (bandit, semgrep)
- Sandboxed execution
- Code review через другого агента

---

## Технические вопросы

### Почему три разные базы данных?

См. [ADR-003](ARCHITECTURE_DECISIONS.md#adr-003-postgresql--redis--qdrant-три-бд)

TL;DR: Каждая БД оптимизирована для своего типа данных:
- **PostgreSQL**: structured data (ACID, joins, analytics)
- **Redis**: fast memory (TTL, counters, sub-millisecond access)
- **Qdrant**: vector search (semantic similarity, embeddings)

### Как агенты общаются между собой?

Через **RabbitMQ Message Bus**:

1. Асинхронные сообщения (не блокируют отправителя)
2. Guaranteed delivery с acknowledgments
3. Два типа routing:
   - **Direct**: message к конкретному агенту
   - **Broadcast**: message всем агентам

См. [API_SPECIFICATION.md - RabbitMQ Protocol](API_SPECIFICATION.md#rabbitmq-message-protocol)

### Можно ли добавить новый скилл вручную?

Да:

1. Написать Python функцию в `shared/skills/my_skill.py`
2. Создать YAML описание в `config/skills/my_skill.yaml`
3. Restart Skills Registry (или hot reload в dev mode)
4. Добавить скилл в agent config (если нужно)

Или попросить Coder создать скилл - это его работа!

### Как работает fallback при недоступности модели?

1. LLMClient пытается вызвать primary model
2. При ошибке (timeout, rate limit, API down):
   - Логирует ошибку
   - Берет следующую модель из `fallback_chain`
   - Пытается её
   - Повторяет до 3 раз
3. При успехе fallback:
   - Отправляет notification в Telegram
   - Логирует использование fallback модели
   - Возвращает результат
4. Если все fallback провалились:
   - Возвращает ошибку
   - Task fails

См. [CONFIGURATION.md - Providers](CONFIGURATION.md#configprovidersyaml)

### Что происходит при превышении токен-лимита?

**At 80% (warning)**:
- Alert в Telegram: "⚠️ Agent approaching limit"
- Продолжает использовать primary model

**At 100% (exceeded)**:
- Alert в Telegram: "🚨 Limit exceeded"
- Автоматическое переключение на cheap model (gpt-4o-mini или llama-free)
- Агент продолжает работу
- Quality может быть ниже

**Сброс лимита**: В 00:00 UTC ежедневно

**Manual override**: `/model @agent <better-model>` (но счетчик не сбрасывается)

### Как посмотреть что агент делает прямо сейчас?

**Telegram**:
```
/status - краткий статус
/logs @agent 5 - последние 5 действий
```

**Web UI**:
- Dashboard → Recent Activity (live feed)
- Agent Detail → Activity Log (детальные логи)
- Real-time updates через WebSocket

**Файловые логи**:
```bash
tail -f data/logs/coder.log | jq '.'
```

### Можно ли откатить задачу/действие агента?

**В MVP**: Нет автоматического rollback.

**Manual rollback**:
- Удалить созданные файлы
- Откатить изменения в БД (если нужно)
- Деактивировать скилл

**В будущем**: Transaction-based operations с возможностью rollback.

---

## Работа с системой

### Как остановить агента который зациклился?

```
/stop @agent

# Если не реагирует:
docker compose restart <agent>

# Nuclear option:
docker compose stop <agent>
docker compose start <agent>
```

### Как изменить токен-лимит для агента?

**Temporary** (до перезапуска):
```sql
-- В PostgreSQL
UPDATE agents
SET config = jsonb_set(
    config,
    '{token_limits,daily}',
    '150000'
)
WHERE id = 'coder';
```

**Permanent**:
1. Изменить в `config/agents/coder.yaml`
2. Restart агента

### Как добавить нового провайдера LLM?

1. Добавить в `config/providers.yaml`:
```yaml
providers:
  new_provider:
    api_key: ${NEW_PROVIDER_KEY}
    base_url: "https://api.newprovider.com/v1"
    models:
      - id: "model-name"
        cost_per_1k_tokens: 0.01
        ...
```

2. Добавить в fallback_chain если нужно

3. Добавить в `.env`:
```bash
NEW_PROVIDER_KEY=your-key
```

4. Restart сервисы

### Как посмотреть сколько токенов осталось до лимита?

**Telegram**:
```
/tokens

Ответ:
coder: 82,450 / 100,000 (82%)
Осталось: 17,550 tokens (~$0.32)
```

**Web UI**: Tokens page показывает детальную статистику

**Programmatically**:
```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8200/api/tokens/stats?period=today | jq '.by_agent'
```

---

## Разработка и отладка

### Как тестировать агента локально без Telegram?

```python
# Создать тестовый скрипт
# test_agent.py

import asyncio
from services.coder.agent import CoderAgent
from shared.models import Task

async def test():
    agent = CoderAgent()
    await agent.start()

    task = Task(
        agent_id="coder",
        description="Create skill for parsing HackerNews",
        payload={}
    )

    result = await agent.execute_task(task)
    print(result)

    await agent.stop()

asyncio.run(test())
```

### Как debug LLM вызовы?

**Включить DEBUG логи**:
```bash
LOG_LEVEL=DEBUG python services/coder/main.py
```

**В логах будет**:
```json
{
  "timestamp": "2026-03-26T15:30:08Z",
  "level": "DEBUG",
  "agent_id": "coder",
  "action": "llm_call",
  "request": {
    "model": "claude-3.5-sonnet",
    "messages": [...],  // Полный prompt
    "max_tokens": 8000
  },
  "response": {
    "content": "...",  // Полный ответ
    "tokens": 1456
  }
}
```

### Как тестировать fallback?

**Способ 1**: Использовать невалидный API key
```bash
# В .env временно
OPENROUTER_API_KEY=invalid-key

# Отправить задачу
/task @coder test task

# Должен сработать fallback на следующую модель
```

**Способ 2**: Mock в тестах
```python
@pytest.mark.asyncio
async def test_fallback(monkeypatch):
    async def mock_api_call_fail(*args, **kwargs):
        raise TimeoutError("API timeout")

    monkeypatch.setattr("httpx.AsyncClient.post", mock_api_call_fail)

    result = await llm_client.complete(messages, "test_agent")

    # Должен использовать fallback
    assert result.fallback_used == True
```

### Как добавить новый action type для логирования?

1. Добавить в код агента:
```python
await self.log_action(
    action="new_action_type",
    parameters={...},
    result={...},
    status="success"
)
```

2. Логи автоматически появятся в:
   - PostgreSQL (action_logs table)
   - Файле (data/logs/{agent}.log)
   - Web UI (Agent Detail → Logs)

3. Для фильтрации в Web UI может потребоваться обновить frontend filter options.

---

## Troubleshooting

### Ошибка "Connection refused" при старте агента

**Причина**: Зависимые сервисы еще не поднялись

**Решение**:
```bash
# Проверить что все БД running
docker compose -f docker-compose.infra.yml ps

# Проверить health
docker compose -f docker-compose.infra.yml ps | grep healthy

# Если не healthy - посмотреть логи
docker compose -f docker-compose.infra.yml logs postgres
```

### Telegram бот не отвечает

**Checklist**:
1. ✅ TELEGRAM_BOT_TOKEN правильный?
2. ✅ TELEGRAM_USER_ID ваш?
3. ✅ Orchestrator service running?
4. ✅ RabbitMQ доступен?
5. ✅ Нет ошибок в логах?

```bash
# Проверить логи Orchestrator
tail -f data/logs/orchestrator.log

# Проверить что процесс живой
ps aux | grep orchestrator

# Перезапустить
docker compose restart orchestrator  # Prod
# или Ctrl+C и python main.py  # Dev
```

### WebSocket не подключается

**Причина**: CORS или authentication

**Решение**:
1. Проверить что в .env правильный CORS_ORIGINS
2. Проверить что JWT token валидный
3. Проверить в browser console ошибки
4. Попробовать без authentication (для теста):
   ```javascript
   const ws = new WebSocket('ws://localhost:8200/ws');
   ```

### Agent застрял на задаче

**Symptoms**: Status "working" более 10 минут

**Diagnosis**:
```bash
# Посмотреть что делает
/logs @agent 5

# Проверить в логах последнее действие
tail -20 data/logs/{agent}.log | jq '.action'
```

**Solutions**:
1. Подождать еще (может быть долгая задача)
2. `/stop @agent` - остановить gracefully
3. `docker compose restart agent` - force restart

### База данных переполнена

**Check size**:
```bash
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT pg_size_pretty(pg_database_size('balbes_agents'));
"
```

**Cleanup**:
```bash
# Удалить старые логи (> 30 дней)
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
DELETE FROM action_logs WHERE timestamp < NOW() - INTERVAL '30 days';
DELETE FROM token_usage WHERE timestamp < NOW() - INTERVAL '30 days';
VACUUM FULL;
"
```

### "Module not found" ошибки

**Причина**: Зависимости не установлены или `shared/` не в PYTHONPATH

**Solution**:
```bash
# Dev: установить в editable mode
pip install -e .

# Или добавить в PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# Prod: должно быть в Dockerfile
COPY shared /app/shared
ENV PYTHONPATH=/app
```

---

## Performance вопросы

### Система работает медленно

**Check**:
1. CPU usage: `htop` или `docker stats`
2. Memory usage: `free -h` или `docker stats`
3. Disk I/O: `iotop`
4. Network: `iftop`

**Common issues**:
- PostgreSQL queries slow → добавить индексы
- Redis memory full → увеличить maxmemory или cleanup
- Too many logs → включить log rotation
- Qdrant slow → optimize indexing

### LLM вызовы слишком долгие

**Normal latency**:
- Simple query: 1-3 секунды
- Code generation: 3-10 секунд
- Large context: 10-30 секунд

**If slower**:
1. Проверить network latency до API
2. Проверить размер prompt (может быть слишком большой)
3. Попробовать другую модель
4. Проверить что не rate limited

### PostgreSQL запросы медленные

```sql
-- Найти медленные запросы
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;

-- Если какие-то запросы медленные - добавить индексы
CREATE INDEX idx_name ON table(column);
```

---

## Scaling вопросы

### Можно ли запустить несколько копий одного агента?

**В MVP**: Нет, каждый агент - singleton.

**В будущем**: Да, можно:
```yaml
# docker-compose
coder_01:
  build: ./services/coder
  # ...

coder_02:
  build: ./services/coder
  # ...
```

RabbitMQ автоматически распределит задачи (round-robin).

### Сколько агентов можно запустить на одном VPS?

**Зависит от ресурсов**:

Каждый агент: ~100-200MB RAM, ~5-10% CPU при активной работе

**4GB VPS**:
- Infrastructure: ~1GB (Postgres, Redis, RabbitMQ, Qdrant)
- Services: ~500MB (Memory Service, Skills Registry, Web)
- Agents: ~2.5GB остается = ~10-12 агентов

**8GB VPS**: Комфортно для 20+ агентов

### Можно ли распределить агенты на разные серверы?

**В MVP**: Нет, все на одном VPS.

**В будущем**: Да, нужно:
1. Вынести RabbitMQ, PostgreSQL, Redis на отдельные серверы
2. Agents подключаются по сети
3. Настроить VPN или private network между серверами

---

## Security вопросы

### Как защищен Web UI?

**MVP**:
- Bearer token для login
- JWT для sessions (24h expiration)
- CORS ограничение
- Rate limiting (100 req/min)

**В будущем**:
- Multi-user с ролями
- OAuth integration
- 2FA

### Можно ли дать доступ другому пользователю?

**В MVP**: Нет, single-user system.

**Workaround**: Поделиться WEB_AUTH_TOKEN (не рекомендуется)

**В будущем**: Multi-user support с ролями (admin, viewer, operator).

### Где хранятся API ключи?

- В `.env` файле (не коммитится в git)
- Загружаются как environment variables
- Доступны только внутри контейнеров/процессов
- Не логируются
- Не передаются через API

**Best practice**: Использовать secrets manager (Vault, AWS Secrets) для production.

---

## Customization вопросы

### Как изменить инструкции агента?

1. Открыть `config/agents/{agent}.yaml`
2. Изменить секцию `instructions`
3. Restart агента

**Для базовых инструкций** (всем агентам):
- Изменить `config/base_instructions.yaml`
- Restart всех агентов

### Как добавить новую команду в Telegram?

1. Добавить handler в `services/orchestrator/handlers/`:
```python
# handlers/my_command.py

async def handle_my_command(update, context):
    # Implementation
    await update.message.reply_text("Response")
```

2. Зарегистрировать в `telegram_bot.py`:
```python
application.add_handler(CommandHandler("mycommand", handle_my_command))
```

3. Добавить в `/help` описание

### Как изменить модель по умолчанию?

**Per agent**:
```yaml
# config/agents/coder.yaml
llm_settings:
  primary_model: "openrouter/openai/gpt-4-turbo"  # Изменить здесь
```

**Globally (fallback chain)**:
```yaml
# config/providers.yaml
default_fallback_chain:
  - provider: openrouter
    model: "openai/gpt-4-turbo"  # Теперь это primary для всех
```

### Как добавить свой скилл?

См. [Пример 17](EXAMPLES.md#пример-17-интеграция-нового-скилла-в-систему)

---

## Data Management вопросы

### Как экспортировать данные?

**PostgreSQL**:
```bash
docker exec balbes-postgres pg_dump -U balbes balbes_agents > backup.sql
```

**Qdrant** (memories):
```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
points = client.scroll(collection_name="agent_memory", limit=10000)[0]

import json
with open("memories_export.json", "w") as f:
    json.dump([p.dict() for p in points], f)
```

**Logs**:
```bash
# Уже в JSON Lines формате
cp data/logs/*.log ./export/
```

### Как очистить память агента?

**Fast memory (Redis)** - expired автоматически по TTL

**Long-term memory (Qdrant)**:
```python
# Удалить все personal memories агента
client.delete(
    collection_name="agent_memory",
    points_selector={
        "filter": {
            "must": [
                {"key": "agent_id", "match": {"value": "coder"}},
                {"key": "scope", "match": {"value": "personal"}}
            ]
        }
    }
)
```

**Осторожно**: Агент потеряет свой опыт!

### Как бэкапить систему?

См. [DEPLOYMENT.md - Backup & Restore](DEPLOYMENT.md#backup--restore)

**Quick backup**:
```bash
./scripts/backup.sh

# Создаст:
# - backups/postgres_YYYYMMDD_HHMMSS.sql
# - backups/qdrant_YYYYMMDD_HHMMSS.tar.gz
# - backups/coder_output_YYYYMMDD_HHMMSS.tar.gz
```

**Automated**: Cron job каждый день в 3:00 AM

---

## Feature Requests

### Можно ли добавить голосовые команды в Telegram?

**Сейчас**: Да — голосовые сообщения принимаются, транскрибируются (гибрид: локальный openai-whisper для коротких, облачный STT для длинных) и обрабатываются как обычный текст. См. `WHISPER_*` в `.env.example` и раздел Voice в CONFIGURATION.

### Будет ли mobile app?

**В MVP**: Нет, только Web UI (адаптивный).

**В будущем**:
- React Native app
- Или просто PWA (Web UI как app)

### Можно ли интегрировать с Discord/Slack?

**В MVP**: Нет, только Telegram.

**В будущем**: Да, можно добавить адаптеры:
- Orchestrator → MultiChannelBot → {Telegram, Discord, Slack}

---

## Миграция и обновление

### Как обновить систему до новой версии?

```bash
# 1. Backup текущей версии
./scripts/backup.sh

# 2. Pull новый код
git pull origin main

# 3. Check changelog
cat CHANGELOG.md

# 4. Применить миграции БД (если есть)
python scripts/migrate.py

# 5. Rebuild images (prod)
docker compose -f docker-compose.prod.yml build

# 6. Restart services
docker compose -f docker-compose.prod.yml up -d

# 7. Проверить что все работает
/status
```

### Что делать если обновление сломало систему?

**Rollback**:
```bash
# 1. Откатить код
git log --oneline -5  # Найти предыдущую версию
git checkout <previous-commit>

# 2. Rebuild
docker compose build

# 3. Restore БД из backup (если схема изменилась)
./scripts/restore.sh backups/postgres_YYYYMMDD.sql

# 4. Restart
docker compose up -d
```

---

## Best Practices

### Рекомендации по использованию

1. **Регулярные backups**: Настроить cron для ежедневных бэкапов
2. **Мониторинг токенов**: Проверять dashboard хотя бы раз в день
3. **Review кода от Coder**: Всегда проверять перед использованием
4. **Логи**: Периодически проверять на ошибки
5. **Updates**: Обновлять зависимости регулярно (security patches)

### Как оптимизировать расходы на токены?

1. **Используйте память агентов**: Вместо повторных LLM вызовов
2. **Оптимизируйте промпты**: Короче = дешевле
3. **Cheap models для простых задач**: gpt-4o-mini вместо Claude
4. **Кэширование**: Одинаковые запросы = один embedding
5. **Batch operations**: Группируйте задачи когда возможно
6. **Лимиты**: Установите разумные daily limits

### Рекомендации по агентам

**Orchestrator**:
- Используйте для координации, не для heavy thinking
- Короткие промпты
- Cheap model подходит для большинства команд

**Coder**:
- Дайте больше токенов (code generation требовательна)
- Premium model рекомендуется (Claude/GPT-4)
- Переключайте на cheap для простых задач (small refactors)

---

## Getting Help

### Где искать информацию?

1. **Документация** в `docs/` - первый источник
2. **Примеры** в `docs/EXAMPLES.md` - практические сценарии
3. **Логи** системы - что происходит
4. **GitHub Issues** - известные проблемы и решения (когда настроим)

### Как сообщить о баге?

1. Проверить логи:
   ```bash
   # Найти ошибку
   grep -r "ERROR" data/logs/*.log | tail -20
   ```

2. Собрать информацию:
   - Что делали (команда/действие)
   - Что ожидали
   - Что получили
   - Логи с ошибкой
   - Версия системы (`git log -1`)

3. Создать GitHub Issue с деталями

### Где получить помощь?

- GitHub Issues (вопросы и проблемы)
- GitHub Discussions (общие вопросы)
- Email: ваш email

---

## Roadmap вопросы

### Когда будет Blogger agent?

После завершения и тестирования MVP (2-3 недели).
Blogger - отдельное большое ТЗ.

### Будет ли GUI для создания агентов?

Возможно в версии 2.0. Пока создаем через YAML configs + Python code.

### Планируется ли marketplace скиллов?

Интересная идея! В backlog. Можно сделать:
- Публикация скиллов
- Sharing между пользователями (если multi-user)
- Rating и reviews

### Будет ли API для внешних интеграций?

В версии 1.1 (после MVP). Webhooks и REST API для:
- Создание задач из внешних систем
- Получение статуса агентов
- Subscribe на события

---

Не нашли ответ? Создайте [GitHub Issue](../issues) с вопросом!
