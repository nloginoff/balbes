"""
Load the full LLM + tools engine (OrchestratorAgent with agent_id=coder) for the coder service.

Requires project root and orchestrator package on sys.path (set in main before import).
"""

from __future__ import annotations

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
        from agent import OrchestratorAgent  # noqa: WPS433 — runtime path

        _ORCH_AGENT = OrchestratorAgent(primary_agent_id="coder")
        logger.info("Coder LLM engine (OrchestratorAgent) constructed for agent_id=coder")
    return _ORCH_AGENT


async def connect_coding_engine() -> None:
    eng = get_coding_engine()
    await eng.connect()
