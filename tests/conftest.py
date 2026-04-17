"""
Pytest configuration and fixtures.

Provides common fixtures for all tests.
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="function")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings for testing"""
    from shared.config import Settings

    return Settings(
        openrouter_api_key="test-key",
        aitunnel_api_key="test-key",
        telegram_bot_token="123:ABC",
        telegram_user_id=123,
        web_auth_token="test-token",
        jwt_secret="test-secret",
        postgres_password="test-password",
    )


@pytest.fixture
async def mock_redis():
    """Mock Redis client"""
    from unittest.mock import AsyncMock

    redis = AsyncMock()
    redis.get.return_value = None
    redis.set.return_value = True
    redis.delete.return_value = 1
    redis.incr.return_value = 1
    redis.lpush.return_value = 1
    redis.lrange.return_value = []

    return redis


@pytest.fixture
async def mock_postgres():
    """Mock PostgreSQL client"""
    from unittest.mock import AsyncMock

    pg = AsyncMock()
    return pg


@pytest.fixture
async def mock_qdrant():
    """Mock Qdrant client"""
    from unittest.mock import Mock

    qdrant = Mock()
    qdrant.search.return_value = []
    qdrant.upsert.return_value = {"status": "ok"}

    return qdrant


@pytest.fixture
def mock_llm_response():
    """Mock LLM response"""
    from shared.models import LLMResponse

    return LLMResponse(
        content="Mock response",
        model="mock-model",
        provider="mock",
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        cost_usd=0.001,
        fallback_used=False,
        duration_ms=100,
    )


@pytest.fixture
def sample_task():
    """Sample task for testing"""
    from uuid import uuid4

    from shared.models import Task

    return Task(
        id=uuid4(),
        agent_id="test_agent",
        description="Test task description",
        status="pending",
        payload={"test": "data"},
        created_by="test",
    )


@pytest.fixture
def sample_message():
    """Sample message for testing"""
    from uuid import uuid4

    from shared.models import Message

    return Message(
        id=uuid4(),
        from_agent="test_sender",
        to_agent="test_receiver",
        type="task",
        payload={"test": "data"},
    )


# Markers for different test types
def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Unit tests (fast, no external dependencies)")
    config.addinivalue_line("markers", "integration: Integration tests (require services running)")
    config.addinivalue_line("markers", "e2e: End-to-end tests (require full system)")
    config.addinivalue_line("markers", "slow: Slow tests (may take several seconds)")


@pytest.fixture
async def openrouter_available() -> bool:
    """Check if OpenRouter API is available"""
    import httpx

    from shared.config import get_settings

    settings = get_settings()
    if not settings.openrouter_api_key or settings.openrouter_api_key.startswith("sk-or-v1-dev"):
        return False

    try:
        from shared.openrouter_http import openrouter_json_headers

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/embeddings",
                headers=openrouter_json_headers(settings),
                json={"model": "text-embedding-3-small", "input": "test"},
            )
            return response.status_code == 200
    except Exception:
        return False
