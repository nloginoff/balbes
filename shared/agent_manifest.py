"""
Load per-agent manifests from config/agents/*.yaml (git-safe, no secrets).

Merges with providers.yaml: manifest overrides tools/skills allowlists and adds delegate_targets.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_MANIFEST_CACHE: dict[str, Any] | None = None


def _project_root() -> Path:
    p = Path(__file__).parent
    for _ in range(5):
        if (p / "config").is_dir():
            return p
        p = p.parent
    return Path(__file__).parent.parent


def manifest_dir() -> Path:
    return _project_root() / "config" / "agents"


@dataclass
class DelegateTarget:
    """HTTP endpoint for delegate_to_agent(agent_id)."""

    agent_id: str
    base_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))


@dataclass
class TelegramFeatureFlags:
    """
    Per-agent Telegram UI capabilities (git-safe YAML `telegram:` block).
    All default True — set a key to false to disable for this agent only.
    """

    voice: bool = True
    commands_menu: bool = True
    # Orchestrator (balbes)
    model_switch: bool = True
    multi_chat: bool = True
    memory_commands: bool = True
    agents_switch: bool = True
    heartbeat_cmd: bool = True
    debug_command: bool = True
    mode_command: bool = True
    tasks_command: bool = True
    stop_command: bool = True
    status_command: bool = True
    link_command: bool = True
    blog_callbacks: bool = True
    join_request_auto: bool = True
    clear_command: bool = True
    help_command: bool = True
    start_command: bool = True
    # Blogger service (business bot)
    posts_commands: bool = True
    business_groups: bool = True
    business_group_capture: bool = True
    private_conversation: bool = True
    register_business_chat: bool = True
    voice_transcription_preview: bool = True


def _merge_telegram_flags(raw: dict[str, Any] | None) -> TelegramFeatureFlags:
    base = TelegramFeatureFlags()
    if not raw or not isinstance(raw, dict):
        return base
    overrides: dict[str, bool] = {}
    for name in base.__dataclass_fields__:
        if name in raw:
            overrides[name] = bool(raw[name])
    return dataclasses.replace(base, **overrides) if overrides else base


@dataclass
class AgentManifest:
    """Effective manifest for one agent after merge."""

    agent_id: str
    tools_allowlist_by_mode: dict[str, set[str] | None] = field(
        default_factory=lambda: {"ask": None, "agent": None, "dev": None}
    )
    skills_allowlist_by_mode: dict[str, set[str] | None] = field(
        default_factory=lambda: {"ask": None, "agent": None, "dev": None}
    )
    delegate_targets: dict[str, DelegateTarget] = field(default_factory=dict)
    telegram: TelegramFeatureFlags = field(default_factory=TelegramFeatureFlags)


def _load_yaml_files() -> dict[str, dict[str, Any]]:
    """agent_id -> raw dict from file."""
    out: dict[str, dict[str, Any]] = {}
    d = manifest_dir()
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.yaml")):
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                continue
            aid = str(data.get("id") or path.stem)
            out[aid] = data
        except Exception:
            continue
    return out


def load_agent_manifests_raw() -> dict[str, dict[str, Any]]:
    """Cached raw manifests keyed by agent id."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        _MANIFEST_CACHE = _load_yaml_files()
    return _MANIFEST_CACHE


def clear_manifest_cache() -> None:
    global _MANIFEST_CACHE
    _MANIFEST_CACHE = None


def _parse_mode_allowlist(block: Any) -> set[str] | None:
    if block is None:
        return None
    if not isinstance(block, list):
        return None
    return {str(x) for x in block}


def get_agent_manifest(agent_id: str) -> AgentManifest:
    """Build AgentManifest for agent_id (defaults if no file)."""
    raw_all = load_agent_manifests_raw()
    raw = raw_all.get(agent_id, {})

    tools_by_mode: dict[str, set[str] | None] = {"ask": None, "agent": None, "dev": None}
    skills_by_mode: dict[str, set[str] | None] = {"ask": None, "agent": None, "dev": None}

    t = raw.get("tools") or {}
    if isinstance(t, dict):
        for mode in ("ask", "agent", "dev"):
            if mode in t:
                tools_by_mode[mode] = _parse_mode_allowlist(t.get(mode))

    s = raw.get("skills") or {}
    if isinstance(s, dict):
        for mode in ("ask", "agent", "dev"):
            if mode in s:
                skills_by_mode[mode] = _parse_mode_allowlist(s.get(mode))

    # Shorthand: top-level tools_allowlist applies to all modes
    if raw.get("tools_allowlist") is not None and isinstance(raw.get("tools_allowlist"), list):
        al = _parse_mode_allowlist(raw.get("tools_allowlist"))
        for mode in ("ask", "agent", "dev"):
            if tools_by_mode[mode] is None:
                tools_by_mode[mode] = al

    delegates: dict[str, DelegateTarget] = {}
    dt = raw.get("delegate_targets") or {}
    if isinstance(dt, dict):
        for aid, spec in dt.items():
            if isinstance(spec, str):
                delegates[str(aid)] = DelegateTarget(str(aid), spec)
            elif isinstance(spec, dict):
                bu = spec.get("base_url") or spec.get("url")
                if bu:
                    delegates[str(aid)] = DelegateTarget(str(aid), str(bu))

    tg_raw = raw.get("telegram")
    telegram = _merge_telegram_flags(tg_raw if isinstance(tg_raw, dict) else None)

    return AgentManifest(
        agent_id=agent_id,
        tools_allowlist_by_mode=tools_by_mode,
        skills_allowlist_by_mode=skills_by_mode,
        delegate_targets=delegates,
        telegram=telegram,
    )


def get_delegate_targets() -> dict[str, DelegateTarget]:
    """Delegate targets from config/agents/balbes.yaml or orchestrator.yaml."""
    for key in ("balbes", "orchestrator"):
        m = get_agent_manifest(key)
        if m.delegate_targets:
            return dict(m.delegate_targets)
    return {}


def get_delegate_base_url(agent_id: str) -> str | None:
    """
    Resolve HTTP base URL for delegate_to_agent(agent_id).
    Manifest overrides defaults; coder/blogger fall back to Settings.
    """
    from shared.config import get_settings

    targets = get_delegate_targets()
    if agent_id in targets:
        return targets[agent_id].base_url
    s = get_settings()
    if agent_id == "coder":
        return s.coder_base_url
    if agent_id == "blogger":
        return s.blogger_base_url
    return None


def resolve_tools_for_agent_with_manifest(
    agent_id: str,
    mode: str,
    providers_config: dict[str, Any] | None,
    full_catalog: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Apply providers.yaml allowlist, then optional per-mode manifest allowlist."""
    from shared.agent_tools.registry import filter_tools_by_allowlist, resolve_tools_for_agent

    base = resolve_tools_for_agent(agent_id, providers_config, full_catalog)
    man = get_agent_manifest(agent_id)
    allow = man.tools_allowlist_by_mode.get(mode)
    if allow is None:
        allow = man.tools_allowlist_by_mode.get("agent")
    if allow is not None:
        return filter_tools_by_allowlist(base, allow)
    return base
