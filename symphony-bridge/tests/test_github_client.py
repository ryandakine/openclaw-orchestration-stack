"""
Unit tests for GitHub API client.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from github.client import (
    GitHubClient,
    GitHubError,
    GitHubRateLimitError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubValidationError,
    PullRequest,
    RateLimitInfo,
)


class TestGitHubError:
    """Tests for GitHub error classes."""
    
    def test_github_error_creation(self):
        """Test creating GitHubError."""
        error = GitHubError("Test error", 404, {"message": "Not found"})
        assert str(error) == "Test error"
        assert error.status_code == 404
        assert error.response_body == {"message": "Not found"}
    
    def test_github_error_without_body(self):
        """Test creating GitHubError without response body."""
        error = GitHubError("Test error")
        assert error.status_code is None
        assert error.response_body == {}


class TestRateLimitInfo:
    """Tests for RateLimitInfo dataclass."""
    
    def test_rate_limit_info_creation(self):
        """Test creating RateLimitInfo."""
        now = int(datetime.now().timestamp())
        info = RateLimitInfo(
            limit=5000,
            remaining=4000,
            reset_timestamp=now + 3600,
            used=1000,
        )
        assert info.limit == 5000
        assert info.remaining == 4000
        assert info.used == 1000
        assert not info.is_exhausted
    
    def test_rate_limit_exhausted(self):
        """Test exhausted rate limit."""
        info = RateLimitInfo(
            limit=5000,
            remaining=0,
            reset_timestamp=int(datetime.now().timestamp()) + 3600,
            used=5000,
        )
        assert info.is_exhausted
        assert info.seconds_until_reset > 0


class TestPullRequest:
    """Tests for PullRequest dataclass."""
    
    def test_from_api_response(self, sample_pr_data):
        """Test creating PullRequest from API response."""
        pr = PullRequest.from_api_response(sample_pr_data)
        
        assert pr.number == 42
        assert pr.title == "Test PR"
        assert pr.body == "Test description"
        assert pr.state == "open"
        assert pr.head_ref == "feature-branch"
        assert pr.base_ref == "main"
        assert pr.head_sha == "abc123"
        assert pr.base_sha == "def456"
        assert pr.user_login == "testuser"
        assert pr.html_url == "https://github.com/owner/repo/pull/42"
        assert not pr.draft
        assert not pr.merged
        assert pr.mergeable is True
        assert pr.mergeable_state == "clean"
        assert "openclaw" in pr.labels
        assert "needs-review" in pr.labels
    
    def test_from_api_response_minimal(self):
        """Test creating PullRequest with minimal data."""
        data = {
            "number": 1,
            "title": "Minimal PR",
            "state": "open",
            "head": {"ref": "branch", "sha": "abc"},
            "base": {"ref": "main", "sha": "def"},
            "user": {"login": "user"},
            "html_url": "https://example.com",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        pr = PullRequest.from_api_response(data)
        assert pr.number == 1
        assert pr.body is None
        assert not pr.draft


class TestGitHubClientInit:
    """Tests for GitHubClient initialization."""
    
    def test_init_with_token(self):
        """Test initialization with explicit token."""
        client = GitHubClient(token="test_token")
        assert client.token == "test_token"
        assert client.app_id is None
    
    def test_init_with_env_token(self, monkeypatch):
        """Test initialization with environment token."""
        monkeypatch.setenv("GITHUB_TOKEN", "env_token")
        client = GitHubClient()
        assert client.token == "env_token"
    
    def test_init_with_app_credentials(self):
        """Test initialization with app credentials."""
        client = GitHubClient(
            app_id="123",
            private_key="-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----",
            installation_id=456,
        )
        assert client.app_id == "123"
        assert client.installation_id == 456
        assert client.token is None
    
    def test_init_without_credentials_raises(self):
        """Test that initialization fails without credentials."""
        with pytest.raises(GitHubAuthError):
            GitHubClient(token=None, app_id=None, private_key=None)


class TestGitHubClientRequest:
    """Tests for GitHubClient request methods."""
    
    def test_handle_error_404(self, github_client):
        """Test handling 404 error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_response.text = '{"message": "Not Found"}'
        
        with pytest.raises(GitHubNotFoundError):
            github_client._handle_error(mock_response)
    
    def test_handle_error_401(self, github_client):
        """Test handling 401 error."""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Bad credentials"}
        mock_response.text = '{"message": "Bad credentials"}'
        
        with pytest.raises(GitHubAuthError):
            github_client._handle_error(mock_response)
    
    def test_handle_error_rate_limit(self, github_client):
        """Test handling rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "API rate limit exceeded"}
        mock_response.text = '{"message": "API rate limit exceeded"}'
        
        with pytest.raises(GitHubRateLimitError):
            github_client._handle_error(mock_response)
    
    def test_update_rate_limit(self, github_client):
        """Test updating rate limit from headers."""
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4000",
            "X-RateLimit-Reset": "1234567890",
            "X-RateLimit-Used": "1000",
        }
        github_client._update_rate_limit(headers)
        
        assert github_client._rate_limit_info is not None
        assert github_client._rate_limit_info.limit == 5000
        assert github_client._rate_limit_info.remaining == 4000
    
    def test_create_pr(self, github_client):
        """Test creating a pull request."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "number": 42,
            "title": "New PR",
            "state": "open",
            "head": {"ref": "feature", "sha": "abc"},
            "base": {"ref": "main", "sha": "def"},
            "user": {"login": "user"},
            "html_url": "https://github.com/owner/repo/pull/42",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        mock_response.headers = {}
        github_client._session.request.return_value = mock_response
        
        pr = github_client.create_pr(
            owner="owner",
            repo="repo",
            title="New PR",
            head="feature",
            base="main",
            body="Description",
        )
        
        assert pr.number == 42
        assert pr.title == "New PR"
        github_client._session.request.assert_called_once()
    
    def test_update_pr(self, github_client):
        """Test updating a pull request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "number": 42,
            "title": "Updated PR",
            "state": "open",
            "head": {"ref": "feature", "sha": "abc"},
            "base": {"ref": "main", "sha": "def"},
            "user": {"login": "user"},
            "html_url": "https://github.com/owner/repo/pull/42",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
        }
        mock_response.headers = {}
        github_client._session.request.return_value = mock_response
        
        pr = github_client.update_pr(
            owner="owner",
            repo="repo",
            pr_number=42,
            title="Updated PR",
        )
        
        assert pr.title == "Updated PR"
        github_client._session.request.assert_called_once()
    
    def test_get_pr(self, github_client):
        """Test getting a pull request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "number": 42,
            "title": "Test PR",
            "state": "open",
            "head": {"ref": "feature", "sha": "abc"},
            "base": {"ref": "main", "sha": "def"},
            "user": {"login": "user"},
            "html_url": "https://github.com/owner/repo/pull/42",
            "labels": [],
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }
        mock_response.headers = {}
        github_client._session.request.return_value = mock_response
        
        pr = github_client.get_pr("owner", "repo", 42)
        
        assert pr.number == 42
        github_client._session.request.assert_called_once()
    
    def test_list_prs(self, github_client):
        """Test listing pull requests."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "number": 1,
                "title": "PR 1",
                "state": "open",
                "head": {"ref": "branch1", "sha": "abc"},
                "base": {"ref": "main", "sha": "def"},
                "user": {"login": "user"},
                "html_url": "https://github.com/owner/repo/pull/1",
                "labels": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
            {
                "number": 2,
                "title": "PR 2",
                "state": "open",
                "head": {"ref": "branch2", "sha": "ghi"},
                "base": {"ref": "main", "sha": "def"},
                "user": {"login": "user"},
                "html_url": "https://github.com/owner/repo/pull/2",
                "labels": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        ]
        mock_response.headers = {}
        github_client._session.request.return_value = mock_response
        
        prs = github_client.list_prs("owner", "repo")
        
        assert len(prs) == 2
        assert prs[0].number == 1
        assert prs[1].number == 2
    
    def test_context_manager(self):
        """Test using client as context manager."""
        with GitHubClient(token="test") as client:
            assert client.token == "test"


class TestGitHubClientEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_response(self, github_client):
        """Test handling empty response body."""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_response.content = b""
        mock_response.headers = {}
        github_client._session.request.return_value = mock_response
        
        result = github_client._request("DELETE", "/test")
        assert result == {}
    
    def test_private_key_from_file(self, tmp_path, monkeypatch):
        """Test loading private key from file."""
        key_file = tmp_path / "key.pem"
        key_file.write_text("-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----")
        
        monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(key_file))
        
        client = GitHubClient.__new__(GitHubClient)
        client.token = None
        client.app_id = None
        key = client._load_private_key_from_env()
        
        assert key is not None
        assert "RSA PRIVATE KEY" in key
