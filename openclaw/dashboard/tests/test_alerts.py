"""
Unit tests for the Alerts module.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock

from alerts import (
    AlertManager,
    AlertRule,
    Alert,
    AlertSeverity,
    AlertChannel,
    get_alert_manager,
    check_thresholds,
    send_alert
)


class TestAlertRule(unittest.TestCase):
    """Test cases for AlertRule dataclass."""

    def test_default_rule(self):
        """Test creating an alert rule with defaults."""
        rule = AlertRule(
            name="test_rule",
            metric="queue_depth.total",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING
        )
        
        self.assertEqual(rule.name, "test_rule")
        self.assertEqual(rule.metric, "queue_depth.total")
        self.assertEqual(rule.operator, ">")
        self.assertEqual(rule.threshold, 100)
        self.assertEqual(rule.severity, AlertSeverity.WARNING)
        self.assertEqual(rule.cooldown_minutes, 30)
        self.assertTrue(rule.enabled)
        self.assertEqual(rule.channels, [AlertChannel.WEBHOOK])

    def test_custom_rule(self):
        """Test creating an alert rule with custom values."""
        rule = AlertRule(
            name="critical_rule",
            metric="stuck_tasks.count",
            operator=">=",
            threshold=50,
            severity=AlertSeverity.CRITICAL,
            channels=[AlertChannel.SLACK, AlertChannel.DISCORD],
            cooldown_minutes=60,
            enabled=False,
            description="Custom description"
        )
        
        self.assertEqual(rule.severity, AlertSeverity.CRITICAL)
        self.assertEqual(rule.cooldown_minutes, 60)
        self.assertFalse(rule.enabled)
        self.assertEqual(len(rule.channels), 2)


class TestAlert(unittest.TestCase):
    """Test cases for Alert dataclass."""

    def test_alert_creation(self):
        """Test creating an alert."""
        alert = Alert(
            rule_name="test_alert",
            severity=AlertSeverity.WARNING,
            message="Test message",
            metric_value=150,
            threshold=100,
            timestamp=datetime.now(timezone.utc)
        )
        
        self.assertEqual(alert.rule_name, "test_alert")
        self.assertEqual(alert.severity, AlertSeverity.WARNING)
        self.assertFalse(alert.acknowledged)


class TestAlertManager(unittest.TestCase):
    """Test cases for AlertManager."""

    def setUp(self):
        """Set up test alert manager."""
        self.manager = AlertManager(
            webhook_url="http://test.webhook",
            slack_webhook="http://test.slack",
            discord_webhook="http://test.discord"
        )

    def test_initialization(self):
        """Test alert manager initialization."""
        self.assertEqual(self.manager.webhook_url, "http://test.webhook")
        self.assertEqual(self.manager.slack_webhook, "http://test.slack")
        self.assertEqual(self.manager.discord_webhook, "http://test.discord")
        self.assertEqual(len(self.manager.rules), len(AlertManager.DEFAULT_RULES))

    def test_add_rule(self):
        """Test adding a new rule."""
        new_rule = AlertRule(
            name="custom_rule",
            metric="custom.metric",
            operator=">",
            threshold=50,
            severity=AlertSeverity.INFO
        )
        
        initial_count = len(self.manager.rules)
        self.manager.add_rule(new_rule)
        
        self.assertEqual(len(self.manager.rules), initial_count + 1)
        self.assertIn(new_rule, self.manager.rules)

    def test_remove_rule(self):
        """Test removing a rule."""
        rule_name = self.manager.rules[0].name
        result = self.manager.remove_rule(rule_name)
        
        self.assertTrue(result)
        self.assertNotIn(rule_name, [r.name for r in self.manager.rules])

    def test_remove_nonexistent_rule(self):
        """Test removing a rule that doesn't exist."""
        result = self.manager.remove_rule("nonexistent_rule")
        self.assertFalse(result)

    def test_get_nested_value(self):
        """Test getting nested values from dict."""
        data = {
            "level1": {
                "level2": {
                    "value": 42
                }
            }
        }
        
        self.assertEqual(
            self.manager._get_nested_value(data, "level1.level2.value"),
            42
        )
        self.assertIsNone(self.manager._get_nested_value(data, "level1.nonexistent"))
        self.assertIsNone(self.manager._get_nested_value(data, "nonexistent.path"))

    def test_evaluate_condition(self):
        """Test condition evaluation."""
        # Greater than
        self.assertTrue(self.manager._evaluate_condition(150, ">", 100))
        self.assertFalse(self.manager._evaluate_condition(50, ">", 100))
        
        # Less than
        self.assertTrue(self.manager._evaluate_condition(50, "<", 100))
        self.assertFalse(self.manager._evaluate_condition(150, "<", 100))
        
        # Equal
        self.assertTrue(self.manager._evaluate_condition(100, "==", 100))
        self.assertFalse(self.manager._evaluate_condition(50, "==", 100))
        
        # Greater than or equal
        self.assertTrue(self.manager._evaluate_condition(100, ">=", 100))
        self.assertTrue(self.manager._evaluate_condition(150, ">=", 100))
        
        # Less than or equal
        self.assertTrue(self.manager._evaluate_condition(100, "<=", 100))
        self.assertTrue(self.manager._evaluate_condition(50, "<=", 100))
        
        # Not equal
        self.assertTrue(self.manager._evaluate_condition(50, "!=", 100))
        self.assertFalse(self.manager._evaluate_condition(100, "!=", 100))

    def test_evaluate_condition_with_none(self):
        """Test condition evaluation with None value."""
        self.assertFalse(self.manager._evaluate_condition(None, ">", 100))

    def test_is_in_cooldown(self):
        """Test cooldown checking."""
        rule = AlertRule(
            name="test_rule",
            metric="test.metric",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            cooldown_minutes=30
        )
        
        # Not in cooldown initially
        self.assertFalse(self.manager._is_in_cooldown(rule))
        
        # Set last alert time
        self.manager._last_alert_time[rule.name] = datetime.now(timezone.utc)
        
        # Should be in cooldown
        self.assertTrue(self.manager._is_in_cooldown(rule))

    def test_check_thresholds_no_trigger(self):
        """Test threshold checking with no alerts triggered."""
        metrics = {
            "queue_depth": {
                "total": 50  # Below default threshold of 100
            }
        }
        
        alerts = self.manager.check_thresholds(metrics)
        self.assertEqual(len(alerts), 0)

    def test_check_thresholds_triggered(self):
        """Test threshold checking with alert triggered."""
        # Create a simple rule that will trigger
        self.manager.rules = [
            AlertRule(
                name="test_trigger",
                metric="queue_depth.total",
                operator=">",
                threshold=100,
                severity=AlertSeverity.WARNING,
                cooldown_minutes=0  # No cooldown for testing
            )
        ]
        
        metrics = {
            "queue_depth": {
                "total": 150  # Above threshold
            }
        }
        
        with patch.object(self.manager, '_send_alert'):
            alerts = self.manager.check_thresholds(metrics)
            
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].rule_name, "test_trigger")
        self.assertEqual(alerts[0].severity, AlertSeverity.WARNING)

    def test_check_thresholds_disabled_rule(self):
        """Test that disabled rules don't trigger."""
        self.manager.rules = [
            AlertRule(
                name="disabled_rule",
                metric="queue_depth.total",
                operator=">",
                threshold=100,
                severity=AlertSeverity.WARNING,
                enabled=False
            )
        ]
        
        metrics = {"queue_depth": {"total": 150}}
        alerts = self.manager.check_thresholds(metrics)
        
        self.assertEqual(len(alerts), 0)

    def test_get_active_alerts(self):
        """Test getting active alerts."""
        alert1 = Alert(
            rule_name="alert1",
            severity=AlertSeverity.WARNING,
            message="Test",
            metric_value=100,
            threshold=50,
            timestamp=datetime.now(timezone.utc)
        )
        alert2 = Alert(
            rule_name="alert2",
            severity=AlertSeverity.CRITICAL,
            message="Test",
            metric_value=100,
            threshold=50,
            timestamp=datetime.now(timezone.utc),
            acknowledged=True
        )
        
        self.manager.active_alerts = [alert1, alert2]
        
        # Get all active (unacknowledged)
        active = self.manager.get_active_alerts()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].rule_name, "alert1")
        
        # Get by severity
        critical = self.manager.get_active_alerts(severity=AlertSeverity.CRITICAL)
        self.assertEqual(len(critical), 0)  # alert2 is acknowledged

    def test_acknowledge_alert(self):
        """Test acknowledging alerts."""
        alert = Alert(
            rule_name="test_alert",
            severity=AlertSeverity.WARNING,
            message="Test",
            metric_value=100,
            threshold=50,
            timestamp=datetime.now(timezone.utc)
        )
        
        self.manager.active_alerts = [alert]
        
        result = self.manager.acknowledge_alert("test_alert")
        self.assertTrue(result)
        self.assertTrue(alert.acknowledged)

    def test_acknowledge_nonexistent_alert(self):
        """Test acknowledging non-existent alert."""
        result = self.manager.acknowledge_alert("nonexistent")
        self.assertFalse(result)

    def test_clear_resolved_alerts(self):
        """Test clearing resolved alerts."""
        # Create a rule
        rule = AlertRule(
            name="test_rule",
            metric="queue_depth.total",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING
        )
        self.manager.rules = [rule]
        
        # Create an active alert
        alert = Alert(
            rule_name="test_rule",
            severity=AlertSeverity.WARNING,
            message="Test",
            metric_value=150,
            threshold=100,
            timestamp=datetime.now(timezone.utc)
        )
        self.manager.active_alerts = [alert]
        
        # Metrics now below threshold
        metrics = {"queue_depth": {"total": 50}}
        
        resolved = self.manager.clear_resolved_alerts(metrics)
        
        self.assertEqual(len(resolved), 1)
        self.assertTrue(alert.acknowledged)
        self.assertEqual(len(self.manager.active_alerts), 0)

    def test_export_import_rules(self):
        """Test exporting and importing rules."""
        original_rules = self.manager.rules[:]
        
        # Export
        exported = self.manager.export_rules()
        self.assertIsInstance(exported, list)
        self.assertGreater(len(exported), 0)
        
        # Clear and import
        self.manager.rules = []
        self.manager.import_rules(exported)
        
        self.assertEqual(len(self.manager.rules), len(original_rules))

    @patch('alerts.request.urlopen')
    def test_send_webhook_alert(self, mock_urlopen):
        """Test sending webhook alert."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        alert = Alert(
            rule_name="test",
            severity=AlertSeverity.WARNING,
            message="Test message",
            metric_value=150,
            threshold=100,
            timestamp=datetime.now(timezone.utc)
        )
        
        rule = AlertRule(
            name="test",
            metric="metric",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.WEBHOOK]
        )
        
        result = self.manager._send_webhook_alert(alert, rule)
        self.assertTrue(result)

    @patch('alerts.request.urlopen')
    def test_send_slack_alert(self, mock_urlopen):
        """Test sending Slack alert."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        alert = Alert(
            rule_name="test",
            severity=AlertSeverity.WARNING,
            message="Test message",
            metric_value=150,
            threshold=100,
            timestamp=datetime.now(timezone.utc)
        )
        
        rule = AlertRule(
            name="test",
            metric="metric",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.SLACK]
        )
        
        result = self.manager._send_slack_alert(alert, rule)
        self.assertTrue(result)

    @patch('alerts.request.urlopen')
    def test_send_discord_alert(self, mock_urlopen):
        """Test sending Discord alert."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        alert = Alert(
            rule_name="test",
            severity=AlertSeverity.WARNING,
            message="Test message",
            metric_value=150,
            threshold=100,
            timestamp=datetime.now(timezone.utc)
        )
        
        rule = AlertRule(
            name="test",
            metric="metric",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.DISCORD]
        )
        
        result = self.manager._send_discord_alert(alert, rule)
        self.assertTrue(result)

    def test_send_alert_no_url(self):
        """Test sending alert with no webhook URL configured."""
        manager = AlertManager()  # No webhooks configured
        
        alert = Alert(
            rule_name="test",
            severity=AlertSeverity.WARNING,
            message="Test",
            metric_value=100,
            threshold=50,
            timestamp=datetime.now(timezone.utc)
        )
        
        rule = AlertRule(
            name="test",
            metric="metric",
            operator=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            channels=[AlertChannel.WEBHOOK]
        )
        
        result = manager._send_webhook_alert(alert, rule)
        self.assertFalse(result)


class TestModuleFunctions(unittest.TestCase):
    """Test module-level convenience functions."""

    def test_singleton_manager(self):
        """Test that get_alert_manager returns singleton."""
        m1 = get_alert_manager()
        m2 = get_alert_manager()
        self.assertIs(m1, m2)

    @patch('alerts.get_alert_manager')
    def test_check_thresholds_convenience(self, mock_get_manager):
        """Test check_thresholds convenience function."""
        mock_manager = Mock()
        mock_manager.check_thresholds.return_value = []
        mock_get_manager.return_value = mock_manager
        
        result = check_thresholds({"test": "data"})
        
        mock_manager.check_thresholds.assert_called_once_with({"test": "data"})
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
