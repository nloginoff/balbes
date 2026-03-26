# Руководство по агентам

## Общая информация

Все агенты наследуют `BaseAgent` и имеют единый интерфейс для:
- LLM вызовов (через multi-provider client)
- Работы с памятью (быстрая + долговременная)
- Выполнения скиллов
- Коммуникации через Message Bus
- Логирования действий

---

## BaseAgent Class

### Описание

Базовый класс для всех агентов, обеспечивающий стандартный набор возможностей.

### Атрибуты

```python
class BaseAgent:
    agent_id: str                      # Уникальный идентификатор
    name: str                          # Человекочитаемое имя
    config: AgentConfig                # Конфигурация из YAML
    llm_client: LLMClient              # Multi-provider LLM client
    memory_client: MemoryClient        # Клиент для Memory Service
    skills_registry: SkillsRegistry    # Клиент для Skills Registry
    message_bus: MessageBus            # RabbitMQ wrapper
    logger: Logger                     # Структурированный логгер
    current_task: Optional[Task]       # Текущая задача
```

### Ключевые методы

```python
async def start(self):
    """
    Запуск агента:
    - Подключение к RabbitMQ
    - Регистрация в Memory Service
    - Загрузка скиллов
    - Начало прослушивания очереди
    """

async def stop(self):
    """Graceful shutdown"""

async def process_message(self, message: Message):
    """
    Обработка входящего сообщения:
    - task: создать и выполнить задачу
    - query: ответить на запрос
    - notification: обработать уведомление
    """

async def execute_task(self, task: Task) -> TaskResult:
    """
    Основной метод выполнения задачи.
    Должен быть переопределен в наследниках.
    """
    raise NotImplementedError

async def execute_skill(
    self,
    skill_name: str,
    params: dict
) -> Any:
    """
    Выполнение скилла через Skills Registry.
    Автоматически логирует выполнение.
    """

async def llm_complete(
    self,
    messages: List[Dict],
    max_tokens: int = None,
    temperature: float = None
) -> LLMResponse:
    """
    LLM completion с автоматическим:
    - Токен-трекингом
    - Fallback при ошибке
    - Переключением на cheap при превышении лимита
    """

async def save_to_memory(
    self,
    content: str,
    scope: str = "personal",
    metadata: dict = None
):
    """Сохранение в долговременную память (Qdrant)"""

async def query_memory(
    self,
    query: str,
    scope: str = "personal",
    limit: int = 5
) -> List[MemorySearchResult]:
    """Поиск в долговременной памяти"""

async def set_context(
    self,
    key: str,
    value: Any,
    ttl: int = 3600
):
    """Сохранение в быструю память (Redis)"""

async def get_context(self, key: str) -> Optional[Any]:
    """Получение из быстрой памяти"""

async def add_to_history(self, role: str, content: str):
    """Добавление в историю диалога"""

async def get_history(self, limit: int = 50) -> List[ConversationMessage]:
    """Получение истории диалога"""

async def send_message(
    self,
    to_agent: str,
    message_type: str,
    payload: dict,
    correlation_id: UUID = None
):
    """Отправка сообщения другому агенту"""

async def log_action(
    self,
    action: str,
    parameters: dict = None,
    result: dict = None,
    status: str = "success",
    duration_ms: int = 0
):
    """Логирование действия"""
```

---

## Orchestrator Agent

### Описание

Главный координирующий агент. Точка входа для пользователя через Telegram и интерфейс для Web UI.

### Ответственности

1. **Прием команд** от пользователя (Telegram + Web UI)
2. **Маршрутизация задач** к специализированным агентам
3. **Мониторинг** состояния всех агентов
4. **Уведомления** пользователя о событиях
5. **Координация** взаимодействий между агентами (при необходимости)

### Конфигурация

