"""
n8n Workflow Tests Package

This package contains tests for validating n8n workflow JSON files
for the OpenClaw Orchestration Stack.

Test Files:
    - test_workflow_structure.py: Validates workflow JSON structure
    - test_workflow_integration.py: Tests workflow interconnections
    - test_json_validity.py: Validates JSON syntax
    - run_all_tests.sh: Shell script to run all tests

Usage:
    # Run all tests
    bash tests/run_all_tests.sh
    
    # Run individual test
    python3 tests/test_workflow_structure.py
    
    # Run with pytest (if available)
    pytest tests/
"""

__version__ = "1.0.0"
__all__ = [
    'WorkflowValidator',
    'WorkflowIntegrationTester',
]


try:
    from .test_workflow_structure import WorkflowValidator
    from .test_workflow_integration import WorkflowIntegrationTester
except ImportError:
    # Allow importing when running directly
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_workflow_structure import WorkflowValidator
    from test_workflow_integration import WorkflowIntegrationTester
