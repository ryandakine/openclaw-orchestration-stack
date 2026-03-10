# Configuration Guide

## Overview

OpenClaw Orchestration Stack can be configured through multiple mechanisms:

1. **Environment Variables** — Runtime configuration
2. **Configuration Files** — YAML-based per-repo configuration
3. **Database Settings** — Dynamic configuration stored in SQLite
4. **Command Line Arguments** — Startup configuration

## Environment Variables

### API Keys (Required)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes* | Anthropic Claude API key (`sk-ant-api03-...`) |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (`sk-proj-...`) |
| `GITHUB_API_KEY` | No | GitHub personal access token (`ghp_...`) |

*At least one LLM provider is required

### Database Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCLAW_DB_PATH` | `data/openclaw.db` | Path to SQLite database |
| `DB_POOL_SIZE` | `10` | Connection pool size |
| `DB_TIMEOUT` | `30` | Connection timeout (seconds) |

### API Server Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | API server port |
| `HOST` | `0.0.0.0` | API server host |
| `OPENCLAW_API_KEY` | None | API authentication key |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins (comma-separated) |

### Worker Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_WORKERS` | `5` | Maximum concurrent workers |
| `TASK_TIMEOUT` | `300` | Task execution timeout (seconds) |
| `LEASE_DURATION` | `300` | Task lease duration (seconds) |
| `MAX_RETRIES` | `3` | Maximum retry attempts |
| `RETRY_BACKOFF` | `2` | Exponential backoff multiplier |

### GitHub Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_API_KEY` | None | GitHub API token |
| `GITHUB_WEBHOOK_SECRET` | None | Webhook signature secret |
| `GITHUB_APP_ID` | None | GitHub App ID |
| `GITHUB_PRIVATE_KEY` | None | GitHub App private key path |

### n8n Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `N8N_HOST` | `localhost` | n8n server host |
| `N8N_PORT` | `5678` | n8n server port |
| `N8N_PROTOCOL` | `http` | n8n protocol |
| `N8N_BASIC_AUTH_USER` | `admin` | n8n basic auth username |
| `N8N_BASIC_AUTH_PASSWORD` | None | n8n basic auth password |
| `N8N_WEBHOOK_URL` | None | n8n webhook base URL |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_FORMAT` | `json` | Log format (json, text) |
| `LOG_FILE` | None | Log file path (stdout if not set) |

### Security

| Variable | Default | Description |
|----------|---------|-------------|
| `ENCRYPTION_KEY` | None | Encryption key for sensitive data |
| `JWT_SECRET` | None | JWT signing secret |
| `TOKEN_EXPIRY` | `3600` | Token expiry in seconds |

## Configuration Files

### Repository Configuration

Create `.openclaw/review.yaml` in your repository root:

```yaml
# Repository metadata
repo:
  name: my-project
  language: mixed  # python, rust, node, mixed
  profile_default: STANDARD  # Review profile
  description: "My awesome project"

# Code commands
commands:
  test:
    - "pytest -q"
    - "cargo test"
  lint:
    - "ruff check ."
    - "cargo fmt --check"
  format:
    - "black ."
    - "cargo fmt"
  build:
    - "cargo build --release"
    - "npm run build"

# Security scanning
security:
  dependency_scan:
    - "pip-audit -r requirements.txt"
    - "cargo audit"
    - "npm audit --audit-level=high"
  secret_scan:
    - "gitleaks detect --no-git -v"
  sast:
    - "bandit -r ."

# Review configuration
review:
  auto_merge: false
  require_approval: true
  reviewer_profiles:
    STANDARD:
      check_tests: true
      check_lint: true
      check_security: true
      check_style: true
    MINIMAL:
      check_tests: false
      check_lint: true
      check_security: true
      check_style: false

# File patterns
files:
  include:
    - "src/**/*.py"
    - "src/**/*.rs"
    - "src/**/*.ts"
  exclude:
    - "**/node_modules/**"
    - "**/target/**"
    - "**/__pycache__/**"
    - "**/*.min.js"

# Notifications
notifications:
  slack:
    webhook_url: "${SLACK_WEBHOOK_URL}"
    channel: "#dev-alerts"
  email:
    on_failure: true
    on_success: false
    recipients:
      - "dev-team@example.com"
