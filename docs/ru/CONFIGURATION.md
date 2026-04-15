# Конфигурация системы

## Переменные окружения

### .env.prod (продакшн)

```bash
# =============================================================================
# LLM Providers
# =============================================================================
OPENROUTER_API_KEY=sk-or-v1-your-key-here
AITUNNEL_API_KEY=                           # Не используется, оставить пустым

# =============================================================================
# Telegram Bot
# =============================================================================
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
# Разрешённые Telegram user ID (через запятую для нескольких пользователей)
TELEGRAM_USER_ID=YOUR_TELEGRAM_USER_ID

# =============================================================================
# Web UI Authentication
# =============================================================================
WEB_AUTH_TOKEN=your-secure-random-token-min-32-chars
JWT_SECRET=your-jwt-secret-min-32-chars
JWT_EXPIRATION_HOURS=24

# =============================================================================
# Databases
# =============================================================================
POSTGRES_HOST=localhost
POSTGRES_PORT=15432
POSTGRES_DB=balbes
POSTGRES_USER=balbes
POSTGRES_PASSWORD=your-strong-password

REDIS_HOST=localhost
REDIS_PORT=16379
REDIS_PASSWORD=

QDRANT_HOST=localhost
QDRANT_PORT=16333
QDRANT_API_KEY=

RABBITMQ_HOST=localhost
RABBITMQ_PORT=15672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# =============================================================================
# Service Ports (prod)
# =============================================================================
ORCHESTRATOR_PORT=18102
CODER_PORT=18103
MEMORY_SERVICE_PORT=18100
SKILLS_REGISTRY_PORT=18101
WEB_BACKEND_PORT=18200

# =============================================================================
# Optional Search Skills
# =============================================================================
BRAVE_SEARCH_KEY=                           # Оставить пустым если не используется
TAVILY_API_KEY=                             # Оставить пустым если не используется

# =============================================================================
# Logging
# =============================================================================
LOG_LEVEL=INFO
LOG_DIR=./data/logs
PYTHONUNBUFFERED=1
```

> **Важно**: `TZ` намеренно не устанавливается — контейнеры монтируют `/etc/localtime`
> и `/etc/timezone` с хоста, Python использует `datetime.now().astimezone()`.

### Входящие webhooks (`services/webhooks_gateway`)

Порт: `WEBHOOKS_GATEWAY_PORT`. Режим Telegram: `TELEGRAM_BOT_MODE` (`polling` \| `webhook`), секреты `TELEGRAM_WEBHOOK_SECRET`, `MAX_WEBHOOK_SECRET`. Мониторинг: `WEBHOOK_NOTIFY_API_KEY`, `NOTIFY_*`, `MAX_BOT_TOKEN` — см. [`.env.example`](../../.env.example) и [`docs/ru/WEBHOOK_NOTIFY.md`](WEBHOOK_NOTIFY.md).

---

## config/agents/*.yaml (манифесты агентов)

Файлы в репозитории **без секретов**: allowlist инструментов по режимам (`ask` / `agent` / `dev`) и таблица **HTTP-делегирования** для `delegate_to_agent`.

Пример [`config/agents/balbes.yaml`](../../config/agents/balbes.yaml):

```yaml
id: balbes
delegate_targets:
  coder: http://127.0.0.1:8001
  blogger: http://127.0.0.1:8105
```

- Базовые URL для `coder` и `blogger` при отсутствии записи подставляются из `CODER_PORT` / `BLOGGER_SERVICE_PORT` (см. `shared.config.Settings`).
- Доверие между сервисами: заголовок `X-Balbes-Delegation-Key` должен совпадать с переменной окружения **`DELEGATION_SHARED_SECRET`** на стороне оркестратора и целевого сервиса. Если секрет не задан, проверка отключена (удобно для локальной разработки).

Реализация загрузки: [`shared/agent_manifest.py`](../../shared/agent_manifest.py).

Блок **`telegram:`** (опционально) задаёт возможности UI бота для агента: голос (`voice`), меню команд (`commands_menu`), переключение модели (`model_switch`), мультичат (`multi_chat`), команды памяти (`memory_commands`), **`debug_command`** (команда `/debug`: трейс LLM и этапов голоса в текущем чате, настройки в Memory) — одинаково для оркестратора и для бизнес-бота блогера. У блогера в Memory Service ключ пользователя — **`blogger_<telegram_id>`** (формула в [`shared/telegram_app/memory_namespace.py`](../../shared/telegram_app/memory_namespace.py)); старый префикс `bbot_<id>` поддерживается только как чтение при миграции. Для сервиса блогера дополнительно — `posts_commands`, `business_groups`, `business_group_capture`, `private_conversation`, `voice_transcription_preview` и др. См. класс `TelegramFeatureFlags` в [`shared/agent_manifest.py`](../../shared/agent_manifest.py). Пример: [`config/agents/blogger.yaml`](../../config/agents/blogger.yaml). Регистрация slash-команд — [`shared/telegram_app/telegram_command_matrix.py`](../../shared/telegram_app/telegram_command_matrix.py).

