# Deployment Guide

## Development Environment Setup

### Prerequisites

- Python 3.13+
- Docker и Docker Compose
- Node.js 18+ (для frontend)
- Git
- 8GB RAM минимум
- 20GB свободного места на диске

### Initial Setup

```bash
# 1. Клонировать репозиторий (или создать структуру)
cd /home/balbes/projects/dev

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или .venv\Scripts\activate  # Windows

# 3. Установить зависимости
pip install -e .[dev]

# 4. Создать .env файл
cp .env.example .env

# Заполнить в .env:
# - OPENROUTER_API_KEY
# - TELEGRAM_BOT_TOKEN
# - TELEGRAM_USER_ID
# - WEB_AUTH_TOKEN
# - Остальное можно оставить defaults для dev

# 5. Validate конфигурация
python scripts/validate_config.py

# 6. Поднять инфраструктуру (БД)
make infra-up

# Подождать пока все поднимется (~10 секунд)
docker-compose -f docker-compose.infra.yml ps
# Все должны быть Up и healthy

# 7. Инициализировать базы данных
make db-init      # PostgreSQL schema
make db-seed      # Загрузка базовых скиллов

# 8. Проверка что БД готовы
psql -h localhost -U balbes -d balbes_agents -c "\dt"
redis-cli ping
curl http://localhost:6333/collections  # Qdrant
curl http://localhost:15672  # RabbitMQ Management UI (guest:guest)
```

### Running Services (Development)

Открыть 6 терминалов:

**Terminal 1: Memory Service**
```bash
cd services/memory-service
uvicorn main:app --reload --host 0.0.0.0 --port 8100

# Проверка: curl http://localhost:8100/health
```

**Terminal 2: Skills Registry**
```bash
cd services/skills-registry
uvicorn main:app --reload --host 0.0.0.0 --port 8101

# Проверка: curl http://localhost:8101/api/v1/skills
```

**Terminal 3: Orchestrator**
```bash
cd services/orchestrator
python main.py

# Проверка: Telegram бот должен ответить на /start
```

**Terminal 4: Coder**
```bash
cd services/coder
python main.py

# Проверка: В логах должно быть "Coder agent started"
```

**Terminal 5: Web Backend**
```bash
cd services/web/backend
uvicorn main:app --reload --host 0.0.0.0 --port 8200

# Проверка: curl http://localhost:8200/health
```

**Terminal 6: Web Frontend**
```bash
cd services/web/frontend
npm install  # Первый раз
npm run dev

# Проверка: Открыть http://localhost:5173
```

### Alternative: tmux для всех сервисов

```bash
# Создать tmux сессию с 6 панелями
tmux new-session -s balbes \; \
  split-window -h \; \
  split-window -v \; \
  select-pane -t 0 \; \
  split-window -v \; \
  select-pane -t 2 \; \
  split-window -v \; \
  select-pane -t 4 \; \
  split-window -v

# В каждой панели запустить соответствующий сервис
# Переключение: Ctrl+B затем arrow keys
# Отключиться: Ctrl+B затем D
# Вернуться: tmux attach -t balbes
```

---

## Production Deployment (VPS)

### VPS Requirements

- **OS**: Ubuntu 22.04 LTS (recommended) или Debian 12
- **RAM**: 4GB минимум, 8GB рекомендуется
- **Disk**: 40GB SSD минимум
- **CPU**: 2 cores минимум
- **Network**: Статический IP

### VPS Initial Setup

```bash
# 1. Подключиться к VPS
ssh root@your-vps-ip

# 2. Обновить систему
apt update && apt upgrade -y

# 3. Создать пользователя для приложения
adduser balbes
usermod -aG sudo balbes
usermod -aG docker balbes  # После установки Docker

# 4. Настроить SSH ключи
mkdir -p /home/balbes/.ssh
cp ~/.ssh/authorized_keys /home/balbes/.ssh/
chown -R balbes:balbes /home/balbes/.ssh
chmod 700 /home/balbes/.ssh
chmod 600 /home/balbes/.ssh/authorized_keys

# 5. Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
systemctl enable docker
systemctl start docker

# 6. Установить Docker Compose
apt install docker-compose-plugin -y

# 7. Настроить firewall
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw enable

# 8. Установить дополнительные утилиты
apt install -y git make curl wget htop

# 9. Переключиться на пользователя balbes
su - balbes
```

