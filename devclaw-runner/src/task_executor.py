"""
Task Execution Module

Handles the execution of implementation tasks including applying code changes,
running tests, and handling failures.
"""

import json
import logging
import os
import re
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union

logger = logging.getLogger(__name__)


class TaskExecutionError(Exception):
    """Raised when task execution fails."""
    pass


class CodeChangeError(TaskExecutionError):
    """Raised when code changes cannot be applied."""
    pass


class TestFailureError(TaskExecutionError):
    """Raised when tests fail."""
    pass


@dataclass
class ExecutionResult:
    """Result of task execution."""
    success: bool
    files_changed: List[str] = field(default_factory=list)
    no_changes: bool = False
    test_results: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'files_changed': self.files_changed,
            'no_changes': self.no_changes,
            'test_results': self.test_results,
            'error_message': self.error_message,
            'metadata': self.metadata
        }


@dataclass
class CodeChange:
    """Represents a single code change operation."""
    operation: str  # 'create', 'modify', 'delete', 'append', 'replace'
    file_path: str
    content: Optional[str] = None
    old_content: Optional[str] = None  # For replace operations
    position: Optional[str] = None  # 'start', 'end', 'after', 'before'
    target: Optional[str] = None  # Target for after/before positioning
    
    def validate(self) -> bool:
        """Validate the change operation."""
        if not self.file_path:
            raise ValueError("file_path is required")
        
        valid_operations = ['create', 'modify', 'delete', 'append', 'replace']
        if self.operation not in valid_operations:
            raise ValueError(f"Invalid operation: {self.operation}")
        
        if self.operation in ['create', 'modify', 'append'] and self.content is None:
            raise ValueError(f"content is required for {self.operation} operation")
        
        if self.operation == 'replace' and self.old_content is None:
            raise ValueError("old_content is required for replace operation")
        
        return True


class CodeChangeApplier:
    """
    Applies code changes to files in a working directory.
    
    Supports:
    - Creating new files
    - Modifying existing files
    - Deleting files
    - Appending content
    - Replacing content (search and replace)
    """
    
    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)
        self.files_changed: List[str] = []
    
    def apply_changes(self, changes: List[CodeChange]) -> List[str]:
        """
        Apply a list of code changes.
        
        Args:
            changes: List of CodeChange objects
            
        Returns:
            List of file paths that were changed
        """
        self.files_changed = []
        
        for change in changes:
            try:
                change.validate()
                self._apply_single_change(change)
            except Exception as e:
                logger.error(f"Failed to apply change to {change.file_path}: {e}")
                raise CodeChangeError(f"Failed to apply change to {change.file_path}: {e}") from e
        
        return self.files_changed
    
    def _apply_single_change(self, change: CodeChange):
        """Apply a single code change."""
        file_path = self.work_dir / change.file_path
        
        if change.operation == 'create':
            self._create_file(file_path, change.content)
        elif change.operation == 'modify':
            self._modify_file(file_path, change.content)
        elif change.operation == 'delete':
            self._delete_file(file_path)
        elif change.operation == 'append':
            self._append_to_file(file_path, change.content, change.position, change.target)
        elif change.operation == 'replace':
            self._replace_in_file(file_path, change.old_content, change.content)
        
        # Track the change
        rel_path = str(file_path.relative_to(self.work_dir))
        if rel_path not in self.files_changed:
            self.files_changed.append(rel_path)
    
    def _create_file(self, file_path: Path, content: str):
        """Create a new file with content."""
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        if file_path.exists():
            logger.warning(f"File already exists, will overwrite: {file_path}")
        
        file_path.write_text(content, encoding='utf-8')
        logger.info(f"Created file: {file_path}")
    
    def _modify_file(self, file_path: Path, content: str):
        """Modify (overwrite) an existing file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        
        file_path.write_text(content, encoding='utf-8')
        logger.info(f"Modified file: {file_path}")
    
    def _delete_file(self, file_path: Path):
        """Delete a file."""
        if not file_path.exists():
            logger.warning(f"File does not exist, skipping delete: {file_path}")
            return
        
        file_path.unlink()
        logger.info(f"Deleted file: {file_path}")
    
    def _append_to_file(
        self,
        file_path: Path,
        content: str,
        position: Optional[str] = None,
        target: Optional[str] = None
    ):
        """Append content to a file."""
        if not file_path.exists():
            # Create the file if it doesn't exist
            self._create_file(file_path, content)
            return
        
        existing_content = file_path.read_text(encoding='utf-8')
        
        if position == 'start':
            new_content = content + existing_content
        elif position == 'after' and target:
            # Insert after the target string
            if target in existing_content:
                new_content = existing_content.replace(
                    target,
                    target + content
                )
            else:
                raise ValueError(f"Target not found in file: {target}")
        elif position == 'before' and target:
            # Insert before the target string
            if target in existing_content:
                new_content = existing_content.replace(
                    target,
                    content + target
                )
            else:
                raise ValueError(f"Target not found in file: {target}")
        else:
            # Default: append to end
            new_content = existing_content + content
        
        file_path.write_text(new_content, encoding='utf-8')
        logger.info(f"Appended content to file: {file_path}")
    
    def _replace_in_file(self, file_path: Path, old_content: str, new_content: str):
        """Replace content in a file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        
        existing_content = file_path.read_text(encoding='utf-8')
        
        if old_content not in existing_content:
            raise ValueError(f"Content to replace not found in file: {old_content[:50]}...")
        
        updated_content = existing_content.replace(old_content, new_content)
        file_path.write_text(updated_content, encoding='utf-8')
        logger.info(f"Replaced content in file: {file_path}")


