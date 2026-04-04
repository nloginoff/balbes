"""
Anonymization engine for business chat messages.

Supports three strategies per chat:
  - roles: user_id → role from role_map (e.g. "менеджер", "разработчик")
  - initials: first_name → first letter + "." (А., Б., В.)
  - full: sender completely removed, content only
"""

import re


class AnonymizationEngine:
    """
    Anonymizes Telegram user identifiers in business messages.
    Strategy and role_map are loaded from the business_chats DB record.
    """

    def __init__(self, strategy: str, role_map: dict[str, str]):
        """
        Args:
            strategy: 'roles' | 'initials' | 'full'
            role_map: {str(user_id): role_label}
        """
        if strategy not in ("roles", "initials", "full"):
            raise ValueError(f"Unknown anonymization strategy: {strategy!r}")
        self.strategy = strategy
        self.role_map = role_map

    def anonymize_sender(
        self,
        user_id: int | str,
        first_name: str | None,
        last_name: str | None = None,
        username: str | None = None,
    ) -> str | None:
        """
        Returns anonymized sender label, or None for 'full' strategy.
        """
        uid = str(user_id)

        if self.strategy == "full":
            return None

        if self.strategy == "roles":
            return self.role_map.get(uid, "сотрудник")

        # initials
        name = first_name or username or ""
        if name:
            return name[0].upper() + "."
        return "?"

    def anonymize_content(self, text: str) -> str:
        """
        Strip potential personal data from content text.
        Currently only removes phone numbers and emails as a basic safeguard.
        """
        # Phone numbers: +7..., 8-xxx, etc.
        text = re.sub(
            r"(\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", "[тел]", text
        )
        # Email addresses
        text = re.sub(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[email]", text)
        return text

    def process(
        self,
        user_id: int | str,
        first_name: str | None,
        text: str,
        last_name: str | None = None,
        username: str | None = None,
    ) -> tuple[str | None, str]:
        """
        Returns (anon_sender, anonymized_content).
        anon_sender is None when strategy == 'full'.
        """
        sender = self.anonymize_sender(user_id, first_name, last_name, username)
        content = self.anonymize_content(text)
        return sender, content
