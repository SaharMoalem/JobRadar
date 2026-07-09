from __future__ import annotations

import json
import logging

from src.domain.career_source import CareerSource, CareerSourceStatus


logger = logging.getLogger("jobradar.discovery")


def filter_enabled_sources(sources: list[CareerSource], correlation_id: str) -> list[CareerSource]:
    enabled: list[CareerSource] = []
    for source in sources:
        if source.status == CareerSourceStatus.ENABLED:
            enabled.append(source)
            continue
        logger.info(
            json.dumps(
                {
                    "event": "source_skipped",
                    "reason": "source_disabled",
                    "source_id": source.id,
                    "correlation_id": correlation_id,
                }
            )
        )
    return enabled
