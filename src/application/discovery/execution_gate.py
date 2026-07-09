from __future__ import annotations

import json
import logging

from src.domain.career_source import CareerSource
from src.domain.compliance_policy import require_runnable
from src.domain.source_policy import SourceValidationError


logger = logging.getLogger("jobradar.discovery")


def gate_source_execution(source: CareerSource, *, correlation_id: str) -> None:
    try:
        require_runnable(source)
    except SourceValidationError as exc:
        logger.info(
            json.dumps(
                {
                    "event": "source_execution_blocked",
                    "reason": exc.code,
                    "message": str(exc),
                    "source_id": source.id,
                    "correlation_id": correlation_id,
                }
            )
        )
        raise
