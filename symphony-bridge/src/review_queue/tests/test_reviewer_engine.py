"""
Unit tests for the Reviewer Engine.

Tests verify:
- Review task entry point
- Diff analysis
- Checklist validation
- Review result submission
- Audit logging
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

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
from review_queue.reviewer_engine import (
    ReviewerEngine,
    ReviewChecklist,
    DiffAnalysis,
    ReviewResult,
)
from review.summary import (
    ReviewFinding,
    FindingSeverity,
    FindingCategory,
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
def reviewer_engine(temp_db):
    """Create a ReviewerEngine instance."""
    return ReviewerEngine()


@pytest.fixture
def sample_task(temp_db):
    """Create a sample task in review_queued status."""
    task_id = "task_review_001"
    insert("tasks", {
        "id": task_id,
        "correlation_id": "corr_review_001",
        "idempotency_key": "idem_review_001",
        "status": "review_queued",
        "assigned_to": "SYMPHONY",
        "intent": "Implement feature X",
        "payload": '{"test": true, "review_queue": {"pr_number": 42, "owner": "org", "repo": "repo"}}',
        "source": "api",
    })
    return task_id


class TestReviewChecklist:
    """Tests for ReviewChecklist class."""
    
    def test_all_passed_true(self):
        """Test all_passed returns True when all items pass."""
        checklist = ReviewChecklist()
        assert checklist.all_passed() is True
    
    def test_all_passed_false_correctness(self):
        """Test all_passed returns False when correctness fails."""
        checklist = ReviewChecklist()
        checklist.correctness = False
        assert checklist.all_passed() is False
    
    def test_all_passed_false_security(self):
        """Test all_passed returns False when security fails."""
        checklist = ReviewChecklist()
        checklist.security = False
        assert checklist.all_passed() is False
    
    def test_get_failed_categories(self):
        """Test getting failed categories."""
        checklist = ReviewChecklist()
        checklist.correctness = False
        checklist.security = False
        
        failed = checklist.get_failed_categories()
        
        assert "correctness" in failed
        assert "security" in failed
        assert "bugs" not in failed
    
    def test_to_dict(self):
        """Test converting checklist to dictionary."""
        checklist = ReviewChecklist()
        checklist.correctness = False
        checklist.correctness_findings = ["Issue 1", "Issue 2"]
        
        result = checklist.to_dict()
        
        assert result["correctness"]["passed"] is False
        assert result["correctness"]["findings"] == ["Issue 1", "Issue 2"]
        assert result["security"]["passed"] is True


class TestDiffAnalysis:
    """Tests for DiffAnalysis class."""
    
    def test_default_values(self):
        """Test default values for DiffAnalysis."""
        analysis = DiffAnalysis()
        
        assert analysis.files_changed == []
        assert analysis.additions == 0
        assert analysis.deletions == 0
        assert analysis.has_tests is False
        assert analysis.has_documentation is False
    
    def test_to_dict(self):
        """Test converting analysis to dictionary."""
        analysis = DiffAnalysis()
        analysis.files_changed = ["file1.py", "file2.py"]
        analysis.additions = 100
        analysis.has_tests = True
        
        result = analysis.to_dict()
        
        assert result["files_changed"] == ["file1.py", "file2.py"]
        assert result["additions"] == 100
        assert result["has_tests"] is True


class TestReviewTask:
    """Tests for review_task method."""
    
    def test_review_task_not_found(self, reviewer_engine):
        """Test review with non-existent task raises error."""
        with pytest.raises(ValueError, match="Task nonexistent not found"):
            reviewer_engine.review_task("nonexistent")
    
    def test_review_task_wrong_status(self, reviewer_engine, temp_db):
        """Test review with wrong task status raises error."""
        insert("tasks", {
            "id": "task_wrong_status",
            "correlation_id": "corr",
            "idempotency_key": "idem",
            "status": "queued",  # Not review_queued
            "assigned_to": "SYMPHONY",
            "intent": "Test",
        })
        
        with pytest.raises(ValueError, match="not in review_queued status"):
            reviewer_engine.review_task("task_wrong_status")
    
    def test_review_task_creates_audit_event(self, reviewer_engine, sample_task):
        """Test that review creates audit events."""
        reviewer_engine.review_task(sample_task)
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.started'"
        )
        assert len(events) == 1
        assert events[0]["correlation_id"] == "corr_review_001"
    
    def test_review_task_creates_review_record(self, reviewer_engine, sample_task):
        """Test that review creates a review record."""
        reviewer_engine.review_task(sample_task)
        
        reviews = execute(
            "SELECT * FROM reviews WHERE task_id = ?",
            (sample_task,)
        )
        assert len(reviews) == 1
        assert reviews[0]["task_id"] == sample_task
        assert reviews[0]["reviewer_id"] == "symphony_reviewer"
    
    def test_review_task_updates_task_status_approve(self, reviewer_engine, sample_task):
        """Test that review updates task status to approved on success."""
        reviewer_engine.review_task(sample_task)
        
        task = get_task_by_id(sample_task)
        assert task["status"] == "approved"
    
    def test_review_task_with_failing_checklist(self, reviewer_engine, sample_task):
        """Test review with failing checklist."""
        # Create a failing checklist
        checklist = ReviewChecklist()
        checklist.tests = False
        checklist.test_findings = ["No tests found"]
        
        reviewer_engine.review_task(sample_task, custom_checklist=checklist)
        
        task = get_task_by_id(sample_task)
        # Should be review_failed due to failing tests
        assert task["status"] == "review_failed"


class TestChecklistValidation:
    """Tests for checklist validation logic."""
    
    def test_tests_check_no_code_changes(self, reviewer_engine):
        """Test that tests check passes when no code changes."""
        checklist = ReviewChecklist()
        analysis = DiffAnalysis()
        analysis.files_changed = ["README.md"]  # Only docs
        
        task = {"payload": "{}"}
        reviewer_engine._run_checklist_validation(task, analysis, checklist)
        
        assert checklist.tests is True
    
    def test_tests_check_missing_tests(self, reviewer_engine):
        """Test that tests check fails when code changes without tests."""
        checklist = ReviewChecklist()
        analysis = DiffAnalysis()
        analysis.files_changed = ["src/main.py", "src/utils.py"]
        analysis.has_tests = False
        
        task = {"payload": "{}"}
        reviewer_engine._run_checklist_validation(task, analysis, checklist)
        
        assert checklist.tests is False
        assert len(checklist.test_findings) == 1
    
    def test_tests_check_with_tests(self, reviewer_engine):
        """Test that tests check passes when tests exist."""
        checklist = ReviewChecklist()
        analysis = DiffAnalysis()
        analysis.files_changed = ["src/main.py", "tests/test_main.py"]
        analysis.has_tests = True
        
        task = {"payload": "{}"}
        reviewer_engine._run_checklist_validation(task, analysis, checklist)
        
        assert checklist.tests is True
    
    def test_scope_check_large_change(self, reviewer_engine):
        """Test that scope check fails for large changes."""
        checklist = ReviewChecklist()
        analysis = DiffAnalysis()
        analysis.total_lines = 1000  # Large change
        
        task = {"payload": "{}"}
        reviewer_engine._run_checklist_validation(task, analysis, checklist)
        
        assert checklist.scope is False
    
    def test_scope_check_small_change(self, reviewer_engine):
        """Test that scope check passes for small changes."""
        checklist = ReviewChecklist()
        analysis = DiffAnalysis()
        analysis.total_lines = 100  # Small change
        
        task = {"payload": "{}"}
        reviewer_engine._run_checklist_validation(task, analysis, checklist)
        
        assert checklist.scope is True


class TestWorkFinish:
    """Tests for work_finish method."""
    
    def test_work_finish_approve(self, reviewer_engine, sample_task):
        """Test work_finish with approve result."""
        from review.summary import ReviewSummary
        
        checklist = ReviewChecklist()
        summary = ReviewSummary(
            result="approve",
            summary="All good",
            findings=[],
        )
        
        result = reviewer_engine.work_finish(sample_task, ReviewResult.APPROVE, summary, checklist)
        
        assert result["result"] == "approve"
        assert result["status"] == "approved"
        
        task = get_task_by_id(sample_task)
        assert task["status"] == "approved"
    
    def test_work_finish_reject(self, reviewer_engine, sample_task):
        """Test work_finish with reject result."""
        from review.summary import ReviewSummary
        
        checklist = ReviewChecklist()
        summary = ReviewSummary(
            result="reject",
            summary="Issues found",
            findings=[],
        )
        
        result = reviewer_engine.work_finish(sample_task, ReviewResult.REJECT, summary, checklist)
        
        assert result["result"] == "reject"
        assert result["status"] == "review_failed"
        
        task = get_task_by_id(sample_task)
        assert task["status"] == "review_failed"
    
    def test_work_finish_block(self, reviewer_engine, sample_task):
        """Test work_finish with block result."""
        from review.summary import ReviewSummary
        
        checklist = ReviewChecklist()
        summary = ReviewSummary(
            result="blocked",
            summary="Critical issues",
            findings=[],
        )
        
        result = reviewer_engine.work_finish(sample_task, ReviewResult.BLOCK, summary, checklist)
        
        assert result["result"] == "blocked"
        assert result["status"] == "blocked"
        
        task = get_task_by_id(sample_task)
        assert task["status"] == "blocked"
    
    def test_work_finish_creates_audit_event(self, reviewer_engine, sample_task):
        """Test that work_finish creates audit event."""
        from review.summary import ReviewSummary
        
        checklist = ReviewChecklist()
        summary = ReviewSummary(
            result="approve",
            summary="All good",
            findings=[],
        )
        
        reviewer_engine.work_finish(sample_task, ReviewResult.APPROVE, summary, checklist)
        
        events = execute(
            "SELECT * FROM audit_events WHERE action LIKE 'review.completed.%'"
        )
        assert len(events) == 1
        assert "approve" in events[0]["action"]


class TestCheckAgainstChecklist:
    """Tests for check_against_checklist method."""
    
    def test_check_against_checklist_updates_checklist(self, reviewer_engine, sample_task):
        """Test that check_against_checklist updates the checklist."""
        checklist = ReviewChecklist()
        # Force tests to fail
        checklist.tests = False
        checklist.test_findings = ["Manual test failure"]
        
        result = reviewer_engine.check_against_checklist(sample_task, checklist)
        
        # Checklist should be updated based on validation
        assert result is checklist
    
    def test_check_against_checklist_task_not_found(self, reviewer_engine):
        """Test check with non-existent task raises error."""
        checklist = ReviewChecklist()
        
        with pytest.raises(ValueError, match="Task nonexistent not found"):
            reviewer_engine.check_against_checklist("nonexistent", checklist)