### Deployment Steps

```bash
# 1. Клонировать репозиторий
cd ~
git clone <your-repo-url> balbes-agents
cd balbes-agents

# 2. Создать production .env
cp .env.example .env
nano .env

# Заполнить production values:
# - Реальные API keys
# - Сильные пароли для БД
# - Production URLs/domains
# - DEBUG=false
# - LOG_LEVEL=INFO

# 3. Создать директории для данных
mkdir -p data/{logs,coder_output,postgres,redis,rabbitmq,qdrant}

# 4. Build Docker images
docker compose -f docker-compose.prod.yml build

# Это может занять 5-10 минут при первом запуске

# 5. Запустить все сервисы
docker compose -f docker-compose.prod.yml up -d

# 6. Проверить статус
docker compose -f docker-compose.prod.yml ps

# Все должны быть Up и healthy
# Если какой-то сервис Unhealthy - смотреть логи:
# docker compose -f docker-compose.prod.yml logs <service-name>

# 7. Инициализировать БД (только первый раз)
docker compose -f docker-compose.prod.yml exec orchestrator python /app/scripts/init_db.py
docker compose -f docker-compose.prod.yml exec orchestrator python /app/scripts/seed_skills.py

# Или если скрипты в отдельном контейнере:
docker run --rm \
  --network balbes_backend \
  --env-file .env \
  -v $(pwd)/scripts:/scripts \
  -v $(pwd)/shared:/shared \
  -v $(pwd)/config:/config \
  python:3.13-slim \
  python /scripts/init_db.py

# 8. Проверить логи
docker compose -f docker-compose.prod.yml logs -f

# Должны увидеть:
# - "Orchestrator agent started"
# - "Coder agent started"
# - "Memory Service started"
# - "Skills Registry started"
# - "Web Backend started"

# 9. Тест через Telegram
# Отправить /start боту - должен ответить

# 10. Открыть Web UI
# http://your-vps-ip
# Залогиниться с WEB_AUTH_TOKEN

# 11. Финальная проверка - создать задачу
# Через Telegram: /task @coder создай тестовый скилл для проверки деплоя
```

### Systemd Service (Auto-start)

```bash
# Создать systemd unit
sudo nano /etc/systemd/system/balbes-agents.service
```

```ini
[Unit]
Description=Balbes Multi-Agent System
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/balbes/balbes-agents
User=balbes
Group=balbes

# Start
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d

# Stop
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down

# Reload
ExecReload=/usr/bin/docker compose -f docker-compose.prod.yml restart

[Install]
WantedBy=multi-user.target
```

```bash
# Активировать
sudo systemctl daemon-reload
sudo systemctl enable balbes-agents.service
sudo systemctl start balbes-agents.service

# Проверить статус
sudo systemctl status balbes-agents.service

# Тест reboot
sudo reboot
# После перезагрузки:
ssh balbes@your-vps-ip
docker ps  # Все контейнеры должны быть running
```

---

## docker-compose.infra.yml (Development)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: balbes-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-balbes_agents}
      POSTGRES_USER: ${POSTGRES_USER:-balbes}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-balbes}"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - balbes

  redis:
    image: redis:7-alpine
    container_name: balbes-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    ports:
      - "${REDIS_PORT:-6379}:6379"
    volumes:
      - ./data/redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - balbes

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: balbes-rabbitmq
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-guest}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD:-guest}
    ports:
      - "${RABBITMQ_PORT:-5672}:5672"
      - "${RABBITMQ_MANAGEMENT_PORT:-15672}:15672"
    volumes:
      - ./data/rabbitmq:/var/lib/rabbitmq
    healthcheck:
      test: rabbitmq-diagnostics -q ping
      interval: 10s
      timeout: 10s
      retries: 5
    networks:
      - balbes

  qdrant:
    image: qdrant/qdrant:latest
    container_name: balbes-qdrant
    restart: unless-stopped
    ports:
      - "${QDRANT_PORT:-6333}:6333"
      - "6334:6334"  # gRPC
    volumes:
      - ./data/qdrant:/qdrant/storage
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - balbes

networks:
  balbes:
    name: balbes_network
    driver: bridge
