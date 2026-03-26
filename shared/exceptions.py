"""
Custom exceptions for the Balbes Multi-Agent System.

Provides specific exception types for better error handling across all services.
"""


class BalbesException(Exception):
    """Base exception for all Balbes errors"""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class AgentException(BalbesException):
    """Base exception for agent-related errors"""

    pass


class AgentNotFoundError(AgentException):
    """Agent with given ID does not exist"""

    pass


class AgentBusyError(AgentException):
    """Agent is currently busy with another task"""

    pass


class AgentConfigError(AgentException):
    """Agent configuration is invalid"""

    pass


class TaskException(BalbesException):
    """Base exception for task-related errors"""

    pass


class TaskNotFoundError(TaskException):
    """Task with given ID does not exist"""

    pass


class TaskTimeoutError(TaskException):
    """Task execution exceeded timeout"""

    pass


class TaskValidationError(TaskException):
    """Task data is invalid"""

    pass


class SkillException(BalbesException):
    """Base exception for skill-related errors"""

    pass


class SkillNotFoundError(SkillException):
    """Skill with given name does not exist"""

    pass


class SkillExecutionError(SkillException):
    """Skill execution failed"""

    pass


class SkillValidationError(SkillException):
    """Skill definition or parameters are invalid"""

    pass


class SkillTimeoutError(SkillException):
    """Skill execution exceeded timeout"""

    pass


class MemoryException(BalbesException):
    """Base exception for memory-related errors"""

    pass


class MemoryStorageError(MemoryException):
    """Failed to store memory"""

    pass


class MemoryRetrievalError(MemoryException):
    """Failed to retrieve memory"""

    pass


class MemorySearchError(MemoryException):
    """Failed to search in memory"""

    pass


class LLMException(BalbesException):
    """Base exception for LLM-related errors"""

    pass


class LLMProviderError(LLMException):
    """LLM provider returned an error"""

    pass


class LLMTimeoutError(LLMException):
    """LLM request timed out"""

    pass


class LLMTokenLimitError(LLMException):
    """Token limit exceeded"""

    pass


class LLMRateLimitError(LLMException):
    """Rate limit exceeded"""

    pass


class LLMAuthenticationError(LLMException):
    """LLM provider authentication failed"""

    pass


class LLMModelNotFoundError(LLMException):
    """Requested model not available"""

    pass


class MessageBusException(BalbesException):
    """Base exception for message bus errors"""

    pass


class MessagePublishError(MessageBusException):
    """Failed to publish message to bus"""

    pass


class MessageConsumeError(MessageBusException):
    """Failed to consume message from bus"""

    pass


class MessageBusConnectionError(MessageBusException):
    """Failed to connect to message bus"""

    pass


class DatabaseException(BalbesException):
    """Base exception for database errors"""

    pass


class DatabaseConnectionError(DatabaseException):
    """Failed to connect to database"""

    pass


class DatabaseQueryError(DatabaseException):
    """Database query failed"""

    pass


class DatabaseConstraintError(DatabaseException):
    """Database constraint violation"""

    pass


class ConfigException(BalbesException):
    """Base exception for configuration errors"""

    pass


class ConfigValidationError(ConfigException):
    """Configuration validation failed"""

    pass


class ConfigLoadError(ConfigException):
    """Failed to load configuration"""

    pass


class SecurityException(BalbesException):
    """Base exception for security-related errors"""

    pass


class AuthenticationError(SecurityException):
    """Authentication failed"""

    pass


class AuthorizationError(SecurityException):
    """Authorization failed (insufficient permissions)"""

    pass


class ValidationException(BalbesException):
    """Base exception for validation errors"""

    pass


class InvalidInputError(ValidationException):
    """Input data is invalid"""

    pass


class InvalidStateError(ValidationException):
    """System or agent is in invalid state for requested operation"""

    pass