```

### Global Configuration

Create `config/openclaw.yaml`:

```yaml
# Global OpenClaw configuration
openclaw:
  # Routing configuration
  routing:
    confidence_threshold: 0.7
    auto_review_threshold: 0.9
    default_worker: DEVCLAW
    
    # Intent routing rules
    intents:
      feature_request: DEVCLAW
      bug_report: DEVCLAW
      code_improvement: DEVCLAW
      review: SYMPHONY
      deployment: SYMPHONY
      question: DEVCLAW

  # Worker configuration
  workers:
    devclaw:
      max_concurrent: 5
      timeout: 300
      retry_attempts: 3
      work_dir: "/tmp/devclaw"
    
    symphony:
      max_concurrent: 3
      timeout: 600
      retry_attempts: 2

  # Queue configuration
  queue:
    type: sqlite  # sqlite, redis, rabbitmq
    poll_interval: 5
    batch_size: 10

  # Audit configuration
  audit:
    enabled: true
    retention_days: 365
    export_format: json

  # Metrics
  metrics:
    enabled: true
    port: 9090
    path: /metrics
```

### Language Profiles

Create `config/languages.yaml`:

```yaml
languages:
  python:
    extensions:
      - .py
      - .pyi
    test_patterns:
      - "test_*.py"
      - "*_test.py"
    test_commands:
      - "pytest"
      - "python -m unittest"
    lint_commands:
      - "ruff check"
      - "flake8"
      - "pylint"
    format_commands:
      - "black"
      - "autopep8"
    type_check_commands:
      - "mypy"
      - "pyright"

  rust:
    extensions:
      - .rs
    test_commands:
      - "cargo test"
    lint_commands:
      - "cargo clippy"
      - "cargo fmt --check"
    format_commands:
      - "cargo fmt"
    build_commands:
      - "cargo build"
      - "cargo check"

  node:
    extensions:
      - .js
      - .ts
      - .jsx
      - .tsx
    test_patterns:
      - "*.test.js"
      - "*.spec.ts"
    test_commands:
      - "npm test"
      - "jest"
    lint_commands:
      - "eslint"
      - "npm run lint"
    format_commands:
      - "prettier"
```

## Database Configuration

### Runtime Settings

Settings stored in SQLite and modifiable at runtime:

```python
from shared.db import execute

# Get setting
result = execute(
    "SELECT value FROM settings WHERE key = ?",
    ("max_workers",),
    fetch_one=True
)

# Set setting
execute(
    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
    ("max_workers", "10")
)
```

### Available Settings

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_workers` | int | 5 | Maximum concurrent workers |
| `task_timeout` | int | 300 | Task timeout (seconds) |
| `lease_duration` | int | 300 | Lease duration (seconds) |
| `retry_attempts` | int | 3 | Max retry attempts |
| `auto_approve_threshold` | float | 0.95 | Auto-approval confidence threshold |
| `notification_enabled` | bool | true | Enable notifications |

## Command Line Configuration

### OpenClaw API

```bash
# Basic usage
python -m openclaw.src.api

# With options
python -m openclaw.src.api \
  --port 8000 \
  --host 0.0.0.0 \
  --log-level INFO \
  --reload

# All options
python -m openclaw.src.api --help
```

### DevClaw Worker

```bash
# Basic usage
python -m devclaw_runner.src.worker

# With options
python -m devclaw_runner.src.worker \
  --worker-id worker-001 \
  --max-concurrent 5 \
  --poll-interval 10
```

### Migration Runner

```bash
# Check status
python shared/migrations/runner.py status

# Run migrations
python shared/migrations/runner.py migrate

# Rollback
python shared/migrations/runner.py rollback --steps 1

# Create new migration
python shared/migrations/runner.py create --name add_users_table
```

## Configuration Priority

Configuration is loaded in this order (later overrides earlier):

1. Default values in code
2. Configuration files (`config/*.yaml`)
3. Environment variables
4. Database settings
5. Command line arguments

Example:
```
Default: PORT=8000
  ↓
Config file: PORT=8080
  ↓
Environment: PORT=9000
  ↓
CLI arg: --port 3000
  ↓
Final: PORT=3000
```

## Environment-Specific Configuration

### Development

```bash
# .env.development
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=DEBUG
OPENCLAW_DB_PATH=data/dev.db
```

