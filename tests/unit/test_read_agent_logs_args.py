"""read_agent_logs argument normalization (LLM / MAX quirks)."""

from shared.agent_tools.registry import normalize_read_agent_logs_args


def test_normalize_null_like_strings() -> None:
    n = normalize_read_agent_logs_args(
        {
            "date": "2026-04-17",
            "start_date": "null",
            "end_date": "",
            "tool_filter": "null",
            "limit": "null",
        }
    )
    assert n["date"] == "2026-04-17"
    assert n["start_date"] is None
    assert n["end_date"] is None
    assert n["tool_filter"] is None
    assert n["limit"] == 50


def test_normalize_limit_string() -> None:
    n = normalize_read_agent_logs_args({"limit": "10"})
    assert n["limit"] == 10


def test_normalize_omit_tool_filter() -> None:
    n = normalize_read_agent_logs_args({"date": "today"})
    assert n["tool_filter"] is None
    assert n["date"] == "today"
