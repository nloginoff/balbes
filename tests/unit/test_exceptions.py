"""
Unit tests for shared.exceptions module.
"""

import pytest

from shared.exceptions import (
    AgentException,
    AgentNotFoundError,
    AuthenticationError,
    BalbesException,
    ConfigException,
    LLMTokenLimitError,
    MemoryException,
    SkillNotFoundError,
    TaskException,
    TaskTimeoutError,
)


class TestExceptions:
    """Tests for custom exceptions"""

    def test_base_exception(self):
        """Test base exception with details"""
        exc = BalbesException("Test error", details={"code": 42})

        assert exc.message == "Test error"
        assert exc.details["code"] == 42
        assert str(exc) == "Test error"

    def test_agent_exception_inheritance(self):
        """Test exception hierarchy"""
        exc = AgentNotFoundError("Agent not found")

        assert isinstance(exc, AgentException)
        assert isinstance(exc, BalbesException)
        assert isinstance(exc, Exception)

    def test_exception_raising(self):
        """Test exception can be raised and caught"""
        with pytest.raises(TaskTimeoutError) as exc_info:
            raise TaskTimeoutError("Task timed out", details={"timeout": 600})

        assert "Task timed out" in str(exc_info.value)
        assert exc_info.value.details["timeout"] == 600

    def test_all_exception_types(self):
        """Test all exception types are instantiable"""
        exceptions = [
            AgentNotFoundError("test"),
            TaskException("test"),
            SkillNotFoundError("test"),
            LLMTokenLimitError("test"),
            MemoryException("test"),
            ConfigException("test"),
            AuthenticationError("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, BalbesException)
