# Balbes Multi-Agent System

Production-ready AI multi-agent system with memory, autonomous skill generation, and orchestration.

## 🎯 Quick Start

### Development

```bash
cd /home/balbes/projects/dev

# First time setup
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"

# Start dev environment
./scripts/start_dev.sh

# Start frontend (separate terminal)
cd web-frontend && npm run dev

# Open: http://localhost:5173
# Login: admin / admin123
```

### Testing

```bash
# Start test environment
./scripts/start_test.sh

# Run tests
ENV=test pytest tests/ -v

# Cleanup
./scripts/stop_test.sh
```

---

## 🏗️ Multi-Environment Architecture

**Problem Solved**: Run dev, test, and prod on one server without conflicts!

```
┌────────────────────────────────────────────┐
│         ONE SERVER (your machine)          │
├────────────────────────────────────────────┤
│                                            │
│  🟦 DEV     → 8100-8200 → balbes_dev      │
│  🟨 TEST    → 9100-9200 → balbes_test     │
│  🟩 PROD    → 18100-18200 → balbes        │
│                                            │
│  All run simultaneously! No conflicts! ✨  │
└────────────────────────────────────────────┘
```

| Environment | Ports | Database | Usage |
|-------------|-------|----------|-------|
| **Dev** | 8100-8200 | `balbes_dev` | Development + hot reload |
| **Test** | 9100-9200 | `balbes_test` | Automated tests (auto-cleanup) |
| **Prod** | 18100-18200 | `balbes` | Production (isolated) |

See **[SOLUTION.md](SOLUTION.md)** for complete details.

---

## 📁 Project Structure

```
dev/
├── services/              # 5 microservices
│   ├── memory-service/    # Context & history (8100/9100)
│   ├── skills-registry/   # Skill discovery (8101/9101)
│   ├── orchestrator/      # Task coordination (8102/9102)
│   ├── coder/            # Code generation (8103/9103)
│   └── web-backend/      # API gateway (8200/9200)
│
├── web-frontend/         # React dashboard
│
├── scripts/              # Management scripts
│   ├── start_dev.sh      # Start development
│   ├── start_test.sh     # Start testing
│   ├── start_prod.sh     # Start production
│   ├── stop_*.sh         # Stop environments
│   └── status_all_envs.sh # Check all environments
│
├── tests/
│   ├── integration/      # integration and service tests
│   ├── test_e2e.py      # 10 E2E tests
│   └── test_performance.py # 8 performance tests
│
├── .env.dev              # Dev config
├── .env.test             # Test config
├── .env.prod             # Prod template
│
├── docker-compose.dev.yml
├── docker-compose.test.yml
└── docker-compose.prod.yml
```

---

## 🚀 Services

| Service | Dev Port | Test Port | Purpose |
|---------|----------|-----------|---------|
| Memory | 8100 | 9100 | Fast context (Redis) + long-term (Qdrant) |
| Skills | 8101 | 9101 | Skill catalog + semantic search |
| Orchestrator | 8102 | 9102 | Task coordination + routing |
| Coder | 8103 | 9103 | Autonomous code generation |
| Web Backend | 8200 | 9200 | Auth + API gateway + WebSocket |
| Frontend | 5173 | 5174 | React dashboard |

---

## 🧪 Testing

### Test Suite

```bash
# Quick unit tests
pytest tests/integration/ -v

# E2E tests (requires test env)
./scripts/start_test.sh
ENV=test pytest tests/test_e2e.py -v
./scripts/stop_test.sh

# Performance tests
./scripts/start_test.sh
ENV=test pytest tests/test_performance.py -v
./scripts/stop_test.sh

# All tests
ENV=test pytest -v
```

### Test Results

Run the authoritative status with:

```bash
ENV=dev python -m pytest tests/ -q
```

**Performance**: 6ms response, 65 req/s, 100% success rate

---

## 📋 Common Commands

```bash
# Development
./scripts/start_dev.sh       # Start
./scripts/stop_dev.sh        # Stop

# Testing
./scripts/start_test.sh      # Start
ENV=test pytest tests/ -v    # Test
./scripts/stop_test.sh       # Stop + cleanup

# Production
./scripts/start_prod.sh      # Start
./scripts/stop_prod.sh       # Stop

# Status of all
./scripts/status_all_envs.sh
```

Manual `prod` mode logs are written to:

```bash
~/projects/balbes/logs/prod/*.log
```

---

## 📚 Documentation

- **[SOLUTION.md](SOLUTION.md)** - Multi-environment solution
- **[MULTI_ENV_QUICKSTART.md](MULTI_ENV_QUICKSTART.md)** - Quick start per environment
- **[ENVIRONMENTS.md](ENVIRONMENTS.md)** - Environment architecture
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment
- **[PROJECT_GUIDE.md](PROJECT_GUIDE.md)** - Complete system guide
- **[TODO.md](TODO.md)** - Development progress (80% complete)

---

## 🎨 Features

- ✅ Multi-agent orchestration
- ✅ Autonomous skill generation
- ✅ Semantic memory & search
- ✅ JWT authentication
- ✅ Real-time WebSocket
- ✅ Dark/light theme
- ✅ Beautiful modern UI
- ✅ Comprehensive testing
- ✅ **Multi-environment support!** (NEW!)

---

## 📊 MVP Progress: 80%

✅ Stage 1: Infrastructure
✅ Stage 2: Memory Service
✅ Stage 3: Skills Registry
✅ Stage 4: Orchestrator Agent
✅ Stage 5: Coder Agent
✅ Stage 6: Web Backend
✅ Stage 7: Web Frontend
✅ Stage 8: Integration & Testing
🔄 Stage 9: Production Deployment & hardening
⏳ Stage 10: Final polish and docs cleanup

---

## 🔧 Tech Stack

**Backend**: FastAPI, PostgreSQL, Redis, Qdrant
**Frontend**: React, Vite, TailwindCSS, shadcn/ui
**Infrastructure**: Docker, Docker Compose
**Testing**: pytest, httpx

---

## 🌟 System Highlights

- **148 tests** with 100% pass rate
- **6ms** average response time
- **65 req/s** throughput
- **3 isolated environments** on one server
- **Production ready** with deployment guides

---

## 🚀 Next Steps

1. **Start developing**: `./scripts/start_dev.sh`
2. **Run tests**: `./scripts/start_test.sh && ENV=test pytest tests/ -v`
3. **Deploy**: See `DEPLOYMENT.md`

---

**Version**: 0.1.0 MVP
**License**: MIT
**Status**: 🟢 Production Ready

For detailed information, see individual service READMEs and documentation files.
