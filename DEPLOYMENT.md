# Balbes Multi-Agent System - Deployment Guide

## Overview

This guide covers deploying Balbes on a production VPS server with Docker and systemd.

> Note: The authoritative and actively maintained flow is:
> 1) environment-specific `.env.*` files, 2) `scripts/start_*.sh`/`stop_*.sh`,
> 3) ports `18100-18200` for production services with isolated infra ports.
> If older examples below conflict with that flow, prefer the script-based flow.

## Prerequisites

- Linux VPS (Ubuntu 22.04+ recommended)
- Docker with Compose v2 plugin (`docker compose`)
- 4GB+ RAM, 2+ CPU cores
- 20GB+ disk space
- Python 3.13 (default `python3`)
- Node.js 20+ (for frontend build)

---

## Pre-Deploy Validation Checklist (Living)

Run this checklist before every deploy. Keep it updated whenever API contracts,
ports, auth flows, or test suites change.

### 0) Start dev environment

```bash
cd /home/balbes/projects/dev
ENV=dev ./scripts/start_dev.sh
```

### 1) Smoke health checks

```bash
curl -sf http://localhost:8100/health   # Memory
curl -sf http://localhost:8101/health   # Skills
curl -sf http://localhost:8102/health   # Orchestrator
curl -sf http://localhost:8103/health   # Coder
curl -sf http://localhost:8200/health   # Web Backend
```

### 2) Full automated test gate

```bash
ENV=dev python -m pytest tests/ -q
```

Expected: all tests pass with zero failures.

### 3) Critical manual API checks

```bash
# Login
curl -s -X POST http://localhost:8200/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# Dashboard (requires user_id query parameter)
curl -s "http://localhost:8200/api/v1/dashboard/status?user_id=admin" \
  -H "Authorization: Bearer <TOKEN>"

# Create task (requires user_id query parameter)
curl -s -X POST "http://localhost:8200/api/v1/tasks?user_id=admin" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"orchestrator","description":"pre-deploy check","payload":{}}'
```

### 4) Frontend sanity check

```bash
cd web-frontend
npm run dev
```

Verify login, dashboard, agents, skills, tasks, and task creation from UI.

### 5) Go/No-Go criteria

- [ ] All health endpoints return success
- [ ] `ENV=dev python -m pytest tests/ -q` passes
- [ ] Manual login + dashboard + create task succeed
- [ ] No recurring errors in `/tmp/balbes-dev-*.log`
- [ ] Secrets are not tracked in git (`.env.dev`, `.env.test`)

### Checklist maintenance rule

- Update this section immediately after any change to:
  - API endpoints or required query/body fields
  - auth credentials or token flow
  - service ports or startup scripts
  - test commands, expected totals, or pass criteria

---

## Quick Deployment (Development)

### 1. Install Dependencies

```bash
# Python dependencies
cd /home/balbes/projects/dev
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

# Frontend dependencies
cd web-frontend
npm install
```

### 2. Start Infrastructure

```bash
# Start Redis, PostgreSQL, Qdrant
sg docker -c 'docker compose -f docker-compose.dev.yml up -d'

# Wait for services to be ready
sleep 10

# Initialize database
python scripts/init_db.py
```

### 3. Start All Services

```bash
# Memory Service (port 8100)
cd services/memory-service
uvicorn main:app --host 0.0.0.0 --port 8100 --reload &

# Skills Registry (port 8101)
cd services/skills-registry
uvicorn main:app --host 0.0.0.0 --port 8101 --reload &

# Orchestrator (port 8102)
cd services/orchestrator
uvicorn main:app --host 0.0.0.0 --port 8102 --reload &

# Coder Agent (port 8103)
cd services/coder
uvicorn main:app --host 0.0.0.0 --port 8103 --reload &

# Web Backend (port 8200)
cd services/web-backend
uvicorn main:app --host 0.0.0.0 --port 8200 --reload &

# Frontend (port 5173)
cd web-frontend
npm run dev &
```

### 4. Verify Services

```bash
# Check all services
curl http://localhost:8100/health  # Memory
curl http://localhost:8101/health  # Skills
curl http://localhost:8102/health  # Orchestrator
curl http://localhost:8103/health  # Coder
curl http://localhost:8200/health  # Web Backend
curl http://localhost:5173         # Frontend
```

---

## Production Deployment

### Architecture

```
Internet
    │
    └─> Nginx (Port 80/443)
         ├─> Frontend static build
         └─> API Gateway (Port 18200)
              ├─> Memory Service (18100)
              ├─> Skills Registry (18101)
              ├─> Orchestrator (18102)
              └─> Coder Agent (18103)
```

