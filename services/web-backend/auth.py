"""
Web Backend API for Balbes Multi-Agent System Dashboard.

Provides REST API endpoints for:
- User authentication
- Agent management
- Task tracking
- Skill management
- Real-time updates (WebSocket)
- System monitoring
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from shared.config import get_settings

try:
    import jwt
except ImportError:
    # Fallback if jwt not available
    jwt = None

settings = get_settings()
logger = logging.getLogger("web_backend.auth")

# Use simple hashing to avoid bcrypt version issues in tests
USE_BCRYPT = False


# ============================================================================
# Auth Models
# ============================================================================


class AuthToken(BaseModel):
    """Authentication token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class User(BaseModel):
    """User model"""

    user_id: str
    username: str
    email: str
    full_name: str | None = None
    is_active: bool = True
    created_at: datetime
    preferences: dict[str, Any] = Field(default_factory=dict)


class LoginRequest(BaseModel):
    """Login request"""

    username: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request"""

    username: str
    email: str
    password: str
    full_name: str | None = None


# ============================================================================
# Agent Models
# ============================================================================


class AgentInfo(BaseModel):
    """Agent information"""

    agent_id: str
    name: str
    status: str
    current_task_id: str | None = None
    total_tokens_used: int = 0
    tasks_completed: int = 0
    created_at: datetime


class AgentStats(BaseModel):
    """Agent statistics"""

    agent_id: str
    name: str
    status: str
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_tokens: int = 0
    avg_task_time: float = 0.0
    success_rate: float = 0.0


# ============================================================================
# Task Models
# ============================================================================


class TaskInfo(BaseModel):
    """Task information"""

    task_id: str
    agent_id: str
    description: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None


class TaskCreate(BaseModel):
    """Create task request"""

    agent_id: str
    description: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    """Update task request"""

    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


# ============================================================================
# Skill Models
# ============================================================================


class SkillInfo(BaseModel):
    """Skill information"""

    skill_id: str
    name: str
    description: str
    category: str
    version: str
    rating: float = 0.0
    usage_count: int = 0
    created_at: datetime


class SkillCreate(BaseModel):
    """Create skill request"""

    name: str
    description: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


# ============================================================================
# Dashboard Models
# ============================================================================


class SystemStatus(BaseModel):
    """System status overview"""

    timestamp: datetime
    agents_online: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_tokens_used: int = 0
    memory_usage_percent: float = 0.0
    services: dict[str, str] = Field(default_factory=dict)


class DashboardData(BaseModel):
    """Dashboard data overview"""

    system_status: SystemStatus
    recent_tasks: list[TaskInfo] = []
    agent_stats: list[AgentStats] = []
    token_usage: dict[str, Any] = {}
    skills_summary: dict[str, Any] = {}


# ============================================================================
# Authentication Helper Functions
# ============================================================================


class AuthManager:
    """Manage authentication and tokens"""

    def __init__(self):
        self.jwt_secret = settings.jwt_secret
        self.jwt_expiration = settings.jwt_expiration_hours
        self.users_db: dict[str, dict[str, Any]] = {}
        self._init_default_user()

    def _init_default_user(self) -> None:
        """Initialize default admin user"""
        admin_username = settings.web_admin_username
        admin_password = settings.web_admin_password

        # Never allow shipping prod with the known default password.
        if settings.env.lower() == "prod" and admin_password == "admin123":
            raise RuntimeError("WEB_ADMIN_PASSWORD must be changed in production")

        password_hash = hashlib.sha256(admin_password.encode()).hexdigest()

        default_user = {
            "user_id": admin_username,
            "username": admin_username,
            "email": f"{admin_username}@balbes.local",
            "full_name": "Administrator",
            "password_hash": password_hash,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }
        self.users_db[admin_username] = default_user
        logger.info("Default admin user initialized from environment")

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """Verify password"""
        try:
            # Simple comparison using SHA256
            return hashlib.sha256(plain_password.encode()).hexdigest() == password_hash
        except Exception as e:
            logger.warning(f"Password verification failed: {e}")
            return False

    def get_password_hash(self, password: str) -> str:
        """Hash password"""
        # Simple hashing using SHA256
        return hashlib.sha256(password.encode()).hexdigest()

    def create_access_token(self, user_id: str) -> AuthToken:
        """Create JWT access token"""
        import base64
        import hashlib

        expires = datetime.now(timezone.utc) + timedelta(hours=self.jwt_expiration)

        payload = {
            "user_id": user_id,
            "exp": int(expires.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

        # Simple JWT encoding without external library
        header = {"alg": "HS256", "typ": "JWT"}
        payload_str = json.dumps(payload)
        header_str = json.dumps(header)

        header_b64 = base64.urlsafe_b64encode(header_str.encode()).decode().rstrip("=")
        payload_b64 = base64.urlsafe_b64encode(payload_str.encode()).decode().rstrip("=")

        message = f"{header_b64}.{payload_b64}"

        # Sign with HMAC
        import hmac

        signature = (
            base64.urlsafe_b64encode(
                hmac.new(self.jwt_secret.encode(), message.encode(), hashlib.sha256).digest()
            )
            .decode()
            .rstrip("=")
        )

        token = f"{message}.{signature}"

        return AuthToken(
            access_token=token,
            token_type="bearer",
            expires_in=int(self.jwt_expiration * 3600),
        )

    def verify_token(self, token: str) -> str | None:
        """Verify JWT token and return user_id"""
        try:
            import base64
            import hashlib
            import hmac

            parts = token.split(".")
            if len(parts) != 3:
                logger.warning("Invalid token format")
                return None

            header_b64, payload_b64, signature = parts

            # Reconstruct message and verify signature
            message = f"{header_b64}.{payload_b64}"

            expected_signature = (
                base64.urlsafe_b64encode(
                    hmac.new(self.jwt_secret.encode(), message.encode(), hashlib.sha256).digest()
                )
                .decode()
                .rstrip("=")
            )

            if signature != expected_signature:
                logger.warning("Invalid token signature")
                return None

            # Decode payload
            padding = 4 - (len(payload_b64) % 4)
            payload_b64_padded = payload_b64 + "=" * (padding % 4)

            payload_str = base64.urlsafe_b64decode(payload_b64_padded).decode()
            payload = json.loads(payload_str)

            # Check expiration
            exp = payload.get("exp", 0)
            if exp < datetime.now(timezone.utc).timestamp():
                logger.warning("Token expired")
                return None

            return payload.get("user_id")

        except Exception as e:
            logger.warning(f"Token verification failed: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> User | None:
        """Authenticate user with username and password"""
        user = self.users_db.get(username)

        if not user:
            return None

        if not self.verify_password(password, user.get("password_hash", "")):
            return None

        return User(
            user_id=user["user_id"],
            username=user["username"],
            email=user["email"],
            full_name=user.get("full_name"),
            is_active=user.get("is_active", True),
            created_at=user["created_at"],
            preferences=user.get("preferences", {}),
        )

    def register_user(
        self, username: str, email: str, password: str, full_name: str | None = None
    ) -> User | None:
        """Register new user"""
        if username in self.users_db:
            logger.warning(f"Username already exists: {username}")
            return None

        user_id = str(uuid4())
        user_data = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name or username,
            "password_hash": self.get_password_hash(password),
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "preferences": {},
        }

        self.users_db[username] = user_data
        logger.info(f"User registered: {username}")

        return User(
            user_id=user_id,
            username=username,
            email=email,
            full_name=full_name,
            is_active=True,
            created_at=user_data["created_at"],
        )

    def get_user(self, user_id: str) -> User | None:
        """Get user by ID"""
        for user_data in self.users_db.values():
            if user_data["user_id"] == user_id:
                return User(
                    user_id=user_data["user_id"],
                    username=user_data["username"],
                    email=user_data["email"],
                    full_name=user_data.get("full_name"),
                    is_active=user_data.get("is_active", True),
                    created_at=user_data["created_at"],
                    preferences=user_data.get("preferences", {}),
                )
        return None


# ============================================================================
# API Service for External Services
# ============================================================================


class APIService:
    """Service for calling external APIs"""

    def __init__(self):
        self.http_client: httpx.AsyncClient | None = None
        self.memory_service_url = f"http://localhost:{settings.memory_service_port}"
        self.skills_registry_url = f"http://localhost:{settings.skills_registry_port}"
        self.orchestrator_url = f"http://localhost:{settings.orchestrator_port}"
        self.coder_url = f"http://localhost:{settings.coder_port}"

    async def connect(self) -> None:
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("API Service initialized")

    async def close(self) -> None:
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()

    async def get_agents(self) -> list[dict[str, Any]]:
        """Get all agents from Memory Service"""
        try:
            if not self.http_client:
                return []

            response = await self.http_client.get(f"{self.memory_service_url}/api/v1/agents")

            if response.status_code == 200:
                data = response.json()
                return data.get("agents", [])
            return []

        except Exception as e:
            logger.warning(f"Failed to get agents: {e}")
            return []

    async def get_agent_stats(self, agent_id: str) -> dict[str, Any]:
        """Get agent statistics"""
        try:
            if not self.http_client:
                return {}

            response = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/agents/{agent_id}/stats"
            )

            if response.status_code == 200:
                return response.json()
            return {}

        except Exception as e:
            logger.warning(f"Failed to get agent stats: {e}")
            return {}

    async def get_tasks(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        """Get tasks"""
        try:
            if not self.http_client:
                return []

            params = {}
            if agent_id:
                params["agent_id"] = agent_id

            response = await self.http_client.get(
                f"{self.memory_service_url}/api/v1/tasks",
                params=params,
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("tasks", [])
            return []

        except Exception as e:
            logger.warning(f"Failed to get tasks: {e}")
            return []

    async def get_skills(self) -> list[dict[str, Any]]:
        """Get skills from Skills Registry"""
        try:
            if not self.http_client:
                return []

            response = await self.http_client.get(f"{self.skills_registry_url}/api/v1/skills")

            if response.status_code == 200:
                data = response.json()
                return data.get("skills", [])
            return []

        except Exception as e:
            logger.warning(f"Failed to get skills: {e}")
            return []

    async def get_token_stats(self) -> dict[str, Any]:
        """Get token usage statistics"""
        try:
            if not self.http_client:
                return {}

            response = await self.http_client.get(f"{self.memory_service_url}/api/v1/tokens/stats")

            if response.status_code == 200:
                return response.json()
            return {}

        except Exception as e:
            logger.warning(f"Failed to get token stats: {e}")
            return {}

    async def submit_task(self, agent_id: str, description: str) -> dict[str, Any]:
        """Submit task to orchestrator"""
        try:
            if not self.http_client:
                return {}

            response = await self.http_client.post(
                f"{self.orchestrator_url}/api/v1/tasks",
                json={
                    "user_id": "web_backend",
                    "description": description,
                    "mode": "ask",
                    "source": "web_backend",
                },
            )

            if response.status_code == 200:
                return response.json()
            return {}

        except Exception as e:
            logger.warning(f"Failed to submit task: {e}")
            return {}

    async def check_services_health(self) -> dict[str, str]:
        """Check health of all services"""
        services = {
            "memory_service": self.memory_service_url,
            "skills_registry": self.skills_registry_url,
            "orchestrator": self.orchestrator_url,
            "coder": self.coder_url,
        }

        status = {}

        for name, url in services.items():
            try:
                if not self.http_client:
                    status[name] = "unavailable"
                    continue

                response = await self.http_client.get(f"{url}/health", timeout=5.0)
                status[name] = "healthy" if response.status_code == 200 else "unhealthy"

            except Exception:
                status[name] = "offline"

        return status
