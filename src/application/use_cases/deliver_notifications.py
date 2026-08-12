from __future__ import annotations

from dataclasses import dataclass

from src.adapters.notification.channel_registry import NotificationChannelRegistry
from src.domain.morning_digest import MorningDigest
from src.domain.notification import (
    NotificationDelivery,
    NotificationDeliveryBatchResult,
    NotificationDeliveryFailure,
    NotificationKind,
    NotificationPayload,
    NotificationValidationError,
)
from src.ports.immediate_alert_port import ImmediateAlertRepositoryPort
from src.ports.morning_digest_port import MorningDigestRepositoryPort
from src.ports.notification_channel_port import (
    NotificationDeliveryRepositoryPort,
    NotificationTelemetryPort,
)


VALID_KINDS: frozenset[str] = frozenset({"immediate_alert", "morning_digest"})


@dataclass(slots=True)
class DeliverNotificationsUseCase:
    alert_repository: ImmediateAlertRepositoryPort
    digest_repository: MorningDigestRepositoryPort
    channel_registry: NotificationChannelRegistry
    delivery_repository: NotificationDeliveryRepositoryPort
    telemetry: NotificationTelemetryPort

    def run(
        self,
        *,
        kind: str,
        correlation_id: str,
        run_context: str | None = None,
        source_id: str | None = None,
        channels: list[str] | None = None,
    ) -> NotificationDeliveryBatchResult | NotificationDeliveryFailure:
        if not (correlation_id or "").strip():
            failure = NotificationDeliveryFailure(
                code="NOTIFICATION_CORRELATION_ID_REQUIRED",
                message="Correlation id is required and cannot be blank.",
                correlation_id=correlation_id or "",
            )
            self.telemetry.record_failure(failure)
            return failure
        correlation_id = correlation_id.strip()
        if run_context is not None and not run_context.strip():
            failure = NotificationDeliveryFailure(
                code="NOTIFICATION_RUN_CONTEXT_INVALID",
                message="Run context cannot be blank when provided.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure
        normalized_source_id: str | None = None
        if source_id is not None:
            normalized_source_id = source_id.strip()
            if not normalized_source_id:
                failure = NotificationDeliveryFailure(
                    code="NOTIFICATION_SOURCE_NOT_FOUND",
                    message="Source id cannot be blank when provided.",
                    correlation_id=correlation_id,
                )
                self.telemetry.record_failure(failure)
                return failure

        if kind not in VALID_KINDS:
            failure = NotificationDeliveryFailure(
                code="NOTIFICATION_KIND_INVALID",
                message="Notification kind must be immediate_alert or morning_digest.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure
        typed_kind: NotificationKind = kind  # type: ignore[assignment]
        context = run_context.strip() if run_context is not None else correlation_id

        try:
            adapters = self.channel_registry.resolve(channels)
        except NotificationValidationError as exc:
            failure = NotificationDeliveryFailure(
                code=exc.code,
                message=str(exc),
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        payloads, skipped_missing = self._build_payloads(
            kind=typed_kind,
            correlation_id=correlation_id,
            run_context=context,
            source_id=normalized_source_id,
        )
        if not payloads and skipped_missing:
            failure = NotificationDeliveryFailure(
                code="NOTIFICATION_SOURCE_NOT_FOUND",
                message="No notification source found for the requested kind/context.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        if payloads and not adapters:
            failure = NotificationDeliveryFailure(
                code="NOTIFICATION_NO_CHANNELS_REGISTERED",
                message="No notification channels are registered.",
                correlation_id=correlation_id,
            )
            self.telemetry.record_failure(failure)
            return failure

        deliveries: list[NotificationDelivery] = []
        failed = 0
        for payload in payloads:
            for adapter in adapters:
                try:
                    delivery = adapter.deliver(payload)
                except Exception as exc:  # noqa: BLE001 - isolate adapter failures
                    failed += 1
                    self.telemetry.record_failure(
                        NotificationDeliveryFailure(
                            code="NOTIFICATION_ADAPTER_FAILED",
                            message=f"{adapter.channel_id}: {exc}",
                            correlation_id=correlation_id,
                        )
                    )
                    continue
                deliveries.append(self.delivery_repository.save_delivery(delivery))

        result = NotificationDeliveryBatchResult(
            deliveries=tuple(deliveries),
            delivered_count=len(deliveries),
            failed_count=failed,
            skipped_missing_source_count=skipped_missing,
            correlation_id=correlation_id,
            run_context=context,
            kind=typed_kind,
        )
        self.telemetry.record_batch(result)
        return result

    def list_deliveries(self) -> list[NotificationDelivery]:
        return self.delivery_repository.list_deliveries()

    def list_in_app(self) -> list[NotificationDelivery]:
        return self.delivery_repository.list_for_channel("in_app")

    def _build_payloads(
        self,
        *,
        kind: NotificationKind,
        correlation_id: str,
        run_context: str,
        source_id: str | None,
    ) -> tuple[list[NotificationPayload], int]:
        if kind == "immediate_alert":
            alerts = self.alert_repository.list_for_run_context(run_context)
            if source_id:
                alerts = [item for item in alerts if item.id == source_id]
            if not alerts:
                return [], 1
            return [
                NotificationPayload(
                    kind="immediate_alert",
                    correlation_id=correlation_id,
                    run_context=run_context,
                    alert=item,
                )
                for item in alerts
            ], 0

        digest: MorningDigest | None
        if source_id:
            digest = next(
                (item for item in self.digest_repository.list_digests() if item.id == source_id),
                None,
            )
            if digest is not None and digest.run_context != run_context:
                digest = None
        else:
            digest = self.digest_repository.get_by_run_context(run_context)
        if digest is None:
            return [], 1
        return [
            NotificationPayload(
                kind="morning_digest",
                correlation_id=correlation_id,
                run_context=run_context,
                digest=digest,
            )
        ], 0
