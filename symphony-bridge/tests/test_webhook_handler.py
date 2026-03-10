"""
Unit tests for webhook handler.
"""

import json
import hmac
import hashlib
import pytest
from unittest.mock import Mock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from webhook_handler import (
    WebhookHandler,
    WebhookPayload,
    PREvent,
    ReviewEvent,
    WebhookEventType,
    PREventAction,
    ReviewEventAction,
    create_webhook_handler,
)


class TestWebhookEventType:
    """Tests for WebhookEventType enum."""
    
    def test_event_values(self):
        """Test event type values."""
        assert WebhookEventType.PULL_REQUEST.value == "pull_request"
        assert WebhookEventType.PULL_REQUEST_REVIEW.value == "pull_request_review"
        assert WebhookEventType.ISSUE_COMMENT.value == "issue_comment"
        assert WebhookEventType.PUSH.value == "push"


class TestPREventAction:
    """Tests for PREventAction enum."""
    
    def test_action_values(self):
        """Test PR action values."""
        assert PREventAction.OPENED.value == "opened"
        assert PREventAction.CLOSED.value == "closed"
        assert PREventAction.SYNCHRONIZE.value == "synchronize"
        assert PREventAction.READY_FOR_REVIEW.value == "ready_for_review"


class TestReviewEventAction:
    """Tests for ReviewEventAction enum."""
    
    def test_action_values(self):
        """Test review action values."""
        assert ReviewEventAction.SUBMITTED.value == "submitted"
        assert ReviewEventAction.EDITED.value == "edited"
        assert ReviewEventAction.DISMISSED.value == "dismissed"


class TestWebhookPayload:
    """Tests for WebhookPayload dataclass."""
    
    def test_properties(self):
        """Test payload properties."""
        payload = WebhookPayload(
            event_type=WebhookEventType.PULL_REQUEST,
            action="opened",
            repository={
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
            },
            sender={"login": "user"},
            raw_data={},
        )
        
        assert payload.owner == "owner"
        assert payload.repo == "repo"
        assert payload.full_name == "owner/repo"


class TestPREvent:
    """Tests for PREvent dataclass."""
    
    def test_from_payload(self, sample_webhook_payload):
        """Test creating PREvent from payload."""
        event = PREvent.from_payload(sample_webhook_payload)
        
        assert event.action == PREventAction.OPENED
        assert event.pr_number == 42
        assert event.pr_title == "Test PR"
        assert event.pr_state == "open"
        assert not event.pr_draft
        assert event.head_ref == "feature-branch"
        assert event.base_ref == "main"
        assert event.user_login == "testuser"


class TestReviewEvent:
    """Tests for ReviewEvent dataclass."""
    
    def test_from_payload(self):
        """Test creating ReviewEvent from payload."""
        payload = {
            "action": "submitted",
            "pull_request": {
                "number": 42,
            },
            "review": {
                "id": 123,
                "state": "approved",
                "body": "LGTM",
                "user": {"login": "reviewer"},
            },
        }
        
        event = ReviewEvent.from_payload(payload)
        
        assert event.action == ReviewEventAction.SUBMITTED
        assert event.pr_number == 42
        assert event.review_id == 123
        assert event.review_state == "approved"
        assert event.reviewer_login == "reviewer"


