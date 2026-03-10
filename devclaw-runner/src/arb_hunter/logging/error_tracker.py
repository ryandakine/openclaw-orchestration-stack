"""
error_tracker.py - Track and categorize errors across the arbitrage hunting pipeline.

Provides comprehensive error tracking including API failures, parse errors,
calculation errors, and other exceptions with context and stack traces.
"""

import json
import traceback
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List, Type
from enum import Enum

import structlog

from .logger_config import get_logger


class ErrorSeverity(str, Enum):
    """Severity levels for errors."""
    CRITICAL = "critical"  # System cannot continue
    HIGH = "high"  # Major functionality impacted
    MEDIUM = "medium"  # Minor functionality impacted
    LOW = "low"  # Warning, non-blocking


class ErrorCategory(str, Enum):
    """Categories of errors in the arbitrage hunting pipeline."""
    API_FAILURE = "api_failure"  # External API errors
    API_TIMEOUT = "api_timeout"  # API request timeouts
    API_RATE_LIMIT = "api_rate_limit"  # Rate limiting
    PARSE_ERROR = "parse_error"  # Data parsing failures
    VALIDATION_ERROR = "validation_error"  # Data validation failures
    CALCULATION_ERROR = "calculation_error"  # Math/logic errors
    MATCH_ERROR = "match_error"  # Market matching errors
    CONFIG_ERROR = "config_error"  # Configuration errors
    NETWORK_ERROR = "network_error"  # Network connectivity
    DATABASE_ERROR = "database_error"  # Database errors
    CACHE_ERROR = "cache_error"  # Cache errors
    ALERT_ERROR = "alert_error"  # Alert sending errors
    UNKNOWN = "unknown"  # Uncategorized errors


@dataclass
class ErrorRecord:
    """Record of an error with full context."""
    error_id: str
    run_id: str
    timestamp: datetime
    category: ErrorCategory
    severity: ErrorSeverity
    error_type: str  # Exception class name
    error_message: str
    stack_trace: Optional[str] = None
    # Context
    source: Optional[str] = None  # Bookmaker/source if applicable
    endpoint: Optional[str] = None  # API endpoint if applicable
    context: Dict[str, Any] = field(default_factory=dict)  # Additional context
    # Recovery
    retryable: bool = False
    retry_count: int = 0
    resolved: bool = False
    resolution_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        result["category"] = self.category.value
        result["severity"] = self.severity.value
        return result


@dataclass
class ErrorSummary:
    """Summary of errors for a run or time period."""
    total_errors: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_severity: Dict[str, int] = field(default_factory=dict)
    by_source: Dict[str, int] = field(default_factory=dict)
    retryable_count: int = 0
    resolved_count: int = 0
    critical_errors: List[str] = field(default_factory=list)


