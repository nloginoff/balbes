"""
Dashboard API endpoints.
"""

import logging
from datetime import datetime, timezone

from auth import DashboardData, SystemStatus
from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("web_backend.api.dashboard")

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/status")
async def get_system_status(user_id: str | None = None) -> SystemStatus:
    """
    Get system status overview.

    Returns:
        System status
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    services = await backend_main.api_service.check_services_health()

    return SystemStatus(
        timestamp=datetime.now(timezone.utc),
        agents_online=5,
        total_tasks=42,
        completed_tasks=38,
        failed_tasks=2,
        total_tokens_used=125000,
        memory_usage_percent=45.2,
        services=services,
    )


@router.get("/overview")
async def get_dashboard_overview(user_id: str | None = None) -> DashboardData:
    """
    Get complete dashboard overview.

    Returns:
        Dashboard data
    """
    import main as backend_main

    if not backend_main.api_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API service not initialized",
        )

    # Gather data from all services
    services = await backend_main.api_service.check_services_health()
    agents = await backend_main.api_service.get_agents()
    tasks = await backend_main.api_service.get_tasks()
    skills = await backend_main.api_service.get_skills()
    token_stats = await backend_main.api_service.get_token_stats()

    status_data = SystemStatus(
        timestamp=datetime.now(timezone.utc),
        agents_online=len([a for a in agents if a.get("status") == "online"]),
        total_tasks=len(tasks),
        services=services,
    )

    return DashboardData(
        system_status=status_data,
        recent_tasks=tasks[:10],
        agent_stats=[],
        token_usage=token_stats,
        skills_summary={
            "total": len(skills),
            "categories": {},
        },
    )
