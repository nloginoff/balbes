# Balbes Multi-Agent System - Overview

```
██████╗  █████╗ ██╗     ██████╗ ███████╗███████╗
██╔══██╗██╔══██╗██║     ██╔══██╗██╔════╝██╔════╝
██████╔╝███████║██║     ██████╔╝█████╗  ███████╗
██╔══██╗██╔══██║██║     ██╔══██╗██╔══╝  ╚════██║
██████╔╝██║  ██║███████╗██████╔╝███████╗███████║
╚═════╝ ╚═╝  ╚═╝╚══════╝╚═════╝ ╚══════╝╚══════╝

Multi-Agent AI System | v0.1.0-dev
```

---

## 🎯 Что это?

**Balbes** - это модульная система независимых AI-агентов для автоматизации задач:
- 🤖 **Coder** - пишет код, создает новые скиллы
- 🎭 **Orchestrator** - управляет всем через Telegram
- 📝 **Blogger** - контент для каналов (будущее)

### Ключевая идея
Вместо одного "всемогущего" агента - команда специализированных агентов,
каждый со своими навыками, памятью и инструкциями.

---

## 📊 Project Stats

```
📁 Project Files
├── 24 Markdown files       (documentation)
├── 14 Python files         (core code + scripts)
├── 5 YAML configs          (providers, agents, skills)
├── 4 Docker files          (compose, Dockerfiles)
├── 5 Shell scripts         (utilities)
└── 13,586 lines            (documentation)

🏗️ Architecture
├── 2 Agents (MVP)          → Orchestrator, Coder
├── 4 Databases             → PostgreSQL, Redis, Qdrant, RabbitMQ
├── 3 HTTP Services         → Memory, Skills, Web Backend
├── 1 Frontend              → React + shadcn/ui
└── 10+ Skills (planned)    → web_search, file_ops, etc

📚 Documentation
├── 17 docs in docs/        → comprehensive guides
├── 18 practical examples   → real-world usage
├── 10-stage dev plan       → from setup to deploy
└── 100% coverage           → every aspect documented

🔧 Tech Stack
├── Python 3.13+            → FastAPI, asyncio
├── TypeScript/React        → Modern UI
├── Docker + Make           → Easy development
├── OpenRouter              → LLM gateway
└── 15+ dependencies        → production-ready
```

---

## 🚀 Quick Navigation

### 🆕 First Time?
**Start here**: [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md)

### 💨 Want to Run It?
**5-min setup**: [`docs/QUICKSTART.md`](docs/QUICKSTART.md)

### 🧠 Understand Architecture?
**Technical spec**: [`docs/TECHNICAL_SPEC.md`](docs/TECHNICAL_SPEC.md)

### 💻 Ready to Code?
**Dev plan**: [`docs/DEVELOPMENT_PLAN.md`](docs/DEVELOPMENT_PLAN.md)

### 🎨 See Examples?
**Use cases**: [`docs/EXAMPLES.md`](docs/EXAMPLES.md)

### 🔍 Need Something?
**Full index**: [`docs/INDEX.md`](docs/INDEX.md)

---

## 🏁 Current Status

```
Phase:     ✅ PLANNING COMPLETE
Progress:  ██░░░░░░░░░░░░░░░░░░ 10%
Next:      💻 Development - Этап 1 (Core Infrastructure)
Timeline:  ~15-20 days to MVP
```

### What's Ready?
- ✅ Technical design complete
- ✅ MVP scope defined
- ✅ Development plan created
- ✅ Infrastructure configured
- ✅ Documentation written
- ✅ Project structure defined

### What's Next?
- ⏳ Implement Core Infrastructure
- ⏳ Build Memory Service
- ⏳ Create Skills Registry
- ⏳ Develop Orchestrator Agent
- ⏳ Develop Coder Agent
- ⏳ Build Web Interface

---