class ErrorTracker:
    """
    Comprehensive error tracking system.
    
    Tracks errors across all components of the arbitrage hunting pipeline
    with categorization, severity levels, and resolution tracking.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("error_tracker")
        self.log_dir = Path(log_dir) if log_dir else None
        self._error_records: List[ErrorRecord] = []
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    def track_error(
        self,
        error_id: str,
        run_id: str,
        exception: Exception,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        source: Optional[str] = None,
        endpoint: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        retryable: bool = False,
        capture_stack: bool = True
    ) -> ErrorRecord:
        """
        Track an error with full context.
        
        Args:
            error_id: Unique error identifier
            run_id: Parent run ID
            exception: The exception that occurred
            category: Error category
            severity: Error severity
            source: Source/bookmaker if applicable
            endpoint: API endpoint if applicable
            context: Additional context data
            retryable: Whether this error is retryable
            capture_stack: Whether to capture stack trace
            
        Returns:
            The ErrorRecord
        """
        stack_trace = None
        if capture_stack:
            stack_trace = traceback.format_exc()
        
        record = ErrorRecord(
            error_id=error_id,
            run_id=run_id,
            timestamp=datetime.now(timezone.utc),
            category=category,
            severity=severity,
            error_type=type(exception).__name__,
            error_message=str(exception),
            stack_trace=stack_trace,
            source=source,
            endpoint=endpoint,
            context=context or {},
            retryable=retryable
        )
        
        self._error_records.append(record)
        self._error_counts[category.value] += 1
        
        # Log based on severity
        log_data = {
            "error_id": error_id,
            "run_id": run_id,
            "category": category.value,
            "severity": severity.value,
            "error_type": record.error_type,
            "error_message": record.error_message,
            "source": source,
            "retryable": retryable
        }
        
        if severity == ErrorSeverity.CRITICAL:
            self.logger.critical("error_tracked", **log_data)
        elif severity == ErrorSeverity.HIGH:
            self.logger.error("error_tracked", **log_data)
        elif severity == ErrorSeverity.MEDIUM:
            self.logger.warning("error_tracked", **log_data)
        else:
            self.logger.info("error_tracked", **log_data)
        
        return record
    
    def track_api_failure(
        self,
        error_id: str,
        run_id: str,
        source: str,
        endpoint: str,
        exception: Exception,
        http_status: Optional[int] = None,
        response_body: Optional[str] = None,
        retryable: bool = True
    ) -> ErrorRecord:
        """
        Track an API failure error.
        
        Args:
            error_id: Unique error identifier
            run_id: Parent run ID
            source: API source/bookmaker
            endpoint: API endpoint
            exception: The exception
            http_status: HTTP status code if available
            response_body: Response body if available
            retryable: Whether to retry
            
        Returns:
            The ErrorRecord
        """
        context = {
            "http_status": http_status,
            "response_body_preview": response_body[:500] if response_body else None
        }
        
        # Determine category based on exception type
        category = ErrorCategory.API_FAILURE
        severity = ErrorSeverity.HIGH
        
        if http_status == 429:
            category = ErrorCategory.API_RATE_LIMIT
            severity = ErrorSeverity.MEDIUM
        elif "timeout" in str(exception).lower():
            category = ErrorCategory.API_TIMEOUT
        
        return self.track_error(
            error_id=error_id,
            run_id=run_id,
            exception=exception,
            category=category,
            severity=severity,
            source=source,
            endpoint=endpoint,
            context=context,
            retryable=retryable
        )
    
    def track_parse_error(
        self,
        error_id: str,
        run_id: str,
        source: str,
        data_type: str,
        exception: Exception,
        data_preview: Optional[str] = None
    ) -> ErrorRecord:
        """
        Track a data parsing error.
        
        Args:
            error_id: Unique error identifier
            run_id: Parent run ID
            source: Data source
            data_type: Type of data being parsed
            exception: The parsing exception
            data_preview: Sample of data that failed parsing
            
        Returns:
            The ErrorRecord
        """
        context = {
            "data_type": data_type,
            "data_preview": data_preview[:500] if data_preview else None
        }
        
        return self.track_error(
            error_id=error_id,
            run_id=run_id,
            exception=exception,
            category=ErrorCategory.PARSE_ERROR,
            severity=ErrorSeverity.HIGH,
            source=source,
            context=context,
            retryable=False
        )
    
    def track_calculation_error(
        self,
        error_id: str,
        run_id: str,
        calculation_type: str,
        exception: Exception,
        inputs: Optional[Dict[str, Any]] = None
    ) -> ErrorRecord:
        """
        Track a calculation error.
        
        Args:
            error_id: Unique error identifier
            run_id: Parent run ID
            calculation_type: Type of calculation (edge, stake, etc.)
            exception: The calculation exception
            inputs: Input values for the calculation
            
        Returns:
            The ErrorRecord
        """
        context = {
            "calculation_type": calculation_type,
            "inputs": inputs
        }
        
        return self.track_error(
            error_id=error_id,
            run_id=run_id,
            exception=exception,
            category=ErrorCategory.CALCULATION_ERROR,
            severity=ErrorSeverity.HIGH,
            context=context,
            retryable=False
        )
    
    def track_validation_error(
        self,
        error_id: str,
        run_id: str,
        validation_type: str,
        field: str,
        expected: Any,
        actual: Any,
        source: Optional[str] = None
    ) -> ErrorRecord:
        """
        Track a data validation error.
        
        Args:
            error_id: Unique error identifier
            run_id: Parent run ID
            validation_type: Type of validation
            field: Field that failed validation
            expected: Expected value
            actual: Actual value
            source: Data source
            
        Returns:
            The ErrorRecord
        """
        exception = ValueError(
            f"Validation failed for {field}: expected {expected}, got {actual}"
        )
        
        context = {
            "validation_type": validation_type,
            "field": field,
            "expected": str(expected),
            "actual": str(actual)
        }
        
        return self.track_error(
            error_id=error_id,
            run_id=run_id,
            exception=exception,
            category=ErrorCategory.VALIDATION_ERROR,
            severity=ErrorSeverity.MEDIUM,
            source=source,
            context=context,
            retryable=False
        )
    
    def mark_resolved(
        self,
        error_id: str,
        resolution_notes: Optional[str] = None
    ) -> bool:
        """
        Mark an error as resolved.
        
        Args:
            error_id: Error to mark resolved
            resolution_notes: Notes about the resolution
            
        Returns:
            True if error was found and marked resolved
        """
        for record in self._error_records:
            if record.error_id == error_id:
                record.resolved = True
                record.resolution_notes = resolution_notes
                
                self.logger.info(
                    "error_marked_resolved",
                    error_id=error_id,
                    category=record.category.value,
                    resolution_notes=resolution_notes
                )
                return True
        
        return False
    
    def increment_retry(self, error_id: str) -> bool:
        """Increment retry count for an error."""
        for record in self._error_records:
            if record.error_id == error_id:
                record.retry_count += 1
                return True
        return False
    
    def get_error_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary of errors.
        
        Args:
            run_id: Filter by run ID (optional)
            
        Returns:
            Summary dictionary
        """
        records = self._error_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        summary = {
            "total_errors": len(records),
            "by_category": {},
            "by_severity": {},
            "by_source": {},
            "retryable": 0,
            "resolved": 0,
            "unresolved": 0,
            "critical_errors": []
        }
        
        for record in records:
            # By category
            cat = record.category.value
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
            
            # By severity
            sev = record.severity.value
            summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
            
            # By source
            src = record.source or "unknown"
            summary["by_source"][src] = summary["by_source"].get(src, 0) + 1
            
            # Retryable
            if record.retryable:
                summary["retryable"] += 1
            
            # Resolved
            if record.resolved:
                summary["resolved"] += 1
            else:
                summary["unresolved"] += 1
            
            # Critical errors
            if record.severity == ErrorSeverity.CRITICAL:
                summary["critical_errors"].append({
                    "error_id": record.error_id,
                    "category": cat,
                    "message": record.error_message
                })
        
        return summary
    
    def get_errors_by_category(
        self,
        category: ErrorCategory,
        run_id: Optional[str] = None
    ) -> List[ErrorRecord]:
        """Get errors filtered by category."""
        records = self._error_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.category == category]
    
    def get_errors_by_severity(
        self,
        severity: ErrorSeverity,
        run_id: Optional[str] = None
    ) -> List[ErrorRecord]:
        """Get errors filtered by severity."""
        records = self._error_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.severity == severity]
    
    def get_retryable_errors(self, run_id: Optional[str] = None) -> List[ErrorRecord]:
        """Get errors that can be retried."""
        records = self._error_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.retryable and not r.resolved]
    
    def persist_records(self, run_id: str) -> Optional[Path]:
        """Persist error records for a run to disk."""
        if not self.log_dir:
            return None
        
        records = [r for r in self._error_records if r.run_id == run_id]
        if not records:
            return None
        
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            run_dir = self.log_dir / "errors" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{run_id}_errors.json"
            with open(file_path, "w") as f:
                json.dump({
                    "run_id": run_id,
                    "errors": [r.to_dict() for r in records],
                    "summary": self.get_error_summary(run_id)
                }, f, indent=2)
            
            return file_path
        except Exception as e:
            self.logger.error(
                "failed_to_persist_error_records",
                run_id=run_id,
                error=str(e)
            )
            return None
    
    def clear_records(self, run_id: Optional[str] = None) -> None:
        """Clear stored records."""
        if run_id:
            self._error_records = [r for r in self._error_records if r.run_id != run_id]
        else:
            self._error_records.clear()
        self._error_counts.clear()


# Import for defaultdict
from collections import defaultdict

# Singleton instance
_error_tracker_instance: Optional[ErrorTracker] = None


def initialize_error_tracker(log_dir: Optional[Path] = None) -> ErrorTracker:
    """Initialize the global error tracker instance."""
    global _error_tracker_instance
    _error_tracker_instance = ErrorTracker(log_dir=log_dir)
    return _error_tracker_instance


def get_error_tracker() -> ErrorTracker:
    """Get the global error tracker instance."""
    if _error_tracker_instance is None:
        return ErrorTracker()
    return _error_tracker_instance
