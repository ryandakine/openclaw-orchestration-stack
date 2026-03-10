"""
Unit tests for the Review Queue Manager.

Tests verify:
- Enqueue for review functionality
- Getting next review from queue
- Review status tracking
- Queue statistics
- Audit logging
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

import sys
from pathlib import Path
# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
# Add symphony-bridge/src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.db import (
    init_pool,
    get_connection,
    transaction,
    execute,
    insert,
    update,
    get_task_by_id,
    close_pool,
)
from review_queue.queue_manager import (
    QueueManager,
    ReviewStatus,
    ReviewQueueItem,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize pool with temp database
    init_pool(db_path=db_path, max_connections=5)
    
    # Load schema
    schema_path = Path(__file__).parent.parent.parent.parent.parent / "shared" / "schemas" / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text())
        conn.commit()
    
    yield db_path
    
    # Cleanup
    close_pool()
    os.unlink(db_path)


@pytest.fixture
def queue_manager(temp_db):
    """Create a QueueManager instance."""
    return QueueManager()


@pytest.fixture
def sample_task(temp_db):
    """Create a sample task for testing."""
    task_id = "task_001"
    insert("tasks", {
        "id": task_id,
        "correlation_id": "corr_001",
        "idempotency_key": "idem_001",
        "status": "executing",
        "assigned_to": "DEVCLAW",
        "intent": "Implement feature X",
        "payload": '{"test": true}',
        "source": "api",
    })
    return task_id


class TestEnqueueForReview:
    """Tests for enqueue_for_review functionality."""
    
    def test_enqueue_success(self, queue_manager, sample_task):
        """Test successful enqueue of a task for review."""
        result = queue_manager.enqueue_for_review(
            task_id=sample_task,
            pr_number=42,
            pr_url="https://github.com/org/repo/pull/42",
            owner="org",
            repo="repo",
            branch="feature-branch",
            priority=5,
        )
        
        assert result.task_id == sample_task
        assert result.status == ReviewStatus.REVIEW_QUEUED
        assert result.pr_number == 42
        assert result.pr_url == "https://github.com/org/repo/pull/42"
        assert result.owner == "org"
        assert result.repo == "repo"
        assert result.branch == "feature-branch"
        assert result.priority == 5
        assert result.correlation_id == "corr_001"
    
    def test_enqueue_updates_task_status(self, queue_manager, sample_task):
        """Test that enqueue updates the task status."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        task = get_task_by_id(sample_task)
        assert task["status"] == "review_queued"
    
    def test_enqueue_updates_payload(self, queue_manager, sample_task):
        """Test that enqueue adds review queue metadata to payload."""
        queue_manager.enqueue_for_review(
            task_id=sample_task,
            pr_number=42,
            priority=5,
        )
        
        task = get_task_by_id(sample_task)
        payload = task["payload"]
        if isinstance(payload, str):
            import json
            payload = json.loads(payload)
        
        assert "review_queue" in payload
        assert payload["review_queue"]["pr_number"] == 42
        assert payload["review_queue"]["priority"] == 5
        assert "enqueued_at" in payload["review_queue"]
    
    def test_enqueue_nonexistent_task(self, queue_manager):
        """Test enqueue with non-existent task raises error."""
        with pytest.raises(ValueError, match="Task nonexistent not found"):
            queue_manager.enqueue_for_review(task_id="nonexistent")
    
    def test_enqueue_invalid_status(self, queue_manager, temp_db):
        """Test enqueue with invalid task status raises error."""
        insert("tasks", {
            "id": "task_invalid",
            "correlation_id": "corr_invalid",
            "idempotency_key": "idem_invalid",
            "status": "queued",  # Not executing or failed
            "assigned_to": "DEVCLAW",
            "intent": "Test",
        })
        
        with pytest.raises(ValueError, match="cannot be enqueued for review"):
            queue_manager.enqueue_for_review(task_id="task_invalid")
    
    def test_enqueue_creates_audit_event(self, queue_manager, sample_task, temp_db):
        """Test that enqueue creates an audit event."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.enqueued'"
        )
        assert len(events) == 1
        assert events[0]["correlation_id"] == "corr_001"


class TestGetNextReview:
    """Tests for get_next_review functionality."""
    
    def test_get_next_from_empty_queue(self, queue_manager, temp_db):
        """Test getting next from empty queue returns None."""
        result = queue_manager.get_next_review()
        assert result is None
    
    def test_get_next_claims_task(self, queue_manager, sample_task):
        """Test that get_next claims the task."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        result = queue_manager.get_next_review(claimed_by="test_reviewer")
        
        assert result is not None
        assert result.claimed_by == "test_reviewer"
        assert result.claimed_at is not None
    
    def test_get_next_updates_task_in_db(self, queue_manager, sample_task):
        """Test that get_next updates the task in the database."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        queue_manager.get_next_review(claimed_by="test_reviewer")
        
        task = get_task_by_id(sample_task)
        assert task["claimed_by"] == "test_reviewer"
        assert task["claimed_at"] is not None
        assert task["lease_expires_at"] is not None
    
    def test_get_next_priority_order(self, queue_manager, temp_db):
        """Test that get_next respects priority ordering."""
        # Create tasks with different priorities
        for i, priority in enumerate([1, 5, 3]):
            task_id = f"task_prio_{i}"
            insert("tasks", {
                "id": task_id,
                "correlation_id": f"corr_{i}",
                "idempotency_key": f"idem_{i}",
                "status": "review_queued",
                "assigned_to": "SYMPHONY",
                "intent": f"Task {i}",
                "payload": f'{{"review_queue": {{"priority": {priority}}}}}',
            })
        
        # Get next should return highest priority (5)
        result = queue_manager.get_next_review()
        assert result is not None
        assert result.priority == 5
        assert result.task_id == "task_prio_1"
    
    def test_get_next_skips_claimed(self, queue_manager, sample_task):
        """Test that get_next skips already claimed tasks."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        # First claim
        first = queue_manager.get_next_review(claimed_by="reviewer_1")
        assert first is not None
        
        # Second claim should return None (queue empty)
        second = queue_manager.get_next_review(claimed_by="reviewer_2")
        assert second is None
    
    def test_get_next_creates_audit_event(self, queue_manager, sample_task):
        """Test that get_next creates an audit event."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        queue_manager.get_next_review(claimed_by="test_reviewer")
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.claimed'"
        )
        assert len(events) == 1


class TestGetReviewStatus:
    """Tests for get_review_status functionality."""
    
    def test_get_status_nonexistent_task(self, queue_manager):
        """Test getting status for non-existent task returns None."""
        result = queue_manager.get_review_status("nonexistent")
        assert result is None
    
    def test_get_status_review_queued(self, queue_manager, sample_task):
        """Test getting status for review queued task."""
        queue_manager.enqueue_for_review(task_id=sample_task, pr_number=42)
        
        status = queue_manager.get_review_status(sample_task)
        
        assert status is not None
        assert status["task_id"] == sample_task
        assert status["status"] == "review_queued"
        assert status["is_review_required"] is True
        assert status["is_approved"] is False
        assert status["pr_number"] == 42
    
    def test_get_status_approved(self, queue_manager, sample_task):
        """Test getting status for approved task."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        # Manually set to approved
        update(
            "tasks",
            {"status": "approved"},
            "id = ?",
            (sample_task,)
        )
        
        status = queue_manager.get_review_status(sample_task)
        
        assert status["status"] == "approved"
        assert status["is_approved"] is True
        assert status["is_review_required"] is False
    
    def test_get_status_blocked(self, queue_manager, sample_task):
        """Test getting status for blocked task."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        # Manually set to blocked
        update(
            "tasks",
            {"status": "blocked"},
            "id = ?",
            (sample_task,)
        )
        
        status = queue_manager.get_review_status(sample_task)
        
        assert status["status"] == "blocked"
        assert status["is_blocked"] is True
    
    def test_get_status_includes_review_count(self, queue_manager, sample_task, temp_db):
        """Test that status includes review count."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        # Add some reviews
        for i in range(3):
            insert("reviews", {
                "id": f"review_{i}",
                "task_id": sample_task,
                "result": "reject",
                "summary": f"Review {i}",
                "reviewer_id": "symphony",
            })
        
        status = queue_manager.get_review_status(sample_task)
        
        assert status["review_count"] == 3
        assert status["latest_review"] is not None


