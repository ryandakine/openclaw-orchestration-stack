"""
PR Lifecycle Manager for Symphony PR Bridge.

Manages the complete lifecycle of pull requests including creation,
updates, merge state checking, issue linking, and status updates.
"""

import re
import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

try:
    from .github.client import GitHubClient, PullRequest, GitHubError, GitHubNotFoundError
    from .github.labels import LabelManager, STANDARD_LABELS
    from .review.reviewer import ReviewManager, ReviewEvent
    from .review.summary import (
        ReviewSummary,
        ReviewFinding,
        format_review_body,
        create_review_comments_from_findings,
    )
except ImportError:
    from github.client import GitHubClient, PullRequest, GitHubError, GitHubNotFoundError
    from github.labels import LabelManager, STANDARD_LABELS
    from review.reviewer import ReviewManager, ReviewEvent
    from review.summary import (
        ReviewSummary,
        ReviewFinding,
        format_review_body,
        create_review_comments_from_findings,
    )

logger = logging.getLogger(__name__)


class PRState(str, Enum):
    """PR lifecycle states."""
    DRAFT = "draft"
    OPEN = "open"
    NEEDS_REVIEW = "needs_review"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    READY_TO_MERGE = "ready_to_merge"
    MERGED = "merged"
    CLOSED = "closed"
    BLOCKED = "blocked"


class MergeState(str, Enum):
    """PR mergeability states."""
    CLEAN = "clean"  # Ready to merge
    BLOCKED = "blocked"  # Blocked by protections
    BEHIND = "behind"  # Needs update from base branch
    DIRTY = "dirty"  # Has merge conflicts
    DRAFT = "draft"  # Is a draft PR
    UNKNOWN = "unknown"  # State unknown


@dataclass
class PRStatus:
    """Current status of a PR."""
    pr_number: int
    state: PRState
    merge_state: MergeState
    is_mergeable: bool
    checks_passing: Optional[bool]
    required_reviews: int
    current_approvals: int
    labels: List[str]
    linked_issues: List[str]
    last_updated: datetime
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pr_number": self.pr_number,
            "state": self.state.value,
            "merge_state": self.merge_state.value,
            "is_mergeable": self.is_mergeable,
            "checks_passing": self.checks_passing,
            "required_reviews": self.required_reviews,
            "current_approvals": self.current_approvals,
            "labels": self.labels,
            "linked_issues": self.linked_issues,
            "last_updated": self.last_updated.isoformat(),
        }


