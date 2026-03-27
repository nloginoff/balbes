# Release Checklist (Go/No-Go)

Использовать перед каждым релизом на `prod`. Цель: единый минимальный набор проверок без ручных отклонений.

## 1) Preconditions

- [x] Все изменения закоммичены и запушены из `~/projects/dev`
- [x] В `~/projects/balbes` выполнен `git pull`
- [x] `.env.prod` заполнен актуальными секретами (без `CHANGE_ME`)

## 2) Script-only restart

- [x] `./scripts/stop_prod.sh`
- [x] `./scripts/start_prod.sh`

## 3) Health checks

- [x] `./scripts/healthcheck.sh prod` -> все проверки `✅`
- [x] `./scripts/status_all_envs.sh` -> prod сервисы `✅`

## 4) Endpoint smoke

- [x] `curl -fsS http://localhost:18100/health`
- [x] `curl -fsS http://localhost:18101/health`
- [x] `curl -fsS http://localhost:18102/health`
- [x] `curl -fsS http://localhost:18103/health`
- [x] `curl -fsS http://localhost:18200/health`

## 5) Infrastructure

- [x] `docker ps --format '{{.Names}}\t{{.Status}}' | rg 'balbes-prod-'`
- [x] Контейнеры `balbes-prod-postgres|redis|qdrant|rabbitmq` в статусе Up/healthy

## 6) Logs sanity

- [x] `rg -n "ERROR|CRITICAL|Traceback|Exception" logs/prod/*.log`
- [x] Нет повторяющихся фатальных ошибок после рестарта

## 7) Go/No-Go

- [x] **GO**: все пункты выше пройдены
- [ ] **NO-GO**: есть красные health checks, падения сервисов или фатальные ошибки в логах

## 8) Rollback (if NO-GO)

1. Остановить prod:
   - `./scripts/stop_prod.sh`
2. Вернуть предыдущий стабильный commit/tag в `~/projects/balbes`
3. Повторить старт:
   - `./scripts/start_prod.sh`
4. Повторить health:
   - `./scripts/healthcheck.sh prod`
