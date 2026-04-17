"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables (from .env file).
"""

from pathlib import Path
from typing import Any, Literal

TelegramBotMode = Literal["polling", "webhook"]

from pydantic import AliasChoices, Field, field_validator
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
    openrouter_http_referer: str = Field(
        default="https://github.com/nloginoff/balbes",
        description="HTTP-Referer for OpenRouter app attribution (dashboard rankings)",
    )
    openrouter_app_title: str = Field(
        default="Balbes Multi Agent",
        description="X-OpenRouter-Title / X-Title for OpenRouter app attribution",
    )
    openrouter_categories: str | None = Field(
        default=None,
        description="Optional comma-separated X-OpenRouter-Categories",
    )

    # =============================================================================
    # Telegram Bot
    # =============================================================================
    telegram_secondary_bot_token: str | None = Field(
        default=None,
        description="Optional second bot token; same handlers, separate Telegram chat IDs",
    )
    telegram_mirror_replies: bool = Field(
        default=False,
        description="If true and secondary bot is set, send assistant replies to both chats",
    )
    telegram_bot_token: str | None = Field(
        default=None, description="Telegram bot token from @BotFather"
    )
    telegram_bot_mode: TelegramBotMode = Field(
        default="polling",
        description="polling = telegram_bot.py uses long polling; webhook = use webhooks-gateway",
    )
    telegram_webhook_secret: str | None = Field(
        default=None,
        description="Optional secret_token for Telegram setWebhook; verify X-Telegram-Bot-Api-Secret-Token",
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
    # Webhooks gateway (services/webhooks-gateway): Telegram, MAX, monitoring notify
    # =============================================================================
    webhooks_gateway_port: int = Field(
        default=8180,
        description="HTTP port for inbound webhooks service (not the dashboard web-backend)",
    )
    webhook_notify_api_key: str | None = Field(
        default=None,
        description=(
            "Bearer token for external monitoring (RU server). If unset, notify endpoint is disabled."
        ),
    )
    notify_delivery_channels: str = Field(
        default="telegram",
        description="Comma-separated outbound channels: telegram, max (max is optional / stub until MAX client is wired).",
    )
    notify_telegram_chat_id: int | None = Field(
        default=None,
        description=(
            "Telegram chat_id for notify messages. If unset, TELEGRAM_USER_ID is used (private chat with bot)."
        ),
    )
    notify_rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        le=10_000,
        description="Max notify POST requests per client IP per minute",
    )
    max_bot_token: str | None = Field(
        default=None,
        description="MAX messenger bot token (optional; outbound notify to MAX when channel enabled)",
    )
    max_api_url: str = Field(
        default="https://platform-api.max.ru",
        description="MAX HTTP API base URL",
    )
    notify_max_chat_id: str | None = Field(
        default=None,
        description="MAX chat_id for notify when delivery channel includes max",
    )
    max_webhook_secret: str | None = Field(
        default=None,
        description=(
            "Optional secret for inbound MAX webhooks: X-Max-Bot-Api-Secret (POST /subscriptions) "
            "or legacy X-Signature HMAC"
        ),
    )
    max_allowed_user_ids: list[int] = Field(
        default_factory=list,
        description=(
            "Whitelist of MAX user_id allowed to trigger orchestrator via webhook. "
            "Set via MAX_ALLOWED_USER_IDS as comma-separated IDs. Empty = no restriction."
        ),
    )

    # =============================================================================
    # Web UI Authentication
    # =============================================================================
    web_auth_token: str = Field(..., description="Secret token for web login")
    jwt_secret: str = Field(
        ...,
        description="JWT secret key",
        validation_alias=AliasChoices("JWT_SECRET", "JWT_SECRET_KEY"),
    )
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
    orchestrator_url: str = Field(
        default="http://127.0.0.1:8102",
        description="Base URL for orchestrator HTTP API (tasks); webhooks-gateway uses for MAX",
    )
    coder_port: int = Field(default=8001)
    coder_service_url: str | None = Field(
        default=None,
        description="Base URL for coder microservice (default http://127.0.0.1:{coder_port})",
    )
    delegation_shared_secret: str | None = Field(
        default=None,
        description=(
            "If set, POST /api/v1/agent/execute on delegate targets must send "
            "header X-Balbes-Delegation-Key with this value (inter-service trust)."
        ),
    )
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

    @property
    def notify_delivery_channels_list(self) -> list[str]:
        """Parsed NOTIFY_DELIVERY_CHANNELS — lowercase tokens: telegram, max."""
        return [x.strip().lower() for x in self.notify_delivery_channels.split(",") if x.strip()]

    @property
    def coder_base_url(self) -> str:
        """HTTP base URL for the coder microservice (used by orchestrator delegation)."""
        if self.coder_service_url:
            return self.coder_service_url.rstrip("/")
        return f"http://127.0.0.1:{self.coder_port}"

    @property
    def blogger_base_url(self) -> str:
        """HTTP base URL for the blogger microservice (delegation / tools)."""
        if self.blogger_service_url:
            return self.blogger_service_url.rstrip("/")
        return f"http://127.0.0.1:{self.blogger_service_port}"

    # =============================================================================
    # Whisper voice transcription (openai-whisper package, local inference)
    # =============================================================================
    whisper_model: str = Field(
        default="large-v3",
        description=(
            "Legacy: kept for YAML/docs compatibility. Local short voice uses whisper_local_model."
        ),
    )
    whisper_local_model: str = Field(
        default="medium",
        description="openai-whisper model for short voice (duration ≤ whisper_local_max_duration_seconds)",
    )
    whisper_local_max_duration_seconds: int = Field(
        default=30,
        ge=1,
        le=3600,
        description="Telegram voice duration (seconds) at or below this uses local Whisper; above uses cloud STT",
    )
    whisper_remote_backend: Literal["openrouter", "yandex", "openrouter_then_yandex"] = Field(
        default="openrouter_then_yandex",
        description="Cloud STT: OpenRouter multimodal audio, Yandex SpeechKit, or try OpenRouter then Yandex",
    )
    whisper_openrouter_stt_model: str = Field(
        default="google/gemini-2.0-flash-001",
        description="OpenRouter model id with audio input (see OpenRouter Models → input_modalities=audio)",
    )
    whisper_openrouter_stt_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        description="HTTP timeout for OpenRouter STT (long voice messages)",
    )
    whisper_yandex_stt_timeout_seconds: float = Field(
        default=300.0,
        ge=30.0,
        description="HTTP timeout for Yandex SpeechKit STT",
    )
    yandex_speech_api_key: str | None = Field(
        default=None,
        description="Yandex Cloud API key for SpeechKit STT (if unset, yandex_search_key may be used)",
    )
    yandex_speech_folder_id: str | None = Field(
        default=None,
        description="Yandex folder for SpeechKit (defaults to yandex_folder_id)",
    )
    whisper_device: str = Field(default="cpu", description="cpu or cuda")
    whisper_fp16: bool | None = Field(
        default=None,
        description="fp16 decode; None = True only when whisper_device is cuda (CPU uses fp32)",
    )
    whisper_beam_size: int = Field(
        default=10,
        ge=1,
        description="Beam search width (openai-whisper decode; higher = slower, often better)",
    )
    whisper_best_of: int = Field(
        default=5,
        ge=1,
        description="Number of candidates when sampling (used with beam search)",
    )
    whisper_patience: float = Field(
        default=2.0,
        ge=0.0,
        description="Beam search patience factor (higher = slower, can improve quality)",
    )
    whisper_language: str | None = Field(
        default="ru",
        description="Language code (e.g. ru) or null/empty for auto-detect",
    )
    whisper_correction_fallback_model: str = Field(
        default="openrouter/minimax/minimax-m2.5",
        description=(
            "OpenRouter model id for transcription LLM correction when chat model is unset "
            "or fails (use a small paid model, not :free)"
        ),
    )
    whisper_correction_timeout_seconds: float = Field(
        default=120.0,
        ge=15.0,
        description="HTTP timeout (seconds) per OpenRouter correction attempt",
    )

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
    # Blogger service
    # =============================================================================
    blogger_service_port: int = Field(default=8105)
    blogger_service_url: str | None = Field(
        default=None,
        description="Base URL for blogger microservice (default http://127.0.0.1:{blogger_service_port})",
    )
    business_bot_token: str | None = Field(
        default=None, description="Telegram bot token for silent business chat watcher + check-in"
    )
    blogger_channel_ru: str | None = Field(
        default=None, description="Telegram channel ID for RU posts"
    )
    blogger_channel_en: str | None = Field(
        default=None, description="Telegram channel ID for EN posts"
    )
    blogger_channel_personal: str | None = Field(
        default=None, description="Telegram channel ID for personal blog posts"
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
        "telegram_secondary_bot_token",
        "business_bot_token",
        "webhook_notify_api_key",
        "max_bot_token",
        "notify_max_chat_id",
        "telegram_webhook_secret",
        "max_webhook_secret",
        "blogger_channel_ru",
        "blogger_channel_en",
        "blogger_channel_personal",
        "brave_search_key",
        "tavily_api_key",
        "yandex_search_key",
        "yandex_folder_id",
        "yandex_search_user",
        "yandex_speech_api_key",
        "yandex_speech_folder_id",
        "whisper_language",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, v: Any) -> str | None:
        """Convert empty strings to None for optional string fields"""
        if v == "" or v is None:
            return None
        return v

    @field_validator("telegram_user_id", "notify_telegram_chat_id", mode="before")
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

    @field_validator("max_allowed_user_ids", mode="before")
    @classmethod
    def parse_max_allowed_user_ids(cls, v: Any) -> list[int]:
        """Parse MAX_ALLOWED_USER_IDS='123,456' into [123, 456]."""
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
