# Примеры использования

Этот документ содержит практические примеры работы с системой.

---

## Пример 1: Создание скилла через Telegram

### Сценарий
Пользователь хочет создать скилл для парсинга новостей с HackerNews.

### Шаги

**1. Отправка команды**
```
User → Telegram:
/task @coder создай скилл для парсинга HackerNews. Скилл должен возвращать топ-10 постов с заголовками и ссылками. Используй requests и beautifulsoup4.
```

**2. Подтверждение**
```
Bot → User:
✅ Задача #a7f3e892-1234-5678-90ab-cdef12345678 создана для @coder
Описание: создай скилл для парсинга HackerNews...
Статус: pending

🟡 @coder начал работу
```

**3. Процесс выполнения** (видно в Web UI live)
```
15:30:05 - Coder: task_started
15:30:06 - Coder: skill_executed (query_memory: "parsing examples")
15:30:08 - Coder: llm_call (claude-3.5-sonnet, tokens: 856)
15:30:12 - Coder: llm_call (generating tests, tokens: 642)
15:30:14 - Coder: skill_executed (write_file: implementation.py)
15:30:14 - Coder: skill_executed (write_file: skill.yaml)
15:30:14 - Coder: skill_executed (write_file: test_implementation.py)
15:30:15 - Coder: skill_executed (execute_command: pytest)
15:30:17 - Coder: task_completed (duration: 12.3s, tokens: 5,234)
```

**4. Результат**
```
Bot → User:
✅ @coder завершил задачу #a7f3e892...

Создан скилл: parse_hackernews
📁 Путь: /data/coder_output/skills/parse_hackernews/

Файлы:
- implementation.py (код скилла)
- skill.yaml (описание)
- test_implementation.py (тесты)
- README.md (документация)

✅ Тесты: 3/3 пройдены
💰 Токены: 5,234
⏱️ Время: 12.3 секунды

Можешь проверить код и использовать скилл!
```

**5. Проверка результата**
```bash
# На VPS или локально
cat /data/coder_output/skills/parse_hackernews/skill.yaml
cat /data/coder_output/skills/parse_hackernews/implementation.py
cat /data/coder_output/skills/parse_hackernews/README.md
```

**6. Использование скилла** (в будущем, когда зарегистрируем)
```
User → Telegram:
/task @blogger используй скилл parse_hackernews и создай пост с топ-3 новостями
```

---

## Пример 2: Мониторинг через Web UI

### Открытие Dashboard

1. Открыть `http://your-domain.com` в браузере
2. Ввести `WEB_AUTH_TOKEN` на странице логина
3. Попасть на Dashboard

### Dashboard view

