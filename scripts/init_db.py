#!/usr/bin/env python3
"""
Initialize PostgreSQL database schema.

Creates all tables, indexes, and views required for the Balbes Multi-Agent System.

Usage:
    python scripts/init_db.py
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import Settings


async def create_schema(conn: asyncpg.Connection):
    """Create database schema"""

    print("Creating tables...")

    # Table: agents
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            agent_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'idle',
            current_task_id UUID,
            current_model VARCHAR(100) NOT NULL,
            config JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            last_activity TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            tokens_used_today INTEGER NOT NULL DEFAULT 0,
            tokens_used_hour INTEGER NOT NULL DEFAULT 0,

            CONSTRAINT status_check CHECK (status IN ('idle', 'working', 'error', 'paused'))
        );
    """)
    print("  ✅ Created table: agents")

    # Table: tasks
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id VARCHAR(50) NOT NULL REFERENCES agents(agent_id),
            parent_task_id UUID REFERENCES tasks(id),
            description TEXT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            payload JSONB NOT NULL DEFAULT '{}',
            result JSONB,
            error TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            retry_count INTEGER NOT NULL DEFAULT 0,
            created_by VARCHAR(50) NOT NULL,

            CONSTRAINT status_check CHECK (status IN ('pending', 'running', 'success', 'failed', 'timeout', 'cancelled'))
        );
    """)
    print("  ✅ Created table: tasks")

    # Table: action_logs
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS action_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id VARCHAR(50) NOT NULL,
            task_id UUID REFERENCES tasks(id),
            action VARCHAR(100) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}',
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            duration_ms INTEGER,
            success BOOLEAN NOT NULL DEFAULT TRUE,
            error TEXT
        );
    """)
    print("  ✅ Created table: action_logs")

    # Table: token_usage
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id VARCHAR(50) NOT NULL,
            task_id UUID REFERENCES tasks(id),
            model VARCHAR(100) NOT NULL,
            provider VARCHAR(50) NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            cost_usd DECIMAL(10, 6) NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
            cached BOOLEAN NOT NULL DEFAULT FALSE
        );
    """)
    print("  ✅ Created table: token_usage")

    print("\nCreating indexes...")

    # Indexes for agents
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_agents_last_activity ON agents(last_activity);"
    )

    # Indexes for tasks
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON tasks(agent_id);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC);")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_agent_status ON tasks(agent_id, status);"
    )

    # Indexes for action_logs
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_logs_agent_id ON action_logs(agent_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_logs_timestamp ON action_logs(timestamp DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_logs_agent_time ON action_logs(agent_id, timestamp DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_action_logs_task_id ON action_logs(task_id);"
    )

    # Indexes for token_usage
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_agent_id ON token_usage(agent_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_timestamp ON token_usage(timestamp DESC);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_usage_agent_time ON token_usage(agent_id, timestamp DESC);"
    )

    print("  ✅ Created all indexes")

    print("\nCreating views...")

    # View: tokens today
    await conn.execute("""
        CREATE OR REPLACE VIEW v_tokens_today AS
        SELECT
            agent_id,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost,
            COUNT(*) as num_calls,
            MAX(timestamp) as last_call
        FROM token_usage
        WHERE DATE(timestamp) = CURRENT_DATE
        GROUP BY agent_id;
    """)
    print("  ✅ Created view: v_tokens_today")

    # View: tokens current hour
    await conn.execute("""
        CREATE OR REPLACE VIEW v_tokens_current_hour AS
        SELECT
            agent_id,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost
        FROM token_usage
        WHERE timestamp >= DATE_TRUNC('hour', NOW())
        GROUP BY agent_id;
    """)
    print("  ✅ Created view: v_tokens_current_hour")

    # View: task stats
    await conn.execute("""
        CREATE OR REPLACE VIEW v_task_stats AS
        SELECT
            agent_id,
            COUNT(*) FILTER (WHERE status = 'success') as completed,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            COUNT(*) FILTER (WHERE status IN ('pending', 'running')) as active,
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) FILTER (WHERE status = 'success') as avg_duration_seconds
        FROM tasks
        GROUP BY agent_id;
    """)
    print("  ✅ Created view: v_task_stats")

    # Table: skills (for Skills Registry)
    print("\nCreating skills table...")
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            skill_id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            description TEXT NOT NULL,
            version VARCHAR(20) NOT NULL DEFAULT '1.0.0',
            tags TEXT[] NOT NULL DEFAULT '{}',
            category VARCHAR(50) NOT NULL,
            implementation_url VARCHAR(500) NOT NULL,
            input_schema JSONB NOT NULL,
            output_schema JSONB NOT NULL,
            estimated_tokens INTEGER NOT NULL DEFAULT 1000,
            authors TEXT[] NOT NULL DEFAULT '{}',
            dependencies TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            usage_count INTEGER NOT NULL DEFAULT 0,
            rating FLOAT NOT NULL DEFAULT 0.0
        );
    """)
    print("  ✅ Created table: skills")

    # Indexes for skills
    print("\nCreating skills indexes...")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_tags ON skills USING GIN(tags);")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_skills_created_at ON skills(created_at DESC);"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_rating ON skills(rating DESC);")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_skills_usage ON skills(usage_count DESC);")
    print("  ✅ Created skills indexes")

    # Views for skills
    print("\nCreating skills views...")
    await conn.execute("""
        CREATE OR REPLACE VIEW v_trending_skills AS
        SELECT
            skill_id,
            name,
            category,
            rating,
            usage_count,
            (usage_count + (rating * 10)) as popularity_score
        FROM skills
        WHERE created_at > NOW() - INTERVAL '30 days'
        ORDER BY popularity_score DESC;
    """)
    print("  ✅ Created view: v_trending_skills")

    await conn.execute("""
        CREATE OR REPLACE VIEW v_top_rated_skills AS
        SELECT
            skill_id,
            name,
            category,
            rating,
            usage_count
        FROM skills
        WHERE usage_count >= 5
        ORDER BY rating DESC, usage_count DESC;
    """)
    print("  ✅ Created view: v_top_rated_skills")

    print("\n✅ Database schema created successfully!")


