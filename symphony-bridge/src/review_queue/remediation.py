"""
Remediation Loop for Symphony Bridge.

Manages the remediation workflow:
- Create remediation tasks from rejected reviews
- Track remediation chains (original → remediation)
- Handle remediation completion and re-review
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime

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


@dataclass
class RemediationChain:
    """Represents a chain of remediation attempts."""
    original_task_id: str
    remediation_task_ids: List[str]
    current_status: str
    total_attempts: int
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "original_task_id": self.original_task_id,
            "remediation_task_ids": self.remediation_task_ids,
            "current_status": self.current_status,
            "total_attempts": self.total_attempts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class RemediationManager:
    """
    Manages the remediation workflow for rejected reviews.
    
    When a review is rejected, a remediation task is created that
    goes back to DevClaw. This manager tracks the chain of
    original → remediation tasks.
    """
    
    # Maximum number of remediation attempts before requiring human intervention
    MAX_REMEDIATION_ATTEMPTS = 3
    
    def __init__(self):
        """Initialize the remediation manager."""
        self.logger = logging.getLogger(__name__)
    
    def _log_audit_event(
        self,
        correlation_id: str,
        action: str,
        payload: Dict[str, Any],
        actor: str = "symphony",
    ) -> None:
        """Log an audit event."""
        try:
            # Note: id is auto-increment, don't specify it
            insert("audit_events", {
                "correlation_id": correlation_id,
                "actor": actor,
                "action": action,
                "payload": json.dumps(payload),
            })
        except Exception as e:
            self.logger.error(f"Failed to log audit event: {e}")
    
    def create_remediation_task(
        self,
        original_task_id: str,
        findings: List[Dict[str, Any]],
        priority_adjustment: int = 0,
    ) -> Dict[str, Any]:
        """
        Create a remediation task from a rejected review.
        
        This is called when a review is rejected and the task needs
        to go back to DevClaw for fixes.
        
        Args:
            original_task_id: The original task that was rejected
            findings: List of findings that need to be addressed
            priority_adjustment: Adjustment to priority (usually higher)
            
        Returns:
            Dictionary with remediation task details
            
        Raises:
            ValueError: If original task not found or max attempts exceeded
        """
        # Get original task
        original_task = get_task_by_id(original_task_id)
        if not original_task:
            raise ValueError(f"Original task {original_task_id} not found")
        
        correlation_id = original_task["correlation_id"]
        
        # Check remediation chain
        chain = self.track_remediation_chain(original_task_id)
        
        if chain["total_attempts"] >= self.MAX_REMEDIATION_ATTEMPTS:
            raise ValueError(
                f"Maximum remediation attempts ({self.MAX_REMEDIATION_ATTEMPTS}) "
                f"exceeded for task {original_task_id}. Human intervention required."
            )
        
        # Create remediation task
        remediation_task_id = str(uuid.uuid4())
        
        # Build remediation intent
        original_intent = original_task.get("intent", "Unknown task")
        remediation_intent = f"Remediate: {original_intent}"
        
        # Parse original payload
        original_payload = original_task.get("payload") or "{}"
        if isinstance(original_payload, str):
            try:
                original_payload = json.loads(original_payload)
            except json.JSONDecodeError:
                original_payload = {}
        else:
            original_payload = dict(original_payload) if original_payload else {}
        
        # Get original priority
        queue_metadata = original_payload.get("review_queue", {})
        original_priority = queue_metadata.get("priority", 0)
        
        # Build remediation payload
        remediation_payload = {
            "original_task_id": original_task_id,
            "remediation_count": chain["total_attempts"] + 1,
            "findings": findings,
            "original_intent": original_intent,
            "original_payload": original_payload,
            "is_remediation": True,
            "remediation_chain": chain["remediation_task_ids"],
            "priority": original_priority + priority_adjustment + 1,  # Increase priority
        }
        
        # Copy PR info from original
        if queue_metadata.get("pr_number"):
            remediation_payload["pr_number"] = queue_metadata["pr_number"]
            remediation_payload["pr_url"] = queue_metadata.get("pr_url")
            remediation_payload["owner"] = queue_metadata.get("owner")
            remediation_payload["repo"] = queue_metadata.get("repo")
            remediation_payload["branch"] = queue_metadata.get("branch")
        
        with transaction() as conn:
            # Create remediation task
            conn.execute(
                """
                INSERT INTO tasks (
                    id, correlation_id, idempotency_key, status, assigned_to,
                    intent, payload, source, requested_by, retry_count, max_retries,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    remediation_task_id,
                    correlation_id,
                    f"remediation_{original_task_id}_{remediation_task_id}",
                    "remediation_queued",
                    "DEVCLAW",
                    remediation_intent,
                    json.dumps(remediation_payload),
                    original_task.get("source", "api"),
                    original_task.get("requested_by", "symphony"),
                    0,
                    original_task.get("max_retries", 3),
                )
            )
            
            # Update original task with remediation reference
            original_payload["latest_remediation_task_id"] = remediation_task_id
            original_payload["remediation_count"] = chain["total_attempts"] + 1
            
            conn.execute(
                """
                UPDATE tasks 
                SET payload = ?
                WHERE id = ?
                """,
                (json.dumps(original_payload), original_task_id)
            )
        
        # Log audit event
        self._log_audit_event(
            correlation_id=correlation_id,
            action="remediation.created",
            payload={
                "original_task_id": original_task_id,
                "remediation_task_id": remediation_task_id,
                "remediation_count": chain["total_attempts"] + 1,
                "findings_count": len(findings),
            },
        )
        
        self.logger.info(
            f"Created remediation task {remediation_task_id} "
            f"for original task {original_task_id} "
            f"(attempt {chain['total_attempts'] + 1})"
        )
        
        return {
            "remediation_task_id": remediation_task_id,
            "original_task_id": original_task_id,
            "remediation_count": chain["total_attempts"] + 1,
            "findings_count": len(findings),
            "priority": remediation_payload["priority"],
            "status": "remediation_queued",
            "assigned_to": "DEVCLAW",
        }
    
    def track_remediation_chain(self, original_task_id: str) -> Dict[str, Any]:
        """
        Track the remediation chain for a task.
        
        Args:
            original_task_id: The original task ID
            
        Returns:
            Dictionary with chain information
        """
        # Get original task
        original_task = get_task_by_id(original_task_id)
        if not original_task:
            return {
                "original_task_id": original_task_id,
                "remediation_task_ids": [],
                "current_status": "not_found",
                "total_attempts": 0,
            }
        
        # Find all remediation tasks for this original task
        remediation_tasks = execute(
            """
            SELECT id, status, payload, created_at
            FROM tasks
            WHERE json_extract(payload, '$.original_task_id') = ?
            AND json_extract(payload, '$.is_remediation') = 1
            ORDER BY created_at ASC
            """,
            (original_task_id,)
        )
        
        remediation_ids = [t["id"] for t in remediation_tasks]
        
        # Determine current status
        current_status = original_task["status"]
        
        # If there's an active remediation task, use its status
        for task in remediation_tasks:
            if task["status"] not in ["failed", "approved", "blocked"]:
                current_status = task["status"]
                break
        
        # Get completion time if all done
        completed_at = None
        if current_status in ["approved", "merged"]:
            completed_at = original_task.get("completed_at")
        
        return {
            "original_task_id": original_task_id,
            "remediation_task_ids": remediation_ids,
            "current_status": current_status,
            "total_attempts": len(remediation_ids),
            "created_at": original_task.get("created_at"),
            "completed_at": completed_at,
            "remediation_tasks": remediation_tasks,
        }
    
    def complete_remediation(
        self,
        remediation_task_id: str,
        success: bool,
        pr_number: Optional[int] = None,
        pr_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mark a remediation task as complete.
        
        This is called when DevClaw finishes the remediation work.
        The task is then moved back to review_queued for re-review.
        
        Args:
            remediation_task_id: The remediation task ID
            success: Whether remediation was successful
            pr_number: Updated PR number
            pr_url: Updated PR URL
            
        Returns:
            Dictionary with completion details
        """
        remediation_task = get_task_by_id(remediation_task_id)
        if not remediation_task:
            raise ValueError(f"Remediation task {remediation_task_id} not found")
        
        if remediation_task["status"] != "remediation_queued":
            raise ValueError(
                f"Remediation task {remediation_task_id} is not in remediation_queued status"
            )
        
        correlation_id = remediation_task["correlation_id"]
        
        # Parse payload
        payload = remediation_task.get("payload") or "{}"
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        else:
            payload = dict(payload) if payload else {}
        
        original_task_id = payload.get("original_task_id")
        
        with transaction() as conn:
            if success:
                # Move remediation task to review_queued for re-review
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'review_queued',
                        assigned_to = 'SYMPHONY',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (remediation_task_id,)
                )
                
                # Update payload with completion info
                payload["remediation_completed_at"] = datetime.utcnow().isoformat()
                payload["remediation_successful"] = True
                if pr_number:
                    payload["pr_number"] = pr_number
                if pr_url:
                    payload["pr_url"] = pr_url
                
                conn.execute(
                    """
                    UPDATE tasks 
                    SET payload = ?
                    WHERE id = ?
                    """,
                    (json.dumps(payload), remediation_task_id)
                )
                
                # Also update the original task to reflect remediation complete
                if original_task_id:
                    original_task = get_task_by_id(original_task_id)
                    if original_task:
                        orig_payload = original_task.get("payload") or "{}"
                        if isinstance(orig_payload, str):
                            try:
                                orig_payload = json.loads(orig_payload)
                            except json.JSONDecodeError:
                                orig_payload = {}
                        else:
                            orig_payload = dict(orig_payload) if orig_payload else {}
                        
                        orig_payload["latest_remediation_completed"] = datetime.utcnow().isoformat()
                        orig_payload["latest_remediation_successful"] = True
                        
                        conn.execute(
                            """
                            UPDATE tasks 
                            SET payload = ?
                            WHERE id = ?
                            """,
                            (json.dumps(orig_payload), original_task_id)
                        )
                
                new_status = "review_queued"
                message = "Remediation completed, queued for re-review"
            else:
                # Mark remediation as failed
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'failed',
                        updated_at = CURRENT_TIMESTAMP,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (remediation_task_id,)
                )
                
                payload["remediation_completed_at"] = datetime.utcnow().isoformat()
                payload["remediation_successful"] = False
                
                conn.execute(
                    """
                    UPDATE tasks 
                    SET payload = ?
                    WHERE id = ?
                    """,
                    (json.dumps(payload), remediation_task_id)
                )
                
                new_status = "failed"
                message = "Remediation failed"
        
        # Log audit event
        self._log_audit_event(
            correlation_id=correlation_id,
            action="remediation.completed",
            payload={
                "remediation_task_id": remediation_task_id,
                "original_task_id": original_task_id,
                "success": success,
                "new_status": new_status,
            },
        )
        
        self.logger.info(
            f"Remediation task {remediation_task_id} completed with status: {new_status}"
        )
        
        return {
            "remediation_task_id": remediation_task_id,
            "original_task_id": original_task_id,
            "success": success,
            "new_status": new_status,
            "message": message,
        }
    
    def get_remediation_findings(self, remediation_task_id: str) -> List[Dict[str, Any]]:
        """
        Get the findings that need to be addressed for a remediation task.
        
        Args:
            remediation_task_id: The remediation task ID
            
        Returns:
            List of findings
        """
        task = get_task_by_id(remediation_task_id)
        if not task:
            return []
        
        payload = task.get("payload") or "{}"
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return []
        
        return payload.get("findings", [])
    
    def resolve_remediation_chain(
        self,
        original_task_id: str,
        final_status: str,
    ) -> Dict[str, Any]:
        """
        Mark an entire remediation chain as resolved.
        
        This is called when the original task is finally approved
        or permanently blocked.
        
        Args:
            original_task_id: The original task ID
            final_status: The final status (approved, blocked, etc.)
            
        Returns:
            Dictionary with resolution details
        """
        chain = self.track_remediation_chain(original_task_id)
        
        with transaction() as conn:
            # Update original task
            conn.execute(
                """
                UPDATE tasks 
                SET status = ?,
                    updated_at = CURRENT_TIMESTAMP,
                    completed_at = CASE WHEN ? IN ('approved', 'blocked') THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id = ?
                """,
                (final_status, final_status, original_task_id)
            )
            
            # Mark all remediation tasks as resolved
            for remediation_id in chain["remediation_task_ids"]:
                conn.execute(
                    """
                    UPDATE tasks 
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (remediation_id,)
                )
        
        # Log audit event
        self._log_audit_event(
            correlation_id=chain.get("original_task_id", ""),
            action="remediation.chain_resolved",
            payload={
                "original_task_id": original_task_id,
                "final_status": final_status,
                "total_attempts": chain["total_attempts"],
            },
        )
        
        self.logger.info(
            f"Remediation chain for {original_task_id} resolved with status: {final_status}"
        )
        
        return {
            "original_task_id": original_task_id,
            "final_status": final_status,
            "total_attempts": chain["total_attempts"],
            "remediation_task_ids": chain["remediation_task_ids"],
        }
    
    def get_pending_remediations(
        self,
        assigned_to: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get all pending remediation tasks.
        
        Args:
            assigned_to: Filter by assigned worker
            limit: Maximum results
            
        Returns:
            List of pending remediation tasks
        """
        if assigned_to:
            rows = execute(
                """
                SELECT * FROM tasks
                WHERE status = 'remediation_queued'
                AND assigned_to = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (assigned_to, limit)
            )
        else:
            rows = execute(
                """
                SELECT * FROM tasks
                WHERE status = 'remediation_queued'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,)
            )
        
        results = []
        for task in rows:
            payload = task.get("payload") or "{}"
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {}
            
            results.append({
                "task_id": task["id"],
                "original_task_id": payload.get("original_task_id"),
                "remediation_count": payload.get("remediation_count", 1),
                "findings_count": len(payload.get("findings", [])),
                "intent": task["intent"],
                "priority": payload.get("priority", 0),
                "assigned_to": task["assigned_to"],
                "created_at": task["created_at"],
            })
        
        return results
