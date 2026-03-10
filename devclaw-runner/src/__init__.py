"""
DevClaw Runner - Worker execution engine for OpenClaw Orchestration Stack.

This package provides the worker implementation for executing implementation tasks.
"""

from worker import DevClawWorker, WorkerConfig, create_worker, TaskClaimError, TaskExecutionError
from git_ops import GitOperations, GitConfig, GitError
from task_executor import TaskExecutor, CodeChangeApplier, TestRunner, ExecutionResult, CodeChange

__version__ = "1.0.0"

__all__ = [
    # Worker
    'DevClawWorker',
    'WorkerConfig',
    'create_worker',
    'TaskClaimError',
    'TaskExecutionError',
    # Git Operations
    'GitOperations',
    'GitConfig',
    'GitError',
    # Task Executor
    'TaskExecutor',
    'CodeChangeApplier',
    'TestRunner',
    'ExecutionResult',
    'CodeChange',
]
