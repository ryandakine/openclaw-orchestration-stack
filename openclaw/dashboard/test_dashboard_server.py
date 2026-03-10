#!/usr/bin/env python3
"""
Test script to verify the OpenClaw Observability Dashboard renders correctly.
Starts the Flask server and performs basic checks.
"""

import json
import sys
import threading
import time
import urllib.request


def start_test_server():
    """Start the Flask test server in a thread."""
    import os
    os.environ['FLASK_ENV'] = 'testing'
    
    from web_dashboard import app
    app.config['TESTING'] = True
    
    # Use werkzeug server for testing
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 5001, app)
    
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    
    return server


def test_dashboard():
    """Test the dashboard endpoints."""
    base_url = "http://127.0.0.1:5001"
    
    print("=" * 60)
    print("OpenClaw Observability Dashboard - Rendering Test")
    print("=" * 60)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Main dashboard page
    print("\n1. Testing main dashboard page (/)...")
    try:
        with urllib.request.urlopen(f"{base_url}/", timeout=5) as response:
            html = response.read().decode('utf-8')
            
            checks = [
                ("OpenClaw Observability Dashboard" in html, "Dashboard title"),
                ("<html" in html, "HTML structure"),
                ("dashboard.js" in html, "Dashboard JS reference"),
                ("style.css" in html, "CSS reference"),
                ("queueDepthChart" in html, "Queue depth chart element"),
                ("statusPieChart" in html, "Status pie chart element"),
                ("cycleTimeChart" in html, "Cycle time chart element"),
                ("reviewChart" in html, "Review chart element"),
                ("stuckTasksList" in html, "Stuck tasks element"),
                ("auditTable" in html, "Audit events table element"),
            ]
            
            for passed, description in checks:
                if passed:
                    print(f"   ✓ {description}")
                    tests_passed += 1
                else:
                    print(f"   ✗ {description}")
                    tests_failed += 1
    except Exception as e:
        print(f"   ✗ Failed to load dashboard: {e}")
        tests_failed += 1
    
    # Test 2: Health check endpoint
    print("\n2. Testing health check endpoint (/api/health)...")
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            checks = [
                ("status" in data, "Status field"),
                ("timestamp" in data, "Timestamp field"),
                ("version" in data, "Version field"),
                ("checks" in data, "Checks field"),
            ]
            
            for passed, description in checks:
                if passed:
                    print(f"   ✓ {description}")
                    tests_passed += 1
                else:
                    print(f"   ✗ {description}")
                    tests_failed += 1
            
            print(f"   Status: {data.get('status', 'unknown')}")
    except Exception as e:
        print(f"   ✗ Failed to get health: {e}")
        tests_failed += 1
    
    # Test 3: Metrics endpoint
    print("\n3. Testing metrics endpoint (/api/metrics)...")
    try:
        with urllib.request.urlopen(f"{base_url}/api/metrics", timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            checks = [
                (data.get("success") == True, "Success flag"),
                ("data" in data, "Data field"),
            ]
            
            for passed, description in checks:
                if passed:
                    print(f"   ✓ {description}")
                    tests_passed += 1
                else:
                    print(f"   ✗ {description}")
                    tests_failed += 1
            
            if "data" in data:
                metrics_checks = [
                    ("queue_depth" in data["data"], "Queue depth metric"),
                    ("stuck_tasks" in data["data"], "Stuck tasks metric"),
                    ("cycle_time" in data["data"], "Cycle time metric"),
                    ("retry_rate" in data["data"], "Retry rate metric"),
                    ("review_metrics" in data["data"], "Review metrics"),
                    ("dead_letter" in data["data"], "Dead letter metric"),
                    ("system_health" in data["data"], "System health metric"),
                ]
                
                for passed, description in metrics_checks:
                    if passed:
                        print(f"   ✓ {description}")
                        tests_passed += 1
                    else:
                        print(f"   ✗ {description}")
                        tests_failed += 1
    except Exception as e:
        print(f"   ✗ Failed to get metrics: {e}")
        tests_failed += 1
    
    # Test 4: Alert rules endpoint
    print("\n4. Testing alert rules endpoint (/api/alerts/rules)...")
    try:
        with urllib.request.urlopen(f"{base_url}/api/alerts/rules", timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            checks = [
                (data.get("success") == True, "Success flag"),
                ("rules" in data, "Rules field"),
                (isinstance(data.get("rules"), list), "Rules is a list"),
            ]
            
            for passed, description in checks:
                if passed:
                    print(f"   ✓ {description}")
                    tests_passed += 1
                else:
                    print(f"   ✗ {description}")
                    tests_failed += 1
            
            if "rules" in data and isinstance(data["rules"], list):
                print(f"   Total rules: {len(data['rules'])}")
    except Exception as e:
        print(f"   ✗ Failed to get alert rules: {e}")
        tests_failed += 1
    
    # Test 5: Static files
    print("\n5. Testing static file serving...")
    static_files = [
        ("/static/style.css", "CSS"),
        ("/static/dashboard.js", "JavaScript"),
    ]
    
    for path, description in static_files:
        try:
            with urllib.request.urlopen(f"{base_url}{path}", timeout=5) as response:
                content = response.read().decode('utf-8')
                if len(content) > 100:  # Basic size check
                    print(f"   ✓ {description} file served ({len(content)} bytes)")
                    tests_passed += 1
                else:
                    print(f"   ✗ {description} file too small")
                    tests_failed += 1
        except Exception as e:
            print(f"   ✗ Failed to load {description}: {e}")
            tests_failed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Test Results: {tests_passed} passed, {tests_failed} failed")
    print("=" * 60)
    
    return tests_failed == 0


def main():
    """Main entry point."""
    print("\nStarting test server...")
    
    # Mock the metrics collector and alert manager for testing
    import unittest.mock as mock
    
    with mock.patch('web_dashboard.metrics_collector') as mock_collector, \
         mock.patch('web_dashboard.alert_manager') as mock_alerts:
        
        # Configure mocks
        mock_collector.get_all_metrics.return_value = {
            "timestamp": "2025-03-07T12:00:00",
            "queue_depth": {
                "by_status": {"queued": 5, "executing": 3, "review_queued": 2},
                "by_priority": {"high": 4, "normal": 6},
                "total": 10
            },
            "stuck_tasks": {"count": 1, "tasks": []},
            "cycle_time": {"avg_seconds": 1800, "median_seconds": 1500, "p95_seconds": 3600, "count": 25},
            "retry_rate": {"total_tasks": 100, "retried_tasks": 10, "retry_rate": 10.0, "avg_retries": 1.5, "max_retries": 3, "high_retry_rate": 2.0},
            "review_metrics": {
                "total_reviews": 20, "passed": 16, "failed": 3, "blocked": 1,
                "pass_rate": 80.0, "fail_rate": 15.0, "block_rate": 5.0
            },
            "dead_letter": {"total_count": 5, "recent_24h": 1, "recent_entries": []},
            "system_health": {
                "status": "healthy", "total_tasks": 50, "active_tasks": 10,
                "stuck_tasks_count": 1, "failed_tasks_count": 2,
                "dead_letter_count": 5, "avg_cycle_time_seconds": 1800,
                "error_rate": 5.0
            }
        }
        
        mock_collector.get_recent_audit_events.return_value = [
            {"id": 1, "timestamp": "2025-03-07T12:00:00", "actor": "openclaw", "action": "task.created", "correlation_id": "corr-1"},
            {"id": 2, "timestamp": "2025-03-07T11:00:00", "actor": "devclaw", "action": "task.completed", "correlation_id": "corr-2"},
        ]
        
        mock_alerts.export_rules.return_value = [
            {"name": "high_queue_depth", "metric": "queue_depth.total", "threshold": 100, "severity": "warning"},
            {"name": "stuck_tasks_warning", "metric": "stuck_tasks.count", "threshold": 10, "severity": "warning"},
        ]
        
        mock_alerts.check_thresholds.return_value = []
        mock_alerts.clear_resolved_alerts.return_value = []
        mock_alerts.get_active_alerts.return_value = []
        
        # Start server
        server = start_test_server()
        print("Test server started on http://127.0.0.1:5001")
        
        # Wait for server to be ready
        time.sleep(1)
        
        try:
            success = test_dashboard()
        finally:
            server.shutdown()
        
        if success:
            print("\n✓ All tests passed!")
            return 0
        else:
            print("\n✗ Some tests failed!")
            return 1


if __name__ == "__main__":
    sys.exit(main())
