"""
Job context module.

Creates and manages run context for each arbitrage hunting job.
"""

import platform
import socket
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Self, Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class JobContext:
    """
    Immutable job context containing run metadata.
    
    This context is passed through the entire pipeline to enable
    tracing, debugging, and audit logging.
    """

    # Identifiers
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # Timestamps
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Environment info
    hostname: str = field(default_factory=socket.gethostname)
    platform: str = field(default_factory=platform.platform)
    python_version: str = field(default_factory=platform.python_version)
    
    # Run metadata
    version: str = "1.0.0"
    triggered_by: str = "manual"  # manual, cron, webhook, etc.
    
    # Pipeline tracking
    stages_completed: list[str] = field(default_factory=list)
    stages_failed: list[str] = field(default_factory=list)
    
    # Metrics (updated during run)
    markets_fetched: int = 0
    markets_normalized: int = 0
    matches_found: int = 0
    arbs_calculated: int = 0
    arbs_filtered: int = 0
    alerts_sent: int = 0
    
    # Error tracking
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "correlation_id": self.correlation_id,
            "started_at": self.started_at.isoformat(),
            "hostname": self.hostname,
            "platform": self.platform,
            "python_version": self.python_version,
            "version": self.version,
            "triggered_by": self.triggered_by,
            "stages_completed": list(self.stages_completed),
            "stages_failed": list(self.stages_failed),
            "metrics": {
                "markets_fetched": self.markets_fetched,
                "markets_normalized": self.markets_normalized,
                "matches_found": self.matches_found,
                "arbs_calculated": self.arbs_calculated,
                "arbs_filtered": self.arbs_filtered,
                "alerts_sent": self.alerts_sent,
            },
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }

    def with_stage_completed(self, stage: str) -> Self:
        """Return new context with stage marked as completed."""
        new_stages = list(self.stages_completed)
        if stage not in new_stages:
            new_stages.append(stage)
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=new_stages,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_stage_failed(self, stage: str, error: Exception | None = None) -> Self:
        """Return new context with stage marked as failed."""
        new_failed = list(self.stages_failed)
        if stage not in new_failed:
            new_failed.append(stage)
        
        new_errors = list(self.errors)
        if error:
            new_errors.append({
                "stage": stage,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=new_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=new_errors,
            warnings=self.warnings,
        )

    def with_markets_fetched(self, count: int) -> Self:
        """Return new context with updated markets fetched count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=count,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_markets_normalized(self, count: int) -> Self:
        """Return new context with updated markets normalized count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=count,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_matches_found(self, count: int) -> Self:
        """Return new context with updated matches found count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=count,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_arbs_calculated(self, count: int) -> Self:
        """Return new context with updated arbs calculated count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=count,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_arbs_filtered(self, count: int) -> Self:
        """Return new context with updated arbs filtered count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=count,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_alerts_sent(self, count: int) -> Self:
        """Return new context with updated alerts sent count."""
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=count,
            errors=self.errors,
            warnings=self.warnings,
        )

    def with_error(self, error: Exception, context: dict[str, Any] | None = None) -> Self:
        """Return new context with added error."""
        new_errors = list(self.errors)
        error_entry: dict[str, Any] = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            error_entry["context"] = context
        new_errors.append(error_entry)
        
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=new_errors,
            warnings=self.warnings,
        )

    def with_warning(self, message: str, context: dict[str, Any] | None = None) -> Self:
        """Return new context with added warning."""
        new_warnings = list(self.warnings)
        warning_entry: dict[str, Any] = {
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if context:
            warning_entry["context"] = context
        new_warnings.append(warning_entry)
        
        return self.__class__(
            run_id=self.run_id,
            correlation_id=self.correlation_id,
            started_at=self.started_at,
            hostname=self.hostname,
            platform=self.platform,
            python_version=self.python_version,
            version=self.version,
            triggered_by=self.triggered_by,
            stages_completed=self.stages_completed,
            stages_failed=self.stages_failed,
            markets_fetched=self.markets_fetched,
            markets_normalized=self.markets_normalized,
            matches_found=self.matches_found,
            arbs_calculated=self.arbs_calculated,
            arbs_filtered=self.arbs_filtered,
            alerts_sent=self.alerts_sent,
            errors=self.errors,
            warnings=new_warnings,
        )

    @property
    def duration_seconds(self) -> float:
        """Calculate elapsed time since job started."""
        return (datetime.now(timezone.utc) - self.started_at).total_seconds()

    @property
    def has_errors(self) -> bool:
        """Check if job has any errors."""
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        """Check if job has any warnings."""
        return len(self.warnings) > 0


def create_job_context(triggered_by: str = "manual") -> JobContext:
    """Factory function to create a new job context."""
    ctx = JobContext(triggered_by=triggered_by)
    logger.info(
        "job_context_created",
        run_id=ctx.run_id,
        correlation_id=ctx.correlation_id,
        triggered_by=triggered_by,
    )
    return ctx
