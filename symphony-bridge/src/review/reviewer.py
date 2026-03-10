"""
PR Review Management for Symphony PR Bridge.

Provides methods for posting reviews, approving PRs, requesting changes,
and posting comments on pull requests.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    from ..github.client import GitHubClient, GitHubError, GitHubNotFoundError
except ImportError:
    from github.client import GitHubClient, GitHubError, GitHubNotFoundError

logger = logging.getLogger(__name__)


class ReviewEvent(str, Enum):
    """GitHub PR review events."""
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    COMMENT = "COMMENT"


class ReviewState(str, Enum):
    """GitHub PR review states."""
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


@dataclass
class ReviewComment:
    """Represents a review comment on a specific line of code."""
    path: str
    body: str
    line: Optional[int] = None
    side: str = "RIGHT"
    start_line: Optional[int] = None
    start_side: Optional[str] = None
    commit_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API request."""
        data = {
            "path": self.path,
            "body": self.body,
            "side": self.side,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.start_line is not None:
            data["start_line"] = self.start_line
        if self.start_side:
            data["start_side"] = self.start_side
        if self.commit_id:
            data["commit_id"] = self.commit_id
        return data


@dataclass
class Review:
    """Represents a GitHub PR review."""
    id: int
    node_id: str
    user_login: str
    body: Optional[str]
    state: ReviewState
    commit_id: str
    html_url: str
    submitted_at: Optional[str] = None
    comments_count: int = 0
    
    @classmethod
    def from_api_response(cls, data: dict) -> "Review":
        """Create Review from GitHub API response."""
        return cls(
            id=data["id"],
            node_id=data["node_id"],
            user_login=data["user"]["login"],
            body=data.get("body"),
            state=ReviewState(data["state"]),
            commit_id=data["commit_id"],
            html_url=data["html_url"],
            submitted_at=data.get("submitted_at"),
            comments_count=data.get("comments_count", 0),
        )


@dataclass
class PRComment:
    """Represents a general PR comment (not tied to code)."""
    id: int
    node_id: str
    user_login: str
    body: str
    html_url: str
    created_at: str
    updated_at: str
    issue_url: Optional[str] = None
    
    @classmethod
    def from_api_response(cls, data: dict) -> "PRComment":
        """Create PRComment from GitHub API response."""
        return cls(
            id=data["id"],
            node_id=data["node_id"],
            user_login=data["user"]["login"],
            body=data["body"],
            html_url=data["html_url"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            issue_url=data.get("issue_url"),
        )


class ReviewManager:
    """Manages PR reviews and comments."""
    
    def __init__(self, client: GitHubClient):
        """
        Initialize review manager.
        
        Args:
            client: GitHub API client
        """
        self.client = client
    
    def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: ReviewEvent = ReviewEvent.COMMENT,
        comments: Optional[List[ReviewComment]] = None,
        commit_id: Optional[str] = None,
    ) -> Review:
        """
        Post a review on a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            body: Review body text
            event: Review event type (APPROVE, REQUEST_CHANGES, COMMENT)
            comments: List of line-specific comments
            commit_id: Specific commit SHA to review (defaults to PR head)
            
        Returns:
            Created Review
        """
        data: Dict[str, Any] = {
            "body": body,
            "event": event.value,
        }
        
        if comments:
            data["comments"] = [c.to_dict() for c in comments]
        
        if commit_id:
            data["commit_id"] = commit_id
        
        response = self.client._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json_data=data,
        )
        
        logger.info(f"Posted {event.value} review on PR #{pr_number} in {owner}/{repo}")
        return Review.from_api_response(response)
    
    def approve_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str = "Approved by Symphony automated review.",
    ) -> Review:
        """
        Approve a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            body: Approval message
            
        Returns:
            Created Review
        """
        return self.post_review(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            body=body,
            event=ReviewEvent.APPROVE,
        )
    
    def request_changes(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        comments: Optional[List[ReviewComment]] = None,
    ) -> Review:
        """
        Request changes on a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            body: Explanation of required changes
            comments: List of line-specific comments
            
        Returns:
            Created Review
        """
        return self.post_review(
            owner=owner,
            repo=repo,
            pr_number=pr_number,
            body=body,
            event=ReviewEvent.REQUEST_CHANGES,
            comments=comments,
        )
    
    def post_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
    ) -> PRComment:
        """
        Post a general comment on a pull request (not a review).
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            body: Comment text
            
        Returns:
            Created PRComment
        """
        response = self.client._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            json_data={"body": body},
        )
        
        logger.info(f"Posted comment on PR #{pr_number} in {owner}/{repo}")
        return PRComment.from_api_response(response)
    
    def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        comment: ReviewComment,
    ) -> dict:
        """
        Post a single review comment on a specific line.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            comment: ReviewComment to post
            
        Returns:
            API response as dictionary
        """
        response = self.client._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            json_data=comment.to_dict(),
        )
        
        logger.info(f"Posted review comment on {comment.path}:{comment.line} in PR #{pr_number}")
        return response
    
    def list_reviews(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        per_page: int = 30,
        page: int = 1,
    ) -> List[Review]:
        """
        List all reviews on a pull request.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            per_page: Results per page (max 100)
            page: Page number
            
        Returns:
            List of Reviews
        """
        response = self.client._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            params={"per_page": per_page, "page": page},
        )
        
        return [Review.from_api_response(r) for r in response]
    
    def get_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_id: int,
    ) -> Review:
        """
        Get a specific review by ID.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            review_id: Review ID
            
        Returns:
            Review
        """
        response = self.client._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}",
        )
        
        return Review.from_api_response(response)
    
    def list_review_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_id: int,
        per_page: int = 30,
        page: int = 1,
    ) -> List[dict]:
        """
        List comments for a specific review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            review_id: Review ID
            per_page: Results per page (max 100)
            page: Page number
            
        Returns:
            List of comment dictionaries
        """
        return self.client._request(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}/comments",
            params={"per_page": per_page, "page": page},
        )
    
    def list_pr_comments(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        since: Optional[str] = None,
        per_page: int = 30,
        page: int = 1,
    ) -> List[PRComment]:
        """
        List all general comments on a PR (not review comments).
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            since: Only comments updated after this time (ISO 8601 format)
            per_page: Results per page (max 100)
            page: Page number
            
        Returns:
            List of PRComments
        """
        params: Dict[str, Any] = {"per_page": per_page, "page": page}
        if since:
            params["since"] = since
        
        response = self.client._request(
            "GET",
            f"/repos/{owner}/{repo}/issues/{pr_number}/comments",
            params=params,
        )
        
        return [PRComment.from_api_response(c) for c in response]
    
    def update_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        body: str,
    ) -> PRComment:
        """
        Update an existing PR comment.
        
        Args:
            owner: Repository owner
            repo: Repository name
            comment_id: Comment ID
            body: New comment text
            
        Returns:
            Updated PRComment
        """
        response = self.client._request(
            "PATCH",
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
            json_data={"body": body},
        )
        
        logger.info(f"Updated comment {comment_id} in {owner}/{repo}")
        return PRComment.from_api_response(response)
    
    def delete_comment(
        self,
        owner: str,
        repo: str,
        comment_id: int,
    ) -> bool:
        """
        Delete a PR comment.
        
        Args:
            owner: Repository owner
            repo: Repository name
            comment_id: Comment ID
            
        Returns:
            True if deleted successfully
        """
        try:
            self.client._request(
                "DELETE",
                f"/repos/{owner}/{repo}/issues/comments/{comment_id}",
            )
            logger.info(f"Deleted comment {comment_id} in {owner}/{repo}")
            return True
        except GitHubNotFoundError:
            logger.warning(f"Comment {comment_id} not found in {owner}/{repo}")
            return False
    
    def dismiss_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_id: int,
        message: str,
        event: str = "DISMISS",
    ) -> Review:
        """
        Dismiss a review.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            review_id: Review ID to dismiss
            message: Dismissal message
            event: Dismiss event type
            
        Returns:
            Dismissed Review
        """
        response = self.client._request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
            json_data={
                "message": message,
                "event": event,
            },
        )
        
        logger.info(f"Dismissed review {review_id} on PR #{pr_number}")
        return Review.from_api_response(response)
    
    def get_combined_review_status(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict:
        """
        Get the combined review status for a PR.
        
        Args:
            owner: Repository owner
            repo: Repository name
            pr_number: PR number
            
        Returns:
            Dictionary with review status information
        """
        reviews = self.list_reviews(owner, repo, pr_number, per_page=100)
        
        # Count by state
        state_counts = {
            ReviewState.APPROVED: 0,
            ReviewState.CHANGES_REQUESTED: 0,
            ReviewState.COMMENTED: 0,
            ReviewState.DISMISSED: 0,
            ReviewState.PENDING: 0,
        }
        
        latest_by_user: Dict[str, Review] = {}
        
        for review in reviews:
            state_counts[review.state] += 1
            # Track latest review from each user
            if review.user_login not in latest_by_user:
                latest_by_user[review.user_login] = review
            elif review.submitted_at and latest_by_user[review.user_login].submitted_at:
                if review.submitted_at > latest_by_user[review.user_login].submitted_at:
                    latest_by_user[review.user_login] = review
        
        # Determine overall state based on latest reviews
        has_approval = any(
            r.state == ReviewState.APPROVED 
            for r in latest_by_user.values()
        )
        has_changes_requested = any(
            r.state == ReviewState.CHANGES_REQUESTED 
            for r in latest_by_user.values()
        )
        
        if has_changes_requested:
            overall_state = "changes_requested"
        elif has_approval:
            overall_state = "approved"
        else:
            overall_state = "pending"
        
        return {
            "state": overall_state,
            "total_reviews": len(reviews),
            "state_counts": {k.value: v for k, v in state_counts.items()},
            "latest_reviews": [
                {
                    "user": r.user_login,
                    "state": r.state.value,
                    "submitted_at": r.submitted_at,
                }
                for r in latest_by_user.values()
            ],
            "approval_count": state_counts[ReviewState.APPROVED],
            "changes_requested_count": state_counts[ReviewState.CHANGES_REQUESTED],
        }
