"""
Unit tests for review management.
"""

import pytest
from unittest.mock import Mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from review.reviewer import (
    ReviewManager,
    Review,
    ReviewEvent,
    ReviewState,
    ReviewComment,
    PRComment,
)


class TestReviewEvent:
    """Tests for ReviewEvent enum."""
    
    def test_event_values(self):
        """Test event values."""
        assert ReviewEvent.APPROVE.value == "APPROVE"
        assert ReviewEvent.REQUEST_CHANGES.value == "REQUEST_CHANGES"
        assert ReviewEvent.COMMENT.value == "COMMENT"


class TestReviewState:
    """Tests for ReviewState enum."""
    
    def test_state_values(self):
        """Test state values."""
        assert ReviewState.APPROVED.value == "APPROVED"
        assert ReviewState.CHANGES_REQUESTED.value == "CHANGES_REQUESTED"
        assert ReviewState.COMMENTED.value == "COMMENTED"
        assert ReviewState.DISMISSED.value == "DISMISSED"
        assert ReviewState.PENDING.value == "PENDING"


class TestReviewComment:
    """Tests for ReviewComment dataclass."""
    
    def test_to_dict_basic(self):
        """Test converting basic comment to dict."""
        comment = ReviewComment(
            path="src/test.py",
            body="Test comment",
            line=42,
        )
        
        data = comment.to_dict()
        
        assert data["path"] == "src/test.py"
        assert data["body"] == "Test comment"
        assert data["line"] == 42
        assert data["side"] == "RIGHT"
    
    def test_to_dict_with_all_fields(self):
        """Test converting comment with all fields to dict."""
        comment = ReviewComment(
            path="src/test.py",
            body="Test comment",
            line=42,
            side="LEFT",
            start_line=40,
            start_side="LEFT",
            commit_id="abc123",
        )
        
        data = comment.to_dict()
        
        assert data["side"] == "LEFT"
        assert data["start_line"] == 40
        assert data["start_side"] == "LEFT"
        assert data["commit_id"] == "abc123"


class TestReview:
    """Tests for Review dataclass."""
    
    def test_from_api_response(self, sample_review_data):
        """Test creating Review from API response."""
        review = Review.from_api_response(sample_review_data)
        
        assert review.id == 12345
        assert review.node_id == "MDE3OlB1bGxSZXF1ZXN0UmV2aWV3MQ=="
        assert review.user_login == "symphony-bot"
        assert review.body == "Review comment"
        assert review.state == ReviewState.APPROVED
        assert review.commit_id == "abc123"
        assert review.html_url == "https://github.com/owner/repo/pull/42#pullrequestreview-12345"
        assert review.submitted_at == "2024-01-01T12:00:00Z"
    
    def test_from_api_response_pending(self):
        """Test creating Review with pending state."""
        data = {
            "id": 1,
            "node_id": "test",
            "user": {"login": "user"},
            "body": None,
            "state": "PENDING",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        review = Review.from_api_response(data)
        
        assert review.state == ReviewState.PENDING
        assert review.body is None


class TestPRComment:
    """Tests for PRComment dataclass."""
    
    def test_from_api_response(self):
        """Test creating PRComment from API response."""
        data = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "user"},
            "body": "Test comment",
            "html_url": "https://example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "issue_url": "https://api.github.com/issues/1",
        }
        
        comment = PRComment.from_api_response(data)
        
        assert comment.id == 123
        assert comment.user_login == "user"
        assert comment.body == "Test comment"
        assert comment.issue_url == "https://api.github.com/issues/1"


