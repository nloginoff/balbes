# Документация - Навигация

Полный индекс документации Balbes Multi-Agent System.

---

## 🚀 Быстрый старт

Если вы только начинаете:

1. **[GETTING_STARTED.md](GETTING_STARTED.md)** ⭐
   - С чего начать
   - Порядок чтения документов
   - Preparation checklist
   - Quick setup

2. **[QUICKSTART.md](QUICKSTART.md)**
   - Первый запуск за 5 минут
   - Команды для разработки
   - Troubleshooting

---

## 📋 Основная документация

### Архитектура и дизайн

**[TECHNICAL_SPEC.md](TECHNICAL_SPEC.md)** - Главный документ
- Введение и цели проекта
- Архитектура системы
- Технический стек
- Ключевые компоненты
- Принципы и ограничения

**[ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)**
- Почему выбрали микросервисы
- Почему RabbitMQ, не Kafka
- Почему 3 базы данных
- И другие архитектурные решения

**[MVP_SCOPE.md](MVP_SCOPE.md)**
- Что входит в MVP ✅
- Что НЕ входит в MVP ❌
- Фокус и приоритеты
- Критерии готовности

---

## 🗂️ Технические спецификации

**[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)**
- Полная структура директорий
- Организация кода
- Naming conventions
- Dependencies management

**[DATA_MODELS.md](DATA_MODELS.md)**
- Все Pydantic models
- PostgreSQL schemas
- Redis data structures
- Qdrant collection schema
- Примеры использования

**[API_SPECIFICATION.md](API_SPECIFICATION.md)**
- Memory Service API
- Skills Registry API
- Web Backend API
- WebSocket protocol
- RabbitMQ message protocol
- Error responses

---

## 🤖 Работа с агентами

**[AGENTS_GUIDE.md](AGENTS_GUIDE.md)**
- BaseAgent класс
- Orchestrator Agent детально
- Coder Agent детально
- Telegram команды
- Agent lifecycle
- Communication patterns
- Best practices

**[CONFIGURATION.md](CONFIGURATION.md)**
- Environment variables
- Providers config
- Agent configs
- Skill configs
- Makefile команды
- Hot reload

---

## 🛠️ Разработка

**[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md)** ⭐
- Поэтапный план (10 этапов)
- Timeline (18-20 дней)
- Критерии приемки каждого этапа
- Risks и mitigation
- Checklist задач

**[EXAMPLES.md](EXAMPLES.md)**
- 18 практических примеров
- Создание скилла
- Мониторинг в Web UI
- Fallback scenarios
- Emergency procedures

---

## 🚀 Деплой и эксплуатация

**[DEPLOYMENT.md](DEPLOYMENT.md)**
- Development environment setup
- Production deployment на VPS
- Docker Compose конфигурации
- Systemd service
- Backup & restore
- Monitoring & maintenance
- Troubleshooting

**[FAQ.md](FAQ.md)**
- Часто задаваемые вопросы
- Общие проблемы и решения
- Performance questions
- Security questions
- Scaling considerations

---

## 📚 Дополнительные материалы

**[../README.md](../README.md)**
- Обзор проекта
- Ключевые особенности
- Quick start commands
- Ссылки на документацию

**[../CHANGELOG.md](../CHANGELOG.md)**
- История изменений
- Releases
- Breaking changes

**[../.env.example](../.env.example)**
- Пример конфигурации
- Описание всех переменных
- Development vs Production settings

---

## 🔍 По категориям

### Для начинающих
1. GETTING_STARTED.md - начать здесь ⭐
2. QUICKSTART.md - быстрый запуск
3. TECHNICAL_SPEC.md - общая картина
4. EXAMPLES.md - практические примеры

### Для разработчиков
1. DEVELOPMENT_PLAN.md - план работ ⭐
2. PROJECT_STRUCTURE.md - где что лежит
3. DATA_MODELS.md - структуры данных
4. API_SPECIFICATION.md - все API
5. AGENTS_GUIDE.md - как работают агенты

### Для DevOps
1. DEPLOYMENT.md - деплой и мониторинг ⭐
2. CONFIGURATION.md - все настройки
3. FAQ.md - troubleshooting

### Для архитекторов
1. TECHNICAL_SPEC.md - архитектура ⭐
2. ARCHITECTURE_DECISIONS.md - rationale
3. DATA_MODELS.md - модель данных

---

## 📖 По задачам

### "Хочу понять проект"
→ README.md → TECHNICAL_SPEC.md → MVP_SCOPE.md

### "Хочу начать разработку"
→ GETTING_STARTED.md → QUICKSTART.md → DEVELOPMENT_PLAN.md

### "Ищу конкретный API endpoint"
→ API_SPECIFICATION.md (Ctrl+F для поиска)

### "Не понимаю как работает агент"
→ AGENTS_GUIDE.md → EXAMPLES.md

### "Как задеплоить?"
→ DEPLOYMENT.md

### "Что-то сломалось"
→ FAQ.md → DEPLOYMENT.md (Troubleshooting)

### "Почему именно так сделано?"
→ ARCHITECTURE_DECISIONS.md

---

## 📊 Статистика документации

```
Всего документов: 14
Общий объем: ~3000+ строк
Примеры кода: 100+
Диаграммы: 5+
```

**Основные документы** (must read):
1. GETTING_STARTED.md - 200 строк
2. TECHNICAL_SPEC.md - 350 строк
3. DEVELOPMENT_PLAN.md - 450 строк
4. AGENTS_GUIDE.md - 400 строк

**Итого must-read**: ~1400 строк (~30-40 минут чтения)

---

## 🔗 External Resources

### LLM Providers
- [OpenRouter](https://openrouter.ai/docs) - multi-model API
- [OpenRouter Models](https://openrouter.ai/models) - доступные модели

### Technologies
- [FastAPI](https://fastapi.tiangolo.com/) - Python async web framework
- [Pydantic](https://docs.pydantic.dev/) - data validation
- [RabbitMQ](https://www.rabbitmq.com/documentation.html) - message broker
- [PostgreSQL](https://www.postgresql.org/docs/) - relational database
- [Redis](https://redis.io/docs/) - in-memory database
- [Qdrant](https://qdrant.tech/documentation/) - vector database
- [React](https://react.dev/) - UI library
- [shadcn/ui](https://ui.shadcn.com/) - UI components
- [Tailwind CSS](https://tailwindcss.com/docs) - CSS framework

### Python Libraries
- [python-telegram-bot](https://docs.python-telegram-bot.org/) - Telegram API
- [aio-pika](https://aio-pika.readthedocs.io/) - RabbitMQ async client
- [asyncpg](https://magicstack.github.io/asyncpg/) - PostgreSQL async client
- [qdrant-client](https://github.com/qdrant/qdrant-client) - Qdrant Python client

---

## 📝 Навигация по коду

### Начни с этих файлов

**Core**:
- `shared/models.py` - все модели данных
- `shared/base_agent.py` - базовый класс агента
- `shared/config.py` - конфигурация

**Services**:
- `services/orchestrator/agent.py` - главный агент
- `services/coder/agent.py` - агент-кодер
- `services/memory-service/main.py` - Memory Service API

**Config**:
- `config/providers.yaml` - LLM провайдеры
- `config/agents/*.yaml` - конфиги агентов
- `config/base_instructions.yaml` - общие инструкции

---

## 🎯 Roadmap документации

### После MVP
- [ ] Tutorial videos
- [ ] Interactive examples
- [ ] API playground
- [ ] Architecture diagrams (Mermaid)
- [ ] Performance tuning guide
- [ ] Security best practices
- [ ] Contribution guidelines

### Для пользователей
- [ ] User guide (non-technical)
- [ ] How-to guides для обычных задач
- [ ] Troubleshooting flowcharts
- [ ] Case studies

---

## 💡 Tips для чтения

1. **Не читайте все подряд** - используйте индекс выше для навигации
2. **Начните с overview** - README + TECHNICAL_SPEC
3. **Используйте поиск** - Ctrl+F в документах
4. **Примеры очень полезны** - EXAMPLES.md содержит практические сценарии
5. **Код - тоже документация** - читайте код вместе с docs

---

## 📞 Помощь

Если не нашли ответ в документации:

1. **Поиск**: Ctrl+F по всем docs
2. **FAQ.md**: Частые вопросы
3. **EXAMPLES.md**: Может быть есть похожий пример
4. **GitHub Issues**: Создать issue с вопросом
5. **Code**: Иногда проще посмотреть код

---

## ✅ Checklist готовности к разработке

Прочитали и поняли:
- [ ] GETTING_STARTED.md
- [ ] TECHNICAL_SPEC.md
- [ ] MVP_SCOPE.md
- [ ] PROJECT_STRUCTURE.md
- [ ] DEVELOPMENT_PLAN.md (хотя бы Этап 1)

Настроили:
- [ ] Environment (.env заполнен)
- [ ] Infrastructure (make infra-up работает)
- [ ] Validation (python scripts/validate_config.py проходит)

Готовы:
- [ ] IDE настроена
- [ ] Git repository готов
- [ ] API ключи получены
- [ ] Понимаете план разработки

**Если все checked** → Начинайте! См. DEVELOPMENT_PLAN.md Этап 1, Задача 1.1 🚀

---

**Last updated**: 2026-03-26
**Version**: 0.1.0 (MVP Planning Phase)
