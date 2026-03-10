"""
Tests for the simplified review queue system.

Key test scenarios:
- Task moves from executing → review_queued when DevClaw completes
- Approve moves to approved
- Reject creates remediation task
"""

import os
import sys
import json
import pytest
import tempfile
import sqlite3
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.db import init_pool, close_pool, execute, get_task_by_id, insert
# Add symphony-bridge/src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from review_state_machine import ReviewState, ReviewResult, get_next_state
from core_review_queue import ReviewQueue


@pytest.fixture
def db_path():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def db(db_path):
    """Initialize the database with schema."""
    # Initialize the connection pool with test db
    init_pool(db_path=db_path)
    
    # Create schema
    schema_path = project_root / "shared" / "schemas" / "schema.sql"
    with open(schema_path, "r") as f:
        schema = f.read()
    
    from shared.db import get_connection
    with get_connection() as conn:
        conn.executescript(schema)
    
    yield
    
    # Cleanup
    close_pool()


@pytest.fixture
def review_queue(db):
    """Create a review queue instance."""
    return ReviewQueue()


def create_task(task_id: str, status: str = "executing", intent: str = "Test task") -> str:
    """Helper to create a task in the database."""
    correlation_id = f"corr-{task_id}"
    insert("tasks", {
        "id": task_id,
        "correlation_id": correlation_id,
        "idempotency_key": f"idem-{task_id}",
        "status": status,
        "assigned_to": "DEVCLAW",
        "intent": intent,
        "payload": json.dumps({"test": True}),
        "source": "api",
        "requested_by": "test",
    })
    return correlation_id


class TestEnqueueForReview:
    """Test: Task moves from executing → review_queued when DevClaw completes."""
    
    def test_enqueue_moves_executing_to_review_queued(self, review_queue):
        """Task in 'executing' state moves to 'review_queued'."""
        task_id = "task-001"
        create_task(task_id, status="executing")
        
        # Enqueue for review
        review_queue.enqueue_for_review(task_id)
        
        # Verify state change
        task = get_task_by_id(task_id)
        assert task["status"] == "review_queued"
    
    def test_enqueue_non_executing_task_fails(self, review_queue):
        """Cannot enqueue a task that is not in 'executing' state."""
        task_id = "task-002"
        create_task(task_id, status="queued")
        
        with pytest.raises(ValueError, match="must be in 'executing' state"):
            review_queue.enqueue_for_review(task_id)
    
    def test_enqueue_nonexistent_task_fails(self, review_queue):
        """Cannot enqueue a task that doesn't exist."""
        with pytest.raises(ValueError, match="not found"):
            review_queue.enqueue_for_review("nonexistent-task")


