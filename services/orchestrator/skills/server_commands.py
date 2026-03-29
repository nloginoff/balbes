"""
Server command execution skill.

Supports two modes:
  whitelist — only commands matching allowed_commands patterns are permitted
  any       — any command can be run (trusted environment only)

All executions are logged with user_id and chat_id.
Blocked patterns are always enforced regardless of mode.
"""

import asyncio
import fnmatch
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("orchestrator.skills.server_commands")


@dataclass
class CommandResult:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    blocked: bool = False
    block_reason: str = ""


# Always-blocked patterns (security hardcoded)
ALWAYS_BLOCKED = [
    r"rm\s+-rf",
    r"rm\s+-r",
    r">\(",
    r"\$\(",
    r"curl\s+.*\|\s*sh",
    r"wget\s+.*\|\s*sh",
    r";\s*rm",
    r"&&\s*rm",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\s*\{",  # fork bomb
    r"chmod\s+777",
    r"sudo\s+su",
    r"> /dev",
]


def _load_full_config() -> dict[str, Any]:
    """Load the entire providers.yaml, returning empty dict on failure."""
    try:
        import yaml

        cfg_path = Path(__file__).parent.parent.parent.parent / "config" / "providers.yaml"
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load providers.yaml: {e}")
    return {}


def _resolve_config(agent_id: str | None = None, mode: str = "agent") -> dict[str, Any]:
    """
    Return the effective server_commands config for the given agent and mode.

    In "ask" mode the per-agent "server_commands_ask" key (if present) is used
    instead of "server_commands", giving a restricted whitelist of safe commands.

    Merge order (later overrides earlier):
      1. Global  skills.server_commands
      2. Per-agent agents[id].server_commands[_ask]  (if agent_id given)
    """
    full = _load_full_config()
    global_cfg: dict[str, Any] = full.get("skills", {}).get("server_commands", {})

    if not agent_id:
        return global_cfg

    ask_key = "server_commands_ask" if mode == "ask" else "server_commands"
    for agent in full.get("agents", []):
        if agent.get("id") != agent_id:
            continue
        # Try mode-specific key first, fall back to generic server_commands
        per_agent_raw = agent.get(ask_key) or agent.get("server_commands")
        if per_agent_raw:
            merged = {**global_cfg, **dict(per_agent_raw)}
            return merged

    return global_cfg


class ServerCommandSkill:
    def __init__(self):
        # Cache is keyed by (agent_id, mode)
        self._cfg_cache: dict[tuple[str | None, str], dict[str, Any]] = {}

    def _get_config(self, agent_id: str | None = None, mode: str = "agent") -> dict[str, Any]:
        key = (agent_id, mode)
        if key not in self._cfg_cache:
            self._cfg_cache[key] = _resolve_config(agent_id, mode)
        return self._cfg_cache[key]

    def _is_always_blocked(self, command: str) -> str | None:
        """Return block reason if command matches an always-blocked pattern."""
        for pattern in ALWAYS_BLOCKED:
            if re.search(pattern, command, re.IGNORECASE):
                return f"Blocked pattern: {pattern}"
        return None

    def _is_whitelisted(self, command: str, allowed: list[str]) -> bool:
        """Check if command matches any whitelist entry (supports {param} wildcards)."""
        cmd_stripped = command.strip()
        for template in allowed:
            # Convert {param} placeholders to glob wildcards
            glob_pattern = re.sub(r"\{[^}]+\}", "*", template)
            if fnmatch.fnmatch(cmd_stripped, glob_pattern):
                return True
            # Also check if command starts with the template base
            base = glob_pattern.split("*")[0].strip()
            if base and cmd_stripped.startswith(base):
                return True
        return False

    async def execute(
        self,
        command: str,
        user_id: str = "unknown",
        chat_id: str = "unknown",
        agent_id: str | None = None,
        mode: str = "agent",
    ) -> dict[str, Any]:
        cfg = self._get_config(agent_id, mode)

        if not cfg.get("enabled", True):
            return {
                "command": command,
                "stdout": "",
                "stderr": "Server commands skill is disabled",
                "exit_code": 1,
                "blocked": True,
                "block_reason": "Skill disabled",
            }

        # Always-blocked check
        block_reason = self._is_always_blocked(command)
        if block_reason:
            logger.warning(
                f"BLOCKED command from user={user_id} chat={chat_id}: '{command}' — {block_reason}"
            )
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Command blocked: {block_reason}",
                "exit_code": 1,
                "blocked": True,
                "block_reason": block_reason,
            }

        mode = cfg.get("mode", "whitelist")
        if mode == "disabled":
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Server commands disabled for agent '{agent_id or 'global'}'",
                "exit_code": 1,
                "blocked": True,
                "block_reason": "Disabled for this agent",
            }
        if mode == "whitelist":
            allowed = cfg.get("allowed_commands", [])
            if not self._is_whitelisted(command, allowed):
                agent_label = f"agent '{agent_id}'" if agent_id else "global whitelist"
                logger.warning(
                    f"NOT WHITELISTED command from user={user_id} chat={chat_id} "
                    f"agent={agent_id}: '{command}'"
                )
                return {
                    "command": command,
                    "stdout": "",
                    "stderr": (
                        f"Command not in whitelist for {agent_label}: '{command}'\n"
                        f"Allowed: {', '.join(allowed[:15])}"
                    ),
                    "exit_code": 1,
                    "blocked": True,
                    "block_reason": "Not in whitelist",
                }

        timeout = cfg.get("timeout_seconds", 30)

        if cfg.get("log_all_calls", True):
            logger.info(f"Executing command user={user_id} chat={chat_id}: '{command}'")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                logger.warning(f"Command timed out after {timeout}s: '{command}'")
                return {
                    "command": command,
                    "stdout": "",
                    "stderr": f"Command timed out after {timeout} seconds",
                    "exit_code": 124,
                    "blocked": False,
                }

            result = {
                "command": command,
                "stdout": stdout_b.decode("utf-8", errors="replace"),
                "stderr": stderr_b.decode("utf-8", errors="replace"),
                "exit_code": proc.returncode or 0,
                "blocked": False,
            }

            logger.info(
                f"Command finished exit_code={result['exit_code']} user={user_id}: '{command}'"
            )
            return result

        except Exception as e:
            logger.error(f"Command execution error: {e}", exc_info=True)
            return {
                "command": command,
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "exit_code": 1,
                "blocked": False,
            }
