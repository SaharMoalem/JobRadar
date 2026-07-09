from src.domain.career_source import CareerSource
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError, enforce_enable_limit


def test_enforce_enable_limit_raises_when_over_cap():
    source = CareerSource(id="s1", name="A", base_url="https://example.com")
    config = SourcePolicyConfig(max_enabled_sources=1)
    try:
        enforce_enable_limit(current_enabled_count=1, source=source, config=config)
    except SourceValidationError as exc:
        assert exc.code == "SOURCE_ENABLED_LIMIT_EXCEEDED"
    else:
        raise AssertionError("Expected SourceValidationError")
