"""
Shared contract for inter-agent delegation: POST /api/v1/agent/execute.

Used by orchestrator (client), coder, blogger, and any future agent service.
"""

from __future__ import annotations

import secrets
from typing import Annotated, Any

from fastapi import Header, HTTPException, status
from pydantic import BaseModel, Field

# Header name for optional shared secret (must match across services).
DELEGATION_HEADER = "X-Balbes-Delegation-Key"

EXECUTE_PATH = "/api/v1/agent/execute"


class AgentExecuteRequest(BaseModel):
    """Request body for agent task execution (delegation)."""

    task: str = Field(..., min_length=1)
    user_id: str = "unknown"
    chat_id: str = "default"
    model_id: str | None = None
    mode: str = "agent"
    trace_id: str | None = None
    debug: bool = False


class AgentExecuteSuccess(BaseModel):
    """Successful execute response."""

    status: str = "success"
    output: str = ""
    task_id: str | None = None
    model_used: str | None = None
    debug_events: list[dict[str, Any]] | None = None
    chat_id: str | None = None


class AgentExecuteFailure(BaseModel):
    """Failed execute response."""

    status: str = "failed"
    error: str = ""
    task_id: str | None = None


def delegation_headers(secret: str | None) -> dict[str, str]:
    """Headers to attach when calling another agent's execute endpoint."""
    if not secret:
        return {}
    return {DELEGATION_HEADER: secret}


def verify_delegation_key(
    expected_secret: str | None,
    header_value: str | None = None,
) -> None:
    """
    If expected_secret is set, require a matching header (constant-time compare).
    If expected_secret is None, accept any request (local dev).
    """
    if not expected_secret:
        return
    if not header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing delegation key",
        )
    if not secrets.compare_digest(header_value.strip(), expected_secret.strip()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid delegation key",
        )


async def verify_delegation_optional(
    x_balbes_delegation_key: Annotated[str | None, Header(alias=DELEGATION_HEADER)] = None,
) -> None:
    """FastAPI Depends(): enforces delegation key when DELEGATION_SHARED_SECRET is set."""
    from shared.config import get_settings

    verify_delegation_key(get_settings().delegation_shared_secret, x_balbes_delegation_key)
