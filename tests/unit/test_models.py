"""
Unit tests for shared.models module.
"""

from datetime import UTC, datetime

import pytest

from shared.models import (
    Agent,
    AgentStatus,
    LLMResponse,
    Memory,
    MemoryScope,
    MemoryType,
    Message,
    MessageType,
    SkillResult,
    Task,
    TaskStatus,
    TokenBudget,
)


class TestAgent:
    """Tests for Agent model"""

    def test_agent_creation(self):
        """Test creating agent with valid data"""
        agent = Agent(
            id="test_agent",
            name="Test Agent",
            current_model="gpt-4",
        )

        assert agent.id == "test_agent"
        assert agent.name == "Test Agent"
        assert agent.status == AgentStatus.IDLE
        assert agent.tokens_used_today == 0

    def test_agent_id_validation(self):
        """Test agent ID validation"""
        with pytest.raises(ValueError):
            Agent(id="Invalid Agent!", name="Test", current_model="gpt-4")

    def test_agent_id_lowercase(self):
        """Test agent ID is converted to lowercase"""
        agent = Agent(id="Test_Agent", name="Test", current_model="gpt-4")
        assert agent.id == "test_agent"


class TestTask:
    """Tests for Task model"""

    def test_task_creation(self):
        """Test creating task with valid data"""
        task = Task(
            agent_id="test_agent",
            description="Test task",
            created_by="user",
        )

        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 0
        assert task.max_retries == 3
        assert task.timeout_seconds == 600

    def test_task_duration(self):
        """Test task duration calculation"""
        task = Task(
            agent_id="test_agent",
            description="Test",
            created_by="user",
            started_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 12, 5, 30, tzinfo=UTC),
        )

        assert task.duration_seconds == 330.0


class TestMessage:
    """Tests for Message model"""

    def test_message_creation(self):
        """Test creating message"""
        msg = Message(
            from_agent="sender",
            to_agent="receiver",
            type=MessageType.TASK,
            payload={"data": "test"},
        )

        assert msg.from_agent == "sender"
        assert msg.to_agent == "receiver"
        assert not msg.is_broadcast

    def test_broadcast_message(self):
        """Test broadcast message"""
        msg = Message(
            from_agent="sender",
            to_agent=None,
            type=MessageType.NOTIFICATION,
            payload={},
        )

        assert msg.is_broadcast


class TestMemory:
    """Tests for Memory model"""

    def test_memory_creation(self):
        """Test creating memory entry"""
        memory = Memory(
            agent_id="test_agent",
            scope=MemoryScope.PERSONAL,
            memory_type=MemoryType.CONTEXT,
            content="Test memory",
        )

        assert memory.agent_id == "test_agent"
        assert memory.scope == MemoryScope.PERSONAL
        assert memory.tags == []


class TestLLMResponse:
    """Tests for LLMResponse model"""

    def test_llm_response_creation(self):
        """Test creating LLM response"""
        response = LLMResponse(
            content="Test response",
            model="gpt-4",
            provider="openrouter",
            prompt_tokens=100,
            completion_tokens=200,
            total_tokens=300,
            cost_usd=0.015,
            duration_ms=1500,
        )

        assert response.total_tokens == 300
        assert response.tokens_per_second == 200.0

    def test_tokens_per_second_zero_duration(self):
        """Test tokens per second with zero duration"""
        response = LLMResponse(
            content="Test",
            model="gpt-4",
            provider="openrouter",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost_usd=0.001,
            duration_ms=0,
        )

        assert response.tokens_per_second == 0.0


class TestTokenBudget:
    """Tests for TokenBudget model"""

    def test_token_budget_over(self):
        """Test over budget detection"""
        budget = TokenBudget(
            agent_id="test",
            limit_day=10000,
            limit_hour=1000,
            used_today=12000,
            used_hour=500,
            remaining_today=-2000,
            remaining_hour=500,
            cost_today_usd=0.5,
        )

        assert budget.is_over_budget

    def test_token_budget_alert(self):
        """Test alert threshold"""
        budget = TokenBudget(
            agent_id="test",
            limit_day=10000,
            limit_hour=1000,
            used_today=8500,
            used_hour=500,
            remaining_today=1500,
            remaining_hour=500,
            cost_today_usd=0.5,
            alert_threshold=0.8,
        )

        assert budget.should_alert


class TestSkillResult:
    """Tests for SkillResult model"""

    def test_skill_result_success(self):
        """Test successful skill result"""
        result = SkillResult(
            success=True,
            data={"output": "test"},
            duration_ms=100,
        )

        assert result.success
        assert result.error is None

    def test_skill_result_failure(self):
        """Test failed skill result"""
        result = SkillResult(
            success=False,
            error="Something went wrong",
            duration_ms=50,
        )

        assert not result.success
        assert result.data is None
