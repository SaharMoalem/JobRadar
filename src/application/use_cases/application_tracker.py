from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.domain.application_tracker import (
    TrackedOpportunity,
    TrackerState,
    TrackerTransition,
    TrackerValidationError,
)
from src.domain.application_tracker_policy import validate_transition
from src.ports.application_tracker_port import ApplicationTrackerRepositoryPort
from src.ports.job_posting_port import JobPostingRepositoryPort


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ApplicationTrackerUseCase:
    tracker_repository: ApplicationTrackerRepositoryPort
    job_posting_repository: JobPostingRepositoryPort

    def bookmark(
        self,
        job_posting_id: str,
        *,
        correlation_id: str = "local",
    ) -> TrackedOpportunity:
        self._require_posting(job_posting_id)
        existing = self.tracker_repository.get(job_posting_id)
        if existing is not None:
            if existing.bookmarked:
                return existing
            existing.bookmarked = True
            existing.bookmarked_at = _utc_now()
            existing.touch()
            return self.tracker_repository.save(existing)

        tracked = TrackedOpportunity(
            job_posting_id=job_posting_id,
            tracker_state=TrackerState.NEW,
            bookmarked=True,
            bookmarked_at=_utc_now(),
        )
        saved = self.tracker_repository.save(tracked)
        self.tracker_repository.append_transition(
            TrackerTransition(
                job_posting_id=job_posting_id,
                from_state=None,
                to_state=TrackerState.NEW,
                reason="bookmarked",
                correlation_id=correlation_id,
            )
        )
        return saved

    def unbookmark(self, job_posting_id: str) -> TrackedOpportunity:
        tracked = self.tracker_repository.get(job_posting_id)
        if tracked is None:
            raise TrackerValidationError(
                "TRACKER_NOT_FOUND",
                f"No tracked opportunity found for job posting '{job_posting_id}'.",
            )
        tracked.bookmarked = False
        tracked.bookmarked_at = None
        tracked.touch()
        return self.tracker_repository.save(tracked)

    def transition(
        self,
        job_posting_id: str,
        *,
        to_state: TrackerState,
        reason: str = "manual_transition",
        correlation_id: str = "local",
    ) -> TrackedOpportunity:
        tracked = self.tracker_repository.get(job_posting_id)
        if tracked is None:
            raise TrackerValidationError(
                "TRACKER_NOT_FOUND",
                f"No tracked opportunity found for job posting '{job_posting_id}'.",
            )
        validate_transition(from_state=tracked.tracker_state, to_state=to_state)
        previous = tracked.tracker_state
        tracked.tracker_state = to_state
        tracked.touch()
        saved = self.tracker_repository.save(tracked)
        self.tracker_repository.append_transition(
            TrackerTransition(
                job_posting_id=job_posting_id,
                from_state=previous,
                to_state=to_state,
                reason=reason,
                correlation_id=correlation_id,
            )
        )
        return saved

    def get(self, job_posting_id: str) -> TrackedOpportunity | None:
        return self.tracker_repository.get(job_posting_id)

    def list_tracked(self) -> list[TrackedOpportunity]:
        return self.tracker_repository.list_all()

    def list_bookmarked(self) -> list[TrackedOpportunity]:
        return self.tracker_repository.list_bookmarked()

    def list_history(self, job_posting_id: str) -> list[TrackerTransition]:
        return self.tracker_repository.list_transitions(job_posting_id)

    def _require_posting(self, job_posting_id: str) -> None:
        postings = {
            posting.id: posting for posting in self.job_posting_repository.list_complete()
        }
        if job_posting_id not in postings:
            raise TrackerValidationError(
                "TRACKER_JOB_POSTING_NOT_FOUND",
                f"Job posting '{job_posting_id}' was not found.",
            )
