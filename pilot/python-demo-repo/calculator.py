"""
Calculator Module

A simple calculator class demonstrating basic arithmetic operations.
This module serves as the demo implementation for the OpenClaw Python pilot.
"""

from typing import Union


Number = Union[int, float]


class CalculatorError(Exception):
    """Base exception for calculator errors."""
    pass


class DivisionByZeroError(CalculatorError):
    """Raised when attempting to divide by zero."""
    pass


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
    
    def add(self, a: Number, b: Number) -> Number:
        """
        Add two numbers.
        
        Args:
            a: First number
            b: Second number
            
        Returns:
            Sum of a and b
        """
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
        if b == 0:
            raise DivisionByZeroError("Cannot divide by zero")
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
        return base ** exponent
    
    def square_root(self, n: Number) -> Number:
        """
        Calculate the square root of a number.
        
        Args:
            n: Number to calculate square root of
            
        Returns:
            Square root of n
            
        Raises:
            CalculatorError: If n is negative
        """
        if n < 0:
            raise CalculatorError("Cannot calculate square root of negative number")
        return n ** 0.5
    
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
        return sum(numbers) / len(numbers)
