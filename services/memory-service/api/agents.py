"""
Agents API endpoints (PostgreSQL-backed agent state).
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from shared.models import AgentStatus

router = APIRouter()


class AgentCreateRequest(BaseModel):
    """Request model for creating agent"""

    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")
    current_model: str = Field(..., description="Current LLM model")
    config: dict[str, Any] = Field(default_factory=dict, description="Agent config")


class AgentStatusUpdateRequest(BaseModel):
    """Request model for updating agent status"""

    status: AgentStatus = Field(..., description="New status")
    current_task_id: UUID | None = Field(default=None, description="Current task ID")


@router.get("/agents")
async def get_all_agents() -> dict[str, Any]:
    """
    Get all agents.

    Returns:
        List of agents
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    agents = await postgres_client.get_all_agents()

    return {"agents": agents}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
) -> dict[str, Any]:
    """
    Get agent by ID.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent data

    Raises:
        404: If agent not found
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    agent = await postgres_client.get_agent(agent_id=agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    return agent


@router.post("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: AgentCreateRequest,
) -> dict[str, Any]:
    """
    Create new agent.

    Args:
        request: Agent data

    Returns:
        Created agent
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    agent = await postgres_client.create_agent(
        agent_id=request.agent_id,
        name=request.name,
        current_model=request.current_model,
        config=request.config,
    )

    return agent


@router.patch("/agents/{agent_id}/status")
async def update_agent_status(
    agent_id: str,
    request: AgentStatusUpdateRequest,
) -> dict[str, str]:
    """
    Update agent status.

    Args:
        agent_id: Agent identifier
        request: Status update

    Returns:
        Status
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    await postgres_client.update_agent_status(
        agent_id=agent_id,
        status=request.status,
        current_task_id=request.current_task_id,
    )

    return {"status": "updated"}


@router.get("/agents/{agent_id}/status")
async def get_agent_status(
    agent_id: str,
) -> dict[str, Any]:
    """
    Get detailed agent status including current task and tokens.

    Args:
        agent_id: Agent identifier

    Returns:
        Agent status with details
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client
    redis_client = memory_main.redis_client

    if not postgres_client or not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database clients not available",
        )

    # Get agent from PostgreSQL
    agent = await postgres_client.get_agent(agent_id=agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    # Get current task if any
    current_task = None
    if agent["current_task_id"]:
        task = await postgres_client.get_task(agent["current_task_id"])
        if task:
            current_task = {
                "id": str(task["id"]),
                "description": task["description"],
                "started_at": task["started_at"].isoformat() if task["started_at"] else None,
                "progress": task.get("payload", {}).get("progress", "In progress..."),
            }

    # Get token usage from Redis
    token_usage = await redis_client.get_token_usage(agent_id=agent_id)

    # TODO: Get token limits from agent config
    # For now, use defaults from settings
    from shared.config import get_settings

    settings = get_settings()

    token_limit_day = settings.default_daily_token_limit
    token_limit_hour = settings.default_hourly_token_limit

    tokens_today = token_usage.get("tokens_today", 0)
    tokens_hour = token_usage.get("tokens_hour", 0)

    return {
        "agent_id": agent["agent_id"],
        "name": agent["name"],
        "status": agent["status"],
        "current_task": current_task,
        "tokens": {
            "today": tokens_today,
            "today_limit": token_limit_day,
            "hour": tokens_hour,
            "hour_limit": token_limit_hour,
            "percentage_used": round((tokens_today / token_limit_day) * 100, 2),
        },
        "last_activity": agent["last_activity"].isoformat(),
    }
