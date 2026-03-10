"""
Unit tests for database schema validation.

Tests verify:
- Table creation and structure
- Column constraints and types
- Index existence
- Foreign key relationships
- CRUD operations
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path

# Add project root to path
import sys
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


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize pool with temp database
    init_pool(db_path=db_path, max_connections=5)
    
    # Load schema
    schema_path = Path(__file__).parent.parent.parent / "shared" / "schemas" / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text())
        conn.commit()
    
    yield db_path
    
    # Cleanup
    close_pool()
    os.unlink(db_path)


class TestTasksTable:
    """Tests for the tasks table schema."""
    
    def test_tasks_table_exists(self, temp_db):
        """Verify tasks table exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'",
            fetch_one=True
        )
        assert result is not None
        assert result["name"] == "tasks"
    
    def test_tasks_columns(self, temp_db):
        """Verify tasks table has correct columns."""
        columns = execute("PRAGMA table_info(tasks)")
        column_names = {col["name"] for col in columns}
        
        expected_columns = {
            "id", "correlation_id", "status", "assigned_to",
            "claimed_by", "claimed_at", "lease_expires_at",
            "retry_count", "payload", "created_at", "updated_at"
        }
        
        assert column_names == expected_columns
    
    def test_tasks_primary_key(self, temp_db):
        """Verify tasks.id is primary key."""
        columns = execute("PRAGMA table_info(tasks)")
        id_column = next(col for col in columns if col["name"] == "id")
        assert id_column["pk"] == 1
    
    def test_tasks_status_constraint(self, temp_db):
        """Verify tasks.status has CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            insert("tasks", {
                "id": "test_001",
                "correlation_id": "corr_001",
                "status": "invalid_status",
                "assigned_to": "DEVCLAW"
            })
    
    def test_tasks_assigned_to_constraint(self, temp_db):
        """Verify tasks.assigned_to has CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            insert("tasks", {
                "id": "test_002",
                "correlation_id": "corr_002",
                "status": "queued",
                "assigned_to": "INVALID_WORKER"
            })
    
    def test_tasks_valid_status_values(self, temp_db):
        """Verify all valid status values are accepted."""
        valid_statuses = ["queued", "executing", "review_queued", "approved", "merged", "failed", "blocked"]
        
        for i, status in enumerate(valid_statuses):
            insert("tasks", {
                "id": f"test_status_{i}",
                "correlation_id": f"corr_{i}",
                "status": status,
                "assigned_to": "DEVCLAW"
            })
        
        results = execute("SELECT COUNT(*) as count FROM tasks")
        assert results[0]["count"] == len(valid_statuses)
    
    def test_tasks_default_retry_count(self, temp_db):
        """Verify tasks.retry_count defaults to 0."""
        insert("tasks", {
            "id": "test_default",
            "correlation_id": "corr_default",
            "status": "queued",
            "assigned_to": "DEVCLAW"
        })
        
        task = get_task_by_id("test_default")
        assert task["retry_count"] == 0
    
    def test_tasks_created_at_default(self, temp_db):
        """Verify tasks.created_at has default value."""
        insert("tasks", {
            "id": "test_timestamp",
            "correlation_id": "corr_ts",
            "status": "queued",
            "assigned_to": "DEVCLAW"
        })
        
        task = get_task_by_id("test_timestamp")
        assert task["created_at"] is not None


class TestReviewsTable:
    """Tests for the reviews table schema."""
    
    def test_reviews_table_exists(self, temp_db):
        """Verify reviews table exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'",
            fetch_one=True
        )
        assert result is not None
        assert result["name"] == "reviews"
    
    def test_reviews_columns(self, temp_db):
        """Verify reviews table has correct columns."""
        columns = execute("PRAGMA table_info(reviews)")
        column_names = {col["name"] for col in columns}
        
        expected_columns = {
            "id", "task_id", "result", "summary",
            "findings", "reviewer_id", "created_at"
        }
        
        assert column_names == expected_columns
    
    def test_reviews_foreign_key(self, temp_db):
        """Verify reviews.task_id has foreign key constraint."""
        # First create a task
        insert("tasks", {
            "id": "task_for_review",
            "correlation_id": "corr_review",
            "status": "review_queued",
            "assigned_to": "SYMPHONY"
        })
        
        # Then create a review referencing it
        insert("reviews", {
            "id": "review_001",
            "task_id": "task_for_review",
            "result": "approve"
        })
        
        review = execute(
            "SELECT * FROM reviews WHERE id = ?",
            ("review_001",),
            fetch_one=True
        )
        assert review["task_id"] == "task_for_review"
    
    def test_reviews_result_constraint(self, temp_db):
        """Verify reviews.result has CHECK constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            insert("reviews", {
                "id": "review_invalid",
                "task_id": "task_for_review",
                "result": "invalid_result"
            })
    
    def test_reviews_valid_results(self, temp_db):
        """Verify all valid result values are accepted."""
        valid_results = ["approve", "reject", "blocked"]
        
        for i, result in enumerate(valid_results):
            task_id = f"task_result_{i}"
            insert("tasks", {
                "id": task_id,
                "correlation_id": f"corr_{i}",
                "status": "review_queued",
                "assigned_to": "SYMPHONY"
            })
            
            insert("reviews", {
                "id": f"review_{result}",
                "task_id": task_id,
                "result": result
            })
        
        results = execute("SELECT COUNT(*) as count FROM reviews")
        assert results[0]["count"] == len(valid_results)
    
    def test_reviews_cascade_delete(self, temp_db):
        """Verify reviews are deleted when task is deleted."""
        # Create task and review
        insert("tasks", {
            "id": "task_cascade",
            "correlation_id": "corr_cascade",
            "status": "review_queued",
            "assigned_to": "SYMPHONY"
        })
        
        insert("reviews", {
            "id": "review_cascade",
            "task_id": "task_cascade",
            "result": "approve"
        })
        
        # Delete task
        with transaction() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", ("task_cascade",))
        
        # Verify review is gone
        review = execute(
            "SELECT * FROM reviews WHERE id = ?",
            ("review_cascade",),
            fetch_one=True
        )
        assert review is None


