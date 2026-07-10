from __future__ import annotations

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.adapters.compliance.http_robots_compliance_adapter import HttpRobotsComplianceAdapter
from src.adapters.crawling.normalizer_registry import InMemoryCrawlNormalizerRegistry
from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.adapters.crawling.plugin_registry import InMemoryCrawlerPluginRegistry
from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.adapters.observability.structured_lifecycle_telemetry_adapter import (
    StructuredLifecycleTelemetryAdapter,
)
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.application.ingestion.enrich_crawl_outcome import CrawlNormalizationService
from src.application.ingestion.normalize_records import NormalizeCrawlRecordsUseCase
from src.application.ingestion.track_lifecycle import JobLifecycleService
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.discover_jobs import DiscoverJobsUseCase
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.crawl import CrawlRunResult, SourceCrawlOutcome, SourceCrawlStatus
from src.domain.job_posting import JobPosting
from src.domain.normalization import NormalizationRejection
from src.domain.source_policy import SourcePolicyConfig, SourceValidationError
from src.ports.compliance_check_port import ComplianceCheckPort
from src.ports.crawler_plugin_port import CrawlerPluginPort

ERROR_STATUS_BY_CODE: dict[str, int] = {
    "SOURCE_NAME_INVALID": 400,
    "SOURCE_URL_INVALID": 400,
    "SOURCE_NOT_FOUND": 404,
    "SOURCE_NOT_ENABLED": 409,
    "SOURCE_COMPLIANCE_NOT_APPROVED": 409,
    "SOURCE_COMPLIANCE_CHECK_FAILED": 409,
    "SOURCE_ENABLED_LIMIT_EXCEEDED": 409,
}


class SourceCreateRequest(BaseModel):
    name: str
    base_url: str
    plugin_id: str = "generic"


class ComplianceRejectRequest(BaseModel):
    reason: str = "manual_rejection"


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    plugin_id: str
    status: str
    compliance_status: str
    compliance_reason: str | None = None
    robots_check_passed: bool | None = None


class RawCrawlRecordResponse(BaseModel):
    external_id: str
    title: str
    url: str
    raw_payload: dict[str, object] = Field(default_factory=dict)


class SourceCrawlOutcomeResponse(BaseModel):
    source_id: str
    plugin_id: str
    status: str
    records: list[RawCrawlRecordResponse] = Field(default_factory=list)
    job_postings: list[JobPostingResponse] = Field(default_factory=list)
    normalization_rejections: list[NormalizationRejectionResponse] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int = 0


class CrawlRunResponse(BaseModel):
    correlation_id: str
    outcomes: list[SourceCrawlOutcomeResponse]
    succeeded_count: int
    failed_count: int


class JobPostingResponse(BaseModel):
    id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: str | None
    career_source_id: str
    external_id: str
    plugin_id: str
    identity_key: str | None = None
    lifecycle_state: str
    last_seen_at: str | None = None
    expired_at: str | None = None
    completeness: str


class JobLifecycleTransitionResponse(BaseModel):
    job_posting_id: str
    from_state: str | None
    to_state: str
    reason: str
    correlation_id: str
    transitioned_at: str


class JobDuplicateLinkResponse(BaseModel):
    canonical_id: str
    identity_key: str
    career_source_id: str
    external_id: str
    duplicate_reason: str
    suppressed_at: str


class NormalizationRejectionResponse(BaseModel):
    external_id: str
    career_source_id: str
    plugin_id: str
    reason: str
    missing_fields: list[str]


def envelope(*, data=None, error=None, meta=None):
    return {"data": data, "error": error, "meta": meta or {}}


