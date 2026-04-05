"""
Load the full LLM + tools engine (OrchestratorAgent with agent_id=coder) for the coder service.

Requires project root and orchestrator package on sys.path (set in main before import).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

logger = logging.getLogger("coder.llm")

_ORCH_AGENT = None


def get_coding_engine():
    """Lazy singleton OrchestratorAgent(primary_agent_id='coder')."""
    global _ORCH_AGENT
    if _ORCH_AGENT is None:
        _ROOT = Path(__file__).resolve().parent.parent.parent
        _ORCH = _ROOT / "services" / "orchestrator"
        for p in (str(_ROOT), str(_ORCH)):
            if p not in sys.path:
                sys.path.insert(0, p)

        # Must load orchestrator/agent.py by path: `from agent` resolves to coder/agent.py when cwd is services/coder.
        orch_agent_path = _ORCH / "agent.py"
        spec = importlib.util.spec_from_file_location("orchestrator_runtime_agent", orch_agent_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load orchestrator agent from {orch_agent_path}")
        orch_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(orch_mod)
        OrchestratorAgent = orch_mod.OrchestratorAgent

        _ORCH_AGENT = OrchestratorAgent(primary_agent_id="coder")
        logger.info("Coder LLM engine (OrchestratorAgent) constructed for agent_id=coder")
    return _ORCH_AGENT


async def connect_coding_engine() -> None:
    eng = get_coding_engine()
    await eng.connect()