```yaml
# config/agents/orchestrator.yaml
agent_id: orchestrator
name: "Orchestrator"
description: "Main coordinating agent"

llm_settings:
  primary_model: "openrouter/anthropic/claude-3.5-sonnet"
  fallback_models:
    - "openrouter/openai/gpt-4-turbo"
    - "aitunnel/gpt-4-turbo"
    - "openrouter/meta-llama/llama-3.1-8b-instruct:free"
  max_tokens: 4000
  temperature: 0.7

token_limits:
  daily: 100000
  hourly: 15000
  alert_threshold: 0.8

skills:
  - send_telegram_message
  - create_task
  - get_agent_status
  - query_logs
  - query_memory
  - send_message
  - search_web

instructions: |
  Ты - Orchestrator, главный координирующий агент системы.

  Твои обязанности:
  1. Принимать команды от пользователя через Telegram
  2. Анализировать запросы и определять нужного агента
  3. Создавать задачи для специализированных агентов
  4. Отслеживать выполнение задач
  5. Сообщать результаты пользователю

  Доступные агенты:
  - @coder - создание Python скиллов и кода

  Стиль общения:
  - Будь кратким и четким
  - Используй эмодзи для статусов (🟢 ✅ ⚠️ ❌)
  - Всегда подтверждай получение команды
  - Сообщай о прогрессе длительных задач

  При получении команды:
  1. Подтверди: "✅ Команда принята"
  2. Определи целевого агента
  3. Создай задачу через Message Bus
  4. Когда агент завершит - сообщи результат

  При ошибках:
  - Логируй детали
  - Сообщи пользователю понятно
  - Предложи альтернативу если возможно

  При токен-алертах:
  - Немедленно уведоми пользователя
  - Укажи какой агент и процент использования
  - При автопереключении на cheap model - сообщи
```

### Telegram Commands Handler

```python
# services/orchestrator/handlers/task.py

async def handle_task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает команду /task @agent <description>

    Example: /task @coder создай скилл для парсинга HackerNews
    """

    # 1. Парсинг команды
    text = update.message.text
    parts = text.split(maxsplit=2)

    if len(parts) < 3:
        await update.message.reply_text("❌ Формат: /task @agent <описание>")
        return

    agent_mention = parts[1]  # @coder
    description = parts[2]

    # 2. Извлечение agent_id
    agent_id = agent_mention.lstrip('@')

    # 3. Валидация агента
    agent_status = await orchestrator.get_agent_status(agent_id)
    if not agent_status:
        await update.message.reply_text(f"❌ Агент {agent_mention} не найден")
        return

    if agent_status.status == "working":
        await update.message.reply_text(
            f"⚠️ Агент {agent_mention} занят задачей {agent_status.current_task_id}\n"
            f"Хотите остановить? /stop {agent_mention}"
        )
        return

    # 4. Создание задачи
    task = await orchestrator.create_task(
        agent_id=agent_id,
        description=description,
        created_by="user"
    )

    # 5. Подтверждение
    await update.message.reply_text(
        f"✅ Задача #{task.id} создана для {agent_mention}\n"
        f"Статус: /task_status {task.id}"
    )
```

### Пример работы

**Сценарий: Создание скилла**

```
User → Telegram:
/task @coder создай скилл для парсинга HackerNews. Должен возвращать топ-10 постов

Orchestrator → Telegram:
✅ Задача #abc-123 создана для @coder

[5 секунд спустя]

Orchestrator → Telegram:
🟡 @coder начал работу над задачей #abc-123

[2 минуты спустя]

Orchestrator → Telegram:
✅ @coder завершил задачу #abc-123
Создан скилл: parse_hackernews
Путь: /data/coder_output/skills/parse_hackernews/
Тесты: ✅ Пройдены (3/3)
Токены: 5,234
```

---

## Coder Agent

### Описание

Специализированный агент для написания Python кода, в первую очередь - создания новых скиллов для других агентов.

### Ответственности MVP

