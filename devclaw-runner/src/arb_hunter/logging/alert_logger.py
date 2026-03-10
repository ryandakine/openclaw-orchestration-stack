"""
alert_logger.py - Log alerts sent for arbitrage opportunities.

Tracks notifications sent via various channels (webhook, email, SMS, push)
with delivery status and timing information.
"""

import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum

import structlog

from .logger_config import get_logger


class AlertChannel(str, Enum):
    """Supported alert channels."""
    WEBHOOK = "webhook"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    SLACK = "slack"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    PAGERDUTY = "pagerduty"


class AlertStatus(str, Enum):
    """Status of an alert delivery."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    RATE_LIMITED = "rate_limited"
    SUPPRESSED = "suppressed"


class AlertPriority(str, Enum):
    """Priority level for alerts."""
    CRITICAL = "critical"  # > 10% edge
    HIGH = "high"  # 5-10% edge
    MEDIUM = "medium"  # 2-5% edge
    LOW = "low"  # < 2% edge


@dataclass
class AlertRecord:
    """Record of an alert sent for an arbitrage opportunity."""
    alert_id: str
    run_id: str
    arb_id: str
    message_id: Optional[str]  # ID from the alerting service
    channel: AlertChannel
    priority: AlertPriority
    status: AlertStatus
    # Content summary (not full content for privacy/security)
    recipient_summary: str  # Obfuscated recipient info
    subject_summary: str  # Subject/preview text
    # Timing
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    # Metrics
    latency_ms: Optional[float] = None  # Time to send
    retry_count: int = 0
    # Error info
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    # Arb context
    edge_percent: Optional[float] = None
    profit_percent: Optional[float] = None
    source_pair: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        result = asdict(self)
        for field_name in ["created_at", "sent_at", "delivered_at", "failed_at"]:
            value = getattr(self, field_name)
            if value:
                result[field_name] = value.isoformat()
            else:
                result[field_name] = None
        result["channel"] = self.channel.value
        result["priority"] = self.priority.value
        result["status"] = self.status.value
        return result


class AlertLogger:
    """
    Logger for alert notifications.
    
    Tracks all alerts sent for arbitrage opportunities including
    delivery status, timing, and channel information.
    """
    
    def __init__(self, log_dir: Optional[Path] = None):
        self.logger = get_logger("alert_logger")
        self.log_dir = Path(log_dir) if log_dir else None
        self._alert_records: List[AlertRecord] = []
        self._suppression_rules: Dict[str, Any] = {}
    
    def log_alert_created(
        self,
        alert_id: str,
        run_id: str,
        arb_id: str,
        channel: AlertChannel,
        priority: AlertPriority,
        recipient_summary: str,
        subject_summary: str,
        edge_percent: Optional[float] = None,
        profit_percent: Optional[float] = None,
        source_pair: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AlertRecord:
        """
        Log creation of an alert (before sending).
        
        Args:
            alert_id: Unique alert identifier
            run_id: Parent run ID
            arb_id: Arbitrage opportunity ID
            channel: Alert channel
            priority: Alert priority level
            recipient_summary: Obfuscated recipient identifier
            subject_summary: Alert subject/preview
            edge_percent: Edge percentage
            profit_percent: Profit percentage
            source_pair: Source pair (e.g., "draftkings:fanduel")
            metadata: Additional metadata
            
        Returns:
            The AlertRecord
        """
        record = AlertRecord(
            alert_id=alert_id,
            run_id=run_id,
            arb_id=arb_id,
            message_id=None,
            channel=channel,
            priority=priority,
            status=AlertStatus.PENDING,
            recipient_summary=recipient_summary,
            subject_summary=subject_summary,
            created_at=datetime.now(timezone.utc),
            edge_percent=edge_percent,
            profit_percent=profit_percent,
            source_pair=source_pair,
            metadata=metadata or {}
        )
        
        self._alert_records.append(record)
        
        self.logger.info(
            "alert_created",
            alert_id=alert_id,
            run_id=run_id,
            arb_id=arb_id,
            channel=channel.value,
            priority=priority.value,
            recipient_summary=recipient_summary,
            edge_percent=round(edge_percent, 4) if edge_percent else None
        )
        
        return record
    
    def log_alert_sent(
        self,
        alert_id: str,
        message_id: str,
        latency_ms: float
    ) -> None:
        """
        Log successful alert delivery.
        
        Args:
            alert_id: Alert identifier
            message_id: Message ID from the alerting service
            latency_ms: Time to send in milliseconds
        """
        record = self._find_record(alert_id)
        if not record:
            self.logger.warning("alert_sent_not_found", alert_id=alert_id)
            return
        
        record.message_id = message_id
        record.status = AlertStatus.SENT
        record.sent_at = datetime.now(timezone.utc)
        record.latency_ms = latency_ms
        
        self.logger.info(
            "alert_sent",
            alert_id=alert_id,
            message_id=message_id,
            channel=record.channel.value,
            priority=record.priority.value,
            latency_ms=round(latency_ms, 2),
            arb_id=record.arb_id
        )
    
    def log_alert_delivered(
        self,
        alert_id: str,
        delivered_at: Optional[datetime] = None
    ) -> None:
        """
        Log confirmed delivery of an alert.
        
        Args:
            alert_id: Alert identifier
            delivered_at: Delivery timestamp (defaults to now)
        """
        record = self._find_record(alert_id)
        if not record:
            return
        
        record.status = AlertStatus.DELIVERED
        record.delivered_at = delivered_at or datetime.now(timezone.utc)
        
        self.logger.info(
            "alert_delivered",
            alert_id=alert_id,
            message_id=record.message_id,
            channel=record.channel.value,
            total_latency_ms=round(record.latency_ms or 0, 2) if record.latency_ms else None
        )
    
    def log_alert_failed(
        self,
        alert_id: str,
        error_message: str,
        error_code: Optional[str] = None,
        retryable: bool = False
    ) -> None:
        """
        Log failed alert delivery.
        
        Args:
            alert_id: Alert identifier
            error_message: Error description
            error_code: Error code from the service
            retryable: Whether the error is retryable
        """
        record = self._find_record(alert_id)
        if not record:
            return
        
        record.status = AlertStatus.RETRYING if retryable else AlertStatus.FAILED
        record.failed_at = datetime.now(timezone.utc)
        record.error_message = error_message
        record.error_code = error_code
        
        if retryable:
            record.retry_count += 1
        
        log_level = "warning" if retryable else "error"
        log_method = getattr(self.logger, log_level)
        
        log_method(
            "alert_failed",
            alert_id=alert_id,
            message_id=record.message_id,
            channel=record.channel.value,
            error_code=error_code,
            error_message=error_message,
            retry_count=record.retry_count,
            retryable=retryable
        )
    
    def log_alert_suppressed(
        self,
        alert_id: str,
        suppress_reason: str,
        rule_id: Optional[str] = None
    ) -> None:
        """
        Log an alert that was suppressed by a rule.
        
        Args:
            alert_id: Alert identifier
            suppress_reason: Reason for suppression
            rule_id: ID of the suppression rule
        """
        record = self._find_record(alert_id)
        if not record:
            return
        
        record.status = AlertStatus.SUPPRESSED
        record.metadata["suppressed"] = True
        record.metadata["suppress_reason"] = suppress_reason
        record.metadata["suppress_rule_id"] = rule_id
        
        self.logger.info(
            "alert_suppressed",
            alert_id=alert_id,
            arb_id=record.arb_id if record else None,
            reason=suppress_reason,
            rule_id=rule_id
        )
    
    def log_rate_limited(
        self,
        channel: AlertChannel,
        retry_after: Optional[int] = None,
        alert_id: Optional[str] = None
    ) -> None:
        """
        Log a rate limit event.
        
        Args:
            channel: Channel that was rate limited
            retry_after: Seconds until retry is allowed
            alert_id: Associated alert ID if applicable
        """
        if alert_id:
            record = self._find_record(alert_id)
            if record:
                record.status = AlertStatus.RATE_LIMITED
        
        self.logger.warning(
            "alert_rate_limited",
            channel=channel.value,
            retry_after_seconds=retry_after,
            alert_id=alert_id
        )
    
    def set_suppression_rules(self, rules: Dict[str, Any]) -> None:
        """Set active suppression rules for reference in logs."""
        self._suppression_rules = rules
    
    def get_alert_summary(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get summary of alerts.
        
        Args:
            run_id: Filter by run ID (optional)
            
        Returns:
            Summary dictionary
        """
        records = self._alert_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        
        total = len(records)
        by_status: Dict[str, int] = {}
        by_channel: Dict[str, int] = {}
        by_priority: Dict[str, int] = {}
        
        total_latency = 0.0
        latency_count = 0
        
        for record in records:
            # Count by status
            status = record.status.value
            by_status[status] = by_status.get(status, 0) + 1
            
            # Count by channel
            channel = record.channel.value
            by_channel[channel] = by_channel.get(channel, 0) + 1
            
            # Count by priority
            priority = record.priority.value
            by_priority[priority] = by_priority.get(priority, 0) + 1
            
            # Accumulate latency
            if record.latency_ms:
                total_latency += record.latency_ms
                latency_count += 1
        
        avg_latency = total_latency / latency_count if latency_count > 0 else 0
        
        return {
            "total_alerts": total,
            "by_status": by_status,
            "by_channel": by_channel,
            "by_priority": by_priority,
            "success_rate": round(by_status.get("sent", 0) / total * 100, 2) if total > 0 else 0,
            "average_latency_ms": round(avg_latency, 2),
            "suppression_rules_active": len(self._suppression_rules)
        }
    
    def get_failed_alerts(self, run_id: Optional[str] = None) -> List[AlertRecord]:
        """Get all failed alerts."""
        records = self._alert_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.status == AlertStatus.FAILED]
    
    def get_alerts_by_priority(
        self,
        priority: AlertPriority,
        run_id: Optional[str] = None
    ) -> List[AlertRecord]:
        """Get alerts filtered by priority."""
        records = self._alert_records
        if run_id:
            records = [r for r in records if r.run_id == run_id]
        return [r for r in records if r.priority == priority]
    
    def _find_record(self, alert_id: str) -> Optional[AlertRecord]:
        """Find an alert record by ID."""
        for record in self._alert_records:
            if record.alert_id == alert_id:
                return record
        return None
    
    def persist_records(self, run_id: str) -> Optional[Path]:
        """Persist alert records for a run to disk."""
        if not self.log_dir:
            return None
        
        records = [r for r in self._alert_records if r.run_id == run_id]
        if not records:
            return None
        
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            run_dir = self.log_dir / "alerts" / date_str
            run_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = run_dir / f"{run_id}_alerts.json"
            with open(file_path, "w") as f:
                json.dump({
                    "run_id": run_id,
                    "alerts": [r.to_dict() for r in records],
                    "summary": self.get_alert_summary(run_id),
                    "suppression_rules": self._suppression_rules
                }, f, indent=2)
            
            return file_path
        except Exception as e:
            self.logger.error(
                "failed_to_persist_alert_records",
                run_id=run_id,
                error=str(e)
            )
            return None
    
    def clear_records(self, run_id: Optional[str] = None) -> None:
        """Clear stored records."""
        if run_id:
            self._alert_records = [r for r in self._alert_records if r.run_id != run_id]
        else:
            self._alert_records.clear()


# Singleton instance
_alert_logger_instance: Optional[AlertLogger] = None


def initialize_alert_logger(log_dir: Optional[Path] = None) -> AlertLogger:
    """Initialize the global alert logger instance."""
    global _alert_logger_instance
    _alert_logger_instance = AlertLogger(log_dir=log_dir)
    return _alert_logger_instance


def get_alert_logger() -> AlertLogger:
    """Get the global alert logger instance."""
    if _alert_logger_instance is None:
        return AlertLogger()
    return _alert_logger_instance
