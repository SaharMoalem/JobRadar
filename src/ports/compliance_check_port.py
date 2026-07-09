from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ComplianceCheckResult:
    passed: bool
    reason: str
    robots_txt_available: bool


class ComplianceCheckPort(Protocol):
    def evaluate(self, base_url: str) -> ComplianceCheckResult: ...