```

**Usage**:
```bash
docker-compose -f docker-compose.infra.yml up -d
docker-compose -f docker-compose.infra.yml ps
docker-compose -f docker-compose.infra.yml logs -f
docker-compose -f docker-compose.infra.yml down
```

---

## docker-compose.prod.yml (Production)

```yaml
version: '3.8'

services:
  # =============================================
  # Infrastructure
  # =============================================

  postgres:
    image: postgres:16-alpine
    container_name: balbes-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - backend

  redis:
    image: redis:7-alpine
    container_name: balbes-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - ./data/redis:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - backend

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: balbes-rabbitmq
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    volumes:
      - ./data/rabbitmq:/var/lib/rabbitmq
    healthcheck:
      test: rabbitmq-diagnostics -q ping
      interval: 10s
      timeout: 10s
      retries: 5
    networks:
      - backend

  qdrant:
    image: qdrant/qdrant:latest
    container_name: balbes-qdrant
    restart: unless-stopped
    volumes:
      - ./data/qdrant:/qdrant/storage
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - backend

  # =============================================
  # Application Services
  # =============================================

  memory-service:
    build:
      context: .
      dockerfile: services/memory-service/Dockerfile
    container_name: balbes-memory-service
    restart: unless-stopped
    env_file: .env
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - QDRANT_HOST=qdrant
      - RABBITMQ_HOST=rabbitmq
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  skills-registry:
    build:
      context: .
      dockerfile: services/skills-registry/Dockerfile
    container_name: balbes-skills-registry
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./config/skills:/app/config/skills:ro
      - ./shared/skills:/app/shared/skills:ro
    depends_on:
      - memory-service
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8101/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.25'

  orchestrator:
    build:
      context: .
      dockerfile: services/orchestrator/Dockerfile
    container_name: balbes-orchestrator
    restart: unless-stopped
    env_file: .env
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - RABBITMQ_HOST=rabbitmq
    depends_on:
      memory-service:
        condition: service_healthy
      skills-registry:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  coder:
    build:
      context: .
      dockerfile: services/coder/Dockerfile
    container_name: balbes-coder
    restart: unless-stopped
    env_file: .env
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - RABBITMQ_HOST=rabbitmq
    volumes:
      - ./data/coder_output:/data/coder_output
    depends_on:
      memory-service:
        condition: service_healthy
      skills-registry:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    networks:
      - backend
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.0'

  web-backend:
    build:
      context: .
      dockerfile: services/web/backend/Dockerfile
    container_name: balbes-web-backend
    restart: unless-stopped
    env_file: .env
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - RABBITMQ_HOST=rabbitmq
    depends_on:
      memory-service:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8200/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - backend
      - frontend
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'

  web-frontend:
    build:
      context: services/web/frontend
      dockerfile: Dockerfile
      args:
        - VITE_API_URL=http://your-vps-ip/api  # Заменить на реальный
        - VITE_WS_URL=ws://your-vps-ip/ws
    container_name: balbes-web-frontend
    restart: unless-stopped
    networks:
      - frontend
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: '0.25'

  nginx:
    image: nginx:alpine
    container_name: balbes-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./data/ssl:/etc/nginx/ssl:ro  # Для HTTPS сертификатов
      - ./data/nginx-logs:/var/log/nginx
    depends_on:
      - web-frontend
      - web-backend
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - frontend
    deploy:
      resources:
        limits:
          memory: 128M
          cpus: '0.25'

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
  rabbitmq_data:
  qdrant_data:
```

**Usage**:
```bash
# Start
docker compose -f docker-compose.prod.yml up -d

# Status
docker compose -f docker-compose.prod.yml ps

# Logs (all services)
docker compose -f docker-compose.prod.yml logs -f

# Logs (specific service)
docker compose -f docker-compose.prod.yml logs -f coder

# Restart service
docker compose -f docker-compose.prod.yml restart coder

# Stop all
docker compose -f docker-compose.prod.yml down

# Stop and remove volumes (DANGER: удалит все данные!)
docker compose -f docker-compose.prod.yml down -v
```

---

## SSL/HTTPS Setup (Optional for MVP)

### Using Let's Encrypt (Free)

```bash
# 1. Установить certbot
sudo apt install certbot

# 2. Получить сертификат (остановить nginx на время)
docker compose -f docker-compose.prod.yml stop nginx

sudo certbot certonly --standalone -d your-domain.com

# Сертификаты будут в /etc/letsencrypt/live/your-domain.com/

