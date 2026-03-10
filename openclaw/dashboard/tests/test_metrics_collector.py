"""
Unit tests for the Metrics Collector module.
"""

import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

from metrics_collector import (
    MetricsCollector,
    QueueDepthMetrics,
    CycleTimeMetrics,
    ReviewMetrics,
    get_collector
)


class TestMetricsCollector(unittest.TestCase):
    """Test cases for MetricsCollector."""

    def setUp(self):
        """Set up test database."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix='.db')
        self.create_test_schema()
        self.collector = MetricsCollector(db_path=self.db_path)
        # Override the execute function to use test database
        self._setup_execute_override()

    def tearDown(self):
        """Clean up test database."""
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def _setup_execute_override(self):
        """Override the execute function to use test database."""
        import metrics_collector
        
        def test_execute(query, parameters=(), fetch_one=False):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                cursor = conn.execute(query, parameters)
                if fetch_one:
                    row = cursor.fetchone()
                    return dict(row) if row else None
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        
        self._original_execute = metrics_collector.execute
        metrics_collector.execute = test_execute
    
    def tearDown(self):
        """Clean up test database."""
        import metrics_collector
        metrics_collector.execute = self._original_execute
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def create_test_schema(self):
        """Create test database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                idempotency_key TEXT UNIQUE NOT NULL,
                status TEXT NOT NULL,
                assigned_to TEXT NOT NULL,
                claimed_by TEXT,
                claimed_at TIMESTAMP,
                lease_expires_at TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                intent TEXT NOT NULL,
                payload JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                requested_by TEXT,
                source TEXT
            );
            
            CREATE TABLE reviews (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                result TEXT NOT NULL,
                summary TEXT,
                findings JSON,
                reviewer_id TEXT,
                reviewer_role TEXT DEFAULT 'symphony',
                started_at TIMESTAMP,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                pr_comment_url TEXT
            );
            
            CREATE TABLE audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                correlation_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                payload JSON,
                ip_address TEXT,
                user_agent TEXT
            );
            
            CREATE TABLE dead_letter_tasks (
                id TEXT PRIMARY KEY,
                original_task_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT NOT NULL,
                error_details JSON,
                original_payload JSON
            );
        """)
        conn.commit()
        conn.close()

    def insert_task(self, task_id, status, **kwargs):
        """Helper to insert a task."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent, created_at, updated_at, completed_at, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id,
            kwargs.get('correlation_id', f'corr-{task_id}'),
            kwargs.get('idempotency_key', f'idem-{task_id}'),
            status,
            kwargs.get('assigned_to', 'DEVCLAW'),
            kwargs.get('intent', 'test'),
            kwargs.get('created_at', datetime.now().isoformat()),
            kwargs.get('updated_at', datetime.now().isoformat()),
            kwargs.get('completed_at'),
            kwargs.get('retry_count', 0)
        ))
        conn.commit()
        conn.close()

    def test_queue_depth_empty(self):
        """Test queue depth with no tasks."""
        metrics = self.collector.queue_depth()
        self.assertEqual(metrics.total, 0)
        self.assertEqual(metrics.by_status, {})

    def test_queue_depth_with_tasks(self):
        """Test queue depth with various tasks."""
        self.insert_task('task-1', 'queued')
        self.insert_task('task-2', 'executing')
        self.insert_task('task-3', 'review_queued')
        self.insert_task('task-4', 'approved')
        
        metrics = self.collector.queue_depth()
        self.assertEqual(metrics.total, 4)
        self.assertEqual(metrics.by_status['queued'], 1)
        self.assertEqual(metrics.by_status['executing'], 1)
        self.assertEqual(metrics.by_status['review_queued'], 1)
        self.assertEqual(metrics.by_status['approved'], 1)

    def test_stuck_tasks_empty(self):
        """Test stuck tasks with no tasks."""
        stuck = self.collector.stuck_tasks()
        self.assertEqual(len(stuck), 0)

    def test_stuck_tasks_detection(self):
        """Test detection of stuck tasks."""
        conn = sqlite3.connect(self.db_path)
        
        # Insert a task that should be detected as stuck
        old_time = (datetime.now() - timedelta(hours=1)).isoformat()
        conn.execute("""
            INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent, 
                             updated_at, claimed_by, lease_expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            'stuck-task-1',
            'corr-1',
            'idem-1',
            'executing',
            'DEVCLAW',
            'test',
            old_time,
            'worker-1',
            (datetime.now() - timedelta(minutes=30)).isoformat()
        ))
        conn.commit()
        conn.close()
        
        stuck = self.collector.stuck_tasks(threshold_minutes=30)
        self.assertGreaterEqual(len(stuck), 1)
        
        stuck_task = stuck[0]
        self.assertEqual(stuck_task['id'], 'stuck-task-1')
        self.assertEqual(stuck_task['status'], 'executing')
        self.assertEqual(stuck_task['stuck_reason'], 'lease_expired')

    def test_cycle_time_no_data(self):
        """Test cycle time with no completed tasks."""
        result = self.collector.cycle_time()
        self.assertIsNone(result)

    def test_cycle_time_with_data(self):
        """Test cycle time calculation."""
        now = datetime.now()
        
        # Insert completed tasks
        conn = sqlite3.connect(self.db_path)
        for i in range(5):
            created = (now - timedelta(hours=2)).isoformat()
            completed = (now - timedelta(hours=1)).isoformat()
            conn.execute("""
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, 
                                 intent, created_at, completed_at, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f'completed-task-{i}',
                f'corr-{i}',
                f'idem-{i}',
                'approved',
                'DEVCLAW',
                'test',
                created,
                completed,
                0
            ))
        conn.commit()
        conn.close()
        
        result = self.collector.cycle_time(hours=24)
        self.assertIsNotNone(result)
        self.assertEqual(result.count, 5)
        self.assertGreater(result.avg_seconds, 0)

    def test_retry_rate_empty(self):
        """Test retry rate with no tasks."""
        result = self.collector.retry_rate()
        self.assertEqual(result['total_tasks'], 0)
        self.assertEqual(result['retry_rate'], 0.0)

    def test_retry_rate_with_retries(self):
        """Test retry rate calculation."""
        # Insert tasks with and without retries
        self.insert_task('task-no-retry', 'completed', retry_count=0)
        self.insert_task('task-retry-1', 'completed', retry_count=1)
        self.insert_task('task-retry-2', 'completed', retry_count=2)
        
        result = self.collector.retry_rate(hours=24)
        self.assertEqual(result['total_tasks'], 3)
        self.assertEqual(result['retried_tasks'], 2)
        self.assertAlmostEqual(result['retry_rate'], 66.67, places=1)

    def test_review_pass_fail_empty(self):
        """Test review metrics with no reviews."""
        result = self.collector.review_pass_fail()
        self.assertEqual(result.total_reviews, 0)
        self.assertEqual(result.pass_rate, 0.0)

    def test_review_pass_fail_with_data(self):
        """Test review pass/fail calculation."""
        # Insert tasks first
        self.insert_task('task-1', 'approved')
        self.insert_task('task-2', 'failed')
        self.insert_task('task-3', 'blocked')
        
        conn = sqlite3.connect(self.db_path)
        # Insert reviews
        conn.execute("""
            INSERT INTO reviews (id, task_id, result, summary, reviewer_id, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('rev-1', 'task-1', 'approve', 'Good', 'symphony', datetime.now().isoformat()))
        conn.execute("""
            INSERT INTO reviews (id, task_id, result, summary, reviewer_id, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('rev-2', 'task-2', 'reject', 'Bad', 'symphony', datetime.now().isoformat()))
        conn.execute("""
            INSERT INTO reviews (id, task_id, result, summary, reviewer_id, completed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ('rev-3', 'task-3', 'blocked', 'Issues', 'symphony', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        result = self.collector.review_pass_fail(hours=24)
        self.assertEqual(result.total_reviews, 3)
        self.assertEqual(result.passed, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.blocked, 1)
        self.assertAlmostEqual(result.pass_rate, 33.33, places=1)

    def test_dead_letter_empty(self):
        """Test dead letter with no entries."""
        result = self.collector.dead_letter_count()
        self.assertEqual(result['total_count'], 0)
        self.assertEqual(result['recent_24h'], 0)

    def test_dead_letter_with_entries(self):
        """Test dead letter count."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO dead_letter_tasks (id, original_task_id, correlation_id, failed_at, reason)
            VALUES (?, ?, ?, ?, ?)
        """, ('dlq-1', 'task-1', 'corr-1', datetime.now().isoformat(), 'Max retries exceeded'))
        conn.execute("""
            INSERT INTO dead_letter_tasks (id, original_task_id, correlation_id, failed_at, reason)
            VALUES (?, ?, ?, ?, ?)
        """, ('dlq-2', 'task-2', 'corr-2', (datetime.now() - timedelta(days=2)).isoformat(), 'Error'))
        conn.commit()
        conn.close()
        
        result = self.collector.dead_letter_count()
        self.assertEqual(result['total_count'], 2)
        self.assertEqual(result['recent_24h'], 1)

    def test_get_all_metrics(self):
        """Test getting all metrics at once."""
        # Add some test data
        self.insert_task('task-1', 'queued')
        self.insert_task('task-2', 'executing')
        
        result = self.collector.get_all_metrics()
        
        self.assertIn('timestamp', result)
        self.assertIn('queue_depth', result)
        self.assertIn('stuck_tasks', result)
        self.assertIn('cycle_time', result)
        self.assertIn('retry_rate', result)
        self.assertIn('review_metrics', result)
        self.assertIn('dead_letter', result)
        self.assertIn('system_health', result)

    def test_get_recent_audit_events(self):
        """Test getting audit events."""
        conn = sqlite3.connect(self.db_path)
        for i in range(5):
            conn.execute("""
                INSERT INTO audit_events (correlation_id, actor, action, payload)
                VALUES (?, ?, ?, ?)
            """, (f'corr-{i}', 'openclaw', f'action-{i}', '{}'))
        conn.commit()
        conn.close()
        
        events = self.collector.get_recent_audit_events(limit=3)
        self.assertEqual(len(events), 3)

    def test_singleton_collector(self):
        """Test that get_collector returns singleton."""
        c1 = get_collector()
        c2 = get_collector()
        self.assertIs(c1, c2)


class TestMetricsClasses(unittest.TestCase):
    """Test data classes."""

    def test_queue_depth_metrics(self):
        """Test QueueDepthMetrics dataclass."""
        metrics = QueueDepthMetrics(
            by_status={'queued': 5, 'executing': 3},
            by_priority={'high': 4, 'normal': 4},
            total=8
        )
        self.assertEqual(metrics.total, 8)
        self.assertEqual(metrics.by_status['queued'], 5)

    def test_cycle_time_metrics(self):
        """Test CycleTimeMetrics dataclass."""
        metrics = CycleTimeMetrics(
            avg_seconds=3600,
            min_seconds=1800,
            max_seconds=7200,
            median_seconds=3600,
            p95_seconds=7000,
            count=10
        )
        self.assertEqual(metrics.avg_seconds, 3600)
        self.assertEqual(metrics.count, 10)

    def test_review_metrics(self):
        """Test ReviewMetrics dataclass."""
        metrics = ReviewMetrics(
            total_reviews=10,
            passed=7,
            failed=2,
            blocked=1,
            pass_rate=70.0,
            fail_rate=20.0,
            block_rate=10.0
        )
        self.assertEqual(metrics.total_reviews, 10)
        self.assertEqual(metrics.pass_rate, 70.0)


if __name__ == '__main__':
    unittest.main()