1. **Создание скиллов**: Python код + YAML описание + pytest тесты
2. **Анализ требований**: понимание что нужно сделать
3. **Поиск примеров**: использование памяти для поиска похожих решений
4. **Тестирование**: автоматический запуск pytest
5. **Retry логика**: до 3 попыток исправить код при провале тестов
6. **Документирование**: создание README для скилла

### НЕ входит в MVP

- Создание новых агентов
- Git операции (commit, push, PR)
- Автоматический деплой
- Code review существующего кода
- Рефакторинг
- Обновление существующих скиллов

### Конфигурация

```yaml
# config/agents/coder.yaml
agent_id: coder
name: "Coder Agent"
description: "Python programming agent for creating skills"

llm_settings:
  primary_model: "openrouter/anthropic/claude-3.5-sonnet"
  fallback_models:
    - "openrouter/openai/gpt-4-turbo"
    - "aitunnel/gpt-4-turbo"
  max_tokens: 8000  # Больше для кода
  temperature: 0.3  # Низкая для детерминизма

token_limits:
  daily: 100000
  hourly: 15000
  alert_threshold: 0.8

skills:
  - read_file
  - write_file
  - execute_command
  - search_web
  - query_memory
  - send_message

constraints:
  max_retries: 3
  test_timeout: 60  # seconds для pytest
  output_base_path: "/data/coder_output"
```

### Workflow создания скилла

```python
async def create_skill(self, description: str, requirements: str = None):
    """
    1. Анализ требований
       - Что должен делать скилл
       - Какие параметры нужны
       - Какие библиотеки использовать

    2. Поиск в памяти
       - query_memory("similar skill implementations")
       - Находит примеры похожих скиллов

    3. Генерация структуры
       - Определяет имя скилла (snake_case)
       - Планирует параметры
       - Выбирает permissions

    4. Генерация кода
       LLM call с промптом:
       "Create Python async function for skill {name}
        Requirements: {description}
        Parameters: {params}
        Must include: type hints, docstring, error handling
        Examples from memory: {examples}"

    5. Генерация YAML
       Создает skill.yaml с описанием параметров

    6. Генерация тестов
       LLM call:
       "Create pytest tests for this skill.
        Minimum 3 tests: success case, error case, edge case"

    7. Сохранение файлов
       - /data/coder_output/skills/{skill_name}/implementation.py
       - /data/coder_output/skills/{skill_name}/skill.yaml
       - /data/coder_output/skills/{skill_name}/test_implementation.py
       - /data/coder_output/skills/{skill_name}/README.md

    8. Запуск тестов
       execute_command(f"pytest {test_file} -v")

    9. Обработка результата
       If tests pass:
         - Сохранить в память успешный результат
         - Отправить success notification

       If tests fail:
         - Проанализировать ошибки
         - Исправить код (LLM call с ошибками)
         - Retry (до max_retries раз)
         - Если все попытки неудачны - сообщить об ошибке

    10. Финализация
        - UPDATE task status в PostgreSQL
        - Отправить результат Orchestrator через RabbitMQ
        - Сохранить experience в память
    """
```

### Промпты

**System Prompt (из instructions)**:

```
Ты - агент-программист на Python. Специализация: создание скиллов (функций) для других агентов.

ВАЖНО:
- Используй async/await для всех I/O операций
- Всегда добавляй type hints
- Пиши Google-style docstrings
- Обрабатывай ошибки gracefully (try-except)
- Следуй PEP 8
- Используй современный Python (3.13+)

Структура скилла:
```python
async def skill_name(
    context: SkillContext,
    param1: str,
    param2: int = 10
) -> dict:
    """
    Brief description.

    Args:
        param1: Description
        param2: Description

    Returns:
        dict: Description of return value

    Raises:
        ValueError: When ...
        TimeoutError: When ...
    """
    try:
        # Implementation
        result = ...
        return {"status": "success", "data": result}
    except Exception as e:
        context.logger.error(f"Skill failed: {e}")
        raise
```

Всегда создавай минимум 3 теста:
1. Успешный кейс
2. Обработка ошибки
3. Edge case
```

**Prompt для генерации кода**:

