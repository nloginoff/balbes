"""
Integration tests for Orchestrator Service.

Tests cover:
- Agent initialization and lifecycle
- Task execution
- Skill selection
- Memory integration
- Notification system
- API endpoints
"""

import logging
import os
import sys

import httpx
import pytest
import pytest_asyncio

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

logger = logging.getLogger("test.orchestrator")


# =============================================================================
# Fixtures
# =============================================================================


@pytest_asyncio.fixture(scope="function")
async def http_client():
    """HTTP client for API testing"""
    client = httpx.AsyncClient(timeout=30.0)
    try:
        yield client
    finally:
        try:
            await client.aclose()
        except RuntimeError:
            pass  # Event loop already closed


@pytest.fixture
def user_id():
    """Test user ID"""
    return "test_user_123"


@pytest.fixture
def task_description():
    """Test task description"""
    return "What are the latest AI trends?"


# =============================================================================
# Orchestrator Agent Tests
# =============================================================================


@pytest.mark.asyncio
async def test_agent_initialization():
    """Test orchestrator agent initialization"""
    from services.orchestrator.agent import OrchestratorAgent

    agent = OrchestratorAgent()
    assert agent.agent_id == "balbes"
    assert agent.memory_service_url
    assert agent.skills_registry_url

    await agent.connect()
    assert agent.http_client is not None

    await agent.close()


@pytest.mark.asyncio
async def test_agent_status():
    """Test agent status endpoint"""
    from services.orchestrator.agent import OrchestratorAgent

    agent = OrchestratorAgent()
    await agent.connect()

    status = await agent.get_agent_status()

    assert status["agent_id"] == "balbes"
    assert status["status"] == "online"
    assert "services" in status
    assert "memory_service" in status["services"]
    assert "skills_registry" in status["services"]

    await agent.close()


@pytest.mark.asyncio
async def test_task_execution_structure(user_id, task_description):
    """Test task execution returns correct structure"""
    from services.orchestrator.agent import OrchestratorAgent

    agent = OrchestratorAgent()
    await agent.connect()

    result = await agent.execute_task(
        description=task_description,
        user_id=user_id,
    )

    # Check result structure
    assert "task_id" in result
    assert "status" in result
    assert "duration_ms" in result

    # Status should be success or failed
    assert result["status"] in ["success", "failed"]

    # Duration should be positive
    assert result["duration_ms"] >= 0

    await agent.close()


@pytest.mark.asyncio
async def test_task_with_context(user_id, task_description):
    """Test task execution with context"""
    from services.orchestrator.agent import OrchestratorAgent

    agent = OrchestratorAgent()
    await agent.connect()

    context = {
        "user_preferences": {"language": "en"},
        "previous_tasks": [],
    }

    result = await agent.execute_task(
        description=task_description,
        user_id=user_id,
        context=context,
    )

    assert "task_id" in result
    assert "status" in result

    await agent.close()


# =============================================================================
# Notification Service Tests
# =============================================================================


@pytest.mark.asyncio
async def test_notification_service_initialization():
    """Test notification service initialization"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    assert service.http_client is not None
    assert len(service.notifications_queue) == 0

    await service.close()


@pytest.mark.asyncio
async def test_task_started_notification(user_id):
    """Test task started notification"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    notification = await service.notify_task_started(
        user_id=user_id,
        task_id="task_123",
        description="Test task",
    )

    assert notification is not None
    assert notification.user_id == user_id
    assert notification.title == "🚀 Task Started"
    assert notification.sent

    await service.close()


@pytest.mark.asyncio
async def test_task_completed_notification(user_id):
    """Test task completed notification"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    notification = await service.notify_task_completed(
        user_id=user_id,
        task_id="task_456",
        skill_name="SearchSkill",
        result={"answer": "Test answer"},
    )

    assert notification is not None
    assert notification.title == "✅ Task Completed"
    assert "SearchSkill" in notification.message

    await service.close()


@pytest.mark.asyncio
async def test_task_failed_notification(user_id):
    """Test task failed notification"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    notification = await service.notify_task_failed(
        user_id=user_id,
        task_id="task_789",
        error="Service not available",
    )

    assert notification is not None
    assert notification.title == "❌ Task Failed"
    assert "Service not available" in notification.message

    await service.close()


