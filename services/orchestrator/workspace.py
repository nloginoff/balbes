"""
Agent Workspace — manages per-agent MD config files (OpenClaw-style).

Each agent has its own folder under data/agents/{agent_id}/ containing:
  AGENTS.md    — operational instructions, behaviour rules, priorities
  SOUL.md      — personality, tone, values, hard limits
  USER.md      — user profile, how to address them
  TOOLS.md     — available tools/skills reference
  MEMORY.md    — curated long-term facts (always loaded into context)
  IDENTITY.md  — agent name, role, emoji

Bootstrap files are loaded at service start and cached in memory.
The agent can read/write its own files via workspace_read / workspace_write tools.
"""

import logging
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("orchestrator.workspace")

# Module-level debounce state: repo_dir → pending Timer
# Shared across all AgentWorkspace instances so writes from different agents
# to the same repo are batched into a single push.
_push_timers: dict[str, threading.Timer] = {}
_push_lock = threading.Lock()
PUSH_DEBOUNCE_SECONDS = 30  # push fires 30s after the last write in a burst

MAX_FILE_CHARS = 20_000
MAX_TOTAL_CHARS = 150_000

# Files loaded in this order and concatenated into the system prompt
BOOTSTRAP_FILES = [
    "IDENTITY.md",
    "SOUL.md",
    "AGENTS.md",
    "USER.md",
    "TOOLS.md",
    "MEMORY.md",
    "HEARTBEAT.md",
]

# Files the agent is allowed to write to
WRITEABLE_FILES = {"AGENTS.md", "SOUL.md", "USER.md", "MEMORY.md", "IDENTITY.md", "HEARTBEAT.md"}


@dataclass
class AgentConfig:
    agent_id: str
    system_prompt: str
    files: dict[str, str] = field(default_factory=dict)  # filename → content