```
Create a Python async function for a skill with the following requirements:

Name: {skill_name}
Description: {description}
Parameters: {parameters}
Required permissions: {permissions}
Additional requirements: {requirements}

Similar examples from my memory:
{memory_examples}

Please provide:
1. Complete implementation with type hints and docstring
2. Proper error handling
3. Return dict with status and data

Use these libraries if needed: {suggested_libraries}
```

**Prompt для генерации тестов**:

```
Create pytest tests for this skill implementation:

{implementation_code}

Requirements:
- Minimum 3 tests
- Use pytest fixtures
- Test success case
- Test error handling
- Test edge cases
- Use pytest.mark.asyncio for async tests
```

### Пример выполнения задачи

```python
# services/coder/agent.py

class CoderAgent(BaseAgent):

    async def execute_task(self, task: Task) -> TaskResult:
        """Главный метод выполнения задачи"""

        start_time = time.time()
        description = task.description

        try:
            # 1. Анализ требований
            await self.log_action("task_started", {"task_id": str(task.id)})

            # 2. Поиск в памяти
            memory_results = await self.query_memory(
                query=f"creating skills similar to: {description}",
                limit=3
            )

            # 3. Генерация скилла
            skill_data = await self._generate_skill(description, memory_results)

            # 4. Сохранение файлов
            output_path = f"/data/coder_output/skills/{skill_data['name']}"
            await self._save_skill_files(output_path, skill_data)

            # 5. Запуск тестов
            test_result = await self._run_tests(output_path)

            # 6. Retry если не прошли
            retry_count = 0
            while not test_result['passed'] and retry_count < self.config.constraints['max_retries']:
                retry_count += 1
                await self.log_action("test_retry", {"attempt": retry_count})

                # Исправляем код на основе ошибок
                skill_data = await self._fix_skill(skill_data, test_result['errors'])
                await self._save_skill_files(output_path, skill_data)
                test_result = await self._run_tests(output_path)

            # 7. Результат
            if test_result['passed']:
                # Сохранить успех в память
                await self.save_to_memory(
                    content=f"Successfully created skill {skill_data['name']}. {description}. Tests passed.",
                    metadata={
                        "task_id": str(task.id),
                        "skill_name": skill_data['name'],
                        "tags": ["skill", "success"],
                        "retries": retry_count
                    }
                )

                duration = int((time.time() - start_time) * 1000)

                return TaskResult(
                    task_id=task.id,
                    status="success",
                    data={
                        "skill_name": skill_data['name'],
                        "output_path": output_path,
                        "tests_passed": True,
                        "retries": retry_count
                    },
                    tokens_used=self._get_tokens_used_for_task(task.id),
                    duration_ms=duration
                )
            else:
                # Все попытки неудачны
                error_msg = f"Failed to create working skill after {retry_count} retries"

                await self.save_to_memory(
                    content=f"Failed to create skill {skill_data['name']}. {description}. {error_msg}",
                    metadata={
                        "task_id": str(task.id),
                        "skill_name": skill_data['name'],
                        "tags": ["skill", "failure"],
                        "error": test_result['errors']
                    }
                )

                return TaskResult(
                    task_id=task.id,
                    status="error",
                    error=error_msg,
                    tokens_used=self._get_tokens_used_for_task(task.id),
                    duration_ms=int((time.time() - start_time) * 1000)
                )

        except Exception as e:
            await self.log_action("task_failed", {"error": str(e)}, status="error")
            return TaskResult(
                task_id=task.id,
                status="error",
                error=str(e),
                tokens_used=0,
                duration_ms=int((time.time() - start_time) * 1000)
            )
```

### Особенности

**Token Management**:
- Использует больше токенов чем Orchestrator (генерация кода)
- Лимит выше (100K/день)
- Температура ниже (0.3) для детерминизма

**Memory Usage**:
- Активно использует долговременную память для поиска примеров
- Сохраняет каждый созданный скилл в память
- Учится на успехах и неудачах

