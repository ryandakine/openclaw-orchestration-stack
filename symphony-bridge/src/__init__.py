"""Symphony PR Bridge for OpenClaw Orchestration Stack."""

from .github import (
    GitHubClient,
    GitHubError,
    GitHubRateLimitError,
    GitHubAuthError,
    GitHubNotFoundError,
    GitHubValidationError,
    PullRequest,
    RateLimitInfo,
    LabelManager,
    Label,
    STANDARD_LABELS,
)

from .review import (
    ReviewManager,
    Review,
    ReviewEvent,
    ReviewState,
    ReviewComment,
    PRComment,
    generate_summary,
    format_comment,
    format_review_body,
    format_inline_comment,
    create_review_comments_from_findings,
    parse_findings_from_json,
    categorize_findings,
    get_severity_emoji,
    ReviewFinding,
    ReviewSummary,
    FindingSeverity,
    FindingCategory,
)

from .pr_lifecycle import (
    PRLifecycleManager,
    PRStatus,
    PRState,
    MergeState,
)

from .webhook_handler import (
    WebhookHandler,
    WebhookPayload,
    PREvent,
    ReviewEvent as WebhookReviewEvent,
    WebhookEventType,
    PREventAction,
    ReviewEventAction,
    create_webhook_handler,
)

__version__ = "0.1.0"

__all__ = [
    # GitHub Client
    "GitHubClient",
    "GitHubError",
    "GitHubRateLimitError",
    "GitHubAuthError",
    "GitHubNotFoundError",
    "GitHubValidationError",
    "PullRequest",
    "RateLimitInfo",
    # Labels
    "LabelManager",
    "Label",
    "STANDARD_LABELS",
    # Review
    "ReviewManager",
    "Review",
    "ReviewEvent",
    "ReviewState",
    "ReviewComment",
    "PRComment",
    # Summary
    "generate_summary",
    "format_comment",
    "format_review_body",
    "format_inline_comment",
    "create_review_comments_from_findings",
    "parse_findings_from_json",
    "categorize_findings",
    "get_severity_emoji",
    "ReviewFinding",
    "ReviewSummary",
    "FindingSeverity",
    "FindingCategory",
    # PR Lifecycle
    "PRLifecycleManager",
    "PRStatus",
    "PRState",
    "MergeState",
    # Webhook
    "WebhookHandler",
    "WebhookPayload",
    "PREvent",
    "WebhookReviewEvent",
    "WebhookEventType",
    "PREventAction",
    "ReviewEventAction",
    "create_webhook_handler",
]