async def seed_initial_agents(conn: asyncpg.Connection):
    """Insert initial agent records"""

    print("\nSeeding initial agents...")

    # Orchestrator
    await conn.execute("""
        INSERT INTO agents (agent_id, name, status, current_model, config)
        VALUES (
            'orchestrator',
            'Orchestrator',
            'idle',
            'openrouter/stepfun/step-3.5-flash:free',
            '{
                "agent_id": "orchestrator",
                "token_limits": {"daily": 100000, "hourly": 15000}
            }'::jsonb
        )
        ON CONFLICT (agent_id) DO NOTHING;
    """)
    print("  ✅ Seeded agent: orchestrator")

    # Coder
    await conn.execute("""
        INSERT INTO agents (agent_id, name, status, current_model, config)
        VALUES (
            'coder',
            'Coder Agent',
            'idle',
            'openrouter/stepfun/step-3.5-flash:free',
            '{
                "agent_id": "coder",
                "token_limits": {"daily": 100000, "hourly": 15000}
            }'::jsonb
        )
        ON CONFLICT (agent_id) DO NOTHING;
    """)
    print("  ✅ Seeded agent: coder")


async def verify_schema(conn: asyncpg.Connection):
    """Verify that schema was created correctly"""

    print("\nVerifying schema...")

    # Check tables
    tables = await conn.fetch("""
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """)

    expected_tables = {"agents", "tasks", "action_logs", "token_usage", "skills"}
    actual_tables = {row["tablename"] for row in tables}

    if expected_tables.issubset(actual_tables):
        print(f"  ✅ All tables present: {', '.join(sorted(expected_tables))}")
    else:
        missing = expected_tables - actual_tables
        print(f"  ❌ Missing tables: {', '.join(missing)}")
        return False

    # Check views
    views = await conn.fetch("""
        SELECT viewname
        FROM pg_views
        WHERE schemaname = 'public';
    """)

    expected_views = {
        "v_tokens_today",
        "v_tokens_current_hour",
        "v_task_stats",
        "v_trending_skills",
        "v_top_rated_skills",
    }
    actual_views = {row["viewname"] for row in views}

    if expected_views.issubset(actual_views):
        print(f"  ✅ All views present: {', '.join(sorted(expected_views))}")
    else:
        missing = expected_views - actual_views
        print(f"  ❌ Missing views: {', '.join(missing)}")
        return False

    # Check agents
    agents = await conn.fetch("SELECT agent_id, name FROM agents ORDER BY agent_id;")
    print(f"  ✅ Agents initialized: {', '.join(row['agent_id'] for row in agents)}")

    return True


async def main():
    """Main initialization function"""

    print("=" * 60)
    print("Balbes Multi-Agent System - Database Initialization")
    print("=" * 60)
    print()

    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        print("Make sure .env file exists and is properly configured.")
        sys.exit(1)

    # Connection string
    dsn = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"

    print("Connecting to PostgreSQL...")
    print(f"  Host: {settings.postgres_host}:{settings.postgres_port}")
    print(f"  Database: {settings.postgres_db}")
    print(f"  User: {settings.postgres_user}")
    print()

    try:
        # Connect
        conn = await asyncpg.connect(dsn)
        print("✅ Connected to PostgreSQL")
        print()

        # Create schema
        await create_schema(conn)

        # Seed agents
        await seed_initial_agents(conn)

        # Verify
        success = await verify_schema(conn)

        # Close
        await conn.close()

        print()
        print("=" * 60)
        if success:
            print("✅ Database initialization completed successfully!")
            print()
            print("Next steps:")
            print("  1. Run: make db-seed (to load base skills)")
            print("  2. Start services: make dev-memory, make dev-skills, etc.")
            print("  3. Test Telegram bot: /start")
        else:
            print("⚠️  Database initialization completed with warnings")
            print("Check the output above for details.")
        print("=" * 60)

    except asyncpg.PostgresError as e:
        print()
        print("❌ PostgreSQL Error:")
        print(f"  {e}")
        print()
        print("Troubleshooting:")
        print("  1. Check that PostgreSQL container is running: docker ps")
        print("  2. Check database credentials in .env file")
        print("  3. Check PostgreSQL logs: docker logs balbes-postgres")
        sys.exit(1)

    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
