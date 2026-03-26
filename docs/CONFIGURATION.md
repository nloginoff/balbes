# Конфигурация системы

## Environment Variables

### .env.example

```bash
# =============================================================================
# LLM Providers
# =============================================================================
OPENROUTER_API_KEY=sk-or-v1-your-key-here
AITUNNEL_API_KEY=your-aitunnel-key-here

# =============================================================================
# Telegram Bot
# =============================================================================
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_USER_ID=123456789

# =============================================================================
# Web UI Authentication
# =============================================================================
WEB_AUTH_TOKEN=your-secure-random-token-here-min-32-chars
JWT_SECRET=your-jwt-secret-key-min-32-chars
JWT_EXPIRATION_HOURS=24

# =============================================================================
# Databases
# =============================================================================
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=balbes_agents
POSTGRES_USER=balbes
POSTGRES_PASSWORD=your-strong-password-here

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=

RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_MANAGEMENT_PORT=15672

# =============================================================================
# Service Ports
# =============================================================================
ORCHESTRATOR_PORT=8000
CODER_PORT=8001
MEMORY_SERVICE_PORT=8100
SKILLS_REGISTRY_PORT=8101
WEB_BACKEND_PORT=8200
WEB_FRONTEND_PORT=5173

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_DIR=./data/logs
LOG_FORMAT=json  # json or text
LOG_ROTATION_SIZE=100MB
LOG_RETENTION_DAYS=7

# =============================================================================
# Token Limits (defaults, can be overridden per agent in config)
# =============================================================================
DEFAULT_DAILY_TOKEN_LIMIT=100000
DEFAULT_HOURLY_TOKEN_LIMIT=15000
TOKEN_ALERT_THRESHOLD=0.8  # Alert at 80%

# =============================================================================
# Performance
# =============================================================================
TASK_TIMEOUT_SECONDS=600  # 10 minutes
MAX_RETRIES=3
RETRY_DELAY_SECONDS=5
CONNECTION_POOL_SIZE=10

# =============================================================================
# Development
# =============================================================================
DEBUG=false
RELOAD=false  # Hot reload для uvicorn
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## config/providers.yaml

```yaml
# Multi-provider LLM configuration

providers:
  openrouter:
    api_key: ${OPENROUTER_API_KEY}
    base_url: "https://openrouter.ai/api/v1"
    timeout: 60
    headers:
      HTTP-Referer: "https://your-domain.com"  # Для статистики в OpenRouter
      X-Title: "Balbes Multi-Agent System"

    models:
      - id: "anthropic/claude-3.5-sonnet"
        display_name: "Claude 3.5 Sonnet"
        cost_per_1k_tokens: 0.015
        context_window: 200000
        capabilities: ["code", "reasoning", "long_context"]
        recommended_for: ["coder", "orchestrator"]

      - id: "openai/gpt-4-turbo"
        display_name: "GPT-4 Turbo"
        cost_per_1k_tokens: 0.01
        context_window: 128000
        capabilities: ["code", "reasoning"]
        recommended_for: ["coder", "orchestrator"]

      - id: "openai/gpt-4o-mini"
        display_name: "GPT-4o Mini"
        cost_per_1k_tokens: 0.0005
        context_window: 128000
        capabilities: ["basic", "fast"]
        recommended_for: ["cheap_fallback"]

      - id: "meta-llama/llama-3.1-8b-instruct:free"
        display_name: "Llama 3.1 8B (Free)"
        cost_per_1k_tokens: 0.0
        context_window: 8192
        capabilities: ["basic"]
        recommended_for: ["free_fallback"]

  aitunnel:
    api_key: ${AITUNNEL_API_KEY}
    base_url: "https://api.aitunnel.com/v1"
    timeout: 60

    models:
      - id: "gpt-4-turbo"
        display_name: "GPT-4 Turbo"
        cost_per_1k_tokens: 0.01
        context_window: 128000
        capabilities: ["code", "reasoning"]

