"""Database migration system."""
from pathlib import Path
from typing import List, Tuple
import sqlite3


class MigrationManager:
    """Manage database migrations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations_dir = Path(__file__).parent
        self._ensure_migration_table()
    
    def _ensure_migration_table(self):
        """Create migrations tracking table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def get_applied_migrations(self) -> List[int]:
        """Get list of applied migration versions."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT version FROM _migrations ORDER BY version")
            return [row[0] for row in cursor.fetchall()]
    
    def get_pending_migrations(self) -> List[Tuple[int, str, Path]]:
        """Get list of pending migrations."""
        applied = set(self.get_applied_migrations())
        pending = []
        
        for migration_file in sorted(self.migrations_dir.glob("*.sql")):
            # Parse version from filename: 001_migration_name.sql
            try:
                version = int(migration_file.stem.split("_")[0])
                name = "_".join(migration_file.stem.split("_")[1:])
                if version not in applied:
                    pending.append((version, name, migration_file))
            except (ValueError, IndexError):
                continue
        
        return pending
    
    def migrate(self):
        """Apply all pending migrations."""
        pending = self.get_pending_migrations()
        
        for version, name, filepath in pending:
            print(f"Applying migration {version}: {name}")
            with open(filepath, 'r') as f:
                sql = f.read()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                    (version, name)
                )
        
        return len(pending)
    
    def rollback(self, target_version: int):
        """Rollback to specific version."""
        # Implementation would require down scripts
        raise NotImplementedError("Rollback requires down migration scripts")
