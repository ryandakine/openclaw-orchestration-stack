"""
OpenClaw Arbitrage Hunter - Logging & Audit Module

Comprehensive observability with structured logs and audit trails.
"""

from .logger_config import (
    initialize_logging,
    get_logger,
    set_correlation_id,
    clear_correlation_id,
    bind_context,
)

from .run_logger import (
    initialize_run_logger,
    get_run_logger,
    RunLogger,
    RunRecord,
    RunStatus,
    RunMetrics,
)

from .market_logger import (
    initialize_market_logger,
    get_market_logger,
    MarketLogger,
    MarketFetchRecord,
    FetchStatus,
)

from .match_logger import (
    initialize_match_logger,
    get_match_logger,
    MatchLogger,
    MatchRecord,
    MatchBatchRecord,
    MatchResolution,
    MatchType,
)

from .reject_logger import (
    initialize_reject_logger,
    get_reject_logger,
    RejectLogger,
    RejectedOpportunity,
    RejectReason,
)

from .alert_logger import (
    initialize_alert_logger,
    get_alert_logger,
    AlertLogger,
    AlertRecord,
    AlertChannel,
    AlertStatus,
    AlertPriority,
)

from .audit_trail import (
    initialize_audit_trail,
    get_audit_trail,
    AuditTrail,
    AuditRecord,
    AuditArtifact,
)

from .metrics_reporter import (
    initialize_metrics_reporter,
    get_metrics_reporter,
    MetricsReporter,
    MetricType,
    MetricDefinition,
)

from .error_tracker import (
    initialize_error_tracker,
    get_error_tracker,
    ErrorTracker,
    ErrorRecord,
    ErrorSeverity,
    ErrorCategory,
)

from .log_aggregator import (
    initialize_log_aggregator,
    get_log_aggregator,
    LogAggregator,
    DailySummary,
    TrendAnalysis,
)

__all__ = [
    # Logger config
    "initialize_logging",
    "get_logger",
    "set_correlation_id",
    "clear_correlation_id",
    "bind_context",
    
    # Run logger
    "initialize_run_logger",
    "get_run_logger",
    "RunLogger",
    "RunRecord",
    "RunStatus",
    "RunMetrics",
    
    # Market logger
    "initialize_market_logger",
    "get_market_logger",
    "MarketLogger",
    "MarketFetchRecord",
    "FetchStatus",
    
    # Match logger
    "initialize_match_logger",
    "get_match_logger",
    "MatchLogger",
    "MatchRecord",
    "MatchBatchRecord",
    "MatchResolution",
    "MatchType",
    
    # Reject logger
    "initialize_reject_logger",
    "get_reject_logger",
    "RejectLogger",
    "RejectedOpportunity",
    "RejectReason",
    
    # Alert logger
    "initialize_alert_logger",
    "get_alert_logger",
    "AlertLogger",
    "AlertRecord",
    "AlertChannel",
    "AlertStatus",
    "AlertPriority",
    
    # Audit trail
    "initialize_audit_trail",
    "get_audit_trail",
    "AuditTrail",
    "AuditRecord",
    "AuditArtifact",
    
    # Metrics reporter
    "initialize_metrics_reporter",
    "get_metrics_reporter",
    "MetricsReporter",
    "MetricType",
    "MetricDefinition",
    
    # Error tracker
    "initialize_error_tracker",
    "get_error_tracker",
    "ErrorTracker",
    "ErrorRecord",
    "ErrorSeverity",
    "ErrorCategory",
    
    # Log aggregator
    "initialize_log_aggregator",
    "get_log_aggregator",
    "LogAggregator",
    "DailySummary",
    "TrendAnalysis",
]
