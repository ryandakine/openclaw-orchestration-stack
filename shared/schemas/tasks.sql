-- Tasks table schema
-- Stores task information for the OpenClaw orchestration system

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'executing', 'review_queued', 'approved', 'merged', 'failed', 'blocked')),
    assigned_to TEXT NOT NULL CHECK (assigned_to IN ('DEVCLAW', 'SYMPHONY')),
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    lease_expires_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    payload JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_correlation_id ON tasks(correlation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease_expires_at ON tasks(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_claimed_by ON tasks(claimed_by);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