class TestGetNextForReview:
    """Test getting the next task from the queue."""
    
    def test_get_next_returns_oldest_task(self, review_queue):
        """Returns the oldest review_queued task."""
        # Create tasks in order
        create_task("task-003", status="review_queued")
        create_task("task-004", status="review_queued")
        
        next_task = review_queue.get_next_for_review()
        assert next_task == "task-003"  # Oldest first
    
    def test_get_next_empty_queue_returns_none(self, review_queue):
        """Returns None when queue is empty."""
        result = review_queue.get_next_for_review()
        assert result is None
    
    def test_get_next_skips_claimed_tasks(self, review_queue):
        """Skips tasks that are currently claimed."""
        create_task("task-005", status="review_queued")
        
        # Claim the task
        from shared.db import transaction
        with transaction() as conn:
            conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = 'reviewer-1', 
                    lease_expires_at = datetime('now', '+30 minutes')
                WHERE id = ?
                """,
                ("task-005",)
            )
        
        # Should return None since task is claimed
        result = review_queue.get_next_for_review()
        assert result is None


class TestSubmitReviewApprove:
    """Test: Approve moves to approved."""
    
    def test_approve_moves_to_approved_state(self, review_queue):
        """Approved review moves task to 'approved' state."""
        task_id = "task-006"
        create_task(task_id, status="review_queued")
        
        result = review_queue.submit_review(
            task_id=task_id,
            result="approve",
            summary="Looks good!"
        )
        
        # Verify result
        assert result["success"] is True
        assert result["action"] == "approve"
        assert result["new_state"] == "approved"
        
        # Verify task state
        task = get_task_by_id(task_id)
        assert task["status"] == "approved"
        assert task["completed_at"] is not None
    
    def test_approve_creates_review_record(self, review_queue):
        """Approve creates a review record in the database."""
        task_id = "task-007"
        create_task(task_id, status="review_queued")
        
        review_queue.submit_review(
            task_id=task_id,
            result="approve",
            summary="LGTM"
        )
        
        # Verify review record
        reviews = execute("SELECT * FROM reviews WHERE task_id = ?", (task_id,))
        assert len(reviews) == 1
        assert reviews[0]["result"] == "approve"
        assert reviews[0]["summary"] == "LGTM"


class TestSubmitReviewReject:
    """Test: Reject creates remediation task."""
    
    def test_reject_moves_to_review_failed(self, review_queue):
        """Rejected review moves task to 'review_failed' state."""
        task_id = "task-008"
        create_task(task_id, status="review_queued")
        
        result = review_queue.submit_review(
            task_id=task_id,
            result="reject",
            summary="Needs fixes",
            findings=[{"issue": "bug", "severity": "high"}]
        )
        
        # Verify result
        assert result["success"] is True
        assert result["action"] == "reject"
        assert result["new_state"] == "review_failed"
        
        # Verify task state
        task = get_task_by_id(task_id)
        assert task["status"] == "review_failed"
    
    def test_reject_creates_remediation_task(self, review_queue):
        """Reject creates a new remediation task for DevClaw."""
        task_id = "task-009"
        create_task(task_id, status="review_queued", intent="Fix the bug")
        
        result = review_queue.submit_review(
            task_id=task_id,
            result="reject",
            summary="Found issues",
            findings=[{"issue": "typo"}]
        )
        
        # Verify remediation task was created
        remediation_id = result.get("remediation_task_id")
        assert remediation_id is not None
        
        remediation_task = get_task_by_id(remediation_id)
        assert remediation_task is not None
        assert remediation_task["status"] == "remediation_queued"
        assert remediation_task["assigned_to"] == "DEVCLAW"
        assert "Remediate:" in remediation_task["intent"]
        
        # Verify payload
        payload = json.loads(remediation_task["payload"])
        assert payload["original_task_id"] == task_id
        assert payload["is_remediation"] is True
        assert len(payload["findings"]) == 1


class TestSubmitReviewBlock:
    """Test block outcome."""
    
    def test_block_moves_to_blocked_state(self, review_queue):
        """Block review moves task to 'blocked' state."""
        task_id = "task-010"
        create_task(task_id, status="review_queued")
        
        result = review_queue.submit_review(
            task_id=task_id,
            result="blocked",
            summary="Critical security issue"
        )
        
        # Verify result
        assert result["success"] is True
        assert result["action"] == "blocked"
        assert result["new_state"] == "blocked"
        
        # Verify task state
        task = get_task_by_id(task_id)
        assert task["status"] == "blocked"


class TestGetReviewStatus:
    """Test getting review status."""
    
    def test_get_status_for_pending_review(self, review_queue):
        """Get status for task waiting for review."""
        task_id = "task-011"
        create_task(task_id, status="review_queued")
        
        status = review_queue.get_review_status(task_id)
        
        assert status["task_id"] == task_id
        assert status["status"] == "review_queued"
        assert status["is_review_required"] is True
        assert status["is_approved"] is False
    
    def test_get_status_for_approved_task(self, review_queue):
        """Get status for approved task."""
        task_id = "task-012"
        create_task(task_id, status="review_queued")
        
        review_queue.submit_review(task_id, "approve", "Good")
        
        status = review_queue.get_review_status(task_id)
        
        assert status["is_review_required"] is False
        assert status["is_approved"] is True
        assert status["review_count"] == 1
    
    def test_get_status_nonexistent_task(self, review_queue):
        """Get status for nonexistent task returns None."""
        status = review_queue.get_review_status("nonexistent")
        assert status is None


class TestStateMachine:
    """Test state machine transitions."""
    
    def test_review_queued_to_approved(self):
        """review_queued → approved on approve."""
        next_state = get_next_state(ReviewState.REVIEW_QUEUED, ReviewResult.APPROVE)
        assert next_state == ReviewState.APPROVED
    
    def test_review_queued_to_review_failed(self):
        """review_queued → review_failed on reject."""
        next_state = get_next_state(ReviewState.REVIEW_QUEUED, ReviewResult.REJECT)
        assert next_state == ReviewState.REVIEW_FAILED
    
    def test_review_queued_to_blocked(self):
        """review_queued → blocked on block."""
        next_state = get_next_state(ReviewState.REVIEW_QUEUED, ReviewResult.BLOCK)
        assert next_state == ReviewState.BLOCKED
    
    def test_invalid_transition_raises_error(self):
        """Invalid transition raises ValueError."""
        with pytest.raises(ValueError):
            get_next_state(ReviewState.APPROVED, ReviewResult.REJECT)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