```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Balbes Multi-Agent System    [Theme Toggle]  [User Icon] │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ 📊 Agents Overview                                           │
│ ┌──────────────────────┐  ┌──────────────────────┐         │
│ │  Orchestrator        │  │  Coder               │         │
│ │  🟢 Idle             │  │  🟡 Working          │         │
│ │                      │  │  Creating skill...   │         │
│ │  Tokens: 5.2k / 100k │  │  Tokens: 12.4k/100k  │         │
│ │  Cost: $0.11         │  │  Cost: $0.23         │         │
│ │  Uptime: 5h 23m      │  │  Task: #a7f3...      │         │
│ └──────────────────────┘  └──────────────────────┘         │
│                                                               │
│ 🔔 Recent Activity                            [View All →]  │
│ ┌───────────────────────────────────────────────────────────┤
│ │ 15:30:17  coder       ✅ Task completed                   │
│ │           Created skill parse_hackernews                  │
│ │                                                            │
│ │ 15:30:15  coder       ✅ Tests passed (3/3)               │
│ │                                                            │
│ │ 15:30:08  coder       💬 LLM call (1,456 tokens)          │
│ │                                                            │
│ │ 15:30:05  coder       ▶️  Task started                    │
│ │           Task: #a7f3e892...                               │
│ │                                                            │
│ │ 15:29:58  orchestrator 📩 Task created for @coder         │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ 💰 Token Usage Today                                         │
│ ┌───────────────────────────────────────────────────────────┤
│ │ Total: 17,684 / 200,000 (8.8%)        Cost: $0.34        │
│ │ [████████░░░░░░░░░░░░░░░░░░░░]                            │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Клик на Agent Card → Agent Detail

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back to Dashboard                                          │
│                                                               │
│ 🤖 Coder Agent                                               │
│ Status: 🟡 Working                                           │
│ Current Task: Creating skill parse_hackernews               │
│ Model: anthropic/claude-3.5-sonnet                          │
│ Uptime: 5h 23m                                               │
│                                                               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 💰 Token Usage                                               │
│                                                               │
│ Today:     12,450 / 100,000 (12.4%)                         │
│ [████████████░░░░░░░░░░░░░░░░░░]                             │
│                                                               │
│ This Hour:  2,340 / 15,000 (15.6%)                          │
│ [███████████░░░░░░░░░░░░░░░]                                 │
│                                                               │
│ Cost Today: $0.23                                            │
│                                                               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 🛠️  Skills (6)                                               │
│                                                               │
│ • read_file       • write_file      • execute_command       │
│ • search_web      • query_memory    • send_message          │
│                                                               │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │
│ 📝 Activity Log                    [Filter ▾] [Export]      │
│                                                               │
│ 🔍 Filter: [All Actions ▾] [Success ▾] [Last 1 hour ▾]     │
│                                                               │
│ ┌───────────────────────────────────────────────────────────┤
│ │ 15:30:17  ✅ task_completed                               │
│ │           Task: #a7f3e892-1234-5678-90ab-cdef12345678     │
│ │           Duration: 12.3s                                  │
│ │           Tokens: 5,234                                    │
│ │           [View Details]                                   │
│ │                                                            │
│ │ 15:30:15  ✅ skill_executed                               │
│ │           Skill: execute_command                           │
│ │           Params: {"command": "pytest ..."}                │
│ │           Result: {"exit_code": 0, "passed": 3}            │
│ │           Duration: 1.8s                                   │
│ │                                                            │
│ │ 15:30:14  ✅ skill_executed                               │
│ │           Skill: write_file                                │
│ │           Params: {"path": "parse_hackernews/..."}         │
│ │           Result: {"size": 1247}                           │
│ │           Duration: 45ms                                   │
│ │                                                            │
│ │ 15:30:08  ✅ llm_call                                     │
│ │           Model: anthropic/claude-3.5-sonnet               │
│ │           Tokens: 1,456 (prompt: 856, completion: 600)     │
│ │           Cost: $0.022                                     │
│ │           Duration: 2.5s                                   │
│ │           Context size: 3,234 tokens                       │
│ │                                                            │
│ │ 15:30:06  ✅ skill_executed                               │
│ │           Skill: query_memory                              │
│ │           Params: {"query": "parsing examples"}            │
│ │           Result: {"results": 2}                           │
│ │           Duration: 234ms                                  │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ [Load More]                                    Page 1 of 45  │
└─────────────────────────────────────────────────────────────┘
```

---

## Пример 3: Отправка задачи через Web UI Chat

### Открыть Chat страницу

