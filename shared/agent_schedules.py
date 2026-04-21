"""
Per-agent scheduled jobs stored at data/agents/<agent_dir>/schedules.yaml.

Directory layout matches AgentWorkspace: `balbes` resolves to `orchestrator/` if
`balbes/` does not exist (legacy). API-facing agent_id for jobs in `orchestrator/`
is `balbes`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEDULE_FILENAME = "schedules.yaml"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def agents_base_dir() -> Path:
    return project_root() / "data" / "agents"


def resolve_agent_dir(agent_id: str) -> Path:
    """Workspace directory for this agent_id (same rules as AgentWorkspace)."""
    base = agents_base_dir()
    ws_dir = base / agent_id
    if agent_id == "balbes" and not ws_dir.exists():
        legacy = base / "orchestrator"
        if legacy.exists():
            ws_dir = legacy
    return ws_dir


def schedule_path_for_agent(agent_id: str) -> Path:
    return resolve_agent_dir(agent_id) / SCHEDULE_FILENAME


def api_agent_id_for_folder(folder_name: str) -> str:
    """Map directory name under data/agents/ to agent_id used in POST /api/v1/tasks."""
    if folder_name == "orchestrator":
        return "balbes"
    return folder_name


def iter_schedule_file_paths() -> list[Path]:
    """All existing data/agents/*/schedules.yaml files."""
    base = agents_base_dir()
    if not base.is_dir():
        return []
    out: list[Path] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        p = d / SCHEDULE_FILENAME
        if p.is_file():
            out.append(p)
    return out


def schedules_snapshot() -> tuple[tuple[str, int], ...]:
    """Stable fingerprint for hot-reload: (path, mtime_ns) per file."""
    snap: list[tuple[str, int]] = []
    for p in iter_schedule_file_paths():
        try:
            st = p.stat()
            snap.append((str(p.resolve()), st.st_mtime_ns))
        except OSError as e:
            logger.debug("schedules_snapshot skip %s: %s", p, e)
    return tuple(sorted(snap))


def load_yaml_path(path: Path) -> dict[str, Any]:
    import yaml

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"jobs": []}
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return {"jobs": []}


def load_all_jobs_flat() -> list[tuple[str, dict[str, Any]]]:
    """
    Load jobs from every per-agent schedules file.

    Returns (api_agent_id, job_dict) where job_dict['agent_id'] is set for the orchestrator API.
    """
    out: list[tuple[str, dict[str, Any]]] = []
    for path in iter_schedule_file_paths():
        folder = path.parent.name
        api_aid = api_agent_id_for_folder(folder)
        raw = load_yaml_path(path)
        for j in raw.get("jobs") or []:
            if not isinstance(j, dict):
                continue
            jp = dict(j)
            jp["agent_id"] = api_aid
            out.append((api_aid, jp))
    return out


def load_yaml_for_agent(agent_id: str) -> dict[str, Any]:
    import yaml

    p = schedule_path_for_agent(agent_id)
    if not p.is_file():
        return {"jobs": []}
    try:
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"jobs": []}
    except Exception as e:
        logger.error("Failed to read %s: %s", p, e)
        return {"jobs": []}


def save_yaml_for_agent(agent_id: str, data: dict[str, Any]) -> None:
    import yaml

    p = schedule_path_for_agent(agent_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
