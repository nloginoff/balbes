# Руководство по агентам

## Обзор

В системе основные роли: оркестратор (Balbes), Coder и сервис Blogger. Делегирование специалистам выполняется **только по HTTP** (`POST /api/v1/agent/execute`), см. [`config/agents/balbes.yaml`](../../config/agents/balbes.yaml) и [`shared/agent_execute_contract.py`](../../shared/agent_execute_contract.py).

| Агент | ID | Emoji | Назначение |
|-------|----|-------|-----------|
| Balbes (Оркестратор) | `balbes` | 🤖 | Главный ассистент, точка входа через Telegram |
| Coder | `coder` | 💻 | Код, файлы, тесты, git (микросервис) |
| Blogger | `blogger` | ✍️ | Черновики, посты, каналы (микросервис; краткий ответ по делегированию) |

---

## OrchestratorAgent

### Архитектура

`OrchestratorAgent` реализован в [`services/orchestrator/agent.py`](../../services/orchestrator/agent.py), наследует [`BaseAgent`](../../shared/agent_base.py) и координирует инструменты, память и задачи.

```python
class OrchestratorAgent(BaseAgent):
    # Компоненты
    tool_dispatcher: ToolDispatcher   # регистрирует и вызывает инструменты
    _workspaces: dict[str, AgentWorkspace]  # кэш MD-файлов агентов
    _memory: RedisMemory              # история чатов, сессии, флаги
    _qdrant: QdrantMemory             # долгосрочная семантическая память

    # Реестр задач (in-memory + Redis mirror)
    _task_registry: dict[str, dict]   # все задачи, ограничен 50 записями
    _background_tasks: dict[str, asyncio.Task]  # активные фоновые задачи
    _background_results: dict[str, dict]        # результаты завершённых задач
    _bg_debug_buffer: dict[str, list[dict]]     # live debug-события для монитора
    _redis: aioredis.Redis | None     # для persist task registry + history summary
```

### Жизненный цикл задачи

```
1. Telegram-бот → POST /api/v1/tasks
2. execute_task(user_id, chat_id, input, model_id, source, mode, debug_events)
   ├── reset_call_counts() — сброс rate-limit счётчиков на задачу
   ├── Загрузка системного промпта из workspace (SOUL.md + AGENTS.md + MEMORY.md + …)
   ├── Загрузка истории чата из Redis
   ├── _maybe_summarize_history() — LLM суммаризация если контекст переполнен
   ├── build_messages_for_llm(history, summary) — адаптивная обрезка под контекст-окно
   ├── _run_llm_with_tools(messages, tools, model_id, …)
   │   ├── LLM round 1 → tool_calls (JSON или XML)
   │   │   └── _normalize_tool_name() — исправляет de-underscored имена
   │   ├── ToolDispatcher.dispatch(tool_name, args)
   │   │   ├── rate limit check (_call_counts)
   │   │   └── emit debug event: tool_start / tool_done
   │   ├── LLM round 2 … MAX_TOOL_CALL_ROUNDS (15)
   │   └── return (response_text, model_used, token_usage)
   ├── Сохранение ответа в историю Redis
   ├── _record_token_usage() — fire-and-forget → /api/v1/tokens/record
   └── return TaskResult {output, model_used, token_usage, debug_events, outbound_attachments?}
```

### XML Tool Call Parsing

Некоторые модели (MiniMax) вставляют вызовы инструментов в виде XML в текст ответа:

```xml
<minimax:toolcall>
  <invoke name="execute_command">
    <parameter name="cmd">git status</parameter>
  </invoke>
</minimax:toolcall>
```

`_parse_xml_tool_calls()` ловит любой вариант:
- `<prefix:tool_call>` — стандартный
- `<prefix:toolcall>` — без подчёркивания (MiniMax)

После парсинга XML-разметка вырезается из текста ответа, чтобы не попасть обратно в LLM.