### Staging

```bash
# .env.staging
ENVIRONMENT=staging
DEBUG=false
LOG_LEVEL=INFO
OPENCLAW_DB_PATH=/var/lib/openclaw/staging.db
GITHUB_API_KEY="ghp_staging_..."
```

### Production

```bash
# .env.production
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING
OPENCLAW_DB_PATH=/var/lib/openclaw/prod.db
GITHUB_API_KEY="ghp_prod_..."
ALLOWED_ORIGINS="https://app.example.com"
```

## Secrets Management

### Using Environment Variables

```bash
# .env (never commit this!)
ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
GITHUB_API_KEY="${GITHUB_API_KEY}"
```

### Using Docker Secrets

```yaml
# docker-compose.yml
secrets:
  anthropic_key:
    file: ./secrets/anthropic_key.txt
  github_key:
    file: ./secrets/github_key.txt

services:
  openclaw:
    secrets:
      - anthropic_key
      - github_key
    environment:
      ANTHROPIC_API_KEY_FILE: /run/secrets/anthropic_key
      GITHUB_API_KEY_FILE: /run/secrets/github_key
```

### Using HashiCorp Vault

```python
import hvac

client = hvac.Client(url='https://vault.example.com')
client.auth.token_login(os.environ['VAULT_TOKEN'])

secret = client.secrets.kv.v2.read_secret_version(
    path='openclaw/api-keys'
)

anthropic_key = secret['data']['data']['anthropic']
```

## Validation

### Configuration Schema

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class OpenClawConfig(BaseModel):
    port: int = Field(default=8000, ge=1024, le=65535)
    log_level: str = Field(default="INFO", regex="^(DEBUG|INFO|WARNING|ERROR)$")
    max_workers: int = Field(default=5, ge=1, le=100)
    allowed_origins: List[str] = Field(default=["*"])
    
    @validator('allowed_origins')
    def validate_origins(cls, v):
        if "*" in v and len(v) > 1:
            raise ValueError("Cannot mix wildcard with specific origins")
        return v

# Validate
try:
    config = OpenClawConfig(**settings)
except ValidationError as e:
    print(f"Invalid configuration: {e}")
```

### Configuration Check Command

```bash
# Validate configuration
python -c "from openclaw.config import validate; validate()"

# Or via CLI
openclaw config validate
```

## Hot Reload

Some settings can be updated without restart:

```bash
# Reload configuration
kill -HUP <openclaw_pid>

# Or via API
curl -X POST http://localhost:8000/admin/reload \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**Hot-reloadable settings:**
- `LOG_LEVEL`
- `MAX_WORKERS`
- `TASK_TIMEOUT`
- Notification settings

## Troubleshooting Configuration

### Configuration Not Loading

```bash
# Check file permissions
ls -la .env
ls -la config/

# Verify YAML syntax
python -c "import yaml; yaml.safe_load(open('config/openclaw.yaml'))"

# Check environment variables
env | grep OPENCLAW
```

### Database Connection Issues

```bash
# Test database path
python -c "
import os
from pathlib import Path
db_path = os.environ.get('OPENCLAW_DB_PATH', 'data/openclaw.db')
print(f'DB Path: {db_path}')
print(f'Parent exists: {Path(db_path).parent.exists()}')
print(f'Writable: {os.access(Path(db_path).parent, os.W_OK)}')"
```

### API Key Issues

```bash
# Test API key
curl -H "X-API-Key: $OPENCLAW_API_KEY" http://localhost:8000/health

# Check key is set
echo "Key length: ${#OPENCLAW_API_KEY}"
```

## Configuration Examples

### Minimal Setup

```bash
# .env
ANTHROPIC_API_KEY="sk-ant-api03-..."
GITHUB_API_KEY="ghp_..."
```

### Full Production Setup

See [docker/docker-compose.yml](../../docker/docker-compose.yml)

### CI/CD Configuration

```yaml
# .github/workflows/openclaw.yml
name: OpenClaw Integration

on: [push, pull_request]

jobs:
  openclaw:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup OpenClaw
        run: |
          pip install openclaw
          openclaw config validate
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

## References

- [Setup Guide](./setup.md) — Installation instructions
- [Security Guide](./security.md) — Security configuration
- [API Documentation](../api/rest-api.md) — API reference
