# OpenClaw Review Configuration System

Per-repo configuration for mixed-language support in the OpenClaw Orchestration Stack.

## Overview

This module provides configuration parsing, language detection, command execution, and review profile management for the `.openclaw/review.yaml` configuration system.

## Components

### 1. `review_config.py` - Config Parser and Validator

Parses and validates `.openclaw/review.yaml` configuration files.

**Key Functions:**
- `parse_review_yaml(content)` - Parse YAML content into ReviewConfig
- `validate_config(config)` - Validate configuration schema
- `load_review_yaml(path)` - Load config from file
- `find_review_yaml(start_path)` - Find config by walking up directory tree

**Dataclasses:**
- `ReviewConfig` - Complete review configuration
- `RepoConfig` - Repository settings (language, profile)
- `CommandsConfig` - Test, lint, typecheck, format, build commands
- `SecurityConfig` - Dependency, secret, and SAST scan commands
- `PolicyConfig` - Review policy settings

### 2. `language_detector.py` - Auto-detect Repo Language

Automatically detects repository language from file presence.

**Key Functions:**
- `detect_language(repo_path)` - Detect primary language
- `detect_monorepo_structure(repo_path)` - Find packages in monorepo
- `get_recommended_commands(language)` - Get recommended commands per language
- `suggest_review_yaml(repo_path)` - Generate suggested config

**Supported Languages:**
- Python (`requirements.txt`, `pyproject.toml`, `setup.py`, `Pipfile`)
- Rust (`Cargo.toml`, `Cargo.lock`)
- Node.js (`package.json`, `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`)
- Go (`go.mod`, `go.sum`)
- Java (`pom.xml`, `build.gradle`)
- Mixed (multiple languages detected)

**Monorepo Detection:**
- npm workspaces
- Cargo workspaces
- Poetry packages
- PDM/Hatch monorepos

### 3. `command_runner.py` - Execute Commands from Config

Executes commands and aggregates results.

**Key Classes:**
- `CommandRunner` - Execute and manage commands
- `CommandResult` - Individual command result
- `RunSummary` - Aggregated execution summary

**Key Methods:**
- `run_command(cmd, category)` - Run single command
- `run_test_commands(commands)` - Execute test suite
- `run_lint_commands(commands)` - Run linters
- `run_security_scans(...)` - Run security checks
- `run_all_from_config(config)` - Run all configured commands

### 4. `profiles.py` - Review Profiles

Predefined review strictness profiles.

**Profiles:**
- `STANDARD` - Default strictness (essential checks)
- `STRICT` - Maximum checks for critical codebases
- `LENIENT` - Minimal checks for rapid prototyping
- `MINIMAL` - Security scans only (fastest)
- `SECURITY_FOCUSED` - Security-first with moderate quality checks

**Key Functions:**
- `get_profile(level)` - Get profile by level
- `list_profiles()` - List all available profiles
- `create_custom_profile(name, base, overrides)` - Create custom profile
- `should_run_check(profile, check_type)` - Check if check should run

## Example Configurations

See `examples/` directory for sample configs:

- `python-review.yaml` - Python projects (pytest, ruff, black, mypy, pip-audit)
- `rust-review.yaml` - Rust projects (cargo test, clippy, audit, fmt)
- `node-review.yaml` - Node.js projects (npm test, eslint, tsc, npm audit)
- `mixed-review.yaml` - Multi-language monorepos

## Usage

```python
from shared.config import (
    parse_review_yaml,
    validate_config,
    detect_language,
    CommandRunner,
    get_profile,
)

# Parse configuration
with open(".openclaw/review.yaml") as f:
    config = parse_review_yaml(f.read())

# Validate
errors = validate_config(config)
if errors:
    print("Validation errors:", errors)

# Detect language
lang_result = detect_language(".")
print(f"Primary language: {lang_result.primary_language}")

# Run commands
runner = CommandRunner()
summary = await runner.run_all_from_config(config)
print(format_summary(summary))

# Get profile
profile = get_profile("STRICT")
print(f"Review profile: {profile.name}")
```

## Review.yaml Schema

```yaml
repo:
  language: mixed  # python, rust, node, go, java, mixed
  profile_default: STANDARD  # STANDARD, STRICT, LENIENT, MINIMAL, SECURITY_FOCUSED

commands:
  test:
    - "pytest -q"
    - "cargo test"
  lint:
    - "ruff check ."
    - "cargo clippy"
  typecheck:
    - "mypy ."
  format:
    - "black --check ."
  build:
    - "cargo build --release"

security:
  dependency_scan:
    - "cargo audit"
    - "pip-audit"
  secret_scan:
    - "gitleaks detect"
  sast_scan:
    - "bandit -r ."

policy:
  allow_warn_merge: false
  fail_on_warn_over: 10
  require_approval: true
  max_review_time_minutes: 30
```

## Testing

Run tests with pytest:

```bash
cd /home/ryan/openclaw-orchestration-stack
python3 -m pytest shared/config/tests/ -v
```

All 123 tests pass.
