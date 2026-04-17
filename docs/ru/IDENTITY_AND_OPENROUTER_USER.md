# Канонический пользователь, связка Telegram ↔ MAX и OpenRouter `user`

## Зачем канонический UUID

Memory и оркестратор работают с **одним** стабильным идентификатором на человека (UUID). Он же уходит в OpenRouter в поле **`user`** для атрибуции расхода в [дашборде OpenRouter](https://openrouter.ai/).

- Telegram: внешний id = десятичный `user.id` из Telegram.
- MAX: внешний id = числовой `user_id` из платформы.

Автоматически они **не** сливаются в одного человека: у каждого канала свой внешний id → при первом обращении создаётся **свой** UUID, пока вы явно не **свяжете** два канала (ниже).

## Где задаётся `user` в OpenRouter

| Сценарий | Значение `user` |
|----------|-----------------|
| Основной чат LLM (`chat/completions`) | Канонический UUID пользователя |
| Коррекция расшифровки голоса, облачный STT OpenRouter | Тот же UUID (если известен); иначе см. ниже |
| Эмбеддинги `code_search` / `index_codebase` | Канонический UUID текущей задачи |
| Эмбеддинги Memory (Qdrant) и skills-registry | `OPENROUTER_SERVICE_USER` (по умолчанию `balbes-service`) — сервисные вызовы без сессии пользователя |

Переменная **`OPENROUTER_SERVICE_USER`** (см. [CONFIGURATION.md](CONFIGURATION.md)) переопределяет «ведро» для обслуживающих запросов.

## Как узнать свой канонический UUID

Через Memory Service (подставьте свой внешний id):

```bash
# Telegram
curl -sS "http://localhost:8101/api/v1/identity/resolve?provider=telegram&external_id=YOUR_TG_USER_ID"

# MAX
curl -sS "http://localhost:8101/api/v1/identity/resolve?provider=max&external_id=YOUR_MAX_USER_ID"
```

В ответе поле `canonical_user_id` — это UUID для Memory и оркестратора.

Порт и хост Memory замените на свои (`MEMORY_SERVICE_URL`).

## Одноразовый код (основной способ)

Инициатор — тот **основной** аккаунт, чью историю вы хотите **сохранить**. Второй канал при вводе кода **теряет** свою изолированную историю в Redis (чаты/история по старому каналу).

| Шаг | Telegram — основа | MAX — основа |
|-----|-------------------|--------------|
| 1 | В Telegram: `/link max` — бот пришлёт код и предупреждение про удаление истории в MAX | В MAX: `/link telegram` — код и предупреждение про Telegram |
| 2 | В MAX: `/link КОД` (тот же код) | В Telegram: `/link КОД` |

Код живёт ~10 минут. API: `POST /api/v1/identity/pairing/create` (только для бэкендов; при `IDENTITY_LINK_SECRET` — заголовок `X-Balbes-Identity-Link-Secret`) и публичный `POST /api/v1/identity/pairing/redeem`.

Ручной **`POST /api/v1/identity/link`** с секретом остаётся для админских сценариев (без одноразового кода): там при конфликте непустых историй оба канала нужно разрулить вручную — см. ниже.

## Как связать Telegram и MAX в один аккаунт (ручной curl)

1. Решите, **какой UUID считать главным** — обычно тот, что уже привязан к Telegram (где больше истории).
2. Убедитесь, что у второго канала либо нет отдельной «тяжёлой» истории в Redis, либо вы готовы перенести её: при конфликте (оба id уже имеют непустые чаты) API вернёт ошибку — объединение таких данных пока не делается автоматически.
3. Вызовите **`POST /api/v1/identity/link`**:

```bash
curl -sS -X POST "http://localhost:8101/api/v1/identity/link" \
  -H "Content-Type: application/json" \
  -H "X-Balbes-Identity-Link-Secret: YOUR_IDENTITY_LINK_SECRET" \
  -d '{
    "canonical_user_id": "UUID_ИЗ_TELEGRAM_RESOLVE",
    "provider": "max",
    "external_id": "YOUR_MAX_USER_ID"
  }'
```

После этого все обращения с `provider=max` и вашим `external_id` будут попадать в **тот же** `canonical_user_id`, что и Telegram — одна история чатов в Memory.

Если переменная **`IDENTITY_LINK_SECRET`** не задана, заголовок `X-Balbes-Identity-Link-Secret` не требуется (удобно только для локальной разработки; в проде секрет лучше включить).

## Обратная связка (MAX главный)

Тело то же самое: укажите `provider` и `external_id` того канала, который нужно **пристыковать** к уже выбранному `canonical_user_id`.

```json
{
  "canonical_user_id": "выбранный-uuid",
  "provider": "telegram",
  "external_id": "YOUR_TG_USER_ID"
}
```

Итог: оба провайдера указывают на один UUID в Redis (`identity:link:telegram:…` и `identity:link:max:…`).
