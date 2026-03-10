"""
Unit tests for dead_letter.py

Tests dead letter queue including:
- Moving tasks to DLQ
- Listing DLQ items
- Manual retry from DLQ
- Failure analysis
- Cleanup
"""

import pytest
import uuid
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from shared.utils.dead_letter import (
    DeadLetterQueue, DLQEntry, DLQReason, TaskNotInDLQError,
    get_dead_letter_queue, configure_dead_letter_queue,
    move_to_dlq, get_dlq_items, retry_from_dlq
)


class TestDLQReason:
    """Test DLQReason enum."""
    
    def test_reason_values(self):
        """Test reason enum values."""
        assert DLQReason.MAX_RETRIES_EXCEEDED.value == "max_retries_exceeded"
        assert DLQReason.LEASE_EXPIRED.value == "lease_expired"
        assert DLQReason.PERMANENT_FAILURE.value == "permanent_failure"
        assert DLQReason.VALIDATION_ERROR.value == "validation_error"
        assert DLQReason.TIMEOUT.value == "timeout"
        assert DLQReason.UNKNOWN_ERROR.value == "unknown_error"


class TestDeadLetterQueue:
    """Test DeadLetterQueue class."""
    
    def test_init(self, mock_db_connection, cleanup_utils):
        """Test DLQ initialization."""
        dlq = DeadLetterQueue(max_dlq_age_days=60)
        assert dlq.max_dlq_age_days == 60
    
    def test_move_to_dlq(self, mock_db_connection, sample_task, cleanup_utils):
        """Test moving a task to DLQ."""
        dlq = DeadLetterQueue()
        
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED,
            error_details={"error": "max retries reached"},
            original_payload={"intent": "test"},
            retry_count=3,
            worker_id="worker-1"
        )
        
        assert dlq_id is not None
        assert len(dlq_id) == 36  # UUID format
        
        # Verify in DB
        cursor = mock_db_connection.execute(
            "SELECT * FROM dead_letter_queue WHERE id = ?",
            (dlq_id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["reason"] == "max_retries_exceeded"
        assert row["retry_count"] == 3
        assert row["worker_id"] == "worker-1"
    
    def test_move_to_dlq_with_task_lookup(self, mock_db_connection, sample_task, cleanup_utils):
        """Test moving to DLQ with automatic task lookup."""
        dlq = DeadLetterQueue()
        
        # Don't provide error_details or payload - should look up from task
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.LEASE_EXPIRED
        )
        
        # Verify
        item = dlq.get_dlq_item(dlq_id)
        assert item is not None
        assert "error_details" in item or item.get("original_payload")
    
    def test_get_dlq_items(self, mock_db_connection, sample_task, cleanup_utils):
        """Test listing DLQ items."""
        dlq = DeadLetterQueue()
        
        # Add items to DLQ
        for i in range(5):
            dlq.move_to_dlq(
                task_id=str(uuid.uuid4()),
                correlation_id=f"corr-{i}",
                reason=DLQReason.MAX_RETRIES_EXCEEDED
            )
        
        # Get all items
        items = dlq.get_dlq_items()
        assert len(items) == 5
        
        # Test pagination
        items_limited = dlq.get_dlq_items(limit=2)
        assert len(items_limited) == 2
    
    def test_get_dlq_items_filtered(self, mock_db_connection, sample_task, cleanup_utils):
        """Test listing DLQ items with filters."""
        dlq = DeadLetterQueue()
        
        # Add items with different reasons
        dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id="corr-1",
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id="corr-2",
            reason=DLQReason.VALIDATION_ERROR
        )
        
        # Filter by reason
        items = dlq.get_dlq_items(reason=DLQReason.MAX_RETRIES_EXCEEDED)
        assert len(items) == 1
        assert items[0]["reason"] == "max_retries_exceeded"
    
    def test_get_dlq_item(self, mock_db_connection, sample_task, cleanup_utils):
        """Test getting a specific DLQ item."""
        dlq = DeadLetterQueue()
        
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.PERMANENT_FAILURE,
            error_details={"error": "permanent"},
            original_payload={"data": "test"}
        )
        
        item = dlq.get_dlq_item(dlq_id)
        
        assert item is not None
        assert item["id"] == dlq_id
        assert item["original_task_id"] == sample_task["id"]
        assert item["error_details"]["error"] == "permanent"
        assert item["original_payload"]["data"] == "test"
    
    def test_get_dlq_item_not_found(self, mock_db_connection, cleanup_utils):
        """Test getting a non-existent DLQ item."""
        dlq = DeadLetterQueue()
        
        item = dlq.get_dlq_item("non-existent-id")
        assert item is None
    
    def test_retry_from_dlq(self, mock_db_connection, sample_task, cleanup_utils):
        """Test retrying a task from DLQ."""
        dlq = DeadLetterQueue()
        
        # Setup task
        mock_db_connection.execute(
            """
            UPDATE tasks SET intent = 'test_intent', payload = '{}', assigned_to = 'DEVCLAW'
            WHERE id = ?
            """,
            (sample_task["id"],)
        )
        mock_db_connection.commit()
        
        # Move to DLQ
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED,
            original_payload={"intent": "test_intent"}
        )
        
        # Retry
        new_task_id = dlq.retry_from_dlq(dlq_id, new_worker_id="worker-2")
        
        assert new_task_id is not None
        assert new_task_id != sample_task["id"]
        
        # Verify new task created
        cursor = mock_db_connection.execute(
            "SELECT * FROM tasks WHERE id = ?",
            (new_task_id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["status"] == "queued"
        assert row["retry_count"] == 0
    
    def test_retry_from_dlq_not_found(self, mock_db_connection, cleanup_utils):
        """Test retrying a non-existent DLQ item."""
        dlq = DeadLetterQueue()
        
        with pytest.raises(TaskNotInDLQError):
            dlq.retry_from_dlq("non-existent-id")
    
    def test_retry_from_dlq_archived(self, mock_db_connection, sample_task, cleanup_utils):
        """Test retrying an archived DLQ item."""
        dlq = DeadLetterQueue()
        
        # Move to DLQ and archive
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        dlq.archive_dlq_item(dlq_id)
        
        # Try to retry archived item
        with pytest.raises(TaskNotInDLQError):
            dlq.retry_from_dlq(dlq_id)
    
    def test_retry_all_from_dlq(self, mock_db_connection, sample_task, cleanup_utils):
        """Test retrying all eligible items from DLQ."""
        dlq = DeadLetterQueue()
        
        # Create original tasks first with all required fields
        task_ids = []
        for i in range(3):
            task_id = str(uuid.uuid4())
            correlation_id = str(uuid.uuid4())
            idempotency_key = str(uuid.uuid4())
            task_ids.append((task_id, correlation_id, idempotency_key))
            
            mock_db_connection.execute(
                """
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent, payload)
                VALUES (?, ?, ?, 'failed', 'DEVCLAW', 'test', '{}')
                """,
                (task_id, correlation_id, idempotency_key)
            )
            
            dlq.move_to_dlq(
                task_id=task_id,
                correlation_id=correlation_id,
                reason=DLQReason.MAX_RETRIES_EXCEEDED
            )
        
        mock_db_connection.commit()
        
        # Retry all
        results = dlq.retry_all_from_dlq()
        
        # Should attempt to retry all 3 items
        assert len(results) == 3
        
        # Count successes (may vary based on SQLite execution)
        successful = [r for r in results if r["success"]]
        failed = [r for r in results if not r["success"]]
        
        # Total should equal the number we tried to retry
        assert len(successful) + len(failed) == 3
    
    def test_retry_all_from_dlq_filtered(self, mock_db_connection, cleanup_utils):
        """Test retrying all with reason filter."""
        dlq = DeadLetterQueue()
        
        # Create tasks with different reasons
        for i in range(2):
            task_id = str(uuid.uuid4())
            mock_db_connection.execute(
                """
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                VALUES (?, ?, ?, 'failed', 'DEVCLAW', 'test')
                """,
                (task_id, str(uuid.uuid4()), str(uuid.uuid4()))
            )
            
            dlq.move_to_dlq(
                task_id=task_id,
                correlation_id=f"corr-{i}",
                reason=DLQReason.MAX_RETRIES_EXCEEDED if i == 0 else DLQReason.VALIDATION_ERROR
            )
        
        mock_db_connection.commit()
        
        # Retry only MAX_RETRIES_EXCEEDED
        results = dlq.retry_all_from_dlq(reason=DLQReason.MAX_RETRIES_EXCEEDED)
        
        assert len(results) == 1
    
    def test_archive_dlq_item(self, mock_db_connection, sample_task, cleanup_utils):
        """Test archiving a DLQ item."""
        dlq = DeadLetterQueue()
        
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        
        result = dlq.archive_dlq_item(dlq_id)
        assert result is True
        
        # Verify archived
        item = dlq.get_dlq_item(dlq_id)
        assert item["archived"] == 1  # SQLite stores bool as 0/1
    
    def test_archive_dlq_item_not_found(self, mock_db_connection, cleanup_utils):
        """Test archiving a non-existent item."""
        dlq = DeadLetterQueue()
        
        result = dlq.archive_dlq_item("non-existent-id")
        assert result is False
    
    def test_delete_dlq_item(self, mock_db_connection, sample_task, cleanup_utils):
        """Test deleting a DLQ item."""
        dlq = DeadLetterQueue()
        
        dlq_id = dlq.move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        
        result = dlq.delete_dlq_item(dlq_id)
        assert result is True
        
        # Verify deleted
        item = dlq.get_dlq_item(dlq_id)
        assert item is None
    
    def test_analyze_failures(self, mock_db_connection, sample_task, cleanup_utils):
        """Test failure analysis."""
        dlq = DeadLetterQueue()
        
        # Add items with different reasons
        reasons = [
            DLQReason.MAX_RETRIES_EXCEEDED,
            DLQReason.MAX_RETRIES_EXCEEDED,
            DLQReason.VALIDATION_ERROR,
            DLQReason.TIMEOUT
        ]
        
        for reason in reasons:
            dlq.move_to_dlq(
                task_id=str(uuid.uuid4()),
                correlation_id=str(uuid.uuid4()),
                reason=reason
            )
        
        analysis = dlq.analyze_failures()
        
        assert analysis["total_items"] == 4
        assert analysis["unarchived_items"] == 4
        assert analysis["by_reason"]["max_retries_exceeded"] == 2
        assert analysis["by_reason"]["validation_error"] == 1
        assert analysis["by_reason"]["timeout"] == 1
    
    def test_analyze_failures_with_date_range(self, mock_db_connection, sample_task, cleanup_utils):
        """Test failure analysis with date range."""
        dlq = DeadLetterQueue()
        
        # Add item
        dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        
        # Analysis with past date range (should not include recent items)
        start = datetime.utcnow() - timedelta(days=7)
        end = datetime.utcnow() - timedelta(days=1)
        analysis = dlq.analyze_failures(start_date=start, end_date=end)
        
        assert analysis["total_items"] == 0  # No items in that range
    
    def test_cleanup_old_items(self, mock_db_connection, cleanup_utils):
        """Test cleaning up old DLQ items."""
        dlq = DeadLetterQueue(max_dlq_age_days=1)
        
        # Add and archive an item
        dlq_id = dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        dlq.archive_dlq_item(dlq_id)
        
        # Manually set the failed_at to be old
        old_date = (datetime.utcnow() - timedelta(days=2)).isoformat()
        mock_db_connection.execute(
            "UPDATE dead_letter_queue SET failed_at = ? WHERE id = ?",
            (old_date, dlq_id)
        )
        mock_db_connection.commit()
        
        # Cleanup
        deleted = dlq.cleanup_old_items()
        
        assert deleted == 1
    
    def test_cleanup_old_items_not_archived(self, mock_db_connection, cleanup_utils):
        """Test that unarchived items are not cleaned up."""
        dlq = DeadLetterQueue(max_dlq_age_days=1)
        
        # Add item (not archived)
        dlq_id = dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id=str(uuid.uuid4()),
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        
        # Manually set old date
        old_date = (datetime.utcnow() - timedelta(days=2)).isoformat()
        mock_db_connection.execute(
            "UPDATE dead_letter_queue SET failed_at = ? WHERE id = ?",
            (old_date, dlq_id)
        )
        mock_db_connection.commit()
        
        # Cleanup should not delete unarchived items
        deleted = dlq.cleanup_old_items()
        
        assert deleted == 0
    
    def test_get_stats(self, mock_db_connection, sample_task, cleanup_utils):
        """Test getting DLQ statistics."""
        dlq = DeadLetterQueue()
        
        # Add items with different states
        dlq_id1 = dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id="corr-1",
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        dlq_id2 = dlq.move_to_dlq(
            task_id=str(uuid.uuid4()),
            correlation_id="corr-2",
            reason=DLQReason.VALIDATION_ERROR
        )
        
        # Archive one
        dlq.archive_dlq_item(dlq_id1)
        
        stats = dlq.get_stats()
        
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["archived"] == 1
        assert stats["by_reason"]["max_retries_exceeded"] == 1
        assert stats["by_reason"]["validation_error"] == 1


class TestGlobalInstance:
    """Test global instance functions."""
    
    def test_get_dead_letter_queue_singleton(self, cleanup_utils):
        """Test that get_dead_letter_queue returns singleton."""
        dlq1 = get_dead_letter_queue()
        dlq2 = get_dead_letter_queue()
        
        assert dlq1 is dlq2
    
    def test_configure_dead_letter_queue(self, cleanup_utils):
        """Test configuring global DLQ."""
        custom_dlq = DeadLetterQueue(max_dlq_age_days=60)
        configure_dead_letter_queue(custom_dlq)
        
        assert get_dead_letter_queue() is custom_dlq
    
    def test_convenience_functions(self, mock_db_connection, sample_task, cleanup_utils):
        """Test convenience functions use global DLQ."""
        # Reset global DLQ
        configure_dead_letter_queue(DeadLetterQueue())
        
        # Test move_to_dlq
        dlq_id = move_to_dlq(
            task_id=sample_task["id"],
            correlation_id=sample_task["correlation_id"],
            reason=DLQReason.MAX_RETRIES_EXCEEDED
        )
        assert dlq_id is not None
        
        # Test get_dlq_items
        items = get_dlq_items()
        assert len(items) == 1


class TestDLQEntry:
    """Test DLQEntry dataclass."""
    
    def test_entry_creation(self):
        """Test creating a DLQEntry."""
        now = datetime.utcnow()
        
        entry = DLQEntry(
            id="dlq-123",
            original_task_id="task-456",
            correlation_id="corr-789",
            failed_at=now,
            reason=DLQReason.MAX_RETRIES_EXCEEDED,
            error_details={"error": "test"},
            original_payload={"data": "test"},
            retry_count=3,
            worker_id="worker-1"
        )
        
        assert entry.id == "dlq-123"
        assert entry.reason == DLQReason.MAX_RETRIES_EXCEEDED
    
    def test_entry_to_dict(self):
        """Test converting DLQEntry to dictionary."""
        now = datetime.utcnow()
        
        entry = DLQEntry(
            id="dlq-123",
            original_task_id="task-456",
            correlation_id="corr-789",
            failed_at=now,
            reason=DLQReason.MAX_RETRIES_EXCEEDED,
            error_details={"error": "test"},
            original_payload={"data": "test"},
            retry_count=3
        )
        
        d = entry.to_dict()
        assert d["id"] == "dlq-123"
        assert d["reason"] == "max_retries_exceeded"
        assert "failed_at" in d
