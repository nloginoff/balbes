"""
Token tracking API endpoints.
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter()


class TokenRecordRequest(BaseModel):
    """Request model for recording token usage"""

    agent_id: str = Field(..., description="Agent identifier")
    model: str = Field(..., description="Model name")
    provider: str = Field(..., description="Provider name")
    prompt_tokens: int = Field(..., ge=0, description="Prompt tokens")
    completion_tokens: int = Field(..., ge=0, description="Completion tokens")
    total_tokens: int = Field(..., ge=0, description="Total tokens")
    cost_usd: float = Field(..., ge=0, description="Cost in USD")
    task_id: UUID | None = Field(default=None, description="Related task ID")
    fallback_used: bool = Field(default=False, description="Whether fallback was used")
    cached: bool = Field(default=False, description="Whether response was cached")


@router.post("/tokens/record", status_code=status.HTTP_201_CREATED)
async def record_token_usage(
    request: TokenRecordRequest,
) -> dict[str, str]:
    """
    Record token usage.

    Args:
        request: Token usage data

    Returns:
        Usage ID
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client
    redis_client = memory_main.redis_client

    if not postgres_client or not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database clients not available",
        )

    # Record in PostgreSQL (permanent storage)
    usage_id = await postgres_client.record_token_usage(
        agent_id=request.agent_id,
        model=request.model,
        provider=request.provider,
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
        total_tokens=request.total_tokens,
        cost_usd=request.cost_usd,
        task_id=request.task_id,
        fallback_used=request.fallback_used,
        cached=request.cached,
    )

    # Update Redis counters (for fast access)
    await redis_client.increment_tokens(
        agent_id=request.agent_id,
        tokens=request.total_tokens,
        cost=request.cost_usd,
    )

    # Update agent's token counters in PostgreSQL
    token_usage = await redis_client.get_token_usage(agent_id=request.agent_id)
    await postgres_client.update_agent_tokens(
        agent_id=request.agent_id,
        tokens_today=token_usage["tokens_today"],
        tokens_hour=token_usage["tokens_hour"],
    )

    return {"usage_id": str(usage_id), "status": "recorded"}


@router.get("/tokens/stats")
async def get_token_stats(
    period: str = Query(
        default="today", description="Period: today, yesterday, this_week, this_month"
    ),
    agent_id: str | None = Query(default=None, description="Filter by agent"),
) -> dict[str, Any]:
    """
    Get token usage statistics.

    Args:
        period: Time period for stats
        agent_id: Optional agent filter

    Returns:
        Token statistics with chart data
    """
    import main as memory_main

    postgres_client = memory_main.postgres_client

    if not postgres_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PostgreSQL client not available",
        )

    if period not in ("today", "yesterday", "this_week", "this_month"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid period. Must be: today, yesterday, this_week, this_month",
        )

    stats = await postgres_client.get_token_stats(period=period, agent_id=agent_id)

    return stats


@router.get("/tokens/agent/{agent_id}")
async def get_agent_token_usage(
    agent_id: str,
) -> dict[str, Any]:
    """
    Get current token usage for agent (from Redis).

    Args:
        agent_id: Agent identifier

    Returns:
        Current token usage
    """
    import main as memory_main

    redis_client = memory_main.redis_client
    from shared.config import get_settings

    if not redis_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis client not available",
        )

    settings = get_settings()

    usage = await redis_client.get_token_usage(agent_id=agent_id)

    tokens_today = usage["tokens_today"]
    tokens_hour = usage["tokens_hour"]

    # TODO: Get limits from agent config
    limit_day = settings.default_daily_token_limit
    limit_hour = settings.default_hourly_token_limit

    return {
        "agent_id": agent_id,
        "tokens_today": tokens_today,
        "limit_day": limit_day,
        "percentage_day": round((tokens_today / limit_day) * 100, 2),
        "tokens_hour": tokens_hour,
        "limit_hour": limit_hour,
        "percentage_hour": round((tokens_hour / limit_hour) * 100, 2),
        "cost_today": usage["cost_today"],
    }