`_normalize_tool_name()` исправляет имена без подчёркиваний:
- `readagentlogs` → `read_agent_logs`
- `delegatetoagent` → `delegate_to_agent`
- `executecommand` → `execute_command` и т.д.

### Делегирование (HTTP)

Инструмент `delegate_to_agent` обращается к микросервисам **только по HTTP**: `POST /api/v1/agent/execute`. Базовый URL: по умолчанию из окружения — [`Settings.coder_base_url` / `blogger_base_url`](../../shared/config.py) (`CODER_PORT` / `CODER_SERVICE_URL`, `BLOGGER_SERVICE_PORT` / `BLOGGER_SERVICE_URL`). Опционально в [`config/agents/balbes.yaml`](../../config/agents/balbes.yaml) можно задать `delegate_targets` (переопределяет env). Жёстко прописанный URL с **другим портом**, чем у запущенных сервисов, даёт быстрый `ConnectError` и почти пустой ответ инструмента. Заголовок доверия: `X-Balbes-Delegation-Key` при `DELEGATION_SHARED_SECRET`. Внутрипроцессного запуска второго агента через LLM оркестратора больше нет.

---

## Blogger (микросервис)

Сервис [`services/blogger`](../../services/blogger): посты, бизнес-бот, очередь публикаций. История DM с владельцем в Memory Service хранится под **`user_id` = `blogger_<telegram_user_id>`** — см. [`shared/telegram_app/memory_namespace.py`](../../shared/telegram_app/memory_namespace.py). Старый префикс `bbot_<id>` при чтении ещё учитывается для миграции. Общий список slash-команд и порядок меню — [`shared/telegram_app/telegram_command_matrix.py`](../../shared/telegram_app/telegram_command_matrix.py); включение/выключение — блок `telegram:` в [`config/agents/blogger.yaml`](../../config/agents/blogger.yaml) (в т.ч. `debug_command` для `/debug`). Подробнее по настройкам: [`docs/ru/CONFIGURATION.md`](CONFIGURATION.md).

---

## Workspace агента

Каждый агент хранит своё состояние в `data/agents/{agent_id}/`:

| Файл | Назначение |
|------|-----------|
| `SOUL.md` | Характер, ценности, стиль общения |
| `AGENTS.md` | Операционные инструкции, workflow, поведение |
| `MEMORY.md` | Постоянная важная память (обновляется агентом) |
| `HEARTBEAT.md` | Чеклист для проактивных сообщений |
| `TOOLS.md` | Документация по всем доступным инструментам |
| `IDENTITY.md` | Имя, описание, примеры общения |
| `config.yaml` | Переопределение модели/лимитов (высший приоритет) |
| `schedules.yaml` | Cron/interval задачи для этого агента (тот же формат, что и `manage_schedule`; для `balbes` каталог может быть `orchestrator/`) |

Схема полей и пример — [`config/schedules.example.yaml`](../../config/schedules.example.yaml).

### config.yaml агента

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
    # …
```

Приоритет настроек (от высшего к низшему):
1. `data/agents/{id}/config.yaml`
2. `config/providers.yaml` → секция `agents[id]`
3. Глобальные defaults в `providers.yaml`

### Версионирование workspace

При каждой записи в workspace-файл:
1. `git add {file} && git commit -m "agent: update {file}"` (синхронно)
2. `threading.Timer(30, git_push)` — debounced push через 30 секунд

Репозиторий: приватный GitHub-репо, настроенный через `setup_memory_repo.sh`.

---

## Делегирование задач

### Инструменты делегирования

```
delegate_to_agent(agent, task, mode, background)
get_agent_result(agent)
cancel_agent_task(agent)
list_agent_tasks(limit)
```

### Foreground делегирование (синхронное)

```python
# Оркестратор вызывает:
result = await _delegate_task(agent_id="coder", task="...", mode="agent")
# Блокирует текущий LLM-раунд до завершения Coder
# Результат возвращается в следующем LLM-раунде как tool result
```

### Background делегирование (асинхронное)

```python
# Оркестратор вызывает:
run_agent_background(user_id, agent_id="coder", task="...", mode="agent")
# Немедленно возвращает: "Задача передана агенту 'coder' (фоновый режим)"
# Coder работает в asyncio.Task; дебаг-события накапливаются в _bg_debug_buffer
```

### Мониторинг фонового задания

```
Telegram-бот
  │  каждые 5 секунд
  ▼
