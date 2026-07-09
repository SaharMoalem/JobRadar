from __future__ import annotations

import json
import logging

from src.domain.career_source import CareerSource, CareerSourceStatus, ComplianceStatus


logger = logging.getLogger("jobradar.discovery")


def _log_skip(*, reason: str, source_id: str, correlation_id: str) -> None:
    logger.info(
        json.dumps(
            {
                "event": "source_skipped",
                "reason": reason,
                "source_id": source_id,
                "correlation_id": correlation_id,
            }
        )
    )


def filter_runnable_sources(sources: list[CareerSource], correlation_id: str) -> list[CareerSource]:
    runnable: list[CareerSource] = []
    for source in sources:
        if source.status != CareerSourceStatus.ENABLED:
            _log_skip(reason="source_disabled", source_id=source.id, correlation_id=correlation_id)
            continue
        if source.compliance_status != ComplianceStatus.APPROVED:
            _log_skip(
                reason="compliance_not_approved",
                source_id=source.id,
                correlation_id=correlation_id,
            )
            continue
        runnable.append(source)
    return runnable


def filter_enabled_sources(sources: list[CareerSource], correlation_id: str) -> list[CareerSource]:
    return filter_runnable_sources(sources, correlation_id)
