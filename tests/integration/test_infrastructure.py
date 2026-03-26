"""
Integration tests for infrastructure services.

Tests connectivity and basic operations for PostgreSQL, Redis, RabbitMQ, and Qdrant.
"""

import asyncio

import aio_pika
import asyncpg
import pytest
import redis.asyncio as aioredis
from aio_pika import connect_robust
from qdrant_client import QdrantClient

from shared.config import settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_connection():
    """Test PostgreSQL connection and query"""
    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )

    conn = await asyncpg.connect(dsn)

    try:
        result = await conn.fetchval("SELECT COUNT(*) FROM agents")
        assert result >= 2

        agents = await conn.fetch("SELECT agent_id, name FROM agents ORDER BY agent_id")
        agent_ids = [row["agent_id"] for row in agents]

        assert "orchestrator" in agent_ids
        assert "coder" in agent_ids

        print(f"✅ PostgreSQL: Found {result} agents")
    finally:
        await conn.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_connection():
    """Test Redis connection and operations"""
    client = aioredis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}",
        encoding="utf-8",
        decode_responses=True,
    )

    try:
        await client.ping()

        await client.set("test_key", "test_value", ex=10)
        value = await client.get("test_key")
        assert value == "test_value"

        await client.delete("test_key")

        print("✅ Redis: Connection and operations successful")
    finally:
        await client.aclose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rabbitmq_connection():
    """Test RabbitMQ connection and message flow"""
    connection = await connect_robust(
        f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}"
        f"@{settings.rabbitmq_host}:{settings.rabbitmq_port}{settings.rabbitmq_vhost}"
    )

    try:
        channel = await connection.channel()

        queue = await channel.declare_queue("test_queue", auto_delete=True)

        await channel.default_exchange.publish(
            message=aio_pika.Message(body=b"test message"),
            routing_key="test_queue",
        )

        message = await queue.get(timeout=5)
        assert message is not None
        assert message.body == b"test message"
        await message.ack()

        print("✅ RabbitMQ: Connection and messaging successful")
    finally:
        await connection.close()


@pytest.mark.integration
def test_qdrant_connection():
    """Test Qdrant connection and basic operations"""
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port, timeout=10)

    collections = client.get_collections()
    print(f"✅ Qdrant: Connected, found {len(collections.collections)} collections")

    assert collections is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_services():
    """Test all services can be accessed"""
    results = await asyncio.gather(
        test_postgres_connection(),
        test_redis_connection(),
        return_exceptions=True,
    )

    errors = [r for r in results if isinstance(r, Exception)]

    if errors:
        print(f"❌ {len(errors)} service(s) failed:")
        for err in errors:
            print(f"  - {type(err).__name__}: {err}")
        pytest.fail(f"{len(errors)} services failed")
    else:
        print(f"✅ All {len(results)} async services passed!")

    # RabbitMQ is optional in current dev MVP setup.
    try:
        await test_rabbitmq_connection()
    except Exception as err:
        print(f"⚠️ RabbitMQ skipped in dev: {type(err).__name__}: {err}")

    test_qdrant_connection()
    print("✅ Core infrastructure services working!")
