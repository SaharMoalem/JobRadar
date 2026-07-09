from __future__ import annotations

from urllib.parse import urlparse

import httpx

from src.ports.compliance_check_port import ComplianceCheckResult


def _robots_url_for_base(base_url: str) -> str:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return base_url.rstrip("/") + "/robots.txt"
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _robots_disallows_all_crawl(body: str) -> bool:
    active_star_agent = False
    for raw_line in body.lower().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            active_star_agent = agent == "*"
            continue
        if active_star_agent and line.startswith("disallow:"):
            path = line.split(":", 1)[1].strip()
            if path == "/":
                return True
    return False


class HttpRobotsComplianceAdapter:
    def __init__(self, *, timeout_seconds: float = 5.0) -> None:
        self._timeout_seconds = timeout_seconds

    def evaluate(self, base_url: str) -> ComplianceCheckResult:
        robots_url = _robots_url_for_base(base_url)
        try:
            response = httpx.get(robots_url, timeout=self._timeout_seconds, follow_redirects=True)
        except httpx.HTTPError:
            return ComplianceCheckResult(
                passed=False,
                reason="robots_txt_unreachable",
                robots_txt_available=False,
            )

        if response.status_code == 404:
            return ComplianceCheckResult(
                passed=True,
                reason="robots_txt_not_found",
                robots_txt_available=False,
            )

        if response.status_code >= 400:
            return ComplianceCheckResult(
                passed=False,
                reason=f"robots_txt_http_{response.status_code}",
                robots_txt_available=True,
            )

        if _robots_disallows_all_crawl(response.text):
            return ComplianceCheckResult(
                passed=False,
                reason="robots_txt_disallows_all",
                robots_txt_available=True,
            )

        return ComplianceCheckResult(
            passed=True,
            reason="robots_txt_allowed",
            robots_txt_available=True,
        )
