from unittest.mock import MagicMock, patch

import httpx

from src.adapters.compliance.http_robots_compliance_adapter import (
    HttpRobotsComplianceAdapter,
    _robots_disallows_all_crawl,
    _robots_url_for_base,
)


def test_robots_url_uses_site_origin_not_path():
    assert (
        _robots_url_for_base("https://company.com/careers/jobs")
        == "https://company.com/robots.txt"
    )


def test_robots_disallows_all_requires_exact_root_path():
    body = "User-agent: *\nDisallow: /jobs\n"
    assert _robots_disallows_all_crawl(body) is False

    body = "User-agent: *\nDisallow: /\n"
    assert _robots_disallows_all_crawl(body) is True


@patch("src.adapters.compliance.http_robots_compliance_adapter.httpx.get")
def test_evaluate_fetches_origin_robots_txt(mock_get: MagicMock):
    mock_get.return_value = httpx.Response(200, text="User-agent: *\nAllow: /\n")
    adapter = HttpRobotsComplianceAdapter()

    result = adapter.evaluate("https://company.com/careers/jobs")

    mock_get.assert_called_once_with(
        "https://company.com/robots.txt",
        timeout=5.0,
        follow_redirects=True,
    )
    assert result.passed is True
    assert result.reason == "robots_txt_allowed"


@patch("src.adapters.compliance.http_robots_compliance_adapter.httpx.get")
def test_evaluate_fail_closed_on_network_error(mock_get: MagicMock):
    mock_get.side_effect = httpx.ConnectError("connection refused")
    adapter = HttpRobotsComplianceAdapter()

    result = adapter.evaluate("https://company.com/jobs")

    assert result.passed is False
    assert result.reason == "robots_txt_unreachable"


@patch("src.adapters.compliance.http_robots_compliance_adapter.httpx.get")
def test_evaluate_passes_when_robots_txt_not_found(mock_get: MagicMock):
    mock_get.return_value = httpx.Response(404, text="not found")
    adapter = HttpRobotsComplianceAdapter()

    result = adapter.evaluate("https://company.com/jobs")

    assert result.passed is True
    assert result.reason == "robots_txt_not_found"


@patch("src.adapters.compliance.http_robots_compliance_adapter.httpx.get")
def test_evaluate_rejects_full_site_disallow(mock_get: MagicMock):
    mock_get.return_value = httpx.Response(200, text="User-agent: *\nDisallow: /\n")
    adapter = HttpRobotsComplianceAdapter()

    result = adapter.evaluate("https://company.com/jobs")

    assert result.passed is False
    assert result.reason == "robots_txt_disallows_all"


@patch("src.adapters.compliance.http_robots_compliance_adapter.httpx.get")
def test_evaluate_allows_path_scoped_disallow(mock_get: MagicMock):
    mock_get.return_value = httpx.Response(200, text="User-agent: *\nDisallow: /jobs\n")
    adapter = HttpRobotsComplianceAdapter()

    result = adapter.evaluate("https://company.com/careers")

    assert result.passed is True
    assert result.reason == "robots_txt_allowed"