```
┌─────────────────────────────────────────────────────────────┐
│ 💬 Chat                                                      │
├─────────────────────────────────────────────────────────────┤
│ Talk to: [🤖 Coder ▾]                                       │
│                                                               │
│ ┌───────────────────────────────────────────────────────────┤
│ │                                                            │
│ │  You                                      15:45           │
│ │  Создай скилл для получения погоды по городу.            │
│ │  Используй API weatherapi.com                             │
│ │                                                            │
│ │                                    15:45  Coder           │
│ │  Понял задачу. Начинаю создание скилла get_weather.      │
│ │  Проверяю память на похожие примеры...                    │
│ │                                                            │
│ │  You                                      15:46           │
│ │  Добавь обработку ошибок если API недоступен              │
│ │                                                            │
│ │                                    15:46  Coder           │
│ │  Хорошо, добавлю retry логику с timeout.                  │
│ │                                                            │
│ │                                    15:48  Coder           │
│ │  ✅ Скилл готов!                                          │
│ │                                                            │
│ │  Создан: get_weather                                      │
│ │  Файлы: implementation.py, skill.yaml, tests              │
│ │  Тесты: ✅ 3/3 passed                                     │
│ │  Путь: /data/coder_output/skills/get_weather/            │
│ │                                                            │
│ │  [View Code] [Register Skill] [Download]                 │
│ │                                                            │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ ┌───────────────────────────────────────────────────────────┤
│ │ Type your message...                             [Send]   │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Real-time updates**: Сообщения появляются мгновенно через WebSocket.

---

## Пример 4: Мониторинг токенов

### Tokens Page

```
┌─────────────────────────────────────────────────────────────┐
│ 💰 Token Usage                     [Today ▾] [Refresh]      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ 📊 Total Usage Today                                         │
│ ┌───────────────────────────────────────────────────────────┤
│ │                                                            │
│ │  17,684 / 200,000 tokens (8.8%)                           │
│ │  [████████░░░░░░░░░░░░░░░░░░░░░░]                         │
│ │                                                            │
│ │  Cost: $0.34                                              │
│ │  Remaining: 182,316 tokens ($3.66 budget left)            │
│ │                                                            │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ 🤖 By Agent                                                  │
│ ┌───────────────────────────────────────────────────────────┤
│ │ Agent        │ Tokens   │ % Used │ Cost   │ Calls │ Avg  │
│ │──────────────┼──────────┼────────┼────────┼───────┼──────│
│ │ coder        │ 12,450   │ 12.4%  │ $0.23  │ 15    │ 830  │
│ │ orchestrator │  5,234   │  5.2%  │ $0.11  │ 28    │ 187  │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ 📈 Usage Over Time (Today)                                   │
│ ┌───────────────────────────────────────────────────────────┤
│ │                                                            │
│ │   12k ┤                                    ╭─╮             │
│ │       │                                    │ │             │
│ │   10k ┤                          ╭─╮      │ │             │
│ │       │                          │ │      │ │             │
│ │    8k ┤                 ╭─╮      │ │ ╭─╮  │ │             │
│ │       │        ╭─╮      │ │      │ │ │ │  │ │             │
│ │    6k ┤   ╭─╮  │ │ ╭─╮  │ │ ╭─╮  │ │ │ │  │ │             │
│ │       │   │ │  │ │ │ │  │ │ │ │  │ │ │ │  │ │             │
│ │    4k ┤╭─╮│ │  │ │ │ │  │ │ │ │  │ │ │ │  │ │             │
│ │       ││ ││ │  │ │ │ │  │ │ │ │  │ │ │ │  │ │             │
│ │    2k ┤│ ││ │  │ │ │ │  │ │ │ │  │ │ │ │  │ │             │
│ │       ││ ││ │  │ │ │ │  │ │ │ │  │ │ │ │  │ │             │
│ │     0 ┴┴─┴┴─┴──┴─┴─┴─┴──┴─┴─┴─┴──┴─┴─┴─┴──┴─┴─────────────│
│ │       00 02 04 06 08 10 12 14 16 18 20 22               │
│ │                        Hour of Day                         │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
│ 🏷️  By Model                                                 │
│ ┌───────────────────────────────────────────────────────────┤
│ │ Model                        │ Calls │ Tokens │ Cost      │
│ │──────────────────────────────┼───────┼────────┼───────────│
│ │ claude-3.5-sonnet            │  35   │ 15,234 │ $0.28     │
│ │ gpt-4-turbo                  │   7   │  2,200 │ $0.04     │
│ │ gpt-4o-mini                  │   1   │    250 │ $0.0001   │
│ │ text-embedding-3-small       │  12   │    450 │ $0.00005  │
│ └───────────────────────────────────────────────────────────┘
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Real-time update (WebSocket event)

Когда Coder завершает задачу, в Dashboard появляется toast notification:

```
╔════════════════════════════════════════╗
║ ✅ Task Completed                      ║
║                                        ║
║ Agent: Coder                           ║
║ Task: Create skill parse_hackernews   ║
║ Duration: 12.3s                        ║
║                                        ║
║ [View Details]                [Dismiss]║
╚════════════════════════════════════════╝
```

И agent card обновляется:
```
🟢 Idle  (было 🟡 Working)
Tokens: 17,684 / 100,000 (обновилось)
```

---

## Пример 5: Fallback при недоступности модели

### Сценарий
OpenRouter API для Claude временно недоступна (rate limit или outage).

### Что происходит

**1. User отправляет задачу**
```
/task @coder создай скилл для парсинга GitHub trending
```

**2. Coder пытается вызвать primary model**
```python
# В LLMClient
try:
    response = await openrouter.chat(model="claude-3.5-sonnet", ...)
except (Timeout, RateLimitError, APIError) as e:
    logger.warning(f"Primary model failed: {e}")
    # Переход на fallback
```

**3. Автоматический fallback**
```
15:45:01 - Coder: llm_call failed (claude-3.5-sonnet)
15:45:01 - Coder: trying fallback (gpt-4-turbo)
15:45:03 - Coder: llm_call success (gpt-4-turbo, tokens: 1,234)
```

**4. Уведомление в Telegram**
```
Bot → User:
⚠️ Model Fallback

Agent: @coder
Основная модель: claude-3.5-sonnet (недоступна)
Использована: gpt-4-turbo

Задача выполняется...
```

