"""MAX platform-api client helpers."""

from shared.max_api import normalize_max_access_token


def test_normalize_max_access_token_strips_bearer() -> None:
    assert normalize_max_access_token("  abc123  ") == "abc123"
    assert normalize_max_access_token("Bearer secret") == "secret"
    assert normalize_max_access_token("bearer secret") == "secret"


def test_normalize_max_access_token_empty() -> None:
    assert normalize_max_access_token("") == ""
