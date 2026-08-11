from datetime import datetime, timezone

from src.adapters.observability.structured_immediate_alert_telemetry_adapter import (
    StructuredImmediateAlertTelemetryAdapter,
)
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_immediate_alert_adapter import (
    InMemoryImmediateAlertAdapter,
    InMemoryImmediateAlertConfigAdapter,
)
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.use_cases.immediate_alert_config import ImmediateAlertConfigService
from src.application.use_cases.trigger_immediate_alerts import TriggerImmediateAlertsUseCase
from src.domain.immediate_alert import ImmediateAlertConfig, ImmediateAlertFailure
from src.domain.job_posting import JobPosting, JobPostingCompleteness
from src.domain.lifecycle import JobLifecycleState
from src.domain.recommendation_gating import GatedRecommendation


def _posting(job_posting_id: str) -> JobPosting:
    return JobPosting(
        id=job_posting_id,
        title=f"Role {job_posting_id}",
        company="Acme",
        location="Tel Aviv",
        url=f"https://jobs.example.com/{job_posting_id}",
        posted_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        career_source_id="src-1",
        external_id=job_posting_id,
        plugin_id="generic",
        lifecycle_state=JobLifecycleState.ACTIVE,
        completeness=JobPostingCompleteness.COMPLETE,
    )


def _gated(job_posting_id: str, match_score: int) -> GatedRecommendation:
    return GatedRecommendation(
        job_posting_id=job_posting_id,
        match_score=match_score,
        profile_version="v1",
        config_version="v1",
        actionable=True,
        gate_trace=(),
        evaluated_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
    )


def _use_case(
    *,
    gated: InMemoryGatedRecommendationAdapter,
    postings: InMemoryJobPostingAdapter,
    configs: InMemoryImmediateAlertConfigAdapter | None = None,
    alerts: InMemoryImmediateAlertAdapter | None = None,
    telemetry: StructuredImmediateAlertTelemetryAdapter | None = None,
) -> TriggerImmediateAlertsUseCase:
    return TriggerImmediateAlertsUseCase(
        gated_recommendation_repository=gated,
        job_posting_repository=postings,
        alert_config_repository=configs or InMemoryImmediateAlertConfigAdapter(),
        alert_repository=alerts or InMemoryImmediateAlertAdapter(),
        telemetry=telemetry or StructuredImmediateAlertTelemetryAdapter(),
    )


def test_config_service_defaults_and_persists():
    service = ImmediateAlertConfigService(repository=InMemoryImmediateAlertConfigAdapter())
    assert service.get().alert_threshold == 90
    saved = service.save(alert_threshold=85)
    assert saved.alert_threshold == 85
    assert service.get().alert_threshold == 85


def test_trigger_creates_alerts_for_high_matches():
    postings = InMemoryJobPostingAdapter()
    high = postings.save_posting(_posting("job-high"))
    low = postings.save_posting(_posting("job-low"))
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated(high.id, 92), _gated(low.id, 80)])
    configs = InMemoryImmediateAlertConfigAdapter()
    configs.save_config(ImmediateAlertConfig(alert_threshold=90))
    alerts = InMemoryImmediateAlertAdapter()
    telemetry = StructuredImmediateAlertTelemetryAdapter()
    use_case = _use_case(
        gated=gated,
        postings=postings,
        configs=configs,
        alerts=alerts,
        telemetry=telemetry,
    )

    result = use_case.run(correlation_id="alert-1", run_context="run-a")

    assert result.triggered_count == 1
    assert result.skipped_below_threshold_count == 1
    assert result.skipped_duplicate_count == 0
    assert result.skipped_missing_posting_count == 0
    saved = alerts.list_alerts()
    assert len(saved) == 1
    assert saved[0].job_posting_id == high.id
    assert saved[0].match_score == 92
    assert saved[0].deep_link == f"/job-postings/{high.id}"
    assert "Role job-high at Acme" in saved[0].role_summary
    metrics = telemetry.snapshot_metrics()
    assert metrics["immediate_alerts_triggered_total"] == 1


def test_trigger_is_idempotent_within_run_context():
    postings = InMemoryJobPostingAdapter()
    job_1 = postings.save_posting(_posting("job-1"))
    job_2 = postings.save_posting(_posting("job-2"))
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated(job_1.id, 95), _gated(job_2.id, 91)])
    alerts = InMemoryImmediateAlertAdapter()
    use_case = _use_case(gated=gated, postings=postings, alerts=alerts)

    first = use_case.run(correlation_id="c1", run_context="digest-run")
    second = use_case.run(correlation_id="c2", run_context="digest-run")

    assert first.triggered_count == 2
    assert second.triggered_count == 0
    assert second.skipped_duplicate_count == 2
    assert len(alerts.list_alerts()) == 2


def test_each_qualifier_processed_once_per_run():
    postings = InMemoryJobPostingAdapter()
    job_a = postings.save_posting(_posting("job-a"))
    job_b = postings.save_posting(_posting("job-b"))
    job_c = postings.save_posting(_posting("job-c"))
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations(
        [_gated(job_a.id, 93), _gated(job_b.id, 91), _gated(job_c.id, 70)]
    )
    alerts = InMemoryImmediateAlertAdapter()
    use_case = _use_case(gated=gated, postings=postings, alerts=alerts)

    result = use_case.run(correlation_id="multi", run_context="run-multi")

    assert result.triggered_count == 2
    assert {item.job_posting_id for item in result.alerts} == {job_a.id, job_b.id}
    assert len(alerts.list_for_run_context("run-multi")) == 2


def test_invalid_persisted_config_returns_failure():
    gated = InMemoryGatedRecommendationAdapter()
    configs = InMemoryImmediateAlertConfigAdapter()
    configs.save_config(ImmediateAlertConfig(alert_threshold=200))
    use_case = _use_case(
        gated=gated,
        postings=InMemoryJobPostingAdapter(),
        configs=configs,
    )

    result = use_case.run(correlation_id="bad-config")

    assert isinstance(result, ImmediateAlertFailure)
    assert result.code == "ALERT_THRESHOLD_OUT_OF_RANGE"


def test_missing_posting_is_counted_not_silent():
    gated = InMemoryGatedRecommendationAdapter()
    gated.replace_recommendations([_gated("orphan-job", 95)])
    telemetry = StructuredImmediateAlertTelemetryAdapter()
    use_case = _use_case(
        gated=gated,
        postings=InMemoryJobPostingAdapter(),
        telemetry=telemetry,
    )

    result = use_case.run(correlation_id="orphan-run", run_context="orphan-ctx")

    assert result.triggered_count == 0
    assert result.skipped_missing_posting_count == 1
    assert telemetry.snapshot_metrics()["immediate_alerts_skipped_missing_posting_total"] == 1


def test_blank_correlation_id_is_rejected():
    use_case = _use_case(
        gated=InMemoryGatedRecommendationAdapter(),
        postings=InMemoryJobPostingAdapter(),
    )

    result = use_case.run(correlation_id="   ")

    assert isinstance(result, ImmediateAlertFailure)
    assert result.code == "ALERT_CORRELATION_ID_REQUIRED"


def test_blank_run_context_is_rejected():
    use_case = _use_case(
        gated=InMemoryGatedRecommendationAdapter(),
        postings=InMemoryJobPostingAdapter(),
    )

    result = use_case.run(correlation_id="ok", run_context="  ")

    assert isinstance(result, ImmediateAlertFailure)
    assert result.code == "ALERT_RUN_CONTEXT_INVALID"
