"""
Unit tests for DevClaw Worker.

Tests cover:
- Worker initialization and configuration
- Task claiming and releasing
- Lease extension
- Task execution flow
- Health checks
- Signal handling
"""

import json
import os
import signal
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add project root and devclaw-runner src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from shared.db import init_pool, close_pool, get_connection, execute, insert, get_task_by_id
from worker import (
    DevClawWorker,
    WorkerConfig,
    create_worker,
    TaskClaimError,
    TaskExecutionError
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    import sqlite3
    
    # Register a custom converter for timestamps that handles ISO format
    # The default converter expects "YYYY-MM-DD HH:MM:SS" but we use ISO format
    def convert_timestamp(val):
        val = val.decode() if isinstance(val, bytes) else val
        # Just return as string, let the caller parse if needed
        return val
    
    # Override the default timestamp converter before creating connections
    sqlite3.register_converter("timestamp", convert_timestamp)
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    # Initialize pool with temp database
    init_pool(db_path=db_path, max_connections=5)
    
    # Load schema
    schema_path = Path(__file__).parent.parent.parent / "shared" / "schemas" / "schema.sql"
    with get_connection() as conn:
        conn.executescript(schema_path.read_text())
        conn.commit()
    
    yield db_path
    
    # Cleanup
    close_pool()
    os.unlink(db_path)


@pytest.fixture
def worker_config(temp_db):
    """Create a worker configuration for testing."""
    return WorkerConfig(
        worker_id=f"test-worker-{uuid.uuid4().hex[:8]}",
        db_path=temp_db,
        poll_interval=1,
        lease_duration=60,
        git_base_path=tempfile.mkdtemp(prefix="devclaw-test-")
    )


@pytest.fixture
def worker(worker_config):
    """Create a DevClaw worker for testing."""
    w = DevClawWorker(worker_config)
    yield w
    # Cleanup
    w.running = False
    if w.current_work_dir and os.path.exists(w.current_work_dir):
        import shutil
        shutil.rmtree(w.current_work_dir)


@pytest.fixture
def sample_task_payload():
    """Create a sample task payload."""
    return {
        'repo_url': 'https://github.com/example/repo.git',
        'branch': 'main',
        'files': {
            'test.txt': {'operation': 'create', 'content': 'Hello World'}
        }
    }


def create_test_task(
    task_id: str = None,
    status: str = 'queued',
    assigned_to: str = 'DEVCLAW',
    payload: dict = None,
    claimed_by: str = None,
    lease_expires: datetime = None
):
    """Helper to create a test task."""
    task_id = task_id or str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    
    task_data = {
        'id': task_id,
        'correlation_id': correlation_id,
        'idempotency_key': str(uuid.uuid4()),
        'status': status,
        'assigned_to': assigned_to,
        'intent': 'Test task intent',
        'payload': json.dumps(payload or {'repo_url': 'https://example.com/repo.git'})
    }
    
    if claimed_by:
        task_data['claimed_by'] = claimed_by
        task_data['claimed_at'] = datetime.utcnow().isoformat()
        task_data['lease_expires_at'] = (lease_expires or datetime.utcnow() + timedelta(minutes=5)).isoformat()
    
    insert('tasks', task_data)
    return task_id


class TestWorkerInitialization:
    """Tests for worker initialization."""
    
    def test_worker_creation(self, worker_config):
        """Test worker can be created with valid config."""
        worker = DevClawWorker(worker_config)
        assert worker.config.worker_id == worker_config.worker_id
        assert worker.running is False
        assert worker.current_task is None
    
    def test_create_worker_factory(self, temp_db):
        """Test the create_worker factory function."""
        worker = create_worker(
            worker_id='test-factory',
            db_path=temp_db,
            poll_interval=10
        )
        assert worker.config.worker_id == 'test-factory'
        assert worker.config.poll_interval == 10
    
    def test_worker_auto_generates_id(self, temp_db):
        """Test worker auto-generates ID if not provided."""
        worker = create_worker(db_path=temp_db)
        assert worker.config.worker_id.startswith('devclaw-')
        assert len(worker.config.worker_id) > 8


class TestTaskClaiming:
    """Tests for task claiming functionality."""
    
    def test_claim_available_task(self, worker, temp_db):
        """Test claiming an available queued task."""
        task_id = create_test_task()
        
        result = worker._claim_task(task_id)
        
        assert result is True
        
        # Verify task was claimed
        task = get_task_by_id(task_id)
        assert task['claimed_by'] == worker.config.worker_id
        assert task['status'] == 'executing'
        assert task['lease_expires_at'] is not None
    
    def test_claim_already_claimed_task(self, worker, temp_db):
        """Test claiming a task already claimed by another worker."""
        other_worker = 'other-worker'
        lease_expires = datetime.utcnow() + timedelta(minutes=5)
        task_id = create_test_task(claimed_by=other_worker, lease_expires=lease_expires)
        
        result = worker._claim_task(task_id)
        
        assert result is False
        
        # Verify task still claimed by other worker
        task = get_task_by_id(task_id)
        assert task['claimed_by'] == other_worker
    
    def test_claim_expired_lease(self, worker, temp_db):
        """Test claiming a task with expired lease."""
        other_worker = 'other-worker'
        expired_lease = datetime.utcnow() - timedelta(minutes=1)
        task_id = create_test_task(
            claimed_by=other_worker,
            lease_expires=expired_lease
        )
        
        result = worker._claim_task(task_id)
        
        assert result is True
        
        # Verify task now claimed by our worker
        task = get_task_by_id(task_id)
        assert task['claimed_by'] == worker.config.worker_id
    
    def test_claim_nonexistent_task(self, worker, temp_db):
        """Test claiming a task that doesn't exist."""
        result = worker._claim_task('nonexistent-task-id')
        
        assert result is False


class TestLeaseExtension:
    """Tests for lease extension functionality."""
    
    def test_extend_lease(self, worker, temp_db):
        """Test extending a task lease."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        
        # Set initial lease
        with get_connection() as conn:
            initial_expires = datetime.utcnow() + timedelta(seconds=30)
            conn.execute(
                "UPDATE tasks SET lease_expires_at = ? WHERE id = ?",
                (initial_expires.isoformat(), task_id)
            )
            conn.commit()
        
        # Extend lease
        result = worker._extend_lease(task_id)
        assert result is True
        
        # Verify lease was extended
        task = get_task_by_id(task_id)
        new_expires = datetime.fromisoformat(task['lease_expires_at'])
        assert new_expires > initial_expires
    
    def test_extend_lease_not_claimed_by_us(self, worker, temp_db):
        """Test extending a lease for a task claimed by another worker."""
        task_id = create_test_task(claimed_by='other-worker')
        
        result = worker._extend_lease(task_id)
        assert result is False


class TestTaskRelease:
    """Tests for task release functionality."""
    
    def test_release_task(self, worker, temp_db):
        """Test releasing a claimed task."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        
        worker._release_task(task_id, reason="Test release")
        
        # Verify task was released
        task = get_task_by_id(task_id)
        assert task['claimed_by'] is None
        assert task['status'] == 'queued'
        assert task['lease_expires_at'] is None
    
    def test_release_task_not_claimed_by_us(self, worker, temp_db):
        """Test releasing a task not claimed by us."""
        task_id = create_test_task(claimed_by='other-worker')
        
        # Should not raise, just log warning
        worker._release_task(task_id, reason="Test release")


class TestTaskCompletion:
    """Tests for task completion functionality."""
    
    def test_mark_task_completed(self, worker, temp_db):
        """Test marking a task as completed."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        
        result = {'success': True, 'files_changed': ['test.py']}
        worker._mark_task_completed(task_id, result)
        
        # Verify task was marked completed
        task = get_task_by_id(task_id)
        assert task['status'] == 'review_queued'
        assert task['claimed_by'] is None
        assert task['completed_at'] is not None
    
    def test_mark_task_failed_with_retry(self, worker, temp_db):
        """Test marking a task as failed with retry."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        
        worker._mark_task_failed(task_id, "Test error", retry=True)
        
        # Verify task was marked for retry
        task = get_task_by_id(task_id)
        assert task['status'] == 'queued'
        assert task['retry_count'] == 1
        assert task['claimed_by'] is None
    
    def test_mark_task_failed_permanently(self, worker, temp_db):
        """Test marking a task as failed permanently."""
        task_id = create_test_task(
            claimed_by=worker.config.worker_id,
            payload={'max_retries': 1}
        )
        
        # First failure - should queue for retry
        worker._mark_task_failed(task_id, "First error", retry=True)
        task = get_task_by_id(task_id)
        assert task['status'] == 'queued'
        assert task['retry_count'] == 1
        
        # Re-claim and fail again - should go to DLQ
        # Update max_retries on the task row itself (not just payload)
        with get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET claimed_by = ?, retry_count = 1, max_retries = 1 WHERE id = ?",
                (worker.config.worker_id, task_id)
            )
            conn.commit()
        
        worker._mark_task_failed(task_id, "Second error", retry=True)
        
        # Verify task was marked failed
        task = get_task_by_id(task_id)
        assert task['status'] == 'failed'