@pytest.mark.asyncio
async def test_notification_history(user_id):
    """Test notification history retrieval"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    # Create multiple notifications
    await service.notify_task_started(
        user_id=user_id,
        task_id="task_1",
        description="Task 1",
    )

    await service.notify_task_completed(
        user_id=user_id,
        task_id="task_2",
        skill_name="Skill1",
        result={"ok": True},
    )

    # Get history
    history = await service.get_notification_history(user_id, limit=10)

    assert len(history) >= 2
    assert history[0]["user_id"] == user_id

    await service.close()


@pytest.mark.asyncio
async def test_mark_notification_as_read(user_id):
    """Test marking notification as read"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    notification = await service.notify_task_started(
        user_id=user_id,
        task_id="task_read",
        description="Task to read",
    )

    assert not notification.read

    # Mark as read
    success = await service.mark_as_read(notification.id)
    assert success
    assert notification.read

    await service.close()


@pytest.mark.asyncio
async def test_clear_notifications(user_id):
    """Test clearing notifications"""
    from services.orchestrator.notifications import NotificationService

    service = NotificationService()
    await service.connect()

    # Create notifications
    await service.notify_task_started(
        user_id=user_id,
        task_id="task_x",
        description="Task X",
    )

    await service.notify_task_started(
        user_id=user_id,
        task_id="task_y",
        description="Task Y",
    )

    # Clear
    cleared = await service.clear_notifications(user_id)
    assert cleared >= 2

    # Verify cleared
    history = await service.get_notification_history(user_id)
    assert len(history) == 0

    await service.close()


# =============================================================================
# API Endpoint Tests
# =============================================================================


@pytest.mark.asyncio
async def test_orchestrator_health_check(http_client):
    """Test health check endpoint"""
    try:
        response = await http_client.get("http://localhost:8102/health")
        assert response.status_code in [200, 503]  # 503 if not running
    except httpx.ConnectError:
        pytest.skip("Orchestrator service not running")


@pytest.mark.asyncio
async def test_orchestrator_root_endpoint(http_client):
    """Test root endpoint"""
    try:
        response = await http_client.get("http://localhost:8102/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert data["service"] == "Orchestrator"
    except httpx.ConnectError:
        pytest.skip("Orchestrator service not running")


@pytest.mark.asyncio
async def test_task_execution_api(http_client, user_id):
    """Test task creation via API"""
    try:
        response = await http_client.post(
            "http://localhost:8102/api/v1/tasks",
            params={
                "user_id": user_id,
                "description": "Test task via API",
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "task_id" in data
            assert "status" in data
        elif response.status_code == 503:
            pytest.skip("Orchestrator not initialized")
        else:
            raise AssertionError(f"Unexpected status: {response.status_code}")

    except httpx.ConnectError:
        pytest.skip("Orchestrator service not running")


@pytest.mark.asyncio
async def test_notification_history_api(http_client, user_id):
    """Test notification history API"""
    try:
        response = await http_client.get(
            "http://localhost:8102/api/v1/notifications/history",
            params={"user_id": user_id, "limit": 10},
        )

        if response.status_code == 200:
            data = response.json()
            assert "user_id" in data
            assert "notifications" in data
        elif response.status_code == 503:
            pytest.skip("Notification service not initialized")
        else:
            raise AssertionError(f"Unexpected status: {response.status_code}")

    except httpx.ConnectError:
        pytest.skip("Orchestrator service not running")


# =============================================================================
# Configuration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_orchestrator_config():
    """Test orchestrator configuration"""
    from shared.config import get_settings

    settings = get_settings()

    assert settings.orchestrator_port == 8102
    assert settings.memory_service_port == 8100
    assert settings.skills_registry_port == 8101
    assert settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR"]
    assert settings.task_timeout_seconds > 0
    assert settings.max_retries > 0


# =============================================================================
# Integration Workflow Tests
# =============================================================================


@pytest.mark.asyncio
async def test_complete_workflow(user_id, task_description):
    """Test complete workflow: agent -> skills -> memory -> notifications"""
    from services.orchestrator.agent import OrchestratorAgent
    from services.orchestrator.notifications import NotificationService

    agent = OrchestratorAgent()
    notifications = NotificationService()

    await agent.connect()
    await notifications.connect()

    # Start task
    start_notif = await notifications.notify_task_started(
        user_id=user_id,
        task_id="workflow_test",
        description=task_description,
    )

    assert start_notif is not None

    # Execute task
    result = await agent.execute_task(
        description=task_description,
        user_id=user_id,
    )

    assert result["task_id"]

    # Notify completion
    if result["status"] == "success":
        completion_notif = await notifications.notify_task_completed(
            user_id=user_id,
            task_id=result["task_id"],
            skill_name=result.get("skill_used", "Unknown"),
            result=result.get("result", {}),
        )
    else:
        completion_notif = await notifications.notify_task_failed(
            user_id=user_id,
            task_id=result["task_id"],
            error=result.get("error", "Unknown error"),
        )

    assert completion_notif is not None

    await agent.close()
    await notifications.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