GET /api/v1/tasks/bg/events?user_id=...&agent_id=coder
  │
  ▼  (poll_bg_task)
_bg_debug_buffer → events []
_task_registry → status (running | completed | failed)
_background_results → result_text (если завершено)
  │
  ▼
• Если debug=on: отправить HTML-трейс событий в Telegram
• Если завершено: отправить заголовок ✅ + результат (если не fallback-текст)
```

### Изоляция sub-агента

Каждый делегированный агент получает:
- Собственный `ToolDispatcher` (не разделяет диспетчер с Оркестратором)
- Вайтлист команд из его собственного `config.yaml` / `providers.yaml`
- Модель из его `default_model`, а не из активного чата Оркестратора
- Свой `debug_events` список для накопления событий в `_bg_debug_buffer`

---

## Инструменты (ToolDispatcher)

### Полный список

| Инструмент | Ask mode | Agent mode | Описание |
|-----------|----------|------------|----------|
| `web_search` | ✅ | ✅ | Brave / Tavily поиск |
| `fetch_url` | ✅ | ✅ | Загрузить URL → текст (html2text) |
| `execute_command` | ✅ (ask-вайтлист) | ✅ (agent-вайтлист) | Команда на сервере |
| `workspace_read` | ✅ | ✅ | Читать MD/YAML из workspace |
| `workspace_write` | ✅ | ✅ | Писать в workspace (авто-коммит) |
| `file_read` | ✅ | ✅ | Читать любой файл проекта |
| `file_write` | ✅ | ✅ | Создать/перезаписать файл проекта |
| `file_patch` | ✅ | ✅ | Точечная замена строки в файле |
| `rename_chat` | ✅ | ✅ | Переименовать текущий чат |
| `save_to_memory` | ✅ | ✅ | Сохранить факт в Qdrant |
| `recall_from_memory` | ✅ | ✅ | Семантический поиск в долгосрочной памяти |
| `code_search` | ✅ | ✅ | Семантический поиск по кодовой базе |
| `index_codebase` | ✅ | ✅ | Переиндексировать кодовую базу в Qdrant |
| `manage_todo` | ✅ | ✅ | Читать/обновлять TODO.md |
| `read_agent_logs` | ✅ | ✅ | Прочитать JSONL-логи активности |
| `manage_schedule` | ✅ | ✅ | Управление задачами по расписанию (файлы `data/agents/<id>/schedules.yaml`; `list` показывает всех агентов) |
| `delegate_to_agent` | ❌ | ✅* | Делегировать задачу другому агенту (*у оркестратора `balbes` в [`config/agents/balbes.yaml`](../../config/agents/balbes.yaml) по умолчанию **отключён** — иначе модель зря уводила задачу в coder) |
| `get_agent_result` | ❌ | ✅* | Получить результат фоновой задачи (*у `balbes` с выключенным делегированием — недоступен) |
| `cancel_agent_task` | ❌ | ✅* | Отменить фоновую задачу (*то же) |
| `list_agent_tasks` | ✅ | ✅ | Реестр всех задач |
| `render_solution` | ✅ | ✅ | Текст решения с формулами → одна или несколько PNG; рендер на сетке, затем **обрезка** по рамке текста (без лишнего пустого поля внизу/по краям) и умеренный перенос строк, чтобы не вылезать за ширину. Файлы в `outbound_attachments` |

**Heartbeat** использует только `workspace_read` (минимальный набор для экономии токенов).

### Как пользоваться `manage_schedule` и `schedules.yaml`

- **Где данные:** у каждого агента свой файл `data/agents/<каталог_агента>/schedules.yaml` (для `balbes` часто каталог `orchestrator/`). Схема полей — [`config/schedules.example.yaml`](../../config/schedules.example.yaml).
- **Инструмент:** `action=list` — все джобы всех агентов; `add` / `remove` / `enable` / `disable` — в рамках файла, выбранного через **`agent_id`** (по умолчанию **текущий** агент задачи: оркестратор → `balbes`, coder → `coder`). Поле **`job_id`** уникально **внутри файла этого агента**, не глобально.
- **Триггеры:** `cron` (поля `hour`, `minute`, опционально `day_of_week` и др.) или `interval` (`minutes`, `hours`, …). В `add` новая задача создаётся **включённой**.
- **Правка всего файла:** `workspace_read(filename='schedules.yaml')` → правка полного YAML → `workspace_write` (как для остальных файлов workspace). Удобно для пакетных изменений; для одной задачи проще `manage_schedule`.
- **Срок применения:** планировщик в Telegram-боте подхватывает изменения примерно за **30 секунд** без рестарта сервисов.
- Подробные инструкции для модели также в **`TOOLS.md`** соответствующего агента в workspace.

### Rate Limiting

Каждый инструмент имеет лимит вызовов на одну задачу (защита от зацикливания):

| Инструмент | Лимит |
|-----------|-------|
| `web_search` | 10 |
| `fetch_url` | 15 |
| `file_read` / `file_write` / `file_patch` | 20–40 |
| `execute_command` | 30 |
| `render_solution` | 3 |
| остальные | 20 |

При превышении лимита инструмент возвращает ошибку с просьбой подвести итог.

### execute_command: вайтлисты

**Ask mode** (информационный, без изменений):
- `date`, `sleep {n}`, `find`, `df -h`, `free -h`, `uptime`
- `docker ps`, `docker logs`, `docker stats`
- `ls`, `cat`, `head`, `tail`, `wc -l`
- `ps aux`, `ping`, `systemctl status`
- Для Coder дополнительно: `pip list`, `pip show`, базовые `git` чтение

**Agent mode** (полный dev-вайтлист):
- Всё из ask +
- `python`, `python3`, `pip install`, `node`, `npm`
- `make`, `pytest`, `ruff`, `mypy`
- Git: `status`, `log`, `diff`, `branch`, `add`, `commit`, `push`, `pull`, `stash`, `checkout`
- `git -C {path} <cmd>` — команды с явным путём к репо (требуется для Coder)

> ⚠️ Coder должен использовать `git -C /path/to/repo command`, а не `cd /path && git command` — второй вариант не проходит вайтлист.

**Если команда отклонена, хотя в репозитории шаблон есть** — проверьте `data/agents/balbes/config.yaml` на сервере: блок `server_commands` / `allowed_commands` имеет **высший приоритет** над `providers.yaml` и может полностью заменить белый список.

**Многострочные команды (heredoc)** — в логах stderr может смешивать вывод shell и Python (например, после `pip install` следующий запуск скрипта без пакета). Для создания файлов надёжнее `workspace_write` / `file_write`, чем длинный `execute_command` с heredoc.

---

## Activity Logging

Каждый вызов инструмента логируется в `data/logs/agent_activity/{agent_id}/{date}.jsonl`:

```jsonl
{"timestamp": "2026-03-29T19:45:00+03:00", "agent_id": "coder", "tool": "execute_command", "input": {"cmd": "pytest tests/"}, "result": "3 passed", "duration_ms": 4231, "success": true, "source": "user"}
```

Инструмент `read_agent_logs` позволяет агенту прочитать логи за любой период прямо в чате.

---

## Orchestrator API

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/v1/tasks` | Создать/выполнить задачу |
| `GET` | `/api/v1/tasks` | Реестр задач (фильтр по user_id) |
| `GET` | `/api/v1/tasks/bg/events` | Статус фоновой задачи + debug-события |
| `GET` | `/health` | Healthcheck |

