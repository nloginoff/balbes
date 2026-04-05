"""
Base agent types and feature flags loaded from providers.yaml.

New agents inherit from BaseAgent and opt in via `features` under their agent entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AgentFeatures:
    """Toggle core behaviors; all default True for backward compatibility."""

    chats: bool = True
    model_switch: bool = True
    trace: bool = True
    debug: bool = True
    tasks_registry: bool = True
    heartbeat: bool = True
    delegation: bool = True


def load_agent_features(agent_id: str, providers_config: dict[str, Any] | None) -> AgentFeatures:
    """Read optional `features:` block from the matching agents[] entry."""
    if not providers_config:
        return AgentFeatures()
    for a in providers_config.get("agents", []) or []:
        if a.get("id") == agent_id:
            f = a.get("features") or {}
            return AgentFeatures(
                chats=bool(f.get("chats", True)),
                model_switch=bool(f.get("model_switch", True)),
                trace=bool(f.get("trace", True)),
                debug=bool(f.get("debug", True)),
                tasks_registry=bool(f.get("tasks_registry", True)),
                heartbeat=bool(f.get("heartbeat", True)),
                delegation=bool(f.get("delegation", True)),
            )
    return AgentFeatures()


class BaseAgent:
    """Minimal base: stable id + feature flags. Services add HTTP, tools, Telegram."""

    def __init__(self, agent_id: str, providers_config: dict[str, Any] | None = None) -> None:
        self.agent_id = agent_id
        self.features = load_agent_features(agent_id, providers_config)
