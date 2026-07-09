from __future__ import annotations

from dataclasses import dataclass

from src.domain.career_source import CareerSource, CareerSourceStatus


class SourceValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True, frozen=True)
class SourcePolicyConfig:
    max_enabled_sources: int = 50


def validate_source_fields(name: str, base_url: str) -> None:
    if not name.strip():
        raise SourceValidationError("SOURCE_NAME_INVALID", "Source name must not be empty.")
    if not base_url.startswith("http://") and not base_url.startswith("https://"):
        raise SourceValidationError(
            "SOURCE_URL_INVALID",
            "Source URL must start with http:// or https://",
        )


def enforce_enable_limit(
    *,
    current_enabled_count: int,
    source: CareerSource,
    config: SourcePolicyConfig,
) -> None:
    if source.status == CareerSourceStatus.ENABLED:
        return
    if current_enabled_count >= config.max_enabled_sources:
        raise SourceValidationError(
            "SOURCE_ENABLED_LIMIT_EXCEEDED",
            f"Cannot enable more than {config.max_enabled_sources} sources in v1.",
        )
