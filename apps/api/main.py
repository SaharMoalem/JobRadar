from __future__ import annotations

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.adapters.compliance.http_robots_compliance_adapter import HttpRobotsComplianceAdapter
from src.adapters.crawling.normalizer_registry import InMemoryCrawlNormalizerRegistry
from src.adapters.crawling.normalizers.generic_stub_normalizer import GenericStubCrawlNormalizer
from src.adapters.crawling.plugin_registry import InMemoryCrawlerPluginRegistry
from src.adapters.crawling.plugins.generic_stub_plugin import GenericStubCrawlerPlugin
from src.adapters.explainability.rule_based_explainability_generator import (
    InMemoryExplainableRecommendationAdapter,
    RuleBasedExplainabilityGeneratorAdapter,
)
from src.adapters.observability.structured_explainability_telemetry_adapter import (
    StructuredExplainabilityTelemetryAdapter,
)
from src.adapters.observability.structured_precision_telemetry_adapter import (
    StructuredPrecisionTelemetryAdapter,
)
from src.adapters.observability.structured_gating_telemetry_adapter import (
    StructuredGatingTelemetryAdapter,
)
from src.adapters.observability.structured_lifecycle_telemetry_adapter import (
    StructuredLifecycleTelemetryAdapter,
)
from src.adapters.observability.structured_scoring_telemetry_adapter import (
    StructuredScoringTelemetryAdapter,
)
from src.adapters.persistence.in_memory_gated_recommendation_adapter import (
    InMemoryGatedRecommendationAdapter,
)
from src.adapters.persistence.in_memory_match_score_adapter import InMemoryMatchScoreAdapter
from src.adapters.persistence.in_memory_recommendation_gate_config_adapter import (
    InMemoryRecommendationGateConfigAdapter,
)
from src.adapters.persistence.in_memory_precision_policy_config_adapter import (
    InMemoryPrecisionPolicyConfigAdapter,
)
from src.adapters.persistence.in_memory_top_recommendation_adapter import (
    InMemoryTopRecommendationAdapter,
)
from src.adapters.persistence.in_memory_user_profile_adapter import InMemoryUserProfileAdapter
from src.adapters.persistence.in_memory_career_source_adapter import InMemoryCareerSourceAdapter
from src.adapters.persistence.in_memory_job_posting_adapter import InMemoryJobPostingAdapter
from src.adapters.persistence.in_memory_opportunity_filter_state_adapter import (
    InMemoryOpportunityFilterStateAdapter,
)
from src.adapters.persistence.in_memory_application_tracker_adapter import (
    InMemoryApplicationTrackerAdapter,
)
from src.adapters.persistence.in_memory_draft_artifact_adapter import InMemoryDraftArtifactAdapter
from src.adapters.drafts.rule_based_draft_artifact_generator import (
    RuleBasedDraftArtifactGeneratorAdapter,
)
from src.adapters.observability.structured_draft_artifact_telemetry_adapter import (
    StructuredDraftArtifactTelemetryAdapter,
)
from src.application.ingestion.enrich_crawl_outcome import CrawlNormalizationService
from src.application.ingestion.normalize_records import NormalizeCrawlRecordsUseCase
from src.application.ingestion.track_lifecycle import JobLifecycleService
from src.application.use_cases.apply_actionable_gating import ApplyActionableGatingUseCase
from src.application.use_cases.apply_precision_policy import ApplyPrecisionPolicyUseCase
from src.application.use_cases.career_source import CareerSourceService
from src.application.use_cases.discover_jobs import DiscoverJobsUseCase
from src.application.use_cases.generate_explainability import GenerateExplainabilityUseCase
from src.application.use_cases.precision_policy_config import PrecisionPolicyConfigService
from src.application.use_cases.recommendation_gate_config import RecommendationGateConfigService
from src.application.use_cases.score_job_postings import ScoreJobPostingsUseCase
from src.application.use_cases.search_opportunities import SearchOpportunitiesUseCase
from src.application.use_cases.application_tracker import ApplicationTrackerUseCase
from src.application.use_cases.generate_draft_artifact import GenerateDraftArtifactUseCase
from src.application.use_cases.user_profile import UserProfileService
from src.application.use_cases.source_compliance import SourceComplianceService
from src.domain.crawl import CrawlRunResult, SourceCrawlOutcome, SourceCrawlStatus
from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleState
from src.domain.opportunity_search import OpportunitySearchCriteria, OpportunitySearchValidationError, WorkModel
from src.domain.application_tracker import TrackerState, TrackerValidationError
from src.domain.draft_artifact import DraftArtifactKind, DraftArtifactValidationError, DraftGenerationFailure
from src.domain.match_scoring import ScoringBatchResult, ScoringFailure
from src.ports.draft_artifact_port import DraftArtifactGeneratorPort
from src.domain.normalization import NormalizationRejection
from src.domain.explainability import ExplainabilityBatchResult, ExplainabilityFailure
from src.domain.precision_policy import (
    PrecisionBatchResult,
    PrecisionFailure,
    PrecisionValidationError,
)
from src.domain.recommendation_gating import GatingBatchResult, GatingFailure, GatingValidationError
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
    "PROFILE_NOT_CONFIGURED": 409,
    "PROFILE_SKILLS_REQUIRED": 400,
    "PROFILE_LOCATIONS_REQUIRED": 400,
    "PROFILE_SENIORITY_REQUIRED": 400,
    "GATE_THRESHOLD_OUT_OF_RANGE": 400,
    "GATE_SKILL_OVERLAP_OUT_OF_RANGE": 400,
    "GATE_RECENCY_WINDOW_INVALID": 400,
    "PRECISION_MIN_CONFIDENCE_OUT_OF_RANGE": 400,
    "PRECISION_MAX_TOP_OUT_OF_RANGE": 400,
    "SEARCH_SCORE_OUT_OF_RANGE": 400,
    "SEARCH_SCORE_RANGE_INVALID": 400,
    "SEARCH_FRESHNESS_DAYS_INVALID": 400,
    "SEARCH_WORK_MODEL_INVALID": 400,
    "SEARCH_LIFECYCLE_STATE_INVALID": 400,
    "TRACKER_JOB_POSTING_NOT_FOUND": 404,
    "TRACKER_NOT_FOUND": 404,
    "TRACKER_TRANSITION_INVALID": 409,
    "TRACKER_TRANSITION_UNCHANGED": 409,
    "TRACKER_STATE_INVALID": 400,
    "DRAFT_JOB_POSTING_NOT_FOUND": 404,
    "DRAFT_TRACKER_NOT_FOUND": 409,
    "DRAFT_TRACKER_CONTEXT_INVALID": 409,
    "DRAFT_KIND_INVALID": 400,
    "DRAFT_GENERATION_FAILED": 502,
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


