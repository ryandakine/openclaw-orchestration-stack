"""
Patch for Scenario 1: Add factorial method to Calculator class

This patch adds the factorial functionality to calculator.py
"""

# Add this method to the Calculator class in calculator.py:

FACTORIAL_PATCH = '''
    def factorial(self, n: int) -> int:
        """
        Calculate the factorial of a non-negative integer.
        
        Args:
            n: Non-negative integer
            
        Returns:
            Factorial of n (n!)
            
        Raises:
            CalculatorError: If n is negative
            TypeError: If n is not an integer
        """
        if not isinstance(n, int):
            raise TypeError("Factorial is only defined for integers")
        if n < 0:
            raise CalculatorError("Factorial is not defined for negative numbers")
        if n == 0 or n == 1:
            return 1
        result = 1
        for i in range(2, n + 1):
            result *= i
        return result
'''

# Add these test methods to test_calculator.py:

FACTORIAL_TESTS = '''
    def test_factorial_zero(self, calculator):
        """Test factorial of zero is 1."""
        result = calculator.factorial(0)
        assert result == 1
    
    def test_factorial_one(self, calculator):
        """Test factorial of one is 1."""
        result = calculator.factorial(1)
        assert result == 1
    
    def test_factorial_positive(self, calculator):
        """Test factorial of positive integer."""
        result = calculator.factorial(5)
        assert result == 120  # 5! = 120
    
    def test_factorial_small(self, calculator):
        """Test factorial of small number."""
        result = calculator.factorial(3)
        assert result == 6  # 3! = 6
    
    def test_factorial_large(self, calculator):
        """Test factorial of larger number."""
        result = calculator.factorial(10)
        assert result == 3628800  # 10! = 3628800
    
    def test_factorial_negative_raises_error(self, calculator):
        """Test that factorial of negative raises error."""
        with pytest.raises(CalculatorError):
            calculator.factorial(-1)
    
    def test_factorial_non_integer_raises_error(self, calculator):
        """Test that factorial of non-integer raises error."""
        with pytest.raises(TypeError):
            calculator.factorial(3.5)
'''
