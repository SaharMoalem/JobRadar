import pytest

from src.domain.application_tracker import TrackerState, TrackerValidationError
from src.domain.application_tracker_policy import validate_transition


def test_valid_transition_new_to_review():
    validate_transition(from_state=TrackerState.NEW, to_state=TrackerState.REVIEW)


def test_invalid_transition_new_to_submitted():
    with pytest.raises(TrackerValidationError) as exc:
        validate_transition(from_state=TrackerState.NEW, to_state=TrackerState.SUBMITTED)
    assert exc.value.code == "TRACKER_TRANSITION_INVALID"


def test_unchanged_transition_rejected():
    with pytest.raises(TrackerValidationError) as exc:
        validate_transition(from_state=TrackerState.REVIEW, to_state=TrackerState.REVIEW)
    assert exc.value.code == "TRACKER_TRANSITION_UNCHANGED"


def test_closed_can_reopen_to_review():
    validate_transition(from_state=TrackerState.CLOSED, to_state=TrackerState.REVIEW)