**Блогер: включить `/debug`.** Откройте [`config/agents/blogger.yaml`](../../config/agents/blogger.yaml) и в блоке `telegram:` задайте `debug_command: true`. Если блока `telegram:` нет или ключа нет, в [`TelegramFeatureFlags`](../../shared/agent_manifest.py) по умолчанию уже `debug_command: true` — команда будет в меню после перезапуска процесса блогера. Чтобы явно отключить: `debug_command: false`.

---

## config/providers.yaml

Центральный конфиг системы. Управляет моделями, агентами, heartbeat, skills, whisper.

### Структура верхнего уровня

```yaml
providers:          # LLM-провайдеры и их модели
agents:             # Настройки агентов (whitelist команд, токен-лимиты, модель)
active_models:      # Модели, доступные пользователю в /model меню
fallback_strategy:  # Поведение при ошибке LLM
default_fallback_chain:  # Цепочка fallback (free → cheap)
cheap_models:       # Для автопереключения при превышении лимита
token_limits:       # Глобальные defaults
memory:             # Стратегия trim/summarize для истории
whisper:            # Справочный блок; реальные параметры — WHISPER_* в .env (см. ниже)
skills:             # web_search, fetch_url, server_commands
heartbeat:          # Проактивные сообщения
embeddings:         # Qdrant embeddings (text-embedding-3-small)
notifications:      # Шаблоны уведомлений
retry:              # Настройки повторных попыток
rate_limiting:      # Ограничение запросов
timeouts:           # Таймауты LLM, skills, БД
```

### Тиры моделей

```yaml
# Тир free — дефолт, heartbeat, первый fallback (бесплатные)
- id: "stepfun/step-3.5-flash:free"      # StepFun Step 3.5 Flash (65K ctx)
- id: "minimax/minimax-m2.5:free"        # MiniMax M2.5 (1M ctx)
- id: "z-ai/glm-4.5-air:free"           # GLM-4.5 Air (32K ctx)
- id: "arcee-ai/trinity-mini:free"       # Trinity Mini (32K ctx)
- id: "openai/gpt-oss-20b:free"          # GPT OSS 20B (128K ctx)

# Тир cheap — автоматический fallback (платные, дешёвые)
- id: "meta-llama/llama-3.1-8b-instruct"   # $0.000018/1K — самая дешёвая
- id: "meta-llama/llama-3.3-70b-instruct"  # $0.00008/1K
- id: "minimax/minimax-m2.5"               # $0.001/1K, 1M ctx

# Тир medium — только явный выбор пользователем
- id: "moonshotai/kimi-k2.5"             # $0.15/1K — дефолт Coder
- id: "google/gemini-3-flash-preview"    # $0.15/1K, 1M ctx

# Тир premium — только явный выбор пользователем
- id: "z-ai/glm-5-turbo"                 # $0.5/1K
- id: "anthropic/claude-sonnet-4.6"      # $3.0/1K, 200K ctx
- id: "openai/gpt-5.4"                   # $15.0/1K
```

В меню `/model` они отображаются с префиксом тира: `🆓` free, `💲` cheap, `🌙` medium, `🎯/⚡/🏆` premium.

### Настройки агентов

```yaml
agents:
  - id: "orchestrator"
    display_name: "Balbes"
    emoji: "🤖"
    # default_model: не задан → берётся первый из active_models (stepfun:free)

    # false = показать ошибку API пользователю (рекомендуется)
    # true  = тихо пробовать следующую модель из fallback_chain
    fallback_enabled: false

    fallback_chain:
      - "openrouter/stepfun/step-3.5-flash:free"
      - "openrouter/meta-llama/llama-3.3-70b-instruct"
      - "openrouter/minimax/minimax-m2.5"

    token_limits:
      daily: 100000
      hourly: 15000

    # Команды в режиме /mode ask (безопасные, read-only)
    server_commands_ask:
      mode: whitelist
      timeout_seconds: 120
      allowed_commands:
        - "date"
        - "sleep {n}"
        - "find {path} -name {pattern}"
        - "df -h"
        - "free -h"
        - "uptime"
        - "docker ps"
        - "docker logs {container}"
        - "ls {path}"
        - "cat {file}"
        - "head -n {n} {file}"
        - "tail -n {n} {file}"
        # ... полный список в config/providers.yaml

    # Команды в режиме /mode agent (полный dev-вайтлист)
    server_commands:
      mode: whitelist
      timeout_seconds: 120
      allowed_commands:
        # ── Всё из ask +
        - "python {script}"
        - "pip install {package}"
        - "pytest {path}"
        - "ruff check {path}"
        - "git status"
        - "git add {file}"
        - "git commit -m {message}"
        - "git push"
        # ... полный список в config/providers.yaml

  - id: "coder"
    display_name: "Coder"
    emoji: "💻"
    default_model: "openrouter/moonshotai/kimi-k2.5"  # явно задан
    fallback_enabled: false
    token_limits:
      daily: 200000
      hourly: 30000
    server_commands_ask:
      # + базовый git read (status, log, diff, branch)
      # + git -C {path} варианты
    server_commands:
      # + git stash, checkout, git -C {path} add/commit/push/pull
      # + mypy, полный git -C {path} набор
```

