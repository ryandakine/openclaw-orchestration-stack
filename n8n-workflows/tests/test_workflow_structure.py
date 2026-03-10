#!/usr/bin/env python3
"""
Test suite for validating n8n workflow JSON structure.

This module validates that workflow JSON files conform to the expected
n8n workflow schema and contain all required components.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class WorkflowValidator:
    """Validator for n8n workflow JSON structure."""
    
    REQUIRED_NODE_FIELDS = ['id', 'name', 'type', 'typeVersion', 'position']
    VALID_NODE_TYPES = [
        'n8n-nodes-base.webhook',
        'n8n-nodes-base.code',
        'n8n-nodes-base.sqlite',
        'n8n-nodes-base.respondToWebhook',
        'n8n-nodes-base.executeWorkflow',
        'n8n-nodes-base.slack',
        'n8n-nodes-base.discord',
        'n8n-nodes-base.emailSend',
        'n8n-nodes-base.httpRequest',
        'n8n-nodes-base.writeBinaryFile',
    ]
    
    def __init__(self, workflow_path: Path):
        self.workflow_path = workflow_path
        self.workflow_data: dict = {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def load(self) -> bool:
        """Load and parse the workflow JSON file."""
        try:
            with open(self.workflow_path, 'r') as f:
                self.workflow_data = json.load(f)
            return True
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {e}")
            return False
        except FileNotFoundError:
            self.errors.append(f"File not found: {self.workflow_path}")
            return False
    
    def validate_structure(self) -> bool:
        """Validate basic workflow structure."""
        if not self.workflow_data:
            self.errors.append("Workflow data is empty")
            return False
        
        # Check required top-level fields
        required_fields = ['name', 'nodes', 'connections', 'settings']
        for field in required_fields:
            if field not in self.workflow_data:
                self.errors.append(f"Missing required field: {field}")
        
        # Validate nodes is a list
        if 'nodes' in self.workflow_data:
            if not isinstance(self.workflow_data['nodes'], list):
                self.errors.append("'nodes' must be a list")
            elif len(self.workflow_data['nodes']) == 0:
                self.errors.append("Workflow must have at least one node")
        
        # Validate connections is a dict
        if 'connections' in self.workflow_data:
            if not isinstance(self.workflow_data['connections'], dict):
                self.errors.append("'connections' must be an object")
        
        return len(self.errors) == 0
    
    def validate_nodes(self) -> bool:
        """Validate individual nodes."""
        nodes = self.workflow_data.get('nodes', [])
        node_ids = set()
        webhook_nodes = []
        
        for i, node in enumerate(nodes):
            node_name = node.get('name', f'Node_{i}')
            
            # Check required fields
            for field in self.REQUIRED_NODE_FIELDS:
                if field not in node:
                    self.errors.append(f"Node '{node_name}': Missing required field '{field}'")
            
            # Check for duplicate IDs
            node_id = node.get('id')
            if node_id:
                if node_id in node_ids:
                    self.errors.append(f"Node '{node_name}': Duplicate ID '{node_id}'")
                node_ids.add(node_id)
            
            # Track webhook nodes
            if node.get('type') == 'n8n-nodes-base.webhook':
                webhook_nodes.append(node)
                self._validate_webhook_node(node)
            
            # Track SQLite nodes for credential check
            if node.get('type') == 'n8n-nodes-base.sqlite':
                self._validate_sqlite_node(node)
            
            # Validate code nodes have jsCode
            if node.get('type') == 'n8n-nodes-base.code':
                params = node.get('parameters', {})
                if 'jsCode' not in params:
                    self.warnings.append(f"Node '{node_name}': Code node missing jsCode")
        
        # Check workflow has at least one webhook or trigger
        if not webhook_nodes:
            self.warnings.append("Workflow has no webhook trigger node")
        
        return len(self.errors) == 0
    
    def _validate_webhook_node(self, node: dict) -> None:
        """Validate webhook node configuration."""
        node_name = node.get('name', 'Unknown')
        params = node.get('parameters', {})
        
        if 'path' not in params:
            self.errors.append(f"Webhook node '{node_name}': Missing 'path' parameter")
        if 'httpMethod' not in params:
            self.errors.append(f"Webhook node '{node_name}': Missing 'httpMethod' parameter")
    
    def _validate_sqlite_node(self, node: dict) -> None:
        """Validate SQLite node has credentials."""
        node_name = node.get('name', 'Unknown')
        credentials = node.get('credentials', {})
        
        if 'sqlite' not in credentials:
            self.warnings.append(f"SQLite node '{node_name}': Missing sqlite credentials reference")
    
    def validate_connections(self) -> bool:
        """Validate node connections."""
        connections = self.workflow_data.get('connections', {})
        node_names = {n.get('name') for n in self.workflow_data.get('nodes', [])}
        
        # Check that all connected nodes exist
        for source_node, connection_list in connections.items():
            if source_node not in node_names and not source_node.endswith(':onError'):
                self.errors.append(f"Connection references unknown node: {source_node}")
            
            if isinstance(connection_list, list):
                for branch in connection_list:
                    if isinstance(branch, list):
                        for conn in branch:
                            if isinstance(conn, dict):
                                target = conn.get('node')
                                if target and target not in node_names:
                                    self.errors.append(
                                        f"Connection from '{source_node}' references unknown node: {target}"
                                    )
        
        return len(self.errors) == 0
    
    def validate_openclaw_standards(self) -> bool:
        """Validate OpenClaw-specific standards."""
        workflow_name = self.workflow_data.get('name', '')
        nodes = self.workflow_data.get('nodes', [])
        node_names = {n.get('name') for n in nodes}
        
        # Check for error handling nodes
        if 'Error Handler' not in node_names:
            self.warnings.append(f"Workflow '{workflow_name}': Missing 'Error Handler' node")
        
        # Check for audit logging
        if 'Log Audit Event' not in node_names:
            self.warnings.append(f"Workflow '{workflow_name}': Missing audit logging")
        
        # Check workflow has a tag
        tags = self.workflow_data.get('tags', [])
        if not tags:
            self.warnings.append(f"Workflow '{workflow_name}': Missing tags")
        else:
            tag_names = {t.get('name') for t in tags}
            if 'openclaw' not in tag_names:
                self.warnings.append(f"Workflow '{workflow_name}': Missing 'openclaw' tag")
        
        return len(self.errors) == 0
    
    def validate(self) -> tuple[bool, list[str], list[str]]:
        """Run all validations and return results."""
        if not self.load():
            return False, self.errors, self.warnings
        
        self.validate_structure()
        self.validate_nodes()
        self.validate_connections()
        self.validate_openclaw_standards()
        
        return len(self.errors) == 0, self.errors, self.warnings


def validate_all_workflows(workflows_dir: Path) -> dict[str, Any]:
    """Validate all workflow JSON files in a directory."""
    results = {
        'passed': [],
        'failed': [],
        'total': 0,
        'errors': {},
        'warnings': {}
    }
    
    workflow_files = list(workflows_dir.glob('*.json'))
    results['total'] = len(workflow_files)
    
    for workflow_file in workflow_files:
        print(f"\n  Validating: {workflow_file.name}...")
        validator = WorkflowValidator(workflow_file)
        is_valid, errors, warnings = validator.validate()
        
        if is_valid:
            results['passed'].append(workflow_file.name)
            print(f"    ✓ Passed ({len(warnings)} warnings)")
        else:
            results['failed'].append(workflow_file.name)
            print(f"    ✗ Failed ({len(errors)} errors, {len(warnings)} warnings)")
        
        if errors:
            results['errors'][workflow_file.name] = errors
            for error in errors:
                print(f"      ERROR: {error}")
        
        if warnings:
            results['warnings'][workflow_file.name] = warnings
            for warning in warnings:
                print(f"      WARNING: {warning}")
    
    return results


def validate_credentials_example(credentials_path: Path) -> tuple[bool, list[str]]:
    """Validate credentials example file."""
    errors = []
    
    try:
        with open(credentials_path, 'r') as f:
            creds = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
        return False, errors
    
    # Check for description fields
    if '_description' not in creds:
        errors.append("Missing _description field")
    if '_usage' not in creds:
        errors.append("Missing _usage field")
    
    # Check for sqlite-credentials
    if 'sqlite-credentials' not in creds:
        errors.append("Missing sqlite-credentials template")
    
    # Validate each credential has required fields
    for cred_name, cred_data in creds.items():
        if cred_name.startswith('_'):
            continue
        
        if not isinstance(cred_data, dict):
            errors.append(f"{cred_name}: Must be an object")
            continue
        
        if 'name' not in cred_data:
            errors.append(f"{cred_name}: Missing 'name' field")
        if 'type' not in cred_data:
            errors.append(f"{cred_name}: Missing 'type' field")
        if 'data' not in cred_data:
            errors.append(f"{cred_name}: Missing 'data' field")
    
    return len(errors) == 0, errors


def main():
    """Main test runner."""
    workflows_dir = Path(__file__).parent.parent / 'workflows'
    credentials_path = Path(__file__).parent.parent / 'credentials' / 'example.json'
    
    print("=" * 70)
    print("n8n Workflow Structure Validation")
    print("=" * 70)
    
    # Validate workflows
    print("\n📋 Validating Workflow Files...")
    results = validate_all_workflows(workflows_dir)
    
    # Validate credentials example
    print("\n📋 Validating Credentials Example...")
    creds_valid, creds_errors = validate_credentials_example(credentials_path)
    
    if creds_valid:
        print(f"  ✓ credentials/example.json is valid")
    else:
        print(f"  ✗ credentials/example.json has errors:")
        for error in creds_errors:
            print(f"    ERROR: {error}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total workflows: {results['total']}")
    print(f"Passed: {len(results['passed'])} ✓")
    print(f"Failed: {len(results['failed'])} ✗")
    
    if results['failed']:
        print(f"\nFailed workflows: {', '.join(results['failed'])}")
    
    # Exit with appropriate code
    if results['failed'] or not creds_valid:
        print("\n❌ Validation FAILED")
        return 1
    else:
        print("\n✅ Validation PASSED")
        return 0


if __name__ == '__main__':
    sys.exit(main())
