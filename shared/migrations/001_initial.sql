-- Migration: 001_initial
-- Description: Initial schema creation for OpenClaw Orchestration Stack
-- Created: 2024-01-15

-- ============================================
-- TASKS TABLE
-- ============================================

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

-- ============================================
-- REVIEWS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('approve', 'reject', 'blocked')),
    summary TEXT,
    findings JSON,
    reviewer_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

-- ============================================
-- AUDIT EVENTS TABLE
-- ============================================

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSON
);

-- ============================================
-- INDEXES
-- ============================================

-- Tasks table indexes
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_correlation_id ON tasks(correlation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease_expires_at ON tasks(lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_tasks_claimed_by ON tasks(claimed_by);
CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_status ON tasks(assigned_to, status);

-- Reviews table indexes
CREATE INDEX IF NOT EXISTS idx_reviews_task_id ON reviews(task_id);
CREATE INDEX IF NOT EXISTS idx_reviews_result ON reviews(result);
CREATE INDEX IF NOT EXISTS idx_reviews_reviewer_id ON reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_created_at ON reviews(created_at);

-- Audit events table indexes
CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_correlation_timestamp ON audit_events(correlation_id, timestamp);

-- ============================================
-- MIGRATION METADATA
-- ============================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT INTO schema_migrations (version, description) VALUES ('001_initial', 'Initial schema creation');
