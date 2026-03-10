"""
Database connection module for the ingestion system.

Provides SQLite connection management with WAL mode for the arbitrage hunter.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

DEFAULT_DB_PATH = os.environ.get(
    "ARB_HUNTER_DB_PATH", 
    "data/arb_hunter.db"
)


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
def get_db_connection():
    """
    Context manager for database connections.
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM events")
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
            conn.execute("INSERT INTO events ...")
            conn.execute("INSERT INTO odds ...")
    """
    with get_db_connection() as conn:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


class IngestionDatabase:
    """
    High-level database interface for the ingestion system.
    
    Provides methods for CRUD operations on events and odds.
    """
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._pool = init_pool(db_path)
    
    def execute(
        self,
        query: str,
        parameters: Optional[tuple] = None,
        fetch_one: bool = False
    ) -> Union[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Execute a query and return results as dictionaries."""
        with get_db_connection() as conn:
            cursor = conn.execute(query, parameters or ())
            
            if fetch_one:
                row = cursor.fetchone()
                return dict(row) if row else None
            else:
                return [dict(row) for row in cursor.fetchall()]
    
    def execute_many(self, query: str, parameters_list: List[tuple]) -> int:
        """Execute a query multiple times with different parameters."""
        with transaction() as conn:
            cursor = conn.executemany(query, parameters_list)
            return cursor.rowcount
    
    def insert(self, table: str, data: Dict[str, Any], return_id: bool = True) -> Union[int, str]:
        """Insert a single row into a table."""
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
        self,
        table: str,
        data: Dict[str, Any],
        where: str,
        where_params: tuple
    ) -> int:
        """Update rows in a table."""
        set_clause = ", ".join(f"{col} = ?" for col in data.keys())
        values = tuple(data.values()) + where_params
        
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"
        
        with transaction() as conn:
            cursor = conn.execute(query, values)
            return cursor.rowcount
    
    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get an event by its ID."""
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_events_by_sport(
        self,
        sport: str,
        start_time_after: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get events by sport with optional time filtering."""
        query = "SELECT * FROM events WHERE sport = ?"
        params: List[Any] = [sport]
        
        if start_time_after:
            query += " AND start_time > ?"
            params.append(start_time_after.isoformat())
        
        query += " ORDER BY start_time"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        return self.execute(query, tuple(params))
    
    def get_odds_by_event(self, event_id: str) -> List[Dict[str, Any]]:
        """Get all odds records for an event."""
        return self.execute(
            """
            SELECT o.*, e.sport, e.teams, e.start_time
            FROM odds o
            JOIN events e ON o.event_id = e.event_id
            WHERE o.event_id = ?
            ORDER BY o.timestamp DESC
            """,
            (event_id,)
        )
    
    def get_latest_odds_by_source(
        self,
        event_id: str,
        source: str
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent odds for an event from a specific source."""
        return self.execute(
            """
            SELECT * FROM odds 
            WHERE event_id = ? AND source = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (event_id, source),
            fetch_one=True
        )
    
    def get_active_events(
        self,
        before_start_time: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get events that haven't started yet."""
        query = "SELECT * FROM events WHERE 1=1"
        params: List[Any] = []
        
        if before_start_time:
            query += " AND start_time > ?"
            params.append(before_start_time.isoformat())
        else:
            query += " AND start_time > datetime('now')"
        
        query += " ORDER BY start_time"
        
        return self.execute(query, tuple(params))
    
    def delete_old_records(self, days: int = 30) -> int:
        """Delete records older than specified days."""
        with transaction() as conn:
            # Delete old odds first (due to foreign key)
            cursor = conn.execute(
                "DELETE FROM odds WHERE timestamp < datetime('now', '-{} days')".format(days)
            )
            odds_deleted = cursor.rowcount
            
            # Delete old events
            cursor = conn.execute(
                "DELETE FROM events WHERE start_time < datetime('now', '-{} days')".format(days)
            )
            events_deleted = cursor.rowcount
            
            return odds_deleted + events_deleted


def init_database(db_path: str = DEFAULT_DB_PATH) -> IngestionDatabase:
    """
    Initialize the database with tables and return a database instance.
    
    Args:
        db_path: Path to the SQLite database file
        
    Returns:
        IngestionDatabase instance
    """
    db = IngestionDatabase(db_path)
    
    # Create tables if they don't exist
    from .models import create_tables
    create_tables(db_path)
    
    return db
