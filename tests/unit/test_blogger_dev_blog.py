"""Tests for dev-blog helpers in blogger agent."""

import pytest

from services.blogger.agent import _parse_topics_planner_json


def test_parse_topics_planner_json_minimal():
    raw = '{"topics": [{"topic_id": "x-y", "label": "Тестовая тема"}]}'
    assert _parse_topics_planner_json(raw) == [{"topic_id": "x-y", "label": "Тестовая тема"}]


def test_parse_topics_planner_json_fenced():
    raw = '```json\n{"topics": [{"topic_id": "a", "label": "B"}]}\n```'
    assert _parse_topics_planner_json(raw) == [{"topic_id": "a", "label": "B"}]


def test_parse_topics_planner_json_invalid():
    assert _parse_topics_planner_json("not json") == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