# Fallback strategy
fallback_strategy:
  # Что делать при недоступности модели
  on_error: "next_in_chain"
  max_fallback_attempts: 3

  # Что делать при превышении токен-лимита
  on_token_limit: "switch_to_cheap"

  # Что делать при rate limit от провайдера
  on_rate_limit: "wait_and_retry"
  rate_limit_wait_seconds: 60

# Default fallback chain (если не указано в agent config)
default_fallback_chain:
  - provider: openrouter
    model: "anthropic/claude-3.5-sonnet"

  - provider: openrouter
    model: "openai/gpt-4-turbo"

  - provider: aitunnel
    model: "gpt-4-turbo"

  - provider: openrouter
    model: "openai/gpt-4o-mini"

  - provider: openrouter
    model: "meta-llama/llama-3.1-8b-instruct:free"

# Cheap models (для автопереключения при превышении лимита)
cheap_models:
  - provider: openrouter
    model: "openai/gpt-4o-mini"

  - provider: openrouter
    model: "meta-llama/llama-3.1-8b-instruct:free"

# Token limits (defaults)
token_limits:
  daily_limit_per_agent: 100000
  hourly_limit_per_agent: 15000
  alert_threshold: 0.8  # 80%
  action_on_exceeded: "switch_to_cheap"  # или "pause"

# Embeddings для Qdrant
embeddings:
  provider: openrouter
  model: "openai/text-embedding-3-small"
  dimensions: 1536
  cost_per_1k_tokens: 0.0001
  batch_size: 100  # Для оптимизации (batch embeddings)

# Notifications
notifications:
  telegram_user_id: ${TELEGRAM_USER_ID}

  triggers:
    - type: token_limit_warning
      threshold: 0.8
      message_template: "⚠️ Agent {agent_id} использовал {percentage}% дневного лимита токенов ({tokens_used}/{limit})"

    - type: token_limit_exceeded
      message_template: "🚨 Agent {agent_id} превысил лимит! Переключаюсь на {cheap_model}"

    - type: model_fallback
      message_template: "⚠️ Model {model} недоступна для {agent_id}, использую {fallback_model}"

    - type: agent_error
      message_template: "❌ Agent {agent_id} ошибка: {error_message}"

    - type: task_completed
      message_template: "✅ Agent {agent_id} завершил задачу #{task_id}"

    - type: task_failed
      message_template: "❌ Agent {agent_id} провалил задачу #{task_id}: {error}"

# Retry settings
retry:
  max_attempts: 3
  backoff_strategy: "exponential"  # linear, exponential, constant
  initial_delay_seconds: 1
  max_delay_seconds: 30
```

---

## config/base_instructions.yaml

```yaml
# Базовые инструкции для всех агентов

base_instructions: |
  ## Общие правила для всех агентов

  ### 1. Логирование
  - Логируй каждое выполненное действие через self.log_action()
  - Включай: action name, parameters, result, status, duration
  - Используй правильный status: "success" или "error"
  - При ошибке включай error_message с деталями

  ### 2. Работа с памятью
  - Перед началом новой задачи ищи в памяти похожие примеры
  - Сохраняй результаты важных задач в долговременную память
  - Используй scope "personal" для своих данных
  - Используй scope "shared" для информации полезной другим агентам
  - Добавляй подробные metadata и tags для лучшего поиска

  ### 3. Использование токенов
  - Минимизируй размер контекста (только релевантная информация)
  - Не загружай всю историю - только последние 10-20 сообщений
  - При поиске в памяти ограничивай результаты (limit=3-5)
  - Не делай повторные LLM вызовы с одинаковым контекстом
  - При ошибке не делай бесконечные retry (максимум 3)

  ### 4. Коммуникация между агентами
  - Используй correlation_id для связи запрос-ответ
  - Отвечай на query messages в течение разумного времени (< 30s)
  - При отправке task другому агенту не жди ответа синхронно
  - Используй broadcast только для важных системных сообщений

  ### 5. Обработка ошибок
  - Всегда используй try-except для потенциально опасных операций
  - Логируй ошибки с полным traceback
  - Не падай при ошибке - возвращай TaskResult со статусом "error"
  - Информируй Orchestrator об ошибках через send_message

  ### 6. Таймауты и ограничения
  - Максимальное время выполнения задачи: 10 минут
  - Timeout для LLM вызовов: 60 секунд
  - Timeout для skill execution: зависит от скилла (обычно 30s)
  - При длительной задаче отправляй промежуточные статусы

  ### 7. Безопасность
  - Проверяй permissions перед выполнением скилла
  - Валидируй все входные параметры
  - Не выполняй опасные команды (rm -rf, dd, etc)
  - Проверяй пути файлов против whitelist
  - Не выводи в лог sensitive данные (API keys, passwords)

  ### 8. Quality
  - Пиши качественный код (type hints, docstrings)
  - Тестируй результаты перед отправкой
  - Используй async/await правильно
  - Не блокируй event loop

