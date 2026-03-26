#!/bin/bash
# Comprehensive system diagnostic

set -e

echo "============================================================"
echo "Balbes Multi-Agent System - Full Diagnostic"
echo "============================================================"
echo ""

# 1. Infrastructure
echo "1️⃣  Infrastructure Services"
echo ""
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "balbes|NAMES"
echo ""

# 2. Service Health
echo "2️⃣  Service Health Checks"
echo ""

echo -n "Memory Service:      "
curl -sf http://localhost:8100/health | jq -r '.status' 2>/dev/null || echo "not responding"

echo -n "Skills Registry:     "
curl -sf http://localhost:8101/health | jq -r '.status' 2>/dev/null || echo "not responding"

echo -n "Web Backend:         "
curl -sf http://localhost:8200/health | jq -r '.status' 2>/dev/null || echo "not responding"

echo ""

# 3. Agent Status
echo "3️⃣  Agent Status (PostgreSQL)"
echo ""

psql -h localhost -U balbes -d balbes_agents -c "
SELECT
    id,
    status,
    COALESCE(LEFT(current_task_id::text, 8), 'none') as task,
    tokens_used_today as tokens_today,
    tokens_used_hour as tokens_hour,
    to_char(last_activity, 'HH24:MI:SS') as last_active
FROM agents
ORDER BY id;
" 2>/dev/null || echo "PostgreSQL not available"

echo ""

# 4. Recent Tasks
echo "4️⃣  Recent Tasks (last 10)"
echo ""

psql -h localhost -U balbes -d balbes_agents -c "
SELECT
    LEFT(id::text, 8) as task_id,
    agent_id,
    status,
    LEFT(description, 50) as description,
    to_char(created_at, 'HH24:MI:SS') as created
FROM tasks
ORDER BY created_at DESC
LIMIT 10;
" 2>/dev/null || echo "PostgreSQL not available"

echo ""

# 5. Token Usage
echo "5️⃣  Token Usage Today"
echo ""

psql -h localhost -U balbes -d balbes_agents -c "
SELECT
    agent_id,
    total_tokens,
    total_cost,
    num_calls,
    to_char(last_call, 'HH24:MI:SS') as last_call
FROM v_tokens_today
ORDER BY total_tokens DESC;
" 2>/dev/null || echo "PostgreSQL not available"

echo ""

# 6. Disk Usage
echo "6️⃣  Disk Usage"
echo ""

if [ -d "data" ]; then
    echo "Data directories:"
    du -sh data/postgres 2>/dev/null || echo "  postgres: not found"
    du -sh data/redis 2>/dev/null || echo "  redis: not found"
    du -sh data/qdrant 2>/dev/null || echo "  qdrant: not found"
    du -sh data/logs 2>/dev/null || echo "  logs: not found"
    du -sh data/coder_output 2>/dev/null || echo "  coder_output: not found"
    echo ""
    echo "Total data size:"
    du -sh data/
else
    echo "data/ directory not found"
fi

echo ""

# 7. Recent Errors
echo "7️⃣  Recent Errors (last 5)"
echo ""

psql -h localhost -U balbes -d balbes_agents -c "
SELECT
    to_char(timestamp, 'YYYY-MM-DD HH24:MI:SS') as time,
    agent_id,
    action,
    LEFT(error_message, 60) as error
FROM action_logs
WHERE status = 'error'
ORDER BY timestamp DESC
LIMIT 5;
" 2>/dev/null || echo "PostgreSQL not available"

# Check if no errors
ERROR_COUNT=$(psql -h localhost -U balbes -d balbes_agents -t -c "
SELECT COUNT(*) FROM action_logs
WHERE status = 'error' AND timestamp >= NOW() - INTERVAL '24 hours';
" 2>/dev/null | tr -d ' ') || ERROR_COUNT="unknown"

if [ "$ERROR_COUNT" = "0" ]; then
    echo ""
    echo "🎉 No errors in last 24 hours!"
fi

echo ""

# 8. System Resources
echo "8️⃣  System Resources"
echo ""

echo "Memory:"
free -h | grep -E "Mem:|Swap:"

echo ""
echo "Disk:"
df -h / | grep -E "Filesystem|/$"

echo ""
echo "CPU Load:"
uptime

echo ""

# 9. Network Connectivity
echo "9️⃣  Network Connectivity"
echo ""

echo -n "OpenRouter API:      "
curl -sf -o /dev/null -w "%{http_code}" https://openrouter.ai/api/v1/models > /dev/null 2>&1 && echo "reachable" || echo "unreachable"

echo -n "Telegram API:        "
curl -sf -o /dev/null -w "%{http_code}" https://api.telegram.org > /dev/null 2>&1 && echo "reachable" || echo "unreachable"

echo ""

# Summary
echo "============================================================"
echo "Diagnostic Complete"
echo ""
echo "For detailed logs run:"
echo "  make infra-logs    # Infrastructure logs"
echo "  make prod-logs     # Production logs (if running)"
echo "  tail -f data/logs/*.log  # Application logs"
echo "============================================================"