class AgentWorkspace:
    """
    Manages an agent's workspace directory of MD config files.

    Usage:
        ws = AgentWorkspace("orchestrator")
        ws.load()
        config = ws.config          # AgentConfig with assembled system_prompt
        ws.write_file("MEMORY.md", new_content)
    """

    def __init__(self, agent_id: str, workspace_root: str | None = None):
        self.agent_id = agent_id
        if workspace_root is None:
            # Resolve relative to project root (two levels up from this file)
            project_root = Path(__file__).parent.parent.parent
            workspace_root = str(project_root / "data" / "agents")
        self.workspace_dir = Path(workspace_root) / agent_id
        self._config: AgentConfig | None = None
        self._lock = threading.Lock()

    def load(self) -> AgentConfig:
        """
        Load all bootstrap files from workspace, assemble system prompt.
        Truncates files exceeding MAX_FILE_CHARS; total capped at MAX_TOTAL_CHARS.
        """
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        files: dict[str, str] = {}
        sections: list[str] = []
        total_chars = 0

        for filename in BOOTSTRAP_FILES:
            path = self.workspace_dir / filename
            if not path.exists():
                continue

            try:
                content = path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Failed to read {filename}: {e}")
                continue

            if not content:
                continue

            if len(content) > MAX_FILE_CHARS:
                logger.warning(
                    f"[{self.agent_id}] {filename} exceeds {MAX_FILE_CHARS} chars, truncating"
                )
                content = content[:MAX_FILE_CHARS] + "\n\n[... truncated ...]"

            if total_chars + len(content) > MAX_TOTAL_CHARS:
                logger.warning(
                    f"[{self.agent_id}] Total workspace exceeds {MAX_TOTAL_CHARS} chars, "
                    f"skipping {filename}"
                )
                break

            files[filename] = content
            sections.append(content)
            total_chars += len(content)
            logger.debug(f"[{self.agent_id}] Loaded {filename} ({len(content)} chars)")

        if sections:
            system_prompt = "\n\n---\n\n".join(sections)
        else:
            system_prompt = (
                f"You are {self.agent_id} assistant. "
                "Reply in the user's language. Be concise and practical."
            )
            logger.info(f"[{self.agent_id}] No workspace files found, using default prompt")

        config = AgentConfig(
            agent_id=self.agent_id,
            system_prompt=system_prompt,
            files=files,
        )

        with self._lock:
            self._config = config

        logger.info(
            f"[{self.agent_id}] Workspace loaded: {len(files)} files, {total_chars} total chars"
        )
        return config

    @property
    def config(self) -> AgentConfig:
        if self._config is None:
            return self.load()
        return self._config

    def reload(self) -> AgentConfig:
        """Force reload workspace from disk."""
        return self.load()

    def read_file(self, filename: str) -> str:
        """
        Read a workspace file. Returns empty string if file doesn't exist.
        Used by workspace_read tool.
        """
        filename = Path(filename).name  # strip any path traversal
        path = self.workspace_dir / filename
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to read {filename}: {e}")
            return ""

    def write_file(self, filename: str, content: str) -> bool:
        """
        Write content to a workspace file.
        Only WRITEABLE_FILES are permitted.
        Reloads workspace after write and auto-commits to memory repo.
        Used by workspace_write tool.
        """
        filename = Path(filename).name  # strip any path traversal
        if filename not in WRITEABLE_FILES:
            logger.warning(f"[{self.agent_id}] Write denied for {filename}")
            return False

        if len(content) > MAX_FILE_CHARS:
            logger.warning(f"[{self.agent_id}] Content too large for {filename}, truncating")
            content = content[:MAX_FILE_CHARS]

        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        path = self.workspace_dir / filename
        try:
            path.write_text(content, encoding="utf-8")
            logger.info(f"[{self.agent_id}] Updated {filename} ({len(content)} chars)")
            self.reload()
            self._git_auto_push(filename)
            return True
        except Exception as e:
            logger.error(f"[{self.agent_id}] Failed to write {filename}: {e}")
            return False

    def _git_auto_push(self, filename: str) -> None:
        """
        Auto-commit workspace change immediately (local, fast), then schedule
        a debounced push. If several files are written within PUSH_DEBOUNCE_SECONDS,
        they are grouped into a single push — no parallel-push conflicts.

        Silently skips if data/agents/ is not a git repository (setup not done).
        """
        repo_dir = self.workspace_dir.parent  # data/agents/

        if not (repo_dir / ".git").exists():
            logger.debug(
                f"[{self.agent_id}] No memory repo at {repo_dir}, skipping auto-commit. "
                "Run scripts/setup_memory_repo.sh to enable."
            )
            return

        def _run(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, cwd=repo_dir, capture_output=True, timeout=15)

        try:
            _run(["git", "add", "-A"])

            # Nothing staged — skip commit
            if _run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
                return

            msg = f"agent({self.agent_id}): update {filename}"
            result = _run(["git", "commit", "-m", msg])
            if result.returncode != 0:
                logger.warning(
                    f"[{self.agent_id}] git commit failed: {result.stderr.decode()[:200]}"
                )
                return

            logger.info(
                f"[{self.agent_id}] Committed {filename}; scheduling push in {PUSH_DEBOUNCE_SECONDS}s"
            )
            self._schedule_debounced_push(repo_dir)

        except subprocess.TimeoutExpired:
            logger.warning(f"[{self.agent_id}] git commit timed out")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] auto-commit failed: {e}")

    def _schedule_debounced_push(self, repo_dir: Path) -> None:
        """
        Cancel any pending push for this repo and schedule a new one.
        This batches multiple rapid writes into a single network push.
        """
        key = str(repo_dir)

        def _do_push() -> None:
            try:
                result = subprocess.run(
                    ["git", "push", "origin", "HEAD"],
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    logger.info(f"Memory repo: pushed to remote ({repo_dir.name})")
                else:
                    logger.warning(f"Memory repo: push failed: {result.stderr.decode()[:200]}")
            except Exception as e:
                logger.warning(f"Memory repo: push error: {e}")
            finally:
                with _push_lock:
                    _push_timers.pop(key, None)

        with _push_lock:
            existing = _push_timers.get(key)
            if existing:
                existing.cancel()
            timer = threading.Timer(PUSH_DEBOUNCE_SECONDS, _do_push)
            timer.daemon = True
            timer.start()
            _push_timers[key] = timer

    def list_files(self) -> list[str]:
        """Return list of existing workspace files."""
        if not self.workspace_dir.exists():
            return []
        return [f.name for f in self.workspace_dir.iterdir() if f.suffix == ".md"]