class TestTaskPolling:
    """Tests for task polling functionality."""
    
    def test_get_available_tasks(self, worker, temp_db):
        """Test getting available tasks."""
        # Create some tasks
        task1 = create_test_task(status='queued')
        task2 = create_test_task(status='queued')
        
        # Create a claimed task (should not be returned)
        task3 = create_test_task(
            status='queued',
            claimed_by='other-worker',
            lease_expires=datetime.utcnow() + timedelta(minutes=5)
        )
        
        tasks = worker._get_available_tasks(limit=10)
        
        assert len(tasks) == 2
        task_ids = {t['id'] for t in tasks}
        assert task1 in task_ids
        assert task2 in task_ids
        assert task3 not in task_ids
    
    def test_get_available_tasks_empty(self, worker, temp_db):
        """Test getting available tasks when none exist."""
        tasks = worker._get_available_tasks(limit=10)
        assert tasks == []
    
    def test_get_available_tasks_excludes_non_queued(self, worker, temp_db):
        """Test that non-queued tasks are excluded."""
        # Create tasks with different statuses (use valid status values from schema)
        create_test_task(status='executing')
        create_test_task(status='failed')
        create_test_task(status='merged')  # 'merged' is the terminal state, not 'completed'
        create_test_task(status='queued')  # Only this one should be returned
        
        tasks = worker._get_available_tasks(limit=10)
        
        assert len(tasks) == 1
        assert tasks[0]['status'] == 'queued'


