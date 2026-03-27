# Release Checklist (Go/No-Go)

Использовать перед каждым релизом на `prod`. Цель: единый минимальный набор проверок без ручных отклонений.

## 1) Preconditions

- [ ] Все изменения закоммичены и запушены из `~/projects/dev`
- [ ] В `~/projects/balbes` выполнен `git pull`
- [ ] `.env.prod` заполнен актуальными секретами (без `CHANGE_ME`)

## 2) Script-only restart

- [ ] `./scripts/stop_prod.sh`
- [ ] `./scripts/start_prod.sh`

## 3) Health checks

- [ ] `./scripts/healthcheck.sh prod` -> все проверки `✅`
- [ ] `./scripts/status_all_envs.sh` -> prod сервисы `✅`

## 4) Endpoint smoke

- [ ] `curl -fsS http://localhost:18100/health`
- [ ] `curl -fsS http://localhost:18101/health`
- [ ] `curl -fsS http://localhost:18102/health`
- [ ] `curl -fsS http://localhost:18103/health`
- [ ] `curl -fsS http://localhost:18200/health`

## 5) Infrastructure

- [ ] `docker ps --format '{{.Names}}\t{{.Status}}' | rg 'balbes-prod-'`
- [ ] Контейнеры `balbes-prod-postgres|redis|qdrant|rabbitmq` в статусе Up/healthy

## 6) Logs sanity

- [ ] `rg -n "ERROR|CRITICAL|Traceback|Exception" logs/prod/*.log`
- [ ] Нет повторяющихся фатальных ошибок после рестарта

## 7) Go/No-Go

- [ ] **GO**: все пункты выше пройдены
- [ ] **NO-GO**: есть красные health checks, падения сервисов или фатальные ошибки в логах

## 8) Rollback (if NO-GO)

1. Остановить prod:
   - `./scripts/stop_prod.sh`
2. Вернуть предыдущий стабильный commit/tag в `~/projects/balbes`
3. Повторить старт:
   - `./scripts/start_prod.sh`
4. Повторить health:
   - `./scripts/healthcheck.sh prod`
