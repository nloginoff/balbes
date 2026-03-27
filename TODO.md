# TODO: MVP Development Tracking

Этот файл отражает текущее состояние проекта и ближайшие шаги.

**Started**: 2026-03-26
**Current phase**: Stage 9 (Production Deployment & hardening)
**Overall MVP progress**: ~90%
**Source of truth for run scripts/docs**: this file + `DEPLOYMENT.md` + `ENVIRONMENTS.md`

---

## ✅ Done

- [x] Этап 0: Planning & Documentation (базовая архитектура и документы)
- [x] Этап 1: Core infrastructure (shared config/models/base setup)
- [x] Этап 2: Memory Service
- [x] Этап 3: Skills Registry
- [x] Этап 4: Orchestrator Agent
- [x] Этап 5: Coder Agent
- [x] Этап 6: Web Backend
- [x] Этап 7: Web Frontend
- [x] Этап 8: Integration & Testing (dev suite стабилизирован)

### Recent completed work (последние итерации)

- [x] Multi-environment isolation (dev/test/prod) с разными портами и БД
- [x] Исправлен запуск prod на одном сервере параллельно с dev
- [x] Исправлены Python compatibility issues (`datetime.UTC` -> `timezone.utc` где нужно)
- [x] Исправлены клиенты Qdrant для локального prod (`https=False` для local HTTP mode)
- [x] Исправлены prod run scripts:
  - [x] `scripts/start_prod.sh` пишет логи в `logs/prod/*.log`
  - [x] `scripts/stop_prod.sh` использует `.pids-prod.txt`
  - [x] `scripts/status_all_envs.sh` показывает корректные prod порты `18100..18200`
- [x] Обновлена ключевая документация (`README.md`, `DEPLOYMENT.md`, `ENVIRONMENTS.md`, `PROJECT_GUIDE.md`)

---

## 🔄 In Progress (Stage 9)

- [x] Prod services поднимаются на Python 3.13
- [x] Frontend build в prod проходит
- [x] Infrastructure контейнеры prod поднимаются стабильно
- [ ] Финализировать единый runbook для штатного ежедневного запуска/остановки prod
- [ ] Проверить и зафиксировать policy по Qdrant API key (local prod vs external prod)
- [ ] Сделать финальный smoke-pass через скрипты без ручных команд

---

## 📌 Next (после стабилизации Stage 9)

### Stage 10: Final Testing & Release Readiness

- [ ] Финальный e2e прогон на актуальном dev
- [ ] Финальный smoke на prod (через script-only flow)
- [ ] Сверка документации с фактическими командами (последний проход)
- [ ] Релизная фиксация: checklist “go/no-go”
- [ ] Зафиксировать post-MVP backlog (что переносим в следующий этап)

---

## ✅ Operational Commands (коротко)

### Development

```bash
./scripts/start_dev.sh
./scripts/stop_dev.sh
```

### Testing

```bash
./scripts/start_test.sh
ENV=test python -m pytest tests/ -q
./scripts/stop_test.sh
```

### Production

```bash
ENV=prod ./scripts/start_prod.sh
./scripts/stop_prod.sh
./scripts/status_all_envs.sh
```

---

## 🧾 Notes

- Продолжаем правило: **все изменения делаем в `~/projects/dev`**, в `~/projects/balbes` только `git pull` и запуск.
- Если что-то “работает только руками”, задача не считается закрытой, пока не работает через скрипты.
- Для локального прода проверяем совместимость Qdrant-конфига и клиентского режима (HTTP/TLS).

---

**Last updated**: 2026-03-27
