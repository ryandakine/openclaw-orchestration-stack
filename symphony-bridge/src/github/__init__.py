"""GitHub API client and label management for Symphony PR Bridge."""

from .client import (
    GitHubClient,
    GitHubError,
    GitHubRateLimitError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubValidationError,
    PullRequest,
    RateLimitInfo,
)

from .labels import (
    LabelManager,
    Label,
    STANDARD_LABELS,
)

__all__ = [
    "GitHubClient",
    "GitHubError",
    "GitHubRateLimitError",
    "GitHubAuthError",
    "GitHubNotFoundError",
    "GitHubValidationError",
    "PullRequest",
    "RateLimitInfo",
    "LabelManager",
    "Label",
    "STANDARD_LABELS",
]