# 3. Скопировать в проект
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ./data/ssl/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ./data/ssl/
sudo chown -R balbes:balbes ./data/ssl

# 4. Обновить nginx.conf (раскомментировать SSL секцию)

# 5. Перезапустить nginx
docker compose -f docker-compose.prod.yml up -d nginx

# 6. Настроить auto-renewal
sudo certbot renew --dry-run  # Тест
sudo crontab -e
# Добавить:
# 0 3 * * * certbot renew --quiet --deploy-hook "systemctl reload balbes-agents"
```

---

## Backup & Restore

### Automated Backup Script

```bash
# scripts/backup.sh

#!/bin/bash

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

echo "Starting backup at $DATE..."

# PostgreSQL
echo "Backing up PostgreSQL..."
docker exec balbes-postgres pg_dump -U balbes balbes_agents > $BACKUP_DIR/postgres_$DATE.sql

# Qdrant (просто копируем volume)
echo "Backing up Qdrant..."
tar -czf $BACKUP_DIR/qdrant_$DATE.tar.gz -C data/qdrant .

# Coder output (созданные скиллы)
echo "Backing up Coder output..."
tar -czf $BACKUP_DIR/coder_output_$DATE.tar.gz -C data/coder_output .

# Configs (на всякий случай)
echo "Backing up configs..."
tar -czf $BACKUP_DIR/configs_$DATE.tar.gz config/

echo "Backup completed!"

# Cleanup old backups (оставить последние 7)
echo "Cleaning old backups..."
ls -t $BACKUP_DIR/postgres_*.sql | tail -n +8 | xargs rm -f
ls -t $BACKUP_DIR/qdrant_*.tar.gz | tail -n +8 | xargs rm -f
ls -t $BACKUP_DIR/coder_output_*.tar.gz | tail -n +8 | xargs rm -f

echo "Done!"
```

```bash
# Сделать executable
chmod +x scripts/backup.sh

# Запустить вручную
./scripts/backup.sh

# Или настроить cron (каждый день в 3:00)
crontab -e
# Добавить:
# 0 3 * * * cd /home/balbes/balbes-agents && ./scripts/backup.sh >> data/logs/backup.log 2>&1
```

### Restore

```bash
# PostgreSQL
docker exec -i balbes-postgres psql -U balbes balbes_agents < backups/postgres_20260326_030000.sql

