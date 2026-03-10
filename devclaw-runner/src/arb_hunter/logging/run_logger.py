"""
run_logger.py - Log each scan run with metadata, timing, and outcome.

Tracks the lifecycle of each arbitrage hunting run including start/end times,
duration, success/failure status, and associated metadata.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict

import structlog

from .logger_config import get_logger, set_correlation_id, bind_context


class RunStatus(str, Enum):
    """Status values for a scan run."""
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class RunMetrics:
    """Metrics collected during a scan run."""
    markets_scanned: int = 0
    markets_fetched: int = 0
    matches_found: int = 0
    opportunities_identified: int = 0
    alerts_sent: int = 0
    errors_encountered: int = 0
    api_calls_made: int = 0
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class RunRecord:
    """Complete record of a scan run."""
    run_id: str
    correlation_id: str
    status: RunStatus
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    success: Optional[bool] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    config_version: Optional[str] = None
    scan_parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: RunMetrics = field(default_factory=RunMetrics)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary for serialization."""
        result = asdict(self)
        # Convert datetime objects to ISO format strings
        result["started_at"] = self.started_at.isoformat()
        if self.ended_at:
            result["ended_at"] = self.ended_at.isoformat()
        return result


class RunLogger:
    """
    Logger for scan run lifecycle events.
    
    Tracks start, progress, and completion of arbitrage scanning runs
    with comprehensive metadata and metrics.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("run_logger")
        self.log_dir = Path(log_dir) if log_dir else None
        self._current_run: Optional[RunRecord] = None
        
    def start_run(
        self,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        config_version: Optional[str] = None,
        scan_parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a new scan run and log the event.
        
        Args:
            run_id: Optional run ID (generated if not provided)
            correlation_id: Optional correlation ID for tracing
            config_version: Version of configuration used
            scan_parameters: Parameters for this scan (sports, markets, etc.)
            metadata: Additional metadata
            
        Returns:
            The run_id for this scan
        """
        run_id = run_id or str(uuid.uuid4())
        correlation_id = correlation_id or run_id
        
        # Set correlation ID for all subsequent logs
        set_correlation_id(correlation_id)
        bind_context(run_id=run_id)
        
        self._current_run = RunRecord(
            run_id=run_id,
            correlation_id=correlation_id,
            status=RunStatus.STARTED,
            started_at=datetime.now(timezone.utc),
            config_version=config_version,
            scan_parameters=scan_parameters or {},
            metadata=metadata or {}
        )
        
        self.logger.info(
            "run_started",
            run_id=run_id,
            correlation_id=correlation_id,
            config_version=config_version,
            scan_parameters=scan_parameters,
            metadata=metadata
        )
        
        return run_id
    
    def update_progress(
        self,
        status: RunStatus,
        metrics_update: Optional[Dict[str, int]] = None,
        message: Optional[str] = None
    ) -> None:
        """
        Update the progress of the current run.
        
        Args:
            status: Current status of the run
            metrics_update: Partial metrics to update
            message: Optional progress message
        """
        if not self._current_run:
            self.logger.warning("update_progress_called_without_active_run")
            return
        
        self._current_run.status = status
        
        if metrics_update:
            for key, value in metrics_update.items():
                if hasattr(self._current_run.metrics, key):
                    setattr(self._current_run.metrics, key, value)
        
        log_data = {
            "run_id": self._current_run.run_id,
            "status": status.value,
            "metrics": self._current_run.metrics
        }
        
        if message:
            log_data["message"] = message
        
        self.logger.info("run_progress_update", **log_data)
    
    def complete_run(
        self,
        success: bool = True,
        final_metrics: Optional[RunMetrics] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None
    ) -> RunRecord:
        """
        Complete the current run and log the final state.
        
        Args:
            success: Whether the run completed successfully
            final_metrics: Final metrics for the run
            error_message: Error message if run failed
            error_type: Type of error if run failed
            
        Returns:
            The completed RunRecord
        """
        if not self._current_run:
            self.logger.warning("complete_run_called_without_active_run")
            raise RuntimeError("No active run to complete")
        
        self._current_run.ended_at = datetime.now(timezone.utc)
        self._current_run.duration_seconds = (
            self._current_run.ended_at - self._current_run.started_at
        ).total_seconds()
        self._current_run.success = success
        self._current_run.status = RunStatus.COMPLETED if success else RunStatus.FAILED
        
        if final_metrics:
            self._current_run.metrics = final_metrics
        
        if error_message:
            self._current_run.error_message = error_message
        if error_type:
            self._current_run.error_type = error_type
        
        log_level = "info" if success else "error"
        log_method = getattr(self.logger, log_level)
        
        log_data = {
            "run_id": self._current_run.run_id,
            "correlation_id": self._current_run.correlation_id,
            "status": self._current_run.status.value,
            "started_at": self._current_run.started_at.isoformat(),
            "ended_at": self._current_run.ended_at.isoformat(),
            "duration_seconds": self._current_run.duration_seconds,
            "success": success,
            "metrics": self._current_run.metrics.to_dict() if hasattr(self._current_run.metrics, 'to_dict') else vars(self._current_run.metrics),
        }
        
        if error_message:
            log_data["error_message"] = error_message
        if error_type:
            log_data["error_type"] = error_type
        
        log_method("run_completed", **log_data)
        
        # Write run record to file if log_dir is configured
        if self.log_dir:
            self._persist_run_record()
        
        return self._current_run
    
    def fail_run(
        self,
        error_message: str,
        error_type: Optional[str] = None,
        exception: Optional[Exception] = None
    ) -> RunRecord:
        """
        Mark the current run as failed with error details.
        
        Args:
            error_message: Description of the error
            error_type: Classification of the error
            exception: Original exception if available
            
        Returns:
            The failed RunRecord
        """
        if exception:
            error_type = error_type or type(exception).__name__
        
        return self.complete_run(
            success=False,
            error_message=error_message,
            error_type=error_type
        )
    
    def get_current_run(self) -> Optional[RunRecord]:
        """Get the currently active run record."""
        return self._current_run
    
    def _persist_run_record(self) -> None:
        """Write the run record to a JSON file for persistence."""
        if not self.log_dir or not self._current_run:
            return
        
        try:
            import json
            self.log_dir.mkdir(parents=True, exist_ok=True)
            
            # Store in date-organized directory
            date_str = self._current_run.started_at.strftime("%Y-%m-%d")
            run_dir = self.log_dir / "runs" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{self._current_run.run_id}.json"
            with open(file_path, "w") as f:
                json.dump(self._current_run.to_dict(), f, indent=2, default=str)
        except Exception as e:
            self.logger.error(
                "failed_to_persist_run_record",
                run_id=self._current_run.run_id,
                error=str(e)
            )


# Singleton instance for application-wide use
_run_logger_instance: Optional[RunLogger] = None


def initialize_run_logger(log_dir: Optional[Path] = None) -> RunLogger:
    """Initialize the global run logger instance."""
    global _run_logger_instance
    _run_logger_instance = RunLogger(log_dir=log_dir)
    return _run_logger_instance


def get_run_logger() -> RunLogger:
    """Get the global run logger instance."""
    if _run_logger_instance is None:
        return RunLogger()
    return _run_logger_instance