## 🎨 System Architecture (High-Level)

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACES                         │
├─────────────────────────┬───────────────────────────────────────┤
│   Telegram Bot          │     Web UI (React)                    │
│   ├─ Commands           │     ├─ Dashboard                      │
│   ├─ Status             │     ├─ Chat Interface                 │
│   └─ Logs               │     └─ Monitoring                     │
└──────────┬──────────────┴──────────────┬────────────────────────┘
           │                              │
           └──────────────┬───────────────┘
                          │
           ┌──────────────▼──────────────┐
           │   ORCHESTRATOR AGENT        │
           │   - Task Management         │
           │   - Agent Coordination      │
           │   - User Communication      │
           └──────────────┬──────────────┘
                          │
           ┌──────────────▼──────────────────────────┐
           │         MESSAGE BUS (RabbitMQ)          │
           │    - Direct messages                    │
           │    - Broadcast messages                 │
           │    - Task queue                         │
           └──┬───────────────────────────┬──────────┘
              │                           │
    ┌─────────▼─────────┐       ┌────────▼──────────┐
    │  CODER AGENT      │       │  BLOGGER AGENT    │
    │  - Create Skills  │       │  (Future)         │
    │  - Write Code     │       │  - Content Gen    │
    │  - Run Tests      │       │  - Publishing     │
    └─────────┬─────────┘       └───────────────────┘
              │
    ┌─────────▼──────────────────────────────────────┐
    │              SHARED SERVICES                    │
    ├─────────────────┬──────────────────┬───────────┤
    │ Memory Service  │ Skills Registry  │ Web API   │
    │ - Redis         │ - Load/Execute   │ - HTTP    │
    │ - Qdrant        │ - Manage Skills  │ - WS      │
    │ - PostgreSQL    │ - Validation     │ - Auth    │
    └─────────────────┴──────────────────┴───────────┘
              │                 │              │
    ┌─────────▼─────────────────▼──────────────▼─────┐
    │              INFRASTRUCTURE                     │
    │  PostgreSQL | Redis | Qdrant | RabbitMQ        │
    └─────────────────────────────────────────────────┘
```

---

## 💡 Key Features

### 🧠 Smart Agents
- Independent AI agents with specialized roles
- Personal skills, instructions, and memory for each agent
- Automatic fallback to cheaper models when token limits hit

### 💾 Hybrid Memory
- **Fast (Redis)**: Context, recent conversations
- **Long-term (Qdrant)**: Semantic search, historical data
- **Structured (PostgreSQL)**: Tasks, logs, agent state

### 🎛️ Full Control
- **Telegram**: Command agents anywhere
- **Web UI**: Monitor, chat, view logs in real-time
- **Token Tracking**: See where tokens are spent

### 🔄 Reliable Execution
- 3 automatic retries on failures
- 10-minute task timeouts
- Detailed logging of every action

### 🛡️ Secure & Scalable
- Token-based auth
- Modular architecture (easy to scale)
- Docker deployment

---

## 🛠️ Tech Highlights

**Backend**: Python 3.13 + FastAPI + asyncio
**Frontend**: React 18 + TypeScript + shadcn/ui
**Databases**: PostgreSQL + Redis + Qdrant
**Message Bus**: RabbitMQ
**LLM**: OpenRouter (multi-provider)
**Deploy**: Docker Compose + Nginx
**Quality**: pytest + ruff + mypy + pre-commit

---

## 📈 Development Roadmap

### MVP (v0.1.0) - Current
- [x] Planning and documentation
- [ ] Core infrastructure
- [ ] Memory Service
- [ ] Skills Registry
- [ ] Orchestrator Agent
- [ ] Coder Agent
- [ ] Web UI
- [ ] Integration testing
- [ ] Production deployment

### Post-MVP (v0.2.0+)
- Blogger Agent
- Advanced content skills
- Multi-channel publishing
- Enhanced monitoring
- Additional agents

---

## 🎓 Learn More

| Topic | Document | Time |
|-------|----------|------|
| **Quick Overview** | [SUMMARY.md](docs/SUMMARY.md) | 5 min |
| **Getting Started** | [GETTING_STARTED.md](docs/GETTING_STARTED.md) | 15 min |
| **Full Tech Spec** | [TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md) | 30 min |
| **Development** | [DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) | 30 min |
| **Examples** | [EXAMPLES.md](docs/EXAMPLES.md) | 20 min |
| **All Docs** | [INDEX.md](docs/INDEX.md) | - |

---

## 🏃 Quick Start

```bash
# Setup
make setup

# Run infrastructure
make infra-up

# Initialize database
make db-init

# Run services (after implementation)
make dev-memory
make dev-skills
make dev-orchestrator
make dev-coder

# Develop!
```

Full guide: [`docs/QUICKSTART.md`](docs/QUICKSTART.md)

---

## 🤝 Contributing

Interested in contributing? See [`CONTRIBUTING.md`](CONTRIBUTING.md)

---

## 📞 Support

- **Docs**: [`docs/`](docs/) folder
- **FAQ**: [`docs/FAQ.md`](docs/FAQ.md)
- **Issues**: GitHub Issues (when available)

---

**Built with** ❤️ **by balbes**
**License**: TBD
**Version**: 0.1.0-dev

---

*Last updated: 2026-03-26*