class UserProfileRequest(BaseModel):
    skills: list[str]
    preferred_locations: list[str]
    preferred_languages: list[str] = Field(default_factory=list)
    target_seniority: str


class UserProfileResponse(BaseModel):
    id: str
    skills: list[str]
    preferred_locations: list[str]
    preferred_languages: list[str]
    target_seniority: str
    profile_version: str
    updated_at: str


class MatchScoreResponse(BaseModel):
    job_posting_id: str
    score: int
    profile_version: str
    config_version: str
    signal_breakdown: dict[str, int]
    computed_at: str


class ScoringBatchResponse(BaseModel):
    scored_count: int
    skipped_count: int
    scores: list[MatchScoreResponse]


class ScoringFailureResponse(BaseModel):
    code: str
    message: str


class RecommendationGateConfigRequest(BaseModel):
    global_threshold: int = 80
    skill_overlap_min_pct: int = 70
    recency_window_days: int = 14
    enforce_seniority: bool = True
    enforce_skill_overlap: bool = True
    enforce_language: bool = True
    enforce_region: bool = True
    enforce_recency: bool = True
    enforce_active_link: bool = True
    config_version: str = "v1"


class RecommendationGateConfigResponse(BaseModel):
    config_version: str
    global_threshold: int
    skill_overlap_min_pct: int
    recency_window_days: int
    enforce_seniority: bool
    enforce_skill_overlap: bool
    enforce_language: bool
    enforce_region: bool
    enforce_recency: bool
    enforce_active_link: bool


class GateTraceEntryResponse(BaseModel):
    gate: str
    passed: bool
    message: str


class GatedRecommendationResponse(BaseModel):
    job_posting_id: str
    match_score: int
    profile_version: str
    config_version: str
    actionable: bool
    gate_trace: list[GateTraceEntryResponse]
    evaluated_at: str


class GatingBatchResponse(BaseModel):
    actionable_count: int
    non_actionable_count: int
    skipped_count: int
    recommendations: list[GatedRecommendationResponse]


class GatingFailureResponse(BaseModel):
    code: str
    message: str


class PrecisionPolicyConfigRequest(BaseModel):
    min_confidence_for_top: int = 85
    max_top_count: int = 10
    config_version: str = "v1"


class PrecisionPolicyConfigResponse(BaseModel):
    config_version: str
    min_confidence_for_top: int
    max_top_count: int


class TopRecommendationResponse(BaseModel):
    job_posting_id: str
    match_score: int
    rank: int | None
    suppressed: bool
    suppression_reason: str | None
    policy_version: str
    gate_config_version: str
    profile_version: str
    evaluated_at: str


class PrecisionBatchResponse(BaseModel):
    top_count: int
    suppressed_low_confidence_count: int
    suppressed_capacity_count: int
    actionable_input_count: int
    top_recommendations: list[TopRecommendationResponse]


class ExplainabilityNoteResponse(BaseModel):
    match_rationale: str
    missing_skills: list[str]
    interview_probability_pct: int
    effort_estimate: str


class ExplainableRecommendationResponse(BaseModel):
    job_posting_id: str
    match_score: int
    profile_version: str
    scoring_config_version: str
    gate_config_version: str
    policy_version: str
    promoted: bool
    note: ExplainabilityNoteResponse | None
    failure_code: str | None
    failure_reason: str | None
    generated_at: str