performance_guidelines:
  - connection_timeout: 10
  - read_timeout: 30
  - pool_size: 10
  - max_overflow: 20

error_handling:
  - log_traceback: true
  - notify_on_critical: true
  - auto_recovery_enabled: false  # Manual для MVP
```

---

## config/agents/orchestrator.yaml

```yaml
agent_id: orchestrator
name: "Orchestrator"
description: "Main coordinating agent with Telegram bot"

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
  Ты - Orchestrator, главный координирующий агент системы Balbes Multi-Agent System.

  ## Твоя роль
  Ты - точка входа для пользователя. Принимаешь команды через Telegram и координируешь работу других агентов.

  ## Доступные агенты
  - @coder - создание Python скиллов по описанию

  ## Workflow обработки команд

  ### /task @agent <описание>
  1. Валидируй что агент существует и доступен
  2. Если агент занят - предупреди пользователя
  3. Создай задачу в PostgreSQL (через Memory Service API)
  4. Отправь задачу агенту через RabbitMQ
  5. Подтверди создание: "✅ Задача #{task_id} создана для @{agent}"
  6. Когда получишь notification о завершении - сообщи результат

  ### /status
  1. Запроси статус всех агентов (Memory Service API)
  2. Отформатируй красиво с эмодзи:
     - 🟢 idle
     - 🟡 working (укажи текущую задачу)
     - 🔴 error
     - ⏸️ paused
  3. Добавь информацию о токенах

  ### /tokens
  1. Запроси статистику (Memory Service API)
  2. Покажи по агентам и общее
  3. Добавь стоимость в $
  4. Дай ссылку на детали в Web UI

  ### /model @agent <model>
  1. Валидируй что модель существует в providers.yaml
  2. Обнови конфигурацию агента
  3. Отправь notification агенту о смене модели
  4. Подтверди изменение

  ## Стиль общения
  - Будь кратким и четким
  - Используй эмодзи для улучшения восприятия:
    - ✅ успех
    - ⚠️ предупреждение
    - ❌ ошибка
    - 🟢🟡🔴 статусы
    - 💰 токены/деньги
    - 📊 статистика
  - Подтверждай получение каждой команды
  - Сообщай о прогрессе длительных операций

  ## Обработка уведомлений от других агентов
  - task_completed → сообщи пользователю с деталями
  - task_failed → сообщи об ошибке, предложи retry
  - token_alert → сразу перешли пользователю
  - agent_error → уведоми и предложи /status для деталей

  ## Приоритеты
  1. Быстрота ответа пользователю (acknowledge команды сразу)
  2. Точность информации (проверяй факты перед сообщением)
  3. Полезность (давай actionable информацию)

  ## Ошибки
  При любой ошибке:
  1. Логируй детали
  2. Сообщи пользователю понятным языком (не технический traceback)
  3. Предложи альтернативу или решение если возможно
```

---

## config/agents/coder.yaml

```yaml
agent_id: coder
name: "Coder Agent"
description: "Python programming agent specialized in creating skills"

