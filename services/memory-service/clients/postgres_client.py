"""
PostgreSQL client for agent state, tasks, and logs.

Provides CRUD operations for:
- agents table
- tasks table
- action_logs table
- token_usage table
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import asyncpg

from shared.config import get_settings
from shared.exceptions import DatabaseConnectionError, DatabaseQueryError
from shared.models import AgentStatus, TaskStatus

settings = get_settings()
logger = logging.getLogger("memory-service.postgres")


class PostgresClient:
    """
    Async PostgreSQL client with connection pooling.
    """

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                min_size=2,
                max_size=settings.connection_pool_size,
                command_timeout=30,
            )

            # Test connection
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            logger.info("PostgreSQL connection pool established")

        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise DatabaseConnectionError(f"PostgreSQL connection failed: {e}")

    async def close(self) -> None:
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def health_check(self) -> bool:
        """Check PostgreSQL connection"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    # =========================================================================
    # Agents Table
    # =========================================================================

    async def get_all_agents(self) -> list[dict[str, Any]]:
        """Get all agents"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        agent_id,
                        name,
                        status,
                        current_task_id,
                        current_model,
                        config,
                        created_at,
                        last_activity,
                        tokens_used_today,
                        tokens_used_hour
                    FROM agents
                    ORDER BY last_activity DESC
                """)

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get agents: {e}")
            raise DatabaseQueryError(f"Failed to query agents: {e}")

    async def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent by ID"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        agent_id,
                        name,
                        status,
                        current_task_id,
                        current_model,
                        config,
                        created_at,
                        last_activity,
                        tokens_used_today,
                        tokens_used_hour
                    FROM agents
                    WHERE agent_id = $1
                """,
                    agent_id,
                )

                return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get agent: {e}")
            raise DatabaseQueryError(f"Failed to query agent: {e}")

    async def create_agent(
        self,
        agent_id: str,
        name: str,
        current_model: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create new agent"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO agents (agent_id, name, current_model, config)
                    VALUES ($1, $2, $3, $4::jsonb)
                    RETURNING
                        agent_id,
                        name,
                        status,
                        current_model,
                        created_at
                """,
                    agent_id,
                    name,
                    current_model,
                    json.dumps(config or {}),
                )

                logger.info(f"Created agent: {agent_id}")
                return dict(row)

        except asyncpg.UniqueViolationError:
            raise DatabaseQueryError(f"Agent '{agent_id}' already exists")
        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            raise DatabaseQueryError(f"Failed to create agent: {e}")

    async def update_agent_status(
        self,
        agent_id: str,
        status: AgentStatus,
        current_task_id: UUID | None = None,
    ) -> None:
        """Update agent status"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agents
                    SET
                        status = $2,
                        current_task_id = $3,
                        last_activity = $4
                    WHERE agent_id = $1
                """,
                    agent_id,
                    status.value,
                    current_task_id,
                    datetime.now(timezone.utc),
                )

                logger.debug(f"Updated agent status: {agent_id} -> {status.value}")

        except Exception as e:
            logger.error(f"Failed to update agent status: {e}")
            raise DatabaseQueryError(f"Failed to update agent: {e}")

    async def update_agent_tokens(
        self,
        agent_id: str,
        tokens_today: int,
        tokens_hour: int,
    ) -> None:
        """Update agent token usage"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE agents
                    SET
                        tokens_used_today = $2,
                        tokens_used_hour = $3,
                        last_activity = $4
                    WHERE agent_id = $1
                """,
                    agent_id,
                    tokens_today,
                    tokens_hour,
                    datetime.now(timezone.utc),
                )

        except Exception as e:
            logger.error(f"Failed to update agent tokens: {e}")
            raise DatabaseQueryError(f"Failed to update agent tokens: {e}")

    # =========================================================================
    # Tasks Table
    # =========================================================================

    async def create_task(
        self,
        agent_id: str,
        description: str,
        created_by: str,
        payload: dict[str, Any] | None = None,
        parent_task_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Create new task"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO tasks (
                        agent_id,
                        description,
                        payload,
                        created_by,
                        parent_task_id
                    )
                    VALUES ($1, $2, $3::jsonb, $4, $5)
                    RETURNING
                        id,
                        agent_id,
                        description,
                        status,
                        created_at
                """,
                    agent_id,
                    description,
                    json.dumps(payload or {}),
                    created_by,
                    parent_task_id,
                )

                logger.info(f"Created task: {row['id']} for agent {agent_id}")
                return dict(row)

        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            raise DatabaseQueryError(f"Failed to create task: {e}")

    async def get_task(self, task_id: UUID) -> dict[str, Any] | None:
        """Get task by ID"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        id,
                        agent_id,
                        parent_task_id,
                        description,
                        payload,
                        status,
                        result,
                        error,
                        created_by,
                        created_at,
                        started_at,
                        completed_at,
                        retry_count
                    FROM tasks
                    WHERE id = $1
                """,
                    task_id,
                )

                return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get task: {e}")
            raise DatabaseQueryError(f"Failed to query task: {e}")

    async def list_tasks(
        self,
        agent_id: str | None = None,
        status: TaskStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List tasks with filters"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            # Build query
            conditions = []
            params = []
            param_idx = 1

            if agent_id:
                conditions.append(f"agent_id = ${param_idx}")
                params.append(agent_id)
                param_idx += 1

            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            async with self.pool.acquire() as conn:
                # Get total count
                count_query = f"SELECT COUNT(*) FROM tasks {where_clause}"
                total = await conn.fetchval(count_query, *params)

                # Get tasks
                params.extend([limit, offset])
                tasks_query = f"""
                    SELECT
                        id,
                        agent_id,
                        description,
                        status,
                        created_by,
                        created_at,
                        started_at,
                        completed_at
                    FROM tasks
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """

                rows = await conn.fetch(tasks_query, *params)
                tasks = [dict(row) for row in rows]

                return {
                    "tasks": tasks,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            raise DatabaseQueryError(f"Failed to list tasks: {e}")

    async def update_task_status(
        self,
        task_id: UUID,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update task status"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            now = datetime.now(timezone.utc)

            async with self.pool.acquire() as conn:
                if status == TaskStatus.RUNNING:
                    await conn.execute(
                        """
                        UPDATE tasks
                        SET status = $2, started_at = $3
                        WHERE id = $1
                    """,
                        task_id,
                        status.value,
                        now,
                    )

                elif status in (TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    await conn.execute(
                        """
                        UPDATE tasks
                        SET
                            status = $2,
                            result = $3::jsonb,
                            error = $4,
                            completed_at = $5
                        WHERE id = $1
                    """,
                        task_id,
                        status.value,
                        json.dumps(result) if result else None,
                        error,
                        now,
                    )

                else:
                    await conn.execute(
                        """
                        UPDATE tasks
                        SET status = $2
                        WHERE id = $1
                    """,
                        task_id,
                        status.value,
                    )

                logger.debug(f"Updated task status: {task_id} -> {status.value}")

        except Exception as e:
            logger.error(f"Failed to update task: {e}")
            raise DatabaseQueryError(f"Failed to update task: {e}")

    # =========================================================================
    # Action Logs Table
    # =========================================================================

    async def create_log(
        self,
        agent_id: str,
        action: str,
        details: dict[str, Any],
        task_id: UUID | None = None,
        duration_ms: int | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> UUID:
        """Create action log entry"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                log_id = await conn.fetchval(
                    """
                    INSERT INTO action_logs (
                        agent_id,
                        task_id,
                        action,
                        details,
                        duration_ms,
                        success,
                        error
                    )
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                    RETURNING id
                """,
                    agent_id,
                    task_id,
                    action,
                    json.dumps(details),
                    duration_ms,
                    success,
                    error,
                )

                logger.debug(f"Created log entry: {log_id}")
                return log_id

        except Exception as e:
            logger.error(f"Failed to create log: {e}")
            raise DatabaseQueryError(f"Failed to create log: {e}")

    async def query_logs(
        self,
        agent_id: str | None = None,
        task_id: UUID | None = None,
        action: str | None = None,
        success: bool | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Query action logs with filters"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            # Build query dynamically
            conditions = []
            params = []
            param_idx = 1

            if agent_id:
                conditions.append(f"agent_id = ${param_idx}")
                params.append(agent_id)
                param_idx += 1

            if task_id:
                conditions.append(f"task_id = ${param_idx}")
                params.append(task_id)
                param_idx += 1

            if action:
                conditions.append(f"action = ${param_idx}")
                params.append(action)
                param_idx += 1

            if success is not None:
                conditions.append(f"success = ${param_idx}")
                params.append(success)
                param_idx += 1

            if from_time:
                conditions.append(f"timestamp >= ${param_idx}")
                params.append(from_time)
                param_idx += 1

            if to_time:
                conditions.append(f"timestamp <= ${param_idx}")
                params.append(to_time)
                param_idx += 1

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

            async with self.pool.acquire() as conn:
                # Get total count
                count_query = f"SELECT COUNT(*) FROM action_logs {where_clause}"
                total = await conn.fetchval(count_query, *params)

                # Get logs
                params.extend([limit, offset])
                logs_query = f"""
                    SELECT
                        id,
                        agent_id,
                        task_id,
                        action,
                        details,
                        timestamp,
                        duration_ms,
                        success,
                        error
                    FROM action_logs
                    {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """

                rows = await conn.fetch(logs_query, *params)
                logs = [dict(row) for row in rows]

                return {
                    "logs": logs,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }

        except Exception as e:
            logger.error(f"Failed to query logs: {e}")
            raise DatabaseQueryError(f"Failed to query logs: {e}")

    # =========================================================================
    # Token Usage Table
    # =========================================================================

    async def record_token_usage(
        self,
        agent_id: str,
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float,
        task_id: UUID | None = None,
        fallback_used: bool = False,
        cached: bool = False,
    ) -> UUID:
        """Record token usage"""
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                usage_id = await conn.fetchval(
                    """
                    INSERT INTO token_usage (
                        agent_id,
                        task_id,
                        model,
                        provider,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        cost_usd,
                        fallback_used,
                        cached
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING id
                """,
                    agent_id,
                    task_id,
                    model,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_usd,
                    fallback_used,
                    cached,
                )

                logger.debug(f"Recorded token usage: {usage_id} ({total_tokens} tokens)")
                return usage_id

        except Exception as e:
            logger.error(f"Failed to record token usage: {e}")
            raise DatabaseQueryError(f"Failed to record token usage: {e}")

    async def get_token_stats(
        self,
        period: str = "today",
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get token usage statistics.

        Args:
            period: 'today', 'yesterday', 'this_week', 'this_month'
            agent_id: Optional agent filter

        Returns:
            dict: Token statistics by agent and time
        """
        if not self.pool:
            raise DatabaseConnectionError("Database pool not initialized")

        try:
            # Determine time range
            now = datetime.now(timezone.utc)

            if period == "today":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif period == "yesterday":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_time = start_time.replace(day=start_time.day - 1)
            elif period == "this_week":
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
                start_time = start_time.replace(day=start_time.day - start_time.weekday())
            elif period == "this_month":
                start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            else:
                start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)

            async with self.pool.acquire() as conn:
                # Query aggregated stats by agent
                query = """
                    SELECT
                        agent_id,
                        SUM(total_tokens) as total_tokens,
                        SUM(cost_usd) as total_cost,
                        COUNT(*) as num_calls,
                        array_agg(DISTINCT model) as models_used
                    FROM token_usage
                    WHERE timestamp >= $1
                """

                params = [start_time]

                if agent_id:
                    query += " AND agent_id = $2"
                    params.append(agent_id)

                query += " GROUP BY agent_id ORDER BY total_tokens DESC"

                rows = await conn.fetch(query, *params)

                by_agent = []
                total_tokens = 0
                total_cost = 0.0

                for row in rows:
                    agent_stats = {
                        "agent_id": row["agent_id"],
                        "total_tokens": row["total_tokens"],
                        "total_cost": round(float(row["total_cost"]), 4),
                        "num_calls": row["num_calls"],
                        "models_used": row["models_used"],
                    }
                    by_agent.append(agent_stats)
                    total_tokens += row["total_tokens"]
                    total_cost += float(row["total_cost"])

                # Get hourly chart data (for today)
                chart_data = []
                if period == "today":
                    for hour in range(24):
                        hour_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                        hour_end = hour_start.replace(minute=59, second=59)

                        hour_query = """
                            SELECT
                                COALESCE(SUM(total_tokens), 0) as tokens,
                                COALESCE(SUM(cost_usd), 0) as cost
                            FROM token_usage
                            WHERE timestamp >= $1 AND timestamp <= $2
                        """

                        hour_params = [hour_start, hour_end]
                        if agent_id:
                            hour_query += " AND agent_id = $3"
                            hour_params.append(agent_id)

                        hour_row = await conn.fetchrow(hour_query, *hour_params)

                        chart_data.append(
                            {
                                "hour": f"{hour:02d}:00",
                                "tokens": hour_row["tokens"],
                                "cost": round(float(hour_row["cost"]), 4),
                            }
                        )

                return {
                    "period": period,
                    "date": now.strftime("%Y-%m-%d"),
                    "by_agent": by_agent,
                    "total_tokens": int(total_tokens) if total_tokens else 0,
                    "total_cost": round(float(total_cost), 4),
                    "chart_data": chart_data,
                }

        except Exception as e:
            logger.error(f"Failed to get token stats: {e}")
            raise DatabaseQueryError(f"Failed to get token stats: {e}")

    async def update_task_result(
        self,
        task_id: UUID,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        """Update task with result"""
        await self.update_task_status(task_id, status, result, error)
