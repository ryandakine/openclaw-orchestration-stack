"""
Patch for Scenario 2: Fix square_root type hint and precision

This patch fixes the square_root method in calculator.py
"""

# Replace the square_root method in calculator.py with:

SQUARE_ROOT_FIX = '''
    def square_root(self, n: Number) -> float:
        """
        Calculate the square root of a number.
        
        Args:
            n: Number to calculate square root of (must be >= 0)
            
        Returns:
            Square root of n as a float
            
        Raises:
            CalculatorError: If n is negative
            
        Example:
            >>> calc = Calculator()
            >>> calc.square_root(16)
            4.0
            >>> calc.square_root(2)
            1.4142135623730951
        """
        if n < 0:
            raise CalculatorError("Cannot calculate square root of negative number")
        # Ensure we return a proper float with correct precision
        result = float(n) ** 0.5
        return float(result)
'''

# Additional test cases to add for regression testing:

REGRESSION_TESTS = '''
    def test_square_root_returns_float(self, calculator):
        """Test that square_root always returns a float."""
        result = calculator.square_root(16)
        assert isinstance(result, float)
        assert result == 4.0
    
    def test_square_root_perfect_square_integer(self, calculator):
        """Test square root of perfect square from integer."""
        result = calculator.square_root(9)
        assert isinstance(result, float)
        assert result == 3.0
    
    def test_square_root_precision(self, calculator):
        """Test that square root maintains precision."""
        result = calculator.square_root(2)
        # Check precision to multiple decimal places
        assert pytest.approx(result, rel=1e-10) == 1.4142135623730951
    
    def test_square_root_very_small_number(self, calculator):
        """Test square root of very small number."""
        result = calculator.square_root(0.0001)
        assert isinstance(result, float)
        assert pytest.approx(result, rel=1e-10) == 0.01
'''