class ExplainabilityBatchResponse(BaseModel):
    promoted_count: int
    failed_count: int
    recommendations: list[ExplainableRecommendationResponse]


class OpportunitySearchRequest(BaseModel):
    role_family: str | None = None
    location: str | None = None
    work_model: str | None = None
    min_score: int | None = None
    max_score: int | None = None
    freshness_days: int | None = None
    lifecycle_states: list[str] | None = None
    session_id: str = "default"


class OpportunityItemResponse(BaseModel):
    job_posting_id: str
    title: str
    company: str
    location: str
    url: str
    posted_at: str | None
    lifecycle_state: str
    role_family: str
    work_model: str
    match_score: int | None


class OpportunitySearchResponse(BaseModel):
    items: list[OpportunityItemResponse]
    total_count: int
    empty: bool


class OpportunityFilterStateResponse(BaseModel):
    session_id: str
    criteria: dict[str, object]
    updated_at: str


class BookmarkRequest(BaseModel):
    job_posting_id: str


class TrackerTransitionRequest(BaseModel):
    to_state: str
    reason: str = "manual_transition"


class TrackedOpportunityResponse(BaseModel):
    job_posting_id: str
    tracker_state: str
    bookmarked: bool
    bookmarked_at: str | None
    updated_at: str


class TrackerTransitionResponse(BaseModel):
    job_posting_id: str
    from_state: str | None
    to_state: str
    reason: str
    correlation_id: str
    transitioned_at: str


class DraftArtifactGenerateRequest(BaseModel):
    job_posting_id: str
    kind: str


class DraftArtifactResponse(BaseModel):
    id: str
    job_posting_id: str
    kind: str
    content: str
    source_reference: str
    status: str
    is_latest: bool
    correlation_id: str
    created_at: str


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


def _profile_to_dict(profile) -> dict:
    return UserProfileResponse(
        id=profile.id,
        skills=list(profile.skills),
        preferred_locations=list(profile.preferred_locations),
        preferred_languages=list(profile.preferred_languages),
        target_seniority=profile.target_seniority,
        profile_version=profile.profile_version,
        updated_at=profile.updated_at.isoformat(),
    ).model_dump()


def _match_score_to_dict(score) -> dict:
    return MatchScoreResponse(
        job_posting_id=score.job_posting_id,
        score=score.score,
        profile_version=score.profile_version,
        config_version=score.config_version,
        signal_breakdown=dict(score.signal_breakdown),
        computed_at=score.computed_at.isoformat(),
    ).model_dump()


def _scoring_result_response(result: ScoringBatchResult | ScoringFailure, *, correlation_id: str):
    if isinstance(result, ScoringFailure):
        status_code = ERROR_STATUS_BY_CODE.get(result.code, 400)
        return JSONResponse(
            status_code=status_code,
            content=envelope(
                error={"code": result.code, "message": result.message},
                meta={"correlation_id": correlation_id},
            ),
        )
    return envelope(
        data=ScoringBatchResponse(
            scored_count=result.scored_count,
            skipped_count=result.skipped_count,
            scores=[_match_score_to_dict(score) for score in result.scores],
        ).model_dump(),
        meta={"correlation_id": correlation_id},
    )


def _gate_config_to_dict(config) -> dict:
    return RecommendationGateConfigResponse(
        config_version=config.config_version,
        global_threshold=config.global_threshold,
        skill_overlap_min_pct=config.skill_overlap_min_pct,
        recency_window_days=config.recency_window_days,
        enforce_seniority=config.enforce_seniority,
        enforce_skill_overlap=config.enforce_skill_overlap,
        enforce_language=config.enforce_language,
        enforce_region=config.enforce_region,
        enforce_recency=config.enforce_recency,
        enforce_active_link=config.enforce_active_link,
    ).model_dump()


def _gated_recommendation_to_dict(recommendation) -> dict:
    return GatedRecommendationResponse(
        job_posting_id=recommendation.job_posting_id,
        match_score=recommendation.match_score,
        profile_version=recommendation.profile_version,
        config_version=recommendation.config_version,
        actionable=recommendation.actionable,
        gate_trace=[
            GateTraceEntryResponse(
                gate=entry.gate,
                passed=entry.passed,
                message=entry.message,
            ).model_dump()
            for entry in recommendation.gate_trace
        ],
        evaluated_at=recommendation.evaluated_at.isoformat(),
    ).model_dump()


def _gating_result_response(result: GatingBatchResult | GatingFailure, *, correlation_id: str):
    if isinstance(result, GatingFailure):
        status_code = ERROR_STATUS_BY_CODE.get(result.code, 400)
        return JSONResponse(
            status_code=status_code,
            content=envelope(
                error={"code": result.code, "message": result.message},
                meta={"correlation_id": correlation_id},
            ),
        )
    return envelope(
        data=GatingBatchResponse(
            actionable_count=result.actionable_count,
            non_actionable_count=result.non_actionable_count,
            skipped_count=result.skipped_count,
            recommendations=[_gated_recommendation_to_dict(item) for item in result.recommendations],
        ).model_dump(),
        meta={"correlation_id": correlation_id},
    )


