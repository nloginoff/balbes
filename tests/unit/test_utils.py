"""
Unit tests for shared.utils module.
"""

from datetime import UTC, datetime

from shared.utils import (
    chunk_text,
    count_tokens,
    format_duration,
    format_tokens,
    hash_string,
    merge_dicts,
    parse_telegram_command,
    safe_dict_get,
    sanitize_filename,
    truncate_string,
    utc_now,
    validate_agent_id,
    validate_skill_name,
)


class TestUtilityFunctions:
    """Tests for utility functions"""

    def test_utc_now(self):
        """Test UTC timestamp generation"""
        now = utc_now()
        assert isinstance(now, datetime)
        assert now.tzinfo == UTC

    def test_sanitize_filename(self):
        """Test filename sanitization"""
        assert sanitize_filename("Test File!.txt") == "test_file.txt"
        assert sanitize_filename("file/with\\slashes") == "filewithslashes"
        assert sanitize_filename("file  with   spaces") == "file_with_spaces"

    def test_truncate_string(self):
        """Test string truncation"""
        long_text = "a" * 200
        truncated = truncate_string(long_text, max_length=50)

        assert len(truncated) == 50
        assert truncated.endswith("...")

    def test_truncate_string_short(self):
        """Test truncation of short string"""
        short_text = "short"
        truncated = truncate_string(short_text, max_length=50)

        assert truncated == short_text

    def test_hash_string(self):
        """Test string hashing"""
        text = "test"
        hash1 = hash_string(text)
        hash2 = hash_string(text)

        assert hash1 == hash2
        assert len(hash1) == 64

    def test_count_tokens(self):
        """Test token counting"""
        text = "Hello, world! This is a test."
        tokens = count_tokens(text)

        assert tokens > 0
        assert tokens < 20

    def test_format_duration(self):
        """Test duration formatting"""
        assert format_duration(30) == "30.0s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3660) == "1h 1m"

    def test_format_tokens(self):
        """Test token formatting"""
        assert format_tokens(500) == "500"
        assert format_tokens(5000) == "5.0K"
        assert format_tokens(5_000_000) == "5.0M"

    def test_safe_dict_get(self):
        """Test safe nested dictionary access"""
        data = {"a": {"b": {"c": 42}}}

        assert safe_dict_get(data, "a.b.c") == 42
        assert safe_dict_get(data, "a.b.x", "default") == "default"
        assert safe_dict_get(data, "x.y.z", None) is None

    def test_parse_telegram_command(self):
        """Test Telegram command parsing"""
        cmd, args = parse_telegram_command("/model claude-3.5-sonnet")
        assert cmd == "model"
        assert args == ["claude-3.5-sonnet"]

        cmd, args = parse_telegram_command("/status")
        assert cmd == "status"
        assert args == []

        cmd, args = parse_telegram_command("Not a command")
        assert cmd == ""
        assert args == []

    def test_chunk_text(self):
        """Test text chunking"""
        text = "a" * 2500
        chunks = chunk_text(text, chunk_size=1000, overlap=100)

        assert len(chunks) == 3
        assert len(chunks[0]) == 1000
        assert chunks[0][-50:] == chunks[1][:50]

    def test_merge_dicts(self):
        """Test deep dictionary merging"""
        base = {"a": {"b": 1, "c": 2}, "d": 3}
        override = {"a": {"b": 10, "e": 4}, "f": 5}

        result = merge_dicts(base, override)

        assert result["a"]["b"] == 10
        assert result["a"]["c"] == 2
        assert result["a"]["e"] == 4
        assert result["d"] == 3
        assert result["f"] == 5

    def test_validate_agent_id(self):
        """Test agent ID validation"""
        assert validate_agent_id("test_agent")
        assert validate_agent_id("agent-1")
        assert validate_agent_id("agent123")
        assert not validate_agent_id("Invalid Agent!")
        assert not validate_agent_id("")

    def test_validate_skill_name(self):
        """Test skill name validation"""
        assert validate_skill_name("web_search")
        assert validate_skill_name("file_ops")
        assert not validate_skill_name("invalid-skill")
        assert not validate_skill_name("Invalid Skill!")
        assert not validate_skill_name("")
