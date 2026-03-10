#!/usr/bin/env python3
"""
Integration tests for n8n workflows.

Tests workflow connectivity, data flow, and business logic validity.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class WorkflowIntegrationTester:
    """Test workflow integration and business logic."""
    
    def __init__(self, workflows_dir: Path):
        self.workflows_dir = workflows_dir
        self.workflows: dict[str, dict] = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def load_all_workflows(self) -> None:
        """Load all workflow files."""
        for workflow_file in self.workflows_dir.glob('*.json'):
            try:
                with open(workflow_file, 'r') as f:
                    self.workflows[workflow_file.stem] = json.load(f)
            except json.JSONDecodeError as e:
                self.errors.append(f"{workflow_file.name}: Invalid JSON - {e}")
    
    def test_task_create_workflow(self) -> bool:
        """Test task-create workflow specific logic."""
        workflow = self.workflows.get('task-create')
        if not workflow:
            self.errors.append("task-create.json not found")
            return False
        
        success = True
        node_names = {n.get('name') for n in workflow.get('nodes', [])}
        
        # Check required nodes
        required_nodes = [
            'Webhook Trigger',
            'Validate Payload',
            'Insert Task to DB',
            'Log Audit Event',
            'Success Response',
            'Error Response',
            'Error Handler'
        ]
        
        for node in required_nodes:
            if node not in node_names:
                self.errors.append(f"task-create: Missing required node '{node}'")
                success = False
        
        # Check webhook path
        webhook_nodes = [n for n in workflow.get('nodes', []) 
                        if n.get('type') == 'n8n-nodes-base.webhook']
        if webhook_nodes:
            path = webhook_nodes[0].get('parameters', {}).get('path', '')
            if 'task/create' not in path:
                self.errors.append(f"task-create: Webhook path should contain 'task/create', got '{path}'")
                success = False
        
        return success
    
    def test_task_completed_workflow(self) -> bool:
        """Test task-completed workflow specific logic."""
        workflow = self.workflows.get('task-completed')
        if not workflow:
            self.errors.append("task-completed.json not found")
            return False
        
        success = True
        node_names = {n.get('name') for n in workflow.get('nodes', [])}
        
        # Check required nodes
        required_nodes = [
            'Webhook Trigger',
            'Update Task Status',
            'Create Review Task',
            'Insert Review Record'
        ]
        
        for node in required_nodes:
            if node not in node_names:
                self.errors.append(f"task-completed: Missing required node '{node}'")
                success = False
        
        # Check webhook path
        webhook_nodes = [n for n in workflow.get('nodes', []) 
                        if n.get('type') == 'n8n-nodes-base.webhook']
        if webhook_nodes:
            path = webhook_nodes[0].get('parameters', {}).get('path', '')
            if 'task/completed' not in path:
                self.errors.append(f"task-completed: Webhook path should contain 'task/completed', got '{path}'")
                success = False
        
        return success
    
    def test_review_report_workflow(self) -> bool:
        """Test review-report workflow specific logic."""
        workflow = self.workflows.get('review-report')
        if not workflow:
            self.errors.append("review-report.json not found")
            return False
        
        success = True
        node_names = {n.get('name') for n in workflow.get('nodes', [])}
        
        # Check required nodes for routing
        required_nodes = [
            'Route by Result',
            'Approve Task',
            'Reject Task',
            'Block Task'
        ]
        
        for node in required_nodes:
            if node not in node_names:
                self.errors.append(f"review-report: Missing required node '{node}'")
                success = False
        
        # Check webhook path
        webhook_nodes = [n for n in workflow.get('nodes', []) 
                        if n.get('type') == 'n8n-nodes-base.webhook']
        if webhook_nodes:
            path = webhook_nodes[0].get('parameters', {}).get('path', '')
            if 'review/report' not in path:
                self.errors.append(f"review-report: Webhook path should contain 'review/report', got '{path}'")
                success = False
        
        return success
    
    def test_audit_append_workflow(self) -> bool:
        """Test audit-append workflow specific logic."""
        workflow = self.workflows.get('audit-append')
        if not workflow:
            self.errors.append("audit-append.json not found")
            return False
        
        success = True
        node_names = {n.get('name') for n in workflow.get('nodes', [])}
        
        # Check required nodes
        if 'Insert Audit Event' not in node_names:
            self.errors.append("audit-append: Missing 'Insert Audit Event' node")
            success = False
        
        # Check for backup mechanism
        if 'Write Backup File' not in node_names:
            self.warnings.append("audit-append: Missing backup file writer")
        
        # Check webhook path
        webhook_nodes = [n for n in workflow.get('nodes', []) 
                        if n.get('type') == 'n8n-nodes-base.webhook']
        if webhook_nodes:
            path = webhook_nodes[0].get('parameters', {}).get('path', '')
            if 'audit/append' not in path:
                self.errors.append(f"audit-append: Webhook path should contain 'audit/append', got '{path}'")
                success = False
        
        return success
    
    def test_notification_send_workflow(self) -> bool:
        """Test notification-send workflow specific logic."""
        workflow = self.workflows.get('notification-send')
        if not workflow:
            self.errors.append("notification-send.json not found")
            return False
        
        success = True
        node_names = {n.get('name') for n in workflow.get('nodes', [])}
        
        # Check for channel handlers
        channel_nodes = [
            'Send Slack Message',
            'Send Discord Message',
            'Send Email',
            'Send Webhook'
        ]
        
        found_channels = [n for n in channel_nodes if n in node_names]
        if len(found_channels) < 2:
            self.warnings.append(f"notification-send: Only {len(found_channels)} channel handlers found")
        
        # Check for channel routing
        if 'Route by Channel' not in node_names:
            self.errors.append("notification-send: Missing 'Route by Channel' node")
            success = False
        
        # Check webhook path
        webhook_nodes = [n for n in workflow.get('nodes', []) 
                        if n.get('type') == 'n8n-nodes-base.webhook']
        if webhook_nodes:
            path = webhook_nodes[0].get('parameters', {}).get('path', '')
            if 'notification/send' not in path:
                self.errors.append(f"notification-send: Webhook path should contain 'notification/send', got '{path}'")
                success = False
        
        return success
    
    def test_workflow_interconnections(self) -> bool:
        """Test that workflows properly reference each other."""
        success = True
        
        # Check task-create calls notification-send
        task_create = self.workflows.get('task-create', {})
        nodes = task_create.get('nodes', [])
        exec_workflow_nodes = [n for n in nodes if n.get('type') == 'n8n-nodes-base.executeWorkflow']
        
        called_workflows = set()
        for node in exec_workflow_nodes:
            workflow_id = node.get('parameters', {}).get('workflowId', '')
            if workflow_id:
                called_workflows.add(workflow_id)
        
        # Check expected inter-workflow calls
        expected_calls = {
            'task-create': ['notification-send', 'audit-append'],
            'task-completed': ['notification-send', 'audit-append'],
            'review-report': ['notification-send', 'audit-append', 'task-create'],
            'notification-send': ['audit-append'],
        }
        
        for workflow_name, expected in expected_calls.items():
            workflow = self.workflows.get(workflow_name, {})
            nodes = workflow.get('nodes', [])
            exec_nodes = [n for n in nodes if n.get('type') == 'n8n-nodes-base.executeWorkflow']
            called = {n.get('parameters', {}).get('workflowId', '') for n in exec_nodes}
            
            for exp in expected:
                if exp not in called and exp != workflow_name:
                    self.warnings.append(
                        f"{workflow_name}: Should call '{exp}' workflow but doesn't"
                    )
        
        return success
    
    def run_all_tests(self) -> dict[str, Any]:
        """Run all integration tests."""
        self.load_all_workflows()
        
        results = {
            'task-create': self.test_task_create_workflow(),
            'task-completed': self.test_task_completed_workflow(),
            'review-report': self.test_review_report_workflow(),
            'audit-append': self.test_audit_append_workflow(),
            'notification-send': self.test_notification_send_workflow(),
            'interconnections': self.test_workflow_interconnections(),
        }
        
        return results


def main():
    """Main test runner."""
    workflows_dir = Path(__file__).parent.parent / 'workflows'
    
    print("=" * 70)
    print("n8n Workflow Integration Tests")
    print("=" * 70)
    
    tester = WorkflowIntegrationTester(workflows_dir)
    results = tester.run_all_tests()
    
    print("\n📋 Test Results:")
    print("-" * 70)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {test_name}")
        if not passed:
            all_passed = False
    
    print("\n" + "-" * 70)
    
    if tester.errors:
        print("\n❌ Errors:")
        for error in tester.errors:
            print(f"  • {error}")
    
    if tester.warnings:
        print("\n⚠️  Warnings:")
        for warning in tester.warnings:
            print(f"  • {warning}")
    
    print("\n" + "=" * 70)
    
    if all_passed and not tester.errors:
        print("✅ All integration tests PASSED")
        return 0
    else:
        print("❌ Some integration tests FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
