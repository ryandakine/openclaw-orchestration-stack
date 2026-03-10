"""
Pytest configuration and fixtures for shared utils tests.
"""

import os
import sys
import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add parent directories to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Ensure data directory exists for tests
os.makedirs(project_root / "data", exist_ok=True)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        path = f.name
    yield path
    # Cleanup
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def test_db(temp_db_path):
    """Create a test database with schema."""
    conn = sqlite3.connect(temp_db_path)
    conn.row_factory = sqlite3.Row
    
    # Create tables
    conn.executescript("""
        -- Tasks table
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            correlation_id TEXT NOT NULL,
            idempotency_key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL,
            assigned_to TEXT NOT NULL,
            claimed_by TEXT,
            claimed_at TIMESTAMP,
            lease_expires_at TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            intent TEXT NOT NULL,
            payload JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            source TEXT
        );
        
        CREATE INDEX idx_tasks_status ON tasks(status);
        CREATE INDEX idx_tasks_correlation_id ON tasks(correlation_id);
        CREATE INDEX idx_tasks_lease_expires ON tasks(lease_expires_at);
        CREATE INDEX idx_tasks_claimed_by ON tasks(claimed_by);
        CREATE INDEX idx_tasks_idempotency ON tasks(idempotency_key);
        
        -- Audit events table
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            payload JSON,
            ip_address TEXT,
            user_agent TEXT
        );
        
        CREATE INDEX idx_audit_correlation_id ON audit_events(correlation_id);
        CREATE INDEX idx_audit_timestamp ON audit_events(timestamp);
        CREATE INDEX idx_audit_action ON audit_events(action);
        
        -- Idempotency store table
        CREATE TABLE IF NOT EXISTS idempotency_store (
            key TEXT PRIMARY KEY,
            correlation_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            response_data JSON,
            request_hash TEXT
        );
        
        CREATE INDEX idx_idempotency_expires ON idempotency_store(expires_at);
        CREATE INDEX idx_idempotency_correlation ON idempotency_store(correlation_id);
        CREATE INDEX idx_idempotency_status ON idempotency_store(status);
        
        -- Request dedup table
        CREATE TABLE IF NOT EXISTS request_dedup (
            correlation_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            response_data JSON,
            worker_id TEXT,
            PRIMARY KEY (correlation_id, idempotency_key)
        );
        
        CREATE INDEX idx_dedup_expires ON request_dedup(expires_at);
        CREATE INDEX idx_dedup_key ON request_dedup(idempotency_key);
        CREATE INDEX idx_dedup_status ON request_dedup(status);
        
        -- Duplicate requests log
        CREATE TABLE IF NOT EXISTS duplicate_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            correlation_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            original_created_at TIMESTAMP,
            handled_as TEXT NOT NULL
        );
        
        -- Dead letter queue
        CREATE TABLE IF NOT EXISTS dead_letter_queue (
            id TEXT PRIMARY KEY,
            original_task_id TEXT NOT NULL,
            correlation_id TEXT NOT NULL,
            failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT NOT NULL,
            error_details JSON,
            original_payload JSON NOT NULL,
            retry_count INTEGER DEFAULT 0,
            worker_id TEXT,
            retried_at TIMESTAMP,
            retry_successful BOOLEAN,
            archived BOOLEAN DEFAULT FALSE
        );
        
        CREATE INDEX idx_dlq_correlation_id ON dead_letter_queue(correlation_id);
        CREATE INDEX idx_dlq_failed_at ON dead_letter_queue(failed_at);
        CREATE INDEX idx_dlq_reason ON dead_letter_queue(reason);
        CREATE INDEX idx_dlq_archived ON dead_letter_queue(archived);
        CREATE INDEX idx_dlq_original_task ON dead_letter_queue(original_task_id);
    """)
    
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def mock_db_connection(test_db, monkeypatch):
    """Mock the database connection for tests."""
    import shared.db as db_module
    
    # Create a mock pool
    class MockPool:
        def __init__(self, conn):
            self._conn = conn
        
        def get_connection(self):
            return self._conn
        
        def return_connection(self, conn):
            pass
        
        def close_all(self):
            pass
    
    # Create a mock transaction context manager
    class MockTransaction:
        def __init__(self, conn):
            self._conn = conn
        
        def __enter__(self):
            return self._conn
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                self._conn.rollback()
            else:
                self._conn.commit()
            return False
    
    # Patch the module functions
    mock_pool = MockPool(test_db)
    
    def mock_get_connection():
        return test_db
    
    def mock_transaction():
        return MockTransaction(test_db)
    
    def mock_execute(query, parameters=None, fetch_one=False):
        cursor = test_db.execute(query, parameters or ())
        if fetch_one:
            row = cursor.fetchone()
            return dict(row) if row else None
        return [dict(row) for row in cursor.fetchall()]
    
    monkeypatch.setattr(db_module, 'get_pool', lambda: mock_pool)
    monkeypatch.setattr(db_module, 'get_connection', mock_get_connection)
    monkeypatch.setattr(db_module, 'transaction', mock_transaction)
    monkeypatch.setattr(db_module, 'execute', mock_execute)
    
    yield test_db


@pytest.fixture
def sample_task(mock_db_connection):
    """Create a sample task in the database."""
    import uuid
    task_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    idempotency_key = str(uuid.uuid4())
    
    mock_db_connection.execute("""
        INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent, payload)
        VALUES (?, ?, ?, 'queued', 'DEVCLAW', 'test_intent', ?)
    """, (task_id, correlation_id, idempotency_key, 
          '{"data": "test_payload"}'))
    mock_db_connection.commit()
    
    return {
        "id": task_id,
        "correlation_id": correlation_id,
        "idempotency_key": idempotency_key,
        "status": "queued",
        "assigned_to": "DEVCLAW",
        "intent": "test_intent"
    }


@pytest.fixture
def sample_worker_id():
    """Return a sample worker ID."""
    return "worker-test-001"


@pytest.fixture
def cleanup_utils():
    """Reset global instances after tests."""
    yield
    # Cleanup will be done after test
    import shared.utils.lease_manager as lm
    import shared.utils.idempotency as im
    import shared.utils.deduplication as dm
    import shared.utils.dead_letter as dl
    
    lm._lease_manager = None
    im._idempotency_store = None
    dm._dedup_manager = None
    dl._dlq = None
