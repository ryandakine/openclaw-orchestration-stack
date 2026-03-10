"""
Dead Letter Queue (DLQ) for OpenClaw Orchestration Stack

Handles tasks that have exceeded their maximum retry attempts.
Provides manual retry capabilities and failure analysis.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from ..db import get_connection, transaction, execute

logger = logging.getLogger(__name__)


class DLQReason(Enum):
    """Reasons for moving a task to the DLQ."""
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    LEASE_EXPIRED = "lease_expired"
    PERMANENT_FAILURE = "permanent_failure"
    VALIDATION_ERROR = "validation_error"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class DLQEntry:
    """Entry in the dead letter queue."""
    id: str
    original_task_id: str
    correlation_id: str
    failed_at: datetime
    reason: DLQReason
    error_details: Dict[str, Any]
    original_payload: Dict[str, Any]
    retry_count: int
    worker_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "original_task_id": self.original_task_id,
            "correlation_id": self.correlation_id,
            "failed_at": self.failed_at.isoformat(),
            "reason": self.reason.value,
            "error_details": self.error_details,
            "original_payload": self.original_payload,
            "retry_count": self.retry_count,
            "worker_id": self.worker_id
        }


class DLQError(Exception):
    """Base exception for DLQ operations."""
    pass


class TaskNotInDLQError(DLQError):
    """Raised when trying to operate on a task not in the DLQ."""
    pass


class DeadLetterQueue:
    """
    Dead Letter Queue for failed tasks.
    
    Features:
    - Move tasks to DLQ after max retries exceeded
    - List and filter DLQ items
    - Manual retry with original payload
    - Failure analysis and reporting
    """
    
    def __init__(self, max_dlq_age_days: int = 30):
        """
        Initialize the DLQ.
        
        Args:
            max_dlq_age_days: Maximum age of DLQ items before automatic cleanup
        """
        self.max_dlq_age_days = max_dlq_age_days
        self._ensure_table()
    
    def _ensure_table(self):
        """Ensure the DLQ table exists."""
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id TEXT PRIMARY KEY,
                    original_task_id TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reason TEXT NOT NULL,
                    error_details JSON,
                    original_payload JSON NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    worker_id TEXT,
                    retried_at TIMESTAMP,
                    retry_successful BOOLEAN,
                    archived BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_correlation_id 
                ON dead_letter_queue(correlation_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_failed_at 
                ON dead_letter_queue(failed_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_reason 
                ON dead_letter_queue(reason)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_archived 
                ON dead_letter_queue(archived) WHERE archived = FALSE
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dlq_original_task 
                ON dead_letter_queue(original_task_id)
            """)
            
            conn.commit()
    
    def move_to_dlq(
        self,
        task_id: str,
        correlation_id: str,
        reason: DLQReason,
        error_details: Optional[Dict[str, Any]] = None,
        original_payload: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        worker_id: Optional[str] = None
    ) -> str:
        """
        Move a failed task to the DLQ.
        
        Args:
            task_id: The original task ID
            correlation_id: The correlation ID
            reason: Reason for failure
            error_details: Detailed error information
            original_payload: Original task payload
            retry_count: Number of retry attempts made
            worker_id: Worker that last attempted the task
        
        Returns:
            DLQ entry ID
        """
        import uuid
        
        dlq_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        # Get task details if not provided
        if original_payload is None or not error_details:
            task = execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
                fetch_one=True
            )
            
            if task:
                if original_payload is None:
                    original_payload = {
                        "intent": task.get("intent"),
                        "payload": json.loads(task["payload"]) if task.get("payload") else {},
                        "assigned_to": task.get("assigned_to"),
                        "status": task.get("status")
                    }
                if not error_details:
                    error_details = {
                        "final_status": task.get("status"),
                        "retry_count": retry_count
                    }
        
        with transaction() as conn:
            # Insert into DLQ
            conn.execute(
                """
                INSERT INTO dead_letter_queue 
                (id, original_task_id, correlation_id, failed_at, reason,
                 error_details, original_payload, retry_count, worker_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (dlq_id, task_id, correlation_id, now.isoformat(),
                 reason.value,
                 json.dumps(error_details) if error_details else None,
                 json.dumps(original_payload) if original_payload else '{}',
                 retry_count, worker_id)
            )
            
            # Update original task to mark as moved to DLQ
            conn.execute(
                """
                UPDATE tasks
                SET status = 'failed',
                    updated_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), task_id)
            )
            
            # Log the move
            conn.execute(
                """
                INSERT INTO audit_events 
                (correlation_id, actor, action, payload)
                VALUES (?, 'system', 'task.moved_to_dlq', ?)
                """,
                (correlation_id, json.dumps({
                    "task_id": task_id,
                    "dlq_id": dlq_id,
                    "reason": reason.value,
                    "retry_count": retry_count
                }))
            )
        
        logger.warning(
            f"Task {task_id} moved to DLQ (id={dlq_id}), reason: {reason.value}"
        )
        return dlq_id
    
    def get_dlq_items(
        self,
        include_archived: bool = False,
        reason: Optional[DLQReason] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List items in the DLQ.
        
        Args:
            include_archived: Include archived items
            reason: Filter by failure reason
            correlation_id: Filter by correlation ID
            limit: Maximum items to return
            offset: Offset for pagination
        
        Returns:
            List of DLQ items
        """
        query = ["SELECT * FROM dead_letter_queue WHERE 1=1"]
        params = []
        
        if not include_archived:
            query.append("AND archived = FALSE")
        
        if reason:
            query.append("AND reason = ?")
            params.append(reason.value)
        
        if correlation_id:
            query.append("AND correlation_id = ?")
            params.append(correlation_id)
        
        query.append("ORDER BY failed_at DESC")
        query.append(f"LIMIT ? OFFSET ?")
        params.extend([limit, offset])
        
        items = execute(" ".join(query), tuple(params))
        
        # Parse JSON fields
        for item in items:
            if item.get("error_details"):
                item["error_details"] = json.loads(item["error_details"])
            if item.get("original_payload"):
                item["original_payload"] = json.loads(item["original_payload"])
        
        return items
    
    def get_dlq_item(self, dlq_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific DLQ item by ID.
        
        Args:
            dlq_id: The DLQ entry ID
        
        Returns:
            DLQ item if found, None otherwise
        """
        item = execute(
            "SELECT * FROM dead_letter_queue WHERE id = ?",
            (dlq_id,),
            fetch_one=True
        )
        
        if item:
            if item.get("error_details"):
                item["error_details"] = json.loads(item["error_details"])
            if item.get("original_payload"):
                item["original_payload"] = json.loads(item["original_payload"])
        
        return item
    
    def retry_from_dlq(
        self,
        dlq_id: str,
        new_worker_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Retry a task from the DLQ.
        
        Creates a new task with the original payload and marks the DLQ entry
        as retried.
        
        Args:
            dlq_id: The DLQ entry ID
            new_worker_id: Optional worker ID to assign
        
        Returns:
            New task ID if retry created, None otherwise
        """
        import uuid
        
        now = datetime.utcnow()
        
        with transaction() as conn:
            # Get the DLQ item
            cursor = conn.execute(
                "SELECT * FROM dead_letter_queue WHERE id = ? AND archived = FALSE",
                (dlq_id,)
            )
            dlq_item = cursor.fetchone()
            
            if not dlq_item:
                raise TaskNotInDLQError(f"DLQ item {dlq_id} not found or archived")
            
            original_payload = json.loads(dlq_item["original_payload"])
            correlation_id = dlq_item["correlation_id"]
            original_task_id = dlq_item["original_task_id"]
            
            # Create new task ID
            new_task_id = str(uuid.uuid4())
            
            # Generate new idempotency key for the retry
            import hashlib
            new_idempotency_key = hashlib.sha256(
                f"{original_task_id}:{now.isoformat()}".encode()
            ).hexdigest()
            
            # Create new task with original payload
            conn.execute(
                """
                INSERT INTO tasks 
                (id, correlation_id, idempotency_key, status, assigned_to, intent, payload,
                 retry_count, max_retries, created_at, updated_at, source)
                SELECT ?, ?, ?, 'queued', assigned_to, intent, payload,
                       0, max_retries, ?, ?, source
                FROM tasks
                WHERE id = ?
                """,
                (new_task_id, correlation_id, new_idempotency_key, now.isoformat(), 
                 now.isoformat(), original_task_id)
            )
            
            # Mark DLQ item as retried
            conn.execute(
                """
                UPDATE dead_letter_queue
                SET retried_at = ?,
                    retry_successful = TRUE,
                    archived = TRUE
                WHERE id = ?
                """,
                (now.isoformat(), dlq_id)
            )
            
            # Log the retry
            conn.execute(
                """
                INSERT INTO audit_events 
                (correlation_id, actor, action, payload)
                VALUES (?, ?, 'dlq.retry', ?)
                """,
                (new_worker_id or 'system', correlation_id, json.dumps({
                    "dlq_id": dlq_id,
                    "original_task_id": original_task_id,
                    "new_task_id": new_task_id
                }))
            )
        
        logger.info(
            f"Retried DLQ item {dlq_id}, new task: {new_task_id}"
        )
        return new_task_id
    
    def retry_all_from_dlq(
        self,
        reason: Optional[DLQReason] = None,
        max_age_hours: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Retry all eligible items from the DLQ.
        
        Args:
            reason: Only retry items with this reason
            max_age_hours: Only retry items newer than this
        
        Returns:
            List of retry results with dlq_id and new_task_id
        """
        query = "SELECT id FROM dead_letter_queue WHERE archived = FALSE"
        params = []
        
        if reason:
            query += " AND reason = ?"
            params.append(reason.value)
        
        if max_age_hours:
            query += " AND failed_at > datetime('now', '-{} hours')".format(max_age_hours)
        
        items = execute(query, tuple(params))
        
        results = []
        for item in items:
            try:
                new_task_id = self.retry_from_dlq(item["id"])
                results.append({
                    "dlq_id": item["id"],
                    "new_task_id": new_task_id,
                    "success": True
                })
            except Exception as e:
                results.append({
                    "dlq_id": item["id"],
                    "error": str(e),
                    "success": False
                })
        
        return results
    
    def archive_dlq_item(self, dlq_id: str) -> bool:
        """
        Archive a DLQ item (mark as resolved without retry).
        
        Args:
            dlq_id: The DLQ entry ID
        
        Returns:
            True if archived successfully
        """
        now = datetime.utcnow()
        
        with transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE dead_letter_queue
                SET archived = TRUE,
                    retried_at = ?
                WHERE id = ?
                """,
                (now.isoformat(), dlq_id)
            )
            
            if cursor.rowcount == 0:
                return False
            
            # Log the archive
            conn.execute(
                """
                INSERT INTO audit_events 
                (correlation_id, actor, action, payload)
                SELECT correlation_id, 'system', 'dlq.archived', ?
                FROM dead_letter_queue WHERE id = ?
                """,
                (json.dumps({"dlq_id": dlq_id}), dlq_id)
            )
        
        logger.info(f"DLQ item {dlq_id} archived")
        return True
    
    def delete_dlq_item(self, dlq_id: str) -> bool:
        """
        Permanently delete a DLQ item.
        
        Args:
            dlq_id: The DLQ entry ID
        
        Returns:
            True if deleted successfully
        """
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM dead_letter_queue WHERE id = ?",
                (dlq_id,)
            )
            return cursor.rowcount > 0
    
    def analyze_failures(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Analyze failure patterns in the DLQ.
        
        Args:
            start_date: Start of analysis period
            end_date: End of analysis period
        
        Returns:
            Analysis results with statistics
        """
        # Build WHERE clause for date range
        date_where = []
        date_params = []
        
        if start_date:
            date_where.append("failed_at >= ?")
            date_params.append(start_date.isoformat())
        
        if end_date:
            date_where.append("failed_at <= ?")
            date_params.append(end_date.isoformat())
        
        date_sql = " AND ".join(date_where) if date_where else "1=1"
        
        with get_connection() as conn:
            # Reason breakdown (with date filter)
            cursor = conn.execute(
                f"SELECT reason, COUNT(*) as count FROM dead_letter_queue WHERE {date_sql} GROUP BY reason",
                tuple(date_params)
            )
            reason_counts = {row["reason"]: row["count"] for row in cursor.fetchall()}
            
            # Total count (with date filter)
            cursor = conn.execute(
                f"SELECT COUNT(*) as count FROM dead_letter_queue WHERE {date_sql}",
                tuple(date_params)
            )
            total_count = cursor.fetchone()["count"]
            
            # Unarchived count (with date filter)
            unarchived_sql = f"{date_sql} AND archived = FALSE" if date_where else "archived = FALSE"
            unarchived_params = date_params.copy()
            cursor = conn.execute(
                f"SELECT COUNT(*) as count FROM dead_letter_queue WHERE {unarchived_sql}",
                tuple(unarchived_params)
            )
            unarchived_count = cursor.fetchone()["count"]
            
            # Recent failures (last 24 hours) - independent of date filter
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM dead_letter_queue 
                WHERE failed_at > datetime('now', '-1 day')
                """
            )
            recent_count = cursor.fetchone()["count"]
            
            # Top failing tasks (with date filter)
            cursor = conn.execute(
                f"""
                SELECT original_task_id, COUNT(*) as failure_count
                FROM dead_letter_queue
                WHERE {date_sql}
                GROUP BY original_task_id
                ORDER BY failure_count DESC
                LIMIT 10
                """,
                tuple(date_params)
            )
            top_failing = [
                {"task_id": row["original_task_id"], "failures": row["failure_count"]}
                for row in cursor.fetchall()
            ]
        
        return {
            "total_items": total_count,
            "unarchived_items": unarchived_count,
            "recent_24h": recent_count,
            "by_reason": reason_counts,
            "top_failing_tasks": top_failing
        }
    
    def cleanup_old_items(self, older_than_days: Optional[int] = None) -> int:
        """
        Clean up old archived DLQ items.
        
        Args:
            older_than_days: Age threshold (uses max_dlq_age_days if None)
        
        Returns:
            Number of items deleted
        """
        age_days = older_than_days or self.max_dlq_age_days
        cutoff = (datetime.utcnow() - timedelta(days=age_days)).isoformat()
        
        with transaction() as conn:
            cursor = conn.execute(
                """
                DELETE FROM dead_letter_queue
                WHERE (archived = TRUE OR retry_successful = TRUE)
                  AND failed_at < ?
                """,
                (cutoff,)
            )
            deleted = cursor.rowcount
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old DLQ items")
        
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get DLQ statistics.
        
        Returns:
            Dictionary with statistics
        """
        with get_connection() as conn:
            # Total count
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM dead_letter_queue"
            )
            total = cursor.fetchone()["count"]
            
            # Active (unarchived) count
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM dead_letter_queue WHERE archived = FALSE"
            )
            active = cursor.fetchone()["count"]
            
            # By reason
            cursor = conn.execute(
                """
                SELECT reason, COUNT(*) as count
                FROM dead_letter_queue
                GROUP BY reason
                """
            )
            by_reason = {row["reason"]: row["count"] for row in cursor.fetchall()}
            
            # Successfully retried
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM dead_letter_queue 
                WHERE retry_successful = TRUE
                """
            )
            retried = cursor.fetchone()["count"]
            
            # Recent (last 24 hours)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM dead_letter_queue 
                WHERE failed_at > datetime('now', '-1 day')
                """
            )
            recent = cursor.fetchone()["count"]
        
        return {
            "total": total,
            "active": active,
            "archived": total - active,
            "by_reason": by_reason,
            "successfully_retried": retried,
            "recent_24h": recent
        }