class TestAuditEventsTable:
    """Tests for the audit_events table schema."""
    
    def test_audit_events_table_exists(self, temp_db):
        """Verify audit_events table exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'",
            fetch_one=True
        )
        assert result is not None
        assert result["name"] == "audit_events"
    
    def test_audit_events_columns(self, temp_db):
        """Verify audit_events table has correct columns."""
        columns = execute("PRAGMA table_info(audit_events)")
        column_names = {col["name"] for col in columns}
        
        expected_columns = {
            "id", "correlation_id", "timestamp",
            "actor", "action", "payload"
        }
        
        assert column_names == expected_columns
    
    def test_audit_events_required_fields(self, temp_db):
        """Verify audit_events required fields work correctly."""
        insert("audit_events", {
            "id": "audit_001",
            "correlation_id": "corr_audit",
            "actor": "openclaw",
            "action": "task_created"
        })
        
        event = execute(
            "SELECT * FROM audit_events WHERE id = ?",
            ("audit_001",),
            fetch_one=True
        )
        assert event["actor"] == "openclaw"
        assert event["action"] == "task_created"


class TestIndexes:
    """Tests for database indexes."""
    
    def test_tasks_status_index(self, temp_db):
        """Verify tasks status index exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_status'",
            fetch_one=True
        )
        assert result is not None
    
    def test_tasks_correlation_id_index(self, temp_db):
        """Verify tasks correlation_id index exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_correlation_id'",
            fetch_one=True
        )
        assert result is not None
    
    def test_tasks_lease_expires_at_index(self, temp_db):
        """Verify tasks lease_expires_at index exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_lease_expires_at'",
            fetch_one=True
        )
        assert result is not None
    
    def test_reviews_task_id_index(self, temp_db):
        """Verify reviews task_id index exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_reviews_task_id'",
            fetch_one=True
        )
        assert result is not None
    
    def test_audit_correlation_id_index(self, temp_db):
        """Verify audit correlation_id index exists."""
        result = execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_audit_correlation_id'",
            fetch_one=True
        )
        assert result is not None


class TestJSONColumns:
    """Tests for JSON column functionality."""
    
    def test_tasks_payload_json(self, temp_db):
        """Verify tasks payload accepts JSON data."""
        payload = '{"key": "value", "nested": {"a": 1}}'
        
        insert("tasks", {
            "id": "test_json",
            "correlation_id": "corr_json",
            "status": "queued",
            "assigned_to": "DEVCLAW",
            "payload": payload
        })
        
        task = get_task_by_id("test_json")
        assert task["payload"] == payload
    
    def test_reviews_findings_json(self, temp_db):
        """Verify reviews findings accepts JSON data."""
        # Create task first
        insert("tasks", {
            "id": "task_json_review",
            "correlation_id": "corr_json",
            "status": "review_queued",
            "assigned_to": "SYMPHONY"
        })
        
        findings = '[{"severity": "critical", "message": "Test finding"}]'
        
        insert("reviews", {
            "id": "review_json",
            "task_id": "task_json_review",
            "result": "reject",
            "findings": findings
        })
        
        review = execute(
            "SELECT * FROM reviews WHERE id = ?",
            ("review_json",),
            fetch_one=True
        )
        assert review["findings"] == findings


class TestConcurrency:
    """Tests for concurrent access patterns."""
    
    def test_wal_mode_enabled(self, temp_db):
        """Verify WAL mode is enabled."""
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            result = cursor.fetchone()
            assert result[0] == "wal"
    
    def test_foreign_keys_enabled(self, temp_db):
        """Verify foreign keys are enabled."""
        with get_connection() as conn:
            cursor = conn.execute("PRAGMA foreign_keys")
            result = cursor.fetchone()
            assert result[0] == 1


class TestCRUDOperations:
    """Tests for basic CRUD operations via db module."""
    
    def test_insert_and_fetch(self, temp_db):
        """Test insert and fetch operations."""
        insert("tasks", {
            "id": "crud_test",
            "correlation_id": "crud_corr",
            "status": "queued",
            "assigned_to": "DEVCLAW"
        })
        
        task = get_task_by_id("crud_test")
        assert task is not None
        assert task["id"] == "crud_test"
    
    def test_update(self, temp_db):
        """Test update operation."""
        insert("tasks", {
            "id": "update_test",
            "correlation_id": "update_corr",
            "status": "queued",
            "assigned_to": "DEVCLAW"
        })
        
        update(
            "tasks",
            {"status": "executing", "claimed_by": "worker_1"},
            "id = ?",
            ("update_test",)
        )
        
        task = get_task_by_id("update_test")
        assert task["status"] == "executing"
        assert task["claimed_by"] == "worker_1"
    
    def test_transaction_rollback(self, temp_db):
        """Test transaction rollback on error."""
        try:
            with transaction() as conn:
                conn.execute("""
                    INSERT INTO tasks (id, correlation_id, status, assigned_to)
                    VALUES (?, ?, ?, ?)
                """, ("rollback_test", "corr", "queued", "DEVCLAW"))
                
                # Force an error
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Verify record was not created
        task = get_task_by_id("rollback_test")
        assert task is None
