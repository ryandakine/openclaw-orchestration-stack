"""
Unit tests for lease_manager.py

Tests queue leasing system including:
- Atomic task claiming
- Lease extension
- Lease release
- Expired lease handling
- Concurrent access scenarios
"""

import pytest
import uuid
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from shared.utils.lease_manager import (
    LeaseManager, Lease,
    TaskAlreadyClaimedError, LeaseExpiredError, TaskNotFoundError,
    get_lease_manager, configure_lease_manager
)


class TestLease:
    """Test the Lease dataclass."""
    
    def test_lease_creation(self):
        """Test creating a Lease object."""
        now = datetime.utcnow()
        expires = now + timedelta(minutes=5)
        
        lease = Lease(
            claimed_by="worker-1",
            claimed_at=now,
            lease_expires_at=expires
        )
        
        assert lease.claimed_by == "worker-1"
        assert lease.claimed_at == now
        assert lease.lease_expires_at == expires
    
    def test_lease_to_dict(self):
        """Test converting Lease to dictionary."""
        now = datetime.utcnow()
        expires = now + timedelta(minutes=5)
        
        lease = Lease(
            claimed_by="worker-1",
            claimed_at=now,
            lease_expires_at=expires
        )
        
        d = lease.to_dict()
        assert d["claimed_by"] == "worker-1"
        assert "claimed_at" in d
        assert "lease_expires_at" in d
    
    def test_lease_from_dict(self):
        """Test creating Lease from dictionary."""
        now = datetime.utcnow()
        expires = now + timedelta(minutes=5)
        
        d = {
            "claimed_by": "worker-1",
            "claimed_at": now.isoformat() + "Z",
            "lease_expires_at": expires.isoformat() + "Z"
        }
        
        lease = Lease.from_dict(d)
        assert lease.claimed_by == "worker-1"
    
    def test_lease_is_expired(self):
        """Test checking if lease is expired."""
        now = datetime.utcnow()
        
        # Expired lease
        expired = Lease(
            claimed_by="worker-1",
            claimed_at=now - timedelta(minutes=10),
            lease_expires_at=now - timedelta(minutes=5)
        )
        assert expired.is_expired() is True
        
        # Active lease
        active = Lease(
            claimed_by="worker-1",
            claimed_at=now,
            lease_expires_at=now + timedelta(minutes=5)
        )
        assert active.is_expired() is False
    
    def test_lease_time_remaining(self):
        """Test calculating time remaining on lease."""
        now = datetime.utcnow()
        
        lease = Lease(
            claimed_by="worker-1",
            claimed_at=now,
            lease_expires_at=now + timedelta(minutes=5)
        )
        
        remaining = lease.time_remaining()
        assert remaining.total_seconds() > 0
        assert remaining.total_seconds() <= 300


