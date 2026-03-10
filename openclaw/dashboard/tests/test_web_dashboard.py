"""
Unit tests for the Web Dashboard module.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, patch, MagicMock


class TestWebDashboard(unittest.TestCase):
    """Test cases for Flask web dashboard."""

    def setUp(self):
        """Set up test client."""
        # Mock the metrics collector and alert manager before importing web_dashboard
        self.mock_collector_patcher = patch('web_dashboard.metrics_collector')
        self.mock_alerts_patcher = patch('web_dashboard.alert_manager')
        
        self.mock_collector = self.mock_collector_patcher.start()
        self.mock_alerts = self.mock_alerts_patcher.start()
        
        # Import web_dashboard after mocking
        from web_dashboard import app
        self.app = app
        self.client = app.test_client()

    def tearDown(self):
        """Clean up patches."""
        self.mock_collector_patcher.stop()
        self.mock_alerts_patcher.stop()

    def test_index_route(self):
        """Test main dashboard page loads."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'OpenClaw Observability Dashboard', response.data)
        self.assertIn(b'dashboard.js', response.data)

    def test_health_check_healthy(self):
        """Test health check endpoint when healthy."""
        self.mock_collector.get_all_metrics.return_value = {
            'system_health': {'status': 'healthy'}
        }
        
        response = self.client.get('/api/health')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('checks', data)

    def test_health_check_critical(self):
        """Test health check endpoint when critical."""
        self.mock_collector.get_all_metrics.return_value = {
            'system_health': {'status': 'critical'}
        }
        
        response = self.client.get('/api/health')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 503)
        self.assertEqual(data['status'], 'critical')

    def test_health_check_error(self):
        """Test health check when exception occurs."""
        self.mock_collector.get_all_metrics.side_effect = Exception("DB Error")
        
        response = self.client.get('/api/health')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 503)
        self.assertEqual(data['status'], 'error')

    def test_get_metrics(self):
        """Test metrics endpoint."""
        self.mock_collector.get_all_metrics.return_value = {
            'queue_depth': {'total': 10},
            'system_health': {'status': 'healthy'}
        }
        self.mock_alerts.check_thresholds.return_value = []
        self.mock_alerts.clear_resolved_alerts.return_value = []
        
        response = self.client.get('/api/metrics')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIn('data', data)
        self.assertIn('queue_depth', data['data'])

    def test_get_metrics_error(self):
        """Test metrics endpoint with error."""
        self.mock_collector.get_all_metrics.side_effect = Exception("DB Error")
        
        response = self.client.get('/api/metrics')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 500)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_get_specific_metric_queue_depth(self):
        """Test getting specific metric - queue_depth."""
        mock_metrics = Mock()
        mock_metrics.by_status = {'queued': 5}
        mock_metrics.by_priority = {'normal': 5}
        mock_metrics.total = 5
        self.mock_collector.queue_depth.return_value = mock_metrics
        
        response = self.client.get('/api/metrics/queue_depth')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['total'], 5)

    def test_get_specific_metric_stuck_tasks(self):
        """Test getting specific metric - stuck_tasks."""
        self.mock_collector.stuck_tasks.return_value = [
            {'id': 'task-1', 'status': 'executing'}
        ]
        
        response = self.client.get('/api/metrics/stuck_tasks')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['count'], 1)

    def test_get_specific_metric_cycle_time(self):
        """Test getting specific metric - cycle_time."""
        mock_cycle = Mock()
        mock_cycle.avg_seconds = 3600
        mock_cycle.median_seconds = 3000
        mock_cycle.p95_seconds = 7200
        mock_cycle.count = 10
        self.mock_collector.cycle_time.return_value = mock_cycle
        
        response = self.client.get('/api/metrics/cycle_time')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['avg_seconds'], 3600)

    def test_get_specific_metric_cycle_time_none(self):
        """Test getting cycle_time when no data."""
        self.mock_collector.cycle_time.return_value = None
        
        response = self.client.get('/api/metrics/cycle_time')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertIsNone(data['data']['avg_seconds'])

    def test_get_specific_metric_retry_rate(self):
        """Test getting specific metric - retry_rate."""
        self.mock_collector.retry_rate.return_value = {
            'total_tasks': 10,
            'retry_rate': 20.0
        }
        
        response = self.client.get('/api/metrics/retry_rate')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['retry_rate'], 20.0)

    def test_get_specific_metric_review_pass_fail(self):
        """Test getting specific metric - review_pass_fail."""
        mock_review = Mock()
        mock_review.total_reviews = 10
        mock_review.passed = 8
        mock_review.failed = 1
        mock_review.blocked = 1
        mock_review.pass_rate = 80.0
        mock_review.fail_rate = 10.0
        mock_review.block_rate = 10.0
        self.mock_collector.review_pass_fail.return_value = mock_review
        
        response = self.client.get('/api/metrics/review_pass_fail')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['pass_rate'], 80.0)

    def test_get_specific_metric_dead_letter(self):
        """Test getting specific metric - dead_letter."""
        self.mock_collector.dead_letter_count.return_value = {
            'total_count': 5,
            'recent_24h': 2
        }
        
        response = self.client.get('/api/metrics/dead_letter')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['total_count'], 5)

    def test_get_specific_metric_unknown(self):
        """Test getting unknown metric."""
        response = self.client.get('/api/metrics/unknown_metric')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 404)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    @patch('shared.db.execute')
    def test_get_tasks(self, mock_execute):
        """Test tasks endpoint."""
        mock_execute.return_value = [
            {'id': 'task-1', 'status': 'queued'},
            {'id': 'task-2', 'status': 'executing'}
        ]
        
        response = self.client.get('/api/tasks')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 2)

    @patch('shared.db.execute')
    def test_get_tasks_with_filters(self, mock_execute):
        """Test tasks endpoint with filters."""
        mock_execute.return_value = [
            {'id': 'task-1', 'status': 'queued'}
        ]
        
        response = self.client.get('/api/tasks?status=queued&limit=10')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])

    def test_get_audit_events(self):
        """Test audit events endpoint."""
        self.mock_collector.get_recent_audit_events.return_value = [
            {'id': 1, 'actor': 'openclaw', 'action': 'task.created'}
        ]
        
        response = self.client.get('/api/audit-events')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 1)

    def test_get_audit_events_with_filters(self):
        """Test audit events endpoint with filters."""
        self.mock_collector.get_recent_audit_events.return_value = []
        
        response = self.client.get('/api/audit-events?actor=openclaw&action=task.created&limit=5')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.mock_collector.get_recent_audit_events.assert_called_with(
            limit=5, actor='openclaw', action='task.created'
        )

    def test_get_alerts(self):
        """Test alerts endpoint."""
        from alerts import Alert, AlertSeverity
        
        mock_alert = Mock()
        mock_alert.rule_name = 'test_alert'
        mock_alert.severity = AlertSeverity.WARNING
        mock_alert.message = 'Test message'
        mock_alert.metric_value = 150
        mock_alert.threshold = 100
        mock_alert.timestamp = datetime.now(timezone.utc)
        mock_alert.acknowledged = False
        
        self.mock_alerts.get_active_alerts.return_value = [mock_alert]
        
        response = self.client.get('/api/alerts')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['alerts'][0]['rule_name'], 'test_alert')

    def test_acknowledge_alert(self):
        """Test acknowledging alert."""
        self.mock_alerts.acknowledge_alert.return_value = True
        
        response = self.client.post('/api/alerts/acknowledge',
                                   data=json.dumps({'rule_name': 'test_alert'}),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.mock_alerts.acknowledge_alert.assert_called_once_with('test_alert')

    def test_acknowledge_alert_missing_name(self):
        """Test acknowledging alert without rule_name."""
        response = self.client.post('/api/alerts/acknowledge',
                                   data=json.dumps({}),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('rule_name is required', data['error'])

    def test_get_alert_rules(self):
        """Test getting alert rules."""
        self.mock_alerts.export_rules.return_value = [
            {'name': 'rule1', 'metric': 'test', 'threshold': 100}
        ]
        
        response = self.client.get('/api/alerts/rules')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.assertEqual(len(data['rules']), 1)

    def test_add_alert_rule(self):
        """Test adding alert rule."""
        response = self.client.post('/api/alerts/rules',
                                   data=json.dumps({
                                       'name': 'new_rule',
                                       'metric': 'test.metric',
                                       'operator': '>',
                                       'threshold': 50,
                                       'severity': 'warning'
                                   }),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.mock_alerts.add_rule.assert_called_once()

    def test_add_alert_rule_missing_fields(self):
        """Test adding alert rule with missing fields."""
        response = self.client.post('/api/alerts/rules',
                                   data=json.dumps({'name': 'incomplete'}),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('Missing required field', data['error'])

    def test_delete_alert_rule(self):
        """Test deleting alert rule."""
        self.mock_alerts.remove_rule.return_value = True
        
        response = self.client.delete('/api/alerts/rules/test_rule')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        self.mock_alerts.remove_rule.assert_called_once_with('test_rule')

    def test_delete_nonexistent_rule(self):
        """Test deleting non-existent alert rule."""
        self.mock_alerts.remove_rule.return_value = False
        
        response = self.client.delete('/api/alerts/rules/nonexistent')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertFalse(data['success'])

    @patch('alerts.send_alert')
    def test_send_manual_alert(self, mock_send_alert):
        """Test sending manual alert."""
        mock_send_alert.return_value = True
        response = self.client.post('/api/send-alert',
                                   data=json.dumps({
                                       'message': 'Test alert',
                                       'severity': 'warning',
                                       'channel': 'webhook'
                                   }),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(data['success'])
        mock_send_alert.assert_called_once()

    def test_send_manual_alert_missing_message(self):
        """Test sending manual alert without message."""
        response = self.client.post('/api/send-alert',
                                   data=json.dumps({}),
                                   content_type='application/json')
        data = json.loads(response.data)
        
        self.assertEqual(response.status_code, 400)
        self.assertFalse(data['success'])
        self.assertIn('message is required', data['error'])


class TestDashboardConfiguration(unittest.TestCase):
    """Test dashboard configuration."""

    @patch.dict(os.environ, {'DASHBOARD_TITLE': 'Custom Title', 'DASHBOARD_REFRESH_INTERVAL': '30'})
    def test_environment_variables(self):
        """Test that environment variables are loaded."""
        # Need to reload module to pick up env vars
        import importlib
        import web_dashboard
        importlib.reload(web_dashboard)
        
        self.assertEqual(web_dashboard.DASHBOARD_TITLE, 'Custom Title')
        self.assertEqual(web_dashboard.REFRESH_INTERVAL, 30)


if __name__ == '__main__':
    unittest.main()
