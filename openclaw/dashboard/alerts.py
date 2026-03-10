"""
Alert System for OpenClaw Observability Dashboard

Monitors system metrics against configured thresholds and sends alerts
via webhooks to Slack, Discord, or other notification channels.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from urllib import request
from datetime import datetime, timedelta, timezone

# Configure logging
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """Supported alert channels."""
    SLACK = "slack"
    DISCORD = "discord"
    WEBHOOK = "webhook"


@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    metric: str  # e.g., "queue_depth.total", "stuck_tasks.count"
    operator: str  # ">", "<", "==", ">=", "<="
    threshold: float
    severity: AlertSeverity
    channels: List[AlertChannel] = field(default_factory=lambda: [AlertChannel.WEBHOOK])
    cooldown_minutes: int = 30
    enabled: bool = True
    description: str = ""


@dataclass
class Alert:
    """An triggered alert."""
    rule_name: str
    severity: AlertSeverity
    message: str
    metric_value: Any
    threshold: float
    timestamp: datetime
    acknowledged: bool = False


class AlertManager:
    """Manages alert rules, threshold checking, and notifications."""

    # Default alert rules
    DEFAULT_RULES: List[AlertRule] = [
        AlertRule(
            name="high_queue_depth",
            metric="queue_depth.total",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            description="Total queue depth exceeds 100 tasks"
        ),
        AlertRule(
            name="critical_queue_depth",
            metric="queue_depth.total",
            operator=">",
            threshold=500,
            severity=AlertSeverity.CRITICAL,
            description="Total queue depth exceeds 500 tasks"
        ),
        AlertRule(
            name="stuck_tasks_warning",
            metric="stuck_tasks.count",
            operator=">",
            threshold=10,
            severity=AlertSeverity.WARNING,
            description="More than 10 tasks are stuck"
        ),
        AlertRule(
            name="stuck_tasks_critical",
            metric="stuck_tasks.count",
            operator=">",
            threshold=20,
            severity=AlertSeverity.CRITICAL,
            description="More than 20 tasks are stuck"
        ),
        AlertRule(
            name="high_fail_rate",
            metric="review_metrics.fail_rate",
            operator=">",
            threshold=30.0,
            severity=AlertSeverity.WARNING,
            description="Task failure rate exceeds 30%"
        ),
        AlertRule(
            name="critical_fail_rate",
            metric="review_metrics.fail_rate",
            operator=">",
            threshold=50.0,
            severity=AlertSeverity.CRITICAL,
            description="Task failure rate exceeds 50%"
        ),
        AlertRule(
            name="dead_letter_warning",
            metric="dead_letter.recent_24h",
            operator=">",
            threshold=5,
            severity=AlertSeverity.WARNING,
            description="More than 5 tasks moved to dead letter queue in 24h"
        ),
        AlertRule(
            name="dead_letter_critical",
            metric="dead_letter.recent_24h",
            operator=">",
            threshold=10,
            severity=AlertSeverity.CRITICAL,
            description="More than 10 tasks moved to dead letter queue in 24h"
        ),
        AlertRule(
            name="high_cycle_time",
            metric="cycle_time.avg_seconds",
            operator=">",
            threshold=3600,  # 1 hour
            severity=AlertSeverity.WARNING,
            description="Average cycle time exceeds 1 hour"
        ),
    ]

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        slack_webhook: Optional[str] = None,
        discord_webhook: Optional[str] = None,
        rules: Optional[List[AlertRule]] = None
    ):
        """Initialize the alert manager.
        
        Args:
            webhook_url: Generic webhook URL for alerts
            slack_webhook: Slack webhook URL
            discord_webhook: Discord webhook URL
            rules: List of alert rules (uses defaults if not provided)
        """
        self.webhook_url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
        self.slack_webhook = slack_webhook or os.environ.get("SLACK_WEBHOOK_URL")
        self.discord_webhook = discord_webhook or os.environ.get("DISCORD_WEBHOOK_URL")
        
        self.rules = rules or self.DEFAULT_RULES.copy()
        self.active_alerts: List[Alert] = []
        self.alert_history: List[Alert] = []
        self._last_alert_time: Dict[str, datetime] = {}
        self._handlers: Dict[AlertChannel, Callable[[Alert, AlertRule], bool]] = {
            AlertChannel.SLACK: self._send_slack_alert,
            AlertChannel.DISCORD: self._send_discord_alert,
            AlertChannel.WEBHOOK: self._send_webhook_alert,
        }

    def add_rule(self, rule: AlertRule) -> None:
        """Add a new alert rule."""
        self.rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove an alert rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"Removed alert rule: {rule_name}")
                return True
        return False

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get a value from nested dictionary using dot notation."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None
        return value

    def _evaluate_condition(self, value: Any, operator: str, threshold: float) -> bool:
        """Evaluate if the condition is met."""
        if value is None:
            return False
        
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False

        if operator == ">":
            return value > threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<":
            return value < threshold
        elif operator == "<=":
            return value <= threshold
        elif operator == "==":
            return value == threshold
        elif operator == "!=":
            return value != threshold
        else:
            logger.warning(f"Unknown operator: {operator}")
            return False

    def _is_in_cooldown(self, rule: AlertRule) -> bool:
        """Check if the rule is in cooldown period."""
        last_time = self._last_alert_time.get(rule.name)
        if last_time is None:
            return False
        return datetime.now(timezone.utc) - last_time < timedelta(minutes=rule.cooldown_minutes)

    def check_thresholds(self, metrics: Dict[str, Any]) -> List[Alert]:
        """Check all alert rules against the provided metrics.
        
        Args:
            metrics: Dictionary of system metrics
            
        Returns:
            List of triggered alerts
        """
        triggered = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            if self._is_in_cooldown(rule):
                continue

            value = self._get_nested_value(metrics, rule.metric)
            if value is None:
                continue

            if self._evaluate_condition(value, rule.operator, rule.threshold):
                alert = Alert(
                    rule_name=rule.name,
                    severity=rule.severity,
                    message=self._format_alert_message(rule, value),
                    metric_value=value,
                    threshold=rule.threshold,
                    timestamp=datetime.now(timezone.utc)
                )
                triggered.append(alert)
                self.active_alerts.append(alert)
                self._last_alert_time[rule.name] = alert.timestamp
                
                # Send notifications
                self._send_alert(alert, rule)

        return triggered

    def _format_alert_message(self, rule: AlertRule, value: Any) -> str:
        """Format an alert message."""
        return (
            f"🚨 Alert: {rule.name}\n"
            f"Severity: {rule.severity.value.upper()}\n"
            f"Metric: {rule.metric} = {value}\n"
            f"Threshold: {rule.operator} {rule.threshold}\n"
            f"Description: {rule.description}"
        )

    def _send_alert(self, alert: Alert, rule: AlertRule) -> None:
        """Send alert through configured channels."""
        for channel in rule.channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    success = handler(alert, rule)
                    if success:
                        logger.info(f"Alert sent via {channel.value}: {rule.name}")
                    else:
                        logger.warning(f"Failed to send alert via {channel.value}: {rule.name}")
                except Exception as e:
                    logger.error(f"Error sending alert via {channel.value}: {e}")

    def _send_webhook_alert(self, alert: Alert, rule: AlertRule) -> bool:
        """Send alert to generic webhook."""
        if not self.webhook_url:
            return False

        payload = {
            "alert": {
                "name": rule.name,
                "severity": alert.severity.value,
                "message": alert.message,
                "metric": rule.metric,
                "value": alert.metric_value,
                "threshold": rule.threshold,
                "operator": rule.operator,
                "timestamp": alert.timestamp.isoformat(),
                "description": rule.description
            }
        }

        return self._post_json(self.webhook_url, payload)

    def _send_slack_alert(self, alert: Alert, rule: AlertRule) -> bool:
        """Send alert to Slack webhook."""
        if not self.slack_webhook:
            return False

        color_map = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ff9900",
            AlertSeverity.CRITICAL: "#ff0000"
        }

        payload = {
            "attachments": [{
                "color": color_map.get(alert.severity, "#808080"),
                "title": f"🚨 OpenClaw Alert: {rule.name}",
                "fields": [
                    {
                        "title": "Severity",
                        "value": alert.severity.value.upper(),
                        "short": True
                    },
                    {
                        "title": "Metric",
                        "value": f"{rule.metric} = {alert.metric_value}",
                        "short": True
                    },
                    {
                        "title": "Threshold",
                        "value": f"{rule.operator} {rule.threshold}",
                        "short": True
                    },
                    {
                        "title": "Description",
                        "value": rule.description,
                        "short": False
                    }
                ],
                "footer": "OpenClaw Observability",
                "ts": int(alert.timestamp.timestamp())
            }]
        }

        return self._post_json(self.slack_webhook, payload)

    def _send_discord_alert(self, alert: Alert, rule: AlertRule) -> bool:
        """Send alert to Discord webhook."""
        if not self.discord_webhook:
            return False

        color_map = {
            AlertSeverity.INFO: 0x36a64f,
            AlertSeverity.WARNING: 0xff9900,
            AlertSeverity.CRITICAL: 0xff0000
        }

        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨"
        }

        payload = {
            "embeds": [{
                "title": f"{emoji_map.get(alert.severity, '🔔')} OpenClaw Alert: {rule.name}",
                "color": color_map.get(alert.severity, 0x808080),
                "fields": [
                    {
                        "name": "Severity",
                        "value": alert.severity.value.upper(),
                        "inline": True
                    },
                    {
                        "name": "Metric",
                        "value": f"{rule.metric} = {alert.metric_value}",
                        "inline": True
                    },
                    {
                        "name": "Threshold",
                        "value": f"{rule.operator} {rule.threshold}",
                        "inline": True
                    },
                    {
                        "name": "Description",
                        "value": rule.description,
                        "inline": False
                    }
                ],
                "timestamp": alert.timestamp.isoformat(),
                "footer": {
                    "text": "OpenClaw Observability"
                }
            }]
        }

        return self._post_json(self.discord_webhook, payload)

    def _post_json(self, url: str, payload: Dict[str, Any]) -> bool:
        """Post JSON payload to webhook URL."""
        try:
            data = json.dumps(payload).encode("utf-8")
            req = request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            
            with request.urlopen(req, timeout=10) as response:
                return response.status in (200, 201, 204)
        except Exception as e:
            logger.error(f"Webhook POST failed: {e}")
            return False

    def get_active_alerts(self, severity: Optional[AlertSeverity] = None) -> List[Alert]:
        """Get currently active (unacknowledged) alerts."""
        alerts = [a for a in self.active_alerts if not a.acknowledged]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def acknowledge_alert(self, rule_name: str) -> bool:
        """Acknowledge all alerts for a rule."""
        found = False
        for alert in self.active_alerts:
            if alert.rule_name == rule_name and not alert.acknowledged:
                alert.acknowledged = True
                found = True
        return found

    def clear_resolved_alerts(self, metrics: Dict[str, Any]) -> List[Alert]:
        """Clear alerts that are no longer triggered."""
        resolved = []
        still_active = []
        
        for alert in self.active_alerts:
            # Find the rule
            rule = next((r for r in self.rules if r.name == alert.rule_name), None)
            if rule and rule.enabled:
                value = self._get_nested_value(metrics, rule.metric)
                if value is not None and not self._evaluate_condition(value, rule.operator, rule.threshold):
                    # Alert is resolved
                    alert.acknowledged = True
                    resolved.append(alert)
                    self.alert_history.append(alert)
                else:
                    still_active.append(alert)
            else:
                still_active.append(alert)
        
        self.active_alerts = still_active
        return resolved

    def export_rules(self) -> List[Dict[str, Any]]:
        """Export alert rules as JSON-serializable dict."""
        return [
            {
                "name": r.name,
                "metric": r.metric,
                "operator": r.operator,
                "threshold": r.threshold,
                "severity": r.severity.value,
                "channels": [c.value for c in r.channels],
                "cooldown_minutes": r.cooldown_minutes,
                "enabled": r.enabled,
                "description": r.description
            }
            for r in self.rules
        ]

    def import_rules(self, rules_data: List[Dict[str, Any]]) -> None:
        """Import alert rules from JSON."""
        self.rules = []
        for data in rules_data:
            rule = AlertRule(
                name=data["name"],
                metric=data["metric"],
                operator=data["operator"],
                threshold=data["threshold"],
                severity=AlertSeverity(data["severity"]),
                channels=[AlertChannel(c) for c in data.get("channels", ["webhook"])],
                cooldown_minutes=data.get("cooldown_minutes", 30),
                enabled=data.get("enabled", True),
                description=data.get("description", "")
            )
            self.rules.append(rule)


# Singleton instance
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """Get the global alert manager instance."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


def check_thresholds(metrics: Dict[str, Any]) -> List[Alert]:
    """Convenience function to check thresholds using global manager."""
    return get_alert_manager().check_thresholds(metrics)


def send_alert(
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    channel: AlertChannel = AlertChannel.WEBHOOK
) -> bool:
    """Send a one-off alert message.
    
    Args:
        message: Alert message
        severity: Alert severity level
        channel: Channel to send through
        
    Returns:
        True if sent successfully
    """
    manager = get_alert_manager()
    
    alert = Alert(
        rule_name="manual_alert",
        severity=severity,
        message=message,
        metric_value=None,
        threshold=0,
        timestamp=datetime.now(timezone.utc)
    )
    
    rule = AlertRule(
        name="manual_alert",
        metric="manual",
        operator=">",
        threshold=0,
        severity=severity,
        channels=[channel]
    )
    
    manager._send_alert(alert, rule)
    return True
