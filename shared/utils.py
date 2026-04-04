"""
Shared utility functions for the Balbes Multi-Agent System.

Provides common functionality used across all services.
"""

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

import tiktoken
from pydantic import BaseModel

T = TypeVar("T")


def utc_now() -> datetime:
    """
    Get current UTC datetime.

    Returns:
        datetime: Current UTC time with timezone info
    """
    return datetime.now(timezone.utc)


def to_json(obj: Any) -> str:
    """
    Convert object to JSON string with custom serialization.

    Args:
        obj: Object to serialize

    Returns:
        str: JSON string
    """

    def default(o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, BaseModel):
            return o.model_dump()
        if hasattr(o, "__dict__"):
            return o.__dict__
        return str(o)

    return json.dumps(obj, default=default, ensure_ascii=False, indent=2)


def from_json(json_str: str) -> Any:
    """
    Parse JSON string to Python object.

    Args:
        json_str: JSON string to parse

    Returns:
        Any: Parsed Python object
    """
    return json.loads(json_str)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to be safe for filesystem.

    Args:
        filename: Original filename

    Returns:
        str: Sanitized filename (alphanumeric, underscore, hyphen, dot)
    """
    filename = re.sub(r"[^\w\s\-\.]", "", filename)
    filename = re.sub(r"[\s]+", "_", filename)
    return filename.lower()


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate string to maximum length.

    Args:
        s: String to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated

    Returns:
        str: Truncated string
    """
    if len(s) <= max_length:
        return s
    return s[: max_length - len(suffix)] + suffix


def hash_string(s: str, algorithm: str = "sha256") -> str:
    """
    Hash string using specified algorithm.

    Args:
        s: String to hash
        algorithm: Hash algorithm (sha256, md5, etc)

    Returns:
        str: Hexadecimal hash
    """
    h = hashlib.new(algorithm)
    h.update(s.encode("utf-8"))
    return h.hexdigest()


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Count tokens in text for given model.

    Args:
        text: Text to count tokens for
        model: Model name to use for tokenization

    Returns:
        int: Number of tokens
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def estimate_cost(
    prompt_tokens: int, completion_tokens: int, model: str, provider: str = "openrouter"
) -> float:
    """
    Estimate cost in USD for LLM call.

    Args:
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        model: Model name
        provider: Provider name

    Returns:
        float: Estimated cost in USD

    Note:
        Uses rough estimates. Actual costs from provider response are more accurate.
    """
    rates = {
        "openrouter": {
            "claude-3.5-sonnet": (0.003, 0.015),
            "gpt-4-turbo": (0.01, 0.03),
            "gpt-3.5-turbo": (0.0005, 0.0015),
            "mixtral-8x7b": (0.0006, 0.0006),
            "gemini-pro": (0.000125, 0.000375),
        }
    }

    provider_rates = rates.get(provider, {})
    input_rate, output_rate = provider_rates.get(model, (0.001, 0.002))

    cost = (prompt_tokens / 1000) * input_rate + (completion_tokens / 1000) * output_rate
    return round(cost, 6)