**Output Structure**:
```
/data/coder_output/skills/parse_hackernews/
├── implementation.py       # Код скилла
├── skill.yaml              # Описание для Skills Registry
├── test_implementation.py  # Pytest тесты
├── README.md               # Документация
└── requirements.txt        # Дополнительные зависимости (если нужны)
```

---

## Команды Telegram Bot (детально)

### /start

```
Пользователь: /start

Бот:
👋 Привет! Я Orchestrator - главный агент системы.

Доступные агенты:
🟢 @coder - создание Python скиллов

Основные команды:
/status - статус агентов
/task @agent <описание> - создать задачу
/tokens - статистика токенов
/help - полная справка

Пример:
/task @coder создай скилл для парсинга HackerNews
```

### /status

```
Пользователь: /status

Бот:
📊 Статус агентов:

🟢 orchestrator - idle
   Токены: 5,234 / 100,000 (5%)
   Последняя активность: 2 мин назад

🟡 coder - working
   Задача: #abc-123 "Create skill..."
   Прогресс: Запуск тестов...
   Токены: 12,450 / 100,000 (12%)
   Последняя активность: 5 сек назад

💰 Общий расход сегодня: $0.34
```

### /task

```
Пользователь: /task @coder создай скилл для парсинга HackerNews топ-10 постов

Бот:
✅ Задача #abc-123 создана для @coder
Описание: создай скилл для парсинга HackerNews топ-10 постов
Статус: pending

[5 секунд]
🟡 @coder начал работу

[Можно проверить статус: /task_status abc-123]
```

### /stop

```
Пользователь: /stop @coder

Бот:
⏹️ Остановка задачи для @coder...

[2 секунды]
✅ Задача #abc-123 остановлена
@coder статус: idle
```

### /model

```
Пользователь: /model @coder openrouter/openai/gpt-4-turbo

Бот:
🔄 Смена модели для @coder...

✅ Модель обновлена:
Было: anthropic/claude-3.5-sonnet
Стало: openai/gpt-4-turbo

Новые параметры:
- Context window: 128K tokens
- Cost: ~$0.01 / 1K tokens
```

### /tokens

```
Пользователь: /tokens

Бот:
💰 Статистика токенов за сегодня:

📊 По агентам:
coder:        12,450 / 100,000 (12%) - $0.23
orchestrator:  5,234 / 100,000 (5%)  - $0.11

Всего:        17,684 / 200,000 (9%)  - $0.34

📈 По часам:
14:00 - 6,234 tokens
15:00 - 8,234 tokens
16:00 - 3,216 tokens

Модели:
anthropic/claude-3.5-sonnet - 15,234 tokens (86%)
openai/gpt-4-turbo          -  2,450 tokens (14%)

Детали: https://your-domain.com/tokens
```

### /logs

```
Пользователь: /logs @coder 5

Бот:
📝 Последние 5 действий @coder:

15:32:10 ✅ task_completed
         Task: #abc-123
         Duration: 2m 5s
         Tokens: 5,234

15:32:05 ✅ skill_executed: execute_command
         Command: pytest
         Result: 3 passed

15:31:50 ✅ skill_executed: write_file
         Path: parse_hackernews/test_implementation.py
         Size: 1.2KB

15:31:45 ✅ llm_call
         Model: claude-3.5-sonnet
         Tokens: 1,456
         Cost: $0.02

15:31:40 ✅ skill_executed: query_memory
         Query: "parsing examples"
         Results: 2

Больше логов: https://your-domain.com/agents/coder
```

### /help

```
Пользователь: /help

Бот:
📚 Справка по командам

🤖 Управление агентами:
/status - статус всех агентов
/task @agent <описание> - создать задачу для агента
/stop @agent - остановить текущую задачу агента
/model @agent <provider/model> - сменить LLM модель

📊 Мониторинг:
/tokens - статистика использования токенов
/logs @agent [N] - последние N действий агента (default: 10)
/task_status <task_id> - статус конкретной задачи

⚙️ Система:
/help - эта справка
/ping - проверка работоспособности

💡 Примеры:
/task @coder создай скилл для парсинга HackerNews
/model @coder openrouter/openai/gpt-4-turbo
/logs @coder 20

🌐 Web интерфейс: https://your-domain.com
```