**5. Web UI notification (toast)**
```
╔════════════════════════════════════════╗
║ ⚠️  Model Fallback                     ║
║                                        ║
║ Agent: Coder                           ║
║ Primary: claude-3.5-sonnet (error)    ║
║ Fallback: gpt-4-turbo ✓               ║
║                                        ║
║ [Dismiss]                              ║
╚════════════════════════════════════════╝
```

**6. Задача выполняется успешно с fallback model**

---

## Пример 6: Превышение токен-лимита

### Сценарий
Coder активно работал и использовал 85,000 токенов (85% от лимита 100k).

### Что происходит

**1. Warning at 80%**
```
Bot → User:
⚠️ Token Budget Alert

Agent: @coder
Usage: 80,000 / 100,000 (80%)
Cost today: $0.18

Осталось 20% дневного лимита.
Рекомендую переключить на более дешевую модель если задачи не критичны.

/model @coder openrouter/gpt-4o-mini
```

**2. User игнорирует warning, отправляет еще задачи**

**3. Превышение лимита (100,234 tokens)**
```
15:50:15 - Coder: token_limit_exceeded
15:50:15 - Coder: switching to cheap model (gpt-4o-mini)
15:50:15 - System: notification sent to user
```

**4. Alert в Telegram**
```
Bot → User:
🚨 Token Limit Exceeded!

Agent: @coder
Usage: 100,234 / 100,000 (100%)
Cost today: $0.23

Агент автоматически переключен на дешевую модель:
openai/gpt-4o-mini

⚠️ Качество ответов может быть ниже.

Для восстановления премиум модели:
/model @coder openrouter/anthropic/claude-3.5-sonnet

Или подождите до 00:00 UTC (сброс лимита).
```

**5. Coder продолжает работу на дешевой модели**

**6. В Web UI токен-индикатор красный**
```
Coder Agent
Tokens: 100,234 / 100,000 (100%) 🔴
[████████████████████████████████] LIMIT EXCEEDED
Current model: gpt-4o-mini (switched automatically)
```

---

## Пример 7: Retry при провале тестов

### Сценарий
Coder создает скилл, но тесты не проходят с первого раза.

### Workflow

**Attempt 1**:
```
15:50:10 - Coder: generated code for skill fetch_quotes
15:50:12 - Coder: generated tests
15:50:14 - Coder: running pytest
15:50:16 - Coder: tests failed (1/3 passed)
```

**Pytest output**:
```
FAILED test_fetch_quotes_invalid_symbol - KeyError: 'price'
```

**Attempt 2** (retry):
```
15:50:17 - Coder: analyzing test errors
15:50:18 - Coder: llm_call (fixing code based on errors)
15:50:22 - Coder: updated implementation.py
15:50:23 - Coder: running pytest
15:50:25 - Coder: tests failed (2/3 passed)
```

**Pytest output**:
```
FAILED test_fetch_quotes_timeout - Timeout not handled
```

**Attempt 3** (retry):
```
15:50:26 - Coder: analyzing test errors
15:50:27 - Coder: llm_call (adding timeout handling)
15:50:31 - Coder: updated implementation.py
15:50:32 - Coder: running pytest
15:50:34 - Coder: tests passed (3/3) ✅
```

**Result**:
```
Bot → User:
✅ @coder завершил задачу

Создан скилл: fetch_quotes
Попытки: 3 (тесты прошли на 3-й попытке)
Токены: 7,856
Время: 24 секунды

Основные исправления:
- Attempt 1→2: Исправлена обработка missing keys
- Attempt 2→3: Добавлен timeout handling

Код готов к использованию!
```

---

## Пример 8: Поиск в долговременной памяти

### Сценарий
Coder получает задачу создать еще один парсинг-скилл и ищет примеры в памяти.

### Запрос к памяти

```python
# В Coder agent
memories = await self.query_memory(
    query="parsing websites with beautifulsoup",
    scope="personal",
    limit=3
)
```

### Результат из Qdrant

