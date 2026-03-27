# Balbes Multi-Environment Configuration Guide

## Problem

На одном сервере нужно запускать:
- **Development** - для разработки (с hot reload)
- **Testing** - для прогона тестов (изолированно)
- **Production** - для реального использования

Конфликты:
- ❌ Одинаковые порты (8100, 8101, etc.)
- ❌ Одинаковые базы данных
- ❌ Одинаковые Redis ключи
- ❌ Конфликты при одновременном запуске

## Solution

Используем **3 изолированных окружения** с разными портами и базами!

---

## Environment Strategy

```
┌──────────────────────────────────────────────────┐
│ DEVELOPMENT (dev)                                │
│ - Services: 8100-8199                           │
│ - Frontend: 5173                                │
│ - DB: balbes_dev                                │
│ - Docker: balbes-dev-*                          │
│ - Hot reload: ✅                                │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ TESTING (test)                                   │
│ - Services: 9100-9199                           │
│ - Frontend: 5174                                │
│ - DB: balbes_test                               │
│ - Docker: balbes-test-*                         │
│ - Auto cleanup: ✅                              │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ PRODUCTION (prod)                                │
│ - Services: 18100-18200                         │
│ - Frontend: 80/443 (Nginx)                      │
│ - Infra: 15432/16379/16333/15673               │
│ - DB: balbes (production)                       │
│ - Docker: balbes-prod-*                         │
│ - Optimized: ✅                                 │
└──────────────────────────────────────────────────┘
```

---

## Port Allocation

| Service | Dev | Test | Prod |
|---------|-----|------|------|
| Memory | 8100 | 9100 | 18100 |
| Skills | 8101 | 9101 | 18101 |
| Orchestrator | 8102 | 9102 | 18102 |
| Coder | 8103 | 9103 | 18103 |
| Web Backend | 8200 | 9200 | 18200 |
| Frontend | 5173 | 5174 | 80/443 |
| PostgreSQL | 5432 | 5433 | 15432 |
| Redis | 6379 | 6380 | 16379 |
| Qdrant | 6333 | 6334 | 16333 |

---

## Database Naming

| Environment | PostgreSQL DB | Redis Prefix | Qdrant Collection |
|-------------|--------------|--------------|-------------------|
| Dev | `balbes_dev` | `dev:` | `balbes_dev_skills` |
| Test | `balbes_test` | `test:` | `balbes_test_skills` |
| Prod | `balbes` | `prod:` | `balbes_skills` |

---

## Environment Files

### `.env.dev` (Development)

```env
# Environment
ENV=dev
DEBUG=true

# PostgreSQL (shared, different DB)
POSTGRES_HOST=localhost
POSTGRES_PORT=15432
POSTGRES_USER=balbes
POSTGRES_PASSWORD=balbes_secret
POSTGRES_DB=balbes_dev

# Redis (different port)
REDIS_HOST=localhost
REDIS_PORT=16379
REDIS_PREFIX=dev

# Qdrant (different port)
QDRANT_HOST=localhost
QDRANT_PORT=16333
QDRANT_COLLECTION_PREFIX=dev

# Services (dev ports)
MEMORY_SERVICE_PORT=8100
SKILLS_REGISTRY_PORT=8101
ORCHESTRATOR_PORT=8102
CODER_PORT=8103
WEB_BACKEND_PORT=8200

MEMORY_SERVICE_URL=http://localhost:8100
SKILLS_REGISTRY_URL=http://localhost:8101
ORCHESTRATOR_URL=http://localhost:8102
CODER_URL=http://localhost:8103

# Frontend
FRONTEND_PORT=5173

# API Keys (dev)
OPENROUTER_API_KEY=sk-or-dev-key
TELEGRAM_BOT_TOKEN=dev-bot-token

# JWT
JWT_SECRET_KEY=dev-secret-key-for-development-only
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### `.env.test` (Testing)

```env
# Environment
ENV=test
DEBUG=true

# PostgreSQL (test database)
POSTGRES_HOST=localhost
POSTGRES_PORT=5433
POSTGRES_USER=balbes
POSTGRES_PASSWORD=balbes_test_secret
POSTGRES_DB=balbes_test

# Redis (test port)
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_PREFIX=test