---

## Agent Lifecycle

### Startup Sequence

```python
1. Загрузка конфигурации из YAML
2. Инициализация клиентов:
   - LLMClient (с providers config)
   - MemoryClient (подключение к Memory Service)
   - SkillsRegistry client
   - MessageBus (подключение к RabbitMQ)
3. Регистрация в Memory Service (запись в таблицу agents)
4. Загрузка скиллов из Skills Registry
5. Восстановление состояния (если были незавершенные задачи)
6. Подписка на RabbitMQ очередь
7. Health check: подтверждение готовности
8. Логирование: "Agent {id} started"
```

### Message Processing Loop

```python
while running:
    # 1. Получить сообщение из RabbitMQ
    message = await message_bus.receive()

    # 2. Обновить last_activity
    await memory_client.update_agent_activity(agent_id)

    # 3. Обработать по типу
    if message.type == "task":
        task = await create_task_from_message(message)
        asyncio.create_task(execute_task(task))  # Non-blocking

    elif message.type == "query":
        response = await handle_query(message)
        await send_message(message.from_agent, "response", response)

    elif message.type == "notification":
        await handle_notification(message)

    # 4. Подтвердить обработку
    await message_bus.ack(message)
```

### Shutdown Sequence

```python
1. Установить флаг остановки (running = False)
2. Дождаться завершения текущей задачи (если есть) или timeout (60s)
3. Сохранить состояние в PostgreSQL
4. Отключиться от RabbitMQ gracefully
5. Закрыть соединения с сервисами
6. Логирование: "Agent {id} stopped gracefully"
```

---

## Agent Communication Patterns

### Pattern 1: Request-Response

```python
# Orchestrator запрашивает информацию у Coder
correlation_id = uuid4()

await orchestrator.send_message(
    to_agent="coder",
    message_type="query",
    payload={"question": "How many skills have you created?"},
    correlation_id=correlation_id
)

# Orchestrator ждет ответа
response = await orchestrator.wait_for_response(
    correlation_id=correlation_id,
    timeout=10
)

# Coder получает query и отвечает
# (в своем message handler)
if message.type == "query":
    answer = await self.handle_query(message.payload)
    await self.send_message(
        to_agent=message.from_agent,
        message_type="response",
        payload={"answer": answer},
        correlation_id=message.correlation_id
    )
```

### Pattern 2: Fire-and-Forget (Task Assignment)

```python
# Orchestrator создает задачу для Coder
await orchestrator.send_message(
    to_agent="coder",
    message_type="task",
    payload={
        "task_id": "abc-123",
        "description": "Create skill..."
    }
)

# Orchestrator НЕ ждет ответа немедленно
# Coder отправит notification когда завершит

# Позже Coder отправляет результат:
await coder.send_message(
    to_agent="orchestrator",
    message_type="notification",
    payload={
        "task_id": "abc-123",
        "status": "completed",
        "result": {...}
    }
)
```

### Pattern 3: Broadcast

```python
# Orchestrator рассылает всем (например, смена конфигурации)
await orchestrator.broadcast_message(
    message_type="notification",
    payload={
        "type": "config_updated",
        "message": "Token limits updated, reloading configs..."
    }
)

# Все агенты получают и обрабатывают
```

---

## Agent State Machine

```
┌─────────┐
│  idle   │ ←──────────────────┐
└────┬────┘                    │
     │ task received           │
     ↓                         │ task completed/failed
┌─────────┐                    │
│ working │ ───────────────────┘
└────┬────┘
     │ error occurred
     ↓
┌─────────┐
│  error  │ ──→ manual intervention → idle
└─────────┘
     ↓ auto-recovery after N seconds
   idle

┌─────────┐
│ paused  │ ←─→ manual pause/resume
└─────────┘
```

