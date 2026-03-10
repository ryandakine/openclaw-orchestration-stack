"""
GitHub Webhook Handler for Symphony PR Bridge.

Handles incoming GitHub webhooks for PR events, review events,
and validates webhook signatures.
"""

import json
import hmac
import hashlib
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

try:
    from .github.client import GitHubClient
    from .github.labels import LabelManager
    from .review.reviewer import ReviewManager
except ImportError:
    from github.client import GitHubClient
    from github.labels import LabelManager
    from review.reviewer import ReviewManager

logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Supported GitHub webhook event types."""
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    PULL_REQUEST_REVIEW_COMMENT = "pull_request_review_comment"
    ISSUE_COMMENT = "issue_comment"
    PUSH = "push"
    STATUS = "status"
    CHECK_RUN = "check_run"
    CHECK_SUITE = "check_suite"
    WORKFLOW_RUN = "workflow_run"


class PREventAction(str, Enum):
    """Pull request event actions."""
    OPENED = "opened"
    CLOSED = "closed"
    REOPENED = "reopened"
    SYNCHRONIZE = "synchronize"  # New commits pushed
    EDITED = "edited"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    LABELED = "labeled"
    UNLABELED = "unlabeled"
    READY_FOR_REVIEW = "ready_for_review"
    CONVERTED_TO_DRAFT = "converted_to_draft"


class ReviewEventAction(str, Enum):
    """Pull request review event actions."""
    SUBMITTED = "submitted"
    EDITED = "edited"
    DISMISSED = "dismissed"


@dataclass
class WebhookPayload:
    """Parsed webhook payload."""
    event_type: WebhookEventType
    action: str
    repository: Dict[str, Any]
    sender: Dict[str, Any]
    raw_data: Dict[str, Any]
    
    @property
    def owner(self) -> str:
        """Get repository owner."""
        return self.repository.get("owner", {}).get("login", "")
    
    @property
    def repo(self) -> str:
        """Get repository name."""
        return self.repository.get("name", "")
    
    @property
    def full_name(self) -> str:
        """Get full repository name (owner/repo)."""
        return self.repository.get("full_name", "")


@dataclass
class PREvent:
    """Pull request event data."""
    action: PREventAction
    pr_number: int
    pr_title: str
    pr_body: Optional[str]
    pr_state: str
    pr_draft: bool
    head_ref: str
    base_ref: str
    head_sha: str
    user_login: str
    labels: list
    
    @classmethod
    def from_payload(cls, payload: dict) -> "PREvent":
        """Create PREvent from webhook payload."""
        pr_data = payload.get("pull_request", {})
        return cls(
            action=PREventAction(payload.get("action", "")),
            pr_number=pr_data.get("number", 0),
            pr_title=pr_data.get("title", ""),
            pr_body=pr_data.get("body"),
            pr_state=pr_data.get("state", ""),
            pr_draft=pr_data.get("draft", False),
            head_ref=pr_data.get("head", {}).get("ref", ""),
            base_ref=pr_data.get("base", {}).get("ref", ""),
            head_sha=pr_data.get("head", {}).get("sha", ""),
            user_login=pr_data.get("user", {}).get("login", ""),
            labels=[label.get("name", "") for label in pr_data.get("labels", [])],
        )


@dataclass
class ReviewEvent:
    """Pull request review event data."""
    action: ReviewEventAction
    pr_number: int
    review_id: int
    review_state: str
    review_body: Optional[str]
    reviewer_login: str
    
    @classmethod
    def from_payload(cls, payload: dict) -> "ReviewEvent":
        """Create ReviewEvent from webhook payload."""
        pr_data = payload.get("pull_request", {})
        review_data = payload.get("review", {})
        return cls(
            action=ReviewEventAction(payload.get("action", "")),
            pr_number=pr_data.get("number", 0),
            review_id=review_data.get("id", 0),
            review_state=review_data.get("state", ""),
            review_body=review_data.get("body"),
            reviewer_login=review_data.get("user", {}).get("login", ""),
        )


class WebhookHandler:
    """Handles GitHub webhook events."""
    
    def __init__(
        self,
        secret: Optional[str] = None,
        client: Optional[GitHubClient] = None,
        event_handlers: Optional[Dict[str, Callable]] = None,
    ):
        """
        Initialize webhook handler.
        
        Args:
            secret: Webhook secret for signature validation
            client: GitHub API client
            event_handlers: Custom event handler callbacks
        """
        self.secret = secret
        self.client = client
        self.event_handlers = event_handlers or {}
        self.label_manager = LabelManager(client) if client else None
        self.review_manager = ReviewManager(client) if client else None
    
    def validate_signature(
        self,
        payload: bytes,
        signature: str,
        algorithm: str = "sha256",
    ) -> bool:
        """
        Validate webhook signature.
        
        Args:
            payload: Raw request body bytes
            signature: Signature from X-Hub-Signature-256 or X-Hub-Signature header
            algorithm: Hash algorithm (sha256 or sha1)
            
        Returns:
            True if signature is valid
        """
        if not self.secret:
            logger.warning("No webhook secret configured, skipping signature validation")
            return True
        
        # Normalize signature header
        if "=" in signature:
            _, signature = signature.split("=", 1)
        
        # Compute expected signature
        if algorithm == "sha256":
            expected = hmac.new(
                self.secret.encode("utf-8"),
                payload,
                hashlib.sha256,
            ).hexdigest()
        else:
            expected = hmac.new(
                self.secret.encode("utf-8"),
                payload,
                hashlib.sha1,
            ).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, signature)
    
    def parse_payload(self, payload: bytes, event_type: str) -> WebhookPayload:
        """
        Parse webhook payload.
        
        Args:
            payload: Raw request body
            event_type: Event type from X-GitHub-Event header
            
        Returns:
            Parsed WebhookPayload
        """
        data = json.loads(payload)
        
        return WebhookPayload(
            event_type=WebhookEventType(event_type),
            action=data.get("action", ""),
            repository=data.get("repository", {}),
            sender=data.get("sender", {}),
            raw_data=data,
        )
    
    def handle_webhook(
        self,
        payload: bytes,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Handle incoming webhook request.
        
        Args:
            payload: Raw request body
            headers: Request headers
            
        Returns:
            Response dictionary
        """
        # Get signature from headers
        signature = headers.get(
            "X-Hub-Signature-256",
            headers.get("X-Hub-Signature", "")
        )
        
        # Validate signature
        if not self.validate_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return {"status": "error", "message": "Invalid signature"}
        
        # Get event type
        event_type = headers.get("X-GitHub-Event", "")
        if not event_type:
            return {"status": "error", "message": "Missing event type"}
        
        logger.info(f"Received {event_type} webhook")
        
        try:
            # Parse payload
            webhook_payload = self.parse_payload(payload, event_type)
            
            # Route to appropriate handler
            if event_type == WebhookEventType.PULL_REQUEST:
                return self.handle_pr_event(webhook_payload)
            elif event_type == WebhookEventType.PULL_REQUEST_REVIEW:
                return self.handle_review_event(webhook_payload)
            elif event_type in self.event_handlers:
                return self.event_handlers[event_type](webhook_payload)
            else:
                logger.debug(f"No handler for event type: {event_type}")
                return {"status": "ignored", "event": event_type}
                
        except Exception as e:
            logger.exception(f"Error handling webhook: {e}")
            return {"status": "error", "message": str(e)}
    
    def handle_pr_event(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Handle pull request events.
        
        Args:
            payload: Parsed webhook payload
            
        Returns:
            Response dictionary
        """
        event = PREvent.from_payload(payload.raw_data)
        logger.info(f"Handling PR #{event.pr_number} {event.action.value} event")
        
        # Call custom handler if registered
        custom_handler = self.event_handlers.get("pull_request")
        if custom_handler:
            return custom_handler(payload, event)
        
        # Default handling
        if event.action == PREventAction.OPENED:
            return self._handle_pr_opened(payload, event)
        elif event.action == PREventAction.SYNCHRONIZE:
            return self._handle_pr_synchronize(payload, event)
        elif event.action == PREventAction.READY_FOR_REVIEW:
            return self._handle_pr_ready_for_review(payload, event)
        elif event.action == PREventAction.LABELED:
            return self._handle_pr_labeled(payload, event)
        elif event.action == PREventAction.CLOSED:
            return self._handle_pr_closed(payload, event)
        
        return {"status": "success", "action": event.action.value, "handled": False}
    
    def _handle_pr_opened(
        self,
        payload: WebhookPayload,
        event: PREvent,
    ) -> Dict[str, Any]:
        """Handle PR opened event."""
        if not self.client:
            return {"status": "skipped", "reason": "no client"}
        
        # Add openclaw label if not present
        if "openclaw" not in event.labels:
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "openclaw",
            )
        
        # Add needs-review label for non-draft PRs
        if not event.pr_draft and "needs-review" not in event.labels:
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "needs-review",
            )
        
        # Post welcome comment
        if self.review_manager:
            welcome_body = self._generate_welcome_comment(event)
            self.review_manager.post_comment(
                payload.owner,
                payload.repo,
                event.pr_number,
                welcome_body,
            )
        
        return {
            "status": "success",
            "action": "opened",
            "pr_number": event.pr_number,
            "labels_added": ["openclaw", "needs-review"] if not event.pr_draft else ["openclaw"],
        }
    
    def _handle_pr_synchronize(
        self,
        payload: WebhookPayload,
        event: PREvent,
    ) -> Dict[str, Any]:
        """Handle PR synchronize (new commits) event."""
        if not self.client:
            return {"status": "skipped", "reason": "no client"}
        
        # Update labels - remove approval since code changed
        if "approved" in event.labels:
            self.label_manager.remove_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "approved",
            )
        
        if "changes-requested" in event.labels:
            self.label_manager.remove_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "changes-requested",
            )
        
        # Re-add needs-review if not draft
        if not event.pr_draft and "needs-review" not in event.labels:
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "needs-review",
            )
        
        return {
            "status": "success",
            "action": "synchronize",
            "pr_number": event.pr_number,
        }
    
    def _handle_pr_ready_for_review(
        self,
        payload: WebhookPayload,
        event: PREvent,
    ) -> Dict[str, Any]:
        """Handle PR marked ready for review."""
        if not self.client:
            return {"status": "skipped", "reason": "no client"}
        
        # Add needs-review label
        if "needs-review" not in event.labels:
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "needs-review",
            )
        
        return {
            "status": "success",
            "action": "ready_for_review",
            "pr_number": event.pr_number,
        }
    
    def _handle_pr_labeled(
        self,
        payload: WebhookPayload,
        event: PREvent,
    ) -> Dict[str, Any]:
        """Handle PR labeled event."""
        # Get the label that was added
        label_data = payload.raw_data.get("label", {})
        label_name = label_data.get("name", "")
        
        logger.info(f"PR #{event.pr_number} labeled with '{label_name}'")
        
        return {
            "status": "success",
            "action": "labeled",
            "pr_number": event.pr_number,
            "label": label_name,
        }
    
    def _handle_pr_closed(
        self,
        payload: WebhookPayload,
        event: PREvent,
    ) -> Dict[str, Any]:
        """Handle PR closed event."""
        # Check if merged
        pr_data = payload.raw_data.get("pull_request", {})
        merged = pr_data.get("merged", False)
        
        return {
            "status": "success",
            "action": "closed",
            "pr_number": event.pr_number,
            "merged": merged,
        }
    
    def handle_review_event(self, payload: WebhookPayload) -> Dict[str, Any]:
        """
        Handle pull request review events.
        
        Args:
            payload: Parsed webhook payload
            
        Returns:
            Response dictionary
        """
        event = ReviewEvent.from_payload(payload.raw_data)
        logger.info(f"Handling review {event.action.value} on PR #{event.pr_number}")
        
        # Call custom handler if registered
        custom_handler = self.event_handlers.get("pull_request_review")
        if custom_handler:
            return custom_handler(payload, event)
        
        # Default handling
        if event.action == ReviewEventAction.SUBMITTED:
            return self._handle_review_submitted(payload, event)
        
        return {"status": "success", "action": event.action.value, "handled": False}
    
    def _handle_review_submitted(
        self,
        payload: WebhookPayload,
        event: ReviewEvent,
    ) -> Dict[str, Any]:
        """Handle review submitted event."""
        if not self.client:
            return {"status": "skipped", "reason": "no client"}
        
        # Update labels based on review state
        if event.review_state == "approved":
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "approved",
            )
            self.label_manager.remove_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "needs-review",
            )
        
        elif event.review_state == "changes_requested":
            self.label_manager.add_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "changes-requested",
            )
            self.label_manager.remove_label(
                payload.owner,
                payload.repo,
                event.pr_number,
                "needs-review",
            )
        
        return {
            "status": "success",
            "action": "review_submitted",
            "pr_number": event.pr_number,
            "review_state": event.review_state,
        }
    
    def _generate_welcome_comment(self, event: PREvent) -> str:
        """Generate welcome comment for new PRs."""
        lines = [
            "## 👋 Welcome to OpenClaw!",
            "",
            f"Thanks for opening this pull request. The Symphony automated review system will analyze your changes.",
            "",
            "### What's Next?",
            "",
            "1. **Automated Review**: Symphony will perform an automated review of your code",
            "2. **Labels**: This PR has been labeled with `openclaw` for tracking",
            "3. **Status Updates**: You'll receive updates as the review progresses",
            "",
            "### Labels",
            "",
            "- `openclaw` - Managed by OpenClaw Orchestration Stack",
            "- `needs-review` - Awaiting automated review",
            "- `approved` - Approved by Symphony",
            "- `changes-requested` - Changes required",
            "",
            "---",
            "*This is an automated message from [Symphony](https://github.com/openclaw-orchestration-stack) 🎼*",
        ]
        return "\n".join(lines)
    
    def register_handler(
        self,
        event_type: str,
        handler: Callable[[WebhookPayload], Dict[str, Any]],
    ):
        """
        Register a custom event handler.
        
        Args:
            event_type: Event type to handle
            handler: Handler function
        """
        self.event_handlers[event_type] = handler
        logger.info(f"Registered handler for {event_type}")
    
    def verify_webhook(
        self,
        payload: bytes,
        signature: str,
        event_type: str,
    ) -> bool:
        """
        Verify webhook authenticity.
        
        Args:
            payload: Raw request body
            signature: Signature header value
            event_type: Event type header value
            
        Returns:
            True if webhook is valid
        """
        if not self.validate_signature(payload, signature):
            return False
        
        try:
            WebhookEventType(event_type)
        except ValueError:
            logger.warning(f"Unknown event type: {event_type}")
            return False
        
        return True


def create_webhook_handler(
    secret: Optional[str] = None,
    token: Optional[str] = None,
) -> WebhookHandler:
    """
    Create a configured webhook handler.
    
    Args:
        secret: Webhook secret
        token: GitHub API token
        
    Returns:
        Configured WebhookHandler
    """
    client = None
    if token:
        client = GitHubClient(token=token)
    
    return WebhookHandler(secret=secret, client=client)
