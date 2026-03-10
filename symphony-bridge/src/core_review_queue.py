"""
Core Review Queue for OpenClaw Mandatory Review System.

Simplified review queue that ensures every DevClaw task passes through
review before being considered complete.
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

# Import database utilities
try:
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        get_task_by_id,
    )
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        get_task_by_id,
    )

from review_state_machine import ReviewState, ReviewResult, get_next_state

logger = logging.getLogger(__name__)


@dataclass
class ReviewRecord:
    """A review record for a task."""
    id: str
    task_id: str
    result: ReviewResult
    summary: str
    reviewer_id: str
    completed_at: datetime
    findings: Optional[List[Dict]] = None


class ReviewQueue:
    """
    Mandatory review queue for OpenClaw tasks.
    
    Every task completed by DevClaw MUST pass through this review queue
    before being considered done.
    """
    
    def __init__(self):
        """Initialize the review queue."""
        self.logger = logging.getLogger(__name__)
    
    def _log_audit(self, correlation_id: str, action: str, payload: Dict[str, Any]) -> None:
        """Log an audit event."""
        try:
            insert("audit_events", {
                "correlation_id": correlation_id,
                "actor": "symphony",
                "action": action,
                "payload": json.dumps(payload),
            })
        except Exception as e:
            self.logger.error(f"Failed to log audit: {e}")
    
    def enqueue_for_review(self, task_id: str) -> None:
        """
        Enqueue a task for review when DevClaw completes.
        
        Moves task from 'executing' to 'review_queued' status.
        
        Args:
            task_id: The task ID to enqueue
            
        Raises:
            ValueError: If task not found or not in correct state
        """
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        # Task must be in 'executing' state to be enqueued
        if task["status"] != "executing":
            raise ValueError(
                f"Task {task_id} must be in 'executing' state, got '{task['status']}'"
            )
        
        correlation_id = task["correlation_id"]
        
        with transaction() as conn:
            conn.execute(
                """
                UPDATE tasks 
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (ReviewState.REVIEW_QUEUED.value, task_id)
            )
        
        self._log_audit(correlation_id, "review.enqueued", {"task_id": task_id})
        self.logger.info(f"Task {task_id} enqueued for review")
    
    def get_next_for_review(self) -> Optional[str]:
        """
        Get the next task waiting for review.
        
        Returns the task_id of the oldest unclaimed review_queued task.
        
        Returns:
            task_id if available, None if queue is empty
        """
        result = execute(
            """
            SELECT id FROM tasks 
            WHERE status = ?
            AND (claimed_by IS NULL OR lease_expires_at < datetime('now'))
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (ReviewState.REVIEW_QUEUED.value,),
            fetch_one=True
        )
        
        return result["id"] if result else None
    
    def submit_review(
        self,
        task_id: str,
        result: str,
        summary: str,
        reviewer_id: str = "symphony",
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Submit a review result for a task.
        
        Args:
            task_id: The task ID being reviewed
            result: 'approve', 'reject', or 'block'
            summary: Review summary text
            reviewer_id: Who performed the review
            findings: Optional list of findings
            
        Returns:
            Dict with review outcome details
            
        Raises:
            ValueError: If task not found or invalid result
        """
        task = get_task_by_id(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        
        if task["status"] != ReviewState.REVIEW_QUEUED.value:
            raise ValueError(
                f"Task {task_id} is not in review_queued state, got '{task['status']}'"
            )
        
        # Parse result
        try:
            review_result = ReviewResult(result)
        except ValueError:
            raise ValueError(f"Invalid result '{result}', must be approve/reject/blocked")
        
        correlation_id = task["correlation_id"]
        review_id = str(uuid.uuid4())
        
        with transaction() as conn:
            # Record the review
            conn.execute(
                """
                INSERT INTO reviews (id, task_id, result, summary, reviewer_id, findings, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (review_id, task_id, review_result.value, summary, reviewer_id, 
                 json.dumps(findings or []))
            )
            
            # Handle based on result
            if review_result == ReviewResult.APPROVE:
                # Move to approved
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP,
                        claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (ReviewState.APPROVED.value, task_id)
                )
                
                self._log_audit(correlation_id, "review.approved", {
                    "task_id": task_id,
                    "review_id": review_id,
                })
                self.logger.info(f"Task {task_id} approved")
                
                return {
                    "success": True,
                    "action": "approve",
                    "task_id": task_id,
                    "new_state": ReviewState.APPROVED.value,
                }
                
            elif review_result == ReviewResult.REJECT:
                # Mark original as review_failed
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = ?, claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (ReviewState.REVIEW_FAILED.value, task_id)
                )
                
                # Create remediation task
                remediation_task_id = str(uuid.uuid4())
                original_payload = task.get("payload") or "{}"
                if isinstance(original_payload, str):
                    try:
                        original_payload = json.loads(original_payload)
                    except json.JSONDecodeError:
                        original_payload = {}
                
                remediation_payload = {
                    "original_task_id": task_id,
                    "findings": findings or [],
                    "original_intent": task.get("intent"),
                    "is_remediation": True,
                }
                
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, correlation_id, idempotency_key, status, assigned_to,
                        intent, payload, source, requested_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        remediation_task_id,
                        correlation_id,
                        f"remediation_{task_id}_{remediation_task_id}",
                        ReviewState.REMEDIATION_QUEUED.value,
                        "DEVCLAW",
                        f"Remediate: {task.get('intent', 'Unknown')}",
                        json.dumps(remediation_payload),
                        task.get("source", "api"),
                        task.get("requested_by", "symphony"),
                    )
                )
                
                self._log_audit(correlation_id, "review.rejected", {
                    "task_id": task_id,
                    "review_id": review_id,
                    "remediation_task_id": remediation_task_id,
                })
                self.logger.info(f"Task {task_id} rejected, remediation {remediation_task_id} created")
                
                return {
                    "success": True,
                    "action": "reject",
                    "task_id": task_id,
                    "new_state": ReviewState.REVIEW_FAILED.value,
                    "remediation_task_id": remediation_task_id,
                }
                
            elif review_result == ReviewResult.BLOCK:
                # Move to blocked
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = ?, claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (ReviewState.BLOCKED.value, task_id)
                )
                
                self._log_audit(correlation_id, "review.blocked", {
                    "task_id": task_id,
                    "review_id": review_id,
                    "reason": summary,
                })
                self.logger.warning(f"Task {task_id} blocked: {summary}")
                
                return {
                    "success": True,
                    "action": review_result.value,
                    "task_id": task_id,
                    "new_state": ReviewState.BLOCKED.value,
                }
        
        # Should never reach here
        return {"success": False, "error": "Unknown result type"}
    
    def get_review_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the review status for a task.
        
        Args:
            task_id: The task ID to check
            
        Returns:
            Dict with status info, or None if task not found
        """
        task = get_task_by_id(task_id)
        if not task:
            return None
        
        # Get reviews for this task
        reviews = execute(
            "SELECT * FROM reviews WHERE task_id = ? ORDER BY completed_at DESC",
            (task_id,)
        )
        
        return {
            "task_id": task_id,
            "status": task["status"],
            "is_review_required": task["status"] == ReviewState.REVIEW_QUEUED.value,
            "is_approved": task["status"] == ReviewState.APPROVED.value,
            "is_blocked": task["status"] == ReviewState.BLOCKED.value,
            "is_in_remediation": task["status"] == ReviewState.REMEDIATION_QUEUED.value,
            "review_count": len(reviews),
            "reviews": reviews,
        }
