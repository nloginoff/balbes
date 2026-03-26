# Multi-Environment Quick Start

## Проблема решена! ✅

Теперь можно запускать **dev**, **test** и **prod** одновременно на одном сервере без конфликтов!

---

## 🎯 Быстрый старт для каждого окружения

### Development (Разработка)

```bash
# Запуск
./scripts/start_dev.sh

# Порты: 8100-8200
# База: balbes_dev
# Hot reload: ✅

# Frontend (отдельный терминал)
cd web-frontend
npm run dev  # http://localhost:5173

# Остановка
./scripts/stop_dev.sh
```

### Testing (Тестирование)

```bash
# Запуск
./scripts/start_test.sh

# Порты: 9100-9200
# База: balbes_test (tmpfs - авто-очистка)

# Запуск тестов
pytest tests/test_e2e.py -v
pytest tests/test_performance.py -v

# Остановка + cleanup
./scripts/stop_test.sh
```

### Production (Продакшен)

```bash
# Запуск
./scripts/start_prod.sh

# Порты: 8100-8200
# База: balbes (persistent)
# Workers: 2-4 per service

# Мониторинг
./scripts/status.sh
systemctl status balbes-*

# Остановка (осторожно!)
./scripts/stop_prod.sh
```

---

## 🔀 Одновременный запуск всех 3-х!

```bash
# Терминал 1: Development
./scripts/start_dev.sh
cd web-frontend && npm run dev

# Терминал 2: Testing
./scripts/start_test.sh
pytest tests/ -v

# Терминал 3: Production
./scripts/start_prod.sh

# Все работают независимо! 🎉
```

---

## 📊 Порты и базы

| Окружение | Services | DB Port | DB Name | Redis | Qdrant |
|-----------|----------|---------|---------|-------|--------|
| **Dev** | 8100-8200 | 5432 | balbes_dev | 6379 | 6333 |
| **Test** | 9100-9200 | 5433 | balbes_test | 6380 | 6335 |
| **Prod** | 8100-8200 | 5432 | balbes | 6379 | 6333 |

---

## 🎨 Типичные сценарии

### Сценарий 1: Разработка новой фичи

```bash
# 1. Запуск dev
./scripts/start_dev.sh

# 2. Разработка (auto-reload работает)
vim services/memory-service/api/something.py

# 3. Тестирование изменений
curl http://localhost:8100/api/v1/something

# 4. Остановка
./scripts/stop_dev.sh
```

### Сценарий 2: Прогон тестов

```bash
# 1. Запуск test окружения
./scripts/start_test.sh

# 2. Запуск тестов
ENV=test pytest tests/ -v

# 3. Автоматическая очистка при остановке
./scripts/stop_test.sh
```

### Сценарий 3: Dev + Test одновременно

```bash
# Terminal 1
./scripts/start_dev.sh
# Разрабатываем на портах 8100-8200

# Terminal 2
./scripts/start_test.sh
ENV=test pytest tests/ -v
# Тестируем на портах 9100-9200

# Никаких конфликтов! ✨
```

---

## 💡 Преимущества

### ✅ Изоляция
- Разные порты → нет конфликтов
- Разные БД → нет перекрытия данных
- Разные Redis префиксы → нет пересечений

### ✅ Гибкость
- Dev с hot reload
- Test с автоочисткой
- Prod с persistence

### ✅ Безопасность
- Dev: слабые ключи (ок)
- Test: fake API keys (ок)
- Prod: strong secrets (required!)

### ✅ Convenience
- Одна команда для запуска
- Автоматическая проверка
- Простая остановка

---

## 🔧 Переменные окружения

Каждое окружение использует свой `.env` файл:

```bash
.env.dev   # Development (commit to git)
.env.test  # Testing (commit to git)
.env.prod  # Production (NEVER commit! Add to .gitignore)
```

Скрипты автоматически загружают правильный файл!

---

## 🐳 Docker изоляция

```
Development:
├── balbes-dev-postgres (port 5432, DB: balbes_dev)
├── balbes-dev-redis (port 6379, prefix: dev:)
└── balbes-dev-qdrant (port 6333, collection: dev_*)

Testing:
├── balbes-test-postgres (port 5433, DB: balbes_test, tmpfs)
├── balbes-test-redis (port 6380, prefix: test:, tmpfs)
└── balbes-test-qdrant (port 6335, collection: test_*, tmpfs)

Production:
├── balbes-prod-postgres (port 5432, DB: balbes, persistent)
├── balbes-prod-redis (port 6379, prefix: prod:, persistent)
└── balbes-prod-qdrant (port 6333, collection: prod_*, persistent)
```

---

## 📝 Чек-лист при разработке

1. **Начало работы**
   ```bash
   ./scripts/start_dev.sh
   ```

2. **Код изменения**
   - Редактируйте файлы
   - Auto-reload работает
   - Проверяйте в браузере

3. **Локальное тестирование**
   ```bash
   # Быстрый тест одного модуля
   pytest tests/integration/test_memory_service.py -v
   ```

4. **Полное тестирование**
   ```bash
   # В отдельном терминале
   ./scripts/start_test.sh
   ENV=test pytest tests/ -v
   ./scripts/stop_test.sh
   ```

5. **Deploy в prod** (когда готово)
   ```bash
   ./scripts/start_prod.sh
   ```

---

## 🎓 Best Practices

### DO ✅
- Всегда использовать соответствующий скрипт
- Dev для разработки (hot reload)
- Test для тестов (изолированно)
- Prod только для реального использования

### DON'T ❌
- Не тестировать на prod данных
- Не использовать prod ключи в dev
- Не коммитить .env.prod с реальными паролями
- Не запускать prod без проверки паролей

---

## 🆘 Troubleshooting

### Конфликт портов

```bash
# Проверить кто занял порт
sudo lsof -i :8100

# Убить процесс
kill $(lsof -ti:8100)
```

### База не инициализируется

```bash
# Для dev
POSTGRES_DB=balbes_dev python scripts/init_db.py

# Для test
POSTGRES_PORT=5433 POSTGRES_DB=balbes_test python scripts/init_db.py

# Для prod
python scripts/init_db.py
```

### Все упало

```bash
# Остановить всё
./scripts/stop_dev.sh
./scripts/stop_test.sh
./scripts/stop_prod.sh

# Очистить Docker
sg docker -c 'docker-compose -f docker-compose.dev.yml down -v'
sg docker -c 'docker-compose -f docker-compose.test.yml down -v'

# Начать заново
./scripts/start_dev.sh
```

---

Теперь можно **разрабатывать**, **тестировать** и **использовать в prod** без конфликтов! 🎉