# Qdrant (test port)
QDRANT_HOST=localhost
QDRANT_PORT=6334
QDRANT_COLLECTION_PREFIX=test

# Services (test ports)
MEMORY_SERVICE_PORT=9100
SKILLS_REGISTRY_PORT=9101
ORCHESTRATOR_PORT=9102
CODER_PORT=9103
WEB_BACKEND_PORT=9200

MEMORY_SERVICE_URL=http://localhost:9100
SKILLS_REGISTRY_URL=http://localhost:9101
ORCHESTRATOR_URL=http://localhost:9102
CODER_URL=http://localhost:9103

# Frontend
FRONTEND_PORT=5174

# API Keys (test)
OPENROUTER_API_KEY=sk-or-test-key
TELEGRAM_BOT_TOKEN=test-bot-token

# JWT
JWT_SECRET_KEY=test-secret-key-for-testing-only
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### `.env.prod` (Production)

```env
# Environment
ENV=prod
DEBUG=false

# PostgreSQL (production)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=balbes
POSTGRES_PASSWORD=CHANGE_THIS_STRONG_PASSWORD
POSTGRES_DB=balbes

# Redis (production)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=CHANGE_THIS_REDIS_PASSWORD
REDIS_PREFIX=prod

# Qdrant (production)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=CHANGE_THIS_QDRANT_KEY
QDRANT_COLLECTION_PREFIX=prod

# Services (production ports)
MEMORY_SERVICE_PORT=18100
SKILLS_REGISTRY_PORT=18101
ORCHESTRATOR_PORT=18102
CODER_PORT=18103
WEB_BACKEND_PORT=18200

MEMORY_SERVICE_URL=http://localhost:18100
SKILLS_REGISTRY_URL=http://localhost:18101
ORCHESTRATOR_URL=http://localhost:18102
CODER_URL=http://localhost:18103

# Frontend (served by Nginx)
FRONTEND_PORT=80

# API Keys (production)
OPENROUTER_API_KEY=your-real-api-key-here
TELEGRAM_BOT_TOKEN=your-real-bot-token-here

# Web/JWT (secure!)
WEB_AUTH_TOKEN=CHANGE_THIS_WEB_AUTH_TOKEN
JWT_SECRET=CHANGE_THIS_JWT_SECRET
JWT_SECRET_KEY=GENERATE_RANDOM_64_CHAR_SECRET_KEY_HERE
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

---

## Usage Examples

### Development Workflow

```bash
# 1. Start dev infrastructure
./scripts/start_dev.sh

# 2. Work on code with hot reload
cd services/memory-service
# Code changes auto-reload

# 3. Test your changes
pytest tests/integration/test_memory_service.py -v

# 4. Stop dev
./scripts/stop_dev.sh
```

### Testing Workflow

```bash
# 1. Start test environment
./scripts/start_test.sh

# 2. Run tests
pytest tests/ -v

# 3. Stop and cleanup
./scripts/stop_test.sh
# Auto-cleans test database
```

### Production Workflow

```bash
# 1. Start production
./scripts/start_prod.sh

# 2. Monitor
./scripts/status.sh prod

# 3. No stopping! (runs 24/7)
```

### Running All 3 Simultaneously

```bash
# Terminal 1: Development
./scripts/start_dev.sh

# Terminal 2: Testing (in another terminal)
./scripts/start_test.sh
pytest tests/ -v

# Terminal 3: Production (in another terminal)
./scripts/start_prod.sh

# All 3 run independently!
# Dev: ports 8100-8200 + DB balbes_dev
# Test: ports 9100-9200 + DB balbes_test
# Prod: ports 18100-18200 + DB balbes (separate containers)
```

---

## Docker Compose Strategy

### `docker-compose.dev.yml` (Development)

```yaml
version: '3.8'

services:
  postgres-dev:
    image: postgres:15
    container_name: balbes-dev-postgres
    environment:
      POSTGRES_USER: balbes
      POSTGRES_PASSWORD: balbes_secret
      POSTGRES_DB: balbes_dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data

  redis-dev:
    image: redis:7-alpine
    container_name: balbes-dev-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_dev_data:/data

  qdrant-dev:
    image: qdrant/qdrant:latest
    container_name: balbes-dev-qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_dev_data:/qdrant/storage

volumes:
  postgres_dev_data:
  redis_dev_data:
  qdrant_dev_data:
```

### `docker-compose.test.yml` (Testing)

```yaml
version: '3.8'

services:
  postgres-test:
    image: postgres:15
    container_name: balbes-test-postgres
    environment:
      POSTGRES_USER: balbes
      POSTGRES_PASSWORD: balbes_test_secret
      POSTGRES_DB: balbes_test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data

  redis-test:
    image: redis:7-alpine
    container_name: balbes-test-redis
    ports:
      - "6380:6379"
    tmpfs:
      - /data

  qdrant-test:
    image: qdrant/qdrant:latest
    container_name: balbes-test-qdrant
    ports:
      - "6334:6333"
    tmpfs:
      - /qdrant/storage
```

### `docker-compose.prod.yml` (Production)

```yaml
version: '3.8'

services:
  postgres-prod:
    image: postgres:15
    container_name: balbes-prod-postgres
    environment:
      POSTGRES_USER: balbes
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: balbes
    ports:
      - "15432:5432"
    volumes:
      - postgres_prod_data:/var/lib/postgresql/data
    restart: always

  redis-prod:
    image: redis:7-alpine
    container_name: balbes-prod-redis
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "16379:6379"
    volumes:
      - redis_prod_data:/data
    restart: always

  qdrant-prod:
    image: qdrant/qdrant:latest
    container_name: balbes-prod-qdrant
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    ports:
      - "16333:6333"
    volumes:
      - qdrant_prod_data:/qdrant/storage
    restart: always

volumes:
  postgres_prod_data:
  redis_prod_data:
  qdrant_prod_data:
```

---

## Recommended Setup

### Single Server with 3 Environments

```
Server (одна машина)
├── Dev Environment
│   ├── Ports: 8100-8200, 5173
│   ├── DB: balbes_dev (PostgreSQL 5432)
│   ├── Redis: 6379, prefix "dev:"
│   └── Auto-reload: ON
│
├── Test Environment
│   ├── Ports: 9100-9200, 5174
│   ├── DB: balbes_test (PostgreSQL 5433)
│   ├── Redis: 6380, prefix "test:"
│   └── Cleanup: AUTO
│
└── Production Environment
    ├── Ports: 18100-18200 (service layer)
    ├── Infra ports: 15432/16379/16333/15673
    ├── DB: balbes (separate Docker)
    ├── Redis: separate Docker
    └── Isolated: Docker network
```

---

## Best Practices

### 1. Use Docker Networks (Recommended!)

```yaml
# docker-compose.prod.yml with isolated network
version: '3.8'

services:
  memory-service:
    networks:
      - prod-network
    # Only accessible within Docker network

networks:
  prod-network:
    driver: bridge
```

### 2. Different Database Names

```bash
# Dev
psql -h localhost -U balbes -d balbes_dev

# Test
psql -h localhost -p 5433 -U balbes -d balbes_test

# Prod
docker exec balbes-prod-postgres psql -U balbes -d balbes
```

### 3. Redis Key Prefixes

```python
# services/memory-service/clients/redis_client.py
class RedisClient:
    def __init__(self):
        self.prefix = os.getenv("REDIS_PREFIX", "prod")

    def _make_key(self, key: str) -> str:
        return f"{self.prefix}:{key}"
```

### 4. Qdrant in local production

For local dockerized production, Qdrant runs on HTTP (`TLS disabled`).
If API key protection is enabled, clients must still connect with HTTP mode.

Current clients in this repo explicitly set `https=False` for local Qdrant
connections in:

- `services/memory-service/clients/qdrant_client.py`
- `services/skills-registry/clients/qdrant_client.py`

If you see `SSL: WRONG_VERSION_NUMBER`, verify both client config and container env.

---

## Quick Commands

### Start Development
```bash
export ENV=dev
source .env.dev
./scripts/start_dev.sh
```

### Start Testing
```bash
export ENV=test
source .env.test
./scripts/start_test.sh
pytest tests/ -v
./scripts/stop_test.sh
```

### Start Production
```bash
export ENV=prod
./scripts/start_prod.sh
```

---

## Migration Guide

From current setup to multi-environment:

1. Backup current data
2. Create environment configs
3. Stop current services
4. Start in appropriate environment
5. Migrate data if needed

---

See detailed implementation in next files!
