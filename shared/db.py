"""
Database Connection Manager for OpenClaw Orchestration Stack

Provides connection pooling, WAL mode, and dictionary-style row access.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


DEFAULT_DB_PATH = os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")


class ConnectionPool:
    """Thread-safe SQLite connection pool with WAL mode support."""
    
    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        max_connections: int = 10,
        timeout: float = 30.0
    ):
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool: List[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._initialized = False
        
        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize the database
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database with WAL mode and settings."""
        if self._initialized:
            return
            
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        try:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode = WAL")
            
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Set synchronous mode for performance/safety balance
            conn.execute("PRAGMA synchronous = NORMAL")
            
            # Set cache size (negative value = KiB)
            conn.execute("PRAGMA cache_size = -32000")  # 32MB cache
            
            # Set temp store to memory
            conn.execute("PRAGMA temp_store = MEMORY")
            
            # Set mmap size for read performance
            conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
            
            conn.commit()
            self._initialized = True
        finally:
            conn.close()
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with proper settings."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Set row factory for dict-like access
        conn.row_factory = sqlite3.Row
        
        return conn
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one."""
        with self._lock:
            if self._pool:
                return self._pool.pop()
            
        return self._create_connection()
    
    def return_connection(self, conn: sqlite3.Connection):
        """Return a connection to the pool."""
        with self._lock:
            if len(self._pool) < self.max_connections:
                self._pool.append(conn)
            else:
                conn.close()
    
    def close_all(self):
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                conn.close()
            self._pool.clear()


# Global connection pool instance
_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def init_pool(
    db_path: str = DEFAULT_DB_PATH,
    max_connections: int = 10,
    timeout: float = 30.0
) -> ConnectionPool:
    """Initialize the global connection pool."""
    global _pool
    
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(db_path, max_connections, timeout)
    
    return _pool


def get_pool() -> ConnectionPool:
    """Get the global connection pool, initializing if necessary."""
    global _pool
    
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool()
    
    return _pool


@contextmanager
def get_connection():
    """
    Context manager for database connections.
    
    Usage:
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM tasks")
            rows = cursor.fetchall()
    """
    pool = get_pool()
    conn = pool.get_connection()
    
    try:
        yield conn
    finally:
        pool.return_connection(conn)


@contextmanager
def transaction():
    """
    Context manager for database transactions.
    Automatically commits on success, rolls back on exception.
    
    Usage:
        with transaction() as conn:
            conn.execute("INSERT INTO tasks ...")
            conn.execute("INSERT INTO audit_events ...")
    """
    with get_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def execute(
    query: str,
    parameters: Optional[tuple] = None,
    fetch_one: bool = False
) -> Union[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Execute a query and return results as dictionaries.
    
    Args:
        query: SQL query string
        parameters: Query parameters
        fetch_one: If True, return single row or None; if False, return list
    
    Returns:
        Dict or list of dicts depending on fetch_one
    """
    with get_connection() as conn:
        cursor = conn.execute(query, parameters or ())
        
        if fetch_one:
            row = cursor.fetchone()
            return dict(row) if row else None
        else:
            return [dict(row) for row in cursor.fetchall()]


def execute_many(query: str, parameters_list: List[tuple]) -> int:
    """
    Execute a query multiple times with different parameters.
    
    Args:
        query: SQL query string
        parameters_list: List of parameter tuples
    
    Returns:
        Number of rows affected
    """
    with transaction() as conn:
        cursor = conn.executemany(query, parameters_list)
        return cursor.rowcount


def insert(
    table: str,
    data: Dict[str, Any],
    return_id: bool = False
) -> Union[int, str]:
    """
    Insert a single row into a table.
    
    Args:
        table: Table name
        data: Dictionary of column names to values
        return_id: If True, return the row ID
    
    Returns:
        Row ID if return_id is True, otherwise row count
    """
    columns = list(data.keys())
    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(columns)
    values = tuple(data.values())
    
    query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
    
    with transaction() as conn:
        cursor = conn.execute(query, values)
        if return_id:
            return cursor.lastrowid
        return cursor.rowcount


def update(
    table: str,
    data: Dict[str, Any],
    where: str,
    where_params: tuple
) -> int:
    """
    Update rows in a table.
    
    Args:
        table: Table name
        data: Dictionary of column names to new values
        where: WHERE clause (without the 'WHERE' keyword)
        where_params: Parameters for WHERE clause
    
    Returns:
        Number of rows updated
    """
    set_clause = ", ".join(f"{col} = ?" for col in data.keys())
    values = tuple(data.values()) + where_params
    
    query = f"UPDATE {table} SET {set_clause} WHERE {where}"
    
    with transaction() as conn:
        cursor = conn.execute(query, values)
        return cursor.rowcount


def delete(
    table: str,
    where: str,
    where_params: tuple
) -> int:
    """
    Delete rows from a table.
    
    Args:
        table: Table name
        where: WHERE clause (without the 'WHERE' keyword)
        where_params: Parameters for WHERE clause
    
    Returns:
        Number of rows deleted
    """
    query = f"DELETE FROM {table} WHERE {where}"
    
    with transaction() as conn:
        cursor = conn.execute(query, where_params)
        return cursor.rowcount


# Convenience functions for common operations

def get_task_by_id(task_id: str) -> Optional[Dict[str, Any]]:
    """Get a task by its ID."""
    return execute(
        "SELECT * FROM tasks WHERE id = ?",
        (task_id,),
        fetch_one=True
    )


def get_tasks_by_status(
    status: str,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Get tasks by status."""
    query = "SELECT * FROM tasks WHERE status = ? ORDER BY created_at"
    params: List[Any] = [status]
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    return execute(query, tuple(params))


def get_pending_tasks_for_worker(
    worker_type: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Get pending tasks assigned to a specific worker type."""
    return execute(
        """
        SELECT * FROM tasks 
        WHERE assigned_to = ? AND status = 'queued'
        AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'))
        ORDER BY created_at
        LIMIT ?
        """,
        (worker_type, limit)
    )


def get_audit_trail(correlation_id: str) -> List[Dict[str, Any]]:
    """Get audit trail for a correlation ID."""
    return execute(
        """
        SELECT * FROM audit_events 
        WHERE correlation_id = ? 
        ORDER BY timestamp
        """,
        (correlation_id,)
    )


def close_pool():
    """Close all connections in the pool. Useful for testing and shutdown."""
    global _pool
    
    with _pool_lock:
        if _pool:
            _pool.close_all()
            _pool = None
