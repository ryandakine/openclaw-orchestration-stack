"""DevClaw Runner package."""

# Use absolute imports to avoid issues with hyphen in package name
import sys
from pathlib import Path

# Add src to path for absolute imports
_src_path = str(Path(__file__).parent / "src")
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

# Now import from src
from worker import DevClawWorker, WorkerConfig, create_worker
from git_ops import GitOperations, GitConfig
from task_executor import TaskExecutor, ExecutionResult

__version__ = "1.0.0"

__all__ = [
    'DevClawWorker',
    'WorkerConfig',
    'create_worker',
    'GitOperations',
    'GitConfig',
    'TaskExecutor',
    'ExecutionResult',
]
