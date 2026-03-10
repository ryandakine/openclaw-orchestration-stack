# Rust Demo Repo for OpenClaw

This is a demonstration Rust project for testing OpenClaw's Rust support.

## Structure

```
.
├── Cargo.toml           # Package configuration
├── src/
│   └── lib.rs          # Main library code
├── tests/
│   └── integration_tests.rs  # Integration tests
└── .openclaw/
    └── review.yaml     # OpenClaw review configuration
```

## Usage

### Run Tests

```bash
cargo test
```

### Run Linter

```bash
cargo clippy -- -D warnings
cargo fmt --check
```

### Security Scan

```bash
cargo audit
```

## OpenClaw Configuration

The `.openclaw/review.yaml` file configures the review process:

- **Language**: Rust
- **Profile**: STANDARD
- **Test Command**: `cargo test`
- **Lint Commands**: `cargo clippy -- -D warnings`, `cargo fmt --check`
- **Security**: `cargo audit`

## Library Features

This demo library provides simple arithmetic operations:

- `add(a, b)` - Add two numbers
- `subtract(a, b)` - Subtract b from a
- `multiply(a, b)` - Multiply two numbers
- `divide(a, b)` - Divide a by b (returns Result)
- `calculate(a, b, op)` - Perform calculation with operator
- `Calculator` - Stateful calculator with history

## License

MIT
