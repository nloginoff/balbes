"""HTTP delegation: POST /api/v1/agent/execute for orchestrator -> blogger."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from shared.agent_execute_contract import (
    AgentExecuteRequest,
    verify_delegation_optional,
)

logger = logging.getLogger("blogger.api.execute")

router = APIRouter(tags=["agent"])


@router.post("/api/v1/agent/execute", dependencies=[Depends(verify_delegation_optional)])
async def agent_execute(request: Request, body: AgentExecuteRequest) -> dict[str, Any]:
    agent = getattr(request.app.state, "blogger_agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Blogger agent not initialized")

    try:
        text = await agent.execute_delegate_task(body.task, user_id=body.user_id)
    except Exception as e:
        logger.exception("blogger execute_delegate_task failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "status": "success",
        "output": text,
        "task_id": None,
        "model_used": getattr(agent, "model", None),
        "debug_events": None,
        "chat_id": body.chat_id,
    }
