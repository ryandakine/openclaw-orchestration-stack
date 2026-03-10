"""
Review Queue Manager for Symphony Bridge.

Manages the review queue including:
- Enqueue tasks when DevClaw completes
- Dequeue tasks for Symphony reviewer
- Track review status
- Audit logging for all actions
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Try both import paths for flexibility
try:
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        update,
        get_task_by_id,
    )
except ImportError:
    import sys
    from pathlib import Path
    # Add project root to path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        update,
        get_task_by_id,
    )

logger = logging.getLogger(__name__)


class ReviewStatus(str, Enum):
    """Review queue status states."""
    REVIEW_QUEUED = "review_queued"
    REVIEW_FAILED = "review_failed"
    REMEDIATION_QUEUED = "remediation_queued"
    APPROVED = "approved"
    BLOCKED = "blocked"


@dataclass
class ReviewQueueItem:
    """Represents an item in the review queue."""
    task_id: str
    correlation_id: str
    status: ReviewStatus
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "status": self.status.value,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "owner": self.owner,
            "repo": self.repo,
            "branch": self.branch,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "priority": self.priority,
        }


class QueueManager:
    """
    Manages the review queue for Symphony Bridge.
    
    This is the critical quality gate - EVERY completed DevClaw task
    MUST pass through review before being considered done.
    """
    
    def __init__(self):
        """Initialize the queue manager."""
        self.logger = logging.getLogger(__name__)
    
    def _log_audit_event(
        self,
        correlation_id: str,
        action: str,
        payload: Dict[str, Any],
        actor: str = "symphony",
    ) -> None:
        """
        Log an audit event for review queue actions.
        
        Args:
            correlation_id: The correlation ID for the event
            action: The action being performed
            payload: Additional event data
            actor: The actor performing the action
        """
        try:
            # Note: id is auto-increment, don't specify it
            insert("audit_events", {
                "correlation_id": correlation_id,
                "actor": actor,
                "action": action,
                "payload": json.dumps(payload),
            })
            self.logger.debug(f"Logged audit event: {action} for {correlation_id}")
        except Exception as e:
            self.logger.error(f"Failed to log audit event: {e}")
    
    def enqueue_for_review(
        self,
        task_id: str,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        priority: int = 0,
    ) -> ReviewQueueItem:
        """
        Enqueue a task for review when DevClaw completes.
        
        This is called when DevClaw finishes implementing a task and
        creates a PR. The task is moved to review_queued status.
        
        Args:
            task_id: The task ID to enqueue
            pr_number: Optional PR number
            pr_url: Optional PR URL
            owner: Repository owner
            repo: Repository name
            branch: Branch name
            priority: Priority level (higher = more urgent)
            
        Returns:
            The created ReviewQueueItem
            
        Raises:
            ValueError: If task not found or not in correct state
        """
        # Get the task
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Verify task is in a state that can be enqueued for review
        valid_prior_states = ["executing", "failed"]
        if task["status"] not in valid_prior_states:
            raise ValueError(
                f"Task {task_id} cannot be enqueued for review from status {task['status']}. "
                f"Expected one of: {valid_prior_states}"
            )
        
        correlation_id = task["correlation_id"]
        
        with transaction() as conn:
            # Update task status to review_queued
            conn.execute(
                """
                UPDATE tasks 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ReviewStatus.REVIEW_QUEUED.value, task_id)
            )
            
            # Store review queue metadata in task payload
            queue_metadata = {
                "pr_number": pr_number,
                "pr_url": pr_url,
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "priority": priority,
                "enqueued_at": datetime.utcnow().isoformat(),
            }
            
            # Merge with existing payload
            existing_payload = task.get("payload") or "{}"
            if isinstance(existing_payload, str):
                existing_payload = json.loads(existing_payload)
            else:
                existing_payload = dict(existing_payload) if existing_payload else {}
            
            existing_payload["review_queue"] = queue_metadata
            
            conn.execute(
                """
                UPDATE tasks 
                SET payload = ?
                WHERE id = ?
                """,
                (json.dumps(existing_payload), task_id)
            )
        
        # Log audit event
        self._log_audit_event(
            correlation_id=correlation_id,
            action="review.enqueued",
            payload={
                "task_id": task_id,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "priority": priority,
            },
        )
        
        self.logger.info(f"Task {task_id} enqueued for review")
        
        return ReviewQueueItem(
            task_id=task_id,
            correlation_id=correlation_id,
            status=ReviewStatus.REVIEW_QUEUED,
            pr_number=pr_number,
            pr_url=pr_url,
            owner=owner,
            repo=repo,
            branch=branch,
            priority=priority,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    
    def get_next_review(
        self,
        claimed_by: Optional[str] = None,
        lease_duration_minutes: int = 30,
    ) -> Optional[ReviewQueueItem]:
        """
        Get the next task for Symphony reviewer.
        
        Claims the task with a lease to prevent concurrent reviews.
        
        Args:
            claimed_by: Identifier of the reviewer claiming the task
            lease_duration_minutes: How long the lease lasts
            
        Returns:
            ReviewQueueItem if available, None if queue is empty
        """
        with transaction() as conn:
            # Find the next available review task
            # Prioritized by priority (desc), then created_at (asc)
            cursor = conn.execute(
                """
                SELECT * FROM tasks 
                WHERE status = ?
                AND (claimed_by IS NULL OR lease_expires_at < datetime('now'))
                ORDER BY 
                    json_extract(payload, '$.review_queue.priority') DESC,
                    created_at ASC
                LIMIT 1
                """,
                (ReviewStatus.REVIEW_QUEUED.value,)
            )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            task = dict(row)
            task_id = task["id"]
            correlation_id = task["correlation_id"]
            
            # Claim the task
            lease_expires = datetime.utcnow()
            lease_expires_str = lease_expires.strftime("%Y-%m-%d %H:%M:%S")
            
            conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = ?, 
                    claimed_at = CURRENT_TIMESTAMP,
                    lease_expires_at = datetime('now', '+{} minutes')
                WHERE id = ?
                """.format(lease_duration_minutes),
                (claimed_by or "symphony_reviewer", task_id)
            )
            
            # Parse payload for queue metadata
            payload = task.get("payload") or "{}"
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            
            queue_metadata = payload.get("review_queue", {})
            
            # Log audit event
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.claimed",
                payload={
                    "task_id": task_id,
                    "claimed_by": claimed_by,
                    "lease_duration_minutes": lease_duration_minutes,
                },
            )
            
            self.logger.info(f"Task {task_id} claimed for review by {claimed_by}")
            
            # Handle datetime fields that may already be datetime objects
            created_at = task.get("created_at")
            updated_at = task.get("updated_at")
            
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            
            return ReviewQueueItem(
                task_id=task_id,
                correlation_id=correlation_id,
                status=ReviewStatus.REVIEW_QUEUED,
                pr_number=queue_metadata.get("pr_number"),
                pr_url=queue_metadata.get("pr_url"),
                owner=queue_metadata.get("owner"),
                repo=queue_metadata.get("repo"),
                branch=queue_metadata.get("branch"),
                created_at=created_at,
                updated_at=updated_at,
                claimed_by=claimed_by,
                claimed_at=datetime.utcnow(),
                priority=queue_metadata.get("priority", 0),
            )
    
    def get_review_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Check the review state for a task.
        
        Args:
            task_id: The task ID to check
            
        Returns:
            Dictionary with review status information, or None if task not found
        """
        task = get_task_by_id(task_id)
        if not task:
            return None
        
        # Get review record if exists
        reviews = execute(
            "SELECT * FROM reviews WHERE task_id = ? ORDER BY completed_at DESC",
            (task_id,)
        )
        
        # Parse payload
        payload = task.get("payload") or "{}"
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        
        queue_metadata = payload.get("review_queue", {})
        
        # Determine if review is in progress
        is_claimed = task.get("claimed_by") is not None
        lease_expired = True
        if task.get("lease_expires_at"):
            lease_expires_at = task["lease_expires_at"]
            if isinstance(lease_expires_at, str):
                lease_expires_at = datetime.fromisoformat(lease_expires_at.replace("Z", "+00:00"))
            lease_expired = datetime.utcnow() > lease_expires_at
        
        return {
            "task_id": task_id,
            "correlation_id": task["correlation_id"],
            "status": task["status"],
            "is_review_required": task["status"] in [
                ReviewStatus.REVIEW_QUEUED.value,
                ReviewStatus.REVIEW_FAILED.value,
            ],
            "is_approved": task["status"] == ReviewStatus.APPROVED.value,
            "is_blocked": task["status"] == ReviewStatus.BLOCKED.value,
            "is_in_remediation": task["status"] == ReviewStatus.REMEDIATION_QUEUED.value,
            "is_claimed": is_claimed and not lease_expired,
            "claimed_by": task.get("claimed_by") if is_claimed and not lease_expired else None,
            "pr_number": queue_metadata.get("pr_number"),
            "pr_url": queue_metadata.get("pr_url"),
            "priority": queue_metadata.get("priority", 0),
            "reviews": reviews,
            "review_count": len(reviews),
            "latest_review": reviews[0] if reviews else None,
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
        }
    
    def list_pending_reviews(
        self,
        limit: int = 50,
        include_claimed: bool = False,
    ) -> List[ReviewQueueItem]:
        """
        List all pending reviews in the queue.
        
        Args:
            limit: Maximum number of results
            include_claimed: Whether to include claimed tasks
            
        Returns:
            List of ReviewQueueItems
        """
        if include_claimed:
            rows = execute(
                """
                SELECT * FROM tasks 
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (ReviewStatus.REVIEW_QUEUED.value, limit)
            )
        else:
            rows = execute(
                """
                SELECT * FROM tasks 
                WHERE status = ?
                AND (claimed_by IS NULL OR lease_expires_at < datetime('now'))
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (ReviewStatus.REVIEW_QUEUED.value, limit)
            )
        
        items = []
        for task in rows:
            payload = task.get("payload") or "{}"
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            
            queue_metadata = payload.get("review_queue", {})
            
            # Handle datetime fields that may already be datetime objects
            created_at = task.get("created_at")
            updated_at = task.get("updated_at")
            claimed_at = task.get("claimed_at")
            
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if isinstance(updated_at, str):
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            if isinstance(claimed_at, str):
                claimed_at = datetime.fromisoformat(claimed_at.replace("Z", "+00:00"))
            
            items.append(ReviewQueueItem(
                task_id=task["id"],
                correlation_id=task["correlation_id"],
                status=ReviewStatus(task["status"]),
                pr_number=queue_metadata.get("pr_number"),
                pr_url=queue_metadata.get("pr_url"),
                owner=queue_metadata.get("owner"),
                repo=queue_metadata.get("repo"),
                branch=queue_metadata.get("branch"),
                created_at=created_at,
                updated_at=updated_at,
                claimed_by=task.get("claimed_by"),
                claimed_at=claimed_at,
                priority=queue_metadata.get("priority", 0),
            ))
        
        return items
    
    def release_claim(self, task_id: str, released_by: Optional[str] = None) -> bool:
        """
        Release a claimed review task back to the queue.
        
        Args:
            task_id: The task ID to release
            released_by: Who is releasing the claim
            
        Returns:
            True if released successfully
        """
        task = get_task_by_id(task_id)
        if not task:
            return False
        
        if not task.get("claimed_by"):
            return False
        
        with transaction() as conn:
            conn.execute(
                """
                UPDATE tasks 
                SET claimed_by = NULL, 
                    claimed_at = NULL,
                    lease_expires_at = NULL
                WHERE id = ?
                """,
                (task_id,)
            )
        
        # Log audit event
        self._log_audit_event(
            correlation_id=task["correlation_id"],
            action="review.released",
            payload={
                "task_id": task_id,
                "released_by": released_by,
                "previously_claimed_by": task.get("claimed_by"),
            },
        )
        
        self.logger.info(f"Task {task_id} released from claim by {released_by}")
        return True
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the review queue.
        
        Returns:
            Dictionary with queue statistics
        """
        stats = execute(
            """
            SELECT 
                status,
                COUNT(*) as count,
                AVG(julianday('now') - julianday(created_at)) * 24 * 60 as avg_age_minutes
            FROM tasks
            WHERE status IN (?, ?, ?, ?)
            GROUP BY status
            """,
            (
                ReviewStatus.REVIEW_QUEUED.value,
                ReviewStatus.REVIEW_FAILED.value,
                ReviewStatus.REMEDIATION_QUEUED.value,
                ReviewStatus.APPROVED.value,
            )
        )
        
        # Count claimed reviews
        claimed_count = execute(
            """
            SELECT COUNT(*) as count
            FROM tasks
            WHERE status = ?
            AND claimed_by IS NOT NULL
            AND lease_expires_at > datetime('now')
            """,
            (ReviewStatus.REVIEW_QUEUED.value,),
            fetch_one=True
        )
        
        result = {
            "by_status": {row["status"]: {"count": row["count"], "avg_age_minutes": row["avg_age_minutes"]} for row in stats},
            "claimed_count": claimed_count["count"] if claimed_count else 0,
        }
        
        # Calculate totals
        total_pending = result["by_status"].get(ReviewStatus.REVIEW_QUEUED.value, {}).get("count", 0)
        result["total_pending"] = total_pending
        result["total_awaiting_review"] = total_pending + result["claimed_count"]
        
        return result
