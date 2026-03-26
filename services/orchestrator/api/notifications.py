"""
Notification API endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger("orchestrator.api.notifications")

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/history")
async def get_notification_history(
    user_id: str,
    limit: int = 10,
) -> dict:
    """
    Get notification history for user.

    Args:
        user_id: User ID
        limit: Max notifications to return

    Returns:
        List of notifications
    """
    import main as orchestrator_main

    if not orchestrator_main.notification_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service not initialized",
        )

    notifications = await orchestrator_main.notification_service.get_notification_history(
        user_id=user_id,
        limit=limit,
    )

    return {
        "user_id": user_id,
        "total": len(notifications),
        "notifications": notifications,
    }


@router.put("/{notification_id}/read")
async def mark_as_read(notification_id: str) -> dict:
    """
    Mark notification as read.

    Args:
        notification_id: Notification ID

    Returns:
        Success status
    """
    import main as orchestrator_main

    if not orchestrator_main.notification_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service not initialized",
        )

    success = await orchestrator_main.notification_service.mark_as_read(notification_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return {
        "notification_id": notification_id,
        "read": True,
    }


@router.delete("/user/{user_id}")
async def clear_notifications(user_id: str) -> dict:
    """
    Clear all notifications for user.

    Args:
        user_id: User ID

    Returns:
        Number of cleared notifications
    """
    import main as orchestrator_main

    if not orchestrator_main.notification_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification service not initialized",
        )

    cleared = await orchestrator_main.notification_service.clear_notifications(user_id)

    return {
        "user_id": user_id,
        "cleared": cleared,
    }
