"""
Unit tests for PR lifecycle manager.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pr_lifecycle import (
    PRLifecycleManager,
    PRStatus,
    PRState,
    MergeState,
)
from github.client import PullRequest
from review.summary import (
    ReviewSummary,
    ReviewFinding,
    FindingSeverity,
    FindingCategory,
)


class TestPRState:
    """Tests for PRState enum."""
    
    def test_state_values(self):
        """Test state values."""
        assert PRState.DRAFT.value == "draft"
        assert PRState.OPEN.value == "open"
        assert PRState.NEEDS_REVIEW.value == "needs_review"
        assert PRState.APPROVED.value == "approved"
        assert PRState.READY_TO_MERGE.value == "ready_to_merge"
        assert PRState.MERGED.value == "merged"
        assert PRState.CLOSED.value == "closed"
        assert PRState.BLOCKED.value == "blocked"


class TestMergeState:
    """Tests for MergeState enum."""
    
    def test_state_values(self):
        """Test merge state values."""
        assert MergeState.CLEAN.value == "clean"
        assert MergeState.BLOCKED.value == "blocked"
        assert MergeState.BEHIND.value == "behind"
        assert MergeState.DIRTY.value == "dirty"
        assert MergeState.DRAFT.value == "draft"
        assert MergeState.UNKNOWN.value == "unknown"


class TestPRStatus:
    """Tests for PRStatus dataclass."""
    
    def test_to_dict(self):
        """Test converting PRStatus to dict."""
        status = PRStatus(
            pr_number=42,
            state=PRState.OPEN,
            merge_state=MergeState.CLEAN,
            is_mergeable=True,
            checks_passing=True,
            required_reviews=1,
            current_approvals=1,
            labels=["openclaw", "approved"],
            linked_issues=["#123"],
            last_updated=datetime(2024, 1, 1, 12, 0, 0),
        )
        
        data = status.to_dict()
        
        assert data["pr_number"] == 42
        assert data["state"] == "open"
        assert data["merge_state"] == "clean"
        assert data["is_mergeable"] is True
        assert data["labels"] == ["openclaw", "approved"]


class TestPRLifecycleManager:
    """Tests for PRLifecycleManager."""
    
    def test_init(self, mock_github_client):
        """Test initialization."""
        manager = PRLifecycleManager(mock_github_client)
        
        assert manager.client == mock_github_client
        assert manager.label_manager is not None
        assert manager.review_manager is not None
    
    def test_create_pr(self, mock_github_client, sample_pr):
        """Test creating a PR."""
        mock_github_client.create_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        manager.label_manager = Mock()
        
        pr = manager.create_or_update_pr(
            owner="owner",
            repo="repo",
            title="New PR",
            head="feature",
            base="main",
            body="Description",
        )
        
        assert pr.number == 42
        manager.label_manager.add_label.assert_called_once()
    
    def test_update_existing_pr(self, mock_github_client, sample_pr):
        """Test updating an existing PR."""
        mock_github_client.update_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        manager.label_manager = Mock()
        
        pr = manager.create_or_update_pr(
            owner="owner",
            repo="repo",
            title="Updated PR",
            head="feature",
            base="main",
            pr_number=42,
        )
        
        assert pr.number == 42
        mock_github_client.update_pr.assert_called_once()
    
    def test_create_pr_with_issue_links(self, mock_github_client, sample_pr):
        """Test creating PR with linked issues."""
        mock_github_client.create_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        manager.label_manager = Mock()
        
        pr = manager.create_or_update_pr(
            owner="owner",
            repo="repo",
            title="PR with issues",
            head="feature",
            base="main",
            link_issues=["123", "#456"],
        )
        
        # Verify create_pr was called with issue links in body
        call_args = mock_github_client.create_pr.call_args
        assert call_args is not None
        body = call_args.kwargs.get("body", "")
        assert "Closes #123" in body
        assert "Closes #456" in body
    
    def test_check_merge_state(self, mock_github_client, sample_pr):
        """Test checking merge state."""
        mock_github_client.get_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        manager.review_manager = Mock()
        manager.review_manager.get_combined_review_status.return_value = {
            "state": "approved",
            "approval_count": 1,
            "changes_requested_count": 0,
        }
        
        # Mock the _get_combined_status method
        manager._get_combined_status = Mock(return_value={
            "state": "success",
            "total_count": 3,
            "statuses": [],
        })
        
        merge_state, details = manager.check_merge_state("owner", "repo", 42)
        
        assert merge_state == MergeState.CLEAN
    
    def test_link_to_issue(self, mock_github_client, sample_pr):
        """Test linking PR to issue."""
        mock_github_client.get_pr.return_value = sample_pr
        
        # Create updated PR with issue link
        updated_pr = Mock()
        updated_pr.number = 42
        updated_pr.body = "Description\n\n### Linked Issues\n\n- Closes #123"
        mock_github_client.update_pr.return_value = updated_pr
        
        manager = PRLifecycleManager(mock_github_client)
        pr = manager.link_to_issue("owner", "repo", 42, "123")
        
        assert "Closes #123" in pr.body
    
    def test_post_status_update(self, mock_github_client):
        """Test posting status update."""
        manager = PRLifecycleManager(mock_github_client)
        manager.review_manager = Mock()
        
        # The post_comment method is called with formatted body
        manager.review_manager.post_comment.return_value = Mock()
        
        comment = manager.post_status_update(
            "owner",
            42,
            "repo",
            "Test status",
            {"key": "value"},
        )
        
        # Verify the method was called
        manager.review_manager.post_comment.assert_called_once()
        # Check that the body contains expected content
        call_args = manager.review_manager.post_comment.call_args
        # call_args is a tuple (args, kwargs), args is (owner, repo, pr_number, body)
        args, kwargs = call_args
        # body is passed as keyword argument 'body' or 4th positional arg
        body = kwargs.get('body', args[3] if len(args) > 3 else "")
        assert "Test status" in body
    
    def test_get_pr_status(self, mock_github_client, sample_pr):
        """Test getting PR status."""
        # Create a sample PR with approved label
        sample_pr.labels = ["openclaw", "approved"]
        sample_pr.body = "Closes #123"
        mock_github_client.get_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        
        # Mock check_merge_state
        manager.check_merge_state = Mock(return_value=(
            MergeState.CLEAN,
            {"mergeable": True, "checks_state": "success", "approval_count": 1},
        ))
        
        status = manager.get_pr_status("owner", "repo", 42)
        
        assert status.pr_number == 42
        assert "openclaw" in status.labels
        assert "#123" in status.linked_issues
        assert "#123" in status.linked_issues
    
    def test_transition_pr_state_to_needs_review(self, mock_github_client, sample_pr):
        """Test transitioning PR to needs review."""
        sample_pr.labels = ["approved"]
        mock_github_client.get_pr.return_value = sample_pr
        
        manager = PRLifecycleManager(mock_github_client)
        manager.label_manager = Mock()
        manager.label_manager.add_label.return_value = ["needs-review", "openclaw"]
        manager.label_manager.remove_label.return_value = ["openclaw"]
        manager.review_manager = Mock()
        manager.review_manager.post_comment.return_value = Mock(body="Status update")
        
        # Mock get_pr_status to avoid complex mocking
        manager.get_pr_status = Mock(return_value=Mock(
            pr_number=42,
            state=PRState.NEEDS_REVIEW,
            labels=["needs-review", "openclaw"],
        ))
        
        status = manager.transition_pr_state("owner", "repo", 42, PRState.NEEDS_REVIEW)
        
        assert status.state == PRState.NEEDS_REVIEW
        # Verify post_status_update was called which uses review_manager.post_comment
        manager.review_manager.post_comment.assert_called_once()
    
    def test_submit_review_from_summary_approve(self, mock_github_client):
        """Test submitting approve review from summary."""
        manager = PRLifecycleManager(mock_github_client)
        manager.review_manager = Mock()
        
        # Return a dict-like object that supports both dict access and attribute access
        class ReviewDict:
            def __init__(self):
                self.state = "APPROVED"
            def __getitem__(self, key):
                return {"state": "APPROVED"}[key]
            def to_dict(self):
                return {"state": "APPROVED"}
        
        manager.review_manager.post_review.return_value = ReviewDict()
        
        manager.label_manager = Mock()
        manager.label_manager.add_label.return_value = []
        manager.label_manager.remove_label.return_value = []
        
        summary = ReviewSummary(
            result="approve",
            summary="LGTM",
            findings=[],
        )
        
        review = manager.submit_review_from_summary(
            "owner",
            "repo",
            42,
            summary,
        )
        
        # Review should be a dict with state (or dict-like)
        assert review["state"] == "APPROVED"
        manager.review_manager.post_review.assert_called_once()
    
    def test_find_existing_symphony_pr(self, mock_github_client, sample_pr):
        """Test finding existing Symphony PR."""
        sample_pr.labels = ["openclaw"]
        mock_github_client.list_prs.return_value = [sample_pr]
        
        manager = PRLifecycleManager(mock_github_client)
        pr = manager.find_existing_symphony_pr("owner", "repo", "feature")
        
        assert pr is not None
        assert pr.number == 42
    
    def test_find_existing_symphony_pr_not_found(self, mock_github_client):
        """Test finding existing Symphony PR when none exists."""
        mock_github_client.list_prs.return_value = []
        
        manager = PRLifecycleManager(mock_github_client)
        pr = manager.find_existing_symphony_pr("owner", "repo", "feature")
        
        assert pr is None
    
    def test_close_pr(self, mock_github_client):
        """Test closing a PR."""
        manager = PRLifecycleManager(mock_github_client)
        manager.review_manager = Mock()
        manager.review_manager.post_comment.return_value = Mock(body="Closing comment")
        
        closed_pr = Mock()
        closed_pr.state = "closed"
        mock_github_client.update_pr.return_value = closed_pr
        
        pr = manager.close_pr("owner", "repo", 42, "Closing this PR")
        
        assert pr.state == "closed"
        manager.review_manager.post_comment.assert_called_once()
        mock_github_client.update_pr.assert_called_once()
    
    def test_extract_linked_issues(self, mock_github_client):
        """Test extracting linked issues from PR body."""
        manager = PRLifecycleManager(mock_github_client)
        
        body = """
This PR fixes some issues.

Closes #123
Fixes #456
Relates to #789
Links to #999
        """
        
        issues = manager._extract_linked_issues(body)
        
        assert "#123" in issues
        assert "#456" in issues
        assert "#789" in issues
        assert "#999" in issues
