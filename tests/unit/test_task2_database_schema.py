"""
Unit tests for Task 2: SQLite Schema for State Persistence
"""
import os
import sqlite3
import tempfile
import pytest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCHEMA_PATH = PROJECT_ROOT / "shared" / "schemas" / "schema.sql"


class TestSchemaFile:
    """Test suite for schema.sql file"""
    
    def test_schema_file_exists(self):
        """Verify schema.sql exists"""
        assert SCHEMA_PATH.exists(), f"schema.sql not found at {SCHEMA_PATH}"
    
    def test_schema_file_not_empty(self):
        """Verify schema.sql has content"""
        content = SCHEMA_PATH.read_text()
        assert len(content) > 100, "schema.sql is too short"
    
    def test_schema_has_tasks_table(self):
        """Verify schema defines tasks table"""
        content = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS tasks" in content
    
    def test_schema_has_reviews_table(self):
        """Verify schema defines reviews table"""
        content = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS reviews" in content
    
    def test_schema_has_audit_events_table(self):
        """Verify schema defines audit_events table"""
        content = SCHEMA_PATH.read_text()
        assert "CREATE TABLE IF NOT EXISTS audit_events" in content
    
    def test_schema_has_indexes(self):
        """Verify schema creates indexes"""
        content = SCHEMA_PATH.read_text()
        assert "CREATE INDEX" in content
    
    def test_schema_has_wal_pragma(self):
        """Verify schema enables WAL mode"""
        content = SCHEMA_PATH.read_text()
        assert "journal_mode = WAL" in content


class TestDatabaseManager:
    """Test suite for database manager"""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        yield db_path
        os.unlink(db_path)
    
    @pytest.fixture
    def db_manager(self, temp_db):
        """Create database manager with temp database."""
        from shared.utils.db_manager import DatabaseManager
        return DatabaseManager(temp_db)
    
    def test_db_manager_initializes_database(self, db_manager, temp_db):
        """Verify db manager creates tables on init"""
        # Check that tables were created
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            )
            assert cursor.fetchone() is not None, "tasks table not created"
    
    def test_db_manager_can_execute_query(self, db_manager):
        """Verify db manager can execute queries"""
        result = db_manager.fetch_one("SELECT 1 as test")
        assert result is not None
        assert result['test'] == 1
    
    def test_db_manager_can_insert_and_select(self, db_manager):
        """Verify basic CRUD operations"""
        # Insert a test task
        db_manager.execute(
            """INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ('test-1', 'corr-1', 'idemp-1', 'queued', 'DEVCLAW', 'test')
        )
        
        # Select it back
        result = db_manager.fetch_one(
            "SELECT * FROM tasks WHERE id = ?", ('test-1',)
        )
        assert result is not None
        assert result['id'] == 'test-1'
        assert result['status'] == 'queued'


class TestSchemaValidation:
    """Test suite for schema validation"""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with schema applied."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        # Apply schema
        with sqlite3.connect(db_path) as conn:
            with open(SCHEMA_PATH, 'r') as f:
                conn.executescript(f.read())
        
        yield db_path
        os.unlink(db_path)
    
    def test_tasks_table_has_required_columns(self, temp_db):
        """Verify tasks table has all required columns"""
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = {row[1] for row in cursor.fetchall()}
        
        required = {'id', 'correlation_id', 'idempotency_key', 'status', 'assigned_to',
                   'claimed_by', 'claimed_at', 'lease_expires_at', 'retry_count', 
                   'intent', 'payload', 'created_at', 'updated_at'}
        assert required.issubset(columns), f"Missing columns: {required - columns}"
    
    def test_reviews_table_has_required_columns(self, temp_db):
        """Verify reviews table has all required columns"""
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("PRAGMA table_info(reviews)")
            columns = {row[1] for row in cursor.fetchall()}
        
        required = {'id', 'task_id', 'result', 'summary', 'findings', 
                   'reviewer_id', 'reviewer_role', 'started_at', 'completed_at'}
        assert required.issubset(columns), f"Missing columns: {required - columns}"
    
    def test_audit_events_table_has_required_columns(self, temp_db):
        """Verify audit_events table has all required columns"""
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute("PRAGMA table_info(audit_events)")
            columns = {row[1] for row in cursor.fetchall()}
        
        required = {'id', 'correlation_id', 'timestamp', 'actor', 'action', 'payload'}
        assert required.issubset(columns), f"Missing columns: {required - columns}"
    
    def test_tasks_status_constraint(self, temp_db):
        """Verify tasks.status has proper CHECK constraint"""
        with sqlite3.connect(temp_db) as conn:
            # Valid status should work
            conn.execute("""
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                VALUES ('t1', 'c1', 'i1', 'queued', 'DEVCLAW', 'test')
            """)
            conn.commit()
            
            # Invalid status should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                    VALUES ('t2', 'c2', 'i2', 'invalid_status', 'DEVCLAW', 'test')
                """)
    
    def test_idempotency_key_is_unique(self, temp_db):
        """Verify idempotency_key uniqueness constraint"""
        with sqlite3.connect(temp_db) as conn:
            conn.execute("""
                INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                VALUES ('t1', 'c1', 'unique-key', 'queued', 'DEVCLAW', 'test')
            """)
            conn.commit()
            
            # Duplicate idempotency_key should fail
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute("""
                    INSERT INTO tasks (id, correlation_id, idempotency_key, status, assigned_to, intent)
                    VALUES ('t2', 'c2', 'unique-key', 'queued', 'DEVCLAW', 'test')
                """)
    
    def test_reviews_foreign_key_constraint(self, temp_db):
        """Verify reviews.task_id foreign key constraint"""
        conn = sqlite3.connect(temp_db)
        conn.execute("PRAGMA foreign_keys = ON")  # Enable FK enforcement
        
        # Should fail without valid task_id
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("""
                INSERT INTO reviews (id, task_id, result, summary, reviewer_id)
                VALUES ('r1', 'non-existent-task', 'approve', 'Good', 'symphony')
            """)
        conn.close()


class TestViews:
    """Test suite for database views"""
    
    @pytest.fixture
    def temp_db(self):
        """Create a temporary database with schema and sample data."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        with sqlite3.connect(db_path) as conn:
            with open(SCHEMA_PATH, 'r') as f:
                conn.executescript(f.read())
        
        yield db_path
        os.unlink(db_path)
    
    def test_v_tasks_available_view_exists(self, temp_db):
        """Verify v_tasks_available view exists"""
        with sqlite3.connect(temp_db) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='view' AND name='v_tasks_available'"
            )
            assert cursor.fetchone() is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
