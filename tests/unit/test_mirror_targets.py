"""Unit tests for agent reply mirror target allowlist (no network)."""

from __future__ import annotations

from types import SimpleNamespace

from shared.outbound.mirror import mirror_target_providers


def test_mirror_target_providers_default() -> None:
    ns = SimpleNamespace(agent_reply_mirror_providers="telegram,max")
    assert mirror_target_providers(ns) == frozenset({"telegram", "max"})


def test_mirror_target_providers_empty_means_nowhere() -> None:
    ns = SimpleNamespace(agent_reply_mirror_providers="")
    assert mirror_target_providers(ns) == frozenset()


def test_mirror_target_providers_whitespace_trimmed() -> None:
    ns = SimpleNamespace(agent_reply_mirror_providers=" Telegram , MAX ")
    assert mirror_target_providers(ns) == frozenset({"telegram", "max"})


def test_mirror_target_providers_single_channel() -> None:
    ns = SimpleNamespace(agent_reply_mirror_providers="max")
    assert mirror_target_providers(ns) == frozenset({"max"})