### POST /api/v1/tasks

Тело запроса — **JSON** (`Content-Type: application/json`). Поле текста пользователя — **`description`** (не `input`).

```json
{
  "user_id": "uuid-canonical-user-id",
  "description": "Что на изображении?",
  "chat_id": "abc123",
  "agent_id": "balbes",
  "model_id": "openrouter/minimax/minimax-m2.5",
  "source": "user",
  "mode": "ask",
  "debug": true,
  "bot_id": "main",
  "attachments": [
    {"kind": "image", "data_url": "data:image/jpeg;base64,..."},
    {"kind": "file_text", "filename": "notes.txt", "text": "..."}
  ],
  "vision_tier": "cheap"
}
```

Подробнее про вложения и vision — [`docs/ru/ATTACHMENTS.md`](ATTACHMENTS.md).

**Параллельные запросы:** для одного `user_id` **не** выполняется несколько foreground-задач сразу (источник не `heartbeat`); лишние `POST` **ждут в очереди** (порядок FIFO), затем идут в агент, чтобы не портить общий `ToolDispatcher` гонками. Отмена по желанию: `POST /api/v1/tasks/cancel?user_id=...` (в Telegram — **`/stop`**) снимается между раундами LLM и между вызовами инструментов. Клиент **Telegram-бот** ждёт HTTP-ответ с таймаутом чтения `ORCHESTRATOR_POST_TIMEOUT_SEC` (с запасом под очередь, по умолчанию 600 с); при **ReadTimeout** бот **не** шлёт cancel автоматически, чтобы не обрывать чужой долгий ответ — пользователь смотрит `/tasks` и при необходимости **/stop**.

