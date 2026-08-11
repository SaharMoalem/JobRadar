from __future__ import annotations

import json
import logging

from src.domain.morning_digest import MorningDigestFailure, MorningDigestResult
from src.ports.morning_digest_port import MorningDigestTelemetryPort

logger = logging.getLogger("jobradar.morning_digest")


class StructuredMorningDigestTelemetryAdapter(MorningDigestTelemetryPort):
    def __init__(self) -> None:
        self._metrics: dict[str, int] = {
            "morning_digest_runs_total": 0,
            "morning_digest_noop_total": 0,
            "morning_digest_items_new_total": 0,
            "morning_digest_items_updated_total": 0,
            "morning_digest_items_expired_total": 0,
            "morning_digest_items_top_total": 0,
            "morning_digest_skipped_threshold_total": 0,
            "morning_digest_skipped_missing_score_total": 0,
            "morning_digest_skipped_missing_posting_total": 0,
            "morning_digest_failures_total": 0,
        }

    def record_result(self, result: MorningDigestResult) -> None:
        digest = result.digest
        self._metrics["morning_digest_runs_total"] += 1
        if digest.is_noop:
            self._metrics["morning_digest_noop_total"] += 1
        self._metrics["morning_digest_items_new_total"] += len(digest.new_items)
        self._metrics["morning_digest_items_updated_total"] += len(digest.updated_items)
        self._metrics["morning_digest_items_expired_total"] += len(digest.expired_items)
        self._metrics["morning_digest_items_top_total"] += len(digest.top_recommendations)
        self._metrics["morning_digest_skipped_threshold_total"] += digest.skipped_below_threshold_count
        self._metrics["morning_digest_skipped_missing_score_total"] += digest.skipped_missing_score_count
        self._metrics["morning_digest_skipped_missing_posting_total"] += (
            digest.skipped_missing_posting_count
        )
        payload = {
            "event": "morning_digest_result",
            "correlation_id": result.correlation_id,
            "run_context": result.run_context,
            "is_noop": digest.is_noop,
            "new_count": len(digest.new_items),
            "updated_count": len(digest.updated_items),
            "expired_count": len(digest.expired_items),
            "top_count": len(digest.top_recommendations),
            "skipped_below_threshold_count": digest.skipped_below_threshold_count,
            "skipped_missing_score_count": digest.skipped_missing_score_count,
            "skipped_missing_posting_count": digest.skipped_missing_posting_count,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def record_failure(self, failure: MorningDigestFailure) -> None:
        self._metrics["morning_digest_failures_total"] += 1
        payload = {
            "event": "morning_digest_failure",
            "correlation_id": failure.correlation_id,
            "code": failure.code,
            "message": failure.message,
        }
        logger.info(json.dumps(payload, sort_keys=True))

    def snapshot_metrics(self) -> dict[str, int]:
        return dict(self._metrics)