### Step 1: Prepare VPS

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install Python 3.13+
sudo apt install python3.13 python3.13-venv python3-pip -y

# Install Node.js 20+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs -y

# Install Nginx
sudo apt install nginx -y
```

### Step 2: Clone & Setup Project

```bash
# Clone repository
cd /opt
sudo git clone <your-repo-url> balbes
sudo chown -R $USER:$USER balbes
cd balbes

# Setup Python environment
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

# Setup frontend
cd web-frontend
npm install
npm run build
cd ..
```

### Step 3: Configure Environment

```bash
# Create production .env
cp .env.prod.example .env.prod

# Edit .env.prod with production values
nano .env.prod
```

For frontend build behind Nginx (same domain, API via `/api`), create production frontend env:

```bash
cd web-frontend
cp .env.production.example .env.production
cd ..
```

**Production `.env.prod` example**:

```env
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=15432
POSTGRES_USER=balbes
POSTGRES_PASSWORD=<strong-password>
POSTGRES_DB=balbes

# Redis
REDIS_HOST=localhost
REDIS_PORT=16379
REDIS_PASSWORD=<strong-password>

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=16333
QDRANT_API_KEY=<api-key>

# Services
MEMORY_SERVICE_URL=http://localhost:18100
SKILLS_REGISTRY_URL=http://localhost:18101
ORCHESTRATOR_URL=http://localhost:18102
CODER_URL=http://localhost:18103
WEB_BACKEND_PORT=18200

# OpenRouter
OPENROUTER_API_KEY=<your-key>

# Telegram (optional)
TELEGRAM_BOT_TOKEN=<your-token>

# JWT
WEB_AUTH_TOKEN=<random-token>
JWT_SECRET=<random-64-char-secret>
JWT_SECRET_KEY=<random-64-char-secret>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

### Step 4: Start Infrastructure

```bash
# Start Docker containers
sg docker -c 'docker compose --env-file .env.prod -f docker-compose.prod.yml up -d'

# Wait for services
sleep 15

# Initialize database
source .venv/bin/activate
ENV=prod \
python scripts/init_db.py
```

### Step 5: Start production services

Use the project scripts as the primary method:

```bash
ENV=prod ./scripts/start_prod.sh
./scripts/status_all_envs.sh
```

If frontend API routing or domain config changed, rebuild frontend before Nginx checks:

```bash
cd web-frontend
npm run build
cd ..
```

### Step 5.1: Script-only smoke check (required)

```bash
./scripts/healthcheck.sh prod
curl -fsS http://localhost:18100/health
curl -fsS http://localhost:18101/health
curl -fsS http://localhost:18102/health
curl -fsS http://localhost:18103/health
curl -fsS http://localhost:18200/health
rg -n "ERROR|CRITICAL|Traceback|Exception" logs/prod/*.log
```

Release gate and rollback rules are documented in `RELEASE_CHECKLIST.md`.

Manual mode in `start_prod.sh` writes logs to:

```bash
~/projects/balbes/logs/prod/*.log
```

and tracks PIDs in:

```bash
~/projects/balbes/.pids-prod.txt
```

### Optional: Setup Systemd Services

Create service files for each microservice:

**`/etc/systemd/system/balbes-memory.service`**:

```ini
[Unit]
Description=Balbes Memory Service
After=network.target docker.service postgresql.service redis.service

[Service]
Type=simple
User=balbes
WorkingDirectory=/opt/balbes
Environment="PATH=/opt/balbes/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/opt/balbes/.venv/bin/uvicorn services.memory-service.main:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create similar files for:
- `balbes-skills.service` (port 18101)
- `balbes-orchestrator.service` (port 18102)
- `balbes-coder.service` (port 18103)
- `balbes-web-backend.service` (port 18200)

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable balbes-memory balbes-skills balbes-orchestrator balbes-coder balbes-web-backend
sudo systemctl start balbes-memory balbes-skills balbes-orchestrator balbes-coder balbes-web-backend

# Check status
sudo systemctl status balbes-*
```

### Step 6: Configure Nginx

**`/etc/nginx/sites-available/balbes`**:

```nginx
upstream backend {
    server localhost:8200;
}

server {
    listen 80;
    server_name your-domain.com;

    # Frontend
    location / {
        root /opt/balbes/web-frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # API
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/balbes /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Step 7: SSL with Let's Encrypt (Optional)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### Step 8: Setup Firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

---

## Monitoring & Maintenance

### Check Service Status

```bash
# Systemd services
sudo systemctl status balbes-*

