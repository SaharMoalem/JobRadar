from __future__ import annotations

from dataclasses import dataclass, field

from src.ports.compliance_check_port import ComplianceCheckResult


@dataclass
class FakeComplianceCheckAdapter:
    results: dict[str, ComplianceCheckResult] = field(default_factory=dict)
    default_passed: bool = True

    def evaluate(self, base_url: str) -> ComplianceCheckResult:
        if base_url in self.results:
            return self.results[base_url]
        return ComplianceCheckResult(
            passed=self.default_passed,
            reason="fake_check_passed" if self.default_passed else "fake_check_failed",
            robots_txt_available=False,
        )