Ответ:
```json
{
  "status": "success",
  "output": "Текст ответа агента",
  "model_used": "openrouter/minimax/minimax-m2.5",
  "debug_events": [...],
  "background_tasks_started": [{"agent_id": "coder", "key": "YOUR_TELEGRAM_USER_ID:coder"}],
  "outbound_attachments": [
    {"kind": "image_png", "filename": "solution_p1.png", "data_base64": "..."}
  ]
}
```

Поле **`outbound_attachments`** присутствует, если агент вызывал инструмент `render_solution` (или делегированный coder вернул вложения — они сливаются в ответ оркестратора). Клиенты вроде Telegram отправляют эти изображения отдельно от текста `output`.

### GET /api/v1/tasks/bg/events

```
GET /api/v1/tasks/bg/events?user_id=YOUR_TELEGRAM_USER_ID&agent_id=coder&consume_result=false
```

Ответ:
```json
{
  "status": "running",
  "events": [
    {"type": "llm", "round": 1, "model": "kimi-k2.5", "agent": "coder"},
    {"type": "tool_done", "tool": "execute_command", "elapsed_ms": 4231, "agent": "coder"}
  ],
  "result": null,
  "finished_at": null
}
```

---

## Telegram Bot

### Режимы

**Ask mode** (по умолчанию):
- Агент может читать/отвечать, использовать все инструменты кроме `delegate_to_agent`
- `execute_command` ограничен информационным вайтлистом
- `workspace_write` доступен (агент может обновлять своё `MEMORY.md`, `config.yaml` и т.д.)

**Agent mode**:
- Все возможности ask +
- `delegate_to_agent` / `get_agent_result` / `cancel_agent_task`
- `execute_command` с полным dev-вайтлистом (git, pytest, pip и т.д.)

### Debug mode

При включённом `/debug` каждое сообщение агента сопровождается HTML-трейсом:

```html
⚙️ Трейс выполнения:
  🤔 [orchestrator] LLM раунд 1 → minimax/minimax-m2.5
  🔧 [orchestrator] execute_command ← cmd='git status'
     ✅ → On branch master (7ms)
  🤔 [coder] LLM раунд 1 → moonshotai/kimi-k2.5
  🔧 [coder] execute_command ← cmd='pytest tests/'
     ✅ → 3 passed (4231ms)
  ⏱ Итого: 12450ms
```

