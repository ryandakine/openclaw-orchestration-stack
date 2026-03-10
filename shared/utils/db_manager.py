"""
Database connection manager for SQLite with connection pooling.
"""
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class DatabaseManager:
    """Thread-safe SQLite database manager with connection pooling."""
    
    def __init__(self, db_path: str = "openclaw.db"):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_database()
    
    def _init_database(self):
        """Initialize database with schema if not exists."""
        schema_path = Path(__file__).parent.parent / "schemas" / "schema.sql"
        
        with self.get_connection() as conn:
            if schema_path.exists():
                with open(schema_path, 'r') as f:
                    conn.executescript(f.read())
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get a database connection (context manager)."""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None  # Autocommit mode for WAL
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode
            self._local.connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection.execute("PRAGMA foreign_keys = ON")
        
        try:
            yield self._local.connection
        except Exception:
            self._local.connection.rollback()
            raise
    
    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        with self.get_connection() as conn:
            return conn.execute(query, params)
    
    def execute_many(self, query: str, params_list: list) -> sqlite3.Cursor:
        """Execute a query multiple times."""
        with self.get_connection() as conn:
            return conn.executemany(query, params_list)
    
    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """Fetch a single row."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchone()
    
    def fetch_all(self, query: str, params: tuple = ()) -> list:
        """Fetch all rows."""
        with self.get_connection() as conn:
            return conn.execute(query, params).fetchall()
    
    def close(self):
        """Close thread-local connection."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(db_path: str = "openclaw.db") -> DatabaseManager:
    """Get or create global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager
