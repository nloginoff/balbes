# MVP Scope - Что входит и не входит

## ✅ Входит в MVP

### Агенты
- ✅ **Orchestrator Agent** - координатор с Telegram ботом
- ✅ **Coder Agent** - создание Python скиллов по описанию

### Инфраструктура
- ✅ BaseAgent класс для всех агентов
- ✅ Multi-provider LLM Client (OpenRouter + AiTunnel)
- ✅ RabbitMQ Message Bus для коммуникации агентов
- ✅ Memory Service (Redis + Qdrant + PostgreSQL)
- ✅ Skills Registry с базовыми скиллами
- ✅ Система логирования (файлы + БД)
- ✅ Токен-трекинг и бюджетирование

### Базовые скиллы (для всех агентов)
- ✅ `search_web` - поиск в интернете
- ✅ `read_file` - чтение файлов
- ✅ `write_file` - запись файлов (с ограничениями)
- ✅ `execute_command` - выполнение shell команд (whitelist)
- ✅ `send_message` - отправка сообщений агентам
- ✅ `query_memory` - поиск в памяти

### Telegram Bot (Orchestrator)
- ✅ `/start` - приветствие
- ✅ `/status` - статус агентов
- ✅ `/task @agent <описание>` - создание задачи
- ✅ `/stop @agent` - остановка задачи
- ✅ `/model @agent <model>` - смена модели
- ✅ `/tokens` - статистика токенов
- ✅ `/logs @agent [N]` - просмотр логов
- ✅ `/help` - справка
- ✅ Уведомления о завершении задач
- ✅ Алерты о токенах и ошибках

### Web UI
- ✅ **Dashboard page**:
  - Список агентов с карточками (статус, токены)
  - Recent activity feed (последние действия)
  - Общая статистика токенов

- ✅ **Agent Detail page**:
  - Детальная информация об агенте
  - Список доступных скиллов
  - Логи с фильтрацией и пагинацией
  - Статистика токенов агента

- ✅ **Chat page**:
  - Выбор агента из dropdown
  - Отправка команд/задач
  - История сообщений

- ✅ **Tokens page**:
  - Таблица использования по агентам
  - График токенов по времени (bar chart)
  - Общая стоимость

- ✅ **Features**:
  - Аутентификация (Bearer token)
  - Light/Dark theme переключатель
  - Real-time updates через WebSocket
  - Адаптивный дизайн (desktop/tablet)
  - Toast уведомления

### LLM Fallback System
- ✅ Цепочка fallback моделей
- ✅ Автоматическое переключение при ошибке
- ✅ Переключение на дешевую модель при превышении токен-лимита
- ✅ Уведомления о fallback в Telegram
- ✅ Логирование всех переключений

### Memory Features
- ✅ Сохранение контекста в Redis (TTL)
- ✅ История диалога (последние 50 сообщений)
- ✅ Индексация важных данных в Qdrant
- ✅ Семантический поиск по памяти
- ✅ Разделение personal/shared scope

### Coder Agent в MVP
- ✅ Создание Python скиллов по описанию
- ✅ Генерация кода + YAML описание + pytest тесты
- ✅ Автоматический запуск тестов
- ✅ Retry до 3 раз при провале тестов
- ✅ Сохранение результата в `/data/coder_output/`
- ✅ Уведомление об успехе/ошибке
- ✅ Поиск примеров в памяти перед созданием

### Development Environment
- ✅ docker-compose.infra.yml (только БД)
- ✅ Makefile с командами для dev
- ✅ Локальный запуск сервисов для разработки
- ✅ .env.example с описанием переменных

### Production Deployment
- ✅ docker-compose.prod.yml (все сервисы)
- ✅ Nginx reverse proxy
- ✅ Health checks для всех сервисов
- ✅ Auto-restart policies
- ✅ Инструкции по деплою на VPS

---

## ❌ НЕ входит в MVP (будущие этапы)

### Агенты
- ❌ Blogger Agent и все его интеграции
- ❌ Researcher Agent
- ❌ Analyst Agent
- ❌ Любые другие специализированные агенты (кроме Orchestrator и Coder)

### Coder Agent Advanced
- ❌ Создание новых агентов
- ❌ Автоматический деплой кода
- ❌ Работа с git (commits, branches, PR)
- ❌ Code review существующего кода
- ❌ Рефакторинг
- ❌ Документация generation

### Telegram Bot Advanced
- ❌ Сложные команды с параметрами
- ❌ Inline keyboards
- ❌ Контекстные диалоги (multi-turn conversations)
- ❌ Голосовые сообщения
- ❌ Группы и каналы (только direct messages)

### Web UI Advanced
- ❌ Визуализация графа взаимодействий агентов
- ❌ Редактирование конфигов агентов через UI
- ❌ Ручное управление памятью (просмотр, редактирование, удаление)
- ❌ Advanced analytics (trends, predictions)
- ❌ Экспорт данных (CSV, JSON)
- ❌ User management (multi-user, roles)
- ❌ Scheduling tasks через UI

### Memory Advanced
- ❌ Автоматическая summarization длинных контекстов
- ❌ Memory consolidation (объединение похожих записей)
- ❌ Забывание (автоматическое удаление неактуальной информации)
- ❌ Memory sharing между агентами с permissions

### Monitoring Advanced
- ❌ Prometheus + Grafana
- ❌ Custom dashboards
- ❌ Alerting rules
- ❌ Performance profiling
- ❌ Distributed tracing

### Infrastructure
- ❌ Kubernetes
- ❌ Service mesh
- ❌ Auto-scaling
- ❌ Multi-region deployment
- ❌ CDN для статики

### Development Tools
- ❌ CI/CD pipeline
- ❌ Automated testing в CI
- ❌ Automated deployments
- ❌ Staging environment
- ❌ Load testing

### Features
- ❌ Плагинная система для агентов
- ❌ Marketplace скиллов
- ❌ Agent templates
- ❌ Webhooks для интеграций
- ❌ REST API для внешних систем
- ❌ CLI tool для управления

---

## 🎯 Фокус MVP

**Главная цель**: Доказать работоспособность архитектуры

**Success criteria**:
1. Можно дать задачу Coder через Telegram
2. Coder создает рабочий скилл с тестами
3. Результат виден в Telegram и Web UI
4. Токены отслеживаются и не превышают бюджет
5. Система стабильно работает на VPS

**Философия MVP**: Минимум функций, максимум качества реализации. Лучше 2 агента, которые работают отлично, чем 5 агентов с багами.

---

## Порядок добавления новых возможностей (после MVP)

### Priority 1 (следующее ТЗ)
1. Blogger Agent - полноценная спецификация
2. Advanced Coder - git integration, auto-deploy workflow
3. Memory management UI - просмотр и управление памятью

### Priority 2
1. Визуализация взаимодействий агентов
2. Researcher Agent
3. Улучшенная система команд Telegram

### Priority 3
1. CI/CD pipeline
2. Advanced monitoring (Prometheus/Grafana)
3. API для внешних интеграций

---

## Критерии готовности к следующему этапу

MVP считается завершенным когда:

- ✅ Все функции из раздела "Входит в MVP" реализованы
- ✅ Критерии приемки из DEVELOPMENT_PLAN.md выполнены
- ✅ Система работает на VPS минимум 3 дня без критических ошибок
- ✅ Coder успешно создал минимум 2 разных скилла
- ✅ Токены используются в пределах бюджета
- ✅ Fallback система сработала минимум 1 раз (доказывает устойчивость)
- ✅ Документация актуальна и полна

После этого можно приступать к разработке следующих агентов и возможностей.
