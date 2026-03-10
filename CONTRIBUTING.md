# Contributing to OpenClaw Orchestration Stack

Thank you for your interest in contributing to OpenClaw! This document provides guidelines and instructions for contributing.

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code:

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Respect different viewpoints and experiences

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git
- Docker (optional)

### Setting Up Development Environment

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/openclaw-orchestration-stack.git
cd openclaw-orchestration-stack

# 3. Create a virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 5. Install pre-commit hooks
pre-commit install

# 6. Run tests to verify setup
pytest
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/my-feature-name
# or
git checkout -b fix/my-bug-fix
```

Branch naming conventions:
- `feature/description` — New features
- `fix/description` — Bug fixes
- `docs/description` — Documentation updates
- `refactor/description` — Code refactoring
- `test/description` — Test additions/improvements

### 2. Make Changes

- Write clear, concise commit messages
- Follow PEP 8 style guide for Python code
- Add docstrings to public functions and classes
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=openclaw --cov=devclaw_runner --cov=symphony_bridge

# Run specific test file
pytest tests/unit/test_openclaw.py

# Run with verbose output
pytest -v
```

### 4. Check Code Quality

```bash
# Format code
make format

# Run linting
make lint

# Run type checking
make type-check

# Run all checks
make check
```

### 5. Commit Changes

```bash
git add .
git commit -m "feat: add feature description

Detailed explanation of the change, including:
- What changed
- Why it changed
- Any breaking changes

Fixes #123"
```

Commit message format (Conventional Commits):
- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `style:` — Code style changes (formatting, semicolons, etc)
- `refactor:` — Code refactoring
- `test:` — Test additions/changes
- `chore:` — Build process or auxiliary tool changes

### 6. Push and Create Pull Request

```bash
git push origin feature/my-feature-name
```

Then create a pull request on GitHub.

## Pull Request Guidelines

### Before Submitting

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] Branch is up to date with main

### PR Description

Include in your PR description:

1. **Summary** — What does this PR do?
2. **Motivation** — Why is this change needed?
3. **Changes** — List of major changes
4. **Testing** — How was this tested?
5. **Screenshots** — If UI changes
6. **Related Issues** — Fixes #123, Relates to #456

### Review Process

1. Automated checks must pass
2. At least one maintainer approval required
3. Address review feedback
4. Squash commits if requested

## Project Structure

```
openclaw-orchestration-stack/
├── openclaw/              # Orchestrator and decision engine
│   ├── src/               # Core orchestration logic
│   ├── schemas/           # Data models and validation
│   └── dashboard/         # Web dashboard
├── devclaw-runner/        # Task execution worker
│   ├── src/               # Runner implementation
│   └── workers/           # Worker implementations
├── symphony-bridge/       # PR management and review
│   ├── src/               # Core bridge functionality
│   ├── github/            # GitHub API integration
│   └── review/            # Review agent logic
├── n8n-workflows/         # n8n automation workflows
├── shared/                # Shared libraries
│   ├── utils/             # Common utilities
│   ├── models/            # Data models
│   └── migrations/        # Database migrations
├── docs/                  # Documentation
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/               # End-to-end tests
└── docker/                # Docker configurations
```

## Coding Standards

### Python

Follow PEP 8 with these additions:

- Maximum line length: 100 characters
- Use type hints for function signatures
- Use docstrings for public APIs (Google style)
- Use f-strings for string formatting

```python
def process_request(
    request: Dict[str, Any],
    timeout: int = 30
) -> ActionPlan:
    """Process an incoming request and return an action plan.
    
    Args:
        request: Dictionary containing request data
        timeout: Maximum time to wait in seconds
        
    Returns:
        ActionPlan with routing decision
        
    Raises:
        RoutingError: If unable to route request
        TimeoutError: If processing exceeds timeout
    """
    # Implementation
```

### Testing

```python
import pytest
from unittest.mock import Mock, patch

def test_process_request_success():
    """Test successful request processing."""
    # Arrange
    request = {"type": "feature_request"}
    
    # Act
    result = process_request(request)
    
    # Assert
    assert result.success is True
    assert result.routing.worker_type == "DEVCLAW"

@pytest.mark.parametrize("intent,expected_worker", [
    ("feature_request", "DEVCLAW"),
    ("review", "SYMPHONY"),
])
def test_routing_decisions(intent, expected_worker):
    """Test routing decisions for different intents."""
    result = route_intent(intent)
    assert result == expected_worker
```

### Documentation

- Use Markdown for documentation
- Include code examples
- Keep README files up to date
- Document API changes

## Testing Guidelines

### Unit Tests

- Test individual functions/classes in isolation
- Use mocks for external dependencies
- Aim for >80% code coverage

### Integration Tests

- Test component interactions
- Use test databases
- Mock external APIs

### End-to-End Tests

- Test complete workflows
- Use real (test) repositories
- Test critical paths

## Documentation

### Code Documentation

- Docstrings for all public functions/classes
- Inline comments for complex logic
- Type hints for function signatures

### User Documentation

- Update relevant docs/ files
- Include examples
- Keep README.md current

### API Documentation

- Document all endpoints
- Include request/response examples
- Document error responses

## Release Process

1. Update version in `__init__.py`
2. Update CHANGELOG.md
3. Create git tag
4. Build and publish Docker images
5. Create GitHub release

## Security

### Reporting Security Issues

Please do NOT report security issues publicly. Instead:

1. Email security@openclaw.dev
2. Include detailed description
3. Allow time for fix before disclosure

### Security Best Practices

- Never commit secrets
- Use parameterized queries
- Validate all inputs
- Follow OWASP guidelines

## Community

### Communication Channels

- GitHub Issues — Bug reports, feature requests
- GitHub Discussions — General discussion
- Discord — Real-time chat (link TBD)

### Getting Help

- Check documentation first
- Search existing issues
- Ask in discussions
- Join community chat

## Recognition

Contributors will be:

- Listed in CONTRIBUTORS.md
- Mentioned in release notes
- Credited in relevant documentation

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

If you have questions about contributing:

1. Check existing documentation
2. Search closed issues
3. Open a discussion
4. Ask in community chat

Thank you for contributing to OpenClaw! 🎉