llm_settings:
  primary_model: "openrouter/anthropic/claude-3.5-sonnet"
  fallback_models:
    - "openrouter/openai/gpt-4-turbo"
    - "aitunnel/gpt-4-turbo"
  max_tokens: 8000  # Больше для генерации кода
  temperature: 0.3  # Низкая для детерминизма в коде

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
  test_timeout_seconds: 60
  output_base_path: "/data/coder_output"
  allowed_write_paths:
    - "/data/coder_output/**"
    - "/tmp/**"

instructions: |
  Ты - Coder Agent, специализированный агент-программист на Python.

  ## Твоя главная задача
  Создавать качественные Python скиллы (async функции) по описанию пользователя.

  ## Workflow создания скилла

  ### 1. Анализ требований
  - Пойми что должен делать скилл
  - Определи необходимые параметры
  - Определи какие библиотеки понадобятся
  - Определи какие permissions нужны (network, write, execute)

  ### 2. Поиск примеров в памяти
  ```python
  examples = await self.query_memory(
      query=f"creating skill similar to: {description}",
      limit=3
  )
  ```
  - Изучи найденные примеры
  - Используй успешные паттерны
  - Избегай ошибок из прошлых неудач

  ### 3. Генерация имени скилла
  - Формат: lowercase, snake_case
  - Описательное: глагол + существительное
  - Примеры: parse_hackernews, fetch_weather, analyze_sentiment

  ### 4. Генерация кода скилла

  **Обязательные требования**:
  ```python
  async def skill_name(
      context: SkillContext,
      param1: str,
      param2: int = 10,
  ) -> dict:
      """
      Brief description in one line.

      More detailed description if needed.

      Args:
          context: Skill execution context
          param1: Description of param1
          param2: Description of param2

      Returns:
          dict: {"status": "success", "data": {...}}

      Raises:
          ValueError: When invalid parameters
          TimeoutError: When operation times out
      """
      try:
          # Validation
          if not param1:
              raise ValueError("param1 is required")

          # Implementation
          context.logger.info(f"Starting {skill_name}")
          result = await do_work(param1, param2)

          # Success
          return {
              "status": "success",
              "data": result
          }

      except Exception as e:
          context.logger.error(f"Skill failed: {e}")
          return {
              "status": "error",
              "error": str(e)
          }
  ```

  **Важно**:
  - Всегда async def
  - Всегда type hints
  - Всегда docstring (Google style)
  - Всегда обработка ошибок
  - Всегда return dict со status
  - Используй context.logger для логирования
  - Импорты в начале файла

  ### 5. Генерация YAML описания

  ```yaml
  name: skill_name
  description: Brief description
  version: "1.0.0"
  author: "coder"
  created_at: "2026-03-26T15:00:00Z"

  parameters:
    - name: param1
      type: string
      required: true
      description: Description

  returns:
    type: dict
    description: Success dict with data

  implementation: skills/{skill_name}/implementation.py

  permissions:
    - network

  constraints:
    timeout: 30
    max_retries: 3

  tags:
    - category
    - feature
  ```

  ### 6. Генерация тестов

  **Минимум 3 теста**:
  ```python
  import pytest
  from implementation import skill_name

  @pytest.fixture
  def mock_context():
      # Mock SkillContext
      pass

  @pytest.mark.asyncio
  async def test_skill_success(mock_context):
      """Test successful execution"""
      result = await skill_name(mock_context, param1="value")
      assert result["status"] == "success"
      assert "data" in result

  @pytest.mark.asyncio
  async def test_skill_invalid_params(mock_context):
      """Test error handling with invalid params"""
      result = await skill_name(mock_context, param1="")
      assert result["status"] == "error"

  @pytest.mark.asyncio
  async def test_skill_edge_case(mock_context):
      """Test edge case"""
      # Your edge case
      pass
  ```

  ### 7. Сохранение файлов
  ```python
  output_path = f"/data/coder_output/skills/{skill_name}"

  await self.execute_skill("write_file", {
      "path": f"{output_path}/implementation.py",
      "content": implementation_code
  })

  await self.execute_skill("write_file", {
      "path": f"{output_path}/skill.yaml",
      "content": yaml_content
  })

  await self.execute_skill("write_file", {
      "path": f"{output_path}/test_implementation.py",
      "content": test_code
  })

  await self.execute_skill("write_file", {
      "path": f"{output_path}/README.md",
      "content": readme_content
  })
  ```

  ### 8. Запуск тестов
  ```python
  test_result = await self.execute_skill("execute_command", {
      "command": f"pytest {output_path}/test_implementation.py -v --tb=short"
  })

  # Парсинг результата
  if "passed" in test_result:
      tests_passed = True
  else:
      tests_passed = False
      errors = extract_errors_from_pytest_output(test_result)
  ```

  ### 9. Retry при провале тестов
  ```python
  retry_count = 0
  while not tests_passed and retry_count < 3:
      retry_count += 1

      # LLM call для исправления
      fixed_code = await self.llm_complete([
          {"role": "system", "content": "Fix this code based on test errors"},
          {"role": "user", "content": f"Code:\n{code}\n\nErrors:\n{errors}"}
      ])

      # Сохранить исправленный код
      await save_fixed_code(fixed_code)

      # Запустить тесты снова
      test_result = await run_tests()
  ```

  ### 10. Финализация

  Если тесты прошли:
  ```python
  # Сохранить успех в память
  await self.save_to_memory(
      content=f"Successfully created skill {skill_name}. Description: {description}. Used libraries: {libraries}. Tests passed on attempt {retry_count + 1}.",
      metadata={
          "task_id": str(task.id),
          "skill_name": skill_name,
          "tags": ["skill", "success", *skill_tags],
          "libraries": libraries,
          "retries": retry_count,
          "tokens_used": tokens
      }
  )

  # Уведомить Orchestrator
  await self.send_message(
      to_agent="orchestrator",
      message_type="notification",
      payload={
          "type": "task_completed",
          "task_id": str(task.id),
          "result": {
              "skill_name": skill_name,
              "output_path": output_path,
              "tests_passed": True
          }
      }
  )
  ```

  Если тесты не прошли после всех попыток:
  ```python
  # Сохранить неудачу в память (чтобы избежать в будущем)
  await self.save_to_memory(
      content=f"Failed to create skill {skill_name}. Description: {description}. Error: {error}. Tried {retry_count} times.",
      metadata={
          "task_id": str(task.id),
          "skill_name": skill_name,
          "tags": ["skill", "failure"],
          "error_type": error_type,
          "retries": retry_count
      }
  )

  # Уведомить об ошибке
  await self.send_message(...)
  ```

  ## Важные замечания
  - Не пиши комментарии-очевидности ("# Import library")
  - Используй meaningful variable names
  - Предпочитай композицию над наследованием
  - Используй context managers (async with) для resources
  - Не используй deprecated библиотеки (проверяй актуальность)
  - Следуй PEP 8 и современным Python best practices
