-- OpenClaw Orchestration Stack - Database Schema
-- Version: 1.0.0

-- Enable WAL mode for better concurrency
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =====================================================
-- TASKS TABLE
-- Stores all tasks in the system with their state
-- =====================================================
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'executing', 'review_queued', 
        'approved', 'merged', 'failed', 'blocked', 
        'review_failed', 'remediation_queued'
    )),
    assigned_to TEXT NOT NULL CHECK (assigned_to IN ('DEVCLAW', 'SYMPHONY', 'N8N', 'MCP')),
    
    -- Queue leasing fields
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    lease_expires_at TIMESTAMP,
    
    -- Retry and metadata
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    
    -- Task payload
    intent TEXT NOT NULL,
    payload JSON,
    
    -- Audit timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Source tracking
    requested_by TEXT,
    source TEXT CHECK (source IN ('chat', 'github_pr', 'github_issue', 'cron', 'api'))
);

-- Indexes for tasks table
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_correlation_id ON tasks(correlation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease_expires ON tasks(lease_expires_at) WHERE claimed_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_claimed_by ON tasks(claimed_by) WHERE claimed_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_idempotency ON tasks(idempotency_key);

-- =====================================================
-- REVIEWS TABLE
-- Stores review results for completed tasks
-- =====================================================
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    
    -- Review result
    result TEXT NOT NULL CHECK (result IN ('approve', 'reject', 'blocked')),
    summary TEXT NOT NULL,
    findings JSON, -- Array of finding objects
    
    -- Reviewer info
    reviewer_id TEXT NOT NULL,
    reviewer_role TEXT DEFAULT 'symphony',
    
    -- Review metadata
    started_at TIMESTAMP,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Optional link to PR comment
    pr_comment_url TEXT
);

-- Indexes for reviews table
CREATE INDEX IF NOT EXISTS idx_reviews_task_id ON reviews(task_id);
CREATE INDEX IF NOT EXISTS idx_reviews_result ON reviews(result);
CREATE INDEX IF NOT EXISTS idx_reviews_completed_at ON reviews(completed_at);

-- =====================================================
-- AUDIT_EVENTS TABLE
-- Append-only audit log for all operations
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    
    -- Event details
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actor TEXT NOT NULL, -- 'openclaw', 'devclaw', 'symphony', 'n8n', 'system'
    action TEXT NOT NULL, -- 'task.created', 'task.claimed', 'task.completed', etc.
    
    -- Payload
    payload JSON,
    
    -- Source info
    ip_address TEXT,
    user_agent TEXT
);

-- Indexes for audit_events table (note: no unique constraints to maintain append-only)
CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);

-- Composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_actor_action_time ON audit_events(actor, action, timestamp);

-- =====================================================
-- IDEMPOTENCY KEYS TABLE
-- For tracking and deduplicating requests
-- =====================================================
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP, -- Optional TTL
    response JSON -- Cached response for duplicate requests
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at) WHERE expires_at IS NOT NULL;

-- =====================================================
-- DEAD LETTER QUEUE
-- For tasks that failed permanently
-- =====================================================
CREATE TABLE IF NOT EXISTS dead_letter_tasks (
    id TEXT PRIMARY KEY,
    original_task_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT NOT NULL,
    error_details JSON,
    original_payload JSON
);

CREATE INDEX IF NOT EXISTS idx_dlq_correlation_id ON dead_letter_tasks(correlation_id);
CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON dead_letter_tasks(failed_at);

-- =====================================================
-- VIEWS FOR COMMON QUERIES
-- =====================================================

-- View: Tasks ready to be claimed (queued and lease expired or never claimed)
CREATE VIEW IF NOT EXISTS v_tasks_available AS
SELECT * FROM tasks 
WHERE status = 'queued' 
  AND (claimed_by IS NULL OR lease_expires_at < datetime('now'));

-- View: Stuck tasks (claimed but lease expired)
CREATE VIEW IF NOT EXISTS v_tasks_stuck AS
SELECT * FROM tasks 
WHERE claimed_by IS NOT NULL 
  AND lease_expires_at < datetime('now')
  AND status IN ('executing', 'review_queued');

-- View: Task metrics summary
CREATE VIEW IF NOT EXISTS v_task_metrics AS
SELECT 
    status,
    assigned_to,
    COUNT(*) as count,
    AVG(julianday('now') - julianday(created_at)) * 24 * 60 as avg_age_minutes
FROM tasks
GROUP BY status, assigned_to;

-- =====================================================
-- TRIGGERS FOR AUTOMATIC TIMESTAMP UPDATES
-- =====================================================
CREATE TRIGGER IF NOT EXISTS tr_tasks_updated_at
AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