```python
[
    MemorySearchResult(
        content="Successfully created skill parse_hackernews. Used BeautifulSoup for parsing HTML. Key points: use requests.get() with timeout, check response.status_code, parse with bs4, extract data with CSS selectors. Tests passed on first try.",
        score=0.89,
        metadata={
            "task_id": "a7f3e892...",
            "skill_name": "parse_hackernews",
            "tags": ["skill", "parsing", "beautifulsoup", "success"],
            "tokens_used": 5234,
            "retries": 0
        },
        timestamp="2026-03-26T15:30:17Z"
    ),

    MemorySearchResult(
        content="Failed to create skill parse_reddit. Error: beautifulsoup4 not installed in tests. Lesson: always include requirements.txt with dependencies.",
        score=0.76,
        metadata={
            "task_id": "b8e4f903...",
            "skill_name": "parse_reddit",
            "tags": ["skill", "parsing", "failure"],
            "error": "ModuleNotFoundError"
        },
        timestamp="2026-03-25T10:15:00Z"
    ),

    MemorySearchResult(
        content="Created skill fetch_weather using requests. Learned: always handle HTTP errors gracefully, use retry with exponential backoff for API calls, include user-agent header.",
        score=0.72,
        metadata={
            "task_id": "c9f5g014...",
            "skill_name": "fetch_weather",
            "tags": ["skill", "api", "requests", "success"]
        },
        timestamp="2026-03-24T14:20:00Z"
    )
]
```

### Использование в промпте

```python
# Coder включает примеры в context для LLM
memories_text = "\n\n".join([
    f"Example {i+1} (relevance: {m.score:.0%}):\n{m.content}"
    for i, m in enumerate(memories)
])

messages = [
    {"role": "system", "content": coder_instructions},
    {"role": "user", "content": f"""
Create a skill for: {description}

Relevant examples from my past experience:
{memories_text}

Apply lessons learned from these examples.
"""}
]
```

### Результат
Coder создает лучший код, используя успешные паттерны и избегая ошибок из прошлого.

---

## Пример 9: Смена модели агента

### Через Telegram

```
User → Bot:
/model @coder openrouter/openai/gpt-4o-mini

Bot → User:
🔄 Изменение модели для @coder...

✅ Модель обновлена:

Было:
- anthropic/claude-3.5-sonnet
- Context: 200K tokens
- Cost: ~$0.015 / 1K tokens

Стало:
- openai/gpt-4o-mini
- Context: 128K tokens
- Cost: ~$0.0005 / 1K tokens (в 30 раз дешевле!)

⚠️ Качество может быть ниже для сложных задач по кодингу.

Вернуть обратно:
/model @coder openrouter/anthropic/claude-3.5-sonnet
```

### В базе данных

```sql
-- PostgreSQL update
UPDATE agents
SET current_model = 'openai/gpt-4o-mini'
WHERE id = 'coder';
```

### В Web UI

Agent Detail page обновляется (real-time):
```
Model: openai/gpt-4o-mini ⚠️
(Changed 2 minutes ago)

[Change Model ▾]
```

---

## Пример 10: Debugging через логи

### Проблема
Coder зависает на задаче более 5 минут.

### Действия

**1. Проверить статус**
```
/status

Bot:
🟡 coder - working
   Задача: #d1a2b3c4... "Create skill..."
   Прогресс: llm_call в процессе
   Время выполнения: 5m 23s
   Токены: 8,450
```

**2. Посмотреть последние логи**
```
/logs @coder 10

Bot:
15:55:23 🟡 llm_call (in progress)
         Model: claude-3.5-sonnet
         Timeout: 60s
         Started: 5m 23s ago

15:50:00 ✅ skill_executed: query_memory
15:49:58 ✅ task_started
```

**3. Анализ в Web UI**

Agent Detail → Logs:
```
15:55:23  llm_call
          Status: in_progress
          Duration: 323,000ms (5m 23s)
          Model: claude-3.5-sonnet
          ⚠️ Unusually long request
```

**4. Решение**

Возможно LLM API зависло. Варианты:
```
Option 1: Подождать еще (timeout 60s, может скоро ответит)
Option 2: /stop @coder и retry задачу
```

**5. Если остановили**
```
/stop @coder

Bot:
⏹️ Остановка задачи для @coder...
✅ Задача #d1a2b3c4 остановлена (timeout)
@coder статус: idle

Можешь повторить задачу:
/task @coder <описание>
```

---

## Пример 11: Broadcast сообщение всем агентам

### Сценарий
Orchestrator хочет уведомить всех агентов о чем-то важном (например, приближение maintenance).

### Код

```python
# В Orchestrator
await self.send_message(
    to_agent="broadcast",
    message_type="notification",
    payload={
        "type": "system_announcement",
        "message": "System maintenance in 10 minutes. Finish current tasks.",
        "severity": "warning"
    }
)
```

### Что происходит

**RabbitMQ**: Сообщение отправляется в `agents.broadcast` exchange (fanout)

