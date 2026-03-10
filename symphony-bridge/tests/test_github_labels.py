"""
Unit tests for GitHub label management.
"""

import pytest
from unittest.mock import Mock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from github.labels import (
    LabelManager,
    Label,
    STANDARD_LABELS,
)
from github.client import GitHubNotFoundError


class TestLabel:
    """Tests for Label dataclass."""
    
    def test_from_api_response(self, sample_label_data):
        """Test creating Label from API response."""
        label = Label.from_api_response(sample_label_data)
        
        assert label.id == 123
        assert label.name == "openclaw"
        assert label.color == "0052CC"
        assert label.description == "Managed by OpenClaw"
        assert label.url == "https://api.github.com/repos/owner/repo/labels/openclaw"
        assert not label.default
    
    def test_from_api_response_minimal(self):
        """Test creating Label with minimal data."""
        data = {
            "name": "bug",
            "color": "ff0000",
        }
        label = Label.from_api_response(data)
        
        assert label.name == "bug"
        assert label.color == "ff0000"
        assert label.description is None
        assert label.id is None


class TestLabelManager:
    """Tests for LabelManager."""
    
    def test_list_labels(self, mock_github_client):
        """Test listing labels."""
        mock_github_client._request.return_value = [
            {"name": "bug", "color": "ff0000"},
            {"name": "feature", "color": "00ff00"},
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.list_labels("owner", "repo")
        
        assert len(labels) == 2
        assert labels[0].name == "bug"
        assert labels[1].name == "feature"
        mock_github_client._request.assert_called_once()
    
    def test_get_label_found(self, mock_github_client):
        """Test getting an existing label."""
        mock_github_client._request.return_value = {
            "name": "openclaw",
            "color": "0052CC",
            "description": "Test",
        }
        
        manager = LabelManager(mock_github_client)
        label = manager.get_label("owner", "repo", "openclaw")
        
        assert label is not None
        assert label.name == "openclaw"
    
    def test_get_label_not_found(self, mock_github_client):
        """Test getting a non-existent label."""
        mock_github_client._request.side_effect = GitHubNotFoundError("Not found")
        
        manager = LabelManager(mock_github_client)
        label = manager.get_label("owner", "repo", "nonexistent")
        
        assert label is None
    
    def test_create_label(self, mock_github_client):
        """Test creating a label."""
        mock_github_client._request.return_value = {
            "name": "new-label",
            "color": "ff0000",
            "description": "New label description",
        }
        
        manager = LabelManager(mock_github_client)
        label = manager.create_label(
            "owner",
            "repo",
            "new-label",
            "#ff0000",  # With # prefix
            "New label description",
        )
        
        assert label.name == "new-label"
        assert label.color == "ff0000"  # # should be stripped
        mock_github_client._request.assert_called_once()
    
    def test_create_label_if_missing_new(self, mock_github_client):
        """Test creating label when it doesn't exist."""
        mock_github_client._request.side_effect = [
            GitHubNotFoundError("Not found"),  # get_label
            {"name": "new-label", "color": "ff0000"},  # create_label
        ]
        
        manager = LabelManager(mock_github_client)
        label = manager.create_label_if_missing(
            "owner",
            "repo",
            "new-label",
            "ff0000",
        )
        
        assert label.name == "new-label"
        assert mock_github_client._request.call_count == 2
    
    def test_create_label_if_missing_existing(self, mock_github_client):
        """Test creating label when it already exists."""
        mock_github_client._request.return_value = {
            "name": "existing-label",
            "color": "00ff00",
        }
        
        manager = LabelManager(mock_github_client)
        label = manager.create_label_if_missing(
            "owner",
            "repo",
            "existing-label",
            "ff0000",  # Different color, but shouldn't update
        )
        
        assert label.name == "existing-label"
        assert mock_github_client._request.call_count == 1  # Only get, not create
    
    def test_add_label(self, mock_github_client):
        """Test adding a label to PR."""
        mock_github_client._request.return_value = [
            {"name": "openclaw"},
            {"name": "needs-review"},
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.add_label("owner", "repo", 42, "needs-review")
        
        assert "needs-review" in labels
        mock_github_client._request.assert_called_once()
    
    def test_add_labels(self, mock_github_client):
        """Test adding multiple labels to PR."""
        mock_github_client._request.return_value = [
            {"name": "openclaw"},
            {"name": "approved"},
            {"name": "auto-merge"},
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.add_labels(
            "owner",
            "repo",
            42,
            ["approved", "auto-merge"],
        )
        
        assert "approved" in labels
        assert "auto-merge" in labels
    
    def test_remove_label(self, mock_github_client):
        """Test removing a label from PR."""
        mock_github_client._request.return_value = [{"name": "openclaw"}]
        
        manager = LabelManager(mock_github_client)
        labels = manager.remove_label("owner", "repo", 42, "needs-review")
        
        assert "needs-review" not in labels
        assert "openclaw" in labels
    
    def test_remove_label_not_found(self, mock_github_client):
        """Test removing a label that doesn't exist on PR."""
        mock_github_client._request.side_effect = [
            GitHubNotFoundError("Not found"),  # remove fails
            [{"name": "openclaw"}],  # list_pr_labels returns current labels
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.remove_label("owner", "repo", 42, "nonexistent")
        
        assert "openclaw" in labels
    
    def test_list_pr_labels(self, mock_github_client):
        """Test listing labels on a PR."""
        mock_github_client._request.return_value = [
            {"name": "openclaw"},
            {"name": "needs-review"},
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.list_pr_labels("owner", "repo", 42)
        
        assert len(labels) == 2
        assert "openclaw" in labels
    
    def test_set_labels(self, mock_github_client):
        """Test setting exact labels on PR."""
        mock_github_client._request.return_value = [
            {"name": "approved"},
            {"name": "openclaw"},
        ]
        
        manager = LabelManager(mock_github_client)
        labels = manager.set_labels("owner", "repo", 42, ["approved", "openclaw"])
        
        assert labels == ["approved", "openclaw"]
    
    def test_setup_standard_labels(self, mock_github_client):
        """Test setting up all standard labels."""
        from github.labels import STANDARD_LABELS
        # Each label requires: 1) GET to check existence, 2) POST to create
        # But since we use create_label_if_missing, first call is GET, second is POST if not found
        side_effects = []
        for i, (name, config) in enumerate(STANDARD_LABELS.items()):
            side_effects.append(GitHubNotFoundError("Not found"))  # GET - not found
            side_effects.append({"name": name, "color": config["color"]})  # POST - create
        
        mock_github_client._request.side_effect = side_effects
        
        manager = LabelManager(mock_github_client)
        labels = manager.setup_standard_labels("owner", "repo")
        
        assert len(labels) == len(STANDARD_LABELS)
        # Each label: 1 GET + 1 POST = 2 calls
        assert mock_github_client._request.call_count == len(STANDARD_LABELS) * 2
    
    def test_has_label_true(self, mock_github_client):
        """Test checking if PR has a label (true case)."""
        mock_github_client._request.return_value = [
            {"name": "openclaw"},
            {"name": "needs-review"},
        ]
        
        manager = LabelManager(mock_github_client)
        result = manager.has_label("owner", "repo", 42, "openclaw")
        
        assert result is True
    
    def test_has_label_false(self, mock_github_client):
        """Test checking if PR has a label (false case)."""
        mock_github_client._request.return_value = [{"name": "openclaw"}]
        
        manager = LabelManager(mock_github_client)
        result = manager.has_label("owner", "repo", 42, "nonexistent")
        
        assert result is False
    
    def test_remove_all_labels(self, mock_github_client):
        """Test removing all labels from PR."""
        mock_github_client._request.return_value = {}
        
        manager = LabelManager(mock_github_client)
        result = manager.remove_all_labels("owner", "repo", 42)
        
        assert result is True
    
    def test_update_label(self, mock_github_client):
        """Test updating a label."""
        mock_github_client._request.return_value = {
            "name": "updated-label",
            "color": "00ff00",
            "description": "Updated description",
        }
        
        manager = LabelManager(mock_github_client)
        label = manager.update_label(
            "owner",
            "repo",
            "old-label",
            new_name="updated-label",
            color="#00ff00",
            description="Updated description",
        )
        
        assert label.name == "updated-label"
        assert label.color == "00ff00"
    
    def test_delete_label_success(self, mock_github_client):
        """Test deleting a label successfully."""
        mock_github_client._request.return_value = {}
        
        manager = LabelManager(mock_github_client)
        result = manager.delete_label("owner", "repo", "label-to-delete")
        
        assert result is True
    
    def test_delete_label_not_found(self, mock_github_client):
        """Test deleting a label that doesn't exist."""
        mock_github_client._request.side_effect = GitHubNotFoundError("Not found")
        
        manager = LabelManager(mock_github_client)
        result = manager.delete_label("owner", "repo", "nonexistent")
        
        assert result is False


class TestStandardLabels:
    """Tests for standard labels configuration."""
    
    def test_standard_labels_defined(self):
        """Test that standard labels are defined."""
        assert "openclaw" in STANDARD_LABELS
        assert "needs-review" in STANDARD_LABELS
        assert "approved" in STANDARD_LABELS
        assert "changes-requested" in STANDARD_LABELS
    
    def test_standard_labels_have_required_fields(self):
        """Test that standard labels have color and description."""
        for name, config in STANDARD_LABELS.items():
            assert "color" in config, f"{name} missing color"
            assert "description" in config, f"{name} missing description"
            assert len(config["color"]) == 6, f"{name} color should be 6 hex chars"
