# Database Architecture

## Overview

The OpenClaw Orchestration Stack uses **SQLite** as its primary database, configured with **WAL (Write-Ahead Logging) mode** for improved concurrency and performance. This choice provides:

- **Zero-configuration deployment** - No separate database server required
- **ACID compliance** - Full transactional support
- **JSON support** - Native JSON column type for flexible schemas
- **Excellent read performance** - Ideal for query-heavy workloads
- **Single-file portability** - Easy backups and migrations

## Schema Design

### Entity Relationship Diagram

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│     tasks       │         │    reviews      │         │  audit_events   │
├─────────────────┤         ├─────────────────┤         ├─────────────────┤
│ PK id           │◄────────┤ FK task_id      │         │ PK id           │
│    correlation_id│        │    result       │         │    correlation_id│
│    status       │         │    summary      │         │    timestamp    │
│    assigned_to  │         │    findings     │         │    actor        │
│    claimed_by   │         │    reviewer_id  │         │    action       │
│    claimed_at   │         │    created_at   │         │    payload      │
│    lease_expires_at       └─────────────────┘         └─────────────────┘
│    retry_count  │
│    payload      │
│    created_at   │
│    updated_at   │
└─────────────────┘
```

### Tables

#### 1. Tasks Table

The central table for tracking all tasks in the system.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Unique task identifier |
| `correlation_id` | TEXT | NOT NULL | Groups related tasks/operations |
| `status` | TEXT | NOT NULL, CHECK | Current status: `queued`, `executing`, `review_queued`, `approved`, `merged`, `failed`, `blocked` |
| `assigned_to` | TEXT | NOT NULL, CHECK | Worker assignment: `DEVCLAW` or `SYMPHONY` |
| `claimed_by` | TEXT | | Worker instance that claimed the task |
| `claimed_at` | TIMESTAMP | | When the task was claimed |
| `lease_expires_at` | TIMESTAMP | | Lease expiration for work queue |
| `retry_count` | INTEGER | DEFAULT 0 | Number of retry attempts |
| `payload` | JSON | | Task-specific data |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Creation timestamp |
| `updated_at` | TIMESTAMP | | Last update timestamp |

**Indexes:**
- `idx_tasks_status` - For status-based queries
- `idx_tasks_correlation_id` - For correlation lookups
- `idx_tasks_lease_expires_at` - For lease management
- `idx_tasks_claimed_by` - For worker tracking
- `idx_tasks_created_at` - For chronological ordering
- `idx_tasks_assigned_status` - Composite for worker queries

#### 2. Reviews Table

Stores human-in-the-loop review results from SYMPHONY.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Unique review identifier |
| `task_id` | TEXT | NOT NULL, FOREIGN KEY | References tasks.id |
| `result` | TEXT | NOT NULL, CHECK | Review outcome: `approve`, `reject`, `blocked` |
| `summary` | TEXT | | Human-readable summary |
| `findings` | JSON | | Structured review findings |
| `reviewer_id` | TEXT | | Identifier of the reviewer |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Review timestamp |

**Indexes:**
- `idx_reviews_task_id` - For task lookups
- `idx_reviews_result` - For result filtering
- `idx_reviews_reviewer_id` - For reviewer tracking
- `idx_reviews_created_at` - For chronological ordering

#### 3. Audit Events Table

Immutable audit trail for all system actions.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | TEXT | PRIMARY KEY | Unique event identifier |
| `correlation_id` | TEXT | NOT NULL | Groups related events |
| `timestamp` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Event timestamp |
| `actor` | TEXT | NOT NULL | Entity performing the action |
| `action` | TEXT | NOT NULL | Action performed |
| `payload` | JSON | | Event-specific data |

**Indexes:**
- `idx_audit_correlation_id` - For trace lookups
- `idx_audit_timestamp` - For time-based queries
- `idx_audit_actor` - For actor tracking
- `idx_audit_action` - For action filtering
- `idx_audit_correlation_timestamp` - Composite for trace ordering

## Connection Management

### Connection Pool

The `shared/db.py` module provides a thread-safe connection pool:

```python
from shared.db import get_connection, transaction

# Simple query
with get_connection() as conn:
    cursor = conn.execute("SELECT * FROM tasks WHERE status = ?", ("queued",))
    rows = cursor.fetchall()

# Transaction
with transaction() as conn:
    conn.execute("INSERT INTO tasks ...")
    conn.execute("INSERT INTO audit_events ...")
    # Auto-commits on success, rolls back on exception
