"""
Unit tests for the Remediation Manager.

Tests verify:
- Remediation task creation
- Remediation chain tracking
- Remediation completion
- Chain resolution
- Max attempts enforcement
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
from review_queue.remediation import (
    RemediationManager,
    RemediationChain,
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
def remediation_manager(temp_db):
    """Create a RemediationManager instance."""
    return RemediationManager()


@pytest.fixture
def original_task(temp_db):
    """Create a sample original task."""
    task_id = "task_orig_001"
    insert("tasks", {
        "id": task_id,
        "correlation_id": "corr_orig_001",
        "idempotency_key": "idem_orig_001",
        "status": "review_failed",
        "assigned_to": "SYMPHONY",
        "intent": "Implement feature",
        "payload": '{"review_queue": {"pr_number": 42, "priority": 1}}',
        "source": "api",
    })
    return task_id


class TestCreateRemediationTask:
    """Tests for create_remediation_task functionality."""
    
    def test_create_remediation_success(self, remediation_manager, original_task):
        """Test successful creation of remediation task."""
        findings = [
            {"message": "Issue 1", "severity": "high"},
            {"message": "Issue 2", "severity": "medium"},
        ]
        
        result = remediation_manager.create_remediation_task(
            original_task_id=original_task,
            findings=findings,
        )
        
        assert result["original_task_id"] == original_task
        assert result["remediation_task_id"] is not None
        assert result["remediation_count"] == 1
        assert result["findings_count"] == 2
        assert result["status"] == "remediation_queued"
        assert result["assigned_to"] == "DEVCLAW"
    
    def test_create_remediation_task_exists(self, remediation_manager, original_task):
        """Test that remediation task is created in database."""
        result = remediation_manager.create_remediation_task(
            original_task_id=original_task,
            findings=[{"message": "Issue"}],
        )
        
        remediation_id = result["remediation_task_id"]
        task = get_task_by_id(remediation_id)
        
        assert task is not None
        assert task["status"] == "remediation_queued"
        assert task["assigned_to"] == "DEVCLAW"
        assert "Remediate:" in task["intent"]
    
    def test_create_remediation_increases_priority(self, remediation_manager, original_task):
        """Test that remediation has increased priority."""
        result = remediation_manager.create_remediation_task(
            original_task_id=original_task,
            findings=[{"message": "Issue"}],
            priority_adjustment=2,
        )
        
        # Original priority was 1, should be 1 + 2 + 1 = 4
        assert result["priority"] == 4
    
    def test_create_remediation_nonexistent_original(self, remediation_manager):
        """Test creation with non-existent original task."""
        with pytest.raises(ValueError, match="Original task nonexistent not found"):
            remediation_manager.create_remediation_task(
                original_task_id="nonexistent",
                findings=[{"message": "Issue"}],
            )
    
    def test_create_remediation_max_attempts(self, remediation_manager, original_task):
        """Test that max remediation attempts are enforced."""
        # Create 3 existing remediation tasks (max is 3)
        for i in range(3):
            insert("tasks", {
                "id": f"rem_{i}",
                "correlation_id": "corr_orig_001",
                "idempotency_key": f"idem_{i}",
                "status": "review_failed",
                "assigned_to": "DEVCLAW",
                "intent": "Remediate",
                "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
            })
        
        with pytest.raises(ValueError, match="Maximum remediation attempts"):
            remediation_manager.create_remediation_task(
                original_task_id=original_task,
                findings=[{"message": "Issue"}],
            )
    
    def test_create_remediation_updates_original_payload(self, remediation_manager, original_task):
        """Test that original task is updated with remediation ref."""
        result = remediation_manager.create_remediation_task(
            original_task_id=original_task,
            findings=[{"message": "Issue"}],
        )
        
        task = get_task_by_id(original_task)
        
        import json
        payload = json.loads(task["payload"])
        assert payload["latest_remediation_task_id"] == result["remediation_task_id"]
        assert payload["remediation_count"] == 1
    
    def test_create_remediation_creates_audit_event(self, remediation_manager, original_task):
        """Test that creation creates audit event."""
        remediation_manager.create_remediation_task(
            original_task_id=original_task,
            findings=[{"message": "Issue"}],
        )
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'remediation.created'"
        )
        assert len(events) == 1


class TestTrackRemediationChain:
    """Tests for track_remediation_chain functionality."""
    
    def test_track_empty_chain(self, remediation_manager, original_task):
        """Test tracking with no remediations."""
        result = remediation_manager.track_remediation_chain(original_task)
        
        assert result["original_task_id"] == original_task
        assert result["remediation_task_ids"] == []
        assert result["total_attempts"] == 0
    
    def test_track_with_remediations(self, remediation_manager, original_task):
        """Test tracking with existing remediations."""
        # Create remediation tasks
        for i in range(3):
            insert("tasks", {
                "id": f"rem_chain_{i}",
                "correlation_id": "corr_orig_001",
                "idempotency_key": f"idem_chain_{i}",
                "status": "review_failed",
                "assigned_to": "DEVCLAW",
                "intent": "Remediate",
                "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
                "created_at": f"2025-01-0{i+1}T00:00:00",
            })
        
        result = remediation_manager.track_remediation_chain(original_task)
        
        assert result["total_attempts"] == 3
        assert len(result["remediation_task_ids"]) == 3
        assert "rem_chain_0" in result["remediation_task_ids"]
    
    def test_track_nonexistent_task(self, remediation_manager):
        """Test tracking for non-existent task."""
        result = remediation_manager.track_remediation_chain("nonexistent")
        
        assert result["original_task_id"] == "nonexistent"
        assert result["current_status"] == "not_found"
        assert result["total_attempts"] == 0


class TestCompleteRemediation:
    """Tests for complete_remediation functionality."""
    
    def test_complete_success(self, remediation_manager, original_task):
        """Test successful completion."""
        # Create remediation task
        insert("tasks", {
            "id": "rem_complete",
            "correlation_id": "corr_orig_001",
            "idempotency_key": "idem_complete",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
        })
        
        result = remediation_manager.complete_remediation(
            remediation_task_id="rem_complete",
            success=True,
            pr_number=43,
        )
        
        assert result["success"] is True
        assert result["new_status"] == "review_queued"
        assert result["original_task_id"] == original_task
    
    def test_complete_success_updates_status(self, remediation_manager, original_task):
        """Test that success updates task to review_queued."""
        insert("tasks", {
            "id": "rem_complete_2",
            "correlation_id": "corr_orig_001",
            "idempotency_key": "idem_complete_2",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
        })
        
        remediation_manager.complete_remediation(
            remediation_task_id="rem_complete_2",
            success=True,
        )
        
        task = get_task_by_id("rem_complete_2")
        assert task["status"] == "review_queued"
        assert task["assigned_to"] == "SYMPHONY"
    
    def test_complete_failure(self, remediation_manager, original_task):
        """Test completion with failure."""
        insert("tasks", {
            "id": "rem_fail",
            "correlation_id": "corr_orig_001",
            "idempotency_key": "idem_fail",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
        })
        
        result = remediation_manager.complete_remediation(
            remediation_task_id="rem_fail",
            success=False,
        )
        
        assert result["success"] is False
        assert result["new_status"] == "failed"
    
    def test_complete_failure_updates_status(self, remediation_manager, original_task):
        """Test that failure marks task as failed."""
        insert("tasks", {
            "id": "rem_fail_2",
            "correlation_id": "corr_orig_001",
            "idempotency_key": "idem_fail_2",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
        })
        
        remediation_manager.complete_remediation(
            remediation_task_id="rem_fail_2",
            success=False,
        )
        
        task = get_task_by_id("rem_fail_2")
        assert task["status"] == "failed"
        assert task["completed_at"] is not None
    
    def test_complete_nonexistent_task(self, remediation_manager):
        """Test completion with non-existent task."""
        with pytest.raises(ValueError, match="Remediation task nonexistent not found"):
            remediation_manager.complete_remediation(
                remediation_task_id="nonexistent",
                success=True,
            )
    
    def test_complete_wrong_status(self, remediation_manager):
        """Test completion with wrong task status."""
        insert("tasks", {
            "id": "rem_wrong",
            "correlation_id": "corr",
            "idempotency_key": "idem_wrong",
            "status": "queued",  # Not remediation_queued
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
        })
        
        with pytest.raises(ValueError, match="not in remediation_queued status"):
            remediation_manager.complete_remediation(
                remediation_task_id="rem_wrong",
                success=True,
            )


class TestResolveRemediationChain:
    """Tests for resolve_remediation_chain functionality."""
    
    def test_resolve_success(self, remediation_manager, original_task):
        """Test successful chain resolution."""
        # Create remediation tasks
        for i in range(2):
            insert("tasks", {
                "id": f"rem_resolve_{i}",
                "correlation_id": "corr_orig_001",
                "idempotency_key": f"idem_resolve_{i}",
                "status": "review_failed",
                "assigned_to": "DEVCLAW",
                "intent": "Remediate",
                "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
            })
        
        result = remediation_manager.resolve_remediation_chain(
            original_task_id=original_task,
            final_status="approved",
        )
        
        assert result["original_task_id"] == original_task
        assert result["final_status"] == "approved"
        assert result["total_attempts"] == 2
    
    def test_resolve_updates_original_status(self, remediation_manager, original_task):
        """Test that resolution updates original task status."""
        remediation_manager.resolve_remediation_chain(
            original_task_id=original_task,
            final_status="approved",
        )
        
        task = get_task_by_id(original_task)
        assert task["status"] == "approved"
        assert task["completed_at"] is not None
    
    def test_resolve_creates_audit_event(self, remediation_manager, original_task):
        """Test that resolution creates audit event."""
        remediation_manager.resolve_remediation_chain(
            original_task_id=original_task,
            final_status="approved",
        )
        
        events = execute(
            "SELECT * FROM audit_events WHERE action = 'remediation.chain_resolved'"
        )
        assert len(events) == 1


class TestGetRemediationFindings:
    """Tests for get_remediation_findings functionality."""
    
    def test_get_findings(self, remediation_manager):
        """Test getting findings from remediation task."""
        findings = [
            {"message": "Issue 1", "severity": "high"},
            {"message": "Issue 2", "severity": "medium"},
        ]
        
        insert("tasks", {
            "id": "rem_findings",
            "correlation_id": "corr",
            "idempotency_key": "idem_findings",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": f'{{"findings": {findings}}}'.replace("'", '"'),
        })
        
        result = remediation_manager.get_remediation_findings("rem_findings")
        
        assert len(result) == 2
    
    def test_get_findings_nonexistent(self, remediation_manager):
        """Test getting findings for non-existent task."""
        result = remediation_manager.get_remediation_findings("nonexistent")
        
        assert result == []


class TestGetPendingRemediations:
    """Tests for get_pending_remediations functionality."""
    
    def test_get_pending_empty(self, remediation_manager):
        """Test getting pending when none exist."""
        result = remediation_manager.get_pending_remediations()
        
        assert result == []
    
    def test_get_pending(self, remediation_manager, original_task):
        """Test getting pending remediations."""
        # Create pending remediation tasks
        for i in range(3):
            insert("tasks", {
                "id": f"rem_pending_{i}",
                "correlation_id": "corr_orig_001",
                "idempotency_key": f"idem_pending_{i}",
                "status": "remediation_queued",
                "assigned_to": "DEVCLAW",
                "intent": f"Remediate {i}",
                "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true, "priority": {i}}}',
            })
        
        result = remediation_manager.get_pending_remediations()
        
        assert len(result) == 3
        assert all(r["status"] == "remediation_queued" for r in result)
    
    def test_get_pending_filter_by_assigned(self, remediation_manager):
        """Test filtering by assigned_to."""
        insert("tasks", {
            "id": "rem_pending_dev",
            "correlation_id": "corr",
            "idempotency_key": "idem_pending_dev",
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
            "intent": "Remediate",
            "payload": '{}',
        })
        
        insert("tasks", {
            "id": "rem_pending_sym",
            "correlation_id": "corr",
            "idempotency_key": "idem_pending_sym",
            "status": "remediation_queued",
            "assigned_to": "SYMPHONY",
            "intent": "Remediate",
            "payload": '{}',
        })
        
        result = remediation_manager.get_pending_remediations(assigned_to="DEVCLAW")
        
        assert len(result) == 1
        assert result[0]["task_id"] == "rem_pending_dev"
    
    def test_get_pending_respects_limit(self, remediation_manager, original_task):
        """Test that limit is respected."""
        for i in range(10):
            insert("tasks", {
                "id": f"rem_limit_{i}",
                "correlation_id": "corr_orig_001",
                "idempotency_key": f"idem_limit_{i}",
                "status": "remediation_queued",
                "assigned_to": "DEVCLAW",
                "intent": f"Remediate {i}",
                "payload": f'{{"original_task_id": "{original_task}", "is_remediation": true}}',
            })
        
        result = remediation_manager.get_pending_remediations(limit=5)
        
        assert len(result) == 5