# Qdrant
docker compose -f docker-compose.prod.yml stop qdrant
rm -rf data/qdrant/*
tar -xzf backups/qdrant_20260326_030000.tar.gz -C data/qdrant/
docker compose -f docker-compose.prod.yml start qdrant

# Coder output
tar -xzf backups/coder_output_20260326_030000.tar.gz -C data/coder_output/
```

---

## Monitoring & Maintenance

### Health Checks

```bash
# Скрипт для проверки всех сервисов
# scripts/healthcheck.sh

#!/bin/bash

echo "Checking service health..."

# PostgreSQL
docker exec balbes-postgres pg_isready -U balbes && echo "✅ PostgreSQL" || echo "❌ PostgreSQL"

# Redis
docker exec balbes-redis redis-cli ping | grep -q PONG && echo "✅ Redis" || echo "❌ Redis"

# RabbitMQ
curl -s -u guest:guest http://localhost:15672/api/health/checks/alarms | grep -q '"status":"ok"' && echo "✅ RabbitMQ" || echo "❌ RabbitMQ"

# Qdrant
curl -s http://localhost:6333/healthz | grep -q "ok" && echo "✅ Qdrant" || echo "❌ Qdrant"

# Memory Service
curl -sf http://localhost:8100/health && echo "✅ Memory Service" || echo "❌ Memory Service"

# Skills Registry
curl -sf http://localhost:8101/health && echo "✅ Skills Registry" || echo "❌ Skills Registry"

# Web Backend
curl -sf http://localhost:8200/health && echo "✅ Web Backend" || echo "❌ Web Backend"

# Orchestrator и Coder (проверяем что процессы живы)
docker ps | grep -q balbes-orchestrator && echo "✅ Orchestrator" || echo "❌ Orchestrator"
docker ps | grep -q balbes-coder && echo "✅ Coder" || echo "❌ Coder"

echo "Done!"
```

### Log Rotation

```bash
# Автоматическая ротация логов
# /etc/logrotate.d/balbes-agents

/home/balbes/balbes-agents/data/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 balbes balbes
    sharedscripts
    postrotate
        # Можно отправить signal для reopen файлов
        # docker compose -f /home/balbes/balbes-agents/docker-compose.prod.yml restart
    endscript
}
```

### Disk Usage Monitoring

```bash
# scripts/check_disk_usage.sh

#!/bin/bash

THRESHOLD=80  # Alert if > 80%

echo "Checking disk usage..."

# Overall disk
USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $USAGE -gt $THRESHOLD ]; then
    echo "⚠️ Disk usage: ${USAGE}% (threshold: ${THRESHOLD}%)"
    # Отправить alert в Telegram (опционально)
else
    echo "✅ Disk usage: ${USAGE}%"
fi

# Data directories
echo ""
echo "Data directories:"
du -sh data/postgres
du -sh data/qdrant
du -sh data/logs
du -sh data/coder_output

# Database sizes
echo ""
echo "Database sizes:"
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT
    pg_size_pretty(pg_database_size('balbes_agents')) as db_size,
    pg_size_pretty(pg_total_relation_size('action_logs')) as logs_size,
    pg_size_pretty(pg_total_relation_size('token_usage')) as tokens_size;
"
```

### Regular Maintenance Tasks

**Daily** (автоматически через cron):
- Backup databases (3:00 AM)
- Check disk usage
- Cleanup old logs (> 7 дней)

**Weekly**:
- Review token usage и costs
- Check error rates в логах
- Review agent performance

**Monthly**:
- Vacuum PostgreSQL
- Optimize Qdrant indices
- Review и cleanup old memories (если накопилось много)

```bash
# Добавить в crontab
crontab -e

# Daily backups
0 3 * * * cd /home/balbes/balbes-agents && ./scripts/backup.sh >> data/logs/backup.log 2>&1

# Daily cleanup
0 4 * * * cd /home/balbes/balbes-agents && make clean-logs

# Daily disk check
0 5 * * * cd /home/balbes/balbes-agents && ./scripts/check_disk_usage.sh >> data/logs/disk_usage.log

# Weekly PostgreSQL vacuum
0 2 * * 0 docker exec balbes-postgres vacuumdb -U balbes -d balbes_agents -z
```

---

## Updating / Redeployment

### Updating Code

```bash
# 1. Pull latest code
cd /home/balbes/balbes-agents
git pull origin main

# 2. Rebuild images
docker compose -f docker-compose.prod.yml build

# 3. Restart services (zero-downtime не гарантируется в MVP)
docker compose -f docker-compose.prod.yml up -d

# Старые контейнеры остановятся, новые запустятся

# 4. Проверить что все поднялось
docker compose -f docker-compose.prod.yml ps

# 5. Проверить логи на ошибки
docker compose -f docker-compose.prod.yml logs --tail=50

# 6. Функциональный тест
# Через Telegram: /status
```

### Rolling Update (для будущего)

Для минимизации downtime:
```bash
# Обновлять по одному сервису
docker compose -f docker-compose.prod.yml up -d --no-deps --build orchestrator
# Подождать пока поднимется
docker compose -f docker-compose.prod.yml up -d --no-deps --build coder
# И так далее
```

---

## Troubleshooting

### Service не запускается

```bash
# 1. Проверить логи
docker compose -f docker-compose.prod.yml logs <service-name>

# 2. Проверить что зависимости healthy
docker compose -f docker-compose.prod.yml ps

# 3. Проверить что порты не заняты
netstat -tulpn | grep <port>

# 4. Проверить environment variables
docker compose -f docker-compose.prod.yml config

# 5. Попробовать запустить вручную
docker compose -f docker-compose.prod.yml run --rm <service-name> sh
# Внутри контейнера:
python main.py  # Смотреть на ошибки
```

### PostgreSQL проблемы

```bash
# Проверить подключение
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "SELECT 1"

# Проверить размер БД
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT pg_size_pretty(pg_database_size('balbes_agents'));
"

# Проверить медленные запросы
docker exec balbes-postgres psql -U balbes -d balbes_agents -c "
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
ORDER BY mean_time DESC
LIMIT 10;
"
```

### RabbitMQ проблемы

```bash
# Management UI
open http://localhost:15672
# Login: guest / guest

# Проверить очереди
docker exec balbes-rabbitmq rabbitmqctl list_queues

# Проверить connections
docker exec balbes-rabbitmq rabbitmqctl list_connections

# Очистить очередь (если застряла)
docker exec balbes-rabbitmq rabbitmqctl purge_queue coder.tasks
```

### Qdrant проблемы

```bash
# Проверить коллекции
curl http://localhost:6333/collections

# Проверить размер коллекции
curl http://localhost:6333/collections/agent_memory

# Backup и recreate (если corrupted)
docker compose stop qdrant
cp -r data/qdrant data/qdrant.backup
rm -rf data/qdrant/*
docker compose start qdrant
# Пересоздать коллекцию через API
```

### Agent зависает

```bash
# 1. Проверить логи агента
tail -100 data/logs/coder.log

# 2. Проверить текущую задачу
docker compose exec memory-service python -c "
from clients.postgres_client import PostgresClient
import asyncio
client = PostgresClient()
task = asyncio.run(client.get_current_task('coder'))
print(task)
"

# 3. Остановить задачу через Telegram
# /stop @coder

# 4. Если не помогло - restart контейнера
docker compose restart coder
```

### High token usage

```bash
# 1. Проверить статистику
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8200/api/tokens/stats?period=today

# 2. Проверить логи для агента
docker compose logs coder | grep "llm_call"

# 3. Проверить размер контекста в вызовах
grep "context_size" data/logs/coder.log | tail -20

# 4. Временно переключить на дешевую модель
# /model @coder openrouter/gpt-4o-mini
```

---

## Performance Optimization

### PostgreSQL

```sql
-- В production рекомендуется периодически:

-- Vacuum для освобождения места
VACUUM ANALYZE;

-- Reindex для оптимизации индексов
REINDEX DATABASE balbes_agents;

-- Проверка размеров таблиц
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Redis

```bash
# Проверка памяти
docker exec balbes-redis redis-cli INFO memory

# Если много памяти используется - можно flush неважное
docker exec balbes-redis redis-cli --scan --pattern "context:*" | xargs docker exec -i balbes-redis redis-cli DEL

# Или настроить eviction policy (уже в docker-compose: allkeys-lru)
```

**Экспорт всех чатов Memory (Redis) на диск** — в `/data_for_agent` по умолчанию, каталоги `{agent_id}__{chat_id}/` (`meta.json`, `history.json`). Из корня репозитория:

```bash
python3 scripts/export_memory_chats_to_data_for_agent.py
```

или `./scripts/export_chats_for_agent.sh` (тот же скрипт). Подхватывается `.env.{ENV}` или `.env` из корня репозитория; Redis задаётся `REDIS_URL` или `REDIS_*` (без полного `Settings` — не нужны секреты веба/Postgres). При необходимости `--redis-url`.

### Qdrant

```python
# Optimize index (через Python script)
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
client.update_collection(
    collection_name="agent_memory",
    optimizer_config={
        "indexing_threshold": 10000
    }
)
```

---

## Disaster Recovery

### Полная потеря данных

**Восстановление**:
1. Поднять чистую инфраструктуру
2. Restore PostgreSQL из backup
3. Restore Qdrant из backup
4. Redis можно не восстанавливать (fast memory - не критично)
5. Запустить агенты
6. Проверить что все работает

```bash
# Assuming fresh VPS
docker compose -f docker-compose.prod.yml up -d postgres redis rabbitmq qdrant
sleep 10
./scripts/restore_backup.sh backups/postgres_20260326_030000.sql backups/qdrant_20260326_030000.tar.gz
docker compose -f docker-compose.prod.yml up -d
```

### Потеря одного сервиса

Docker restart policy `unless-stopped` автоматически перезапустит упавший контейнер.

Если контейнер постоянно падает:
```bash
# 1. Проверить логи
docker compose logs <service>

# 2. Попробовать rebuild
docker compose build <service>
docker compose up -d <service>

# 3. Если не помогает - откатиться на предыдущую версию кода
git log  # Найти предыдущий working commit
git checkout <commit-hash>
docker compose build <service>
docker compose up -d <service>
```

---

## Security Checklist (Production)

- [ ] Использовать сильные пароли для всех БД
- [ ] WEB_AUTH_TOKEN минимум 32 символа, случайный
- [ ] JWT_SECRET минимум 32 символа, случайный
- [ ] .env файл с permissions 600 (только владелец может читать)
- [ ] Firewall настроен (только 22, 80, 443 открыты)
- [ ] SSH ключи используются (не пароли)
- [ ] Root login disabled для SSH
- [ ] Регулярные обновления системы (apt update && apt upgrade)
- [ ] Backups настроены и протестированы
- [ ] Monitoring alerts настроены
- [ ] Логи не содержат sensitive data (API keys, passwords)

```bash
# Проверка permissions
ls -la .env  # Должно быть -rw------- (600)
chmod 600 .env  # Если нет

# Проверка firewall
sudo ufw status

# Проверка SSH config
cat /etc/ssh/sshd_config | grep PermitRootLogin  # Должно быть "no"
```

---

## Scaling Considerations (для будущего)

Когда система вырастет:

### Horizontal Scaling
- Запускать multiple instances агентов (coder_01, coder_02)
- Load balancing через RabbitMQ (multiple consumers одной очереди)
- Distributed Qdrant (sharding)

### Vertical Scaling
- Увеличить ресурсы VPS
- Настроить connection pools
- Оптимизировать БД (partitioning для больших таблиц)

### Caching
- Redis для кэширования частых API запросов
- CDN для frontend статики
- Кэширование embeddings (уже есть в плане)

**Пока для MVP**: Single VPS достаточно для 10 агентов.

---

## Rollback Strategy

Если что-то пошло не так после обновления:

```bash
# Quick rollback
git log --oneline -10  # Найти предыдущий working commit
git checkout <previous-commit>
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# Если и это не помогло - restore из backup
./scripts/restore_backup.sh <backup-files>
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Все тесты проходят локально
- [ ] Ruff проверка проходит
- [ ] Документация обновлена
- [ ] CHANGELOG.md updated
- [ ] Создан git tag для версии
- [ ] Backup текущей production БД

### Deployment
- [ ] Pull latest code на VPS
- [ ] Build Docker images
- [ ] Run `docker compose up -d`
- [ ] Проверить health checks
- [ ] Функциональный тест (создать задачу)
- [ ] Проверить Web UI
- [ ] Проверить Telegram bot

### Post-Deployment
- [ ] Мониторить логи первые 30 минут
- [ ] Проверить что backups работают
- [ ] Уведомить команду/себя об успешном деплое
- [ ] Записать в CHANGELOG дату деплоя

### Rollback Plan (если что-то не так)
- [ ] Готов предыдущий git commit
- [ ] Готов backup БД
- [ ] Команда rollback протестирована

---

## Tips & Tricks

### Быстрый restart конкретного агента

```bash
docker compose restart coder
docker compose logs -f coder  # Следить за стартом
```

### Exec в контейнер для debugging

```bash
docker compose exec coder sh
# Внутри контейнера:
python
>>> from shared.llm_client import LLMClient
>>> # Debug code...
```

### Посмотреть environment переменные в контейнере

```bash
docker compose exec coder env
```

### Копирование файлов из/в контейнер

```bash
# Из контейнера на хост
docker cp balbes-coder:/data/coder_output/skills ./local_backup/

# С хоста в контейнер
docker cp ./new_config.yaml balbes-coder:/app/config/
```

### Очистка Docker (если заканчивается место)

```bash
# Удалить неиспользуемые images
docker image prune -a

# Удалить неиспользуемые volumes
docker volume prune

# Полная очистка (ОСТОРОЖНО)
docker system prune -a --volumes
```

---

## Monitoring Services (Optional, post-MVP)

### Simple Uptime Monitoring

Использовать бесплатные сервисы:
- **UptimeRobot** - проверка доступности каждые 5 минут
- **Healthchecks.io** - cron job monitoring

```bash
# Добавить в cron для healthchecks.io
*/5 * * * * curl -fsS --retry 3 https://hc-ping.com/your-uuid-here > /dev/null
```

### Logs Aggregation (Future)

Для продвинутого мониторинга (после MVP):
- **Grafana Loki** для логов
- **Prometheus** для метрик
- **Grafana** для визуализации

---

## Support & Maintenance Contact

**Deployment issues**: Проверить логи, DEPLOYMENT.md, GitHub Issues
**Configuration issues**: См. CONFIGURATION.md
**Development issues**: См. DEVELOPMENT_PLAN.md