```

---

## Skill YAML Examples

### config/skills/search_web.yaml

```yaml
name: search_web
description: Search the web using DuckDuckGo API
version: "1.0.0"
author: "system"
created_at: "2026-03-26T10:00:00Z"

parameters:
  - name: query
    type: string
    required: true
    description: Search query string

  - name: num_results
    type: integer
    required: false
    default: 5
    description: Number of results to return (1-10)

returns:
  type: list
  description: List of search results with title, url, snippet

implementation: shared/skills/search_web.py

permissions:
  - network
  - api_call

constraints:
  timeout: 30
  max_retries: 3
  rate_limit: 10  # requests per minute

tags:
  - search
  - web
  - external_api
```

### config/skills/write_file.yaml

```yaml
name: write_file
description: Write content to a file on disk
version: "1.0.0"
author: "system"
created_at: "2026-03-26T10:00:00Z"

parameters:
  - name: path
    type: string
    required: true
    description: File path (must be in allowed paths)

  - name: content
    type: string
    required: true
    description: Content to write

returns:
  type: dict
  description: "{status, path, size}"

implementation: shared/skills/file_operations.py:write_file

permissions:
  - write

constraints:
  allowed_paths:
    - "/data/coder_output/**"
    - "/tmp/**"
  max_file_size_mb: 10
  timeout: 10

