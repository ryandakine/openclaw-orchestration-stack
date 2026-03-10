"""
Tests for the Calculator Module

This module contains pytest tests demonstrating proper testing practices
including fixtures, parametrized tests, and exception testing.
"""

import pytest
from calculator import Calculator, CalculatorError, DivisionByZeroError


@pytest.fixture
def calculator():
    """Provide a fresh Calculator instance for each test."""
    return Calculator()


class TestCalculatorBasicOperations:
    """Tests for basic arithmetic operations."""
    
    def test_add_positive_numbers(self, calculator):
        """Test adding two positive numbers."""
        result = calculator.add(2, 3)
        assert result == 5
    
    def test_add_negative_numbers(self, calculator):
        """Test adding negative numbers."""
        result = calculator.add(-2, -3)
        assert result == -5
    
    def test_add_mixed_numbers(self, calculator):
        """Test adding positive and negative numbers."""
        result = calculator.add(-2, 3)
        assert result == 1
    
    def test_add_floats(self, calculator):
        """Test adding floating point numbers."""
        result = calculator.add(2.5, 3.5)
        assert result == 6.0
    
    def test_subtract_positive_numbers(self, calculator):
        """Test subtracting two positive numbers."""
        result = calculator.subtract(5, 3)
        assert result == 2
    
    def test_subtract_negative_numbers(self, calculator):
        """Test subtracting negative numbers."""
        result = calculator.subtract(-5, -3)
        assert result == -2
    
    def test_subtract_mixed_numbers(self, calculator):
        """Test subtracting from negative number."""
        result = calculator.subtract(-5, 3)
        assert result == -8


class TestCalculatorMultiplicationDivision:
    """Tests for multiplication and division operations."""
    
    def test_multiply_positive_numbers(self, calculator):
        """Test multiplying two positive numbers."""
        result = calculator.multiply(4, 5)
        assert result == 20
    
    def test_multiply_by_zero(self, calculator):
        """Test multiplying by zero."""
        result = calculator.multiply(100, 0)
        assert result == 0
    
    def test_multiply_negative_numbers(self, calculator):
        """Test multiplying two negative numbers."""
        result = calculator.multiply(-4, -5)
        assert result == 20
    
    def test_multiply_mixed_numbers(self, calculator):
        """Test multiplying positive and negative numbers."""
        result = calculator.multiply(-4, 5)
        assert result == -20
    
    def test_divide_positive_numbers(self, calculator):
        """Test dividing two positive numbers."""
        result = calculator.divide(10, 2)
        assert result == 5.0
    
    def test_divide_by_one(self, calculator):
        """Test dividing by one."""
        result = calculator.divide(10, 1)
        assert result == 10.0
    
    def test_divide_negative_numbers(self, calculator):
        """Test dividing negative numbers."""
        result = calculator.divide(-10, -2)
        assert result == 5.0
    
    def test_divide_by_zero_raises_error(self, calculator):
        """Test that dividing by zero raises DivisionByZeroError."""
        with pytest.raises(DivisionByZeroError):
            calculator.divide(10, 0)
    
    def test_divide_zero_by_number(self, calculator):
        """Test dividing zero by a number."""
        result = calculator.divide(0, 5)
        assert result == 0.0


class TestCalculatorAdvancedOperations:
    """Tests for advanced operations like power and square root."""
    
    def test_power_positive_integers(self, calculator):
        """Test power with positive integers."""
        result = calculator.power(2, 3)
        assert result == 8
    
    def test_power_zero_exponent(self, calculator):
        """Test power with zero exponent."""
        result = calculator.power(5, 0)
        assert result == 1
    
    def test_power_negative_exponent(self, calculator):
        """Test power with negative exponent."""
        result = calculator.power(2, -1)
        assert result == 0.5
    
    def test_square_root_perfect_square(self, calculator):
        """Test square root of a perfect square."""
        result = calculator.square_root(16)
        assert result == 4.0
    
    def test_square_root_non_perfect_square(self, calculator):
        """Test square root of a non-perfect square."""
        result = calculator.square_root(2)
        assert pytest.approx(result, 0.001) == 1.414
    
    def test_square_root_of_zero(self, calculator):
        """Test square root of zero."""
        result = calculator.square_root(0)
        assert result == 0.0
    
    def test_square_root_of_one(self, calculator):
        """Test square root of one."""
        result = calculator.square_root(1)
        assert result == 1.0
    
    def test_square_root_negative_raises_error(self, calculator):
        """Test that square root of negative number raises error."""
        with pytest.raises(CalculatorError):
            calculator.square_root(-4)


class TestCalculatorAverage:
    """Tests for the average calculation."""
    
    def test_average_of_positive_numbers(self, calculator):
        """Test average of positive numbers."""
        result = calculator.average([1, 2, 3, 4, 5])
        assert result == 3.0
    
    def test_average_of_same_numbers(self, calculator):
        """Test average of identical numbers."""
        result = calculator.average([5, 5, 5, 5])
        assert result == 5.0
    
    def test_average_of_two_numbers(self, calculator):
        """Test average of two numbers."""
        result = calculator.average([10, 20])
        assert result == 15.0
    
    def test_average_of_single_number(self, calculator):
        """Test average of single number."""
        result = calculator.average([42])
        assert result == 42.0
    
    def test_average_of_mixed_numbers(self, calculator):
        """Test average of positive and negative numbers."""
        result = calculator.average([-5, 5, -10, 10])
        assert result == 0.0
    
    def test_average_empty_list_raises_error(self, calculator):
        """Test that average of empty list raises error."""
        with pytest.raises(CalculatorError):
            calculator.average([])


class TestCalculatorEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_large_numbers_addition(self, calculator):
        """Test addition with large numbers."""
        result = calculator.add(1_000_000, 2_000_000)
        assert result == 3_000_000
    
    def test_small_float_addition(self, calculator):
        """Test addition with very small floats."""
        result = calculator.add(0.0001, 0.0002)
        assert pytest.approx(result, 0.00001) == 0.0003
    
    def test_subtract_resulting_zero(self, calculator):
        """Test subtraction that results in zero."""
        result = calculator.subtract(5, 5)
        assert result == 0
    
    def test_multiply_by_one(self, calculator):
        """Test multiplying by one."""
        result = calculator.multiply(42, 1)
        assert result == 42
    
    def test_divide_resulting_whole_number(self, calculator):
        """Test division that results in whole number."""
        result = calculator.divide(10, 5)
        assert result == 2.0
    
    def test_divide_resulting_float(self, calculator):
        """Test division that results in float."""
        result = calculator.divide(10, 4)
        assert result == 2.5
