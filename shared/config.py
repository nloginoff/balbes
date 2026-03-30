"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables (from .env file).
"""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Find project root (where .env file is located)
def find_project_root() -> Path:
    """Find project root by looking for .env file"""
    current = Path(__file__).parent.parent.resolve()

    # Look for .env in current directory and parents
    for path in [current] + list(current.parents):
        if (path / ".env").exists():
            return path

    # Default to current directory's parent
    return current


PROJECT_ROOT = find_project_root()


def get_env_file() -> str:
    """Get environment-specific .env file based on ENV variable"""
    import os

    env = os.getenv("ENV", "dev")
    env_file = PROJECT_ROOT / f".env.{env}"

    # Fallback to .env if environment-specific file doesn't exist
    if not env_file.exists():
        env_file = PROJECT_ROOT / ".env"

    return str(env_file)


class Settings(BaseSettings):
    # Runtime environment
    env: str = Field(default="dev", description="Runtime environment: dev/test/prod")

    """
    Global settings for Balbes Multi-Agent System.

    Loads from .env file and environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars
    )

    # =============================================================================
    # LLM Providers
    # =============================================================================
    openrouter_api_key: str | None = Field(default=None, description="OpenRouter API key")
    aitunnel_api_key: str | None = Field(default=None, description="AiTunnel API key")
    default_chat_model: str = Field(
        default="openrouter/stepfun/step-3.5-flash:free",
        description="Default model — overridden by first entry in providers.yaml active_models",
    )

    # =============================================================================
    # Telegram Bot
    # =============================================================================
    telegram_bot_token: str | None = Field(
        default=None, description="Telegram bot token from @BotFather"
    )
    telegram_user_id: int | None = Field(default=None, description="Your Telegram user ID")
    telegram_allowed_users: list[int] = Field(
        default_factory=list,
        description=(
            "Whitelist of Telegram user IDs allowed to use the bot. "
            "Set via TELEGRAM_ALLOWED_USERS env var as comma-separated IDs. "
            "Empty list = no restriction (not recommended for production)."
        ),
    )

    # =============================================================================
    # Web UI Authentication
    # =============================================================================
    web_auth_token: str = Field(..., description="Secret token for web login")
    jwt_secret: str = Field(..., description="JWT secret key")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiration")
    web_admin_username: str = Field(default="admin", description="Default web admin username")
    web_admin_password: str = Field(default="admin123", description="Default web admin password")

    # =============================================================================
    # PostgreSQL
    # =============================================================================
    postgres_host: str = Field(default="localhost")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="balbes_agents")
    postgres_user: str = Field(default="balbes")
    postgres_password: str = Field(..., description="PostgreSQL password")

    @property
    def postgres_dsn(self) -> str:
        """PostgreSQL connection string"""
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # =============================================================================
    # Redis
    # =============================================================================
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str | None = Field(default="")
    redis_db: int = Field(default=0)

    @property
    def redis_url(self) -> str:
        """Redis connection URL"""
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # =============================================================================
    # Qdrant
    # =============================================================================
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)
    qdrant_api_key: str | None = Field(default="")
    qdrant_collection: str = Field(default="agent_memory")

    # =============================================================================
    # RabbitMQ
    # =============================================================================
    rabbitmq_host: str = Field(default="localhost")
    rabbitmq_port: int = Field(default=5672)
    rabbitmq_user: str = Field(default="guest")
    rabbitmq_password: str = Field(default="guest")
    rabbitmq_vhost: str = Field(default="/")

    @property
    def rabbitmq_url(self) -> str:
        """RabbitMQ connection URL"""
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"

    # =============================================================================
    # Service Ports
    # =============================================================================
    orchestrator_port: int = Field(default=8102)
    coder_port: int = Field(default=8001)
    memory_service_port: int = Field(default=8100)
    memory_service_url: str = Field(default="http://localhost:8100")
    skills_registry_port: int = Field(default=8101)
    web_backend_port: int = Field(default=8200)
    web_frontend_port: int = Field(default=5173)

    # =============================================================================
    # Logging
    # =============================================================================
    log_level: str = Field(default="INFO", description="DEBUG, INFO, WARNING, ERROR, CRITICAL")
    log_dir: str = Field(default="./data/logs")
    log_format: str = Field(default="json", description="json or text")
    log_rotation_size: str = Field(default="100MB")
    log_retention_days: int = Field(default=7)

    # =============================================================================
    # Token Limits
    # =============================================================================
    default_daily_token_limit: int = Field(default=100000)
    default_hourly_token_limit: int = Field(default=15000)
    token_alert_threshold: float = Field(default=0.8, ge=0, le=1)

    # =============================================================================
    # Performance
    # =============================================================================
    task_timeout_seconds: int = Field(default=600, description="10 minutes")
    max_retries: int = Field(default=3)
    retry_delay_seconds: int = Field(default=1)
    connection_pool_size: int = Field(default=10)

    # =============================================================================
    # Development
    # =============================================================================
    debug: bool = Field(default=False)
    reload: bool = Field(default=False, description="Hot reload for uvicorn")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated CORS origins",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins as list"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    # =============================================================================
    # Whisper voice transcription
    # =============================================================================
    whisper_model: str = Field(default="base", description="tiny/base/small/medium/large")
    whisper_device: str = Field(default="cpu", description="cpu or cuda")
    whisper_compute_type: str = Field(default="int8", description="int8/float16/float32")
    whisper_language: str = Field(default="ru", description="Language code for transcription")

    # =============================================================================
    # Search skills
    # =============================================================================
    brave_search_key: str | None = Field(default=None, description="Brave Search API key")
    tavily_api_key: str | None = Field(default=None, description="Tavily Search API key")
    # Yandex Search API v2 (Yandex Cloud / AI Studio)
    # Key format: AQVN... — get at console.yandex.cloud → IAM → Service accounts → API keys
    yandex_search_key: str | None = Field(
        default=None, description="Yandex Search API v2 key (AQVN...)"
    )
    # Folder ID — get at console.yandex.cloud → Resource Manager → select folder → copy ID
    yandex_folder_id: str | None = Field(
        default=None, description="Yandex Cloud folder ID (b1g...)"
    )
    # Legacy XML API (no longer used — kept for env compat)
    yandex_search_user: str | None = Field(
        default=None, description="[legacy] Yandex XML Search username"
    )

    # =============================================================================
    # Optional
    # =============================================================================
    domain: str | None = Field(default=None, description="Production domain")
    ssl_enabled: bool = Field(default=False)
    ssl_cert_path: str | None = Field(default=None)
    ssl_key_path: str | None = Field(default=None)

    @field_validator(
        "openrouter_api_key",
        "aitunnel_api_key",
        "telegram_bot_token",
        "brave_search_key",
        "tavily_api_key",
        "yandex_search_key",
        "yandex_folder_id",
        "yandex_search_user",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> str | None:
        """Convert empty strings to None for optional string fields"""
        if v == "" or v is None:
            return None
        return v

    @field_validator("telegram_user_id", mode="before")
    @classmethod
    def empty_int_to_none(cls, v: Any) -> int | None:
        """Convert empty strings to None for optional int fields"""
        if v == "" or v is None:
            return None
        return int(v)

    @field_validator("telegram_allowed_users", mode="before")
    @classmethod
    def parse_allowed_users(cls, v: Any) -> list[int]:
        """Parse TELEGRAM_ALLOWED_USERS='123,456' into [123, 456]."""
        if not v or v == "":
            return []
        if isinstance(v, list):
            return [int(x) for x in v if str(x).strip()]
        return [int(x.strip()) for x in str(v).split(",") if x.strip()]


# Singleton instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Get or create settings singleton.

    Returns:
        Settings: Global settings instance
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# For convenience
settings = get_settings()


if __name__ == "__main__":
    # Test loading settings
    print("Testing settings loading...")
    print()

    try:
        s = get_settings()

        print("✅ Settings loaded successfully")
        print()
        print("Configuration:")
        print(f"  PostgreSQL: {s.postgres_host}:{s.postgres_port}/{s.postgres_db}")
        print(f"  Redis: {s.redis_host}:{s.redis_port}")
        print(f"  RabbitMQ: {s.rabbitmq_host}:{s.rabbitmq_port}")
        print(f"  Qdrant: {s.qdrant_host}:{s.qdrant_port}")
        print()
        print(f"  OpenRouter key: {s.openrouter_api_key[:10]}...")
        print(f"  Telegram bot: {s.telegram_bot_token[:10]}...")
        print(f"  Telegram user: {s.telegram_user_id}")
        print()
        print(f"  Log level: {s.log_level}")
        print(f"  Debug: {s.debug}")
        print(
            f"  Token limits: {s.default_daily_token_limit}/day, {s.default_hourly_token_limit}/hour"
        )

    except Exception as e:
        print(f"❌ Error loading settings: {e}")
        print()
        print("Make sure .env file exists and all required variables are set.")
        print("See .env.example for template.")
