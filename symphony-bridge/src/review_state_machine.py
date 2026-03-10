"""
Review State Machine for OpenClaw Mandatory Review Queue.

Defines the state transitions for the review workflow:
- review_queued → approved (on approve)
- review_queued → review_failed → remediation_queued (on reject)
- review_queued → blocked (on block)
"""

from enum import Enum
from typing import Set, Dict, List


class ReviewState(str, Enum):
    """Review queue states."""
    REVIEW_QUEUED = "review_queued"
    APPROVED = "approved"
    REVIEW_FAILED = "review_failed"
    REMEDIATION_QUEUED = "remediation_queued"
    BLOCKED = "blocked"


class ReviewResult(str, Enum):
    """Review decision results."""
    APPROVE = "approve"
    REJECT = "reject"
    BLOCK = "blocked"  # Matches schema CHECK constraint


# Valid state transitions
# Format: {current_state: {result: next_state}}
STATE_TRANSITIONS: Dict[ReviewState, Dict[ReviewResult, ReviewState]] = {
    ReviewState.REVIEW_QUEUED: {
        ReviewResult.APPROVE: ReviewState.APPROVED,
        ReviewResult.REJECT: ReviewState.REVIEW_FAILED,
        ReviewResult.BLOCK: ReviewState.BLOCKED,
    },
    ReviewState.REVIEW_FAILED: {
        # After review failure, remediation is queued
        # This is an automatic transition, not a review result
    },
}


def get_next_state(current_state: ReviewState, result: ReviewResult) -> ReviewState:
    """
    Get the next state based on current state and review result.
    
    Args:
        current_state: The current review state
        result: The review result (approve/reject/block)
        
    Returns:
        The next state
        
    Raises:
        ValueError: If the transition is not valid
    """
    transitions = STATE_TRANSITIONS.get(current_state, {})
    next_state = transitions.get(result)
    
    if next_state is None:
        raise ValueError(
            f"Invalid transition from {current_state.value} with result {result.value}"
        )
    
    return next_state


def is_valid_transition(current_state: ReviewState, result: ReviewResult) -> bool:
    """Check if a transition is valid."""
    transitions = STATE_TRANSITIONS.get(current_state, {})
    return result in transitions


def get_allowed_results(current_state: ReviewState) -> List[ReviewResult]:
    """Get the allowed review results for a given state."""
    transitions = STATE_TRANSITIONS.get(current_state, {})
    return list(transitions.keys())
