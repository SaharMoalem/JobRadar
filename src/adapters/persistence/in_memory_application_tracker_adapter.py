from __future__ import annotations

from src.domain.application_tracker import TrackedOpportunity, TrackerTransition
from src.ports.application_tracker_port import ApplicationTrackerRepositoryPort


class InMemoryApplicationTrackerAdapter(ApplicationTrackerRepositoryPort):
    def __init__(self) -> None:
        self._tracked: dict[str, TrackedOpportunity] = {}
        self._transitions: list[TrackerTransition] = []

    def get(self, job_posting_id: str) -> TrackedOpportunity | None:
        return self._tracked.get(job_posting_id)

    def save(self, tracked: TrackedOpportunity) -> TrackedOpportunity:
        self._tracked[tracked.job_posting_id] = tracked
        return tracked

    def list_all(self) -> list[TrackedOpportunity]:
        return sorted(self._tracked.values(), key=lambda item: item.job_posting_id)

    def list_bookmarked(self) -> list[TrackedOpportunity]:
        return [
            item
            for item in self.list_all()
            if item.bookmarked
        ]

    def append_transition(self, transition: TrackerTransition) -> TrackerTransition:
        self._transitions.append(transition)
        return transition

    def list_transitions(self, job_posting_id: str) -> list[TrackerTransition]:
        return sorted(
            (
                transition
                for transition in self._transitions
                if transition.job_posting_id == job_posting_id
            ),
            key=lambda transition: transition.transitioned_at,
        )
