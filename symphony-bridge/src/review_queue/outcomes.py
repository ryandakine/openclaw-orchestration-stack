"""
Review Outcome Handlers for Symphony Bridge.

Handles the different review outcomes:
- Approve: Mark PR ready for merge
- Reject: Create remediation task back to DevClaw
- Block: Mark as blocked, human needed
"""

import json
import uuid
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

try:
    from shared.db import (
        get_connection,
        transaction,
        execute,
        insert,
        update,
        get_task_by_id,
    )
    from ..github.client import GitHubClient
    from ..github.labels import LabelManager
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
    from github.client import GitHubClient
    from github.labels import LabelManager

logger = logging.getLogger(__name__)


class ReviewResult(str, Enum):
    """Review result types."""
    APPROVE = "approve"
    REJECT = "reject"
    BLOCK = "blocked"


@dataclass
class OutcomeResult:
    """Result of handling a review outcome."""
    success: bool
    action: str
    task_id: str
    message: str
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "action": self.action,
            "task_id": self.task_id,
            "message": self.message,
            "details": self.details,
        }


class OutcomeHandler:
    """
    Handles review outcomes from Symphony reviewer.
    
    This is the critical quality gate enforcement:
    - APPROVE: Task is complete, PR ready for merge
    - REJECT: Task needs remediation, back to DevClaw
    - BLOCK: Task blocked, human intervention required
    """
    
    def __init__(
        self,
        github_client: Optional[GitHubClient] = None,
        label_manager: Optional[LabelManager] = None,
    ):
        """
        Initialize the outcome handler.
        
        Args:
            github_client: Optional GitHub client for PR updates
            label_manager: Optional label manager for PR labels
        """
        self.github_client = github_client
        self.label_manager = label_manager
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
    
    def handle_approve(
        self,
        task_id: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        review_comment: Optional[str] = None,
    ) -> OutcomeResult:
        """
        Handle APPROVE outcome - Mark PR ready for merge.
        
        This is the success path - the task has passed review and is
        considered complete. The PR is marked as approved and ready.
        
        Args:
            task_id: The task ID
            owner: Repository owner (for PR updates)
            repo: Repository name (for PR updates)
            pr_number: PR number (for PR updates)
            review_comment: Optional approval comment
            
        Returns:
            OutcomeResult with action details
        """
        task = get_task_by_id(task_id)
        if not task:
            return OutcomeResult(
                success=False,
                action="approve",
                task_id=task_id,
                message=f"Task {task_id} not found",
            )
        
        correlation_id = task["correlation_id"]
        
        try:
            with transaction() as conn:
                # Update task status to approved
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'approved',
                        updated_at = CURRENT_TIMESTAMP,
                        completed_at = CURRENT_TIMESTAMP,
                        claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (task_id,)
                )
            
            # Update PR labels if GitHub client available
            pr_updated = False
            if self.label_manager and owner and repo and pr_number:
                try:
                    self.label_manager.add_label(owner, repo, pr_number, "approved")
                    self.label_manager.remove_label(owner, repo, pr_number, "needs-review")
                    self.label_manager.remove_label(owner, repo, pr_number, "changes-requested")
                    pr_updated = True
                except Exception as e:
                    self.logger.warning(f"Failed to update PR labels: {e}")
            
            # Log audit event
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.outcome.approve",
                payload={
                    "task_id": task_id,
                    "pr_number": pr_number,
                    "pr_updated": pr_updated,
                },
            )
            
            self.logger.info(f"Task {task_id} approved - ready for merge")
            
            return OutcomeResult(
                success=True,
                action="approve",
                task_id=task_id,
                message="Task approved and marked ready for merge",
                details={
                    "pr_updated": pr_updated,
                    "pr_number": pr_number,
                    "status": "approved",
                },
            )
            
        except Exception as e:
            self.logger.exception(f"Failed to handle approve for task {task_id}: {e}")
            return OutcomeResult(
                success=False,
                action="approve",
                task_id=task_id,
                message=f"Failed to approve: {e}",
            )
    
    def handle_reject(
        self,
        task_id: str,
        findings: List[Dict[str, Any]],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        auto_create_remediation: bool = True,
    ) -> OutcomeResult:
        """
        Handle REJECT outcome - Create remediation task back to DevClaw.
        
        The task failed review and needs to be fixed. A remediation
        task is created that goes back to DevClaw for fixes.
        
        Args:
            task_id: The original task ID
            findings: List of findings that caused rejection
            owner: Repository owner (for PR updates)
            repo: Repository name (for PR updates)
            pr_number: PR number (for PR updates)
            auto_create_remediation: Whether to auto-create remediation task
            
        Returns:
            OutcomeResult with action details
        """
        task = get_task_by_id(task_id)
        if not task:
            return OutcomeResult(
                success=False,
                action="reject",
                task_id=task_id,
                message=f"Task {task_id} not found",
            )
        
        correlation_id = task["correlation_id"]
        remediation_task_id = None
        
        try:
            with transaction() as conn:
                # Update original task status to review_failed
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'review_failed',
                        updated_at = CURRENT_TIMESTAMP,
                        claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (task_id,)
                )
                
                # Create remediation task if requested
                if auto_create_remediation:
                    remediation_task_id = str(uuid.uuid4())
                    
                    # Build remediation payload
                    original_payload = task.get("payload") or "{}"
                    if isinstance(original_payload, str):
                        try:
                            original_payload = json.loads(original_payload)
                        except json.JSONDecodeError:
                            original_payload = {}
                    
                    remediation_payload = {
                        "original_task_id": task_id,
                        "remediation_count": self._get_remediation_count(task_id) + 1,
                        "findings": findings,
                        "original_intent": task.get("intent"),
                        "original_payload": original_payload,
                        "is_remediation": True,
                    }
                    
                    conn.execute(
                        """
                        INSERT INTO tasks (
                            id, correlation_id, idempotency_key, status, assigned_to,
                            intent, payload, source, requested_by, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """,
                        (
                            remediation_task_id,
                            correlation_id,
                            f"remediation_{task_id}_{remediation_task_id}",
                            "remediation_queued",
                            "DEVCLAW",
                            f"Remediate: {task.get('intent', 'Unknown')}",
                            json.dumps(remediation_payload),
                            task.get("source", "api"),
                            task.get("requested_by", "symphony"),
                        )
                    )
                    
                    # Update original task with remediation reference
                    original_payload_updated = task.get("payload") or "{}"
                    if isinstance(original_payload_updated, str):
                        try:
                            original_payload_updated = json.loads(original_payload_updated)
                        except json.JSONDecodeError:
                            original_payload_updated = {}
                    else:
                        original_payload_updated = dict(original_payload_updated) if original_payload_updated else {}
                    
                    original_payload_updated["latest_remediation_task_id"] = remediation_task_id
                    original_payload_updated["remediation_count"] = remediation_payload["remediation_count"]
                    
                    conn.execute(
                        """
                        UPDATE tasks 
                        SET payload = ?
                        WHERE id = ?
                        """,
                        (json.dumps(original_payload_updated), task_id)
                    )
            
            # Update PR labels if GitHub client available
            pr_updated = False
            if self.label_manager and owner and repo and pr_number:
                try:
                    self.label_manager.add_label(owner, repo, pr_number, "changes-requested")
                    self.label_manager.remove_label(owner, repo, pr_number, "needs-review")
                    self.label_manager.remove_label(owner, repo, pr_number, "approved")
                    pr_updated = True
                except Exception as e:
                    self.logger.warning(f"Failed to update PR labels: {e}")
            
            # Log audit event
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.outcome.reject",
                payload={
                    "task_id": task_id,
                    "remediation_task_id": remediation_task_id,
                    "findings_count": len(findings),
                    "pr_number": pr_number,
                    "pr_updated": pr_updated,
                },
            )
            
            self.logger.info(
                f"Task {task_id} rejected - remediation task {remediation_task_id} created"
            )
            
            return OutcomeResult(
                success=True,
                action="reject",
                task_id=task_id,
                message="Task rejected and remediation queued",
                details={
                    "remediation_task_id": remediation_task_id,
                    "findings_count": len(findings),
                    "pr_updated": pr_updated,
                    "pr_number": pr_number,
                    "status": "review_failed",
                },
            )
            
        except Exception as e:
            self.logger.exception(f"Failed to handle reject for task {task_id}: {e}")
            return OutcomeResult(
                success=False,
                action="reject",
                task_id=task_id,
                message=f"Failed to reject: {e}",
            )
    
    def handle_block(
        self,
        task_id: str,
        reason: str,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        notify_channels: Optional[List[str]] = None,
    ) -> OutcomeResult:
        """
        Handle BLOCK outcome - Mark as blocked, human needed.
        
        The task has critical issues that require human intervention.
        This blocks the task from proceeding and notifies appropriate
        channels.
        
        Args:
            task_id: The task ID
            reason: Why the task is blocked
            owner: Repository owner (for PR updates)
            repo: Repository name (for PR updates)
            pr_number: PR number (for PR updates)
            notify_channels: Channels to notify (e.g., ['slack', 'email'])
            
        Returns:
            OutcomeResult with action details
        """
        task = get_task_by_id(task_id)
        if not task:
            return OutcomeResult(
                success=False,
                action="block",
                task_id=task_id,
                message=f"Task {task_id} not found",
            )
        
        correlation_id = task["correlation_id"]
        
        try:
            with transaction() as conn:
                # Update task status to blocked
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'blocked',
                        updated_at = CURRENT_TIMESTAMP,
                        claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL
                    WHERE id = ?
                    """,
                    (task_id,)
                )
                
                # Add block reason to payload
                original_payload = task.get("payload") or "{}"
                if isinstance(original_payload, str):
                    try:
                        original_payload = json.loads(original_payload)
                    except json.JSONDecodeError:
                        original_payload = {}
                else:
                    original_payload = dict(original_payload) if original_payload else {}
                
                original_payload["block_reason"] = reason
                original_payload["blocked_at"] = datetime.utcnow().isoformat()
                original_payload["blocked_by"] = "symphony_reviewer"
                
                conn.execute(
                    """
                    UPDATE tasks 
                    SET payload = ?
                    WHERE id = ?
                    """,
                    (json.dumps(original_payload), task_id)
                )
            
            # Update PR labels if GitHub client available
            pr_updated = False
            if self.label_manager and owner and repo and pr_number:
                try:
                    self.label_manager.add_label(owner, repo, pr_number, "blocked")
                    self.label_manager.remove_label(owner, repo, pr_number, "needs-review")
                    self.label_manager.remove_label(owner, repo, pr_number, "approved")
                    pr_updated = True
                except Exception as e:
                    self.logger.warning(f"Failed to update PR labels: {e}")
            
            # Log audit event
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.outcome.block",
                payload={
                    "task_id": task_id,
                    "reason": reason,
                    "pr_number": pr_number,
                    "pr_updated": pr_updated,
                    "notify_channels": notify_channels,
                },
            )
            
            self.logger.warning(f"Task {task_id} BLOCKED: {reason}")
            
            # Note: Notifications would be handled here in a full implementation
            
            return OutcomeResult(
                success=True,
                action="block",
                task_id=task_id,
                message=f"Task blocked: {reason}",
                details={
                    "reason": reason,
                    "pr_updated": pr_updated,
                    "pr_number": pr_number,
                    "status": "blocked",
                    "notify_channels": notify_channels or [],
                },
            )
            
        except Exception as e:
            self.logger.exception(f"Failed to handle block for task {task_id}: {e}")
            return OutcomeResult(
                success=False,
                action="block",
                task_id=task_id,
                message=f"Failed to block: {e}",
            )
    
    def process_review_result(
        self,
        task_id: str,
        result: ReviewResult,
        findings: List[Dict[str, Any]],
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OutcomeResult:
        """
        Process a review result and dispatch to appropriate handler.
        
        This is the main entry point for handling review results.
        
        Args:
            task_id: The task ID
            result: The review result
            findings: List of findings
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            metadata: Additional metadata
            
        Returns:
            OutcomeResult from the handler
        """
        if result == ReviewResult.APPROVE:
            return self.handle_approve(
                task_id=task_id,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                review_comment=metadata.get("review_comment") if metadata else None,
            )
        elif result == ReviewResult.REJECT:
            return self.handle_reject(
                task_id=task_id,
                findings=findings,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                auto_create_remediation=metadata.get("auto_create_remediation", True) if metadata else True,
            )
        elif result == ReviewResult.BLOCK:
            reason = "Critical issues found"
            if findings:
                reason = findings[0].get("message", reason)
            if metadata and metadata.get("block_reason"):
                reason = metadata["block_reason"]
            
            return self.handle_block(
                task_id=task_id,
                reason=reason,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                notify_channels=metadata.get("notify_channels") if metadata else None,
            )
        else:
            return OutcomeResult(
                success=False,
                action="unknown",
                task_id=task_id,
                message=f"Unknown review result: {result}",
            )
    
    def _get_remediation_count(self, task_id: str) -> int:
        """Get the number of previous remediation attempts for a task."""
        try:
            result = execute(
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE json_extract(payload, '$.original_task_id') = ?
                AND json_extract(payload, '$.is_remediation') = 1
                """,
                (task_id,),
                fetch_one=True
            )
            return result["count"] if result else 0
        except Exception as e:
            self.logger.warning(f"Failed to get remediation count: {e}")
            return 0
    
    def unblock_task(
        self,
        task_id: str,
        unblocked_by: str,
        reason: str,
    ) -> OutcomeResult:
        """
        Unblock a previously blocked task (manual intervention).
        
        Args:
            task_id: The blocked task ID
            unblocked_by: Who is unblocking the task
            reason: Why the task is being unblocked
            
        Returns:
            OutcomeResult
        """
        task = get_task_by_id(task_id)
        if not task:
            return OutcomeResult(
                success=False,
                action="unblock",
                task_id=task_id,
                message=f"Task {task_id} not found",
            )
        
        if task["status"] != "blocked":
            return OutcomeResult(
                success=False,
                action="unblock",
                task_id=task_id,
                message=f"Task {task_id} is not blocked (status: {task['status']})",
            )
        
        correlation_id = task["correlation_id"]
        
        try:
            with transaction() as conn:
                # Update task to review_queued for re-review
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'review_queued',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (task_id,)
                )
                
                # Update payload
                original_payload = task.get("payload") or "{}"
                if isinstance(original_payload, str):
                    try:
                        original_payload = json.loads(original_payload)
                    except json.JSONDecodeError:
                        original_payload = {}
                else:
                    original_payload = dict(original_payload) if original_payload else {}
                
                original_payload["unblocked_at"] = datetime.utcnow().isoformat()
                original_payload["unblocked_by"] = unblocked_by
                original_payload["unblock_reason"] = reason
                
                conn.execute(
                    """
                    UPDATE tasks 
                    SET payload = ?
                    WHERE id = ?
                    """,
                    (json.dumps(original_payload), task_id)
                )
            
            # Log audit event
            self._log_audit_event(
                correlation_id=correlation_id,
                action="review.unblock",
                payload={
                    "task_id": task_id,
                    "unblocked_by": unblocked_by,
                    "reason": reason,
                },
            )
            
            self.logger.info(f"Task {task_id} unblocked by {unblocked_by}")
            
            return OutcomeResult(
                success=True,
                action="unblock",
                task_id=task_id,
                message="Task unblocked and queued for re-review",
                details={
                    "unblocked_by": unblocked_by,
                    "reason": reason,
                    "new_status": "review_queued",
                },
            )
            
        except Exception as e:
            self.logger.exception(f"Failed to unblock task {task_id}: {e}")
            return OutcomeResult(
                success=False,
                action="unblock",
                task_id=task_id,
                message=f"Failed to unblock: {e}",
            )
