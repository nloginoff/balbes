"""
Regression: one foreground task per user_id (orchestrator).

Parallel POST /api/v1/tasks for the same user used to share one ToolDispatcher and
left multiple tasks stuck in *running*; a non-blocking per-user lock rejects duplicates.
"""

import asyncio

import pytest

from services.orchestrator.agent import OrchestratorAgent


@pytest.mark.asyncio
async def test_user_execute_lock_blocks_second_acquirer():
    """asyncio.wait_for(.acquire(), 0) fails when the lock is already held."""
    agent = OrchestratorAgent()
    lock = agent._lock_for_user("u-test-lock")
    await lock.acquire()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(lock.acquire(), 0.0)
    lock.release()
