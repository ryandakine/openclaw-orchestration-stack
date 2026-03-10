"""
Queue Leasing System for OpenClaw Orchestration Stack

Provides atomic task claiming and lease management for distributed workers.
Uses SQLite atomic operations to prevent race conditions.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager

from ..db import get_connection, transaction, execute

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """Represents a task lease."""
    claimed_by: str
    claimed_at: datetime
    lease_expires_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert lease to dictionary."""
        return {
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() + "Z",
            "lease_expires_at": self.lease_expires_at.isoformat() + "Z"
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Lease":
        """Create Lease from dictionary."""
        return cls(
            claimed_by=data["claimed_by"],
            claimed_at=datetime.fromisoformat(data["claimed_at"].replace("Z", "+00:00")),
            lease_expires_at=datetime.fromisoformat(data["lease_expires_at"].replace("Z", "+00:00"))
        )
    
    def is_expired(self) -> bool:
        """Check if lease has expired."""
        return datetime.utcnow() > self.lease_expires_at
    
    def time_remaining(self) -> timedelta:
        """Get time remaining on lease."""
        remaining = self.lease_expires_at - datetime.utcnow()
        return max(remaining, timedelta(0))


class LeaseError(Exception):
    """Base exception for lease operations."""
    pass


class TaskAlreadyClaimedError(LeaseError):
    """Raised when trying to claim an already claimed task."""
    pass


class LeaseExpiredError(LeaseError):
    """Raised when operating on an expired lease."""
    pass


class TaskNotFoundError(LeaseError):
    """Raised when task is not found."""
    pass


class LeaseManager:
    """
    Manages task leases using atomic SQLite operations.
    
    Provides:
    - Atomic task claiming with UPDATE ... WHERE
    - Lease extension for long-running tasks
    - Lease release on completion/failure
    - Expired lease recovery
    """
    
    def __init__(self, default_lease_duration: int = 300):
        """
        Initialize lease manager.
        
        Args:
            default_lease_duration: Default lease duration in seconds (default: 5 minutes)
        """
        self.default_lease_duration = default_lease_duration
    
    def claim_task(
        self,
        task_id: str,
        worker_id: str,
        lease_duration: Optional[int] = None
    ) -> Optional[Lease]:
        """
        Atomically claim a task for processing.
        
        Uses UPDATE ... WHERE to ensure atomicity - only one worker can claim.
        
        Args:
            task_id: The task ID to claim
            worker_id: Unique identifier for the worker
            lease_duration: Lease duration in seconds (uses default if None)
        
        Returns:
            Lease object if claim successful, None if task not available
        
        Raises:
            TaskNotFoundError: If task doesn't exist
        """
        duration = lease_duration or self.default_lease_duration
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=duration)
        
        with transaction() as conn:
            # First check if task exists
            cursor = conn.execute(
                "SELECT status, claimed_by, lease_expires_at FROM tasks WHERE id = ?",
                (task_id,)
            )
            task = cursor.fetchone()
            
            if not task:
                raise TaskNotFoundError(f"Task {task_id} not found")
            
            # Attempt atomic claim using UPDATE ... WHERE
            # This ensures only one worker can claim the task
            cursor = conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = ?,
                    claimed_at = ?,
                    lease_expires_at = ?,
                    status = 'executing',
                    updated_at = ?
                WHERE id = ?
                  AND status = 'queued'
                  AND (claimed_by IS NULL OR lease_expires_at < ?)
                """,
                (worker_id, now.isoformat(), expires_at.isoformat(), 
                 now.isoformat(), task_id, now.isoformat())
            )
            
            if cursor.rowcount == 0:
                # Task was not available for claiming
                logger.debug(f"Task {task_id} not available for claiming by {worker_id}")
                return None
            
            # Log the claim
            conn.execute(
                """
                INSERT INTO audit_events (correlation_id, actor, action, payload)
                SELECT correlation_id, ?, 'task.claimed', ?
                FROM tasks WHERE id = ?
                """,
                (worker_id, json.dumps({
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "lease_expires_at": expires_at.isoformat()
                }), task_id)
            )
        
        lease = Lease(
            claimed_by=worker_id,
            claimed_at=now,
            lease_expires_at=expires_at
        )
        
        logger.info(f"Task {task_id} claimed by {worker_id}, expires at {expires_at.isoformat()}")
        return lease
    
    def claim_next_available(
        self,
        worker_id: str,
        assigned_to: Optional[str] = None,
        lease_duration: Optional[int] = None
    ) -> Optional[Tuple[str, Lease]]:
        """
        Atomically claim the next available task.
        
        Args:
            worker_id: Unique identifier for the worker
            assigned_to: Filter by assigned_to (e.g., 'DEVCLAW', 'SYMPHONY')
            lease_duration: Lease duration in seconds
        
        Returns:
            Tuple of (task_id, Lease) if claim successful, None otherwise
        """
        duration = lease_duration or self.default_lease_duration
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=duration)
        
        with transaction() as conn:
            # Build query based on filters
            where_clauses = [
                "status = 'queued'",
                "(claimed_by IS NULL OR lease_expires_at < ?)"
            ]
            params = [now.isoformat()]
            
            if assigned_to:
                where_clauses.append("assigned_to = ?")
                params.append(assigned_to)
            
            where_sql = " AND ".join(where_clauses)
            
            # Find next available task
            cursor = conn.execute(
                f"""
                SELECT id FROM tasks 
                WHERE {where_sql}
                ORDER BY created_at ASC
                LIMIT 1
                """,
                tuple(params)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            task_id = row["id"]
            
            # Attempt atomic claim
            cursor = conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = ?,
                    claimed_at = ?,
                    lease_expires_at = ?,
                    status = 'executing',
                    updated_at = ?
                WHERE id = ?
                  AND status = 'queued'
                  AND (claimed_by IS NULL OR lease_expires_at < ?)
                """,
                (worker_id, now.isoformat(), expires_at.isoformat(),
                 now.isoformat(), task_id, now.isoformat())
            )
            
            if cursor.rowcount == 0:
                # Another worker claimed it between select and update
                return None
            
            # Log the claim
            conn.execute(
                """
                INSERT INTO audit_events (correlation_id, actor, action, payload)
                SELECT correlation_id, ?, 'task.claimed', ?
                FROM tasks WHERE id = ?
                """,
                (worker_id, json.dumps({
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "lease_expires_at": expires_at.isoformat()
                }), task_id)
            )
        
        lease = Lease(
            claimed_by=worker_id,
            claimed_at=now,
            lease_expires_at=expires_at
        )
        
        logger.info(f"Task {task_id} claimed by {worker_id}")
        return (task_id, lease)
    
    def extend_lease(
        self,
        task_id: str,
        worker_id: str,
        extension_duration: int
    ) -> Optional[Lease]:
        """
        Extend an existing lease while worker is still processing.
        
        Args:
            task_id: The task ID
            worker_id: Worker that owns the lease (for verification)
            extension_duration: Extension duration in seconds
        
        Returns:
            Updated Lease object if successful, None if lease not found/owned
        
        Raises:
            LeaseExpiredError: If lease has already expired
        """
        now = datetime.utcnow()
        new_expires_at = now + timedelta(seconds=extension_duration)
        
        with transaction() as conn:
            # Verify current lease and extend atomically
            cursor = conn.execute(
                """
                UPDATE tasks 
                SET lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND claimed_by = ?
                  AND lease_expires_at > ?
                """,
                (new_expires_at.isoformat(), now.isoformat(),
                 task_id, worker_id, now.isoformat())
            )
            
            if cursor.rowcount == 0:
                # Check if lease exists but expired
                cursor = conn.execute(
                    "SELECT lease_expires_at, claimed_by FROM tasks WHERE id = ?",
                    (task_id,)
                )
                row = cursor.fetchone()
                
                if row and row["claimed_by"] == worker_id:
                    expires = datetime.fromisoformat(row["lease_expires_at"])
                    if expires <= now:
                        raise LeaseExpiredError(f"Lease for task {task_id} has expired")
                
                return None
            
            # Log the extension
            conn.execute(
                """
                INSERT INTO audit_events (correlation_id, actor, action, payload)
                SELECT correlation_id, ?, 'task.lease_extended', ?
                FROM tasks WHERE id = ?
                """,
                (worker_id, json.dumps({
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "new_expires_at": new_expires_at.isoformat()
                }), task_id)
            )
        
        lease = Lease(
            claimed_by=worker_id,
            claimed_at=now,  # We keep original claimed_at, but this is for return value
            lease_expires_at=new_expires_at
        )
        
        logger.info(f"Lease extended for task {task_id} by {worker_id}, new expiry: {new_expires_at.isoformat()}")
        return lease
    
    def release_lease(
        self,
        task_id: str,
        worker_id: str,
        new_status: str = "completed",
        result_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Release a lease on task completion or failure.
        
        Args:
            task_id: The task ID
            worker_id: Worker that owns the lease
            new_status: New task status ('completed', 'failed', 'review_queued', etc.)
            result_data: Optional result data to store
        
        Returns:
            True if released successfully, False if lease not owned by worker
        """
        now = datetime.utcnow()
        
        with transaction() as conn:
            # Verify ownership and release
            cursor = conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = NULL,
                    claimed_at = NULL,
                    lease_expires_at = NULL,
                    status = ?,
                    updated_at = ?,
                    completed_at = CASE WHEN ? IN ('completed', 'failed') THEN ? ELSE completed_at END
                WHERE id = ?
                  AND claimed_by = ?
                """,
                (new_status, now.isoformat(), new_status, now.isoformat(),
                 task_id, worker_id)
            )
            
            if cursor.rowcount == 0:
                logger.warning(f"Failed to release lease for task {task_id} by {worker_id}")
                return False
            
            # Log the release
            conn.execute(
                """
                INSERT INTO audit_events (correlation_id, actor, action, payload)
                SELECT correlation_id, ?, ?, ?
                FROM tasks WHERE id = ?
                """,
                (worker_id, f"task.{new_status}", json.dumps({
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "result": result_data
                }), task_id)
            )
        
        logger.info(f"Lease released for task {task_id} by {worker_id}, new status: {new_status}")
        return True
    
    def handle_expired_leases(
        self,
        max_retries: int = 3,
        retry_delay_seconds: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Reset expired leases back to queued state.
        
        Called by a monitor process to handle crashed workers.
        
        Args:
            max_retries: Maximum retry count before moving to DLQ
            retry_delay_seconds: Delay before a failed task can be retried
        
        Returns:
            List of reset tasks with details
        """
        now = datetime.utcnow()
        reset_tasks = []
        
        with transaction() as conn:
            # Find all expired leases
            cursor = conn.execute(
                """
                SELECT id, correlation_id, claimed_by, claimed_at, 
                       lease_expires_at, retry_count, max_retries
                FROM tasks 
                WHERE claimed_by IS NOT NULL 
                  AND lease_expires_at < ?
                  AND status IN ('executing', 'review_queued')
                """,
                (now.isoformat(),)
            )
            expired_tasks = cursor.fetchall()
            
            for task in expired_tasks:
                task_id = task["id"]
                claimed_by = task["claimed_by"]
                retry_count = task["retry_count"] or 0
                max_task_retries = task["max_retries"] or max_retries
                
                if retry_count >= max_task_retries:
                    # Move to failed status (will be picked up by DLQ handler)
                    new_status = "failed"
                    logger.warning(f"Task {task_id} exceeded max retries, marking as failed")
                else:
                    # Reset to queued for retry
                    new_status = "queued"
                
                # Reset the lease
                cursor = conn.execute(
                    """
                    UPDATE tasks 
                    SET claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL,
                        status = ?,
                        retry_count = retry_count + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (new_status, now.isoformat(), task_id)
                )
                
                if cursor.rowcount > 0:
                    reset_info = {
                        "task_id": task_id,
                        "correlation_id": task["correlation_id"],
                        "previous_worker": claimed_by,
                        "claimed_at": task["claimed_at"],
                        "lease_expired_at": task["lease_expires_at"],
                        "new_status": new_status,
                        "retry_count": retry_count + 1
                    }
                    reset_tasks.append(reset_info)
                    
                    # Log the reset
                    conn.execute(
                        """
                        INSERT INTO audit_events 
                        (correlation_id, actor, action, payload)
                        VALUES (?, 'system', 'task.lease_expired', ?)
                        """,
                        (task["correlation_id"], json.dumps(reset_info))
                    )
                    
                    logger.info(f"Expired lease reset for task {task_id}, new status: {new_status}")
        
        return reset_tasks
    
    def get_lease(self, task_id: str) -> Optional[Lease]:
        """
        Get current lease information for a task.
        
        Args:
            task_id: The task ID
        
        Returns:
            Lease object if task has a lease, None otherwise
        """
        result = execute(
            """
            SELECT claimed_by, claimed_at, lease_expires_at
            FROM tasks
            WHERE id = ? AND claimed_by IS NOT NULL
            """,
            (task_id,),
            fetch_one=True
        )
        
        if not result:
            return None
        
        return Lease(
            claimed_by=result["claimed_by"],
            claimed_at=datetime.fromisoformat(result["claimed_at"]),
            lease_expires_at=datetime.fromisoformat(result["lease_expires_at"])
        )
    
    def is_claimed_by(self, task_id: str, worker_id: str) -> bool:
        """
        Check if a task is claimed by a specific worker.
        
        Args:
            task_id: The task ID
            worker_id: Worker to check
        
        Returns:
            True if task is claimed by the worker and lease not expired
        """
        now = datetime.utcnow().isoformat()
        
        result = execute(
            """
            SELECT 1 FROM tasks
            WHERE id = ?
              AND claimed_by = ?
              AND lease_expires_at > ?
            """,
            (task_id, worker_id, now),
            fetch_one=True
        )
        
        return result is not None
    
    def get_stuck_tasks(
        self,
        older_than_seconds: int = 300
    ) -> List[Dict[str, Any]]:
        """
        Get tasks with stuck/expired leases for monitoring.
        
        Args:
            older_than_seconds: Minimum age of expired lease to consider stuck
        
        Returns:
            List of stuck task details
        """
        cutoff = (datetime.utcnow() - timedelta(seconds=older_than_seconds)).isoformat()
        
        return execute(
            """
            SELECT id, correlation_id, claimed_by, claimed_at,
                   lease_expires_at, status, retry_count
            FROM tasks
            WHERE claimed_by IS NOT NULL
              AND lease_expires_at < ?
              AND status IN ('executing', 'review_queued')
            ORDER BY lease_expires_at ASC
            """,
            (cutoff,)
        )
    
    def get_worker_tasks(
        self,
        worker_id: str,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all tasks claimed by a worker.
        
        Args:
            worker_id: Worker ID
            status: Optional status filter
        
        Returns:
            List of task details
        """
        if status:
            return execute(
                """
                SELECT id, correlation_id, status, claimed_at,
                       lease_expires_at, retry_count
                FROM tasks
                WHERE claimed_by = ? AND status = ?
                ORDER BY claimed_at ASC
                """,
                (worker_id, status)
            )
        else:
            return execute(
                """
                SELECT id, correlation_id, status, claimed_at,
                       lease_expires_at, retry_count
                FROM tasks
                WHERE claimed_by = ?
                ORDER BY claimed_at ASC
                """,
                (worker_id,)
            )


# Global instance
_lease_manager: Optional[LeaseManager] = None


def get_lease_manager(default_lease_duration: int = 300) -> LeaseManager:
    """Get or create global lease manager instance."""
    global _lease_manager
    if _lease_manager is None:
        _lease_manager = LeaseManager(default_lease_duration)
    return _lease_manager


def configure_lease_manager(manager: LeaseManager):
    """Configure the global lease manager."""
    global _lease_manager
    _lease_manager = manager
