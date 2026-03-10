# Documentation Tests

This directory contains tests for validating the OpenClaw documentation.

## Purpose

The tests in this directory verify:

1. **Link Integrity** — All internal links point to existing files
2. **Code Block Validity** — Code examples compile/parse correctly
3. **Configuration Validity** — YAML/JSON examples are syntactically correct
4. **Documentation Structure** — Required files exist and follow conventions

## Running Tests

```bash
# Run all documentation tests
pytest docs/tests/test_docs.py

# Run with verbose output
pytest docs/tests/test_docs.py -v

# Run specific test category
pytest docs/tests/test_docs.py::TestLinks
pytest docs/tests/test_docs.py::TestCodeBlocks
```

## Test Coverage

- **Link Tests**: Verify internal and external links
- **Code Block Tests**: Validate syntax of Python, JSON, YAML, and Bash code
- **Config Tests**: Verify Docker Compose and Kubernetes manifests
- **Structure Tests**: Ensure required documentation files exist

## Adding Tests

When adding new documentation:

1. Run tests to ensure links are valid
2. Ensure code blocks are syntactically correct
3. Follow the established header formatting conventions