Трейс отправляется с `parse_mode="HTML"` для надёжной обработки спецсимволов.
Длинные сообщения автоматически разбиваются на части по 4096 символов (`_split_message`).

**В обычном режиме** (debug off, agent mode) показывается компактный прогресс-индикатор:
```
⚙️ Работаю… раунд 3 | execute_command · file_patch
```
Сообщение редактируется на месте и удаляется при получении финального ответа.

### Heartbeat

- Запускается каждые 5 минут фоновым `asyncio.Task` в боте
- Читает `HEARTBEAT.md` и `MEMORY.md` через `workspace_read`
- Не загружает историю чата и не использует tool-схемы кроме `workspace_read`
- Использует только бесплатные модели; цепочка fallback:
  1. stepfun/step-3.5-flash:free
  2. minimax/minimax-m2.5:free
  3. z-ai/glm-4.5-air:free
  4. arcee-ai/trinity-mini:free
  5. openai/gpt-oss-20b:free
  6. meta-llama/llama-3.1-8b-instruct (cheapest paid, последний резерв)
  7. Если все недоступны — отправить сообщение об ошибке пользователю
- Работает только в часы `active_hours_start`–`active_hours_end` (локальное серверное время)
- Если модель вернула пустой текст, пользователю **не** показывается стандартное сообщение «модель вернула пустой ответ» (оно остаётся для обычных задач, не heartbeat)
- Ответ `HEARTBEAT_OK` в кавычках или с обёртками не дублируется в Telegram

---

## Добавление нового агента

1. Создать директорию `data/agents/{id}/` с MD-файлами и `config.yaml`
2. Добавить запись в `providers.yaml` → секция `agents`:
   ```yaml
   - id: "researcher"
     display_name: "Researcher"
     emoji: "🔍"
     default_model: "openrouter/moonshotai/kimi-k2.5"
     fallback_enabled: false
     token_limits: { daily: 150000, hourly: 20000 }
     server_commands_ask: { mode: whitelist, timeout_seconds: 120, allowed_commands: [...] }
     server_commands:     { mode: whitelist, timeout_seconds: 120, allowed_commands: [...] }
   ```
3. Создать `services/researcher/` с FastAPI-сервисом (опционально, если агент автономен)
4. Добавить в `AGENTS_TOOLS` в `tools.py` если нужны специфические инструменты
5. Оркестратор автоматически обнаружит агента по `providers.yaml` в `/agents` меню

---

## Troubleshooting

### Агент не выполняет команду

- Проверить, что режим `/mode agent` включён (для dev-команд)
- Команда должна точно совпадать с шаблоном в вайтлисте (с учётом `{placeholder}`)
- `git -C /path cmd` разрешён; `cd /path && git cmd` — нет

### Heartbeat не работает

```bash
# Проверить логи
tail -f ~/projects/balbes/logs/prod/telegram_bot.log | grep heartbeat

# Проверить конфиг
grep -A 10 "heartbeat:" config/providers.yaml

# Запустить вручную через Telegram
/heartbeat
```

### Фоновая задача не присылает обновления

- Убедиться, что orchestrator запущен с `--workers 1` (task registry in-memory)
- Проверить `_bg_monitors` — монитор должен быть создан
- `/tasks` показывает задачу? Если да, монитор можно запустить вручную через `/tasks`

### XML из LLM попадает в чат

- Должно быть исправлено в v0.3.0 для всех вариантов `<prefix:toolcall>` и `<prefix:tool_call>`
- Проверить логи: `grep "Parsed.*XML tool" logs/prod/orchestrator.log`
- Если модель использует нестандартный формат XML — добавить в `_XML_TOOL_CALL_RE` или таблицу `_TOOL_NAME_CANONICAL`