class TestLeaseManager:
    """Test the LeaseManager class."""
    
    def test_init(self):
        """Test LeaseManager initialization."""
        manager = LeaseManager(default_lease_duration=600)
        assert manager.default_lease_duration == 600
    
    def test_claim_task_success(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test successfully claiming a task."""
        manager = LeaseManager(default_lease_duration=300)
        
        lease = manager.claim_task(sample_task["id"], sample_worker_id)
        
        assert lease is not None
        assert lease.claimed_by == sample_worker_id
        assert lease.lease_expires_at > datetime.utcnow()
        
        # Verify task is updated in DB
        cursor = mock_db_connection.execute(
            "SELECT status, claimed_by FROM tasks WHERE id = ?",
            (sample_task["id"],)
        )
        row = cursor.fetchone()
        assert row["status"] == "executing"
        assert row["claimed_by"] == sample_worker_id
    
    def test_claim_task_not_found(self, mock_db_connection, sample_worker_id, cleanup_utils):
        """Test claiming a non-existent task."""
        manager = LeaseManager(default_lease_duration=300)
        
        with pytest.raises(TaskNotFoundError):
            manager.claim_task("non-existent-task", sample_worker_id)
    
    def test_claim_task_already_claimed(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test claiming a task that's already claimed."""
        manager = LeaseManager(default_lease_duration=300)
        
        # First claim succeeds
        lease1 = manager.claim_task(sample_task["id"], sample_worker_id)
        assert lease1 is not None
        
        # Second claim fails (task is executing)
        lease2 = manager.claim_task(sample_task["id"], "other-worker")
        assert lease2 is None
    
    def test_claim_expired_lease(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test claiming a task with an expired lease."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Manually set an expired lease
        past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_db_connection.execute(
            """
            UPDATE tasks 
            SET claimed_by = ?, claimed_at = ?, lease_expires_at = ?, status = 'queued'
            WHERE id = ?
            """,
            ("old-worker", past, past, sample_task["id"])
        )
        mock_db_connection.commit()
        
        # New worker can claim
        lease = manager.claim_task(sample_task["id"], sample_worker_id)
        assert lease is not None
        assert lease.claimed_by == sample_worker_id
    
    def test_claim_next_available(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test claiming the next available task."""
        manager = LeaseManager(default_lease_duration=300)
        
        result = manager.claim_next_available(sample_worker_id, assigned_to="DEVCLAW")
        
        assert result is not None
        task_id, lease = result
        assert task_id == sample_task["id"]
        assert lease.claimed_by == sample_worker_id
    
    def test_claim_next_available_no_tasks(self, mock_db_connection, sample_worker_id, cleanup_utils):
        """Test claiming when no tasks available."""
        manager = LeaseManager(default_lease_duration=300)
        
        result = manager.claim_next_available(sample_worker_id)
        assert result is None
    
    def test_extend_lease_success(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test extending an active lease."""
        manager = LeaseManager(default_lease_duration=300)
        
        # First claim the task
        lease = manager.claim_task(sample_task["id"], sample_worker_id)
        assert lease is not None
        
        old_expiry = lease.lease_expires_at
        
        # Extend the lease
        extended = manager.extend_lease(sample_task["id"], sample_worker_id, 600)
        assert extended is not None
        assert extended.lease_expires_at > old_expiry
    
    def test_extend_lease_wrong_worker(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test extending a lease owned by another worker."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Claim as one worker
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Try to extend as another worker
        result = manager.extend_lease(sample_task["id"], "other-worker", 600)
        assert result is None
    
    def test_extend_expired_lease(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test extending an already expired lease."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Set expired lease
        past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_db_connection.execute(
            """
            UPDATE tasks 
            SET claimed_by = ?, claimed_at = ?, lease_expires_at = ?, status = 'executing'
            WHERE id = ?
            """,
            (sample_worker_id, past, past, sample_task["id"])
        )
        mock_db_connection.commit()
        
        # Should raise LeaseExpiredError
        with pytest.raises(LeaseExpiredError):
            manager.extend_lease(sample_task["id"], sample_worker_id, 600)
    
    def test_release_lease_success(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test releasing a lease."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Claim the task
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Release the lease
        released = manager.release_lease(sample_task["id"], sample_worker_id, "completed")
        assert released is True
        
        # Verify task is released
        cursor = mock_db_connection.execute(
            "SELECT status, claimed_by FROM tasks WHERE id = ?",
            (sample_task["id"],)
        )
        row = cursor.fetchone()
        assert row["status"] == "completed"
        assert row["claimed_by"] is None
    
    def test_release_lease_wrong_worker(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test releasing a lease owned by another worker."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Claim as one worker
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Try to release as another worker
        result = manager.release_lease(sample_task["id"], "other-worker", "completed")
        assert result is False
    
    def test_handle_expired_leases(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test handling expired leases."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Set expired lease
        past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_db_connection.execute(
            """
            UPDATE tasks 
            SET claimed_by = ?, claimed_at = ?, lease_expires_at = ?, 
                status = 'executing', retry_count = 0
            WHERE id = ?
            """,
            (sample_worker_id, past, past, sample_task["id"])
        )
        mock_db_connection.commit()
        
        # Handle expired leases
        reset_tasks = manager.handle_expired_leases(max_retries=3)
        
        assert len(reset_tasks) == 1
        assert reset_tasks[0]["task_id"] == sample_task["id"]
        assert reset_tasks[0]["new_status"] == "queued"
    
    def test_handle_expired_leases_max_retries(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test handling expired leases that exceed max retries."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Set expired lease with max retries reached
        past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_db_connection.execute(
            """
            UPDATE tasks 
            SET claimed_by = ?, claimed_at = ?, lease_expires_at = ?, 
                status = 'executing', retry_count = 3, max_retries = 3
            WHERE id = ?
            """,
            (sample_worker_id, past, past, sample_task["id"])
        )
        mock_db_connection.commit()
        
        # Handle expired leases
        reset_tasks = manager.handle_expired_leases(max_retries=3)
        
        assert len(reset_tasks) == 1
        assert reset_tasks[0]["new_status"] == "failed"
    
    def test_get_lease(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test getting lease information."""
        manager = LeaseManager(default_lease_duration=300)
        
        # No lease initially
        lease = manager.get_lease(sample_task["id"])
        assert lease is None
        
        # Claim the task
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Get the lease
        lease = manager.get_lease(sample_task["id"])
        assert lease is not None
        assert lease.claimed_by == sample_worker_id
    
    def test_is_claimed_by(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test checking if task is claimed by a specific worker."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Not claimed initially
        assert manager.is_claimed_by(sample_task["id"], sample_worker_id) is False
        
        # Claim the task
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Check ownership
        assert manager.is_claimed_by(sample_task["id"], sample_worker_id) is True
        assert manager.is_claimed_by(sample_task["id"], "other-worker") is False
    
    def test_get_stuck_tasks(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test getting stuck tasks."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Create a stuck task (expired lease)
        past = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_db_connection.execute(
            """
            UPDATE tasks 
            SET claimed_by = ?, claimed_at = ?, lease_expires_at = ?, status = 'executing'
            WHERE id = ?
            """,
            (sample_worker_id, past, past, sample_task["id"])
        )
        mock_db_connection.commit()
        
        stuck = manager.get_stuck_tasks(older_than_seconds=300)
        
        assert len(stuck) == 1
        assert stuck[0]["id"] == sample_task["id"]
    
    def test_get_worker_tasks(self, mock_db_connection, sample_task, sample_worker_id, cleanup_utils):
        """Test getting all tasks claimed by a worker."""
        manager = LeaseManager(default_lease_duration=300)
        
        # Claim the task
        manager.claim_task(sample_task["id"], sample_worker_id)
        
        # Get worker tasks
        tasks = manager.get_worker_tasks(sample_worker_id)
        
        assert len(tasks) == 1
        assert tasks[0]["id"] == sample_task["id"]


class TestConcurrentClaiming:
    """Test concurrent task claiming scenarios.
    
    Note: These tests verify the atomic claim logic but may not fully test
    concurrency in the mock database environment. In production, SQLite's
    WAL mode and atomic UPDATE ... WHERE ensure proper concurrency.
    """
    
    def test_concurrent_claim_race_condition(self, mock_db_connection, sample_task, cleanup_utils):
        """Test that only one worker can claim in a race condition."""
        import concurrent.futures
        
        manager = LeaseManager(default_lease_duration=300)
        results = []
        lock = threading.Lock()
        
        # First verify the task is available
        initial = mock_db_connection.execute(
            "SELECT status, claimed_by FROM tasks WHERE id = ?",
            (sample_task["id"],)
        ).fetchone()
        assert initial["status"] == "queued"
        
        def try_claim(worker_id):
            try:
                lease = manager.claim_task(sample_task["id"], worker_id)
                with lock:
                    results.append((worker_id, lease is not None))
                return lease
            except Exception as e:
                with lock:
                    results.append((worker_id, False, str(e)))
                return None
        
        # Try to claim from multiple threads simultaneously
        workers = [f"worker-{i}" for i in range(5)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_claim, w) for w in workers]
            concurrent.futures.wait(futures)
        
        # Count successful claims - in a proper SQLite environment only one succeeds
        # In mock environment, due to single connection, behavior may vary
        successful_claims = [r for r in results if r[1] is True]
        failed_claims = [r for r in results if r[1] is False]
        
        # At most one should successfully claim (atomic guarantee)
        assert len(successful_claims) <= 1
        
        # Most attempts should either succeed (1) or return None (others)
        assert len(successful_claims) + len(failed_claims) == len(workers)
    
    def test_atomic_claim_next_available(self, mock_db_connection, sample_task, cleanup_utils):
        """Test atomic claiming of next available task."""
        import concurrent.futures
        
        # Create multiple tasks
        for i in range(5):
            task_id = str(uuid.uuid4())
            mock_db_connection.execute(
                """
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                VALUES (?, ?, ?, 'queued', 'DEVCLAW', 'test')
                """,
                (task_id, str(uuid.uuid4()), str(uuid.uuid4()))
            )
        mock_db_connection.commit()
        
        # Verify we have 6 tasks total
        count = mock_db_connection.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE status = 'queued'"
        ).fetchone()["count"]
        assert count == 6
        
        manager = LeaseManager(default_lease_duration=300)
        claimed_tasks = []
        lock = threading.Lock()
        
        def try_claim(worker_id):
            result = manager.claim_next_available(worker_id, assigned_to="DEVCLAW")
            if result:
                task_id, lease = result
                with lock:
                    claimed_tasks.append((worker_id, task_id))
        
        # Try to claim from multiple threads
        workers = [f"worker-{i}" for i in range(10)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(try_claim, w) for w in workers]
            concurrent.futures.wait(futures)
        
        # Should have claimed at most 6 tasks (the available ones)
        # In mock environment, we may get fewer due to single connection
        assert len(claimed_tasks) <= 6
        
        # Each claimed task should be unique
        task_ids = [t[1] for t in claimed_tasks]
        assert len(task_ids) == len(set(task_ids))


class TestGlobalInstance:
    """Test global instance functions."""
    
    def test_get_lease_manager_singleton(self, cleanup_utils):
        """Test that get_lease_manager returns singleton."""
        manager1 = get_lease_manager()
        manager2 = get_lease_manager()
        
        assert manager1 is manager2
    
    def test_configure_lease_manager(self, cleanup_utils):
        """Test configuring global lease manager."""
        custom_manager = LeaseManager(default_lease_duration=600)
        configure_lease_manager(custom_manager)
        
        assert get_lease_manager() is custom_manager
