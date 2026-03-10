"""
Pytest configuration for dashboard tests.
"""

import os
import sys
import tempfile

# Add the dashboard directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def temp_db_path():
    """Provide a temporary database file path."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def mock_metrics():
    """Provide mock metrics data."""
    return {
        "queue_depth": {
            "by_status": {
                "queued": 5,
                "executing": 3,
                "review_queued": 2
            },
            "by_priority": {
                "high": 4,
                "normal": 6
            },
            "total": 10
        },
        "stuck_tasks": {
            "count": 2,
            "tasks": [
                {
                    "id": "task-1",
                    "status": "executing",
                    "stuck_reason": "lease_expired",
                    "minutes_stuck": 45.5
                }
            ]
        },
        "cycle_time": {
            "avg_seconds": 1800,
            "median_seconds": 1500,
            "p95_seconds": 3600,
            "count": 25
        },
        "retry_rate": {
            "total_tasks": 100,
            "retried_tasks": 10,
            "retry_rate": 10.0,
            "avg_retries": 1.5
        },
        "review_metrics": {
            "total_reviews": 20,
            "passed": 16,
            "failed": 3,
            "blocked": 1,
            "pass_rate": 80.0,
            "fail_rate": 15.0,
            "block_rate": 5.0
        },
        "dead_letter": {
            "total_count": 5,
            "recent_24h": 1
        },
        "system_health": {
            "status": "healthy",
            "total_tasks": 50,
            "active_tasks": 10,
            "stuck_tasks_count": 2,
            "error_rate": 5.0
        }
    }
