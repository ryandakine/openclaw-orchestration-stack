"""
Web Dashboard for OpenClaw Observability

Flask-based web UI providing real-time metrics, visualizations,
and alerting for the OpenClaw Orchestration Stack.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, render_template_string

# Import metrics collector and alerts
try:
    from .metrics_collector import MetricsCollector, get_collector
    from .alerts import get_alert_manager, AlertSeverity, AlertChannel, AlertRule
except ImportError:
    from metrics_collector import MetricsCollector, get_collector
    from alerts import get_alert_manager, AlertSeverity, AlertChannel, AlertRule


# Create Flask app
app = Flask(__name__, static_folder="static")
app.config["JSON_SORT_KEYS"] = False

# Get singleton instances
metrics_collector = get_collector()
alert_manager = get_alert_manager()

# Configuration
DASHBOARD_TITLE = os.environ.get("DASHBOARD_TITLE", "OpenClaw Observability Dashboard")
REFRESH_INTERVAL = int(os.environ.get("DASHBOARD_REFRESH_INTERVAL", "10"))


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


@app.route("/")
def index():
    """Main dashboard page."""
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/health")
def health_check():
    """Health check endpoint."""
    try:
        metrics = metrics_collector.get_all_metrics()
        health = metrics.get("system_health", {})
        
        status_code = 200
        if health.get("status") == "critical":
            status_code = 503
        elif health.get("status") == "degraded":
            status_code = 200  # Still up, but degraded
        
        return jsonify({
            "status": health.get("status", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0",
            "checks": {
                "database": "ok",
                "metrics": "available"
            }
        }), status_code
    except Exception as e:
        return jsonify({
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }), 503


@app.route("/api/metrics")
def get_metrics():
    """Get all system metrics."""
    try:
        metrics = metrics_collector.get_all_metrics()
        
        # Check for alerts
        alerts = alert_manager.check_thresholds(metrics)
        
        # Clear resolved alerts
        resolved = alert_manager.clear_resolved_alerts(metrics)
        
        return jsonify({
            "success": True,
            "data": metrics,
            "alerts_triggered": len(alerts),
            "alerts_resolved": len(resolved)
        })
    except Exception as e:
        app.logger.error(f"Error getting metrics: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/metrics/<metric_name>")
def get_specific_metric(metric_name: str):
    """Get a specific metric."""
    try:
        if metric_name == "queue_depth":
            result = metrics_collector.queue_depth()
            data = {
                "by_status": result.by_status,
                "by_priority": result.by_priority,
                "total": result.total
            }
        elif metric_name == "stuck_tasks":
            tasks = metrics_collector.stuck_tasks()
            data = {"count": len(tasks), "tasks": tasks}
        elif metric_name == "cycle_time":
            result = metrics_collector.cycle_time()
            data = {
                "avg_seconds": result.avg_seconds if result else None,
                "median_seconds": result.median_seconds if result else None,
                "p95_seconds": result.p95_seconds if result else None,
                "count": result.count if result else 0
            }
        elif metric_name == "retry_rate":
            data = metrics_collector.retry_rate()
        elif metric_name == "review_pass_fail":
            result = metrics_collector.review_pass_fail()
            data = {
                "total_reviews": result.total_reviews,
                "passed": result.passed,
                "failed": result.failed,
                "blocked": result.blocked,
                "pass_rate": result.pass_rate,
                "fail_rate": result.fail_rate,
                "block_rate": result.block_rate
            }
        elif metric_name == "dead_letter":
            data = metrics_collector.dead_letter_count()
        else:
            return jsonify({
                "success": False,
                "error": f"Unknown metric: {metric_name}"
            }), 404
        
        return jsonify({"success": True, "data": data})
    except Exception as e:
        app.logger.error(f"Error getting metric {metric_name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/tasks")
def get_tasks():
    """Get tasks with optional filtering."""
    try:
        status = request.args.get("status")
        limit = request.args.get("limit", 50, type=int)
        
        # Import here to avoid circular imports
        try:
            from shared.db import execute
        except ImportError:
            from metrics_collector import execute
        
        query = "SELECT * FROM tasks"
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        tasks = execute(query, tuple(params))
        
        return jsonify({
            "success": True,
            "count": len(tasks),
            "tasks": tasks
        })
    except Exception as e:
        app.logger.error(f"Error getting tasks: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/audit-events")
def get_audit_events():
    """Get recent audit events."""
    try:
        limit = request.args.get("limit", 50, type=int)
        actor = request.args.get("actor")
        action = request.args.get("action")
        
        events = metrics_collector.get_recent_audit_events(
            limit=limit,
            actor=actor,
            action=action
        )
        
        return jsonify({
            "success": True,
            "count": len(events),
            "events": events
        })
    except Exception as e:
        app.logger.error(f"Error getting audit events: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/alerts")
def get_alerts():
    """Get active alerts."""
    severity = request.args.get("severity")
    alert_severity = AlertSeverity(severity) if severity else None
    
    alerts = alert_manager.get_active_alerts(severity=alert_severity)
    
    return jsonify({
        "success": True,
        "count": len(alerts),
        "alerts": [
            {
                "rule_name": a.rule_name,
                "severity": a.severity.value,
                "message": a.message,
                "metric_value": a.metric_value,
                "threshold": a.threshold,
                "timestamp": a.timestamp.isoformat(),
                "acknowledged": a.acknowledged
            }
            for a in alerts
        ]
    })


@app.route("/api/alerts/acknowledge", methods=["POST"])
def acknowledge_alert():
    """Acknowledge an alert."""
    data = request.get_json() or {}
    rule_name = data.get("rule_name")
    
    if not rule_name:
        return jsonify({
            "success": False,
            "error": "rule_name is required"
        }), 400
    
    success = alert_manager.acknowledge_alert(rule_name)
    
    return jsonify({
        "success": success,
        "message": f"Alert {rule_name} acknowledged" if success else f"Alert {rule_name} not found"
    })


@app.route("/api/alerts/rules")
def get_alert_rules():
    """Get alert rules configuration."""
    return jsonify({
        "success": True,
        "rules": alert_manager.export_rules()
    })


@app.route("/api/alerts/rules", methods=["POST"])
def add_alert_rule():
    """Add a new alert rule."""
    data = request.get_json() or {}
    
    required_fields = ["name", "metric", "operator", "threshold", "severity"]
    for field in required_fields:
        if field not in data:
            return jsonify({
                "success": False,
                "error": f"Missing required field: {field}"
            }), 400
    
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
    
    alert_manager.add_rule(rule)
    
    return jsonify({
        "success": True,
        "message": f"Alert rule '{rule.name}' added"
    })


@app.route("/api/alerts/rules/<rule_name>", methods=["DELETE"])
def delete_alert_rule(rule_name: str):
    """Delete an alert rule."""
    success = alert_manager.remove_rule(rule_name)
    
    return jsonify({
        "success": success,
        "message": f"Alert rule '{rule_name}' deleted" if success else f"Alert rule '{rule_name}' not found"
    })


@app.route("/api/send-alert", methods=["POST"])
def send_manual_alert():
    """Send a manual alert."""
    data = request.get_json() or {}
    message = data.get("message")
    severity = data.get("severity", "info")
    channel = data.get("channel", "webhook")
    
    if not message:
        return jsonify({
            "success": False,
            "error": "message is required"
        }), 400
    
    try:
        from alerts import send_alert
        send_alert(
            message=message,
            severity=AlertSeverity(severity),
            channel=AlertChannel(channel)
        )
        return jsonify({
            "success": True,
            "message": "Alert sent"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# HTML Template for the dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ DASHBOARD_TITLE }}</title>
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🔍 OpenClaw Observability Dashboard</h1>
            <div class="header-controls">
                <button id="themeToggle" class="btn btn-secondary">🌙 Dark</button>
                <button id="refreshBtn" class="btn btn-primary">🔄 Refresh</button>
            </div>
        </header>
        
        <div class="status-bar">
            <span id="statusIndicator" class="status-badge status-unknown">Checking...</span>
            <span id="lastUpdate">Last updated: Never</span>
            <span id="autoRefresh">Auto-refresh: ON ({{ REFRESH_INTERVAL }}s)</span>
        </div>
        
        <!-- Alerts Panel -->
        <section id="alertsSection" class="alerts-panel hidden">
            <h2>🚨 Active Alerts</h2>
            <div id="alertsList" class="alerts-list"></div>
        </section>
        
        <!-- Metrics Grid -->
        <div class="metrics-grid">
            <!-- Queue Depth Gauge -->
            <div class="card">
                <h3>📊 Queue Depth</h3>
                <div class="gauge-container">
                    <canvas id="queueDepthChart"></canvas>
                </div>
                <div id="queueDepthStats" class="stats"></div>
            </div>
            
            <!-- Task Status Pie Chart -->
            <div class="card">
                <h3>📈 Task Status Distribution</h3>
                <div class="chart-container">
                    <canvas id="statusPieChart"></canvas>
                </div>
            </div>
            
            <!-- Cycle Time Trend -->
            <div class="card wide">
                <h3>⏱️ Cycle Time Trends</h3>
                <div class="chart-container">
                    <canvas id="cycleTimeChart"></canvas>
                </div>
                <div id="cycleTimeStats" class="stats"></div>
            </div>
            
            <!-- Stuck Tasks Alert Panel -->
            <div class="card wide" id="stuckTasksCard">
                <h3>⚠️ Stuck Tasks</h3>
                <div id="stuckTasksList" class="stuck-tasks-list">
                    <p class="empty">No stuck tasks detected</p>
                </div>
            </div>
            
            <!-- Review Metrics -->
            <div class="card">
                <h3>✅ Review Pass/Fail</h3>
                <div class="chart-container">
                    <canvas id="reviewChart"></canvas>
                </div>
                <div id="reviewStats" class="stats"></div>
            </div>
            
            <!-- System Health -->
            <div class="card">
                <h3>🏥 System Health</h3>
                <div id="healthStatus" class="health-status">
                    <div class="health-indicator health-unknown">Unknown</div>
                </div>
                <div id="healthStats" class="stats"></div>
            </div>
            
            <!-- Retry Rate -->
            <div class="card">
                <h3>🔄 Retry Rate</h3>
                <div id="retryRateStats" class="stats"></div>
            </div>
            
            <!-- Dead Letter Queue -->
            <div class="card">
                <h3>💀 Dead Letter Queue</h3>
                <div id="dlqStats" class="stats"></div>
            </div>
        </div>
        
        <!-- Recent Audit Events -->
        <section class="card wide">
            <h3>📋 Recent Audit Events</h3>
            <div class="table-container">
                <table id="auditTable">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Actor</th>
                            <th>Action</th>
                            <th>Correlation ID</th>
                        </tr>
                    </thead>
                    <tbody id="auditTableBody">
                        <tr><td colspan="4" class="empty">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
        
        <footer>
            <p>OpenClaw Observability Dashboard v1.0.0 | 
               <a href="/api/metrics">API</a> | 
               <a href="/api/health">Health</a></p>
        </footer>
    </div>
    
    <script src="/static/dashboard.js"></script>
    <script>
        // Initialize configuration
        window.DASHBOARD_CONFIG = {
            refreshInterval: {{ REFRESH_INTERVAL }},
            title: "{{ DASHBOARD_TITLE }}"
        };
    </script>
</body>
</html>
""".replace("{{ DASHBOARD_TITLE }}", DASHBOARD_TITLE).replace("{{ REFRESH_INTERVAL }}", str(REFRESH_INTERVAL))


def run_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the Flask development server."""
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    # Get configuration from environment
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    debug = os.environ.get("DASHBOARD_DEBUG", "false").lower() == "true"
    
    print(f"Starting OpenClaw Observability Dashboard on http://{host}:{port}")
    run_server(host=host, port=port, debug=debug)
