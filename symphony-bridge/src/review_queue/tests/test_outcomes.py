"""
Unit tests for Review Outcome Handlers.

Tests verify:
- Approve flow
- Reject flow (with remediation)
- Block flow
- Unblock functionality
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
from review_queue.outcomes import (
    OutcomeHandler,
    OutcomeResult,
    ReviewResult,
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
def outcome_handler(temp_db):
    """Create an OutcomeHandler instance."""
    return OutcomeHandler()


@pytest.fixture
def approved_task(temp_db):
    """Create a sample task in approved status."""
    task_id = "task_approved_001"
    insert("tasks", {
        "id": task_id,
        "correlation_id": "corr_approved_001",
        "idempotency_key": "idem_approved_001",
        "status": "review_queued",
        "assigned_to": "SYMPHONY",
        "intent": "Implement feature",
        "payload": '{"pr_number": 42, "owner": "org", "repo": "repo"}',
        "source": "api",
    })
    return task_id


@pytest.fixture
def blocked_task(temp_db):
    """Create a sample task in blocked status."""
    task_id = "task_blocked_001"
    insert("tasks", {
        "id": task_id,
        "correlation_id": "corr_blocked_001",
        "idempotency_key": "idem_blocked_001",
        "status": "blocked",
        "assigned_to": "SYMPHONY",
        "intent": "Implement feature",
        "payload": '{"block_reason": "Critical issue"}',
        "source": "api",
    })
    return task_id


class TestHandleApprove:
    """Tests for handle_approve flow."""
    
    def test_approve_success(self, outcome_handler, approved_task):
        """Test successful approve."""
        result = outcome_handler.handle_approve(
            task_id=approved_task,
            owner="org",
            repo="repo",
            pr_number=42,
        )
        
        assert result.success is True
        assert result.action == "approve"
        assert result.task_id == approved_task
        assert result.details["status"] == "approved"
    
    def test_approve_updates_task_status(self, outcome_handler, approved_task):
        """Test that approve updates task status."""
        outcome_handler.handle_approve(task_id=approved_task)
        
        task = get_task_by_id(approved_task)
        assert task["status"] == "approved"
    
    def test_approve_sets_completed_at(self, outcome_handler, approved_task):
        """Test that approve sets completed_at timestamp."""
        outcome_handler.handle_approve(task_id=approved_task)
        
        task = get_task_by_id(approved_task)
        assert task["completed_at"] is not None
    
    def test_approve_clears_claim(self, outcome_handler, approved_task):
        """Test that approve clears claimed_by."""
        # Set as claimed
        update(
            "tasks",
            {"claimed_by": "reviewer", "claimed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")},
            "id = ?",
            (approved_task,)
        )
        
        outcome_handler.handle_approve(task_id=approved_task)
        
        task = get_task_by_id(approved_task)
        assert task["claimed_by"] is None
    
    def test_approve_nonexistent_task(self, outcome_handler):
        """Test approve with non-existent task."""
        result = outcome_handler.handle_approve(task_id="nonexistent")
        
        assert result.success is False
        assert "not found" in result.message
    
    def test_approve_creates_audit_event(self, outcome_handler, approved_task):
        """Test that approve creates audit event."""
        outcome_handler.handle_approve(task_id=approved_task)
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.outcome.approve'"
        )
        assert len(events) == 1
        assert events[0]["correlation_id"] == "corr_approved_001"


class TestHandleReject:
    """Tests for handle_reject flow."""
    
    def test_reject_success(self, outcome_handler, approved_task):
        """Test successful reject."""
        findings = [
            {"message": "Issue 1", "severity": "high"},
            {"message": "Issue 2", "severity": "medium"},
        ]
        
        result = outcome_handler.handle_reject(
            task_id=approved_task,
            findings=findings,
            owner="org",
            repo="repo",
            pr_number=42,
        )
        
        assert result.success is True
        assert result.action == "reject"
        assert result.task_id == approved_task
        assert result.details["remediation_task_id"] is not None
    
    def test_reject_updates_task_status(self, outcome_handler, approved_task):
        """Test that reject updates original task status."""
        outcome_handler.handle_reject(
            task_id=approved_task,
            findings=[{"message": "Issue"}],
        )
        
        task = get_task_by_id(approved_task)
        assert task["status"] == "review_failed"
    
    def test_reject_creates_remediation_task(self, outcome_handler, approved_task):
        """Test that reject creates a remediation task."""
        result = outcome_handler.handle_reject(
            task_id=approved_task,
            findings=[{"message": "Issue"}],
        )
        
        remediation_id = result.details["remediation_task_id"]
        remediation_task = get_task_by_id(remediation_id)
        
        assert remediation_task is not None
        assert remediation_task["status"] == "remediation_queued"
        assert remediation_task["assigned_to"] == "DEVCLAW"
        assert "Remediate:" in remediation_task["intent"]
    
    def test_remediation_task_links_original(self, outcome_handler, approved_task):
        """Test that remediation task links to original."""
        result = outcome_handler.handle_reject(
            task_id=approved_task,
            findings=[{"message": "Issue"}],
        )
        
        remediation_id = result.details["remediation_task_id"]
        remediation_task = get_task_by_id(remediation_id)
        
        import json
        payload = json.loads(remediation_task["payload"])
        assert payload["original_task_id"] == approved_task
        assert payload["is_remediation"] is True
    
    def test_reject_updates_original_payload(self, outcome_handler, approved_task):
        """Test that reject updates original task with remediation ref."""
        result = outcome_handler.handle_reject(
            task_id=approved_task,
            findings=[{"message": "Issue"}],
        )
        
        remediation_id = result.details["remediation_task_id"]
        original_task = get_task_by_id(approved_task)
        
        import json
        payload = json.loads(original_task["payload"])
        assert payload["latest_remediation_task_id"] == remediation_id
        assert payload["remediation_count"] == 1
    
    def test_reject_nonexistent_task(self, outcome_handler):
        """Test reject with non-existent task."""
        result = outcome_handler.handle_reject(
            task_id="nonexistent",
            findings=[{"message": "Issue"}],
        )
        
        assert result.success is False
        assert "not found" in result.message
    
    def test_reject_creates_audit_event(self, outcome_handler, approved_task):
        """Test that reject creates audit event."""
        outcome_handler.handle_reject(
            task_id=approved_task,
            findings=[{"message": "Issue"}],
        )
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.outcome.reject'"
        )
        assert len(events) == 1


class TestHandleBlock:
    """Tests for handle_block flow."""
    
    def test_block_success(self, outcome_handler, approved_task):
        """Test successful block."""
        result = outcome_handler.handle_block(
            task_id=approved_task,
            reason="Critical security vulnerability",
            owner="org",
            repo="repo",
            pr_number=42,
        )
        
        assert result.success is True
        assert result.action == "block"
        assert result.task_id == approved_task
        assert "Critical security vulnerability" in result.message
    
    def test_block_updates_task_status(self, outcome_handler, approved_task):
        """Test that block updates task status."""
        outcome_handler.handle_block(
            task_id=approved_task,
            reason="Critical issue",
        )
        
        task = get_task_by_id(approved_task)
        assert task["status"] == "blocked"
    
    def test_block_updates_payload(self, outcome_handler, approved_task):
        """Test that block adds reason to payload."""
        outcome_handler.handle_block(
            task_id=approved_task,
            reason="Security issue",
        )
        
        task = get_task_by_id(approved_task)
        
        import json
        payload = json.loads(task["payload"])
        assert payload["block_reason"] == "Security issue"
        assert "blocked_at" in payload
        assert payload["blocked_by"] == "symphony_reviewer"
    
    def test_block_nonexistent_task(self, outcome_handler):
        """Test block with non-existent task."""
        result = outcome_handler.handle_block(
            task_id="nonexistent",
            reason="Issue",
        )
        
        assert result.success is False
        assert "not found" in result.message
    
    def test_block_creates_audit_event(self, outcome_handler, approved_task):
        """Test that block creates audit event."""
        outcome_handler.handle_block(
            task_id=approved_task,
            reason="Critical issue",
        )
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.outcome.block'"
        )
        assert len(events) == 1


class TestUnblockTask:
    """Tests for unblock_task functionality."""
    
    def test_unblock_success(self, outcome_handler, blocked_task):
        """Test successful unblock."""
        result = outcome_handler.unblock_task(
            task_id=blocked_task,
            unblocked_by="admin",
            reason="False positive",
        )
        
        assert result.success is True
        assert result.action == "unblock"
        assert result.details["new_status"] == "review_queued"
    
    def test_unblock_updates_task_status(self, outcome_handler, blocked_task):
        """Test that unblock updates task status."""
        outcome_handler.unblock_task(
            task_id=blocked_task,
            unblocked_by="admin",
            reason="False positive",
        )
        
        task = get_task_by_id(blocked_task)
        assert task["status"] == "review_queued"
    
    def test_unblock_updates_payload(self, outcome_handler, blocked_task):
        """Test that unblock adds info to payload."""
        outcome_handler.unblock_task(
            task_id=blocked_task,
            unblocked_by="admin",
            reason="False positive",
        )
        
        task = get_task_by_id(blocked_task)
        
        import json
        payload = json.loads(task["payload"])
        assert "unblocked_at" in payload
        assert payload["unblocked_by"] == "admin"
        assert payload["unblock_reason"] == "False positive"
    
    def test_unblock_non_blocked_task(self, outcome_handler, approved_task):
        """Test unblock on non-blocked task fails."""
        result = outcome_handler.unblock_task(
            task_id=approved_task,
            unblocked_by="admin",
            reason="Test",
        )
        
        assert result.success is False
        assert "not blocked" in result.message
    
    def test_unblock_nonexistent_task(self, outcome_handler):
        """Test unblock with non-existent task."""
        result = outcome_handler.unblock_task(
            task_id="nonexistent",
            unblocked_by="admin",
            reason="Test",
        )
        
        assert result.success is False
        assert "not found" in result.message
    
    def test_unblock_creates_audit_event(self, outcome_handler, blocked_task):
        """Test that unblock creates audit event."""
        outcome_handler.unblock_task(
            task_id=blocked_task,
            unblocked_by="admin",
            reason="False positive",
        )
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'review.unblock'"
        )
        assert len(events) == 1


class TestProcessReviewResult:
    """Tests for process_review_result dispatcher."""
    
    def test_process_approve(self, outcome_handler, approved_task):
        """Test processing approve result."""
        result = outcome_handler.process_review_result(
            task_id=approved_task,
            result=ReviewResult.APPROVE,
            findings=[],
        )
        
        assert result.success is True
        assert result.action == "approve"
    
    def test_process_reject(self, outcome_handler, approved_task):
        """Test processing reject result."""
        result = outcome_handler.process_review_result(
            task_id=approved_task,
            result=ReviewResult.REJECT,
            findings=[{"message": "Issue"}],
        )
        
        assert result.success is True
        assert result.action == "reject"
    
    def test_process_block(self, outcome_handler, approved_task):
        """Test processing block result."""
        result = outcome_handler.process_review_result(
            task_id=approved_task,
            result=ReviewResult.BLOCK,
            findings=[{"message": "Critical"}],
            metadata={"block_reason": "Security"},
        )
        
        assert result.success is True
        assert result.action == "block"
    
    def test_process_unknown_result(self, outcome_handler, approved_task):
        """Test processing unknown result type."""
        result = outcome_handler.process_review_result(
            task_id=approved_task,
            result="unknown",  # type: ignore
            findings=[],
        )
        
        assert result.success is False
        assert "Unknown" in result.message
