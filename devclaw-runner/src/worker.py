"""
DevClaw Runner - Main Worker Class

Polls task queue, claims tasks atomically, executes them, and handles cleanup.
"""

import json
import logging
import os
import signal
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.db import (
    get_connection,
    transaction,
    execute,
    insert,
    update,
    get_task_by_id,
)
from git_ops import GitOperations
from task_executor import TaskExecutor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """Configuration for the DevClaw worker."""
    worker_id: str
    db_path: str
    poll_interval: int = 5  # seconds
    lease_duration: int = 300  # 5 minutes
    lease_extension_buffer: int = 60  # Extend lease 1 min before expiry
    max_retries: int = 3
    retry_base_delay: float = 1.0
    git_base_path: str = "/tmp/devclaw-repos"
    health_check_port: Optional[int] = None
    sigterm_timeout: int = 30  # seconds to graceful shutdown


class TaskClaimError(Exception):
    """Raised when task claim fails."""
    pass


class TaskExecutionError(Exception):
    """Raised when task execution fails."""
    pass


class DevClawWorker:
    """
    Main worker class for executing implementation tasks.
    
    Features:
    - Polls task queue for queued tasks
    - Atomically claims tasks with lease metadata
    - Checks out git repos and makes code changes
    - Commits and pushes changes
    - Notifies completion
    - Handles retries and cleanup
    - Supports lease extension while working
    - Safe cleanup on crash/SIGTERM
    """
    
    def __init__(self, config: WorkerConfig):
        self.config = config
        self.running = False
        self.current_task: Optional[Dict[str, Any]] = None
        self.current_work_dir: Optional[str] = None
        self.git_ops = GitOperations()
        self.task_executor = TaskExecutor()
        self._shutdown_event = threading.Event()
        self._lease_extension_thread: Optional[threading.Thread] = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        
        # Ensure git base path exists
        Path(config.git_base_path).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"DevClaw worker initialized: {config.worker_id}")
    
    def _handle_sigterm(self, signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self._shutdown_event.set()
        self.running = False
        
        # Release current task if any
        if self.current_task:
            self._release_task(
                self.current_task['id'],
                reason=f"Worker shutdown (signal {signum})"
            )
        
        # Wait for cleanup (with timeout)
        if self._lease_extension_thread and self._lease_extension_thread.is_alive():
            self._lease_extension_thread.join(timeout=self.config.sigterm_timeout)
    
    def _get_available_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get available tasks that are queued and not claimed or lease expired.
        
        Uses the v_tasks_available view for efficient querying.
        """
        return execute(
            """
            SELECT * FROM v_tasks_available 
            WHERE assigned_to = 'DEVCLAW'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,)
        )
    
    def _claim_task(self, task_id: str) -> bool:
        """
        Atomically claim a task by updating its lease metadata.
        
        Uses a transaction to ensure atomicity.
        Returns True if claim was successful, False otherwise.
        """
        try:
            now = datetime.utcnow()
            lease_expires = now + timedelta(seconds=self.config.lease_duration)
            
            with transaction() as conn:
                # Try to claim the task atomically
                cursor = conn.execute(
                    """
                    UPDATE tasks 
                    SET claimed_by = ?,
                        claimed_at = ?,
                        lease_expires_at = ?,
                        status = 'executing',
                        updated_at = ?
                    WHERE id = ? 
                      AND status = 'queued'
                      AND (claimed_by IS NULL OR lease_expires_at < ?)
                    """,
                    (
                        self.config.worker_id,
                        now.isoformat(),
                        lease_expires.isoformat(),
                        now.isoformat(),
                        task_id,
                        now.isoformat()
                    )
                )
                
                if cursor.rowcount == 0:
                    logger.warning(f"Failed to claim task {task_id}: already claimed")
                    return False
                
                # Log audit event
                conn.execute(
                    """
                    INSERT INTO audit_events (correlation_id, actor, action, payload)
                    SELECT correlation_id, ?, 'task.claimed', ?
                    FROM tasks WHERE id = ?
                    """,
                    (
                        'devclaw',
                        json.dumps({
                            'task_id': task_id,
                            'worker_id': self.config.worker_id,
                            'lease_expires': lease_expires.isoformat()
                        }),
                        task_id
                    )
                )
            
            logger.info(f"Successfully claimed task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error claiming task {task_id}: {e}")
            return False
    
    def _extend_lease(self, task_id: str) -> bool:
        """Extend the lease for a currently held task."""
        try:
            new_expires = datetime.utcnow() + timedelta(seconds=self.config.lease_duration)
            
            with transaction() as conn:
                cursor = conn.execute(
                    """
                    UPDATE tasks 
                    SET lease_expires_at = ?,
                        updated_at = ?
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (
                        new_expires.isoformat(),
                        datetime.utcnow().isoformat(),
                        task_id,
                        self.config.worker_id
                    )
                )
                
                if cursor.rowcount > 0:
                    logger.debug(f"Extended lease for task {task_id} until {new_expires}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Error extending lease for task {task_id}: {e}")
            return False
    
    def _start_lease_extension(self, task_id: str):
        """Start background thread to extend lease periodically."""
        def extend_loop():
            while (self.running and 
                   self.current_task and 
                   self.current_task['id'] == task_id and
                   not self._shutdown_event.is_set()):
                
                # Sleep for a portion of the lease duration
                sleep_time = self.config.lease_duration - self.config.lease_extension_buffer
                if sleep_time <= 0:
                    sleep_time = self.config.lease_duration // 2
                
                if self._shutdown_event.wait(timeout=sleep_time):
                    break
                
                # Check if we should extend
                if self.current_task and self.current_task['id'] == task_id:
                    self._extend_lease(task_id)
        
        self._lease_extension_thread = threading.Thread(
            target=extend_loop,
            daemon=True
        )
        self._lease_extension_thread.start()
    
    def _release_task(self, task_id: str, reason: str = ""):
        """Release a task back to the queue."""
        try:
            with transaction() as conn:
                conn.execute(
                    """
                    UPDATE tasks 
                    SET claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL,
                        status = 'queued',
                        updated_at = ?
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (datetime.utcnow().isoformat(), task_id, self.config.worker_id)
                )
                
                # Log audit event
                conn.execute(
                    """
                    INSERT INTO audit_events (correlation_id, actor, action, payload)
                    SELECT correlation_id, ?, 'task.released', ?
                    FROM tasks WHERE id = ?
                    """,
                    (
                        'devclaw',
                        json.dumps({
                            'task_id': task_id,
                            'worker_id': self.config.worker_id,
                            'reason': reason
                        }),
                        task_id
                    )
                )
            
            logger.info(f"Released task {task_id}: {reason}")
            
        except Exception as e:
            logger.error(f"Error releasing task {task_id}: {e}")
    
    def _mark_task_completed(self, task_id: str, result: Dict[str, Any]):
        """Mark a task as completed successfully."""
        try:
            with transaction() as conn:
                conn.execute(
                    """
                    UPDATE tasks 
                    SET status = 'review_queued',
                        claimed_by = NULL,
                        claimed_at = NULL,
                        lease_expires_at = NULL,
                        completed_at = ?,
                        updated_at = ?
                    WHERE id = ? AND claimed_by = ?
                    """,
                    (
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat(),
                        task_id,
                        self.config.worker_id
                    )
                )
                
                # Log audit event
                conn.execute(
                    """
                    INSERT INTO audit_events (correlation_id, actor, action, payload)
                    SELECT correlation_id, ?, 'task.completed', ?
                    FROM tasks WHERE id = ?
                    """,
                    (
                        'devclaw',
                        json.dumps({
                            'task_id': task_id,
                            'worker_id': self.config.worker_id,
                            'result': result
                        }),
                        task_id
                    )
                )
            
            logger.info(f"Marked task {task_id} as completed")
            
        except Exception as e:
            logger.error(f"Error marking task {task_id} as completed: {e}")
    
    def _mark_task_failed(self, task_id: str, error: str, retry: bool = True):
        """Mark a task as failed with optional retry."""
        try:
            task = get_task_by_id(task_id)
            if not task:
                logger.error(f"Task {task_id} not found for failure marking")
                return
            
            retry_count = task.get('retry_count', 0) + 1
            max_retries = task.get('max_retries', self.config.max_retries)
            
            if retry and retry_count < max_retries:
                # Retry the task
                with transaction() as conn:
                    conn.execute(
                        """
                        UPDATE tasks 
                        SET retry_count = ?,
                            status = 'queued',
                            claimed_by = NULL,
                            claimed_at = NULL,
                            lease_expires_at = NULL,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            retry_count,
                            datetime.utcnow().isoformat(),
                            task_id
                        )
                    )
                
                # Calculate backoff delay
                delay = self.config.retry_base_delay * (2 ** (retry_count - 1))
                logger.info(f"Task {task_id} failed, will retry {retry_count}/{max_retries} after {delay}s: {error}")
            else:
                # Move to dead letter queue
                with transaction() as conn:
                    conn.execute(
                        """
                        INSERT INTO dead_letter_tasks 
                        (id, original_task_id, correlation_id, reason, error_details, original_payload)
                        SELECT ?, id, correlation_id, ?, ?, payload
                        FROM tasks WHERE id = ?
                        """,
                        (
                            str(uuid.uuid4()),
                            error,
                            json.dumps({'retry_count': retry_count, 'max_retries': max_retries}),
                            task_id
                        )
                    )
                    
                    conn.execute(
                        """
                        UPDATE tasks 
                        SET status = 'failed',
                            claimed_by = NULL,
                            claimed_at = NULL,
                            lease_expires_at = NULL,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (datetime.utcnow().isoformat(), task_id)
                    )
                
                logger.error(f"Task {task_id} failed permanently after {retry_count} retries: {error}")
            
            # Log audit event
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_events (correlation_id, actor, action, payload)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        task.get('correlation_id', ''),
                        'devclaw',
                        'task.failed',
                        json.dumps({
                            'task_id': task_id,
                            'worker_id': self.config.worker_id,
                            'error': error,
                            'retry_count': retry_count
                        })
                    )
                )
                conn.commit()
                
        except Exception as e:
            logger.error(f"Error marking task {task_id} as failed: {e}")
    
    def _execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a claimed task.
        
        Returns a dict with execution results.
        """
        task_id = task['id']
        payload = json.loads(task['payload']) if task.get('payload') else {}
        
        repo_url = payload.get('repo_url')
        branch = payload.get('branch', 'main')
        intent = task.get('intent', '')
        
        if not repo_url:
            raise TaskExecutionError("No repo_url in task payload")
        
        # Create working directory
        work_dir = Path(self.config.git_base_path) / f"{task_id}_{int(time.time())}"
        work_dir.mkdir(parents=True, exist_ok=True)
        self.current_work_dir = str(work_dir)
        
        try:
            # Clone repository
            logger.info(f"Cloning {repo_url} to {work_dir}")
            self.git_ops.clone_repo(repo_url, str(work_dir))
            
            # Create feature branch
            feature_branch = f"devclaw/{task_id}"
            self.git_ops.checkout_branch(str(work_dir), branch, create_from=feature_branch)
            
            # Execute task using task_executor
            execution_result = self.task_executor.execute(
                work_dir=str(work_dir),
                intent=intent,
                payload=payload
            )
            
            # Commit changes
            commit_message = f"[{task_id}] {intent[:50]}"
            self.git_ops.commit_changes(
                str(work_dir),
                message=commit_message,
                allow_empty=execution_result.get('no_changes', False)
            )
            
            # Push changes
            push_result = self.git_ops.push_changes(str(work_dir), feature_branch)
            
            return {
                'success': True,
                'work_dir': str(work_dir),
                'branch': feature_branch,
                'commit_message': commit_message,
                'files_changed': execution_result.get('files_changed', []),
                'push_result': push_result
            }
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            raise TaskExecutionError(str(e))
    
    def _cleanup_work_dir(self):
        """Clean up the current working directory."""
        if self.current_work_dir:
            if Path(self.current_work_dir).exists():
                try:
                    import shutil
                    shutil.rmtree(self.current_work_dir)
                    logger.debug(f"Cleaned up work directory: {self.current_work_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up work directory {self.current_work_dir}: {e}")
            self.current_work_dir = None
    
    def _process_single_task(self, task: Dict[str, Any]) -> bool:
        """
        Process a single task from claim to completion.
        
        Returns True if task was processed, False otherwise.
        """
        task_id = task['id']
        
        # Try to claim the task
        if not self._claim_task(task_id):
            return False
        
        self.current_task = task
        
        try:
            # Start lease extension thread
            self._start_lease_extension(task_id)
            
            # Execute the task
            logger.info(f"Executing task {task_id}: {task.get('intent', 'N/A')}")
            result = self._execute_task(task)
            
            # Mark as completed
            self._mark_task_completed(task_id, result)
            logger.info(f"Task {task_id} completed successfully")
            return True
            
        except TaskExecutionError as e:
            logger.error(f"Task {task_id} execution error: {e}")
            self._mark_task_failed(task_id, str(e), retry=True)
            return False
            
        except Exception as e:
            logger.exception(f"Unexpected error processing task {task_id}: {e}")
            self._mark_task_failed(task_id, str(e), retry=True)
            return False
            
        finally:
            # Stop lease extension
            self._shutdown_event.set()
            if self._lease_extension_thread:
                self._lease_extension_thread.join(timeout=5)
            self._shutdown_event.clear()
            
            # Cleanup
            self._cleanup_work_dir()
            self.current_task = None
    
    def run_single_iteration(self) -> bool:
        """
        Run a single polling iteration.
        
        Returns True if a task was processed, False otherwise.
        """
        try:
            # Get available tasks
            tasks = self._get_available_tasks(limit=1)
            
            if not tasks:
                return False
            
            # Process the first available task
            return self._process_single_task(tasks[0])
            
        except Exception as e:
            logger.exception(f"Error in polling iteration: {e}")
            return False
    
    def run(self):
        """Main worker loop - continuously poll and process tasks."""
        logger.info(f"Starting DevClaw worker {self.config.worker_id}")
        self.running = True
        
        while self.running and not self._shutdown_event.is_set():
            try:
                processed = self.run_single_iteration()
                
                if not processed:
                    # No tasks available, wait before polling again
                    logger.debug(f"No tasks available, sleeping for {self.config.poll_interval}s")
                    if self._shutdown_event.wait(timeout=self.config.poll_interval):
                        break
                        
            except Exception as e:
                logger.exception(f"Error in main loop: {e}")
                # Wait before retrying
                if self._shutdown_event.wait(timeout=self.config.poll_interval):
                    break
        
        logger.info(f"DevClaw worker {self.config.worker_id} stopped")
    
    def health_check(self) -> Dict[str, Any]:
        """Return health check status."""
        return {
            'worker_id': self.config.worker_id,
            'running': self.running,
            'current_task': self.current_task['id'] if self.current_task else None,
            'current_work_dir': self.current_work_dir,
            'timestamp': datetime.utcnow().isoformat()
        }


def create_worker(
    worker_id: Optional[str] = None,
    db_path: Optional[str] = None,
    poll_interval: int = 5,
    lease_duration: int = 300,
    **kwargs
) -> DevClawWorker:
    """Factory function to create a DevClaw worker with common defaults."""
    config = WorkerConfig(
        worker_id=worker_id or f"devclaw-{uuid.uuid4().hex[:8]}",
        db_path=db_path or os.environ.get('OPENCLAW_DB_PATH', 'data/openclaw.db'),
        poll_interval=poll_interval,
        lease_duration=lease_duration,
        **kwargs
    )
    return DevClawWorker(config)


if __name__ == '__main__':
    # Simple CLI to run the worker
    import argparse
    
    parser = argparse.ArgumentParser(description='DevClaw Runner Worker')
    parser.add_argument('--worker-id', help='Worker ID (auto-generated if not provided)')
    parser.add_argument('--db-path', help='Database path')
    parser.add_argument('--poll-interval', type=int, default=5, help='Polling interval in seconds')
    parser.add_argument('--lease-duration', type=int, default=300, help='Lease duration in seconds')
    parser.add_argument('--git-base-path', default='/tmp/devclaw-repos', help='Base path for git repos')
    
    args = parser.parse_args()
    
    worker = create_worker(
        worker_id=args.worker_id,
        db_path=args.db_path,
        poll_interval=args.poll_interval,
        lease_duration=args.lease_duration,
        git_base_path=args.git_base_path
    )
    
    worker.run()