tags:
  - file
  - io
  - write
```

### config/skills/execute_command.yaml

```yaml
name: execute_command
description: Execute a shell command (restricted to whitelist)
version: "1.0.0"
author: "system"
created_at: "2026-03-26T10:00:00Z"

parameters:
  - name: command
    type: string
    required: true
    description: Command to execute (must be in whitelist)

  - name: cwd
    type: string
    required: false
    description: Working directory

  - name: timeout
    type: integer
    required: false
    default: 30
    description: Timeout in seconds

returns:
  type: dict
  description: "{status, stdout, stderr, exit_code}"

implementation: shared/skills/execute.py

permissions:
  - execute

constraints:
  allowed_commands:
    - pytest
    - python
    - ls
    - cat
    - grep
    - head
    - tail
    - echo
  timeout: 60
  max_output_size_kb: 1024

tags:
  - shell
  - command
  - execution
```

---

## Makefile

```makefile
.PHONY: help infra-up infra-down dev-* prod-* db-* test clean

help:
	@echo "Available commands:"
	@echo "  make infra-up        - Start infrastructure (databases)"
	@echo "  make infra-down      - Stop infrastructure"
	@echo "  make dev-orch        - Run Orchestrator (dev)"
	@echo "  make dev-coder       - Run Coder (dev)"
	@echo "  make dev-memory      - Run Memory Service (dev)"
	@echo "  make dev-skills      - Run Skills Registry (dev)"
	@echo "  make dev-web         - Run Web Backend (dev)"
	@echo "  make dev-frontend    - Run Web Frontend (dev)"
	@echo "  make prod-up         - Start all services (prod)"
	@echo "  make prod-down       - Stop all services (prod)"
	@echo "  make prod-logs       - Show production logs"
	@echo "  make db-init         - Initialize databases"
	@echo "  make db-backup       - Backup PostgreSQL"
	@echo "  make test            - Run all tests"
	@echo "  make clean           - Clean temporary files"

# Development - Infrastructure
infra-up:
	docker-compose -f docker-compose.infra.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@docker-compose -f docker-compose.infra.yml ps

infra-down:
	docker-compose -f docker-compose.infra.yml down

infra-logs:
	docker-compose -f docker-compose.infra.yml logs -f

# Development - Services
dev-orch:
	cd services/orchestrator && python main.py

dev-coder:
	cd services/coder && python main.py

dev-memory:
	cd services/memory-service && uvicorn main:app --reload --host 0.0.0.0 --port 8100

dev-skills:
	cd services/skills-registry && uvicorn main:app --reload --host 0.0.0.0 --port 8101

dev-web:
	cd services/web/backend && uvicorn main:app --reload --host 0.0.0.0 --port 8200

dev-frontend:
	cd services/web/frontend && npm run dev

# Production
prod-build:
	docker-compose -f docker-compose.prod.yml build

prod-up:
	docker-compose -f docker-compose.prod.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 10
	@docker-compose -f docker-compose.prod.yml ps

prod-down:
	docker-compose -f docker-compose.prod.yml down

prod-restart:
	docker-compose -f docker-compose.prod.yml restart

prod-logs:
	docker-compose -f docker-compose.prod.yml logs -f

prod-logs-service:
	docker-compose -f docker-compose.prod.yml logs -f $(SERVICE)

# Database
db-init:
	python scripts/init_db.py

db-seed:
	python scripts/seed_skills.py

db-backup:
	@mkdir -p backups
	docker exec balbes-postgres pg_dump -U balbes balbes_agents > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup created in backups/"

