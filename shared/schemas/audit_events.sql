-- Audit events table schema
-- Stores audit trail for all system actions

CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    payload JSON
);

-- Indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_correlation_id ON audit_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_correlation_timestamp ON audit_events(correlation_id, timestamp);