```

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `max_connections` | 10 | Maximum pooled connections |
| `timeout` | 30s | Connection timeout |
| `journal_mode` | WAL | Write-ahead logging |
| `synchronous` | NORMAL | Sync mode (NORMAL/FULL/OFF) |
| `cache_size` | 32MB | Page cache size |
| `temp_store` | MEMORY | Temporary storage location |
| `mmap_size` | 256MB | Memory-mapped I/O size |

## Migrations

### Migration System

Migrations are managed via `shared/migrations/runner.py`:

```bash
# Check status
python shared/migrations/runner.py status

# Run all pending migrations
python shared/migrations/runner.py migrate

# Migrate to specific version
python shared/migrations/runner.py migrate --target 002

# Create new migration
python shared/migrations/runner.py create --name add_users_table
```

### Migration Format

Migrations follow the naming convention: `###_description.sql`

```sql
-- Migration: 002_add_users
-- Description: Add users table for authentication

CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Record migration
INSERT INTO schema_migrations (version, description) 
VALUES ('002', 'add_users');
```

## Performance Considerations

### Read Optimization

1. **WAL Mode** - Allows readers to proceed without blocking on writers
2. **Indexes** - Strategic indexes on all query columns
3. **Connection Pooling** - Reuses connections to avoid overhead
4. **Memory Mapping** - 256MB mmap for frequently accessed data

### Write Optimization

1. **Batch Inserts** - Use `executemany()` for bulk operations
2. **Transactions** - Group writes in transactions
3. **NORMAL Synchronous** - Balance between safety and speed

### Query Patterns

**Get pending tasks for worker:**
```sql
SELECT * FROM tasks 
WHERE assigned_to = ? AND status = 'queued'
AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'))
ORDER BY created_at
LIMIT ?
```

**Get audit trail:**
```sql
SELECT * FROM audit_events 
WHERE correlation_id = ? 
ORDER BY timestamp
```

**Get task with reviews:**
```sql
SELECT t.*, r.result as review_result, r.summary as review_summary
FROM tasks t
LEFT JOIN reviews r ON t.id = r.task_id
WHERE t.id = ?
```

## Backup and Recovery

### Automated Backups

```python
# SQLite backup API
import sqlite3

def backup_database(source_path, backup_path):
    source = sqlite3.connect(source_path)
    backup = sqlite3.connect(backup_path)
    
    with backup:
        source.backup(backup)
    
    backup.close()
    source.close()
```

### Point-in-Time Recovery

WAL mode provides natural checkpointing. To recover:

1. Stop the application
2. Copy database file and `-wal` file together
3. Restart with recovered files

## Monitoring

### Key Metrics

| Metric | Query |
|--------|-------|
| Queue depth | `SELECT status, COUNT(*) FROM tasks GROUP BY status` |
| Average task age | `SELECT AVG(julianday('now') - julianday(created_at)) FROM tasks WHERE status = 'queued'` |
| Review backlog | `SELECT COUNT(*) FROM tasks WHERE status = 'review_queued'` |
| Worker efficiency | `SELECT assigned_to, AVG(julianday(updated_at) - julianday(created_at)) FROM tasks WHERE status = 'merged' GROUP BY assigned_to` |

### Health Checks

```python
def db_health_check():
    with get_connection() as conn:
        # Check writable
        conn.execute("CREATE TABLE IF NOT EXISTS _health_check (id INTEGER)")
        conn.execute("INSERT INTO _health_check VALUES (1)")
        conn.execute("DELETE FROM _health_check WHERE id = 1")
        
        # Check WAL mode
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"
        
        # Check foreign keys
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
```

## Security

### Data Protection

1. **File Permissions** - Database file should be readable only by application user
2. **Encryption** - Consider SQLCipher for sensitive deployments
3. **Audit Trail** - All actions logged in audit_events table

### Access Control

The database is accessed only through the `shared/db.py` module, which:
- Validates all inputs
- Uses parameterized queries (prevents SQL injection)
- Enforces foreign key constraints
- Provides audit logging hooks

## Future Considerations

### Scaling Path

If SQLite becomes a bottleneck:

1. **Read Replicas** - SQLite can be replicated using Litestream
2. **Connection Proxy** - PgBouncer-style pooling
3. **Migration to PostgreSQL** - Schema is compatible with minimal changes

### Schema Evolution

Planned future tables:
- `workers` - Worker registration and heartbeat
- `workflows` - Workflow definitions
- `workflow_executions` - Workflow instance tracking