**Все агенты получают**:
```
15:50:00 - Orchestrator: notification received
           Type: system_announcement
           Message: System maintenance in 10 minutes...

15:50:00 - Coder: notification received
           Type: system_announcement
           Message: System maintenance in 10 minutes...
           Action: Finishing current task #abc123
```

**Каждый агент обрабатывает**:
- Orchestrator: уведомляет пользователя в Telegram
- Coder: пытается завершить текущую задачу быстрее или сохраняет прогресс

---

## Пример 12: Context в быстрой памяти

### Сценарий
Coder работает над задачей и сохраняет промежуточное состояние.

### Сохранение context

```python
# Coder в процессе работы
await self.set_context(
    key="current_task_state",
    value={
        "task_id": str(task.id),
        "step": "generating_tests",
        "files_created": ["implementation.py", "skill.yaml"],
        "skill_name": "parse_github_trending",
        "retries": 0
    },
    ttl=3600  # 1 час
)
```

### Redis хранит

```
Key: context:coder:current_task_state
Value: {JSON}
TTL: 3600 seconds
```

### Использование

```python
# Если Coder крашнулся и перезапустился
state = await self.get_context("current_task_state")

if state:
    # Восстановить задачу
    task_id = state["task_id"]
    step = state["step"]
    logger.info(f"Recovering task {task_id} from step {step}")
    # Continue from where left off
```

---

## Пример 13: Создание совершенно нового агента (future)

Когда MVP готов и хотим добавить Blogger агента.

### Шаги

**1. Создать конфиг**
```yaml
# config/agents/blogger.yaml
agent_id: blogger
name: "Blogger Agent"
description: "Content creation and posting agent"

llm_settings:
  primary_model: "openrouter/openai/gpt-4o-mini"  # Дешевле для контента
  max_tokens: 2000
  temperature: 0.9  # Выше для креативности

token_limits:
  daily: 50000  # Меньше чем у Coder

skills:
  - generate_content
  - post_to_telegram
  - post_to_youtube
  - search_web
  - query_memory
  - send_message

instructions: |
  Ты - Blogger Agent. Создаешь и публикуешь контент...
```

**2. Создать класс агента**
```python
# services/blogger/agent.py
from shared.base_agent import BaseAgent

class BloggerAgent(BaseAgent):
    async def execute_task(self, task: Task) -> TaskResult:
        # Implementation
        pass
```

**3. Зарегистрировать в PostgreSQL**
```python
python scripts/create_agent.py --config config/agents/blogger.yaml
```

**4. Добавить в docker-compose.prod.yml**
```yaml
blogger:
  build: ./services/blogger
  # ...
```

**5. Запустить**
```bash
# Dev
cd services/blogger && python main.py

# Prod
docker compose up -d blogger
```

**6. Обновить Orchestrator**
```python
# Добавить blogger в список known agents
KNOWN_AGENTS = ["orchestrator", "coder", "blogger"]
```

**7. Использовать**
```
/task @blogger создай пост про AI для Telegram канала
```

---

## Пример 14: Анализ стоимости токенов

### SQL запрос для детальной статистики

```sql
-- Стоимость по агентам за неделю
SELECT
    agent_id,
    DATE(timestamp) as date,
    SUM(total_tokens) as tokens,
    SUM(cost_usd) as cost,
    COUNT(*) as num_calls,
    AVG(total_tokens) as avg_tokens_per_call
FROM token_usage
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY agent_id, DATE(timestamp)
ORDER BY date DESC, cost DESC;

-- Самые дорогие задачи
SELECT
    t.id as task_id,
    t.agent_id,
    t.description,
    SUM(tu.total_tokens) as total_tokens,
    SUM(tu.cost_usd) as total_cost,
    t.status,
    EXTRACT(EPOCH FROM (t.completed_at - t.started_at)) as duration_seconds
FROM tasks t
JOIN token_usage tu ON tu.task_id = t.id
WHERE t.created_at >= NOW() - INTERVAL '7 days'
GROUP BY t.id
ORDER BY total_cost DESC
LIMIT 10;

-- Модели по популярности
SELECT
    model,
    provider,
    COUNT(*) as num_calls,
    SUM(total_tokens) as total_tokens,
    SUM(cost_usd) as total_cost,
    AVG(total_tokens) as avg_tokens
FROM token_usage
WHERE timestamp >= NOW() - INTERVAL '7 days'
GROUP BY model, provider
ORDER BY total_cost DESC;
```

### Результат (example)

