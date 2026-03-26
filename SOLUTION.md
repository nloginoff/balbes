# Решение проблемы Multi-Environment

## ❓ Проблема

**Вопрос**: Как разрабатывать и тестировать на одном сервере, если порты и базы одинаковые?

**Проблемы**:
- ❌ Конфликт портов (8100, 8101, etc.)
- ❌ Конфликт баз данных (balbes)
- ❌ Перекрытие Redis ключей
- ❌ Невозможность одновременного запуска

## ✅ Решение

Создана система **3-х изолированных окружений** с разными портами, базами и конфигурациями!

---

## 🎯 Архитектура решения

```
┌─────────────────────────────────────────────────────────────┐
│                    ОДНА МАШИНА (VPS)                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🟦 DEVELOPMENT (разработка с hot reload)                  │
│  ├─ Services: 8100-8200                                    │
│  ├─ PostgreSQL: 5432, DB: balbes_dev                       │
│  ├─ Redis: 6379, prefix: dev:                              │
│  ├─ Qdrant: 6333, collection: dev_*                        │
│  ├─ Frontend: 5173                                         │
│  └─ Docker: balbes-dev-*                                   │
│                                                             │
│  🟨 TESTING (автоматические тесты + очистка)              │
│  ├─ Services: 9100-9200                                    │
│  ├─ PostgreSQL: 5433, DB: balbes_test (tmpfs!)            │
│  ├─ Redis: 6380, prefix: test: (tmpfs!)                   │
│  ├─ Qdrant: 6335, collection: test_* (tmpfs!)             │
│  ├─ Frontend: 5174                                         │
│  ├─ Docker: balbes-test-*                                  │
│  └─ Auto-cleanup при stop!                                │
│                                                             │
│  🟩 PRODUCTION (изолированная сеть + persistence)         │
│  ├─ Services: 8100-8200 (Docker network)                  │
│  ├─ PostgreSQL: Docker container, DB: balbes              │
│  ├─ Redis: Docker container, prefix: prod:                │
│  ├─ Qdrant: Docker container, collection: prod_*          │
│  ├─ Frontend: Nginx на port 80/443                        │
│  ├─ Docker: balbes-prod-* (separate network)              │
│  └─ Persistent volumes!                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Ключевые решения

### 1. Разные порты для Test

| Service | Dev | Test | Prod |
|---------|-----|------|------|
| Memory | 8100 | **9100** | 8100 |
| Skills | 8101 | **9101** | 8101 |
| Orchestrator | 8102 | **9102** | 8102 |
| Coder | 8103 | **9103** | 8103 |
| Web Backend | 8200 | **9200** | 8200 |
| PostgreSQL | 5432 | **5433** | 5432 |
| Redis | 6379 | **6380** | 6379 |
| Qdrant | 6333 | **6335** | 6333 |

### 2. Разные базы данных

```sql
-- Development
CREATE DATABASE balbes_dev;

-- Testing
CREATE DATABASE balbes_test;

-- Production
CREATE DATABASE balbes;
```

### 3. Redis префиксы

```
dev:context:agent123       # Development
test:context:agent123      # Testing
prod:context:agent123      # Production
```

### 4. Qdrant коллекции

```
dev_skills                 # Development
test_skills                # Testing
prod_skills                # Production
```

### 5. Изоляция через Docker networks

```yaml
# Prod имеет отдельную сеть
networks:
  balbes-prod-network:
    driver: bridge
```

---

## 📁 Созданные файлы

### Environment Configs (3 файла)
```
.env.dev        # Dev конфигурация (commit to git)
.env.test       # Test конфигурация (commit to git)
.env.prod       # Prod шаблон (НЕ commit!)
```

### Docker Compose (3 файла)
```
docker-compose.dev.yml      # Dev infrastructure
docker-compose.test.yml     # Test infrastructure (tmpfs!)
docker-compose.prod.yml     # Prod infrastructure (isolated)
```

### Scripts (7 файлов)
```
scripts/start_dev.sh        # Запуск dev
scripts/stop_dev.sh         # Остановка dev
scripts/start_test.sh       # Запуск test
scripts/stop_test.sh        # Остановка test + cleanup
scripts/start_prod.sh       # Запуск prod
scripts/stop_prod.sh        # Остановка prod
scripts/status_all_envs.sh  # Статус всех окружений
```

### Documentation (3 файла)
```
ENVIRONMENTS.md              # Концепция multi-env
MULTI_ENV_QUICKSTART.md      # Quick start для каждого env
SOLUTION.md                  # Это файл (детальное решение)
```

**Total**: 16 новых файлов

---

## 🚀 Как это использовать

### Сценарий 1: Разработка фичи

```bash
# Утро: Запуск dev
./scripts/start_dev.sh

# День: Код + auto-reload
vim services/memory-service/api/new_feature.py
# Сохранили → сервис перезагрузился!

# Проверка
curl http://localhost:8100/api/v1/new_feature

# Вечер: Остановка
./scripts/stop_dev.sh
```

### Сценарий 2: Запуск тестов

```bash
# Запуск test окружения
./scripts/start_test.sh

# Прогон тестов (автоматически используют порты 9100-9200)
ENV=test pytest tests/ -v

