from __future__ import annotations

from src.domain.application_tracker import TrackerState, TrackerValidationError

ALLOWED_TRANSITIONS: dict[TrackerState, frozenset[TrackerState]] = {
    TrackerState.NEW: frozenset({TrackerState.REVIEW, TrackerState.CLOSED}),
    TrackerState.REVIEW: frozenset(
        {TrackerState.APPLY, TrackerState.REJECTED, TrackerState.CLOSED, TrackerState.NEW}
    ),
    TrackerState.APPLY: frozenset(
        {TrackerState.SUBMITTED, TrackerState.REJECTED, TrackerState.CLOSED, TrackerState.REVIEW}
    ),
    TrackerState.SUBMITTED: frozenset({TrackerState.REJECTED, TrackerState.CLOSED}),
    TrackerState.REJECTED: frozenset({TrackerState.CLOSED, TrackerState.REVIEW}),
    TrackerState.CLOSED: frozenset({TrackerState.REVIEW}),
}


def validate_transition(*, from_state: TrackerState, to_state: TrackerState) -> None:
    if from_state == to_state:
        raise TrackerValidationError(
            "TRACKER_TRANSITION_UNCHANGED",
            f"Tracker is already in state '{to_state.value}'.",
        )
    allowed = ALLOWED_TRANSITIONS.get(from_state, frozenset())
    if to_state not in allowed:
        raise TrackerValidationError(
            "TRACKER_TRANSITION_INVALID",
            f"Cannot transition from '{from_state.value}' to '{to_state.value}'.",
        )