def error_response(exc: SourceValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


CRAWL_FAILURE_STATUS_BY_CODE: dict[str, int] = {
    "CRAWLER_PLUGIN_FAILED": 502,
    "CRAWLER_EMPTY_RESULT": 422,
    "CRAWLER_PLUGIN_NOT_FOUND": 422,
}


def crawl_outcome_response(outcome: SourceCrawlOutcome, *, correlation_id: str) -> JSONResponse | dict:
    data = _outcome_to_dict(outcome)
    meta = {"correlation_id": correlation_id}
    if outcome.status == SourceCrawlStatus.SUCCEEDED:
        return envelope(data=data, meta=meta)
    status_code = CRAWL_FAILURE_STATUS_BY_CODE.get(outcome.error_code or "", 422)
    return JSONResponse(
        status_code=status_code,
        content=envelope(
            data=data,
            error={"code": outcome.error_code, "message": outcome.error_message},
            meta=meta,
        ),
    )


def _job_posting_to_dict(posting: JobPosting) -> dict:
    return JobPostingResponse(
        id=posting.id,
        title=posting.title,
        company=posting.company,
        location=posting.location,
        url=posting.url,
        posted_at=posting.posted_at.isoformat() if posting.posted_at else None,
        career_source_id=posting.career_source_id,
        external_id=posting.external_id,
        plugin_id=posting.plugin_id,
        identity_key=posting.identity_key,
        lifecycle_state=posting.lifecycle_state.value,
        last_seen_at=posting.last_seen_at.isoformat() if posting.last_seen_at else None,
        expired_at=posting.expired_at.isoformat() if posting.expired_at else None,
        completeness=posting.completeness.value,
    ).model_dump()


def _lifecycle_transition_to_dict(transition) -> dict:
    return JobLifecycleTransitionResponse(
        job_posting_id=transition.job_posting_id,
        from_state=transition.from_state.value if transition.from_state else None,
        to_state=transition.to_state.value,
        reason=transition.reason,
        correlation_id=transition.correlation_id,
        transitioned_at=transition.transitioned_at.isoformat(),
    ).model_dump()


def _duplicate_link_to_dict(link) -> dict:
    return JobDuplicateLinkResponse(
        canonical_id=link.canonical_id,
        identity_key=link.identity_key,
        career_source_id=link.career_source_id,
        external_id=link.external_id,
        duplicate_reason=link.duplicate_reason,
        suppressed_at=link.suppressed_at.isoformat(),
    ).model_dump()


def _rejection_to_dict(rejection: NormalizationRejection) -> dict:
    return NormalizationRejectionResponse(
        external_id=rejection.external_id,
        career_source_id=rejection.career_source_id,
        plugin_id=rejection.plugin_id,
        reason=rejection.reason,
        missing_fields=list(rejection.missing_fields),
    ).model_dump()


def _outcome_to_dict(outcome: SourceCrawlOutcome) -> dict:
    return SourceCrawlOutcomeResponse(
        source_id=outcome.source_id,
        plugin_id=outcome.plugin_id,
        status=outcome.status.value,
        records=[
            RawCrawlRecordResponse(
                external_id=record.external_id,
                title=record.title,
                url=record.url,
                raw_payload=record.raw_payload,
            )
            for record in outcome.records
        ],
        job_postings=[_job_posting_to_dict(posting) for posting in outcome.job_postings],
        normalization_rejections=[
            _rejection_to_dict(rejection) for rejection in outcome.normalization_rejections
        ],
        error_code=outcome.error_code,
        error_message=outcome.error_message,
        duration_ms=outcome.duration_ms,
    ).model_dump()


def _run_to_dict(run: CrawlRunResult) -> dict:
    return CrawlRunResponse(
        correlation_id=run.correlation_id,
        outcomes=[_outcome_to_dict(outcome) for outcome in run.outcomes],
        succeeded_count=run.succeeded_count,
        failed_count=run.failed_count,
    ).model_dump()


def _build_normalizer_registry(
    extra_plugins: list[CrawlerPluginPort] | None = None,
) -> InMemoryCrawlNormalizerRegistry:
    normalizer = GenericStubCrawlNormalizer()
    plugin_ids = {"generic"}
    for plugin in extra_plugins or []:
        plugin_ids.add(plugin.plugin_id)
    return InMemoryCrawlNormalizerRegistry({plugin_id: normalizer for plugin_id in plugin_ids})


def _build_plugin_registry(extra_plugins: list[CrawlerPluginPort] | None = None) -> InMemoryCrawlerPluginRegistry:
    registry = InMemoryCrawlerPluginRegistry({"generic": GenericStubCrawlerPlugin()})
    for plugin in extra_plugins or []:
        registry.register(plugin)
    return registry


def create_app(
    *,
    max_enabled_sources: int = 50,
    compliance_checker: ComplianceCheckPort | None = None,
    extra_plugins: list[CrawlerPluginPort] | None = None,
    job_posting_repository: InMemoryJobPostingAdapter | None = None,
    lifecycle_telemetry: StructuredLifecycleTelemetryAdapter | None = None,
) -> FastAPI:
    app = FastAPI(title="JobRadar API")
    repository = InMemoryCareerSourceAdapter()
    telemetry = lifecycle_telemetry or StructuredLifecycleTelemetryAdapter()
    postings = job_posting_repository or InMemoryJobPostingAdapter(telemetry=telemetry)
    service = CareerSourceService(
        repository=repository,
        config=SourcePolicyConfig(max_enabled_sources=max_enabled_sources),
    )
    compliance_service = SourceComplianceService(
        repository=repository,
        compliance_checker=compliance_checker or HttpRobotsComplianceAdapter(),
    )
    plugin_registry = _build_plugin_registry(extra_plugins)
    normalizer_registry = _build_normalizer_registry(extra_plugins)
    normalize_use_case = NormalizeCrawlRecordsUseCase(job_posting_repository=postings)
    normalization_service = CrawlNormalizationService(
        repository=repository,
        normalizer_registry=normalizer_registry,
        normalize_use_case=normalize_use_case,
    )
    lifecycle_service = JobLifecycleService(repository=postings, telemetry=telemetry)
    discovery_service = DiscoverJobsUseCase(
        repository=repository,
        plugin_registry=plugin_registry,
        normalization_service=normalization_service,
        lifecycle_service=lifecycle_service,
    )

    @app.post("/career-sources")
    def create_source(payload: SourceCreateRequest):
        try:
            source = service.create(payload.name, payload.base_url, plugin_id=payload.plugin_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.get("/career-sources")
    def list_sources():
        items = [SourceResponse.model_validate(item).model_dump() for item in service.list_all()]
        return envelope(data=items)

    @app.patch("/career-sources/{source_id}")
    def update_source(source_id: str, payload: SourceCreateRequest):
        try:
            source = service.update(
                source_id,
                payload.name,
                payload.base_url,
                plugin_id=payload.plugin_id,
            )
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/enable")
    def enable_source(source_id: str):
        try:
            source = service.enable(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/disable")
    def disable_source(source_id: str):
        try:
            source = service.disable(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/compliance/approve")
    def approve_compliance(source_id: str):
        try:
            source = compliance_service.approve(source_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/compliance/reject")
    def reject_compliance(source_id: str, payload: ComplianceRejectRequest):
        try:
            source = compliance_service.reject(source_id, reason=payload.reason)
        except SourceValidationError as exc:
            return error_response(exc)
        return envelope(data=SourceResponse.model_validate(source).model_dump())

    @app.post("/career-sources/{source_id}/execute")
    def execute_source(source_id: str, x_correlation_id: str = Header(default="local")):
        try:
            outcome = discovery_service.run_source(source_id, correlation_id=x_correlation_id)
        except SourceValidationError as exc:
            return error_response(exc)
        return crawl_outcome_response(outcome, correlation_id=x_correlation_id)

    @app.post("/discovery/runs")
    def run_discovery(x_correlation_id: str = Header(default="local")):
        run = discovery_service.run_all(correlation_id=x_correlation_id)
        return envelope(
            data=_run_to_dict(run),
            meta={"correlation_id": x_correlation_id},
        )

    @app.get("/job-postings")
    def list_job_postings():
        items = [_job_posting_to_dict(posting) for posting in postings.list_complete()]
        return envelope(data=items)

    @app.get("/job-duplicate-links")
    def list_job_duplicate_links():
        items = [_duplicate_link_to_dict(link) for link in postings.list_duplicate_links()]
        return envelope(data=items)

    @app.get("/job-lifecycle-transitions")
    def list_job_lifecycle_transitions(job_posting_id: str | None = None):
        items = [
            _lifecycle_transition_to_dict(transition)
            for transition in postings.list_lifecycle_transitions(job_posting_id)
        ]
        return envelope(data=items)

    @app.get("/observability/lifecycle-metrics")
    def lifecycle_metrics():
        return envelope(data=telemetry.snapshot_metrics())

    return app


app = create_app()
