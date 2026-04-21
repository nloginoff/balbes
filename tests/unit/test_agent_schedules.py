"""Tests for per-agent schedule file paths and loading."""

from pathlib import Path

from shared.agent_schedules import (
    api_agent_id_for_folder,
    load_all_jobs_flat,
    project_root,
    resolve_agent_dir,
    save_yaml_for_agent,
    schedule_path_for_agent,
)


def test_project_root_is_dev_root():
    pr = project_root()
    assert (pr / "pyproject.toml").is_file() or (pr / "shared" / "agent_schedules.py").is_file()


def test_resolve_balbes_prefers_orchestrator_when_balbes_missing(monkeypatch, tmp_path: Path):
    agents = tmp_path / "data" / "agents"
    (agents / "orchestrator").mkdir(parents=True)
    monkeypatch.setattr(
        "shared.agent_schedules.agents_base_dir",
        lambda: agents,
    )
    d = resolve_agent_dir("balbes")
    assert d.name == "orchestrator"


def test_api_agent_id_for_folder():
    assert api_agent_id_for_folder("orchestrator") == "balbes"
    assert api_agent_id_for_folder("coder") == "coder"


def test_schedule_path_for_agent_uses_resolve(monkeypatch, tmp_path: Path):
    agents = tmp_path / "data" / "agents"
    (agents / "coder").mkdir(parents=True)
    monkeypatch.setattr("shared.agent_schedules.agents_base_dir", lambda: agents)
    p = schedule_path_for_agent("coder")
    assert p == agents / "coder" / "schedules.yaml"


def test_save_yaml_for_agent_triggers_memory_repo_hook(monkeypatch, tmp_path: Path):
    agents = tmp_path / "data" / "agents"
    (agents / "coder").mkdir(parents=True)
    monkeypatch.setattr("shared.agent_schedules.agents_base_dir", lambda: agents)
    calls: list[tuple[str, str, str | None]] = []

    def fake_trigger(aid: str, fn: str, workspace_root: str | None = None) -> None:
        calls.append((aid, fn, workspace_root))

    monkeypatch.setattr(
        "services.orchestrator.workspace.trigger_memory_repo_commit_for_agent",
        fake_trigger,
    )
    save_yaml_for_agent("coder", {"jobs": []})
    assert len(calls) == 1
    assert calls[0][0] == "coder"
    assert calls[0][1] == "schedules.yaml"
    assert calls[0][2] == str(agents)


def test_load_all_jobs_flat_reads_orchestrator_folder(monkeypatch, tmp_path: Path):
    agents = tmp_path / "data" / "agents" / "orchestrator"
    agents.mkdir(parents=True)
    (agents / "schedules.yaml").write_text(
        "jobs:\n"
        "  - id: test_job\n"
        "    enabled: true\n"
        "    trigger: cron\n"
        "    agent_id: balbes\n"
        "    hour: 9\n"
        "    minute: 0\n"
        "    prompt: hi\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "shared.agent_schedules.agents_base_dir", lambda: tmp_path / "data" / "agents"
    )
    flat = load_all_jobs_flat()
    assert len(flat) == 1
    aid, j = flat[0]
    assert aid == "balbes"
    assert j.get("id") == "test_job"
    assert j.get("agent_id") == "balbes"