# Остановка + автоматическая очистка
./scripts/stop_test.sh
```

### Сценарий 3: Dev + Test одновременно

```bash
# Terminal 1: Development
./scripts/start_dev.sh
cd web-frontend && npm run dev
# Работаем на портах 8100-8200

# Terminal 2: Testing
./scripts/start_test.sh
ENV=test pytest tests/ -v
# Тестируем на портах 9100-9200

# НЕТ КОНФЛИКТОВ! ✨
```

### Сценарий 4: Все 3 окружения

```bash
# Terminal 1: Dev
./scripts/start_dev.sh

# Terminal 2: Test
./scripts/start_test.sh

# Terminal 3: Prod
./scripts/start_prod.sh

# Terminal 4: Мониторинг
watch -n 5 ./scripts/status_all_envs.sh

# Все работают независимо!
```

---

## 🎨 Визуализация

```
Port Layout на одном сервере:

5000-5999: Frontend
├─ 5173: Dev Frontend
├─ 5174: Test Frontend
└─ 80/443: Prod Frontend (Nginx)

6000-6999: Infrastructure
├─ 6333: Dev Qdrant
├─ 6335: Test Qdrant
├─ 6379: Dev Redis
├─ 6380: Test Redis
├─ 5432: Dev PostgreSQL
└─ 5433: Test PostgreSQL

8000-8999: Dev & Prod Services
├─ 8100: Dev/Prod Memory
├─ 8101: Dev/Prod Skills
├─ 8102: Dev/Prod Orchestrator
├─ 8103: Dev/Prod Coder
└─ 8200: Dev/Prod Web Backend

9000-9999: Test Services
├─ 9100: Test Memory
├─ 9101: Test Skills
├─ 9102: Test Orchestrator
├─ 9103: Test Coder
└─ 9200: Test Web Backend
```

---

## 🔒 Изоляция данных

### Development
```
PostgreSQL: balbes_dev
Redis keys: dev:context:*, dev:history:*
Qdrant: dev_skills, dev_memory
Logs: /tmp/balbes-dev-*.log
```

### Testing
```
PostgreSQL: balbes_test (tmpfs - в памяти!)
Redis keys: test:context:*, test:history:*
Qdrant: test_skills, test_memory (tmpfs!)
Logs: /tmp/balbes-test-*.log
Auto-cleanup: ✅
```

### Production
```
PostgreSQL: balbes (persistent volume)
Redis keys: prod:context:*, prod:history:*
Qdrant: prod_skills, prod_memory (persistent)
Logs: /var/log/balbes-*.log
Backup: automated
```

---

## 💡 Преимущества решения

### ✅ Полная изоляция
- Каждое окружение независимо
- Разные порты → нет конфликтов
- Разные БД → нет перекрытия
- Разные Docker контейнеры → полная изоляция

### ✅ Удобство разработки
- Dev с hot reload
- Test с автоочисткой
- Prod со стабильностью

### ✅ Безопасность
- Test использует tmpfs (данные в памяти)
- Prod изолирован в Docker network
- Разные пароли для каждого env

### ✅ Гибкость
- Можно запускать 1, 2 или 3 окружения
- Легко переключаться
- Простые команды

---

## 🧪 Тестирование

### Dev тесты (быстрые)

```bash
# Без запуска test окружения
pytest tests/integration/test_memory_service.py -v
# Использует dev порты (8100-8200)
```

### Test тесты (полные)

```bash
# С запуском test окружения
./scripts/start_test.sh
ENV=test pytest tests/ -v
./scripts/stop_test.sh
# Использует test порты (9100-9200)
```

---

## 📊 Сравнение подходов

| Подход | Конфликты | Изоляция | Сложность | Рекомендация |
|--------|-----------|----------|-----------|--------------|
| Один порт | ❌ Да | ❌ Нет | 🟢 Low | ❌ Плохо |
| Разные машины | ✅ Нет | ✅ Полная | 🔴 High | ⚠️ Дорого |
| **Разные порты** | ✅ Нет | ✅ Хорошая | 🟡 Medium | ✅ **Оптимально!** |

---

## 🎓 Best Practices

### Development
```bash
# Каждый день
./scripts/start_dev.sh
# ... разработка ...
./scripts/stop_dev.sh
```

### Before Commit
```bash
# Запуск тестов в изолированном окружении
./scripts/start_test.sh
ENV=test pytest tests/ -v
./scripts/stop_test.sh
```

### Production
```bash
# Один раз настроили
./scripts/start_prod.sh

# Мониторим
./scripts/status_all_envs.sh

# Обновления через CI/CD
```

---

## 🎉 Результат

Теперь на **одном сервере** можно:

✅ Разрабатывать (dev)
✅ Тестировать (test)
✅ Использовать в production (prod)
✅ **Всё одновременно!**

Без конфликтов, с полной изоляцией и удобными командами!

---

## 📝 Быстрая шпаргалка

```bash
# Development
./scripts/start_dev.sh      # Запуск
./scripts/stop_dev.sh       # Остановка

# Testing
./scripts/start_test.sh     # Запуск
ENV=test pytest tests/ -v   # Тесты
./scripts/stop_test.sh      # Остановка + cleanup

# Production
./scripts/start_prod.sh     # Запуск
./scripts/stop_prod.sh      # Остановка

# Статус всех окружений
./scripts/status_all_envs.sh
```

---

Проблема **решена**! 🎊
