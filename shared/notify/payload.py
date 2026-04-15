"""Pydantic models and Telegram HTML formatting for monitoring webhooks."""

from html import escape
from typing import Any

from pydantic import BaseModel, Field


class WebhookPayload(BaseModel):
    """Inbound JSON from external monitoring (e.g. RU server)."""

    event_type: str = Field(..., description="e.g. error, warning, info, success")
    service: str = Field(..., description="Logical service name")
    severity: str = Field(
        ...,
        description="e.g. critical, high, medium, low",
    )
    message: str = Field(..., description="Human-readable summary")
    timestamp: str = Field(..., description="ISO 8601 timestamp string")
    details: dict[str, Any] | None = Field(default=None)


class NotificationFormatter:
    """Format payload as Telegram HTML (safe escaping)."""

    EMOJI_MAP = {
        "error": "🔴",
        "warning": "🟡",
        "info": "🔵",
        "success": "🟢",
    }

    SEVERITY_LABEL = {
        "critical": "⚠️ КРИТИЧНО",
        "high": "⚠️ ВЫСОКИЙ",
        "medium": "⚠️ СРЕДНИЙ",
        "low": "ℹ️ НИЗКИЙ",
    }

    @classmethod
    def format_telegram_html(cls, payload: WebhookPayload) -> str:
        """Build HTML message for Telegram sendMessage parse_mode=HTML."""
        emoji = cls.EMOJI_MAP.get(payload.event_type.lower(), "📢")
        sev = payload.severity.lower()
        severity = cls.SEVERITY_LABEL.get(sev, escape(sev))

        lines: list[str] = [
            f"{emoji} <b>{escape(payload.service.upper())}</b>",
            f"Уровень: {severity}",
            f"Тип: <code>{escape(payload.event_type)}</code>",
            f"Время: <code>{escape(payload.timestamp)}</code>",
            "",
            escape(payload.message),
        ]

        if payload.details:
            lines.append("")
            lines.append("<b>Детали:</b>")
            for key, value in payload.details.items():
                if key == "stack_trace":
                    continue
                lines.append(f"• <code>{escape(str(key))}</code>: {escape(str(value))}")

        return "\n".join(lines)

    @classmethod
    def format_plain(cls, payload: WebhookPayload) -> str:
        """Plain text for channels without HTML parse mode."""
        emoji = cls.EMOJI_MAP.get(payload.event_type.lower(), "📢")
        sev = payload.severity.lower()
        severity = cls.SEVERITY_LABEL.get(sev, sev)
        lines = [
            f"{emoji} {payload.service.upper()}",
            f"Уровень: {severity}",
            f"Тип: {payload.event_type}",
            f"Время: {payload.timestamp}",
            "",
            payload.message,
        ]
        if payload.details:
            lines.append("")
            lines.append("Детали:")
            for key, value in payload.details.items():
                if key == "stack_trace":
                    continue
                lines.append(f"• {key}: {value}")
        return "\n".join(lines)
