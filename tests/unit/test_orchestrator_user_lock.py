"""
Regression: per-user asyncio.Lock on foreground execute_task (orchestrator).

Serializes work for the same user_id (queue); heartbeat does not use this lock.
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
