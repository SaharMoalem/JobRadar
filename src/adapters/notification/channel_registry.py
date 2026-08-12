from __future__ import annotations

from src.domain.notification import NotificationValidationError
from src.ports.notification_channel_port import NotificationChannelAdapter


class NotificationChannelRegistry:
    def __init__(self, adapters: list[NotificationChannelAdapter] | None = None) -> None:
        self._adapters: list[NotificationChannelAdapter] = list(adapters or [])

    def register(self, adapter: NotificationChannelAdapter) -> None:
        if any(existing.channel_id == adapter.channel_id for existing in self._adapters):
            raise NotificationValidationError(
                "NOTIFICATION_CHANNEL_DUPLICATE",
                f"Notification channel '{adapter.channel_id}' is already registered.",
            )
        self._adapters.append(adapter)

    def all(self) -> list[NotificationChannelAdapter]:
        return list(self._adapters)

    def resolve(self, channel_ids: list[str] | None = None) -> list[NotificationChannelAdapter]:
        if not channel_ids:
            return self.all()
        by_id = {adapter.channel_id: adapter for adapter in self._adapters}
        selected: list[NotificationChannelAdapter] = []
        seen: set[str] = set()
        for channel_id in channel_ids:
            if channel_id in seen:
                continue
            seen.add(channel_id)
            adapter = by_id.get(channel_id)
            if adapter is None:
                raise NotificationValidationError(
                    "NOTIFICATION_CHANNEL_UNKNOWN",
                    f"Unknown notification channel '{channel_id}'.",
                )
            selected.append(adapter)
        return selected
