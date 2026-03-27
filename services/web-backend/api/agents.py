"""
Agents API endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("web_backend.api.agents")

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.get("")
async def get_agents(user_id: str | None = None) -> dict:
    """
    Get all agents.

    Returns:
        List of agents
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    agents = await backend_main.api_service.get_agents()

    return {
        "total": len(agents),
        "agents": agents,
    }


@router.get("/{agent_id}")
async def get_agent_details(agent_id: str, user_id: str | None = None) -> dict:
    """
    Get agent details and statistics.

    Args:
        agent_id: Agent ID

    Returns:
        Agent details with stats
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    stats = await backend_main.api_service.get_agent_stats(agent_id)

    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    return stats
