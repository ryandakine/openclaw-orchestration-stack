//! Integration tests for rust-demo-repo
//!
//! These tests verify the library's behavior from an external perspective,
//! testing public API usage as a consumer would.

use rust_demo_repo::{
    add, subtract, multiply, divide, calculate, Calculator, ArithmeticError, CalculationResult,
};

#[test]
fn test_basic_arithmetic_integration() {
    // Test all basic operations work together
    let a = 100;
    let b = 25;
    
    assert_eq!(add(a, b), 125);
    assert_eq!(subtract(a, b), 75);
    assert_eq!(multiply(a, b), 2500);
    assert_eq!(divide(a, b).unwrap(), 4);
}

#[test]
fn test_calculation_result_serialization() {
    // Test that results can be serialized (important for API responses)
    let result = calculate(42, 8, '+').unwrap();
    
    let json = serde_json::to_string(&result).expect("Should serialize to JSON");
    let deserialized: CalculationResult = serde_json::from_str(&json).expect("Should deserialize");
    
    assert_eq!(result, deserialized);
}

#[test]
fn test_calculator_history_persistence() {
    let mut calc = Calculator::new();
    
    // Perform several calculations
    calc.compute(1, 2, '+').unwrap();
    calc.compute(10, 5, '-').unwrap();
    calc.compute(3, 4, '*').unwrap();
    calc.compute(20, 4, '/').unwrap();
    
    let history = calc.history();
    assert_eq!(history.len(), 4);
    
    // Verify history contents
    assert_eq!(history[0].result, 3);
    assert_eq!(history[0].operation, "add");
    
    assert_eq!(history[1].result, 5);
    assert_eq!(history[1].operation, "subtract");
    
    assert_eq!(history[2].result, 12);
    assert_eq!(history[2].operation, "multiply");
    
    assert_eq!(history[3].result, 5);
    assert_eq!(history[3].operation, "divide");
}

#[test]
fn test_error_handling_integration() {
    // Test that errors are properly propagated
    let result = divide(100, 0);
    assert!(result.is_err());
    assert_eq!(result.unwrap_err(), ArithmeticError::DivisionByZero);
    
    // Test that valid operations still work after an error
    assert_eq!(divide(100, 10).unwrap(), 10);
}

#[test]
fn test_calculator_error_handling() {
    let mut calc = Calculator::new();
    
    // Failed computation should not be added to history
    let result = calc.compute(10, 0, '/');
    assert!(result.is_err());
    assert!(calc.history().is_empty());
    
    // Successful computation should be added
    calc.compute(10, 5, '+').unwrap();
    assert_eq!(calc.history().len(), 1);
}

#[test]
fn test_edge_cases() {
    // Test with maximum values
    let max = i64::MAX;
    let min = i64::MIN;
    
    // Addition near limits
    let _ = add(0, max);
    let _ = add(0, min);
    
    // Multiplication by zero
    assert_eq!(multiply(max, 0), 0);
    assert_eq!(multiply(min, 0), 0);
    
    // Division of zero
    assert_eq!(divide(0, max).unwrap(), 0);
    assert_eq!(divide(0, min).unwrap(), 0);
}

#[test]
fn test_negative_numbers() {
    assert_eq!(add(-5, -3), -8);
    assert_eq!(subtract(-5, -3), -2);
    assert_eq!(multiply(-5, -3), 15);
    assert_eq!(multiply(-5, 3), -15);
    assert_eq!(divide(-10, 2).unwrap(), -5);
    assert_eq!(divide(-10, -2).unwrap(), 5);
}

#[test]
fn test_all_operations_via_calculate() {
    // Test that calculate function handles all operations correctly
    assert_eq!(calculate(10, 5, '+').unwrap().result, 15);
    assert_eq!(calculate(10, 5, '-').unwrap().result, 5);
    assert_eq!(calculate(10, 5, '*').unwrap().result, 50);
    assert_eq!(calculate(10, 5, '/').unwrap().result, 2);
}
