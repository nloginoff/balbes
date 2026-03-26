"""
Integration tests for Memory Service.

Tests the full flow of Memory Service API with real database connections.
Requires infrastructure to be running (PostgreSQL, Redis, Qdrant).
"""

import asyncio
from uuid import uuid4

import httpx
import pytest

# Base URL for Memory Service
BASE_URL = "http://localhost:8100"


@pytest.fixture
def agent_id():
    """Test agent ID (use existing agent from DB)"""
    return "coder"


@pytest.fixture
def task_id():
    """Test task ID"""
    return str(uuid4())


class TestHealthCheck:
    """Test health check endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test that health check returns 200"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health")

            assert response.status_code == 200
            data = response.json()

            assert data["service"] == "memory-service"
            assert "status" in data
            assert "redis" in data
            assert "qdrant" in data
            assert "postgres" in data


class TestContext:
    """Test context endpoints (Redis)"""

    @pytest.mark.asyncio
    async def test_set_and_get_context(self, agent_id):
        """Test setting and getting context"""
        async with httpx.AsyncClient() as client:
            # Set context
            context_data = {
                "key": "test_context",
                "value": {"step": 1, "files": ["main.py"]},
                "ttl": 60,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/context/{agent_id}",
                json=context_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "ok"
            assert result["key"] == "test_context"
            assert "expires_at" in result

            # Get context
            response = await client.get(f"{BASE_URL}/api/v1/context/{agent_id}/test_context")

            assert response.status_code == 200
            result = response.json()
            assert result["key"] == "test_context"
            assert result["value"] == {"step": 1, "files": ["main.py"]}
            assert result["ttl_remaining"] > 0

    @pytest.mark.asyncio
    async def test_delete_context(self, agent_id):
        """Test deleting context"""
        async with httpx.AsyncClient() as client:
            # Set context first
            await client.post(
                f"{BASE_URL}/api/v1/context/{agent_id}",
                json={"key": "to_delete", "value": {"test": True}, "ttl": 60},
            )

            # Delete it
            response = await client.delete(f"{BASE_URL}/api/v1/context/{agent_id}/to_delete")

            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "deleted"

            # Try to get - should be 404
            response = await client.get(f"{BASE_URL}/api/v1/context/{agent_id}/to_delete")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_context_expiration(self, agent_id):
        """Test that context expires after TTL"""
        async with httpx.AsyncClient() as client:
            # Set context with 2 second TTL
            await client.post(
                f"{BASE_URL}/api/v1/context/{agent_id}",
                json={"key": "expire_test", "value": {"test": True}, "ttl": 2},
            )

            # Should exist immediately
            response = await client.get(f"{BASE_URL}/api/v1/context/{agent_id}/expire_test")
            assert response.status_code == 200

            # Wait for expiration
            await asyncio.sleep(3)

            # Should be gone
            response = await client.get(f"{BASE_URL}/api/v1/context/{agent_id}/expire_test")
            assert response.status_code == 404


class TestHistory:
    """Test history endpoints (Redis)"""

    @pytest.mark.asyncio
    async def test_add_and_get_history(self, agent_id):
        """Test adding and retrieving history"""
        async with httpx.AsyncClient() as client:
            # Clear history first
            await client.delete(f"{BASE_URL}/api/v1/history/{agent_id}")

            # Add messages
            messages = [
                {"role": "user", "content": "Hello", "metadata": {}},
                {"role": "assistant", "content": "Hi there", "metadata": {}},
                {"role": "user", "content": "How are you?", "metadata": {}},
            ]

            for msg in messages:
                response = await client.post(
                    f"{BASE_URL}/api/v1/history/{agent_id}",
                    json=msg,
                )
                assert response.status_code == 200

            # Get history
            response = await client.get(f"{BASE_URL}/api/v1/history/{agent_id}")

            assert response.status_code == 200
            result = response.json()
            assert result["total"] == 3
            assert len(result["messages"]) == 3

            # Verify chronological order
            assert result["messages"][0]["role"] == "user"
            assert result["messages"][0]["content"] == "Hello"


class TestMemory:
    """Test long-term memory endpoints (Qdrant)"""

    @pytest.mark.asyncio
    async def test_store_and_search_memory(self, agent_id):
        """Test storing and searching memory"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Store memory
            memory_data = {
                "agent_id": agent_id,
                "content": "I successfully created a skill for parsing HackerNews using BeautifulSoup",
                "scope": "personal",
                "metadata": {"skill_name": "parse_hackernews", "tags": ["parsing", "web"]},
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/memory",
                json=memory_data,
            )

            assert response.status_code == 201
            result = response.json()
            assert result["status"] == "stored"
            assert "memory_id" in result

            # Search memory
            search_data = {
                "agent_id": agent_id,
                "query": "how did I parse websites before",
                "scope": "personal",
                "limit": 5,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/memory/search",
                json=search_data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["total"] >= 1

            # Should find our memory
            found = any("BeautifulSoup" in r["content"] for r in result["results"])
            assert found, "Should find the stored memory"


class TestAgents:
    """Test agent endpoints (PostgreSQL)"""

    @pytest.mark.asyncio
    async def test_get_all_agents(self):
        """Test getting all agents"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/v1/agents")

            assert response.status_code == 200
            result = response.json()
            assert "agents" in result

            # Should have at least orchestrator and coder
            agent_ids = [a["agent_id"] for a in result["agents"]]
            assert "orchestrator" in agent_ids
            assert "coder" in agent_ids


class TestTasks:
    """Test task endpoints (PostgreSQL)"""

    @pytest.mark.asyncio
    async def test_create_and_get_task(self, agent_id):
        """Test creating and retrieving task"""
        async with httpx.AsyncClient() as client:
            # Create task
            task_data = {
                "agent_id": agent_id,
                "description": "Test task",
                "payload": {"test": True},
                "created_by": "test",
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/tasks",
                json=task_data,
            )

            assert response.status_code == 201
            result = response.json()
            assert "task_id" in result
            assert result["status"] == "pending"

            task_id = result["task_id"]

            # Get task
            response = await client.get(f"{BASE_URL}/api/v1/tasks/{task_id}")

            assert response.status_code == 200
            task = response.json()
            assert task["id"] == task_id
            assert task["agent_id"] == agent_id
            assert task["description"] == "Test task"
            assert task["status"] == "pending"


class TestLogs:
    """Test log endpoints (PostgreSQL)"""

    @pytest.mark.asyncio
    async def test_create_and_query_logs(self, agent_id):
        """Test creating and querying logs"""
        async with httpx.AsyncClient() as client:
            # Create log
            log_data = {
                "agent_id": agent_id,
                "action": "test_action",
                "details": {"test": True},
                "duration_ms": 100,
                "success": True,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/logs",
                json=log_data,
            )

            assert response.status_code == 201
            result = response.json()
            assert "log_id" in result

            # Query logs
            response = await client.get(
                f"{BASE_URL}/api/v1/logs?agent_id={agent_id}&action=test_action"
            )

            assert response.status_code == 200
            result = response.json()
            assert result["total"] >= 1

            # Find our log
            found = any(
                log["agent_id"] == agent_id and log["action"] == "test_action"
                for log in result["logs"]
            )
            assert found


class TestTokens:
    """Test token tracking endpoints"""

    @pytest.mark.asyncio
    async def test_record_and_get_tokens(self, agent_id):
        """Test recording and retrieving token usage"""
        async with httpx.AsyncClient() as client:
            # Record token usage
            token_data = {
                "agent_id": agent_id,
                "model": "claude-3.5-sonnet",
                "provider": "openrouter",
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "cost_usd": 0.002,
                "fallback_used": False,
                "cached": False,
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/tokens/record",
                json=token_data,
            )

            assert response.status_code == 201
            result = response.json()
            assert result["status"] == "recorded"

            # Get token stats
            response = await client.get(f"{BASE_URL}/api/v1/tokens/stats?period=today")

            assert response.status_code == 200
            result = response.json()
            assert result["period"] == "today"
            assert result["total_tokens"] > 0


class TestFullFlow:
    """Test complete workflow"""

    @pytest.mark.asyncio
    async def test_complete_agent_workflow(self):
        """
        Test complete workflow:
        1. Create agent
        2. Set context
        3. Add history
        4. Store memory
        5. Create task
        6. Log action
        7. Record tokens
        8. Verify all data
        """
        test_agent_id = f"test_agent_{uuid4().hex[:8]}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Create agent
            agent_data = {
                "agent_id": test_agent_id,
                "name": "Test Agent",
                "current_model": "claude-3.5-sonnet",
                "config": {},
            }

            response = await client.post(
                f"{BASE_URL}/api/v1/agents",
                json=agent_data,
            )
            assert response.status_code == 201

            # 2. Set context
            await client.post(
                f"{BASE_URL}/api/v1/context/{test_agent_id}",
                json={"key": "workflow_test", "value": {"test": True}, "ttl": 60},
            )

            # 3. Add history
            await client.post(
                f"{BASE_URL}/api/v1/history/{test_agent_id}",
                json={"role": "user", "content": "Test message", "metadata": {}},
            )

            # 4. Store memory
            memory_response = await client.post(
                f"{BASE_URL}/api/v1/memory",
                json={
                    "agent_id": test_agent_id,
                    "content": "Test memory content for workflow",
                    "scope": "personal",
                    "metadata": {},
                },
            )
            assert memory_response.status_code == 201

            # 5. Create task
            task_response = await client.post(
                f"{BASE_URL}/api/v1/tasks",
                json={
                    "agent_id": test_agent_id,
                    "description": "Test task",
                    "created_by": "test",
                },
            )
            assert task_response.status_code == 201
            task_id = task_response.json()["task_id"]

            # 6. Log action
            await client.post(
                f"{BASE_URL}/api/v1/logs",
                json={
                    "agent_id": test_agent_id,
                    "action": "workflow_test",
                    "details": {"test": True},
                    "success": True,
                },
            )

            # 7. Record tokens
            await client.post(
                f"{BASE_URL}/api/v1/tokens/record",
                json={
                    "agent_id": test_agent_id,
                    "model": "claude-3.5-sonnet",
                    "provider": "openrouter",
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "cost_usd": 0.002,
                },
            )

            # 8. Verify all data

            # Verify agent
            response = await client.get(f"{BASE_URL}/api/v1/agents/{test_agent_id}")
            assert response.status_code == 200

            # Verify context
            response = await client.get(f"{BASE_URL}/api/v1/context/{test_agent_id}/workflow_test")
            assert response.status_code == 200

            # Verify history
            response = await client.get(f"{BASE_URL}/api/v1/history/{test_agent_id}")
            assert response.status_code == 200
            assert response.json()["total"] >= 1

            # Verify memory (search)
            response = await client.post(
                f"{BASE_URL}/api/v1/memory/search",
                json={
                    "agent_id": test_agent_id,
                    "query": "workflow test",
                    "limit": 5,
                },
            )
            assert response.status_code == 200

            # Verify task
            response = await client.get(f"{BASE_URL}/api/v1/tasks/{task_id}")
            assert response.status_code == 200

            # Verify logs
            response = await client.get(f"{BASE_URL}/api/v1/logs?agent_id={test_agent_id}")
            assert response.status_code == 200
            assert response.json()["total"] >= 1

            # Verify tokens
            response = await client.get(f"{BASE_URL}/api/v1/tokens/agent/{test_agent_id}")
            assert response.status_code == 200
            token_data = response.json()
            assert token_data["tokens_today"] >= 150

            print(f"\n✅ Complete workflow test passed for agent: {test_agent_id}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
