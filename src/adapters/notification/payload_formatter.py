from __future__ import annotations

from src.domain.notification import NotificationPayload, NotificationValidationError


def format_payload_detail(payload: NotificationPayload) -> str:
    if payload.kind == "immediate_alert":
        if payload.alert is None:
            raise NotificationValidationError(
                "NOTIFICATION_PAYLOAD_INVALID",
                "Immediate alert payload is missing its alert artifact.",
            )
        alert = payload.alert
        return f"High-match alert: {alert.role_summary} (score {alert.match_score}) {alert.deep_link}"
    if payload.digest is None:
        raise NotificationValidationError(
            "NOTIFICATION_PAYLOAD_INVALID",
            "Morning digest payload is missing its digest artifact.",
        )
    digest = payload.digest
    return (
        f"Morning digest {digest.digest_date}: "
        f"new={len(digest.new_items)} updated={len(digest.updated_items)} "
        f"expired={len(digest.expired_items)} top={len(digest.top_recommendations)}"
    )
