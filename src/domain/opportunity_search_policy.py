from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.job_posting import JobPosting
from src.domain.lifecycle import JobLifecycleState
from src.domain.match_scoring import MatchScore
from src.domain.opportunity_search import (
    OpportunityItem,
    OpportunitySearchCriteria,
    OpportunitySearchResult,
    OpportunitySearchValidationError,
    WorkModel,
)

DEFAULT_VISIBLE_LIFECYCLE_STATES = (
    JobLifecycleState.NEW,
    JobLifecycleState.UPDATED,
    JobLifecycleState.ACTIVE,
)

WORK_MODEL_SORT_PRIORITY = {
    WorkModel.HYBRID: 0,
    WorkModel.ON_SITE: 1,
    WorkModel.REMOTE: 2,
}


def validate_search_criteria(criteria: OpportunitySearchCriteria) -> None:
    if criteria.min_score is not None and not 0 <= criteria.min_score <= 100:
        raise OpportunitySearchValidationError(
            "SEARCH_SCORE_OUT_OF_RANGE",
            "Minimum score must be between 0 and 100.",
        )
    if criteria.max_score is not None and not 0 <= criteria.max_score <= 100:
        raise OpportunitySearchValidationError(
            "SEARCH_SCORE_OUT_OF_RANGE",
            "Maximum score must be between 0 and 100.",
        )
    if (
        criteria.min_score is not None
        and criteria.max_score is not None
        and criteria.min_score > criteria.max_score
    ):
        raise OpportunitySearchValidationError(
            "SEARCH_SCORE_RANGE_INVALID",
            "Minimum score cannot exceed maximum score.",
        )
    if criteria.freshness_days is not None and criteria.freshness_days < 1:
        raise OpportunitySearchValidationError(
            "SEARCH_FRESHNESS_DAYS_INVALID",
            "Freshness window must be at least 1 day.",
        )


def extract_role_family(posting: JobPosting) -> str:
    metadata_value = posting.source_metadata.get("role_family")
    if isinstance(metadata_value, str) and metadata_value.strip():
        return metadata_value.strip().lower()
    return "general"


def extract_work_model(posting: JobPosting) -> WorkModel:
    metadata_value = posting.source_metadata.get("work_model")
    if isinstance(metadata_value, str):
        normalized = metadata_value.strip().lower().replace("-", "_")
        for model in WorkModel:
            if model.value == normalized:
                return model
    return WorkModel.ON_SITE


def _matches_role_family(posting: JobPosting, role_family: str) -> bool:
    needle = role_family.strip().lower()
    if not needle:
        return True
    return needle == extract_role_family(posting)


def _matches_location(posting: JobPosting, location: str) -> bool:
    needle = location.strip().lower()
    if not needle:
        return True
    return needle in posting.location.lower()


def _matches_freshness(posting: JobPosting, freshness_days: int, *, now: datetime) -> bool:
    if posting.posted_at is None:
        return False
    posted_at = posting.posted_at if posting.posted_at.tzinfo else posting.posted_at.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(days=freshness_days)
    return posted_at >= cutoff


def _matches_score_range(score: MatchScore | None, criteria: OpportunitySearchCriteria) -> bool:
    if criteria.min_score is None and criteria.max_score is None:
        return True
    if score is None:
        return False
    if criteria.min_score is not None and score.score < criteria.min_score:
        return False
    if criteria.max_score is not None and score.score > criteria.max_score:
        return False
    return True


def search_opportunities(
    postings: list[JobPosting],
    scores_by_id: dict[str, MatchScore],
    *,
    criteria: OpportunitySearchCriteria,
    now: datetime | None = None,
) -> OpportunitySearchResult:
    validate_search_criteria(criteria)
    evaluated_at = now or datetime.now(timezone.utc)
    allowed_states = criteria.lifecycle_states or DEFAULT_VISIBLE_LIFECYCLE_STATES

    filtered: list[OpportunityItem] = []
    for posting in postings:
        if posting.lifecycle_state not in allowed_states:
            continue
        if criteria.role_family is not None and not _matches_role_family(posting, criteria.role_family):
            continue
        if criteria.location is not None and not _matches_location(posting, criteria.location):
            continue
        work_model = extract_work_model(posting)
        if criteria.work_model is not None and work_model != criteria.work_model:
            continue
        if criteria.freshness_days is not None and not _matches_freshness(
            posting,
            criteria.freshness_days,
            now=evaluated_at,
        ):
            continue
        score = scores_by_id.get(posting.id)
        if not _matches_score_range(score, criteria):
            continue
        filtered.append(
            OpportunityItem(
                job_posting_id=posting.id,
                title=posting.title,
                company=posting.company,
                location=posting.location,
                url=posting.url,
                posted_at=posting.posted_at,
                lifecycle_state=posting.lifecycle_state,
                role_family=extract_role_family(posting),
                work_model=work_model,
                match_score=score.score if score is not None else None,
            )
        )

    sorted_items = sorted(
        filtered,
        key=lambda item: (
            WORK_MODEL_SORT_PRIORITY[item.work_model],
            -(item.match_score if item.match_score is not None else -1),
            item.job_posting_id,
        ),
    )
    return OpportunitySearchResult(
        items=tuple(sorted_items),
        total_count=len(sorted_items),
        is_empty=len(sorted_items) == 0,
        criteria=criteria,
    )