# Docker containers
docker ps

# Logs
sudo journalctl -u balbes-memory -f
sudo journalctl -u balbes-skills -f
```

### Database Backup

```bash
# PostgreSQL backup
docker exec balbes-postgres pg_dump -U balbes balbes > backup_$(date +%Y%m%d).sql

# Automated daily backups
cat > /opt/balbes/scripts/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/opt/balbes/backups
mkdir -p $BACKUP_DIR
docker exec balbes-postgres pg_dump -U balbes balbes | gzip > $BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
EOF

chmod +x /opt/balbes/scripts/backup.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/balbes/scripts/backup.sh") | crontab -
```

### Update Deployment

```bash
cd /opt/balbes
git pull
source .venv/bin/activate
pip install -r requirements.txt

# Rebuild frontend
cd web-frontend
npm install
npm run build
cd ..

# Restart services
sudo systemctl restart balbes-*
```

---

## Docker Compose (Alternative)

### Dockerfiles

**`services/memory-service/Dockerfile`**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8100"]
```

Create similar Dockerfiles for other services.

### `docker-compose.prod.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_USER: balbes
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: balbes
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: always

  redis:
    image: redis:7-alpine
    command: redis-server --requirepass ${REDIS_PASSWORD}
    ports:
      - "6379:6379"
    restart: always

  qdrant:
    image: qdrant/qdrant:latest
    environment:
      QDRANT__SERVICE__API_KEY: ${QDRANT_API_KEY}
    volumes:
      - qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
    restart: always

  memory-service:
    build:
      context: ./services/memory-service
    depends_on:
      - postgres
      - redis
      - qdrant
    environment:
      - POSTGRES_HOST=postgres
      - REDIS_HOST=redis
      - QDRANT_HOST=qdrant
    ports:
      - "8100:8100"
    restart: always

  skills-registry:
    build:
      context: ./services/skills-registry
    depends_on:
      - postgres
      - qdrant
    environment:
      - POSTGRES_HOST=postgres
      - QDRANT_HOST=qdrant
    ports:
      - "8101:8101"
    restart: always

  orchestrator:
    build:
      context: ./services/orchestrator
    depends_on:
      - memory-service
      - skills-registry
    environment:
      - MEMORY_SERVICE_URL=http://memory-service:8100
      - SKILLS_REGISTRY_URL=http://skills-registry:8101
    ports:
      - "8102:8102"
    restart: always

  coder:
    build:
      context: ./services/coder
    depends_on:
      - skills-registry
    environment:
      - SKILLS_REGISTRY_URL=http://skills-registry:8101
    ports:
      - "8103:8103"
    restart: always

  web-backend:
    build:
      context: ./services/web-backend
    depends_on:
      - memory-service
      - skills-registry
      - orchestrator
      - coder
    environment:
      - MEMORY_SERVICE_URL=http://memory-service:8100
      - SKILLS_REGISTRY_URL=http://skills-registry:8101
      - ORCHESTRATOR_URL=http://orchestrator:8102
      - CODER_URL=http://coder:8103
    ports:
      - "8200:8200"
    restart: always

  nginx:
    image: nginx:alpine
    depends_on:
      - web-backend
    volumes:
      - ./web-frontend/dist:/usr/share/nginx/html
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "80:80"
      - "443:443"
    restart: always

volumes:
  postgres_data:
  qdrant_data:
```

### Deploy with Docker Compose

```bash
# Build and start all services
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

---

## Security Checklist

- [ ] Change all default passwords
- [ ] Use strong JWT secret key (64+ chars)
- [ ] Enable Redis password
- [ ] Enable Qdrant API key
- [ ] Configure firewall (ufw)
- [ ] Setup SSL/TLS certificates
- [ ] Disable debug mode
- [ ] Setup log rotation
- [ ] Configure backup automation
- [ ] Enable rate limiting
- [ ] Setup monitoring (Prometheus/Grafana)

---

## Monitoring Setup

### Prometheus + Grafana

```bash
# Add to docker-compose.prod.yml
prometheus:
  image: prom/prometheus
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  ports:
    - "9090:9090"

grafana:
  image: grafana/grafana
  depends_on:
    - prometheus
  ports:
    - "3000:3000"
  volumes:
    - grafana_data:/var/lib/grafana
```

### Health Check Script

```bash
#!/bin/bash
# /opt/balbes/scripts/healthcheck.sh

SERVICES=(
  "http://localhost:8100/health"
  "http://localhost:8101/health"
  "http://localhost:8102/health"
  "http://localhost:8103/health"
  "http://localhost:8200/health"
)

for url in "${SERVICES[@]}"; do
  if curl -sf "$url" > /dev/null; then
    echo "✅ $url"
  else
    echo "❌ $url FAILED"
    # Send alert (email, Slack, etc.)
  fi
done
```