class PRLifecycleManager:
    """Manages the complete PR lifecycle."""
    
    def __init__(
        self,
        client: GitHubClient,
        label_manager: Optional[LabelManager] = None,
        review_manager: Optional[ReviewManager] = None,
    ):
        """
        Initialize PR lifecycle manager.
        
        Args:
            client: GitHub API client
            label_manager: Label manager instance
            review_manager: Review manager instance
        """
        self.client = client
        self.label_manager = label_manager or LabelManager(client)
        self.review_manager = review_manager or ReviewManager(client)
    
    def create_or_update_pr(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: Optional[str] = None,
        pr_number: Optional[int] = None,
        draft: bool = False,
        labels: Optional[List[str]] = None,
        link_issues: Optional[List[str]] = None,
    ) -> PullRequest:
        """
        Create a new PR or update an existing one.
        
        Args:
            owner: Repository owner
            repo: Repository name
            title: PR title
            head: Head branch
            base: Base branch
            body: PR body/description
            pr_number: Existing PR number to update (if None, creates new)
            draft: Create as draft
            labels: Labels to apply
            link_issues: Issue numbers to link
            
        Returns:
            Created or updated PullRequest
        """
        # Prepare body with issue links
        full_body = self._prepare_body(body, link_issues)
        
        if pr_number:
            # Update existing PR
            try:
                pr = self.client.update_pr(
                    owner=owner,
                    repo=repo,
                    pr_number=pr_number,
                    title=title,
                    body=full_body,
                )
                logger.info(f"Updated PR #{pr_number} in {owner}/{repo}")
            except GitHubNotFoundError:
                logger.warning(f"PR #{pr_number} not found, creating new")
                pr = None
        else:
            pr = None
        
        if not pr:
            # Create new PR
            pr = self.client.create_pr(
                owner=owner,
                repo=repo,
                title=title,
                head=head,
                base=base,
                body=full_body,
                draft=draft,
            )
            logger.info(f"Created PR #{pr.number} in {owner}/{repo}")
        
        # Apply labels
        if labels:
            self.label_manager.add_labels(owner, repo, pr.number, labels)
        
        # Add openclaw label by default
        if "openclaw" not in (labels or []):
            self.label_manager.add_label(owner, repo, pr.number, "openclaw")
        
        return pr
    
    def _prepare_body(
        self,
        body: Optional[str],
        link_issues: Optional[List[str]],
    ) -> str:
        """Prepare PR body with issue links."""
        parts = []
        
        if body:
            parts.append(body)
        
        if link_issues:
            parts.append("")
            parts.append("### Linked Issues")
            parts.append("")
            for issue in link_issues:
                # Handle both "#123" and "123" formats
                issue_num = issue.lstrip("#")
                parts.append(f"- Closes #{issue_num}")
        
        return "\n".join(parts) if parts else ""
    
    def check_merge_state(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> Tuple[MergeState, Dict[str, Any]]:
        """
        Check the merge state of a PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            Tuple of (MergeState, details dict)
        """
        pr = self.client.get_pr(owner, repo, pr_number)
        
        # Get check runs status
        checks_data = self._get_combined_status(owner, repo, pr.head_sha)
        
        # Get review status
        review_status = self.review_manager.get_combined_review_status(
            owner, repo, pr_number
        )
        
        # Determine merge state
        if pr.draft:
            merge_state = MergeState.DRAFT
        elif pr.mergeable_state == "clean":
            merge_state = MergeState.CLEAN
        elif pr.mergeable_state == "blocked":
            merge_state = MergeState.BLOCKED
        elif pr.mergeable_state == "behind":
            merge_state = MergeState.BEHIND
        elif pr.mergeable_state == "dirty":
            merge_state = MergeState.DIRTY
        else:
            merge_state = MergeState.UNKNOWN
        
        is_mergeable = pr.mergeable is True and merge_state == MergeState.CLEAN
        
        details = {
            "mergeable": pr.mergeable,
            "mergeable_state": pr.mergeable_state,
            "checks_state": checks_data.get("state"),
            "checks_total": checks_data.get("total_count", 0),
            "checks_completed": len(checks_data.get("statuses", [])),
            "review_state": review_status.get("state"),
            "approval_count": review_status.get("approval_count", 0),
            "changes_requested_count": review_status.get("changes_requested_count", 0),
        }
        
        return merge_state, details
    
    def _get_combined_status(
        self,
        owner: str,
        repo: str,
        ref: str,
    ) -> dict:
        """Get combined status for a ref."""
        try:
            return self.client._request(
                "GET",
                f"/repos/{owner}/{repo}/commits/{ref}/status",
            )
        except GitHubError as e:
            logger.warning(f"Failed to get status for {ref}: {e}")
            return {"state": "unknown", "total_count": 0, "statuses": []}
    
    def link_to_issue(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        issue_number: str,
    ) -> PullRequest:
        """
        Link a PR to an issue by updating the PR body.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            issue_number: Issue number to link
            
        Returns:
            Updated PullRequest
        """
        pr = self.client.get_pr(owner, repo, pr_number)
        
        # Check if already linked
        issue_num = issue_number.lstrip("#")
        if f"#{issue_num}" in (pr.body or ""):
            logger.debug(f"PR #{pr_number} already linked to issue #{issue_num}")
            return pr
        
        # Add link to body
        new_body = self._prepare_body(pr.body, [issue_number])
        
        return self.client.update_pr(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            body=new_body,
        )
    
    def post_status_update(
        self,
        owner: str,
        pr_number: int,
        repo: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Post a status update comment on a PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            status: Status message
            details: Additional details to include
            
        Returns:
            Created comment
        """
        lines = [
            "## 📊 Symphony Status Update",
            "",
            f"**Status**: {status}",
        ]
        
        if details:
            lines.append("")
            lines.append("### Details")
            lines.append("")
            for key, value in details.items():
                lines.append(f"- **{key}**: {value}")
        
        lines.append("")
        lines.append("---")
        lines.append(f"*Updated at {datetime.utcnow().isoformat()} UTC*")
        
        body = "\n".join(lines)
        return self.review_manager.post_comment(owner, repo, pr_number, body)
    
    def get_pr_status(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> PRStatus:
        """
        Get comprehensive PR status.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            PRStatus object
        """
        pr = self.client.get_pr(owner, repo, pr_number)
        merge_state, details = self.check_merge_state(owner, repo, pr_number)
        
        # Determine lifecycle state
        state = self._determine_lifecycle_state(pr, merge_state, details)
        
        # Get linked issues from body
        linked_issues = self._extract_linked_issues(pr.body)
        
        return PRStatus(
            pr_number=pr.number,
            state=state,
            merge_state=merge_state,
            is_mergeable=details.get("mergeable", False),
            checks_passing=details.get("checks_state") == "success",
            required_reviews=1,  # Default, could be fetched from branch protection
            current_approvals=details.get("approval_count", 0),
            labels=pr.labels,
            linked_issues=linked_issues,
            last_updated=datetime.fromisoformat(pr.updated_at.replace("Z", "+00:00")),
        )
    
    def _determine_lifecycle_state(
        self,
        pr: PullRequest,
        merge_state: MergeState,
        details: dict,
    ) -> PRState:
        """Determine the lifecycle state of a PR."""
        if pr.state == "closed":
            return PRState.CLOSED
        
        if pr.merged:
            return PRState.MERGED
        
        if pr.draft:
            return PRState.DRAFT
        
        if "blocked" in pr.labels:
            return PRState.BLOCKED
        
        if details.get("changes_requested_count", 0) > 0:
            return PRState.CHANGES_REQUESTED
        
        if "approved" in pr.labels or details.get("approval_count", 0) >= 1:
            if merge_state == MergeState.CLEAN:
                return PRState.READY_TO_MERGE
            return PRState.APPROVED
        
        if "needs-review" in pr.labels:
            return PRState.NEEDS_REVIEW
        
        if "in-review" in pr.labels:
            return PRState.IN_REVIEW
        
        return PRState.OPEN
    
    def _extract_linked_issues(self, body: Optional[str]) -> List[str]:
        """Extract linked issue numbers from PR body."""
        if not body:
            return []
        
        # Match patterns like "Closes #123", "Fixes #123", "Relates to #123"
        pattern = r"(?:closes|fixes|resolves|relates to|links to)\s+#(\d+)"
        matches = re.findall(pattern, body, re.IGNORECASE)
        return [f"#{m}" for m in matches]
    
    def transition_pr_state(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        new_state: PRState,
    ) -> PRStatus:
        """
        Transition a PR to a new lifecycle state.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            new_state: Target state
            
        Returns:
            Updated PRStatus
        """
        current_status = self.get_pr_status(owner, repo, pr_number)
        
        # Update labels based on state transition
        labels_to_add = []
        labels_to_remove = []
        
        if new_state == PRState.NEEDS_REVIEW:
            labels_to_add.append("needs-review")
            labels_to_remove.extend(["approved", "changes-requested"])
        
        elif new_state == PRState.APPROVED:
            labels_to_add.append("approved")
            labels_to_remove.extend(["needs-review", "changes-requested"])
        
        elif new_state == PRState.CHANGES_REQUESTED:
            labels_to_add.append("changes-requested")
            labels_to_remove.extend(["needs-review", "approved"])
        
        elif new_state == PRState.READY_TO_MERGE:
            labels_to_add.extend(["approved", "auto-merge"])
            labels_to_remove.extend(["needs-review", "changes-requested"])
        
        elif new_state == PRState.BLOCKED:
            labels_to_add.append("blocked")
        
        # Apply label changes
        for label in labels_to_add:
            if label not in current_status.labels:
                self.label_manager.add_label(owner, repo, pr_number, label)
        
        for label in labels_to_remove:
            if label in current_status.labels:
                self.label_manager.remove_label(owner, repo, pr_number, label)
        
        # Post status update
        self.post_status_update(
            owner,
            repo,
            pr_number,
            f"PR transitioned to **{new_state.value}**",
        )
        
        return self.get_pr_status(owner, repo, pr_number)
    
    def submit_review_from_summary(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        summary: ReviewSummary,
    ) -> dict:
        """
        Submit a review based on a ReviewSummary.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            summary: ReviewSummary with findings
            
        Returns:
            Created review
        """
        # Determine review event from result
        if summary.result == "approve":
            event = ReviewEvent.APPROVE
        elif summary.result == "reject":
            event = ReviewEvent.REQUEST_CHANGES
        else:
            event = ReviewEvent.COMMENT
        
        # Format review body
        body = format_review_body(summary, concise=False)
        
        # Create review comments from findings
        comments = create_review_comments_from_findings(summary.findings)
        
        # Submit review
        review = self.review_manager.post_review(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            body=body,
            event=event,
            comments=comments if comments else None,
        )
        
        # Update labels based on review
        if summary.result == "approve":
            self.label_manager.add_label(owner, repo, pr_number, "symphony-reviewed")
            self.label_manager.add_label(owner, repo, pr_number, "approved")
            self.label_manager.remove_label(owner, repo, pr_number, "needs-review")
            self.label_manager.remove_label(owner, repo, pr_number, "changes-requested")
        elif summary.result == "reject":
            self.label_manager.add_label(owner, repo, pr_number, "symphony-reviewed")
            self.label_manager.add_label(owner, repo, pr_number, "changes-requested")
            self.label_manager.remove_label(owner, repo, pr_number, "needs-review")
        
        logger.info(f"Submitted {summary.result} review on PR #{pr_number}")
        return review.to_dict() if hasattr(review, 'to_dict') else review
    
    def find_existing_symphony_pr(
        self,
        owner: str,
        repo: str,
        head_branch: str,
    ) -> Optional[PullRequest]:
        """
        Find an existing Symphony PR for a branch.
        
        Args:
            owner: Repository owner
            repo: Repository name
            head_branch: Head branch name
            
        Returns:
            Existing PullRequest or None
        """
        prs = self.client.list_prs(
            owner=owner,
            repo=repo,
            state="open",
            head=f"{owner}:{head_branch}",
        )
        
        for pr in prs:
            if "openclaw" in pr.labels or "symphony-generated" in pr.labels:
                return pr
        
        return None
    
    def close_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment: Optional[str] = None,
    ) -> PullRequest:
        """
        Close a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            comment: Optional closing comment
            
        Returns:
            Closed PullRequest
        """
        if comment:
            self.review_manager.post_comment(owner, repo, pr_number, comment)
        
        return self.client.update_pr(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            state="closed",
        )
