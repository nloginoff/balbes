"""
Notification System for Balbes Multi-Agent System.

Handles:
- Task updates (start, progress, completion)
- System alerts and warnings
- User notifications
- Notification preferences and history
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

import httpx

from shared.config import get_settings

settings = get_settings()
logger = logging.getLogger("orchestrator.notifications")


class NotificationLevel(str, Enum):
    """Notification severity level"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


class NotificationType(str, Enum):
    """Notification type"""

    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    SKILL_EXECUTED = "skill_executed"
    SYSTEM_ALERT = "system_alert"
    CONTEXT_UPDATED = "context_updated"


class Notification:
    """Notification object"""

    def __init__(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        message: str,
        level: NotificationLevel = NotificationLevel.INFO,
        data: dict[str, Any] | None = None,
    ):
        self.id = str(uuid4())
        self.user_id = user_id
        self.type = notification_type
        self.title = title
        self.message = message
        self.level = level
        self.data = data or {}
        self.created_at = datetime.now(timezone.utc)
        self.sent = False
        self.read = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type.value,
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "sent": self.sent,
            "read": self.read,
        }


class NotificationService:
    """
    Service for managing and sending notifications.

    Features:
    - Create notifications
    - Send via Telegram
    - Store in database
    - Track notification history
    - User preferences
    """

    def __init__(self):
        self.http_client: httpx.AsyncClient | None = None
        self.notifications_queue: list[Notification] = []
        self.memory_service_url = f"http://localhost:{settings.memory_service_port}"

    async def connect(self) -> None:
        """Initialize HTTP client"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Notification Service initialized")

    async def close(self) -> None:
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("Notification Service closed")

    async def notify_task_started(
        self,
        user_id: str,
        task_id: str,
        description: str,
    ) -> Notification | None:
        """Notify when task starts"""
        notification = Notification(
            user_id=user_id,
            notification_type=NotificationType.TASK_STARTED,
            title="🚀 Task Started",
            message=f"Started processing: {description[:50]}...",
            level=NotificationLevel.INFO,
            data={
                "task_id": task_id,
                "description": description,
            },
        )

        await self.send_notification(notification)
        return notification

    async def notify_task_completed(
        self,
        user_id: str,
        task_id: str,
        skill_name: str,
        result: dict[str, Any],
    ) -> Notification | None:
        """Notify when task completes successfully"""
        notification = Notification(
            user_id=user_id,
            notification_type=NotificationType.TASK_COMPLETED,
            title="✅ Task Completed",
            message=f"Successfully executed {skill_name}",
            level=NotificationLevel.SUCCESS,
            data={
                "task_id": task_id,
                "skill": skill_name,
                "result": result,
            },
        )

        await self.send_notification(notification)
        return notification

    async def notify_task_failed(
        self,
        user_id: str,
        task_id: str,
        error: str,
    ) -> Notification | None:
        """Notify when task fails"""
        notification = Notification(
            user_id=user_id,
            notification_type=NotificationType.TASK_FAILED,
            title="❌ Task Failed",
            message=f"Task failed: {error[:50]}...",
            level=NotificationLevel.ERROR,
            data={
                "task_id": task_id,
                "error": error,
            },
        )

        await self.send_notification(notification)
        return notification

    async def notify_skill_executed(
        self,
        user_id: str,
        skill_name: str,
        success: bool,
    ) -> Notification | None:
        """Notify when skill is executed"""
        notification = Notification(
            user_id=user_id,
            notification_type=NotificationType.SKILL_EXECUTED,
            title=f"🔧 Skill Executed: {skill_name}",
            message=f"Skill {'executed successfully' if success else 'failed'}",
            level=NotificationLevel.SUCCESS if success else NotificationLevel.WARNING,
            data={
                "skill_name": skill_name,
                "success": success,
            },
        )

        await self.send_notification(notification)
        return notification

    async def notify_system_alert(
        self,
        user_id: str,
        title: str,
        message: str,
        alert_type: str = "warning",
    ) -> Notification | None:
        """Send system alert notification"""
        level = NotificationLevel.ERROR if alert_type == "error" else NotificationLevel.WARNING

        notification = Notification(
            user_id=user_id,
            notification_type=NotificationType.SYSTEM_ALERT,
            title=title,
            message=message,
            level=level,
            data={
                "alert_type": alert_type,
            },
        )

        await self.send_notification(notification)
        return notification

    async def send_notification(self, notification: Notification) -> bool:
        """Send notification to user"""
        try:
            # Store in notification queue
            self.notifications_queue.append(notification)

            # Save to Memory Service
            await self._save_to_memory(notification)

            # Send via Telegram (in production)
            await self._send_via_telegram(notification)

            notification.sent = True
            logger.info(f"Notification sent to user {notification.user_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to send notification: {e}", exc_info=True)
            return False

    async def _save_to_memory(self, notification: Notification) -> None:
        """Save notification to Memory Service for history"""
        try:
            if not self.http_client:
                return

            memory_data = {
                "agent_id": "notification_service",
                "content": notification.message,
                "memory_type": "notification",
                "importance": 0.5,
                "metadata": {
                    "notification_id": notification.id,
                    "type": notification.type.value,
                    "level": notification.level.value,
                },
            }

            await self.http_client.post(
                f"{self.memory_service_url}/api/v1/memory",
                json=memory_data,
                timeout=5.0,
            )

        except Exception as e:
            logger.warning(f"Failed to save notification to memory: {e}")

    async def _send_via_telegram(self, notification: Notification) -> None:
        """Send notification via Telegram (stub for now)"""
        # In production, this would integrate with Telegram bot
        logger.debug(
            f"[Telegram] {notification.title}: {notification.message} "
            f"(user: {notification.user_id})"
        )

    async def get_notification_history(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get notification history for user"""
        # Filter queue by user_id and return recent notifications
        user_notifications = [n for n in self.notifications_queue if n.user_id == user_id]

        # Sort by created_at descending and limit
        user_notifications.sort(key=lambda n: n.created_at, reverse=True)

        return [n.to_dict() for n in user_notifications[:limit]]

    async def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        for notification in self.notifications_queue:
            if notification.id == notification_id:
                notification.read = True
                return True
        return False

    async def clear_notifications(self, user_id: str) -> int:
        """Clear all notifications for user"""
        initial_count = len(self.notifications_queue)

        self.notifications_queue = [n for n in self.notifications_queue if n.user_id != user_id]

        cleared = initial_count - len(self.notifications_queue)
        logger.info(f"Cleared {cleared} notifications for user {user_id}")

        return cleared