Run every 5 minutes:

```bash
*/5 * * * * /opt/balbes/scripts/healthcheck.sh
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u balbes-memory -n 50
docker logs balbes-memory-service

# Check port conflicts
sudo lsof -i :18100

# Check dependencies
docker ps
psql -h localhost -U balbes -d balbes -c "SELECT 1;"
redis-cli -h localhost ping
curl http://localhost:16333/health

# If Qdrant shows SSL wrong version errors:
# ensure clients use HTTP mode (https=False) and restart services
```

### High Memory Usage

```bash
# Check container stats
docker stats

# Restart services
sudo systemctl restart balbes-*

# Clear Redis cache
redis-cli FLUSHDB
```

### Database Issues

```bash
# Check connections
psql -h localhost -U balbes -d balbes -c "SELECT count(*) FROM pg_stat_activity;"

# Vacuum database
psql -h localhost -U balbes -d balbes -c "VACUUM ANALYZE;"

# Backup and restore
pg_dump -h localhost -U balbes balbes > backup.sql
psql -h localhost -U balbes balbes < backup.sql
```

---

## Performance Tuning

### PostgreSQL

```sql
-- Increase connection pool
ALTER SYSTEM SET max_connections = 200;

-- Tune memory
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- Restart
SELECT pg_reload_conf();
```

### Redis

```bash
# Edit redis.conf
maxmemory 512mb
maxmemory-policy allkeys-lru
```

### Nginx

```nginx
# Enable gzip
gzip on;
gzip_types text/plain text/css application/json application/javascript;

# Caching
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m;
proxy_cache api_cache;
proxy_cache_valid 200 5m;
```

---

## Scaling

### Horizontal Scaling

Run multiple instances behind load balancer:

```yaml
# docker-compose.scale.yml
services:
  orchestrator:
    deploy:
      replicas: 3

  coder:
    deploy:
      replicas: 2
```

### Vertical Scaling

Increase resources per service:

```yaml
services:
  memory-service:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
```

---

## Maintenance

### Log Rotation

```bash
# /etc/logrotate.d/balbes
/opt/balbes/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 balbes balbes
    sharedscripts
    postrotate
        systemctl reload balbes-*
    endscript
}
```

### Database Maintenance

```bash
# Weekly vacuum (Sunday 3 AM)
0 3 * * 0 psql -h localhost -U balbes -d balbes -c "VACUUM ANALYZE;"
```

### Update Checklist

- [ ] Backup database
- [ ] Test in staging
- [ ] Pull latest code
- [ ] Update dependencies
- [ ] Run migrations
- [ ] Rebuild services
- [ ] Run tests
- [ ] Restart services
- [ ] Verify health
- [ ] Monitor for errors

---

## Cost Estimation

### VPS Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4GB | 8GB |
| Disk | 20GB SSD | 50GB SSD |
| Network | 1TB/mo | Unlimited |

### Monthly Costs

- VPS (DigitalOcean, Linode): $20-40/mo
- Domain + SSL: $10-20/year
- OpenRouter API: Pay-as-you-go
- Backups: $5-10/mo

**Total**: ~$25-50/month

---

## Support & Resources

- Documentation: `/opt/balbes/docs/`
- Logs: `/opt/balbes/logs/`
- Backups: `/opt/balbes/backups/`
- Config: `/opt/balbes/.env`

### Useful Commands

```bash
# Restart all
sudo systemctl restart balbes-*

# View logs
sudo journalctl -u balbes-* -f

# Database shell
psql -h localhost -U balbes -d balbes

# Redis shell
redis-cli

# Docker logs
docker logs -f <container-name>
```

---

## Production Checklist

- [ ] All services deployed
- [ ] Infrastructure healthy
- [ ] Database initialized
- [ ] SSL configured
- [ ] Firewall enabled
- [ ] Backups automated
- [ ] Monitoring setup
- [ ] Logs rotating
- [ ] Health checks running
- [ ] Documentation updated
- [ ] Admin user created
- [ ] Test deployment works

---

## Next Steps After Deployment

1. **Create admin user** via Web Backend API
2. **Test full workflow** from frontend
3. **Setup monitoring alerts**
4. **Configure auto-scaling** (if needed)
5. **Document runbooks** for common issues
6. **Train team** on system operations

---

Deployment complete! System should be accessible at `http://your-domain.com` 🚀
