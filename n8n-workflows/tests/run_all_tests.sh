#!/bin/bash
#
# Run all n8n workflow tests
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=========================================="
echo "OpenClaw n8n Workflow Tests"
echo "=========================================="
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not installed"
    exit 1
fi

# Run structure tests
echo "Running structure tests..."
echo "------------------------------------------"
python3 "$SCRIPT_DIR/test_workflow_structure.py"
STRUCTURE_EXIT=$?
echo ""

# Run integration tests
echo "Running integration tests..."
echo "------------------------------------------"
python3 "$SCRIPT_DIR/test_workflow_integration.py"
INTEGRATION_EXIT=$?
echo ""

# Run JSON validation
echo "Running JSON validation..."
echo "------------------------------------------"
python3 "$SCRIPT_DIR/test_json_validity.py"
JSON_EXIT=$?
echo ""

# Summary
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo "Structure tests:   $([ $STRUCTURE_EXIT -eq 0 ] && echo 'PASS ✓' || echo 'FAIL ✗')"
echo "Integration tests: $([ $INTEGRATION_EXIT -eq 0 ] && echo 'PASS ✓' || echo 'FAIL ✗')"
echo "JSON validity:     $([ $JSON_EXIT -eq 0 ] && echo 'PASS ✓' || echo 'FAIL ✗')"
echo ""

# Final exit code
if [ $STRUCTURE_EXIT -eq 0 ] && [ $INTEGRATION_EXIT -eq 0 ] && [ $JSON_EXIT -eq 0 ]; then
    echo "✅ All tests PASSED"
    exit 0
else
    echo "❌ Some tests FAILED"
    exit 1
fi
