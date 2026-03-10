//! Demo library for OpenClaw Rust support testing
//!
//! This library provides simple arithmetic operations to demonstrate
//! Rust project structure and testing with OpenClaw.

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors that can occur in arithmetic operations
#[derive(Error, Debug, PartialEq)]
pub enum ArithmeticError {
    #[error("Division by zero")]
    DivisionByZero,
    #[error("Integer overflow")]
    Overflow,
}

/// Result of an arithmetic operation
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CalculationResult {
    pub operation: String,
    pub operands: Vec<i64>,
    pub result: i64,
}

/// Adds two numbers together
///
/// # Examples
///
/// ```
/// use rust_demo_repo::add;
/// assert_eq!(add(2, 3), 5);
/// ```
pub fn add(a: i64, b: i64) -> i64 {
    a + b
}

/// Subtracts the second number from the first
///
/// # Examples
///
/// ```
/// use rust_demo_repo::subtract;
/// assert_eq!(subtract(5, 3), 2);
/// ```
pub fn subtract(a: i64, b: i64) -> i64 {
    a - b
}

/// Multiplies two numbers
///
/// # Examples
///
/// ```
/// use rust_demo_repo::multiply;
/// assert_eq!(multiply(3, 4), 12);
/// ```
pub fn multiply(a: i64, b: i64) -> i64 {
    a * b
}

/// Divides the first number by the second
///
/// # Errors
///
/// Returns `ArithmeticError::DivisionByZero` if `b` is zero.
///
/// # Examples
///
/// ```
/// use rust_demo_repo::divide;
/// assert_eq!(divide(10, 2).unwrap(), 5);
/// ```
pub fn divide(a: i64, b: i64) -> Result<i64, ArithmeticError> {
    if b == 0 {
        Err(ArithmeticError::DivisionByZero)
    } else {
        Ok(a / b)
    }
}

/// Performs a calculation and returns a structured result
///
/// # Examples
///
/// ```
/// use rust_demo_repo::calculate;
/// let result = calculate(10, 5, '+').unwrap();
/// assert_eq!(result.result, 15);
/// ```
pub fn calculate(a: i64, b: i64, op: char) -> Result<CalculationResult, ArithmeticError> {
    let (result, operation) = match op {
        '+' => (add(a, b), "add".to_string()),
        '-' => (subtract(a, b), "subtract".to_string()),
        '*' => (multiply(a, b), "multiply".to_string()),
        '/' => (divide(a, b)?, "divide".to_string()),
        _ => (0, "unknown".to_string()),
    };

    Ok(CalculationResult {
        operation,
        operands: vec![a, b],
        result,
    })
}

/// A simple calculator struct that maintains state
#[derive(Debug, Default)]
pub struct Calculator {
    history: Vec<CalculationResult>,
}

impl Calculator {
    /// Creates a new Calculator instance
    pub fn new() -> Self {
        Self {
            history: Vec::new(),
        }
    }

    /// Performs a calculation and stores it in history
    pub fn compute(&mut self, a: i64, b: i64, op: char) -> Result<i64, ArithmeticError> {
        let calc_result = calculate(a, b, op)?;
        let result = calc_result.result;
        self.history.push(calc_result);
        Ok(result)
    }

    /// Returns the calculation history
    pub fn history(&self) -> &[CalculationResult] {
        &self.history
    }

    /// Clears the calculation history
    pub fn clear(&mut self) {
        self.history.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_add() {
        assert_eq!(add(2, 3), 5);
        assert_eq!(add(-1, 1), 0);
        assert_eq!(add(0, 0), 0);
    }

    #[test]
    fn test_subtract() {
        assert_eq!(subtract(5, 3), 2);
        assert_eq!(subtract(3, 5), -2);
        assert_eq!(subtract(0, 0), 0);
    }

    #[test]
    fn test_multiply() {
        assert_eq!(multiply(3, 4), 12);
        assert_eq!(multiply(-2, 3), -6);
        assert_eq!(multiply(0, 100), 0);
    }

    #[test]
    fn test_divide() {
        assert_eq!(divide(10, 2).unwrap(), 5);
        assert_eq!(divide(7, 2).unwrap(), 3);
        assert_eq!(divide(0, 5).unwrap(), 0);
    }

    #[test]
    fn test_divide_by_zero() {
        assert_eq!(divide(10, 0), Err(ArithmeticError::DivisionByZero));
    }

    #[test]
    fn test_calculate() {
        let result = calculate(10, 5, '+').unwrap();
        assert_eq!(result.result, 15);
        assert_eq!(result.operation, "add");

        let result = calculate(10, 5, '-').unwrap();
        assert_eq!(result.result, 5);
        assert_eq!(result.operation, "subtract");
    }

    #[test]
    fn test_calculator() {
        let mut calc = Calculator::new();
        
        assert_eq!(calc.compute(10, 5, '+').unwrap(), 15);
        assert_eq!(calc.compute(10, 5, '-').unwrap(), 5);
        
        assert_eq!(calc.history().len(), 2);
        
        calc.clear();
        assert!(calc.history().is_empty());
    }
}