**Transitions**:
- `idle → working`: task received
- `working → idle`: task completed successfully
- `working → error`: unrecoverable error
- `error → idle`: manual recovery or auto-recovery
- `* → paused`: manual pause (admin command)
- `paused → idle`: manual resume

---

## Token Budget Management

### Token Tracking Flow

```python
# При каждом LLM call:

1. LLMClient.complete() вызывается
2. Проверка текущего бюджета:
   daily_used = await redis.get(f"token_budget:{agent_id}:daily")
   if daily_used >= daily_limit:
       → switch to cheap model
       → send alert to Telegram
3. Выполнение LLM call
4. Получение ответа с token counts
5. Запись в PostgreSQL (token_usage table)
6. Увеличение счетчиков в Redis:
   await redis.incr(f"token_budget:{agent_id}:daily", total_tokens)
   await redis.incr(f"token_budget:{agent_id}:hourly", total_tokens)
7. Проверка threshold (80%):
   if (daily_used / daily_limit) >= 0.8 and not alert_sent:
       → send warning to Telegram
       → set flag: token_alert_sent:{agent_id}:daily
```

### Alert Messages

**80% Warning**:
```
⚠️ Token Budget Alert

Agent: @coder
Usage: 80,000 / 100,000 (80%)
Cost today: $0.18
Time: 15:30

Осталось 20% дневного лимита.
Рекомендую переключить на более дешевую модель если задачи не критичны.

/model @coder openrouter/gpt-3.5-turbo
```

**100% Exceeded**:
```
🚨 Token Limit Exceeded!

Agent: @coder
Usage: 100,234 / 100,000 (100%)
Cost today: $0.23

Агент автоматически переключен на дешевую модель:
meta-llama/llama-3.1-8b-instruct:free

Качество ответов может быть ниже.
Для восстановления премиум модели:
/model @coder openrouter/anthropic/claude-3.5-sonnet
```

---

## Best Practices для Agents

### 1. Efficient Context Management

```python
# ❌ Плохо: загружать всю историю
history = await self.get_history(limit=1000)  # Too much

# ✅ Хорошо: только релевантное
history = await self.get_history(limit=10)  # Last 10 messages
relevant_memories = await self.query_memory(query, limit=3)  # Top 3 matches
```

### 2. Proper Error Handling

```python
# ❌ Плохо: падать при ошибке
result = await self.execute_skill("write_file", params)

# ✅ Хорошо: обрабатывать gracefully
try:
    result = await self.execute_skill("write_file", params)
except PermissionError as e:
    await self.log_action("skill_failed", {"error": str(e)}, status="error")
    return TaskResult(status="error", error=f"Permission denied: {e}")
except Exception as e:
    await self.log_action("skill_failed", {"error": str(e)}, status="error")
    return TaskResult(status="error", error=f"Unexpected error: {e}")
```

### 3. Memory Best Practices

```python
# Сохранять успехи для обучения
if task_successful:
    await self.save_to_memory(
        content=f"Completed: {task.description}. Approach: {approach}. Result: {result}",
        metadata={
            "task_id": str(task.id),
            "tags": ["success", task_type],
            "approach": approach,
            "tokens_used": tokens
        }
    )

# Сохранять неудачи для избегания повторений
if task_failed:
    await self.save_to_memory(
        content=f"Failed: {task.description}. Error: {error}. Attempted: {approach}",
        metadata={
            "task_id": str(task.id),
            "tags": ["failure", task_type],
            "error_type": type(error).__name__
        }
    )
```

### 4. Token Conservation

```python
# Минимизировать размер промпта
messages = [
    {"role": "system", "content": self.config.instructions},
    # Добавлять только релевантный контекст:
    *relevant_history[-5:],  # Последние 5 сообщений, не все
    *relevant_memories,      # Топ-3 примера, не все
    {"role": "user", "content": task.description}
]

# Использовать streaming только если нужно
response = await self.llm_complete(messages, stream=False)
```