class TestWebhookHandler:
    """Tests for WebhookHandler."""
    
    def test_init_with_secret(self):
        """Test initialization with secret."""
        handler = WebhookHandler(secret="my_secret")
        
        assert handler.secret == "my_secret"
        assert handler.client is None
    
    def test_validate_signature_valid(self):
        """Test validating valid signature."""
        secret = "test_secret"
        payload = b'{"action": "opened"}'
        
        # Generate valid signature
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected}"
        
        handler = WebhookHandler(secret=secret)
        result = handler.validate_signature(payload, signature)
        
        assert result is True
    
    def test_validate_signature_invalid(self):
        """Test validating invalid signature."""
        handler = WebhookHandler(secret="test_secret")
        result = handler.validate_signature(b'{"test": true}', "sha256=invalid")
        
        assert result is False
    
    def test_validate_signature_no_secret(self):
        """Test validation when no secret configured."""
        handler = WebhookHandler(secret=None)
        result = handler.validate_signature(b'{"test": true}', "any_signature")
        
        assert result is True  # Skips validation
    
    def test_parse_payload(self):
        """Test parsing webhook payload."""
        payload_data = {
            "action": "opened",
            "repository": {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
            },
            "sender": {"login": "user"},
        }
        
        handler = WebhookHandler()
        payload = handler.parse_payload(
            json.dumps(payload_data).encode(),
            "pull_request",
        )
        
        assert payload.event_type == WebhookEventType.PULL_REQUEST
        assert payload.action == "opened"
        assert payload.owner == "owner"
    
    def test_handle_pr_opened(self, mock_github_client):
        """Test handling PR opened event."""
        handler = WebhookHandler(client=mock_github_client)
        handler.label_manager = Mock()
        handler.label_manager.add_label.return_value = ["openclaw"]
        handler.review_manager = Mock()
        handler.review_manager.post_comment.return_value = Mock(body="Welcome")
        
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=dummy",
        }
        
        payload = json.dumps({
            "action": "opened",
            "number": 42,
            "pull_request": {
                "number": 42,
                "title": "Test PR",
                "body": "Description",
                "state": "open",
                "draft": False,
                "head": {"ref": "feature", "sha": "abc"},
                "base": {"ref": "main", "sha": "def"},
                "user": {"login": "user"},
                "labels": [],
            },
            "repository": {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
            },
            "sender": {"login": "user"},
        }).encode()
        
        # Mock signature validation
        handler.validate_signature = Mock(return_value=True)
        
        result = handler.handle_webhook(payload, headers)
        
        assert result["status"] == "success"
        assert result["action"] == "opened"
    
    def test_handle_pr_synchronize(self, mock_github_client):
        """Test handling PR synchronize event."""
        handler = WebhookHandler(client=mock_github_client)
        handler.label_manager = Mock()
        handler.label_manager.remove_label.return_value = ["openclaw"]
        handler.label_manager.add_label.return_value = ["needs-review", "openclaw"]
        
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=dummy",
        }
        
        # Labels should be objects with name property in real webhook
        payload = json.dumps({
            "action": "synchronize",
            "number": 42,
            "pull_request": {
                "number": 42,
                "title": "Test PR",
                "state": "open",
                "draft": False,
                "head": {"ref": "feature", "sha": "abc"},
                "base": {"ref": "main", "sha": "def"},
                "user": {"login": "user"},
                "labels": [{"name": "approved"}, {"name": "openclaw"}],  # Proper format
            },
            "repository": {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
            },
            "sender": {"login": "user"},
        }).encode()
        
        handler.validate_signature = Mock(return_value=True)
        
        result = handler.handle_webhook(payload, headers)
        
        assert result["status"] == "success"
        assert result["action"] == "synchronize"
    
    def test_handle_review_submitted_approved(self, mock_github_client):
        """Test handling review submitted with approval."""
        mock_github_client._request.side_effect = [
            [{"name": "approved"}],  # add_label response
            [{"name": "openclaw"}],  # remove_label response
        ]
        
        handler = WebhookHandler(client=mock_github_client)
        
        headers = {
            "X-GitHub-Event": "pull_request_review",
            "X-Hub-Signature-256": "sha256=dummy",
        }
        
        payload = json.dumps({
            "action": "submitted",
            "pull_request": {
                "number": 42,
            },
            "review": {
                "id": 123,
                "state": "approved",
                "body": "LGTM",
                "user": {"login": "reviewer"},
            },
            "repository": {
                "name": "repo",
                "full_name": "owner/repo",
                "owner": {"login": "owner"},
            },
            "sender": {"login": "reviewer"},
        }).encode()
        
        handler.validate_signature = Mock(return_value=True)
        
        result = handler.handle_webhook(payload, headers)
        
        assert result["status"] == "success"
        assert result["review_state"] == "approved"
    
    def test_handle_invalid_signature(self):
        """Test handling webhook with invalid signature."""
        handler = WebhookHandler(secret="test_secret")
        
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=invalid",
        }
        
        result = handler.handle_webhook(b'{"test": true}', headers)
        
        assert result["status"] == "error"
        assert result["message"] == "Invalid signature"
    
    def test_handle_unknown_event(self):
        """Test handling unknown event type."""
        handler = WebhookHandler(secret="test")  # Set secret to enable validation
        handler.validate_signature = Mock(return_value=True)
        
        headers = {
            "X-GitHub-Event": "unknown_event",
            "X-Hub-Signature-256": "sha256=dummy",
        }
        
        payload = json.dumps({
            "action": "test",
            "repository": {"name": "repo", "owner": {"login": "owner"}},
            "sender": {"login": "user"},
        }).encode()
        
        # The handler now returns error for invalid event types instead of ignored
        # because parse_payload validates the event type
        result = handler.handle_webhook(payload, headers)
        
        # With the current implementation, unknown events raise ValueError
        assert result["status"] == "error"
    
    def test_register_handler(self):
        """Test registering custom handler."""
        handler = WebhookHandler()
        custom_handler = Mock(return_value={"status": "custom"})
        
        handler.register_handler("pull_request", custom_handler)
        
        assert "pull_request" in handler.event_handlers
        
        # Test calling
        handler.validate_signature = Mock(return_value=True)
        headers = {
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=dummy",
        }
        payload = json.dumps({
            "action": "opened",
            "pull_request": {"number": 42, "state": "open", "draft": False, "head": {"ref": "f"}, "base": {"ref": "m"}, "user": {"login": "u"}, "labels": []},
            "repository": {"name": "r", "owner": {"login": "o"}},
            "sender": {"login": "u"},
        }).encode()
        
        result = handler.handle_webhook(payload, headers)
        
        assert result["status"] == "custom"
    
    def test_verify_webhook_valid(self):
        """Test verifying valid webhook."""
        secret = "test_secret"
        payload = b'{"test": true}'
        
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected}"
        
        handler = WebhookHandler(secret=secret)
        result = handler.verify_webhook(payload, signature, "pull_request")
        
        assert result is True
    
    def test_verify_webhook_invalid_signature(self):
        """Test verifying webhook with invalid signature."""
        handler = WebhookHandler(secret="test_secret")
        result = handler.verify_webhook(b'{"test": true}', "sha256=invalid", "pull_request")
        
        assert result is False
    
    def test_verify_webhook_invalid_event(self):
        """Test verifying webhook with invalid event type."""
        handler = WebhookHandler()
        handler.validate_signature = Mock(return_value=True)
        
        result = handler.verify_webhook(b'{}', "sha256=dummy", "invalid_event")
        
        assert result is False


class TestCreateWebhookHandler:
    """Tests for create_webhook_handler function."""
    
    def test_create_with_token(self):
        """Test creating handler with token."""
        handler = create_webhook_handler(
            secret="test_secret",
            token="test_token",
        )
        
        assert handler.secret == "test_secret"
        assert handler.client is not None
    
    def test_create_without_token(self):
        """Test creating handler without token."""
        handler = create_webhook_handler(secret="test_secret")
        
        assert handler.secret == "test_secret"
        assert handler.client is None