```
Top 10 Most Expensive Tasks (Last 7 Days):

task_id                                | agent_id | tokens | cost   | duration
---------------------------------------|----------|--------|--------|----------
a7f3e892-1234-5678-90ab-cdef12345678  | coder    | 15,234 | $0.28  | 45.2s
b8e4f903-2345-6789-01bc-def234567890  | coder    | 12,450 | $0.23  | 128.9s
c9f5g014-3456-7890-12cd-ef3456789012  | coder    | 8,756  | $0.16  | 34.1s
...

Total cost last 7 days: $3.45
Average per day: $0.49
```

---

## Пример 15: Быстрый diagnostic всей системы

### Скрипт

```bash
#!/bin/bash
# scripts/diagnostic.sh

echo "=== Balbes Multi-Agent System Diagnostic ==="
echo ""

echo "1. Infrastructure Services"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep balbes

echo ""
echo "2. Service Health Checks"
curl -s http://localhost:8100/health | jq '.status' && echo "  ✅ Memory Service"
curl -s http://localhost:8101/health | jq '.status' && echo "  ✅ Skills Registry"
curl -s http://localhost:8200/health | jq '.status' && echo "  ✅ Web Backend"

echo ""
echo "3. Agent Status"
psql -h localhost -U balbes -d balbes_agents -t -c "
SELECT
    id,
    status,
    COALESCE(current_task_id::text, 'none') as task,
    tokens_used_today
FROM agents;
"

echo ""
echo "4. Recent Tasks (last 5)"
psql -h localhost -U balbes -d balbes_agents -t -c "
SELECT
    LEFT(id::text, 8) as id,
    agent_id,
    status,
    LEFT(description, 40) as description
FROM tasks
ORDER BY created_at DESC
LIMIT 5;
"

echo ""
echo "5. Token Usage Today"
psql -h localhost -U balbes -d balbes_agents -t -c "
SELECT * FROM v_tokens_today;
"

echo ""
echo "6. Disk Usage"
du -sh data/postgres data/redis data/qdrant data/logs data/coder_output

echo ""
echo "7. Recent Errors (last 10)"
psql -h localhost -U balbes -d balbes_agents -t -c "
SELECT
    timestamp,
    agent_id,
    action,
    LEFT(error_message, 50) as error
FROM action_logs
WHERE status = 'error'
ORDER BY timestamp DESC
LIMIT 10;
"

echo ""
echo "=== Diagnostic Complete ==="
```

### Вывод

```
=== Balbes Multi-Agent System Diagnostic ===

1. Infrastructure Services
balbes-postgres    Up 5 hours (healthy)   0.0.0.0:5432->5432/tcp
balbes-redis       Up 5 hours (healthy)   0.0.0.0:6379->6379/tcp
balbes-rabbitmq    Up 5 hours (healthy)   0.0.0.0:5672->5672/tcp
balbes-qdrant      Up 5 hours (healthy)   0.0.0.0:6333->6333/tcp

2. Service Health Checks
  ✅ Memory Service
  ✅ Skills Registry
  ✅ Web Backend

3. Agent Status
 orchestrator | idle    | none     | 5234
 coder        | working | #a7f3... | 12450

4. Recent Tasks (last 5)
 a7f3e892 | coder | in_progress | Create skill parse_hackernews
 b8e4f903 | coder | completed   | Create skill fetch_weather
 c9f5g014 | coder | completed   | Create skill fetch_quotes

5. Token Usage Today
 coder        | 17684 | 0.34 | 43  | 2026-03-26 15:30:17
 orchestrator | 5234  | 0.11 | 28  | 2026-03-26 15:35:00

6. Disk Usage
156M    data/postgres
2.3M    data/redis
45M     data/qdrant
12M     data/logs
8.2M    data/coder_output

7. Recent Errors (last 10)
(No errors found)

=== Diagnostic Complete ===
```

---

## Пример 16: Типичный день работы системы

```
00:00 - System resets daily token counters
00:05 - Scheduled backup runs (PostgreSQL, Qdrant)

09:30 - User: /status
        Bot: All agents idle

09:35 - User: /task @coder создай скилл для парсинга currency rates
        Coder: работает 2 минуты, создает скилл
        Bot: ✅ Скилл создан (tokens: 6,234)

10:15 - User: /task @coder создай скилл для отправки email
        Coder: работает 1.5 минуты, создает скилл
        Bot: ✅ Скилл создан (tokens: 4,890)

12:00 - Background: token budget check
        Coder: 11,124 / 100,000 (11%)
        Orchestrator: 1,234 / 100,000 (1%)

14:30 - User в Web UI: отправляет задачу через Chat
        Coder: создает скилл analyze_sentiment
        Web UI: real-time updates в Dashboard
        Toast: "✅ Task completed"

16:45 - Coder превышает 80% лимита
        Bot: ⚠️ Token budget alert (82,450 / 100,000)
        User: /model @coder openrouter/gpt-4o-mini

18:30 - User: /tokens
        Bot: Статистика за день
        Total: 89,670 tokens, $1.67

23:55 - System: Все агенты idle
        Логи ротируются (если > 100MB)
```