class TestListPendingReviews:
    """Tests for list_pending_reviews functionality."""
    
    def test_list_empty_queue(self, queue_manager):
        """Test listing empty queue returns empty list."""
        results = queue_manager.list_pending_reviews()
        assert results == []
    
    def test_list_pending(self, queue_manager, temp_db):
        """Test listing pending reviews."""
        # Create multiple tasks
        for i in range(3):
            insert("tasks", {
                "id": f"task_list_{i}",
                "correlation_id": f"corr_{i}",
                "idempotency_key": f"idem_{i}",
                "status": "review_queued",
                "assigned_to": "SYMPHONY",
                "intent": f"Task {i}",
                "payload": '{"review_queue": {}}',
            })
        
        results = queue_manager.list_pending_reviews()
        
        assert len(results) == 3
        assert all(isinstance(r, ReviewQueueItem) for r in results)
    
    def test_list_respects_limit(self, queue_manager, temp_db):
        """Test that list respects the limit parameter."""
        for i in range(10):
            insert("tasks", {
                "id": f"task_limit_{i}",
                "correlation_id": f"corr_{i}",
                "idempotency_key": f"idem_{i}",
                "status": "review_queued",
                "assigned_to": "SYMPHONY",
                "intent": f"Task {i}",
                "payload": '{"review_queue": {}}',
            })
        
        results = queue_manager.list_pending_reviews(limit=5)
        
        assert len(results) == 5
    
    def test_list_excludes_claimed(self, queue_manager, temp_db):
        """Test that list excludes claimed tasks when specified."""
        # Create unclaimed task
        insert("tasks", {
            "id": "task_unclaimed",
            "correlation_id": "corr_1",
            "idempotency_key": "idem_1",
            "status": "review_queued",
            "assigned_to": "SYMPHONY",
            "intent": "Unclaimed",
            "payload": '{"review_queue": {}}',
        })
        
        # Create claimed task
        insert("tasks", {
            "id": "task_claimed",
            "correlation_id": "corr_2",
            "idempotency_key": "idem_2",
            "status": "review_queued",
            "assigned_to": "SYMPHONY",
            "intent": "Claimed",
            "claimed_by": "reviewer",
            "claimed_at": datetime.utcnow().isoformat(),
            "lease_expires_at": "2099-12-31 23:59:59",
            "payload": '{"review_queue": {}}',
        })
        
        results = queue_manager.list_pending_reviews(include_claimed=False)
        
        assert len(results) == 1
        assert results[0].task_id == "task_unclaimed"


class TestReleaseClaim:
    """Tests for release_claim functionality."""
    
    def test_release_claim_success(self, queue_manager, sample_task):
        """Test successful claim release."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        queue_manager.get_next_review(claimed_by="reviewer")
        
        result = queue_manager.release_claim(sample_task, released_by="admin")
        
        assert result is True
        
        task = get_task_by_id(sample_task)
        assert task["claimed_by"] is None
        assert task["claimed_at"] is None
    
    def test_release_unclaimed_task(self, queue_manager, sample_task):
        """Test releasing unclaimed task returns False."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        
        result = queue_manager.release_claim(sample_task)
        
        assert result is False
    
    def test_release_nonexistent_task(self, queue_manager):
        """Test releasing non-existent task returns False."""
        result = queue_manager.release_claim("nonexistent")
        assert result is False
    
    def test_release_creates_audit_event(self, queue_manager, sample_task):
        """Test that release creates an audit event."""
        queue_manager.enqueue_for_review(task_id=sample_task)
        queue_manager.get_next_review(claimed_by="reviewer")
        queue_manager.release_claim(sample_task, released_by="admin")
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.released'"
        )
        assert len(events) == 1


class TestQueueStatistics:
    """Tests for get_queue_statistics functionality."""
    
    def test_empty_statistics(self, queue_manager):
        """Test statistics for empty queue."""
        stats = queue_manager.get_queue_statistics()
        
        assert "by_status" in stats
        assert "claimed_count" in stats
        assert "total_pending" in stats
    
    def test_statistics_with_tasks(self, queue_manager, temp_db):
        """Test statistics with various task statuses."""
        # Create tasks with different statuses
        statuses = ["review_queued", "review_queued", "review_failed", "approved"]
        for i, status in enumerate(statuses):
            insert("tasks", {
                "id": f"task_stat_{i}",
                "correlation_id": f"corr_{i}",
                "idempotency_key": f"idem_{i}",
                "status": status,
                "assigned_to": "SYMPHONY",
                "intent": f"Task {i}",
            })
        
        stats = queue_manager.get_queue_statistics()
        
        assert stats["by_status"]["review_queued"]["count"] == 2
        assert stats["by_status"]["review_failed"]["count"] == 1
        assert stats["by_status"]["approved"]["count"] == 1
        assert stats["total_pending"] == 2
    
    def test_statistics_claimed_count(self, queue_manager, temp_db):
        """Test that statistics include claimed count."""
        # Create claimed task
        insert("tasks", {
            "id": "task_claimed",
            "correlation_id": "corr_1",
            "idempotency_key": "idem_1",
            "status": "review_queued",
            "assigned_to": "SYMPHONY",
            "intent": "Claimed",
            "claimed_by": "reviewer",
            "claimed_at": datetime.utcnow().isoformat(),
            "lease_expires_at": "2099-12-31 23:59:59",
        })
        
        stats = queue_manager.get_queue_statistics()
        
        assert stats["claimed_count"] == 1
