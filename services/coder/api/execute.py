"""HTTP endpoint: full coder task (LLM + tools) for orchestrator delegation."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("coder.api.execute")

router = APIRouter(tags=["agent"])


class ExecuteRequest(BaseModel):
    task: str = Field(..., min_length=1)
    user_id: str = "unknown"
    chat_id: str = "default"
    model_id: str | None = None
    mode: str = "agent"
    trace_id: str | None = None
    debug: bool = False


@router.post("/api/v1/agent/execute")
async def agent_execute(request: Request, body: ExecuteRequest) -> dict[str, Any]:
    engine = getattr(request.app.state, "coding_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Coder LLM engine not initialized")

    ctx: dict[str, Any] = {"source": "delegate", "debug": body.debug, "mode": body.mode}
    try:
        result = await engine.execute_task(
            description=body.task,
            user_id=body.user_id,
            chat_id=body.chat_id,
            agent_id="coder",
            model_id=body.model_id,
            context=ctx,
        )
    except Exception as e:
        logger.exception("execute_task failed")
        raise HTTPException(status_code=500, detail=str(e)) from e

    if result.get("status") == "success":
        inner = result.get("result") or {}
        return {
            "status": "success",
            "output": inner.get("output", ""),
            "task_id": result.get("task_id"),
            "model_used": result.get("model_used"),
            "debug_events": result.get("debug_events"),
            "chat_id": result.get("chat_id"),
        }

    return {
        "status": "failed",
        "error": result.get("error", "unknown error"),
        "task_id": result.get("task_id"),
    }
