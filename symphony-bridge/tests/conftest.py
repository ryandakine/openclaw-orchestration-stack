"""
Pytest configuration and fixtures for Symphony PR Bridge tests.
"""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from github.client import GitHubClient, PullRequest, RateLimitInfo
from github.labels import LabelManager, Label
from review.reviewer import ReviewManager, Review, ReviewEvent
from review.summary import (
    ReviewFinding,
    ReviewSummary,
    FindingSeverity,
    FindingCategory,
)
from pr_lifecycle import PRLifecycleManager, PRState, MergeState
from webhook_handler import WebhookHandler


class MockResponse:
    """Mock requests response."""
    
    def __init__(
        self,
        json_data=None,
        status_code=200,
        headers=None,
        text="",
        content=None,
    ):
        self.json_data = json_data or {}
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text or json.dumps(json_data) if json_data else ""
        self.content = content or self.text.encode()
    
    def json(self):
        return self.json_data
    
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


@pytest.fixture
def mock_response():
    """Factory for mock responses."""
    def _make_response(**kwargs):
        return MockResponse(**kwargs)
    return _make_response


@pytest.fixture
def mock_github_client():
    """Create a mock GitHub client."""
    client = Mock(spec=GitHubClient)
    client.token = "test_token"
    client.base_url = "https://api.github.com"
    client._request = Mock()
    return client


@pytest.fixture
def github_client():
    """Create a real GitHub client with mocked session."""
    with patch("requests.Session") as mock_session_class:
        mock_session = Mock()
        mock_session_class.return_value = mock_session
        
        client = GitHubClient(token="test_token")
        # Replace the session with our mock
        client._session = mock_session
        client._rate_limit_info = None
        yield client


@pytest.fixture
def sample_pr_data():
    """Sample pull request data from GitHub API."""
    return {
        "number": 42,
        "title": "Test PR",
        "body": "Test description",
        "state": "open",
        "head": {
            "ref": "feature-branch",
            "sha": "abc123",
        },
        "base": {
            "ref": "main",
            "sha": "def456",
        },
        "user": {
            "login": "testuser",
        },
        "html_url": "https://github.com/owner/repo/pull/42",
        "draft": False,
        "merged": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "labels": [
            {"name": "openclaw"},
            {"name": "needs-review"},
        ],
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T12:00:00Z",
    }


@pytest.fixture
def sample_pr(sample_pr_data):
    """Sample PullRequest object."""
    return PullRequest.from_api_response(sample_pr_data)


@pytest.fixture
def sample_label_data():
    """Sample label data from GitHub API."""
    return {
        "id": 123,
        "name": "openclaw",
        "color": "0052CC",
        "description": "Managed by OpenClaw",
        "url": "https://api.github.com/repos/owner/repo/labels/openclaw",
        "default": False,
    }


@pytest.fixture
def sample_label(sample_label_data):
    """Sample Label object."""
    return Label.from_api_response(sample_label_data)


@pytest.fixture
def sample_review_data():
    """Sample review data from GitHub API."""
    return {
        "id": 12345,
        "node_id": "MDE3OlB1bGxSZXF1ZXN0UmV2aWV3MQ==",
        "user": {
            "login": "symphony-bot",
        },
        "body": "Review comment",
        "state": "APPROVED",
        "commit_id": "abc123",
        "html_url": "https://github.com/owner/repo/pull/42#pullrequestreview-12345",
        "submitted_at": "2024-01-01T12:00:00Z",
        "comments_count": 0,
    }


@pytest.fixture
def sample_finding():
    """Sample ReviewFinding."""
    return ReviewFinding(
        message="Test finding message",
        severity=FindingSeverity.MEDIUM,
        category=FindingCategory.BUG,
        file_path="src/test.py",
        line_number=42,
        suggestion="Fix this issue",
        rule_id="TEST-001",
    )


@pytest.fixture
def sample_review_summary(sample_finding):
    """Sample ReviewSummary."""
    return ReviewSummary(
        result="reject",
        summary="Test review summary",
        findings=[sample_finding],
        metadata={"test": True},
    )


@pytest.fixture
def sample_webhook_payload():
    """Sample webhook payload."""
    return {
        "action": "opened",
        "number": 42,
        "pull_request": {
            "number": 42,
            "title": "Test PR",
            "body": "Test description",
            "state": "open",
            "draft": False,
            "head": {
                "ref": "feature-branch",
                "sha": "abc123",
            },
            "base": {
                "ref": "main",
                "sha": "def456",
            },
            "user": {
                "login": "testuser",
            },
            "labels": [],
        },
        "repository": {
            "id": 123,
            "name": "repo",
            "full_name": "owner/repo",
            "owner": {
                "login": "owner",
            },
        },
        "sender": {
            "login": "testuser",
        },
    }
