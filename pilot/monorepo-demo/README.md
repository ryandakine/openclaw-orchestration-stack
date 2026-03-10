# OpenClaw Monorepo Demo

This is a demonstration of a mixed-language monorepo using the OpenClaw Orchestration Stack.

## Structure

```
monorepo-demo/
├── apps/
│   ├── frontend/     # React application (Node.js)
│   └── backend/      # Flask API (Python)
├── libs/
│   └── shared/       # Shared library (Rust)
└── .openclaw/
    └── review.yaml   # OpenClaw review configuration
```

## Workspaces

### Frontend (apps/frontend)
- **Language**: Node.js / React
- **Commands**:
  - `npm test` - Run tests
  - `npm run lint` - Lint code
  - `npm run build` - Build application

### Backend (apps/backend)
- **Language**: Python / Flask
- **Commands**:
  - `pytest` - Run tests
  - `ruff check .` - Lint code
  - `mypy .` - Type check

### Shared (libs/shared)
- **Language**: Rust
- **Commands**:
  - `cargo test` - Run tests
  - `cargo clippy` - Lint code
  - `cargo build` - Build library

## Usage

### Detect Workspace Structure

```python
from shared.config.language_detector import get_workspace_packages

packages = get_workspace_packages(".")
for name, info in packages.items():
    print(f"{name}: {info['language']} at {info['path']}")
```

### Run Commands for All Workspaces

```python
from shared.config.command_runner import CommandRunner
import asyncio

runner = CommandRunner()
workspaces = {
    "frontend": {
        "path": "apps/frontend",
        "language": "node",
        "commands": {"test": ["npm test"]}
    },
    "backend": {
        "path": "apps/backend",
        "language": "python",
        "commands": {"test": ["pytest"]}
    }
}

summary = asyncio.run(runner.run_all_workspaces(workspaces))
print(summary)
```

### Selective Testing

Only test workspaces that have changed:

```python
from shared.config.command_runner import detect_changed_workspaces

changed_files = ["apps/frontend/src/App.jsx"]
workspaces = {...}  # All workspaces

changed = detect_changed_workspaces(".", workspaces, changed_files)
# Returns: {'frontend': {...}, 'shared': {...}}
```

## OpenClaw Configuration

The `.openclaw/review.yaml` file defines:

- Workspace configurations per package
- Language-specific commands
- Security scan settings
- Policy settings
- Monorepo-specific options (selective testing, parallel execution)
