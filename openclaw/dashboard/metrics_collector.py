"""
Metrics Collector for OpenClaw Observability Dashboard

Collects and aggregates metrics from the SQLite database for monitoring
the health and performance of the orchestration stack.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# Import shared database utilities
try:
    from shared.db import get_connection, execute
except ImportError:
    # Fallback for standalone usage
    import sqlite3

    DEFAULT_DB_PATH = os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")

    def get_connection():
        """Get a database connection."""
        conn = sqlite3.connect(DEFAULT_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(query: str, parameters: Tuple = (), fetch_one: bool = False):
        """Execute a query and return results."""
        conn = get_connection()
        try:
            cursor = conn.execute(query, parameters)
            if fetch_one:
                row = cursor.fetchone()
                return dict(row) if row else None
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


@dataclass
class QueueDepthMetrics:
    """Queue depth metrics by status and priority."""
    by_status: Dict[str, int]
    by_priority: Dict[str, int]
    total: int


@dataclass
class CycleTimeMetrics:
    """Task cycle time metrics."""
    avg_seconds: float
    min_seconds: float
    max_seconds: float
    median_seconds: float
    p95_seconds: float
    count: int


@dataclass
class ReviewMetrics:
    """Review pass/fail metrics."""
    total_reviews: int
    passed: int
    failed: int
    blocked: int
    pass_rate: float
    fail_rate: float
    block_rate: float


@dataclass
class SystemHealth:
    """Overall system health metrics."""
    status: str  # "healthy", "degraded", "critical"
    total_tasks: int
    active_tasks: int
    stuck_tasks_count: int
    failed_tasks_count: int
    dead_letter_count: int
    avg_cycle_time_seconds: float
    error_rate: float


class MetricsCollector:
    """Collector for OpenClaw system metrics."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the metrics collector.
        
        Args:
            db_path: Path to the SQLite database. Uses env var OPENCLAW_DB_PATH or default.
        """
        self.db_path = db_path or os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")

    def queue_depth(self) -> QueueDepthMetrics:
        """Get current queue depth metrics.
        
        Returns:
            QueueDepthMetrics with breakdown by status and priority.
        """
        # Count by status
        status_query = """
            SELECT status, COUNT(*) as count
            FROM tasks
            GROUP BY status
        """
        status_results = execute(status_query)
        by_status = {row["status"]: row["count"] for row in status_results}

        # Try to get priority from payload JSON if available
        priority_query = """
            SELECT 
                COALESCE(
                    json_extract(payload, '$.priority'),
                    'normal'
                ) as priority,
                COUNT(*) as count
            FROM tasks
            WHERE status IN ('queued', 'executing', 'review_queued')
            GROUP BY priority
        """
        try:
            priority_results = execute(priority_query)
            by_priority = {row["priority"]: row["count"] for row in priority_results}
        except Exception:
            # Fallback if json_extract fails
            by_priority = {"unknown": sum(by_status.get(s, 0) for s in ["queued", "executing", "review_queued"])}

        total = sum(by_status.values())

        return QueueDepthMetrics(
            by_status=by_status,
            by_priority=by_priority,
            total=total
        )

    def stuck_tasks(self, threshold_minutes: int = 30) -> List[Dict[str, Any]]:
        """Get tasks that appear to be stuck.
        
        Tasks are considered stuck if they:
        - Are in 'executing' or 'review_queued' status
        - Have a claim that expired
        - Or haven't been updated in threshold_minutes
        
        Args:
            threshold_minutes: Minutes without update to consider a task stuck
            
        Returns:
            List of stuck task records.
        """
        query = """
            SELECT 
                t.id,
                t.status,
                t.assigned_to,
                t.claimed_by,
                t.claimed_at,
                t.lease_expires_at,
                t.updated_at,
                t.retry_count,
                t.intent,
                t.correlation_id,
                t.created_at,
                CASE 
                    WHEN t.lease_expires_at < datetime('now') THEN 'lease_expired'
                    WHEN t.updated_at < datetime('now', ?) THEN 'stale'
                    ELSE 'unknown'
                END as stuck_reason,
                ROUND(
                    (julianday('now') - julianday(COALESCE(t.updated_at, t.created_at))) * 24 * 60,
                    2
                ) as minutes_stuck
            FROM tasks t
            WHERE t.status IN ('executing', 'review_queued')
              AND (
                  t.lease_expires_at < datetime('now')
                  OR t.updated_at < datetime('now', ?)
              )
            ORDER BY t.updated_at ASC
        """
        offset = f"-{threshold_minutes} minutes"
        return execute(query, (offset, offset))

    def cycle_time(
        self,
        start_status: str = "queued",
        end_status: str = "approved",
        hours: int = 24
    ) -> Optional[CycleTimeMetrics]:
        """Calculate cycle time metrics from start_status to end_status.
        
        Args:
            start_status: Initial task status
            end_status: Final task status
            hours: Lookback period in hours
            
        Returns:
            CycleTimeMetrics or None if no data.
        """
        query = """
            SELECT 
                t.id,
                t.created_at as start_time,
                t.completed_at as end_time,
                ROUND(
                    (julianday(t.completed_at) - julianday(t.created_at)) * 24 * 60 * 60,
                    2
                ) as cycle_seconds
            FROM tasks t
            WHERE t.status = ?
              AND t.completed_at IS NOT NULL
              AND t.completed_at >= datetime('now', ?)
            ORDER BY cycle_seconds
        """
        offset = f"-{hours} hours"
        results = execute(query, (end_status, offset))

        if not results:
            return None

        cycle_times = [row["cycle_seconds"] for row in results if row["cycle_seconds"] is not None]
        
        if not cycle_times:
            return None

        cycle_times.sort()
        count = len(cycle_times)
        avg_sec = sum(cycle_times) / count
        min_sec = cycle_times[0]
        max_sec = cycle_times[-1]
        median_sec = cycle_times[count // 2] if count % 2 == 1 else (
            cycle_times[count // 2 - 1] + cycle_times[count // 2]
        ) / 2
        p95_idx = int(count * 0.95)
        p95_sec = cycle_times[min(p95_idx, count - 1)]

        return CycleTimeMetrics(
            avg_seconds=avg_sec,
            min_seconds=min_sec,
            max_seconds=max_sec,
            median_seconds=median_sec,
            p95_seconds=p95_sec,
            count=count
        )

    def retry_rate(self, hours: int = 24) -> Dict[str, Any]:
        """Calculate task retry rate metrics.
        
        Args:
            hours: Lookback period in hours
            
        Returns:
            Dictionary with retry metrics.
        """
        query = """
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN retry_count > 0 THEN 1 ELSE 0 END) as retried_tasks,
                AVG(retry_count) as avg_retries,
                MAX(retry_count) as max_retries,
                SUM(CASE WHEN retry_count >= 3 THEN 1 ELSE 0 END) as high_retry_tasks
            FROM tasks
            WHERE created_at >= datetime('now', ?)
        """
        offset = f"-{hours} hours"
        result = execute(query, (offset,), fetch_one=True)

        if not result or result["total_tasks"] == 0:
            return {
                "total_tasks": 0,
                "retried_tasks": 0,
                "retry_rate": 0.0,
                "avg_retries": 0.0,
                "max_retries": 0,
                "high_retry_rate": 0.0
            }

        total = result["total_tasks"]
        retried = result["retried_tasks"]

        return {
            "total_tasks": total,
            "retried_tasks": retried,
            "retry_rate": round(retried / total * 100, 2),
            "avg_retries": round(result["avg_retries"] or 0, 2),
            "max_retries": result["max_retries"],
            "high_retry_rate": round((result["high_retry_tasks"] or 0) / total * 100, 2)
        }

    def review_pass_fail(self, hours: int = 24) -> ReviewMetrics:
        """Calculate review pass/fail statistics.
        
        Args:
            hours: Lookback period in hours
            
        Returns:
            ReviewMetrics with pass/fail counts and rates.
        """
        query = """
            SELECT 
                result,
                COUNT(*) as count
            FROM reviews
            WHERE completed_at >= datetime('now', ?)
            GROUP BY result
        """
        offset = f"-{hours} hours"
        results = execute(query, (offset,))

        counts = {"approve": 0, "reject": 0, "blocked": 0}
        for row in results:
            if row["result"] in counts:
                counts[row["result"]] = row["count"]

        total = sum(counts.values())

        if total == 0:
            return ReviewMetrics(
                total_reviews=0,
                passed=0,
                failed=0,
                blocked=0,
                pass_rate=0.0,
                fail_rate=0.0,
                block_rate=0.0
            )

        return ReviewMetrics(
            total_reviews=total,
            passed=counts["approve"],
            failed=counts["reject"],
            blocked=counts["blocked"],
            pass_rate=round(counts["approve"] / total * 100, 2),
            fail_rate=round(counts["reject"] / total * 100, 2),
            block_rate=round(counts["blocked"] / total * 100, 2)
        )

    def dead_letter_count(self) -> Dict[str, Any]:
        """Get dead letter queue statistics.
        
        Returns:
            Dictionary with dead letter counts and recent entries.
        """
        # Total count
        count_result = execute(
            "SELECT COUNT(*) as count FROM dead_letter_tasks",
            fetch_one=True
        )
        total = count_result["count"] if count_result else 0

        # Recent failures (last 24 hours)
        recent_query = """
            SELECT COUNT(*) as count 
            FROM dead_letter_tasks 
            WHERE failed_at >= datetime('now', '-24 hours')
        """
        recent_result = execute(recent_query, fetch_one=True)
        recent = recent_result["count"] if recent_result else 0

        # Recent entries
        entries_query = """
            SELECT 
                id,
                original_task_id,
                correlation_id,
                failed_at,
                reason,
                error_details
            FROM dead_letter_tasks
            ORDER BY failed_at DESC
            LIMIT 10
        """
        recent_entries = execute(entries_query)

        return {
            "total_count": total,
            "recent_24h": recent,
            "recent_entries": recent_entries
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics in a single call.
        
        Returns:
            Dictionary containing all system metrics.
        """
        queue_metrics = self.queue_depth()
        stuck = self.stuck_tasks()
        cycle_time_metrics = self.cycle_time()
        retry_metrics = self.retry_rate()
        review_metrics = self.review_pass_fail()
        dlq = self.dead_letter_count()

        # Calculate system health
        active_tasks = sum(
            queue_metrics.by_status.get(s, 0) 
            for s in ["queued", "executing", "review_queued"]
        )
        failed_tasks = queue_metrics.by_status.get("failed", 0)
        
        error_rate = 0.0
        total_completed = review_metrics.total_reviews
        if total_completed > 0:
            error_rate = (review_metrics.failed + review_metrics.blocked) / total_completed

        # Determine health status
        if dlq["recent_24h"] > 10 or len(stuck) > 20 or error_rate > 0.5:
            health_status = "critical"
        elif dlq["recent_24h"] > 5 or len(stuck) > 10 or error_rate > 0.3:
            health_status = "degraded"
        else:
            health_status = "healthy"

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "queue_depth": {
                "by_status": queue_metrics.by_status,
                "by_priority": queue_metrics.by_priority,
                "total": queue_metrics.total
            },
            "stuck_tasks": {
                "count": len(stuck),
                "tasks": stuck[:10]  # Limit to first 10
            },
            "cycle_time": {
                "avg_seconds": cycle_time_metrics.avg_seconds if cycle_time_metrics else None,
                "median_seconds": cycle_time_metrics.median_seconds if cycle_time_metrics else None,
                "p95_seconds": cycle_time_metrics.p95_seconds if cycle_time_metrics else None,
                "count": cycle_time_metrics.count if cycle_time_metrics else 0
            },
            "retry_rate": retry_metrics,
            "review_metrics": {
                "total_reviews": review_metrics.total_reviews,
                "passed": review_metrics.passed,
                "failed": review_metrics.failed,
                "blocked": review_metrics.blocked,
                "pass_rate": review_metrics.pass_rate,
                "fail_rate": review_metrics.fail_rate,
                "block_rate": review_metrics.block_rate
            },
            "dead_letter": dlq,
            "system_health": {
                "status": health_status,
                "total_tasks": queue_metrics.total,
                "active_tasks": active_tasks,
                "stuck_tasks_count": len(stuck),
                "failed_tasks_count": failed_tasks,
                "dead_letter_count": dlq["total_count"],
                "avg_cycle_time_seconds": cycle_time_metrics.avg_seconds if cycle_time_metrics else 0,
                "error_rate": round(error_rate * 100, 2)
            }
        }

    def get_recent_audit_events(
        self,
        limit: int = 50,
        actor: Optional[str] = None,
        action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent audit events.
        
        Args:
            limit: Maximum number of events to return
            actor: Filter by actor (optional)
            action: Filter by action (optional)
            
        Returns:
            List of audit event records.
        """
        conditions = []
        params = []
        
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        if action:
            conditions.append("action = ?")
            params.append(action)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT 
                id,
                correlation_id,
                timestamp,
                actor,
                action,
                payload,
                ip_address,
                user_agent
            FROM audit_events
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        params.append(limit)
        
        return execute(query, tuple(params))


# Singleton instance for convenience
_collector: Optional[MetricsCollector] = None


def get_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector
