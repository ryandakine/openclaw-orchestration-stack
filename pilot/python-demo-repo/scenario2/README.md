# Scenario 2: Bug Fix

## Description
Fix a bug where the `square_root` method returns an incorrect type hint and lacks precision for floating point results.

## Current Issue
The `square_root` method currently has a return type of `Number` but always returns `float`. Additionally, it doesn't handle very small numbers well due to floating point precision issues.

## Requirements
- Fix return type hint from `Number` to `float`
- Add better precision handling for floating point results
- Ensure proper error messages for edge cases

## Expected Changes
```python
# Before
def square_root(self, n: Number) -> Number:
    ...
    return n ** 0.5

# After  
def square_root(self, n: Number) -> float:
    ...
    return float(n ** 0.5)
```

## Files to Modify
- `calculator.py` - Fix type hint and precision

## OpenClaw Flow
1. Classify intent: `bug_report`
2. Route to: `DEVCLAW`
3. Action type: `bug_fix`
4. Execute changes
5. Run validation: `pytest`, `ruff`, `black`, `mypy`
6. Verify existing tests still pass
7. Queue for review
8. Symphony review: Verify type correctness
9. Merge on approval