def safe_dict_get(d: dict, path: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary value using dot notation.

    Args:
        d: Dictionary to search
        path: Dot-separated path (e.g., "a.b.c")
        default: Default value if path not found

    Returns:
        Any: Value at path or default

    Example:
        >>> d = {"a": {"b": {"c": 42}}}
        >>> safe_dict_get(d, "a.b.c")
        42
        >>> safe_dict_get(d, "a.b.x", "missing")
        'missing'
    """
    keys = path.split(".")
    value = d

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        str: Formatted duration (e.g., "2m 30s", "1h 15m")
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def format_tokens(tokens: int) -> str:
    """
    Format token count in human-readable format.

    Args:
        tokens: Number of tokens

    Returns:
        str: Formatted tokens (e.g., "1.2K", "15.3M")
    """
    if tokens < 1000:
        return str(tokens)
    elif tokens < 1_000_000:
        return f"{tokens / 1000:.1f}K"
    else:
        return f"{tokens / 1_000_000:.1f}M"


def ensure_dir(path: Path | str) -> Path:
    """
    Ensure directory exists, create if needed.

    Args:
        path: Directory path

    Returns:
        Path: Resolved directory path
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def is_safe_path(path: Path | str, allowed_roots: list[Path]) -> bool:
    """
    Check if path is safe (within allowed roots).

    Args:
        path: Path to check
        allowed_roots: List of allowed root directories

    Returns:
        bool: True if path is safe
    """
    path = Path(path).resolve()
    return any(
        path == root or root in path.parents for root in (Path(r).resolve() for r in allowed_roots)
    )


async def retry_async(
    func: Callable[..., Any],
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Any:
    """
    Retry async function with exponential backoff.

    Args:
        func: Async function to retry
        max_retries: Maximum number of retries
        delay: Initial delay between retries (seconds)
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch

    Returns:
        Any: Result from func

    Raises:
        Exception: Last exception if all retries fail
    """
    last_exception = None
    current_delay = delay

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries:
                await asyncio.sleep(current_delay)
                current_delay *= backoff
            else:
                raise last_exception from last_exception

    raise last_exception from last_exception


async def timeout_async(coro: Any, timeout_seconds: float) -> Any:
    """
    Execute coroutine with timeout.

    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds

    Returns:
        Any: Result from coroutine

    Raises:
        asyncio.TimeoutError: If timeout exceeded
    """
    return await asyncio.wait_for(coro, timeout=timeout_seconds)


def validate_agent_id(agent_id: str) -> bool:
    """
    Validate agent ID format.

    Args:
        agent_id: Agent ID to validate

    Returns:
        bool: True if valid
    """
    if not agent_id:
        return False

    pattern = r"^[a-z0-9_\-]+$"
    return bool(re.match(pattern, agent_id.lower()))


def validate_skill_name(skill_name: str) -> bool:
    """
    Validate skill name format.

    Args:
        skill_name: Skill name to validate

    Returns:
        bool: True if valid
    """
    if not skill_name:
        return False

    pattern = r"^[a-z0-9_]+$"
    return bool(re.match(pattern, skill_name.lower()))


def parse_telegram_command(text: str) -> tuple[str, list[str]]:
    """
    Parse Telegram command and arguments.

    Args:
        text: Message text

    Returns:
        tuple: (command, arguments)

    Example:
        >>> parse_telegram_command("/model claude-3.5-sonnet")
        ('model', ['claude-3.5-sonnet'])
    """
    if not text.startswith("/"):
        return ("", [])

    parts = text[1:].split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    args = parts[1].split() if len(parts) > 1 else []

    return (command, args)


def format_log_line(level: str, agent_id: str, message: str, **kwargs: Any) -> str:
    """
    Format log line as JSON for structured logging.

    Args:
        level: Log level (INFO, WARNING, ERROR, etc)
        agent_id: Agent ID
        message: Log message
        **kwargs: Additional fields

    Returns:
        str: JSON log line
    """
    log_data = {
        "timestamp": utc_now().isoformat(),
        "level": level.upper(),
        "agent_id": agent_id,
        "message": message,
        **kwargs,
    }
    return json.dumps(log_data, ensure_ascii=False)


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
    """
    Split text into overlapping chunks.

    Args:
        text: Text to chunk
        chunk_size: Maximum chunk size in characters
        overlap: Number of characters to overlap between chunks

    Returns:
        list[str]: List of text chunks
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap

    return chunks


def merge_dicts(base: dict, override: dict) -> dict:
    """
    Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Dictionary with override values

    Returns:
        dict: Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    """
    Extract code blocks from markdown text.

    Args:
        text: Markdown text

    Returns:
        list[tuple]: List of (language, code) tuples
    """
    pattern = r"```(\w+)?\n(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    return [(lang or "text", code.strip()) for lang, code in matches]


def get_project_root() -> Path:
    """
    Get project root directory.

    Returns:
        Path: Project root path
    """
    current = Path(__file__).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent

    return Path.cwd()


def load_yaml_safe(file_path: Path | str) -> dict[str, Any]:
    """
    Load YAML file safely.

    Args:
        file_path: Path to YAML file

    Returns:
        dict: Parsed YAML content

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid
    """
    import yaml

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e


def save_yaml_safe(data: dict[str, Any], file_path: Path | str) -> None:
    """
    Save data to YAML file safely.

    Args:
        data: Data to save
        file_path: Path to YAML file
    """
    import yaml

    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)


_providers_config_cache: dict[str, Any] = {}


def get_providers_config() -> dict[str, Any]:
    """Load and cache config/providers.yaml from the project root.

    Searches upward from this file's location to find the project root
    (directory containing config/providers.yaml). Result is cached in-process.
    """
    global _providers_config_cache
    if _providers_config_cache:
        return _providers_config_cache

    import yaml

    # Walk up from shared/ to find project root
    candidate = Path(__file__).parent
    for _ in range(4):
        cfg_path = candidate / "config" / "providers.yaml"
        if cfg_path.exists():
            try:
                with cfg_path.open(encoding="utf-8") as f:
                    _providers_config_cache = yaml.safe_load(f) or {}
            except Exception:
                _providers_config_cache = {}
            return _providers_config_cache
        candidate = candidate.parent

    return {}