**Итого за день**:
- 7 задач выполнено
- 89,670 токенов использовано
- $1.67 стоимость
- 0 критических ошибок
- 1 fallback на дешевую модель
- 7 новых скиллов создано

---

## Пример 17: Интеграция нового скилла в систему

### После того как Coder создал скилл

**1. Проверка кода**
```bash
# Review созданного кода
cat data/coder_output/skills/parse_hackernews/implementation.py
cat data/coder_output/skills/parse_hackernews/skill.yaml
cat data/coder_output/skills/parse_hackernews/README.md

# Запуск тестов вручную (для уверенности)
cd data/coder_output/skills/parse_hackernews
pytest test_implementation.py -v
```

**2. Копирование в проект**
```bash
# Copy implementation
cp data/coder_output/skills/parse_hackernews/implementation.py \
   shared/skills/parse_hackernews.py

# Copy YAML definition
cp data/coder_output/skills/parse_hackernews/skill.yaml \
   config/skills/parse_hackernews.yaml

# Copy tests
cp data/coder_output/skills/parse_hackernews/test_implementation.py \
   tests/unit/test_skills/test_parse_hackernews.py
```

**3. Регистрация скилла**
```bash
# Restart Skills Registry (подхватит новый YAML)
# Dev:
# Ctrl+C и перезапустить

# Prod:
docker compose restart skills-registry
```

**4. Назначение скилла агенту**

Добавить в `config/agents/blogger.yaml` (когда будет):
```yaml
skills:
  - parse_hackernews
  - ...
```

**5. Использование**
```
/task @blogger создай пост с топ-3 новостями с HackerNews
```

Blogger теперь может использовать `parse_hackernews` скилл!

---

## Пример 18: Emergency Procedures

### Сценарий 1: Все агенты перестали отвечать

```bash
# 1. Проверить что RabbitMQ работает
docker ps | grep rabbitmq
curl http://localhost:15672/api/health/checks/alarms

# 2. Проверить очереди
docker exec balbes-rabbitmq rabbitmqctl list_queues

# 3. Если очереди переполнены - очистить
docker exec balbes-rabbitmq rabbitmqctl purge_queue orchestrator.tasks
docker exec balbes-rabbitmq rabbitmqctl purge_queue coder.tasks

# 4. Restart агентов
docker compose restart orchestrator coder

# 5. Проверка
/status
```

### Сценарий 2: PostgreSQL переполнен

```bash
# 1. Проверить размер
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT pg_size_pretty(pg_database_size('balbes_agents'));
"

# 2. Найти самые большие таблицы
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass))
FROM pg_tables WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::regclass) DESC;
"

# 3. Очистка старых данных (> 30 дней)
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
DELETE FROM action_logs WHERE timestamp < NOW() - INTERVAL '30 days';
DELETE FROM token_usage WHERE timestamp < NOW() - INTERVAL '30 days';
VACUUM FULL;
"

# 4. Если все еще проблемы - увеличить disk на VPS
```

### Сценарий 3: Token costs слишком высокие

```bash
# 1. Анализ кто тратит
psql -h localhost -U balbes -d balbes_agents -c "
SELECT
    agent_id,
    model,
    SUM(total_tokens) as tokens,
    SUM(cost_usd) as cost,
    COUNT(*) as calls
FROM token_usage
WHERE timestamp >= NOW() - INTERVAL '24 hours'
GROUP BY agent_id, model
ORDER BY cost DESC;
"

# 2. Переключить на дешевые модели
/model @coder openrouter/gpt-4o-mini
/model @orchestrator openrouter/gpt-4o-mini

# 3. Уменьшить лимиты в config/agents/*.yaml
token_limits:
  daily: 50000  # Было 100000
  hourly: 7500  # Было 15000

# 4. Restart агентов для применения
docker compose restart coder orchestrator
```

---

Эти примеры показывают реальные сценарии использования системы. По мере разработки и использования будут добавляться новые примеры.