db-restore:
	@read -p "Enter backup file: " file; \
	docker exec -i balbes-postgres psql -U balbes balbes_agents < $$file

# Testing
test:
	pytest

test-unit:
	pytest tests/unit -v

test-integration:
	pytest tests/integration -v

test-e2e:
	pytest tests/e2e -v

test-cov:
	pytest --cov=shared --cov=services --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# Code Quality
lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy shared/ services/ --ignore-missing-imports

quality: lint format typecheck

# Cleanup
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf htmlcov/
	rm -rf .coverage

clean-logs:
	find data/logs -name "*.log" -mtime +7 -delete
	@echo "Deleted logs older than 7 days"

clean-all: clean clean-logs
	docker-compose -f docker-compose.infra.yml down -v
	rm -rf data/postgres data/redis data/rabbitmq data/qdrant

# Setup (first time)
setup: infra-up db-init db-seed
	@echo "Setup complete! Run 'make dev-*' to start services"

# Quick start all dev services (requires multiple terminals)
dev-all:
	@echo "Start these in separate terminals:"
	@echo "  Terminal 1: make dev-memory"
	@echo "  Terminal 2: make dev-skills"
	@echo "  Terminal 3: make dev-orch"
	@echo "  Terminal 4: make dev-coder"
	@echo "  Terminal 5: make dev-web"
	@echo "  Terminal 6: make dev-frontend"
```

---

## Docker Configuration

### docker-compose.infra.yml (см. DEPLOYMENT.md)

### Dockerfile Example (Orchestrator)

```dockerfile
# services/orchestrator/Dockerfile

FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared code
COPY ../../shared /app/shared

# Copy service code
COPY . /app

# Copy configs
COPY ../../config /app/config

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Run
CMD ["python", "main.py"]
```

---

## Nginx Configuration

```nginx
# nginx.conf

user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript
               application/x-javascript application/xml+rss
               application/javascript application/json;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
    limit_req_zone $binary_remote_addr zone=web_limit:10m rate=300r/m;

    server {
        listen 80;
        server_name your-domain.com;  # Заменить на реальный домен

        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # Frontend
        location / {
            proxy_pass http://web-frontend:80;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;

            limit_req zone=web_limit burst=50 nodelay;
        }

        # Backend API
        location /api/ {
            proxy_pass http://web-backend:8200/api/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

            limit_req zone=api_limit burst=20 nodelay;

            # CORS headers (если нужно)
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;
        }

        # WebSocket
        location /ws {
            proxy_pass http://web-backend:8200/ws;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_read_timeout 86400;  # 24 hours for long-lived connections
        }
    }

    # SSL configuration (uncomment for HTTPS)
    # server {
    #     listen 443 ssl http2;
    #     server_name your-domain.com;
    #
    #     ssl_certificate /etc/nginx/ssl/fullchain.pem;
    #     ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    #
    #     # ... same locations as above ...
    # }

    # Redirect HTTP to HTTPS (uncomment for HTTPS)
    # server {
    #     listen 80;
    #     server_name your-domain.com;
    #     return 301 https://$server_name$request_uri;
    # }
}
```

---

## Production vs Development Config Differences

| Config | Development | Production |
|--------|-------------|------------|
| **DEBUG** | `true` | `false` |
| **RELOAD** | `true` (hot reload) | `false` |
| **LOG_LEVEL** | `DEBUG` | `INFO` |
| **CORS** | `*` (все origins) | Конкретные домены |
| **Databases** | localhost:ports | Docker network names |
| **Volumes** | Code mounted | Only data volumes |
| **Restart policy** | `no` | `unless-stopped` |
| **SSL** | Off | On (рекомендуется) |

---

## Configuration Loading

### Python (Pydantic Settings)

```python
# shared/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Global settings loaded from environment"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # LLM
    openrouter_api_key: str
    aitunnel_api_key: str

    # Telegram
    telegram_bot_token: str
    telegram_user_id: int

    # Auth
    web_auth_token: str
    jwt_secret: str
    jwt_expiration_hours: int = 24

    # Databases
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "balbes_agents"
    postgres_user: str = "balbes"
    postgres_password: str

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""

    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"

    # Logging
    log_level: str = "INFO"
    log_dir: str = "./data/logs"
    log_format: str = "json"

    # Token limits
    default_daily_token_limit: int = 100000
    default_hourly_token_limit: int = 15000
    token_alert_threshold: float = 0.8

    # Performance
    task_timeout_seconds: int = 600
    max_retries: int = 3

    # Dev
    debug: bool = False
    reload: bool = False

