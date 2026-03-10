# Scenario 3: Refactoring

## Description
Refactor the Calculator class to use a more extensible operation registration pattern and extract validation logic.

## Current Structure
All operations are hardcoded methods in the Calculator class.

## Proposed Structure
- Extract validation logic into separate private methods
- Use a more functional approach for operation definitions
- Maintain backward compatibility with existing API

## Requirements
- Create `_validate_number()` and `_validate_non_zero()` private methods
- Extract common validation patterns
- Improve code organization without breaking existing tests
- Add operation registry for extensibility (optional enhancement)

## Files to Modify
- `calculator.py` - Refactor structure
- No changes needed to test_calculator.py (backward compatible)

## Expected Improvements
- Better separation of concerns
- Reduced code duplication
- Easier to add new operations
- More maintainable validation logic

## OpenClaw Flow
1. Classify intent: `code_improvement`
2. Route to: `DEVCLAW`
3. Action type: `refactoring`
4. Execute changes
5. Run validation: `pytest`, `ruff`, `black`, `mypy`
6. Ensure ALL existing tests pass (no breaking changes)
7. Queue for review
8. Symphony review: Verify code quality improvements
9. Merge on approval
