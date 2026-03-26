# Executive Summary

Краткое изложение проекта для быстрого понимания.

---

## Что это?

**Balbes Multi-Agent System** - модульная система независимых AI-агентов для автоматизации задач (кодинг, контент, исследования) с управлением через Telegram и веб-интерфейс.

---

## Ключевая идея

Вместо одного большого AI-ассистента - **множество специализированных агентов**, каждый эксперт в своей области:
- 🤖 **Orchestrator** - координатор, управляет всеми
- 💻 **Coder** - пишет Python код и создает новые "скиллы"
- 📝 **Blogger** - создает контент (после MVP)
- 🔬 **Researcher** - исследует информацию (после MVP)
- ... и другие по мере необходимости (до 10 агентов)

---

## Почему это полезно?

### Проблема
Существующие AI системы (OpenClaw и др.):
- Делают слишком много лишнего
- Монолитные, сложно расширять
- Плохой контроль токенов и расходов
- Сложно кастомизировать под свои нужды

### Решение
Balbes Multi-Agent System:
- ✅ Минималистичный - только нужное
- ✅ Модульный - легко добавлять/убирать агенты
- ✅ Экономичный - строгий контроль токен-бюджета
- ✅ Прозрачный - полное логирование и мониторинг
- ✅ Гибкий - настраивается под любые задачи

---

## Архитектура в одной картинке

```
User (Telegram / Web)
    ↓
Orchestrator (координатор)
    ↓
Message Bus (RabbitMQ) ← асинхронная коммуникация
    ↓
Specialized Agents (Coder, Blogger, ...)
    ↓
Services (Memory, Skills Registry)
    ↓
Storage (PostgreSQL, Redis, Qdrant)
```

**Принцип**: Каждый агент - независимый микросервис.

---

## Основные возможности

### 1. Управление через Telegram
```
/task @coder создай скилл для парсинга новостей
→ 2 минуты спустя
✅ Скилл создан, тесты пройдены!
```

### 2. Web Dashboard
- Мониторинг всех агентов в real-time
- Детальные логи действий
- Статистика использования токенов
- Чат для отправки команд

### 3. Умная память
- **Быстрая** (Redis): контекст текущей сессии
- **Долговременная** (Qdrant): индексированная история с семантическим поиском
- Агенты учатся на прошлом опыте

### 4. Multi-Provider LLM
- OpenRouter (Claude, GPT-4, Llama)
- AiTunnel (fallback)
- Автоматический fallback при недоступности
- Автопереключение на дешевые модели при превышении лимита

### 5. Token Economy
- Лимиты per agent (daily, hourly)
- Детальный трекинг расходов
- Алерты при превышении
- Оптимизация через память

---

## Технологии

**Backend**: Python 3.13, FastAPI, asyncio
**Frontend**: React 18, TypeScript, shadcn/ui, Tailwind
**Databases**: PostgreSQL, Redis, Qdrant
**Message Queue**: RabbitMQ
**LLM**: OpenRouter (multi-provider gateway)
**Deployment**: Docker, Docker Compose, Nginx

**Почему именно эти?** См. ARCHITECTURE_DECISIONS.md

---

## MVP Scope

### ✅ Включено
- 2 агента: Orchestrator + Coder
- Telegram bot с основными командами
- Web UI с 4 страницами (Dashboard, Agent Detail, Chat, Tokens)
- Memory system (быстрая + долговременная)
- 6 базовых скиллов
- Multi-provider LLM с fallback
- Детальное логирование
- Token tracking

### ❌ НЕ включено (после MVP)
- Blogger и другие агенты
- Advanced Coder (git, auto-deploy)
- Prometheus/Grafana
- CI/CD pipeline
- Multi-user support

**Философия MVP**: Минимум функций, максимум качества.

---

## Timeline

**Planning**: 1 день (✅ готово)
**Development**: 15-20 дней
**Total**: ~3 недели до working MVP

**Этапы**:
1. Week 1: Core infrastructure, Memory, Skills
2. Week 2: Orchestrator, Coder
3. Week 3: Web UI, Testing, Deploy

---

## Success Criteria

MVP считается успешным если:

✅ Можно дать задачу Coder через Telegram
✅ Coder создает рабочий скилл с тестами
✅ Результат виден в Telegram и Web UI
✅ Токены отслеживаются и в бюджете
✅ Система стабильно работает на VPS
✅ Fallback механизм работает
✅ Система работает 3+ дня без критических ошибок

---

## Costs

### Development
- Time: 15-20 дней разработки
- LLM API (для тестирования): ~$5-10

### Operation (monthly)
- VPS (4GB RAM): $15-25
- LLM API (активное использование): $30-60
- **Total**: $45-85/месяц

**ROI**: Если система экономит хотя бы 5-10 часов работы в месяц - уже окупается.

---

## Key Benefits

1. **Автоматизация**: Рутинные задачи выполняются автоматически
2. **Масштабируемость**: Легко добавлять новых агентов
3. **Прозрачность**: Полный контроль над действиями и расходами
4. **Гибкость**: Настраивается под любые задачи
5. **Обучаемость**: Агенты накапливают опыт и улучшаются

---

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| LLM API нестабильность | Medium | High | Fallback chain |
| Token costs превышение | Low | Medium | Strict limits + alerts |
| Сложность RabbitMQ | Medium | Medium | Simple topology + tests |
| Coder плохой код | High (initially) | Medium | Tests + retry + memory |

---

## Next Steps

1. ✅ **Planning** - Готово!
2. 🎯 **Setup** - `make setup`
3. 💻 **Development** - Следовать DEVELOPMENT_PLAN.md
4. 🧪 **Testing** - Continuous testing
5. 🚀 **Deploy** - Production на VPS
6. 📊 **Monitor** - Использовать и улучшать

---

## Questions?

- **Техническая документация**: docs/ folder (14 файлов)
- **Быстрый старт**: QUICKSTART.md
- **FAQ**: FAQ.md
- **Примеры**: EXAMPLES.md
- **План**: DEVELOPMENT_PLAN.md

---

## Vision (long-term)

После MVP, система вырастет в:
- 🤖 10+ специализированных агентов
- 🧠 Умная система памяти с auto-consolidation
- 📊 Advanced analytics и мониторинг
- 🔄 CI/CD для автоматического деплоя
- 🌐 API для внешних интеграций
- 👥 Multi-user support

**Но сначала**: Отличный MVP! 🎯

---

**TL;DR**: Система независимых AI-агентов, каждый - эксперт в своей области. Управление через Telegram и Web UI. Полный контроль токенов и расходов. Модульная архитектура для легкого расширения.

**Status**: 📝 Planning Complete → 💻 Ready for Development

**Next**: `make setup` и начать Этап 1!
