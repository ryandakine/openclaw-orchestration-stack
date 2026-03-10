-- OpenClaw Orchestration Stack - SQLite Database Schema
-- Version: 1.2.1

-- ============================================================================
-- Tasks Table - Core task storage
-- ============================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' 
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')),
    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    intent TEXT,
    route_target TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    worker_id TEXT,
    result TEXT,
    error_message TEXT,
    metadata TEXT,  -- JSON blob
    parent_task_id TEXT,
    FOREIGN KEY (parent_task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_worker ON tasks(worker_id);

-- ============================================================================
-- Task Queue Table - For lease-based work distribution
-- ============================================================================
CREATE TABLE IF NOT EXISTS task_queue (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'queued' 
        CHECK (status IN ('queued', 'leased', 'completed', 'failed')),
    lease_expires_at TIMESTAMP,
    worker_id TEXT,
    lease_count INTEGER DEFAULT 0,
    max_leases INTEGER DEFAULT 3,
    queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_status ON task_queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_lease ON task_queue(lease_expires_at);

-- ============================================================================
-- Workers Table - Worker registration and health
-- ============================================================================
CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active' 
        CHECK (status IN ('active', 'paused', 'offline', 'disabled')),
    capabilities TEXT,  -- JSON array of capabilities
    last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_tasks_completed INTEGER DEFAULT 0,
    total_tasks_failed INTEGER DEFAULT 0,
    metadata TEXT  -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);
CREATE INDEX IF NOT EXISTS idx_workers_heartbeat ON workers(last_heartbeat);

-- ============================================================================
-- Reviews Table - Code review tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    repository TEXT NOT NULL,
    pr_number INTEGER NOT NULL,
    commit_sha TEXT,
    status TEXT DEFAULT 'pending' 
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed')),
    reviewer TEXT,  -- worker_id or 'ai'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    summary TEXT,
    findings_count INTEGER DEFAULT 0,
    metadata TEXT,  -- JSON blob
    UNIQUE(repository, pr_number, commit_sha)
);

CREATE INDEX IF NOT EXISTS idx_reviews_repo ON reviews(repository);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);

-- ============================================================================
-- Review Findings Table - Individual review comments/issues
-- ============================================================================
CREATE TABLE IF NOT EXISTS review_findings (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    severity TEXT CHECK (severity IN ('critical', 'warning', 'suggestion', 'praise')),
    category TEXT,  -- security, performance, style, etc.
    message TEXT NOT NULL,
    suggestion TEXT,
    code_snippet TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_findings_review ON review_findings(review_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON review_findings(severity);

-- ============================================================================
-- Audit Log Table - System events
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level TEXT CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    component TEXT NOT NULL,  -- api, worker, symphony, etc.
    event_type TEXT NOT NULL,
    task_id TEXT,
    worker_id TEXT,
    message TEXT NOT NULL,
    metadata TEXT  -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_component ON audit_log(component);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_log(task_id);

-- ============================================================================
-- Idempotency Keys Table - Prevent duplicate operations
-- ============================================================================
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    response TEXT  -- Cached response for completed operations
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires ON idempotency_keys(expires_at);

-- ============================================================================
-- Webhook Events Table - GitHub webhook tracking
-- ============================================================================
CREATE TABLE IF NOT EXISTS webhook_events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,  -- github, gitlab, etc.
    event_type TEXT NOT NULL,  -- pull_request, push, etc.
    payload TEXT NOT NULL,  -- JSON payload
    signature TEXT,
    processed BOOLEAN DEFAULT FALSE,
    processing_result TEXT,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_webhook_source ON webhook_events(source);
CREATE INDEX IF NOT EXISTS idx_webhook_processed ON webhook_events(processed);

-- ============================================================================
-- Configuration Table - System settings
-- ============================================================================
CREATE TABLE IF NOT EXISTS configuration (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default configuration
INSERT OR IGNORE INTO configuration (key, value, description) VALUES
    ('max_workers', '5', 'Maximum number of concurrent workers'),
    ('task_timeout', '300', 'Task execution timeout in seconds'),
    ('lease_duration', '300', 'Task lease duration in seconds'),
    ('max_retries', '3', 'Maximum task retry attempts'),
    ('enable_audit_log', 'true', 'Enable detailed audit logging'),
    ('github_webhook_secret', '', 'GitHub webhook secret'),
    ('api_rate_limit', '100', 'API requests per minute per client');

-- ============================================================================
-- Views for Common Queries
-- ============================================================================

-- Active tasks view
CREATE VIEW IF NOT EXISTS v_active_tasks AS
SELECT 
    t.*,
    w.name as worker_name
FROM tasks t
LEFT JOIN workers w ON t.worker_id = w.id
WHERE t.status IN ('pending', 'in_progress')
ORDER BY t.priority ASC, t.created_at ASC;

-- Worker performance view
CREATE VIEW IF NOT EXISTS v_worker_stats AS
SELECT 
    w.id,
    w.name,
    w.status,
    w.total_tasks_completed,
    w.total_tasks_failed,
    CASE 
        WHEN w.total_tasks_completed + w.total_tasks_failed = 0 THEN 0
        ELSE (w.total_tasks_completed * 100.0 / (w.total_tasks_completed + w.total_tasks_failed))
    END as success_rate,
    w.last_heartbeat
FROM workers w;

-- Review summary view
CREATE VIEW IF NOT EXISTS v_review_summary AS
SELECT 
    r.*,
    COUNT(f.id) as total_findings,
    SUM(CASE WHEN f.severity = 'critical' THEN 1 ELSE 0 END) as critical_count,
    SUM(CASE WHEN f.severity = 'warning' THEN 1 ELSE 0 END) as warning_count,
    SUM(CASE WHEN f.severity = 'suggestion' THEN 1 ELSE 0 END) as suggestion_count
FROM reviews r
LEFT JOIN review_findings f ON r.id = f.review_id
GROUP BY r.id;

-- ============================================================================
-- Triggers for Updated Timestamps
-- ============================================================================

CREATE TRIGGER IF NOT EXISTS update_tasks_timestamp 
AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- ============================================================================
-- Cleanup Procedure (run periodically)
-- ============================================================================

-- Delete old completed tasks (keep 30 days)
DELETE FROM tasks 
WHERE status IN ('completed', 'failed', 'cancelled') 
AND completed_at < datetime('now', '-30 days');

-- Delete expired idempotency keys
DELETE FROM idempotency_keys 
WHERE expires_at < datetime('now');

-- Delete old processed webhooks (keep 7 days)
DELETE FROM webhook_events 
WHERE processed = TRUE 
AND received_at < datetime('now', '-7 days');

-- Vacuum to reclaim space
VACUUM;
