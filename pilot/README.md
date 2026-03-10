# OpenClaw Python Pilot

This directory contains a complete Python demonstration of the OpenClaw Orchestration Stack.

## Overview

The Python Pilot demonstrates how OpenClaw processes a real Python repository through the complete automation workflow. It includes:

1. **A sample Python project** (`python-demo-repo/`) with:
   - Calculator module with comprehensive functionality
   - Full pytest test suite
   - Python-specific OpenClaw configuration
   - Three test scenarios (feature addition, bug fix, refactoring)

2. **Pilot test suite** (`test_python_pilot.py`) that verifies:
   - Repository structure validation
   - Review configuration parsing
   - Intent classification
   - Routing decisions
   - Action plan generation
   - Command execution
   - End-to-end workflow simulation

## Directory Structure

```
pilot/
├── README.md                       # This file
├── test_python_pilot.py            # Pilot test suite (38 tests)
└── python-demo-repo/               # Demo Python project
    ├── calculator.py               # Calculator implementation
    ├── test_calculator.py          # pytest test suite (36 tests)
    ├── requirements.txt            # Python dependencies
    ├── .openclaw/
    │   └── review.yaml             # OpenClaw configuration
    ├── scenario1/                  # Feature addition scenario
    │   ├── README.md
    │   └── calculator_patch.py
    ├── scenario2/                  # Bug fix scenario
    │   ├── README.md
    │   └── bugfix_patch.py
    └── scenario3/                  # Refactoring scenario
        ├── README.md
        └── refactor_patch.py
```

## Quick Start

### Run the Calculator Tests

```bash
cd pilot/python-demo-repo
python3 -m pytest test_calculator.py -v
```

### Run the Pilot Tests

```bash
# From project root
python3 -m pytest pilot/test_python_pilot.py -v
```

### Run All Tests

```bash
# From project root
python3 -m pytest pilot/ -v
```

## Test Scenarios

### Scenario 1: Feature Addition
- **Intent**: Add factorial method to Calculator
- **Classification**: `feature_request`
- **Routes to**: DEVCLAW
- **Action Type**: `code_generation`

### Scenario 2: Bug Fix
- **Intent**: Fix return type hint in square_root method
- **Classification**: `bug_report`
- **Routes to**: DEVCLAW
- **Action Type**: `bug_fix`

### Scenario 3: Refactoring
- **Intent**: Refactor Calculator for better code organization
- **Classification**: `code_improvement`
- **Routes to**: DEVCLAW
- **Action Type**: `refactoring`

## OpenClaw Configuration

The `.openclaw/review.yaml` file configures the review process:

```yaml
repo:
  language: python
  profile_default: STANDARD

commands:
  test:
    - "pytest -q"
  lint:
    - "ruff check ."
    - "black --check ."
  typecheck:
    - "mypy ."

security:
  dependency_scan:
    - "pip-audit -r requirements.txt"
```

## End-to-End Flow Demonstration

The pilot tests demonstrate the full OpenClaw flow:

```
1. Request Received (Intent Classification)
   └─ classify_intent() → IntentClassification

2. Routing Decision
   └─ route_to() → RoutingDecision

3. Action Plan Generation
   └─ create_action_plan() → ActionPlan

4. Task Execution (Mocked DEVCLAW)
   └─ CommandRunner.execute()

5. Validation
   └─ pytest, ruff, black, mypy

6. Review Queue (SYMPHONY)
   └─ Review findings

7. Resolution
   └─ Pass → Merge / Fail → Remediation
```

## Test Coverage

### Pilot Tests (38 tests)

| Test Category | Count | Description |
|---------------|-------|-------------|
| Repository Structure | 7 | File existence, syntax validation |
| Review Configuration | 8 | Config loading, validation |
| Intent Classification | 3 | Scenario classification |
| OpenClaw Routing | 3 | Routing decisions |
| Action Plan Generation | 3 | Plan creation |
| Command Runner | 3 | Command execution |
| End-to-End Flow | 3 | Full workflow tests |
| Mocked Integration | 3 | Component mocking |
| Scenario Execution | 4 | Patch validation |
| Summary | 1 | Documentation test |

### Calculator Tests (36 tests)

| Test Category | Count | Description |
|---------------|-------|-------------|
| Basic Operations | 7 | add, subtract |
| Multiplication/Division | 7 | multiply, divide |
| Advanced Operations | 7 | power, square_root |
| Average | 6 | List averaging |
| Edge Cases | 9 | Boundary conditions |

## Dependencies

The demo project uses:
- **pytest**: Testing framework
- **ruff**: Fast Python linter
- **black**: Code formatter
- **mypy**: Static type checker
- **pip-audit**: Security vulnerability scanner

## CI/CD Integration

This pilot can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Pilot Tests
  run: |
    python3 -m pytest pilot/test_python_pilot.py -v
    
- name: Run Demo Project Tests
  run: |
    cd pilot/python-demo-repo
    python3 -m pytest test_calculator.py -v
```

## Extending the Pilot

To add new scenarios:

1. Create a new directory: `scenarioN/`
2. Add `README.md` describing the scenario
3. Add patch files showing expected changes
4. Add tests to `test_python_pilot.py`

## Notes

- All tests mock external dependencies (no actual LLM calls)
- Tests use temporary directories to avoid side effects
- The pilot demonstrates OpenClaw concepts without requiring full infrastructure