class TestHealthCheck:
    """Tests for health check functionality."""
    
    def test_health_check_idle(self, worker):
        """Test health check when idle."""
        health = worker.health_check()
        
        assert health['worker_id'] == worker.config.worker_id
        assert health['running'] is False
        assert health['current_task'] is None
        assert health['current_work_dir'] is None
        assert 'timestamp' in health
    
    def test_health_check_busy(self, worker, temp_db):
        """Test health check when processing a task."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        worker.current_task = get_task_by_id(task_id)
        worker.running = True
        
        health = worker.health_check()
        
        assert health['running'] is True
        assert health['current_task'] == task_id


class TestSignalHandling:
    """Tests for signal handling."""
    
    def test_sigterm_handler(self, worker, temp_db):
        """Test SIGTERM handler releases task."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        worker.current_task = get_task_by_id(task_id)
        worker.running = True
        
        # Simulate SIGTERM
        worker._handle_sigterm(signal.SIGTERM, None)
        
        assert worker.running is False
        
        # Verify task was released
        task = get_task_by_id(task_id)
        assert task['claimed_by'] is None
        assert task['status'] == 'queued'
    
    def test_sigint_handler(self, worker, temp_db):
        """Test SIGINT handler releases task."""
        task_id = create_test_task(claimed_by=worker.config.worker_id)
        worker.current_task = get_task_by_id(task_id)
        worker.running = True
        
        # Simulate SIGINT
        worker._handle_sigterm(signal.SIGINT, None)
        
        assert worker.running is False


class TestTaskExecution:
    """Tests for task execution."""
    
    @patch('worker.GitOperations')
    @patch('worker.TaskExecutor')
    def test_execute_task_success(self, mock_executor_class, mock_git_class, worker, temp_db, sample_task_payload):
        """Test successful task execution."""
        # Setup mocks
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        
        mock_executor = MagicMock()
        mock_executor_class.return_value = mock_executor
        mock_executor.execute.return_value = {
            'success': True,
            'files_changed': ['test.txt']
        }
        
        # Re-initialize worker with mocks
        worker.git_ops = mock_git
        worker.task_executor = mock_executor
        
        task = {
            'id': 'test-task',
            'intent': 'Test task',
            'payload': json.dumps(sample_task_payload)
        }
        
        result = worker._execute_task(task)
        
        assert result['success'] is True
        assert 'work_dir' in result
        mock_git.clone_repo.assert_called_once()
        mock_git.commit_changes.assert_called_once()
        mock_git.push_changes.assert_called_once()
    
    @patch('worker.GitOperations')
    def test_execute_task_no_repo_url(self, mock_git_class, worker, temp_db):
        """Test task execution fails without repo_url."""
        mock_git = MagicMock()
        mock_git_class.return_value = mock_git
        worker.git_ops = mock_git
        
        task = {
            'id': 'test-task',
            'intent': 'Test task',
            'payload': json.dumps({})  # No repo_url
        }
        
        with pytest.raises(TaskExecutionError):
            worker._execute_task(task)


class TestRunSingleIteration:
    """Tests for the run_single_iteration method."""
    
    @patch.object(DevClawWorker, '_claim_task')
    @patch.object(DevClawWorker, '_execute_task')
    @patch.object(DevClawWorker, '_mark_task_completed')
    def test_run_single_iteration_success(
        self, mock_mark_completed, mock_execute, mock_claim, worker, temp_db
    ):
        """Test successful single iteration."""
        # Create a task
        task_id = create_test_task()
        
        # Setup mocks
        mock_claim.return_value = True
        mock_execute.return_value = {'success': True}
        
        result = worker.run_single_iteration()
        
        assert result is True
        mock_claim.assert_called_once_with(task_id)
        mock_execute.assert_called_once()
        mock_mark_completed.assert_called_once()
    
    def test_run_single_iteration_no_tasks(self, worker, temp_db):
        """Test single iteration when no tasks available."""
        result = worker.run_single_iteration()
        
        assert result is False


class TestCleanup:
    """Tests for cleanup functionality."""
    
    def test_cleanup_work_dir(self, worker):
        """Test cleanup of working directory."""
        # Create a temp directory
        work_dir = tempfile.mkdtemp()
        test_file = Path(work_dir) / "test.txt"
        test_file.write_text("test")
        
        worker.current_work_dir = work_dir
        
        worker._cleanup_work_dir()
        
        assert not os.path.exists(work_dir)
        assert worker.current_work_dir is None
    
    def test_cleanup_nonexistent_dir(self, worker):
        """Test cleanup when directory doesn't exist."""
        worker.current_work_dir = "/nonexistent/path"
        
        # Should not raise
        worker._cleanup_work_dir()
        
        assert worker.current_work_dir is None
