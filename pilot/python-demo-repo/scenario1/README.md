# Scenario 1: Simple Feature Addition

## Description
Add a new `factorial` method to the Calculator class that calculates the factorial of a non-negative integer.

## Requirements
- Add `factorial(n: int) -> int` method to Calculator class
- Raise `CalculatorError` for negative numbers
- Return 1 for factorial(0) per mathematical convention
- Include proper docstrings and type hints

## Expected Test Cases
```python
def test_factorial_zero(self, calculator):
    assert calculator.factorial(0) == 1

def test_factorial_positive(self, calculator):
    assert calculator.factorial(5) == 120

def test_factorial_negative_raises_error(self, calculator):
    with pytest.raises(CalculatorError):
        calculator.factorial(-1)
```

## Files to Modify
- `calculator.py` - Add factorial method
- `test_calculator.py` - Add factorial tests

## OpenClaw Flow
1. Classify intent: `feature_request`
2. Route to: `DEVCLAW`
3. Action type: `code_generation`
4. Execute changes
5. Run validation: `pytest`, `ruff`, `black`, `mypy`
6. Queue for review
7. Symphony review: Verify implementation correctness
8. Merge on approval