# Global instance
_dlq: Optional[DeadLetterQueue] = None


def get_dead_letter_queue(max_dlq_age_days: int = 30) -> DeadLetterQueue:
    """Get or create global DLQ instance."""
    global _dlq
    if _dlq is None:
        _dlq = DeadLetterQueue(max_dlq_age_days)
    return _dlq


def configure_dead_letter_queue(dlq: DeadLetterQueue):
    """Configure the global DLQ."""
    global _dlq
    _dlq = dlq


# Convenience functions

def move_to_dlq(
    task_id: str,
    correlation_id: str,
    reason: DLQReason,
    error_details: Optional[Dict[str, Any]] = None,
    original_payload: Optional[Dict[str, Any]] = None,
    retry_count: int = 0,
    worker_id: Optional[str] = None
) -> str:
    """Move task to DLQ using global instance."""
    dlq = get_dead_letter_queue()
    return dlq.move_to_dlq(
        task_id, correlation_id, reason, error_details,
        original_payload, retry_count, worker_id
    )


def get_dlq_items(
    include_archived: bool = False,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get DLQ items using global instance."""
    dlq = get_dead_letter_queue()
    return dlq.get_dlq_items(include_archived=include_archived, limit=limit)


def retry_from_dlq(dlq_id: str, new_worker_id: Optional[str] = None) -> Optional[str]:
    """Retry from DLQ using global instance."""
    dlq = get_dead_letter_queue()
    return dlq.retry_from_dlq(dlq_id, new_worker_id)
