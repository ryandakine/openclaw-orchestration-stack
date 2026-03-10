#!/usr/bin/env python3
"""
Database Migration Runner for OpenClaw Orchestration Stack

Usage:
    python runner.py migrate          # Run all pending migrations
    python runner.py migrate --target 002_add_users  # Migrate to specific version
    python runner.py rollback         # Rollback last migration
    python runner.py status           # Show migration status
    python runner.py create --name "add_users_table"  # Create new migration
"""

import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple


DEFAULT_DB_PATH = os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")
MIGRATIONS_DIR = Path(__file__).parent


class MigrationRunner:
    """Handles database migrations for the OpenClaw orchestration stack."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._ensure_migrations_table()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper settings."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    
    def _ensure_migrations_table(self):
        """Ensure the schema_migrations table exists."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT
                )
            """)
            conn.commit()
    
    def _get_applied_migrations(self) -> List[str]:
        """Get list of already applied migration versions."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
            return [row["version"] for row in cursor.fetchall()]
    
    def _get_available_migrations(self) -> List[Tuple[str, Path]]:
        """Get list of available migration files sorted by version."""
        migrations = []
        pattern = re.compile(r"^(\d+)_.*\.sql$")
        
        for file_path in MIGRATIONS_DIR.glob("*.sql"):
            match = pattern.match(file_path.name)
            if match:
                version = match.group(1)
                migrations.append((version, file_path))
        
        migrations.sort(key=lambda x: int(x[0]))
        return migrations
    
    def status(self) -> None:
        """Show current migration status."""
        applied = set(self._get_applied_migrations())
        available = self._get_available_migrations()
        
        print(f"\nDatabase: {self.db_path}")
        print(f"Migrations directory: {MIGRATIONS_DIR}")
        print("\n" + "=" * 60)
        print(f"{'Status':<10} {'Version':<10} {'Name':<40}")
        print("=" * 60)
        
        for version, path in available:
            status = "✓ applied" if version in applied else "pending"
            name = path.stem
            print(f"{status:<10} {version:<10} {name:<40}")
        
        print("=" * 60)
        print(f"\nApplied: {len(applied)} | Pending: {len(available) - len(applied)}")
    
    def migrate(self, target: Optional[str] = None) -> None:
        """Run pending migrations up to target version."""
        applied = set(self._get_applied_migrations())
        available = self._get_available_migrations()
        
        pending = [(v, p) for v, p in available if v not in applied]
        
        if target:
            pending = [(v, p) for v, p in pending if int(v) <= int(target)]
        
        if not pending:
            print("No pending migrations.")
            return
        
        print(f"\nRunning {len(pending)} migration(s)...")
        print("=" * 60)
        
        with self._get_connection() as conn:
            for version, path in pending:
                print(f"\nApplying {path.name}...")
                
                # Read and execute migration
                sql = path.read_text()
                conn.executescript(sql)
                
                # Record migration
                conn.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (version, path.stem)
                )
                
                print(f"✓ Applied {path.name}")
            
            conn.commit()
        
        print("\n" + "=" * 60)
        print("Migrations complete!")
    
    def rollback(self, steps: int = 1) -> None:
        """Rollback the last n migrations."""
        applied = self._get_applied_migrations()
        
        if not applied:
            print("No migrations to rollback.")
            return
        
        to_rollback = applied[-steps:]
        
        print(f"\nRolling back {len(to_rollback)} migration(s)...")
        print("=" * 60)
        
        # Note: SQLite doesn't support DROP TABLE IF EXISTS with CASCADE
        # In a real implementation, you'd have down migrations
        print("⚠️  Rollback not fully implemented - manual intervention may be required")
        print(f"Would rollback versions: {', '.join(to_rollback)}")
    
    def create(self, name: str) -> Path:
        """Create a new migration file."""
        available = self._get_available_migrations()
        
        if available:
            last_version = int(available[-1][0])
        else:
            last_version = 0
        
        new_version = str(last_version + 1).zfill(3)
        filename = f"{new_version}_{name}.sql"
        filepath = MIGRATIONS_DIR / filename
        
        template = f"""-- Migration: {new_version}_{name}
-- Description: 
-- Created: {__import__('datetime').datetime.now().strftime('%Y-%m-%d')}

-- Write your up migration here

-- Record migration
INSERT INTO schema_migrations (version, description) VALUES ('{new_version}', '{name}');
"""
        
        filepath.write_text(template)
        print(f"✓ Created migration: {filepath}")
        return filepath


def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw Database Migration Runner"
    )
    parser.add_argument(
        "--db-path",
        default=DEFAULT_DB_PATH,
        help="Path to SQLite database"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # migrate command
    migrate_parser = subparsers.add_parser("migrate", help="Run pending migrations")
    migrate_parser.add_argument(
        "--target",
        help="Target migration version"
    )
    
    # rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback migrations")
    rollback_parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of migrations to rollback"
    )
    
    # status command
    subparsers.add_parser("status", help="Show migration status")
    
    # create command
    create_parser = subparsers.add_parser("create", help="Create new migration")
    create_parser.add_argument(
        "--name",
        required=True,
        help="Migration name (e.g., 'add_users_table')"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    runner = MigrationRunner(args.db_path)
    
    if args.command == "migrate":
        runner.migrate(args.target)
    elif args.command == "rollback":
        runner.rollback(args.steps)
    elif args.command == "status":
        runner.status()
    elif args.command == "create":
        runner.create(args.name)


if __name__ == "__main__":
    main()
