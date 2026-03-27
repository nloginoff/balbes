"""
Shared Pydantic models for the Balbes Multi-Agent System.

Defines all data models used across services for type safety and validation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class AgentStatus(str, Enum):
    """Agent status states"""

    IDLE = "idle"
    WORKING = "working"
    ERROR = "error"
    PAUSED = "paused"


class TaskStatus(str, Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    """Types of inter-agent messages"""

    TASK = "task"
    RESULT = "result"
    STATUS = "status"
    ERROR = "error"
    NOTIFICATION = "notification"


class MemoryScope(str, Enum):
    """Memory visibility scope"""

    SHARED = "shared"
    PERSONAL = "personal"


class MemoryType(str, Enum):
    """Memory storage type"""

    CONTEXT = "context"
    LONG_TERM = "long_term"


class LLMResponse(BaseModel):
    """Response from LLM provider"""

    content: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    fallback_used: bool = False
    fallback_reason: str | None = None
    duration_ms: int
    cached: bool = False

    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens per second"""
        if self.duration_ms == 0:
            return 0.0
        return (self.total_tokens / self.duration_ms) * 1000


class Agent(BaseModel):
    """Agent entity"""

    id: str
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task_id: UUID | None = None
    current_model: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_used_today: int = 0
    tokens_used_hour: int = 0

    @field_validator("id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent ID format"""
        if not v or not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Agent ID must be alphanumeric (with _ or -)")
        return v.lower()


class Task(BaseModel):
    """Task entity"""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    parent_task_id: UUID | None = None
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: dict[str, Any] | None = None
    error: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 600

    @property
    def duration_seconds(self) -> float | None:
        """Calculate task duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_timeout(self) -> bool:
        """Check if task has timed out"""
        if self.started_at and not self.completed_at:
            elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
            return elapsed > self.timeout_seconds
        return False


class Message(BaseModel):
    """Inter-agent message"""

    id: UUID = Field(default_factory=uuid4)
    from_agent: str
    to_agent: str | None = None
    type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    task_id: UUID | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_broadcast(self) -> bool:
        """Check if message is broadcast"""
        return self.to_agent is None


class Memory(BaseModel):
    """Memory entry"""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    scope: MemoryScope
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int | None = None
    tags: list[str] = Field(default_factory=list)


class ActionLog(BaseModel):
    """Log entry for agent action"""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    task_id: UUID | None = None
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: int | None = None
    success: bool = True
    error: str | None = None


class TokenUsage(BaseModel):
    """Token usage tracking"""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    task_id: UUID | None = None
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fallback_used: bool = False
    cached: bool = False


class Skill(BaseModel):
    """Skill definition"""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    implementation_path: str
    requires_confirmation: bool = False
    timeout_seconds: int = 60
    enabled: bool = True
    owner_agent: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_skill_name(cls, v: str) -> str:
        """Validate skill name format"""
        if not v or not v.replace("_", "").isalnum():
            raise ValueError("Skill name must be alphanumeric with underscores")
        return v.lower()


class SkillResult(BaseModel):
    """Result from skill execution"""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int
    logs: list[str] = Field(default_factory=list)


class LLMProviderConfig(BaseModel):
    """LLM provider configuration"""

    name: str
    api_key: str
    base_url: str
    models: list[str]
    default_model: str
    timeout: int = 120
    max_retries: int = 3
    enabled: bool = True


class AgentConfig(BaseModel):
    """Agent-specific configuration"""

    agent_id: str
    name: str
    model: str
    provider: str
    max_tokens: int = 4096
    temperature: float = 0.7
    skills: list[str] = Field(default_factory=list)
    instructions_path: str
    token_limit_day: int = 100000
    token_limit_hour: int = 10000
    auto_fallback: bool = True
    fallback_model: str | None = None


class TaskResult(BaseModel):
    """Result of task execution"""

    task_id: UUID
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_seconds: float | None = None
    tokens_used: int = 0
    retry_count: int = 0
    logs: list[str] = Field(default_factory=list)


class HealthStatus(BaseModel):
    """Health check status for services"""

    service: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy"""
        return self.status == "healthy"


class WebSocketMessage(BaseModel):
    """WebSocket message for real-time updates"""

    event: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TokenBudget(BaseModel):
    """Token budget and usage tracking"""

    agent_id: str
    limit_day: int
    limit_hour: int
    used_today: int
    used_hour: int
    remaining_today: int
    remaining_hour: int
    cost_today_usd: float
    alert_threshold: float = 0.8

    @property
    def is_over_budget(self) -> bool:
        """Check if over token budget"""
        return self.used_today >= self.limit_day or self.used_hour >= self.limit_hour

    @property
    def should_alert(self) -> bool:
        """Check if should send alert"""
        return (
            self.used_today >= self.limit_day * self.alert_threshold
            or self.used_hour >= self.limit_hour * self.alert_threshold
        )
