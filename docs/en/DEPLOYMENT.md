# Deployment Guide

---

## Architecture

Balbes runs as a set of Python services managed by bash scripts (no Kubernetes or heavy orchestration required):

```
┌─────────────────────────────────────────────────────┐
│  Linux Server                                       │
│                                                     │
│  ├── orchestrator (uvicorn, port 18102)             │
│  │     Telegram bot + main agent                   │
│  ├── coder (uvicorn, port 18103)                    │
│  │     Coding agent (receives delegated tasks)     │
│  ├── memory-service (uvicorn, port 18100)           │
│  │     Chat history + session state                │
│  └── skills-registry (uvicorn, port 18101)          │
│        Skill registry                              │
│                                                     │
│  Infrastructure (Docker Compose):                   │
│  ├── PostgreSQL  (port 5432)                        │
│  ├── Redis       (port 6379)                        │
│  ├── Qdrant      (port 6333)                        │
│  └── RabbitMQ    (port 5672)                        │
└─────────────────────────────────────────────────────┘
```

---

## Initial Server Setup

```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3.13 python3.13-venv ffmpeg git curl

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# Clone repo
git clone https://github.com/your-username/balbes.git ~/projects/balbes
cd ~/projects/balbes

# Configure
cp .env.example .env.prod
nano .env.prod   # fill in all required values

# Create Python venv
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r services/orchestrator/requirements.txt
```

---

## Starting Services

### Infrastructure first

```bash
cd ~/projects/balbes
docker compose -f docker-compose.prod.yml up -d
```

### Application services

```bash
bash scripts/start_prod.sh
```

This starts all services with `uvicorn --workers 1` (single worker — required for in-memory state).

### Verify everything is running

```bash
bash scripts/healthcheck.sh prod
```

Expected output:
```
✅ PostgreSQL
✅ Redis
✅ Qdrant
✅ RabbitMQ
✅ memory-service (18100)
✅ skills-registry (18101)
✅ orchestrator (18102)
✅ coder (18103)
```

---

## Logs

```bash
# Live logs
tail -f logs/prod/orchestrator.log
tail -f logs/prod/telegram_bot.log
tail -f logs/prod/coder.log

# Last 100 lines
tail -100 logs/prod/orchestrator.log
```

---

## Updating

```bash
cd ~/projects/balbes
git pull
bash scripts/restart_prod.sh
```

The restart script:
1. Stops all services gracefully
2. Starts infrastructure if not running
3. Starts application services
4. Runs a health check

---

## Dev → Prod Workflow

The repo uses a single `master` branch. Development happens in a separate `dev/` directory:

```bash
# On dev machine (~/projects/dev)
git add .
git commit -m "feat: ..."
git push

# On production server (~/projects/balbes)
git pull
bash scripts/restart_prod.sh
```

---

## Process Management

Services are managed with PID files in `.pids-prod.txt`. The scripts handle start/stop/restart automatically.

To manually stop all services:

```bash
bash scripts/stop_prod.sh
```

To check running processes:

```bash
cat .pids-prod.txt
ps aux | grep uvicorn
```

---

## Ports Reference

| Service | Port | Notes |
|---------|------|-------|
| Orchestrator + Telegram bot | 18102 | Main entry point |
| Coder agent | 18103 | Receives delegated tasks |
| Memory service | 18100 | Chat history + sessions |
| Skills registry | 18101 | Skill management |
| PostgreSQL | 5432 | Via Docker |
| Redis | 6379 | Via Docker |
| Qdrant | 6333 | Via Docker |
| RabbitMQ | 5672 | Via Docker |

---

## Security Checklist

Before opening the repo or exposing the server:

- [ ] `.env.prod` is in `.gitignore` ✅
- [ ] `.pids-prod.txt` is in `.gitignore` ✅
- [ ] `TELEGRAM_USER_ID` set to only your user IDs
- [ ] `WEB_AUTH_TOKEN` and `JWT_SECRET` are random strings (not defaults)
- [ ] `POSTGRES_PASSWORD` is a strong password
- [ ] Firewall: only ports 80/443 open externally (all service ports internal only)
- [ ] No API keys committed to git

---

*[Русская версия](../ru/DEPLOYMENT.md)*