> **Для Coder**: всегда используйте `git -C /path/to/repo command`.
> Паттерн `cd /path && git command` не проходит вайтлист.

### Heartbeat

```yaml
heartbeat:
  enabled: true
  every_minutes: 5
  model: "openrouter/stepfun/step-3.5-flash:free"
  fallback_models:
    - "openrouter/minimax/minimax-m2.5:free"
    - "openrouter/z-ai/glm-4.5-air:free"
    - "openrouter/arcee-ai/trinity-mini:free"
    - "openrouter/openai/gpt-oss-20b:free"
    - "openrouter/meta-llama/llama-3.1-8b-instruct"   # cheapest paid
  active_hours_start: "09:00"    # локальное серверное время
  active_hours_end: "23:00"
  # target_user_id берётся из TELEGRAM_USER_ID (.env.prod)
```

Heartbeat использует только `workspace_read` — без истории чата и прочих tool-схем — для минимального расхода токенов.

### Voice / Whisper

Параметры задаются **переменными окружения** (`WHISPER_*`, `YANDEX_SPEECH_*`) — полный список в **`.env.example`** и в англ. [CONFIGURATION.md](../en/CONFIGURATION.md#optional--voice-telegram). Блок в `providers.yaml` остаётся справочным (см. комментарии в файле).

**Пайплайн:**

1. **Короткие** голосовые (длительность из Telegram ≤ `WHISPER_LOCAL_MAX_DURATION_SECONDS`) — локально **openai-whisper** с моделью `WHISPER_LOCAL_MODEL` (часто `medium`), нужны `ffmpeg` и пакет `openai-whisper`.
2. **Длинные** или **без известной длительности** — облачный STT: **OpenRouter** (чат с `input_audio`) и/или **Yandex SpeechKit** в зависимости от `WHISPER_REMOTE_BACKEND`; для ключей SpeechKit можно не задавать `YANDEX_SPEECH_*` — тогда используются `YANDEX_SEARCH_KEY` и `YANDEX_FOLDER_ID`.
3. После сырой расшифровки — **LLM-коррекция** через OpenRouter (сначала модель текущего чата, затем `WHISPER_CORRECTION_FALLBACK_MODEL`).

```yaml
whisper:
  model: "large-v3"    # legacy в YAML; локальный путь — WHISPER_LOCAL_MODEL в .env
  device: "cpu"
  beam_size: 10
  language: "ru"
```

### Web Search

```yaml
skills:
  web_search:
    enabled: true
    default_provider: "duckduckgo"
    providers:
      duckduckgo: { enabled: true, max_results: 5 }
      brave:  { enabled: false, api_key: ${BRAVE_SEARCH_KEY} }
      tavily: { enabled: false, api_key: ${TAVILY_API_KEY} }
```

### Memory / Context Window

```yaml
memory:
  # "trim"      — молча обрезать старые сообщения (по умолчанию)
  # "summarize" — суммаризировать обрезаемую часть через дешёвую LLM
  history_strategy: "trim"

  # Модель для суммаризации (только при history_strategy: "summarize")
  # summary_model: "meta-llama/llama-3.1-8b-instruct:free"

  trim_threshold: 0.85          # начинать обрезку при 85% заполнения контекста
  max_messages_in_context: 50   # жёсткий лимит сообщений независимо от токенов
  system_prompt_reserve: 500    # резерв токенов для системного промпта
```

При `history_strategy: "summarize"`:
1. Если история не умещается в контекстное окно — `_maybe_summarize_history()` вызывает `summary_model` для краткого пересказа старых сообщений
2. Саммари сохраняется в Redis на 7 дней (ключ `balbes:history_summary:{user_id}:{chat_id}`) и переиспользуется
3. В следующем `build_messages_for_llm` саммари вставляется как системное сообщение вместо обрезанных записей

---

## data/agents/{id}/config.yaml

Файл высшего приоритета — переопределяет любые настройки из `providers.yaml`.
Агент может сам редактировать этот файл через `workspace_write`.

```yaml
# data/agents/coder/config.yaml
default_model: "openrouter/moonshotai/kimi-k2.5"

token_limits:
  daily: 200000
  hourly: 30000

server_commands:
  mode: whitelist
  timeout_seconds: 120
  allowed_commands:
    - "pytest {path}"
    - "python {script}"
    - "git -C {path} status"
    # ...
```

---

## Приоритет конфигурации

```
data/agents/{id}/config.yaml   (высший приоритет)
       ↓
config/providers.yaml → agents[id]
       ↓
config/providers.yaml → global defaults (token_limits, fallback_strategy)
```

---

## Конфигурация Redis (структуры)

| Ключ | Тип | TTL | Назначение |
|------|-----|-----|-----------|
| `chat:{user_id}:{chat_id}:history` | Sorted Set | 7 дней | История сообщений |
| `chat:{user_id}:{chat_id}:meta` | Hash | 7 дней | Название, модель, агент, флаги |
| `user:{user_id}:active_chat` | String | — | ID активного чата |
| `user:{user_id}:chats` | Set | — | Все chat_id пользователя |
| `chat:{user_id}:{chat_id}:debug` | String | — | Флаг debug on/off |
| `chat:{user_id}:{chat_id}:mode` | String | — | "ask" или "agent" |
| `balbes:task:{task_id}` | String (JSON) | 24 ч | Запись о задаче (реестр) |
| `balbes:task_ids` | Sorted Set | — | Индекс task_id по времени |
| `balbes:history_summary:{user_id}:{chat_id}` | String | 7 дней | LLM-саммари истории чата |

---

## Docker Compose (prod)

```yaml
# docker-compose.prod.yml — ключевые моменты

services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
      - /etc/localtime:/etc/localtime:ro    # ← часовой пояс с хоста
      - /etc/timezone:/etc/timezone:ro

  redis:
    image: redis:7-alpine
    volumes:
      - /etc/localtime:/etc/localtime:ro

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./data/qdrant:/qdrant/storage
      - /etc/localtime:/etc/localtime:ro
```

Примонтирование `/etc/localtime` и `/etc/timezone` с хоста обеспечивает единый часовой пояс для всех контейнеров и Python-сервисов без жёсткого прописывания `TZ`.

---

## Скрипты управления

| Скрипт | Назначение |
|--------|-----------|
| `scripts/start_prod.sh` | Запуск продакшн-сервисов (uvicorn --workers 1) |
| `scripts/restart_prod.sh` | Перезапуск + healthcheck |
| `scripts/stop_prod.sh` | Остановка всех сервисов |
| `scripts/healthcheck.sh prod` | Проверка 10 компонентов |
| `scripts/setup_memory_repo.sh <url>` | Инициализация приватного git-репо для data/agents/ |
| `scripts/start_dev.sh` | Запуск dev-окружения |

### setup_memory_repo.sh

```bash
# Первый раз на dev
bash scripts/setup_memory_repo.sh git@github.com:user/balbes-memory.git

# Первый раз на prod (если репо уже существует)
bash scripts/setup_memory_repo.sh git@github.com:user/balbes-memory.git
# Скрипт корректно обрабатывает пустой remote — создаёт initial commit
```

---

## Порты по окружениям

| Сервис | Dev | Test | Prod |
|--------|-----|------|------|
| Memory Service | 8100 | 9100 | 18100 |
| Skills Registry | 8101 | 9101 | 18101 |
| Orchestrator | 8102 | 9102 | 18102 |
| Coder | 8103 | 9103 | 18103 |
| Web Backend | 8200 | 9200 | 18200 |
| PostgreSQL | 5432 | 5433 | 15432 |
| Redis | 6379 | 6380 | 16379 |
| Qdrant | 6333 | 6334 | 16333 |

---

## Диагностика

### Проверка конфигурации

```bash
# Проверить что providers.yaml валиден
python -c "import yaml; yaml.safe_load(open('config/providers.yaml'))" && echo OK

# Проверить переменные окружения
grep -v '^#' .env.prod | grep -v '^$'

# Проверить модели в меню (из active_models)
python -c "
import yaml
c = yaml.safe_load(open('config/providers.yaml'))
for m in c['active_models']:
    print(m['tier'], m['id'])
"
```

### Проверка здоровья системы

```bash
# Все 10 компонентов
bash scripts/healthcheck.sh prod

# Только orchestrator
curl http://localhost:18102/health

# Задачи в реестре
curl "http://localhost:18102/api/v1/tasks?user_id=YOUR_TELEGRAM_USER_ID"
```

### Логи

```bash
# Продакшн-логи (папка ~/projects/balbes)
tail -f logs/prod/orchestrator.log
tail -f logs/prod/telegram_bot.log
tail -f logs/prod/coder.log

# Логи активности агентов
ls data/logs/agent_activity/orchestrator/
cat data/logs/agent_activity/orchestrator/2026-03-29.jsonl | python -m json.tool | head -40
```