class TestRunner:
    """
    Runs tests in the working directory.
    
    Supports multiple test frameworks and configurable commands.
    """
    
    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir)
    
    def detect_test_framework(self) -> Optional[str]:
        """Auto-detect the test framework used in the project."""
        work_path = Path(self.work_dir)
        
        # Check for Python pytest
        if (work_path / 'pytest.ini').exists() or \
           (work_path / 'pyproject.toml').exists() or \
           (work_path / 'setup.py').exists() or \
           (work_path / 'setup.cfg').exists():
            # Check if pytest is available
            if self._command_exists('pytest'):
                return 'pytest'
        
        # Check for Python unittest
        if list(work_path.glob('**/test_*.py')) or list(work_path.glob('**/*_test.py')):
            if self._command_exists('python') or self._command_exists('python3'):
                return 'unittest'
        
        # Check for Node.js/Jest
        if (work_path / 'package.json').exists():
            package_json = work_path / 'package.json'
            try:
                content = json.loads(package_json.read_text())
                test_script = content.get('scripts', {}).get('test', '')
                if 'jest' in test_script:
                    return 'jest'
                elif 'mocha' in test_script:
                    return 'mocha'
                elif 'vitest' in test_script:
                    return 'vitest'
                elif 'npm' in test_script or 'yarn' in test_script:
                    return 'npm'
            except (json.JSONDecodeError, IOError):
                pass
        
        # Check for Java/Maven
        if (work_path / 'pom.xml').exists():
            return 'maven'
        
        # Check for Java/Gradle
        if (work_path / 'build.gradle').exists() or (work_path / 'build.gradle.kts').exists():
            return 'gradle'
        
        # Check for Go
        if (work_path / 'go.mod').exists():
            return 'go'
        
        # Check for Rust
        if (work_path / 'Cargo.toml').exists():
            return 'cargo'
        
        return None
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH."""
        try:
            subprocess.run(
                ['which', command],
                capture_output=True,
                check=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def run_tests(
        self,
        framework: Optional[str] = None,
        command: Optional[str] = None,
        timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Run tests and return results.
        
        Args:
            framework: Test framework to use (auto-detected if None)
            command: Custom test command (overrides framework)
            timeout: Test timeout in seconds
            
        Returns:
            Dict with test results
        """
        if command:
            return self._run_custom_command(command, timeout)
        
        if not framework:
            framework = self.detect_test_framework()
        
        if not framework:
            logger.warning("No test framework detected, skipping tests")
            return {
                'success': True,
                'skipped': True,
                'message': 'No test framework detected'
            }
        
        test_commands = {
            'pytest': ['pytest', '-v', '--tb=short'],
            'unittest': ['python', '-m', 'unittest', 'discover', '-v'],
            'jest': ['npm', 'test'],
            'mocha': ['npm', 'test'],
            'vitest': ['npm', 'test'],
            'npm': ['npm', 'test'],
            'maven': ['mvn', 'test'],
            'gradle': ['gradle', 'test'],
            'go': ['go', 'test', './...'],
            'cargo': ['cargo', 'test']
        }
        
        cmd = test_commands.get(framework)
        if not cmd:
            raise TestFailureError(f"Unknown test framework: {framework}")
        
        return self._run_command(cmd, timeout)
    
    def _run_command(self, cmd: List[str], timeout: int) -> Dict[str, Any]:
        """Run a command and return results."""
        logger.info(f"Running tests: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            success = result.returncode == 0
            
            return {
                'success': success,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"Tests timed out after {timeout}s")
            raise TestFailureError(f"Tests timed out after {timeout}s") from e
        except subprocess.SubprocessError as e:
            logger.error(f"Failed to run tests: {e}")
            raise TestFailureError(f"Failed to run tests: {e}") from e
    
    def _run_custom_command(self, command: str, timeout: int) -> Dict[str, Any]:
        """Run a custom test command."""
        import shlex
        cmd = shlex.split(command)
        return self._run_command(cmd, timeout)


class TaskExecutor:
    """
    Main task executor that coordinates code changes and test execution.
    
    Features:
    - Apply code changes from task payload
    - Run tests
    - Handle failures with rollback capability
    """
    
    def __init__(self):
        self.change_applier: Optional[CodeChangeApplier] = None
        self.test_runner: Optional[TestRunner] = None
    
    def execute(
        self,
        work_dir: str,
        intent: str,
        payload: Dict[str, Any]
    ) -> ExecutionResult:
        """
        Execute a task.
        
        Args:
            work_dir: Working directory for the task
            intent: Task intent description
            payload: Task payload with changes and configuration
            
        Returns:
            ExecutionResult with execution details
        """
        self.change_applier = CodeChangeApplier(work_dir)
        self.test_runner = TestRunner(work_dir)
        
        try:
            # Extract changes from payload
            changes = self._parse_changes(payload)
            
            if not changes:
                logger.info("No code changes specified in task")
                return ExecutionResult(
                    success=True,
                    no_changes=True,
                    metadata={'intent': intent}
                )
            
            # Apply code changes
            logger.info(f"Applying {len(changes)} code changes")
            files_changed = self.change_applier.apply_changes(changes)
            
            # Run tests if configured
            test_results = None
            run_tests = payload.get('run_tests', True)
            
            if run_tests:
                test_framework = payload.get('test_framework')
                test_command = payload.get('test_command')
                
                try:
                    test_results = self.test_runner.run_tests(
                        framework=test_framework,
                        command=test_command
                    )
                    
                    if not test_results.get('success', False):
                        # Tests failed
                        return ExecutionResult(
                            success=False,
                            files_changed=files_changed,
                            test_results=test_results,
                            error_message="Tests failed",
                            metadata={'intent': intent}
                        )
                        
                except TestFailureError as e:
                    return ExecutionResult(
                        success=False,
                        files_changed=files_changed,
                        error_message=str(e),
                        metadata={'intent': intent}
                    )
            
            return ExecutionResult(
                success=True,
                files_changed=files_changed,
                test_results=test_results,
                metadata={'intent': intent}
            )
            
        except Exception as e:
            logger.exception(f"Task execution failed: {e}")
            return ExecutionResult(
                success=False,
                error_message=str(e),
                metadata={'intent': intent}
            )
    
    def _parse_changes(self, payload: Dict[str, Any]) -> List[CodeChange]:
        """
        Parse code changes from task payload.
        
        Supports multiple formats:
        - 'changes': List of change dicts
        - 'files': Dict of file paths to content
        - 'patches': List of patch strings
        """
        changes = []
        
        # Format 1: Explicit changes list
        if 'changes' in payload:
            for change_dict in payload['changes']:
                changes.append(CodeChange(**change_dict))
        
        # Format 2: Simple files dict
        elif 'files' in payload:
            for file_path, content in payload['files'].items():
                changes.append(CodeChange(
                    operation='create' if isinstance(content, str) else content.get('operation', 'create'),
                    file_path=file_path,
                    content=content if isinstance(content, str) else content.get('content')
                ))
        
        # Format 3: Patches
        elif 'patches' in payload:
            # TODO: Implement patch parsing
            logger.warning("Patch format not yet implemented")
        
        return changes
    
    def handle_failure(
        self,
        work_dir: str,
        error: Exception,
        cleanup: bool = True
    ) -> Dict[str, Any]:
        """
        Handle task execution failure.
        
        Args:
            work_dir: Working directory
            error: The error that occurred
            cleanup: Whether to cleanup the work directory
            
        Returns:
            Dict with failure details
        """
        logger.error(f"Handling task failure: {error}")
        
        result = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'work_dir': work_dir,
            'cleanup_performed': False
        }
        
        if cleanup:
            try:
                import shutil
                if os.path.exists(work_dir):
                    shutil.rmtree(work_dir)
                    result['cleanup_performed'] = True
                    logger.info(f"Cleaned up work directory: {work_dir}")
            except Exception as cleanup_error:
                logger.error(f"Cleanup failed: {cleanup_error}")
                result['cleanup_error'] = str(cleanup_error)
        
        return result


# Plugin system for custom task handlers

class TaskHandler(ABC):
    """Abstract base class for custom task handlers."""
    
    @abstractmethod
    def can_handle(self, task_type: str) -> bool:
        """Check if this handler can handle the given task type."""
        pass
    
    @abstractmethod
    def execute(self, work_dir: str, payload: Dict[str, Any]) -> ExecutionResult:
        """Execute the task."""
        pass


class TaskHandlerRegistry:
    """Registry for custom task handlers."""
    
    def __init__(self):
        self._handlers: List[TaskHandler] = []
    
    def register(self, handler: TaskHandler):
        """Register a task handler."""
        self._handlers.append(handler)
        logger.info(f"Registered task handler: {type(handler).__name__}")
    
    def get_handler(self, task_type: str) -> Optional[TaskHandler]:
        """Get a handler for the given task type."""
        for handler in self._handlers:
            if handler.can_handle(task_type):
                return handler
        return None


# Global registry instance
_handler_registry = TaskHandlerRegistry()


def register_task_handler(handler: TaskHandler):
    """Register a custom task handler."""
    _handler_registry.register(handler)


def get_task_handler(task_type: str) -> Optional[TaskHandler]:
    """Get a handler for the given task type."""
    return _handler_registry.get_handler(task_type)