# Usage
settings = Settings()
```

---

## Configuration Validation

### Startup Validation Script

```python
# scripts/validate_config.py

"""
Validate configuration before starting services.
Run this to check that all required config is present and valid.
"""

import sys
from shared.config import Settings
import yaml

def validate_env():
    """Validate environment variables"""
    try:
        settings = Settings()
        print("✅ Environment variables loaded")
        return True
    except Exception as e:
        print(f"❌ Environment validation failed: {e}")
        return False

def validate_providers_config():
    """Validate providers.yaml"""
    try:
        with open("config/providers.yaml") as f:
            config = yaml.safe_load(f)

        assert "providers" in config
        assert "openrouter" in config["providers"]
        assert "fallback_chain" in config

        print("✅ Providers config valid")
        return True
    except Exception as e:
        print(f"❌ Providers config invalid: {e}")
        return False

def validate_agents_config():
    """Validate agent configs"""
    try:
        for agent in ["orchestrator", "coder"]:
            with open(f"config/agents/{agent}.yaml") as f:
                config = yaml.safe_load(f)
            assert "agent_id" in config
            assert "skills" in config
            print(f"✅ Agent config valid: {agent}")
        return True
    except Exception as e:
        print(f"❌ Agent config invalid: {e}")
        return False

def validate_skills_config():
    """Validate skill configs"""
    try:
        import os
        skill_files = os.listdir("config/skills")
        assert len(skill_files) >= 6, "Expected at least 6 base skills"
        print(f"✅ Skills config valid: {len(skill_files)} skills found")
        return True
    except Exception as e:
        print(f"❌ Skills config invalid: {e}")
        return False

if __name__ == "__main__":
    print("Validating configuration...\n")

    results = [
        validate_env(),
        validate_providers_config(),
        validate_agents_config(),
        validate_skills_config()
    ]

    if all(results):
        print("\n✅ All configuration valid!")
        sys.exit(0)
    else:
        print("\n❌ Configuration validation failed!")
        sys.exit(1)
```

**Usage**:
```bash
python scripts/validate_config.py
```

---

## Hot Reload Configuration (Development)

Некоторые конфиги могут перезагружаться без перезапуска:

**Можно hot reload**:
- `config/providers.yaml` - отправить SIGHUP процессу
- `config/skills/*.yaml` - Skills Registry перезагрузит автоматически
- `config/base_instructions.yaml` - отправить SIGHUP

**Требуют перезапуска**:
- `config/agents/*.yaml` - нужен restart агента
- `.env` переменные - нужен restart всех сервисов

```python
# В каждом сервисе добавить signal handler

import signal

def reload_config(signum, frame):
    """Reload configuration on SIGHUP"""
    logger.info("Reloading configuration...")
    global config
    config = load_config()
    logger.info("Configuration reloaded")

signal.signal(signal.SIGHUP, reload_config)
```

```bash
# Отправка сигнала
kill -HUP $(pgrep -f "python.*orchestrator")
```

---

## Configuration Best Practices

1. **Secrets**: Никогда не коммитить .env с реальными ключами
2. **Defaults**: Разумные defaults для необязательных параметров
3. **Validation**: Валидировать при загрузке (Pydantic Settings)
4. **Documentation**: Комментарии в .env.example для каждой переменной
5. **Environment-specific**: Разные .env для dev/staging/prod
6. **Version control**: Коммитить только .env.example и config/*.yaml
