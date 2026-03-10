/**
 * Tests for calculator module
 * Uses Node.js built-in test runner
 */

const { describe, it } = require('node:test');
const assert = require('node:assert');
const { add, subtract, multiply, divide } = require('../src/index');

describe('Calculator', () => {
  describe('add', () => {
    it('should add two positive numbers', () => {
      assert.strictEqual(add(2, 3), 5);
    });

    it('should add negative numbers', () => {
      assert.strictEqual(add(-2, -3), -5);
    });

    it('should handle zero', () => {
      assert.strictEqual(add(5, 0), 5);
    });
  });

  describe('subtract', () => {
    it('should subtract two numbers', () => {
      assert.strictEqual(subtract(5, 3), 2);
    });

    it('should handle negative result', () => {
      assert.strictEqual(subtract(3, 5), -2);
    });
  });

  describe('multiply', () => {
    it('should multiply two numbers', () => {
      assert.strictEqual(multiply(4, 3), 12);
    });

    it('should handle zero', () => {
      assert.strictEqual(multiply(5, 0), 0);
    });
  });

  describe('divide', () => {
    it('should divide two numbers', () => {
      assert.strictEqual(divide(12, 4), 3);
    });

    it('should throw on division by zero', () => {
      assert.throws(() => divide(5, 0), /Division by zero/);
    });
  });
});