def gating_error_response(exc: GatingValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def _precision_config_to_dict(config) -> dict:
    return PrecisionPolicyConfigResponse(
        config_version=config.config_version,
        min_confidence_for_top=config.min_confidence_for_top,
        max_top_count=config.max_top_count,
    ).model_dump()


def _top_recommendation_to_dict(recommendation) -> dict:
    return TopRecommendationResponse(
        job_posting_id=recommendation.job_posting_id,
        match_score=recommendation.match_score,
        rank=recommendation.rank,
        suppressed=recommendation.suppressed,
        suppression_reason=recommendation.suppression_reason,
        policy_version=recommendation.policy_version,
        gate_config_version=recommendation.gate_config_version,
        profile_version=recommendation.profile_version,
        evaluated_at=recommendation.evaluated_at.isoformat(),
    ).model_dump()


def _precision_result_response(result: PrecisionBatchResult | PrecisionFailure, *, correlation_id: str):
    if isinstance(result, PrecisionFailure):
        status_code = ERROR_STATUS_BY_CODE.get(result.code, 400)
        return JSONResponse(
            status_code=status_code,
            content=envelope(
                error={"code": result.code, "message": result.message},
                meta={"correlation_id": correlation_id},
            ),
        )
    return envelope(
        data=PrecisionBatchResponse(
            top_count=result.top_count,
            suppressed_low_confidence_count=result.suppressed_low_confidence_count,
            suppressed_capacity_count=result.suppressed_capacity_count,
            actionable_input_count=result.actionable_input_count,
            top_recommendations=[
                _top_recommendation_to_dict(item) for item in result.top_recommendations if not item.suppressed
            ],
        ).model_dump(),
        meta={"correlation_id": correlation_id},
    )


def precision_error_response(exc: PrecisionValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def _explainability_note_to_dict(note) -> dict:
    return ExplainabilityNoteResponse(
        match_rationale=note.match_rationale,
        missing_skills=list(note.missing_skills),
        interview_probability_pct=note.interview_probability_pct,
        effort_estimate=note.effort_estimate,
    ).model_dump()


def _explainable_recommendation_to_dict(recommendation) -> dict:
    return ExplainableRecommendationResponse(
        job_posting_id=recommendation.job_posting_id,
        match_score=recommendation.match_score,
        profile_version=recommendation.profile_version,
        scoring_config_version=recommendation.scoring_config_version,
        gate_config_version=recommendation.gate_config_version,
        policy_version=recommendation.policy_version,
        promoted=recommendation.promoted,
        note=_explainability_note_to_dict(recommendation.note) if recommendation.note else None,
        failure_code=recommendation.failure_code,
        failure_reason=recommendation.failure_reason,
        generated_at=recommendation.generated_at.isoformat(),
    ).model_dump()


def _explainability_result_response(
    result: ExplainabilityBatchResult | ExplainabilityFailure,
    *,
    correlation_id: str,
):
    if isinstance(result, ExplainabilityFailure):
        status_code = ERROR_STATUS_BY_CODE.get(result.code, 400)
        return JSONResponse(
            status_code=status_code,
            content=envelope(
                error={"code": result.code, "message": result.message},
                meta={"correlation_id": correlation_id},
            ),
        )
    return envelope(
        data=ExplainabilityBatchResponse(
            promoted_count=result.promoted_count,
            failed_count=result.failed_count,
            recommendations=[
                _explainable_recommendation_to_dict(item)
                for item in result.recommendations
                if item.promoted
            ],
        ).model_dump(),
        meta={"correlation_id": correlation_id},
    )


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


def _criteria_to_dict(criteria: OpportunitySearchCriteria) -> dict[str, object]:
    payload: dict[str, object] = {}
    if criteria.role_family is not None:
        payload["role_family"] = criteria.role_family
    if criteria.location is not None:
        payload["location"] = criteria.location
    if criteria.work_model is not None:
        payload["work_model"] = criteria.work_model.value
    if criteria.min_score is not None:
        payload["min_score"] = criteria.min_score
    if criteria.max_score is not None:
        payload["max_score"] = criteria.max_score
    if criteria.freshness_days is not None:
        payload["freshness_days"] = criteria.freshness_days
    if criteria.lifecycle_states is not None:
        payload["lifecycle_states"] = [state.value for state in criteria.lifecycle_states]
    return payload


def _criteria_from_request(payload: OpportunitySearchRequest) -> OpportunitySearchCriteria:
    work_model: WorkModel | None = None
    if payload.work_model is not None:
        normalized = payload.work_model.strip().lower().replace("-", "_")
        try:
            work_model = WorkModel(normalized)
        except ValueError as exc:
            raise OpportunitySearchValidationError(
                "SEARCH_WORK_MODEL_INVALID",
                f"Unsupported work model: {payload.work_model}",
            ) from exc

    lifecycle_states: tuple[JobLifecycleState, ...] | None = None
    if payload.lifecycle_states is not None:
        parsed_states: list[JobLifecycleState] = []
        for state_value in payload.lifecycle_states:
            try:
                parsed_states.append(JobLifecycleState(state_value))
            except ValueError as exc:
                raise OpportunitySearchValidationError(
                    "SEARCH_LIFECYCLE_STATE_INVALID",
                    f"Unsupported lifecycle state: {state_value}",
                ) from exc
        lifecycle_states = tuple(parsed_states)

    return OpportunitySearchCriteria(
        role_family=payload.role_family,
        location=payload.location,
        work_model=work_model,
        min_score=payload.min_score,
        max_score=payload.max_score,
        freshness_days=payload.freshness_days,
        lifecycle_states=lifecycle_states,
    )


def _opportunity_item_to_dict(item) -> dict:
    return OpportunityItemResponse(
        job_posting_id=item.job_posting_id,
        title=item.title,
        company=item.company,
        location=item.location,
        url=item.url,
        posted_at=item.posted_at.isoformat() if item.posted_at else None,
        lifecycle_state=item.lifecycle_state.value,
        role_family=item.role_family,
        work_model=item.work_model.value,
        match_score=item.match_score,
    ).model_dump()


def _filter_state_to_dict(state) -> dict:
    return OpportunityFilterStateResponse(
        session_id=state.session_id,
        criteria=_criteria_to_dict(state.criteria),
        updated_at=state.updated_at.isoformat(),
    ).model_dump()


def opportunity_search_error_response(exc: OpportunitySearchValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def tracker_error_response(exc: TrackerValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def _tracked_opportunity_to_dict(tracked) -> dict:
    return TrackedOpportunityResponse(
        job_posting_id=tracked.job_posting_id,
        tracker_state=tracked.tracker_state.value,
        bookmarked=tracked.bookmarked,
        bookmarked_at=tracked.bookmarked_at.isoformat() if tracked.bookmarked_at else None,
        updated_at=tracked.updated_at.isoformat(),
    ).model_dump()


def _tracker_transition_to_dict(transition) -> dict:
    return TrackerTransitionResponse(
        job_posting_id=transition.job_posting_id,
        from_state=transition.from_state.value if transition.from_state else None,
        to_state=transition.to_state.value,
        reason=transition.reason,
        correlation_id=transition.correlation_id,
        transitioned_at=transition.transitioned_at.isoformat(),
    ).model_dump()


def draft_error_response(exc: DraftArtifactValidationError) -> JSONResponse:
    status_code = ERROR_STATUS_BY_CODE.get(exc.code, 400)
    return JSONResponse(
        status_code=status_code,
        content=envelope(error={"code": exc.code, "message": str(exc)}),
    )


def _draft_artifact_to_dict(artifact) -> dict:
    return DraftArtifactResponse(
        id=artifact.id,
        job_posting_id=artifact.job_posting_id,
        kind=artifact.kind.value,
        content=artifact.content,
        source_reference=artifact.source_reference,
        status=artifact.status.value,
        is_latest=artifact.is_latest,
        correlation_id=artifact.correlation_id,
        created_at=artifact.created_at.isoformat(),
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
    user_profile_repository: InMemoryUserProfileAdapter | None = None,
    match_score_repository: InMemoryMatchScoreAdapter | None = None,
    scoring_telemetry: StructuredScoringTelemetryAdapter | None = None,
    gate_config_repository: InMemoryRecommendationGateConfigAdapter | None = None,
    gated_recommendation_repository: InMemoryGatedRecommendationAdapter | None = None,
    gating_telemetry: StructuredGatingTelemetryAdapter | None = None,
    precision_config_repository: InMemoryPrecisionPolicyConfigAdapter | None = None,
    top_recommendation_repository: InMemoryTopRecommendationAdapter | None = None,
    precision_telemetry: StructuredPrecisionTelemetryAdapter | None = None,
    explainable_recommendation_repository: InMemoryExplainableRecommendationAdapter | None = None,
    explainability_telemetry: StructuredExplainabilityTelemetryAdapter | None = None,
    opportunity_filter_state_repository: InMemoryOpportunityFilterStateAdapter | None = None,
    application_tracker_repository: InMemoryApplicationTrackerAdapter | None = None,
    draft_artifact_repository: InMemoryDraftArtifactAdapter | None = None,
    draft_artifact_generator: DraftArtifactGeneratorPort | None = None,
    draft_artifact_telemetry: StructuredDraftArtifactTelemetryAdapter | None = None,
) -> FastAPI:
    app = FastAPI(title="JobRadar API")
    repository = InMemoryCareerSourceAdapter()
    telemetry = lifecycle_telemetry or StructuredLifecycleTelemetryAdapter()
    scoring_metrics = scoring_telemetry or StructuredScoringTelemetryAdapter()
    gating_metrics = gating_telemetry or StructuredGatingTelemetryAdapter()
    precision_metrics = precision_telemetry or StructuredPrecisionTelemetryAdapter()
    explainability_metrics = explainability_telemetry or StructuredExplainabilityTelemetryAdapter()
    postings = job_posting_repository or InMemoryJobPostingAdapter(telemetry=telemetry)
    profiles = user_profile_repository or InMemoryUserProfileAdapter()
    match_scores = match_score_repository or InMemoryMatchScoreAdapter()
    gate_configs = gate_config_repository or InMemoryRecommendationGateConfigAdapter()
    gated_recommendations = gated_recommendation_repository or InMemoryGatedRecommendationAdapter()
    precision_configs = precision_config_repository or InMemoryPrecisionPolicyConfigAdapter()
    top_recommendations = top_recommendation_repository or InMemoryTopRecommendationAdapter()
    explainable_recommendations = (
        explainable_recommendation_repository or InMemoryExplainableRecommendationAdapter()
    )
    opportunity_filter_states = (
        opportunity_filter_state_repository or InMemoryOpportunityFilterStateAdapter()
    )
    application_trackers = application_tracker_repository or InMemoryApplicationTrackerAdapter()
    draft_artifacts = draft_artifact_repository or InMemoryDraftArtifactAdapter()
    draft_metrics = draft_artifact_telemetry or StructuredDraftArtifactTelemetryAdapter()
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
    profile_service = UserProfileService(repository=profiles)
    scoring_service = ScoreJobPostingsUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=match_scores,
        telemetry=scoring_metrics,
    )
    gate_config_service = RecommendationGateConfigService(repository=gate_configs)
    gating_service = ApplyActionableGatingUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=match_scores,
        gate_config_repository=gate_configs,
        gated_recommendation_repository=gated_recommendations,
        telemetry=gating_metrics,
    )
    precision_config_service = PrecisionPolicyConfigService(repository=precision_configs)
    precision_service = ApplyPrecisionPolicyUseCase(
        gated_recommendation_repository=gated_recommendations,
        precision_config_repository=precision_configs,
        top_recommendation_repository=top_recommendations,
        telemetry=precision_metrics,
    )
    explainability_service = GenerateExplainabilityUseCase(
        profile_repository=profiles,
        job_posting_repository=postings,
        match_score_repository=match_scores,
        gated_recommendation_repository=gated_recommendations,
        top_recommendation_repository=top_recommendations,
        explainable_recommendation_repository=explainable_recommendations,
        generator=RuleBasedExplainabilityGeneratorAdapter(),
        telemetry=explainability_metrics,
    )
    opportunity_search_service = SearchOpportunitiesUseCase(
        job_posting_repository=postings,
        match_score_repository=match_scores,
        filter_state_repository=opportunity_filter_states,
    )
    tracker_service = ApplicationTrackerUseCase(
        tracker_repository=application_trackers,
        job_posting_repository=postings,
    )
    draft_service = GenerateDraftArtifactUseCase(
        job_posting_repository=postings,
        tracker_repository=application_trackers,
        profile_repository=profiles,
        draft_repository=draft_artifacts,
        generator=draft_artifact_generator or RuleBasedDraftArtifactGeneratorAdapter(),
        telemetry=draft_metrics,
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

    @app.get("/user-profile")
    def get_user_profile():
        profile = profile_service.get()
        if profile is None:
            return JSONResponse(
                status_code=404,
                content=envelope(error={"code": "PROFILE_NOT_CONFIGURED", "message": "User profile is not configured."}),
            )
        return envelope(data=_profile_to_dict(profile))

    @app.put("/user-profile")
    def save_user_profile(payload: UserProfileRequest):
        profile = profile_service.save(
            skills=payload.skills,
            preferred_locations=payload.preferred_locations,
            preferred_languages=payload.preferred_languages,
            target_seniority=payload.target_seniority,
        )
        return envelope(data=_profile_to_dict(profile))

    @app.post("/match-scores/run")
    def run_match_scoring(x_correlation_id: str = Header(default="local")):
        result = scoring_service.score_all_eligible(correlation_id=x_correlation_id)
        return _scoring_result_response(result, correlation_id=x_correlation_id)

    @app.get("/match-scores")
    def list_match_scores():
        items = [_match_score_to_dict(score) for score in match_scores.list_scores()]
        return envelope(data=items)

    @app.get("/observability/scoring-metrics")
    def scoring_metrics_endpoint():
        return envelope(data=scoring_metrics.snapshot_metrics())

    @app.get("/recommendation-gate-config")
    def get_recommendation_gate_config():
        return envelope(data=_gate_config_to_dict(gate_config_service.get()))

    @app.put("/recommendation-gate-config")
    def save_recommendation_gate_config(payload: RecommendationGateConfigRequest):
        try:
            config = gate_config_service.save(
                global_threshold=payload.global_threshold,
                skill_overlap_min_pct=payload.skill_overlap_min_pct,
                recency_window_days=payload.recency_window_days,
                enforce_seniority=payload.enforce_seniority,
                enforce_skill_overlap=payload.enforce_skill_overlap,
                enforce_language=payload.enforce_language,
                enforce_region=payload.enforce_region,
                enforce_recency=payload.enforce_recency,
                enforce_active_link=payload.enforce_active_link,
                config_version=payload.config_version,
            )
        except GatingValidationError as exc:
            return gating_error_response(exc)
        return envelope(data=_gate_config_to_dict(config))

    @app.post("/recommendations/gating/run")
    def run_recommendation_gating(x_correlation_id: str = Header(default="local")):
        result = gating_service.run_gating(correlation_id=x_correlation_id)
        return _gating_result_response(result, correlation_id=x_correlation_id)

    @app.get("/recommendations")
    def list_recommendations():
        items = [
            _gated_recommendation_to_dict(item) for item in gated_recommendations.list_recommendations()
        ]
        return envelope(data=items)

    @app.get("/recommendations/actionable")
    def list_actionable_recommendations():
        items = [_gated_recommendation_to_dict(item) for item in gated_recommendations.list_actionable()]
        return envelope(data=items)

    @app.get("/observability/gating-metrics")
    def gating_metrics_endpoint():
        return envelope(data=gating_metrics.snapshot_metrics())

    @app.get("/recommendation-precision-config")
    def get_recommendation_precision_config():
        return envelope(data=_precision_config_to_dict(precision_config_service.get()))

    @app.put("/recommendation-precision-config")
    def save_recommendation_precision_config(payload: PrecisionPolicyConfigRequest):
        try:
            config = precision_config_service.save(
                min_confidence_for_top=payload.min_confidence_for_top,
                max_top_count=payload.max_top_count,
                config_version=payload.config_version,
            )
        except PrecisionValidationError as exc:
            return precision_error_response(exc)
        return envelope(data=_precision_config_to_dict(config))

    @app.post("/recommendations/precision/run")
    def run_precision_policy(x_correlation_id: str = Header(default="local")):
        result = precision_service.run_precision_policy(correlation_id=x_correlation_id)
        return _precision_result_response(result, correlation_id=x_correlation_id)

    @app.get("/recommendations/top")
    def list_top_recommendations():
        items = [_top_recommendation_to_dict(item) for item in top_recommendations.list_top()]
        return envelope(data=items)

    @app.get("/recommendations/precision-traces")
    def list_precision_traces():
        items = [_top_recommendation_to_dict(item) for item in top_recommendations.list_all()]
        return envelope(data=items)

    @app.get("/observability/precision-metrics")
    def precision_metrics_endpoint():
        return envelope(data=precision_metrics.snapshot_metrics())

    @app.post("/recommendations/explainability/run")
    def run_explainability(x_correlation_id: str = Header(default="local")):
        result = explainability_service.run_explainability(correlation_id=x_correlation_id)
        return _explainability_result_response(result, correlation_id=x_correlation_id)

    @app.get("/recommendations/explainable")
    def list_explainable_recommendations():
        items = [
            _explainable_recommendation_to_dict(item)
            for item in explainable_recommendations.list_promoted()
        ]
        return envelope(data=items)

    @app.get("/recommendations/explainability-traces")
    def list_explainability_traces():
        items = [
            _explainable_recommendation_to_dict(item) for item in explainable_recommendations.list_all()
        ]
        return envelope(data=items)

    @app.get("/observability/explainability-metrics")
    def explainability_metrics_endpoint():
        return envelope(data=explainability_metrics.snapshot_metrics())

    @app.post("/opportunities/search")
    def search_opportunities(payload: OpportunitySearchRequest):
        try:
            criteria = _criteria_from_request(payload)
            result = opportunity_search_service.search(criteria, session_id=payload.session_id)
        except OpportunitySearchValidationError as exc:
            return opportunity_search_error_response(exc)
        return envelope(
            data=OpportunitySearchResponse(
                items=[_opportunity_item_to_dict(item) for item in result.items],
                total_count=result.total_count,
                empty=result.is_empty,
            ).model_dump(),
            meta={
                "session_id": payload.session_id,
                "applied_filter": _criteria_to_dict(result.criteria),
            },
        )

    @app.get("/opportunity-filter-state")
    def get_opportunity_filter_state(session_id: str = "default"):
        state = opportunity_search_service.get_filter_state(session_id)
        if state is None:
            return envelope(data=None, meta={"session_id": session_id})
        return envelope(data=_filter_state_to_dict(state), meta={"session_id": session_id})

    @app.put("/opportunity-filter-state")
    def save_opportunity_filter_state(payload: OpportunitySearchRequest):
        try:
            criteria = _criteria_from_request(payload)
            state = opportunity_search_service.save_filter_state(criteria, session_id=payload.session_id)
        except OpportunitySearchValidationError as exc:
            return opportunity_search_error_response(exc)
        return envelope(
            data=_filter_state_to_dict(state),
            meta={"session_id": payload.session_id},
        )

    @app.post("/tracker/bookmarks")
    def bookmark_opportunity(payload: BookmarkRequest, x_correlation_id: str = Header(default="local")):
        try:
            tracked = tracker_service.bookmark(
                payload.job_posting_id,
                correlation_id=x_correlation_id,
            )
        except TrackerValidationError as exc:
            return tracker_error_response(exc)
        return envelope(data=_tracked_opportunity_to_dict(tracked), meta={"correlation_id": x_correlation_id})

    @app.delete("/tracker/bookmarks/{job_posting_id}")
    def unbookmark_opportunity(job_posting_id: str):
        try:
            tracked = tracker_service.unbookmark(job_posting_id)
        except TrackerValidationError as exc:
            return tracker_error_response(exc)
        return envelope(data=_tracked_opportunity_to_dict(tracked))

    @app.get("/tracker/bookmarks")
    def list_bookmarked_opportunities():
        items = [_tracked_opportunity_to_dict(item) for item in tracker_service.list_bookmarked()]
        return envelope(data=items)

    @app.get("/tracker")
    def list_tracked_opportunities():
        items = [_tracked_opportunity_to_dict(item) for item in tracker_service.list_tracked()]
        return envelope(data=items)

    @app.get("/tracker/{job_posting_id}")
    def get_tracked_opportunity(job_posting_id: str):
        tracked = tracker_service.get(job_posting_id)
        if tracked is None:
            return JSONResponse(
                status_code=404,
                content=envelope(
                    error={
                        "code": "TRACKER_NOT_FOUND",
                        "message": f"No tracked opportunity found for job posting '{job_posting_id}'.",
                    }
                ),
            )
        return envelope(data=_tracked_opportunity_to_dict(tracked))

    @app.post("/tracker/{job_posting_id}/transitions")
    def transition_tracked_opportunity(
        job_posting_id: str,
        payload: TrackerTransitionRequest,
        x_correlation_id: str = Header(default="local"),
    ):
        try:
            to_state = TrackerState(payload.to_state.strip().lower())
        except ValueError:
            return tracker_error_response(
                TrackerValidationError(
                    "TRACKER_STATE_INVALID",
                    f"Unsupported tracker state: {payload.to_state}",
                )
            )
        try:
            tracked = tracker_service.transition(
                job_posting_id,
                to_state=to_state,
                reason=payload.reason,
                correlation_id=x_correlation_id,
            )
        except TrackerValidationError as exc:
            return tracker_error_response(exc)
        return envelope(
            data=_tracked_opportunity_to_dict(tracked),
            meta={"correlation_id": x_correlation_id},
        )

    @app.get("/tracker/{job_posting_id}/transitions")
    def list_tracker_transitions(job_posting_id: str):
        items = [
            _tracker_transition_to_dict(transition)
            for transition in tracker_service.list_history(job_posting_id)
        ]
        return envelope(data=items)

    @app.post("/draft-artifacts/generate")
    def generate_draft_artifact(
        payload: DraftArtifactGenerateRequest,
        x_correlation_id: str = Header(default="local"),
    ):
        try:
            kind = DraftArtifactKind(payload.kind.strip().lower())
        except ValueError:
            failure = DraftGenerationFailure(
                code="DRAFT_KIND_INVALID",
                message=f"Unsupported draft artifact kind: {payload.kind}",
                correlation_id=x_correlation_id,
            )
            draft_metrics.record_failure(failure)
            return draft_error_response(
                DraftArtifactValidationError(failure.code, failure.message)
            )
        try:
            artifact = draft_service.generate(
                job_posting_id=payload.job_posting_id,
                kind=kind,
                correlation_id=x_correlation_id,
            )
        except DraftArtifactValidationError as exc:
            return draft_error_response(exc)
        return envelope(
            data=_draft_artifact_to_dict(artifact),
            meta={"correlation_id": x_correlation_id},
        )

    @app.get("/draft-artifacts")
    def list_draft_artifacts(job_posting_id: str, kind: str | None = None, latest_only: bool = False):
        parsed_kind: DraftArtifactKind | None = None
        if kind is not None:
            try:
                parsed_kind = DraftArtifactKind(kind.strip().lower())
            except ValueError:
                return draft_error_response(
                    DraftArtifactValidationError(
                        "DRAFT_KIND_INVALID",
                        f"Unsupported draft artifact kind: {kind}",
                    )
                )
        if latest_only:
            items = draft_service.list_latest_for_posting(job_posting_id)
            if parsed_kind is not None:
                items = [item for item in items if item.kind == parsed_kind]
        else:
            items = draft_service.list_for_posting(job_posting_id, kind=parsed_kind)
        return envelope(data=[_draft_artifact_to_dict(item) for item in items])

    @app.get("/draft-artifacts/{artifact_id}")
    def get_draft_artifact(artifact_id: str):
        artifact = draft_service.get(artifact_id)
        if artifact is None:
            return JSONResponse(
                status_code=404,
                content=envelope(
                    error={
                        "code": "DRAFT_ARTIFACT_NOT_FOUND",
                        "message": f"Draft artifact '{artifact_id}' was not found.",
                    }
                ),
            )
        return envelope(data=_draft_artifact_to_dict(artifact))

    @app.get("/observability/draft-artifact-metrics")
    def draft_artifact_metrics_endpoint():
        return envelope(data=draft_metrics.snapshot_metrics())

    return app


app = create_app()
