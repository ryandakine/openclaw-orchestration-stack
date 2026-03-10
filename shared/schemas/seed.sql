-- Seed data for OpenClaw Orchestration Stack
-- Sample data for development and testing

-- ============================================
-- SAMPLE TASKS
-- ============================================

INSERT INTO tasks (id, correlation_id, status, assigned_to, payload, created_at, updated_at) VALUES
('task_001', 'corr_001', 'approved', 'DEVCLAW', 
 '{"type": "code_generation", "description": "Generate API endpoint for user authentication", "language": "python", "framework": "fastapi"}',
 '2024-01-15 10:00:00', '2024-01-15 10:30:00'),

('task_002', 'corr_002', 'review_queued', 'SYMPHONY',
 '{"type": "code_review", "description": "Review database schema changes", "files": ["schema.sql", "models.py"]}',
 '2024-01-15 11:00:00', '2024-01-15 11:15:00'),

('task_003', 'corr_003', 'queued', 'DEVCLAW',
 '{"type": "refactoring", "description": "Refactor authentication middleware", "target": "middleware/auth.py"}',
 '2024-01-15 12:00:00', NULL),

('task_004', 'corr_004', 'executing', 'DEVCLAW',
 '{"type": "bug_fix", "description": "Fix memory leak in connection pool", "priority": "high"}',
 '2024-01-15 13:00:00', '2024-01-15 13:05:00'),

('task_005', 'corr_005', 'failed', 'DEVCLAW',
 '{"type": "test_generation", "description": "Generate unit tests for payment service", "error": "Timeout during test execution"}',
 '2024-01-15 14:00:00', '2024-01-15 14:10:00'),

('task_006', 'corr_006', 'blocked', 'SYMPHONY',
 '{"type": "deployment", "description": "Deploy to production environment", "blocker": "Security review pending"}',
 '2024-01-15 15:00:00', '2024-01-15 15:30:00'),

('task_007', 'corr_007', 'merged', 'DEVCLAW',
 '{"type": "feature", "description": "Add caching layer for API responses", "language": "python"}',
 '2024-01-15 09:00:00', '2024-01-15 09:45:00');

-- ============================================
-- SAMPLE REVIEWS
-- ============================================

INSERT INTO reviews (id, task_id, result, summary, findings, reviewer_id, created_at) VALUES
('review_001', 'task_001', 'approve', 
 'Code generation completed successfully. All requirements met.',
 '[{"severity": "info", "message": "Good use of type hints"}, {"severity": "info", "message": "Proper error handling implemented"}]',
 'reviewer_001',
 '2024-01-15 10:25:00'),

('review_002', 'task_002', 'reject',
 'Security concerns identified in database access patterns.',
 '[{"severity": "critical", "message": "SQL injection vulnerability detected"}, {"severity": "warning", "message": "Missing input validation"}]',
 'reviewer_002',
 '2024-01-15 11:20:00'),

('review_003', 'task_006', 'blocked',
 'Deployment blocked pending security audit.',
 '[{"severity": "critical", "message": "Security audit not completed"}, {"severity": "warning", "message": "Missing deployment documentation"}]',
 'reviewer_003',
 '2024-01-15 15:25:00'),

('review_004', 'task_007', 'approve',
 'Excellent implementation. Caching strategy is sound.',
 '[{"severity": "info", "message": "Efficient cache key generation"}, {"severity": "info", "message": "Proper TTL configuration"}]',
 'reviewer_001',
 '2024-01-15 09:40:00');

-- ============================================
-- SAMPLE AUDIT EVENTS
-- ============================================

INSERT INTO audit_events (id, correlation_id, timestamp, actor, action, payload) VALUES
('audit_001', 'corr_001', '2024-01-15 10:00:00', 'openclaw', 'task_created',
 '{"task_id": "task_001", "type": "code_generation"}'),

('audit_002', 'corr_001', '2024-01-15 10:15:00', 'devclaw', 'task_claimed',
 '{"task_id": "task_001", "worker": "devclaw_worker_1"}'),

('audit_003', 'corr_001', '2024-01-15 10:30:00', 'devclaw', 'task_completed',
 '{"task_id": "task_001", "status": "completed"}'),

('audit_004', 'corr_001', '2024-01-15 10:31:00', 'symphony', 'review_requested',
 '{"task_id": "task_001", "review_id": "review_001"}'),

('audit_005', 'corr_001', '2024-01-15 10:35:00', 'symphony', 'review_completed',
 '{"task_id": "task_001", "review_id": "review_001", "result": "approve"}'),

('audit_006', 'corr_001', '2024-01-15 10:36:00', 'openclaw', 'task_merged',
 '{"task_id": "task_001"}'),

('audit_007', 'corr_002', '2024-01-15 11:00:00', 'openclaw', 'task_created',
 '{"task_id": "task_002", "type": "code_review"}'),

('audit_008', 'corr_005', '2024-01-15 14:10:00', 'devclaw', 'task_failed',
 '{"task_id": "task_005", "error": "Timeout during test execution"}'),

('audit_009', 'corr_005', '2024-01-15 14:11:00', 'openclaw', 'retry_scheduled',
 '{"task_id": "task_005", "retry_count": 1, "next_attempt": "2024-01-15 14:20:00"}');
