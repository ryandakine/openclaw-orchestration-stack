"""
Patch for Scenario 3: Refactor Calculator class for better structure

This patch refactors calculator.py to use better code organization
while maintaining backward compatibility.
"""

# Full refactored Calculator class to replace in calculator.py:

REFACTORED_CALCULATOR = '''
"""
Calculator Module

A simple calculator class demonstrating basic arithmetic operations.
This module serves as the demo implementation for the OpenClaw Python pilot.
"""

from typing import Union, Callable
from functools import wraps


Number = Union[int, float]


class CalculatorError(Exception):
    """Base exception for calculator errors."""
    pass


class DivisionByZeroError(CalculatorError):
    """Raised when attempting to divide by zero."""
    pass


def _validate_number(name: str, value: Number) -> None:
    """Validate that a value is a valid number."""
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")


def _validate_non_zero(name: str, value: Number) -> None:
    """Validate that a value is not zero."""
    if value == 0:
        raise DivisionByZeroError(f"{name} cannot be zero")


class Calculator:
    """
    A simple calculator supporting basic arithmetic operations.
    
    This class demonstrates clean Python code with type hints,
    proper documentation, and error handling.
    
    Example:
        >>> calc = Calculator()
        >>> calc.add(2, 3)
        5
        >>> calc.multiply(4, 5)
        20
    """
    
    def __init__(self):
        """Initialize the calculator with operation registry."""
        self._operations: dict[str, Callable] = {
            'add': self.add,
            'subtract': self.subtract,
            'multiply': self.multiply,
            'divide': self.divide,
            'power': self.power,
            'square_root': self.square_root,
            'average': self.average,
        }
    
    def _validate_operands(self, a: Number, b: Number) -> None:
        """Validate both operands are valid numbers."""
        _validate_number("First operand", a)
        _validate_number("Second operand", b)
    
    def add(self, a: Number, b: Number) -> Number:
        """
        Add two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of a and b
        """
        self._validate_operands(a, b)
        return a + b
    
    def subtract(self, a: Number, b: Number) -> Number:
        """
        Subtract b from a.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Difference of a and b
        """
        self._validate_operands(a, b)
        return a - b
    
    def multiply(self, a: Number, b: Number) -> Number:
        """
        Multiply two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Product of a and b
        """
        self._validate_operands(a, b)
        return a * b
    
    def divide(self, a: Number, b: Number) -> Number:
        """
        Divide a by b.
        
        Args:
            a: Numerator
            b: Denominator
            
        Returns:
            Quotient of a and b
            
        Raises:
            DivisionByZeroError: If b is zero
        """
        self._validate_operands(a, b)
        _validate_non_zero("Denominator", b)
        return a / b
    
    def power(self, base: Number, exponent: Number) -> Number:
        """
        Calculate base raised to the power of exponent.
        
        Args:
            base: Base number
            exponent: Exponent
            
        Returns:
            base^exponent
        """
        self._validate_operands(base, exponent)
        return base ** exponent
    
    def square_root(self, n: Number) -> float:
        """
        Calculate the square root of a number.
        
        Args:
            n: Number to calculate square root of (must be >= 0)
            
        Returns:
            Square root of n as a float
            
        Raises:
            CalculatorError: If n is negative
        """
        _validate_number("Input", n)
        if n < 0:
            raise CalculatorError("Cannot calculate square root of negative number")
        return float(n ** 0.5)
    
    def average(self, numbers: list[Number]) -> Number:
        """
        Calculate the average of a list of numbers.
        
        Args:
            numbers: List of numbers
            
        Returns:
            Average of the numbers
            
        Raises:
            CalculatorError: If numbers is empty
        """
        if not numbers:
            raise CalculatorError("Cannot calculate average of empty list")
        for i, n in enumerate(numbers):
            _validate_number(f"Element at index {i}", n)
        return sum(numbers) / len(numbers)
    
    def execute(self, operation: str, *args) -> Number:
        """
        Execute a registered operation by name.
        
        Args:
            operation: Name of the operation to execute
            *args: Arguments for the operation
            
        Returns:
            Result of the operation
            
        Raises:
            CalculatorError: If operation is not registered
        """
        if operation not in self._operations:
            raise CalculatorError(f"Unknown operation: {operation}")
        return self._operations[operation](*args)
    
    @property
    def available_operations(self) -> list[str]:
        """Return list of available operation names."""
        return list(self._operations.keys())
'''

# Additional tests for new functionality:

REFACTOR_TESTS = '''
class TestCalculatorRefactoredFeatures:
    """Tests for features added during refactoring."""
    
    def test_execute_add(self, calculator):
        """Test executing add via execute method."""
        result = calculator.execute('add', 2, 3)
        assert result == 5
    
    def test_execute_multiply(self, calculator):
        """Test executing multiply via execute method."""
        result = calculator.execute('multiply', 4, 5)
        assert result == 20
    
    def test_execute_unknown_operation_raises_error(self, calculator):
        """Test that unknown operation raises error."""
        with pytest.raises(CalculatorError):
            calculator.execute('unknown', 1, 2)
    
    def test_available_operations(self, calculator):
        """Test that available operations are returned."""
        ops = calculator.available_operations
        assert 'add' in ops
        assert 'subtract' in ops
        assert 'multiply' in ops
        assert 'divide' in ops
        assert 'power' in ops
        assert 'square_root' in ops
        assert 'average' in ops
    
    def test_invalid_operand_type_raises_error(self, calculator):
        """Test that invalid operand types raise TypeError."""
        with pytest.raises(TypeError):
            calculator.add("not a number", 2)
'''