class TestReviewManager:
    """Tests for ReviewManager."""
    
    def test_post_review(self, mock_github_client):
        """Test posting a review."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "symphony"},
            "body": "Review body",
            "state": "COMMENTED",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        
        manager = ReviewManager(mock_github_client)
        review = manager.post_review(
            owner="owner",
            repo="repo",
            pr_number=42,
            body="Review body",
            event=ReviewEvent.COMMENT,
        )
        
        assert review.body == "Review body"
        assert review.state == ReviewState.COMMENTED
        mock_github_client._request.assert_called_once()
    
    def test_post_review_with_comments(self, mock_github_client):
        """Test posting a review with line comments."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "symphony"},
            "body": "Review",
            "state": "CHANGES_REQUESTED",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        
        comments = [
            ReviewComment(path="file.py", body="Issue here", line=10),
            ReviewComment(path="file.py", body="Another issue", line=20),
        ]
        
        manager = ReviewManager(mock_github_client)
        review = manager.post_review(
            owner="owner",
            repo="repo",
            pr_number=42,
            body="Please fix these issues",
            event=ReviewEvent.REQUEST_CHANGES,
            comments=comments,
        )
        
        call_args = mock_github_client._request.call_args
        # call_args is a tuple of (args, kwargs)
        kwargs = call_args[1] if len(call_args) > 1 else call_args.kwargs
        assert kwargs["json_data"]["event"] == "REQUEST_CHANGES"
        assert len(kwargs["json_data"]["comments"]) == 2
    
    def test_approve_pr(self, mock_github_client):
        """Test approving a PR."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "symphony"},
            "body": "Approved by Symphony automated review.",
            "state": "APPROVED",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        
        manager = ReviewManager(mock_github_client)
        review = manager.approve_pr("owner", "repo", 42)
        
        assert review.state == ReviewState.APPROVED
        call_args = mock_github_client._request.call_args
        assert call_args[1]["json_data"]["event"] == "APPROVE"
    
    def test_request_changes(self, mock_github_client):
        """Test requesting changes."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "symphony"},
            "body": "Please fix",
            "state": "CHANGES_REQUESTED",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        
        manager = ReviewManager(mock_github_client)
        review = manager.request_changes(
            "owner",
            "repo",
            42,
            "Please address these issues",
        )
        
        assert review.state == ReviewState.CHANGES_REQUESTED
        call_args = mock_github_client._request.call_args
        assert call_args[1]["json_data"]["event"] == "REQUEST_CHANGES"
    
    def test_post_comment(self, mock_github_client):
        """Test posting a general comment."""
        mock_github_client._request.return_value = {
            "id": 456,
            "node_id": "test",
            "user": {"login": "symphony"},
            "body": "General comment",
            "html_url": "https://example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        
        manager = ReviewManager(mock_github_client)
        comment = manager.post_comment("owner", "repo", 42, "General comment")
        
        assert comment.body == "General comment"
        mock_github_client._request.assert_called_once()
    
    def test_post_review_comment(self, mock_github_client):
        """Test posting a single review comment."""
        mock_github_client._request.return_value = {
            "id": 789,
            "path": "file.py",
            "line": 42,
            "body": "Issue here",
        }
        
        manager = ReviewManager(mock_github_client)
        comment = ReviewComment(
            path="file.py",
            body="Issue here",
            line=42,
        )
        result = manager.post_review_comment("owner", "repo", 42, comment)
        
        assert result["path"] == "file.py"
        assert result["line"] == 42
    
    def test_list_reviews(self, mock_github_client):
        """Test listing reviews."""
        mock_github_client._request.return_value = [
            {
                "id": 1,
                "node_id": "test",
                "user": {"login": "user1"},
                "body": "LGTM",
                "state": "APPROVED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "node_id": "test",
                "user": {"login": "user2"},
                "body": "Please fix",
                "state": "CHANGES_REQUESTED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T01:00:00Z",
            },
        ]
        
        manager = ReviewManager(mock_github_client)
        reviews = manager.list_reviews("owner", "repo", 42)
        
        assert len(reviews) == 2
        assert reviews[0].state == ReviewState.APPROVED
        assert reviews[1].state == ReviewState.CHANGES_REQUESTED
    
    def test_get_review(self, mock_github_client):
        """Test getting a specific review."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "user"},
            "body": "Review",
            "state": "COMMENTED",
            "commit_id": "abc",
            "html_url": "https://example.com",
        }
        
        manager = ReviewManager(mock_github_client)
        review = manager.get_review("owner", "repo", 42, 123)
        
        assert review.id == 123
    
    def test_list_review_comments(self, mock_github_client):
        """Test listing comments for a review."""
        mock_github_client._request.return_value = [
            {"id": 1, "body": "Comment 1", "path": "file.py", "line": 10},
            {"id": 2, "body": "Comment 2", "path": "file.py", "line": 20},
        ]
        
        manager = ReviewManager(mock_github_client)
        comments = manager.list_review_comments("owner", "repo", 42, 123)
        
        assert len(comments) == 2
    
    def test_list_pr_comments(self, mock_github_client):
        """Test listing PR comments."""
        mock_github_client._request.return_value = [
            {
                "id": 1,
                "node_id": "test",
                "user": {"login": "user"},
                "body": "Comment 1",
                "html_url": "https://example.com",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        ]
        
        manager = ReviewManager(mock_github_client)
        comments = manager.list_pr_comments("owner", "repo", 42)
        
        assert len(comments) == 1
        assert comments[0].body == "Comment 1"
    
    def test_update_comment(self, mock_github_client):
        """Test updating a comment."""
        mock_github_client._request.return_value = {
            "id": 123,
            "node_id": "test",
            "user": {"login": "user"},
            "body": "Updated comment",
            "html_url": "https://example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
        }
        
        manager = ReviewManager(mock_github_client)
        comment = manager.update_comment("owner", "repo", 123, "Updated comment")
        
        assert comment.body == "Updated comment"
    
    def test_delete_comment_success(self, mock_github_client):
        """Test deleting a comment successfully."""
        mock_github_client._request.return_value = {}
        
        manager = ReviewManager(mock_github_client)
        result = manager.delete_comment("owner", "repo", 123)
        
        assert result is True
    
    def test_get_combined_review_status(self, mock_github_client):
        """Test getting combined review status."""
        mock_github_client._request.return_value = [
            {
                "id": 1,
                "node_id": "test",
                "user": {"login": "user1"},
                "body": "LGTM",
                "state": "APPROVED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "node_id": "test",
                "user": {"login": "user2"},
                "body": "LGTM",
                "state": "APPROVED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T01:00:00Z",
            },
        ]
        
        manager = ReviewManager(mock_github_client)
        status = manager.get_combined_review_status("owner", "repo", 42)
        
        assert status["state"] == "approved"
        assert status["total_reviews"] == 2
        assert status["approval_count"] == 2
    
    def test_get_combined_review_status_with_changes(self, mock_github_client):
        """Test review status with changes requested."""
        mock_github_client._request.return_value = [
            {
                "id": 1,
                "node_id": "test",
                "user": {"login": "user1"},
                "body": "LGTM",
                "state": "APPROVED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T00:00:00Z",
            },
            {
                "id": 2,
                "node_id": "test",
                "user": {"login": "user2"},
                "body": "Please fix",
                "state": "CHANGES_REQUESTED",
                "commit_id": "abc",
                "html_url": "https://example.com",
                "submitted_at": "2024-01-01T01:00:00Z",
            },
        ]
        
        manager = ReviewManager(mock_github_client)
        status = manager.get_combined_review_status("owner", "repo", 42)
        
        # Latest review from user2 is CHANGES_REQUESTED
        assert status["state"] == "changes_requested"
        assert status["changes_requested_count"] == 1