### 5. Logging Best Practices

```python
# Логировать ключевые моменты
await self.log_action("task_started", {"task_id": str(task.id)})
await self.log_action("llm_call", {"model": model, "tokens": tokens})
await self.log_action("skill_executed", {"skill": skill_name, "result": result})
await self.log_action("task_completed", {"task_id": str(task.id), "duration": duration})

# НЕ логировать каждую мелочь (избыточно):
# await self.log_action("variable_set", {"var": "x", "value": 5})  # ❌
```

---

## Adding New Agents (для будущего)

### Checklist

1. ✅ Создать директорию `services/{agent_name}/`
2. ✅ Создать класс агента наследующий `BaseAgent`
3. ✅ Создать конфиг `config/agents/{agent_name}.yaml`
4. ✅ Определить специфичные скиллы (если нужны)
5. ✅ Реализовать `execute_task()` метод
6. ✅ Создать Dockerfile
7. ✅ Добавить в docker-compose.prod.yml
8. ✅ Зарегистрировать в PostgreSQL (таблица agents)
9. ✅ Создать RabbitMQ очередь
10. ✅ Обновить Orchestrator (добавить в список known agents)
11. ✅ Написать тесты
12. ✅ Обновить документацию

### Template для нового агента

```python
# services/{agent_name}/agent.py

from shared.base_agent import BaseAgent
from shared.models import Task, TaskResult

class NewAgent(BaseAgent):
    """
    Agent description.

    Responsibilities:
    - Responsibility 1
    - Responsibility 2
    """

    async def execute_task(self, task: Task) -> TaskResult:
        """
        Main task execution logic.

        Args:
            task: Task to execute

        Returns:
            TaskResult with status and data
        """
        try:
            await self.log_action("task_started", {"task_id": str(task.id)})

            # Your implementation here
            result = await self._do_work(task)

            await self.log_action("task_completed", {
                "task_id": str(task.id),
                "result": result
            })

            return TaskResult(
                task_id=task.id,
                status="success",
                data=result,
                tokens_used=self._get_tokens_for_task(task.id),
                duration_ms=...
            )

        except Exception as e:
            await self.log_action("task_failed", {
                "task_id": str(task.id),
                "error": str(e)
            }, status="error")

            return TaskResult(
                task_id=task.id,
                status="error",
                error=str(e),
                tokens_used=0,
                duration_ms=...
            )

    async def _do_work(self, task: Task):
        """Implement your agent logic here"""
        pass
```

---

## Troubleshooting

### Agent не запускается

**Проверить**:
1. Доступность зависимых сервисов (RabbitMQ, Memory Service)
2. Конфигурация в `config/agents/{agent}.yaml` корректна
3. Переменные окружения установлены
4. Логи агента: `tail -f data/logs/{agent}.log`

### Agent зависает

**Возможные причины**:
1. Бесконечный цикл в задаче (проверить логи)
2. Ожидание ответа от недоступного сервиса (timeout?)
3. Memory leak (проверить использование памяти)
4. Deadlock в async коде

**Решение**:
- Остановить задачу: `/stop @agent`
- Проверить логи
- При необходимости перезапустить агента

### Agent превышает токен-лимиты

**Причины**:
1. Слишком большой контекст (загружает много истории)
2. Много retry при ошибках
3. Неэффективные промпты

**Решение**:
- Оптимизировать загрузку контекста
- Уменьшить max_retries
- Улучшить промпты
- Временно переключить на дешевую модель

### Задача выполняется слишком долго

**Timeout**: 10 минут (по умолчанию)

**Если превышен**:
- Автоматическая отмена
- Error notification в Telegram
- Лог с деталями

**Решение**:
- Проанализировать логи - где застряло
- Оптимизировать задачу (разбить на подзадачи)
- Увеличить timeout в конфиге (если обоснованно)
