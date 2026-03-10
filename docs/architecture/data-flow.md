# Data Flow Documentation

## Overview

This document describes the complete data flow through the OpenClaw Orchestration Stack, from initial request ingestion to final resolution.

## Request Lifecycle

### Phase 1: Request Ingestion (OpenClaw)

**Entry Points:**
- REST API (`POST /ingest`)
- GitHub Webhooks (PR events, Issue events)
- Scheduled triggers (Cron)
- CLI commands

**Data Flow:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Request    │────►│   Validate   │────►│  Generate    │
│   Source     │     │   Request    │     │   IDs        │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Route to   │◄────│   Check      │◄────│   Classify   │
│   Worker     │     │   Idempotency│     │   Intent     │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Key Data Transformations:**
- Raw request → Structured `IngestRequest`
- Payload → `IntentClassification` (category, confidence, keywords)
- Intent + Context → `RoutingDecision` (worker_type, action_type)
- All fields + Metadata → `ActionPlan`

**Example:**
```javascript
// Input: Raw request
{
  "payload": {
    "type": "feature_request",
    "description": "Add user authentication"
  },
  "context": {
    "source": "github_webhook",
    "repository": "myorg/myrepo"
  }
}

// Output: ActionPlan
{
  "plan_id": "plan_a1b2c3d4",
  "correlation_id": "corr_12345678",
  "request_id": "req_87654321",
  "intent": {
    "category": "feature_request",
    "confidence": 0.95,
    "confidence_level": "high",
    "keywords": ["add", "authentication"]
  },
  "routing": {
    "worker_type": "DEVCLAW",
    "action_type": "code_generation",
    "confidence": 0.92,
    "reasoning": "Clear feature development request",
    "requires_review": true
  }
}
```

### Phase 2: Queue Management (n8n)

**Data Flow:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Receive     │────►│  Write Audit │────►│  Create      │
│  ActionPlan  │     │  Event       │     │  Task        │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Worker      │◄────│  Assign      │◄────│  Set         │
│  Picks Up    │     │  Worker      │     │  Status      │
└──────────────┘     └──────────────┘     └──────────────┘
```

**Database Operations:**
```sql
-- Create task from ActionPlan
INSERT INTO tasks (
    id, correlation_id, status, assigned_to, 
    payload, created_at
) VALUES (
    'task_001', 'corr_001', 'queued', 'DEVCLAW',
    '{"plan_id": "plan_001", ...}', 
    datetime('now')
);

-- Write audit event
INSERT INTO audit_events (
    id, correlation_id, actor, action, payload
) VALUES (
    'audit_001', 'corr_001', 'n8n', 'task.created',
    '{"task_id": "task_001"}'
);
```

### Phase 3: Task Execution (DevClaw)

**Data Flow:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Claim       │────►│  Checkout    │────►│  Apply       │
│  Task Lease  │     │  Repository  │     │  Changes     │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Report      │◄────│  Run         │◄────│  Commit &    │
│  Results     │     │  Tests       │     │  Push        │
└──────────────┘     └──────────────┘     └──────────────┘
```

**State Transitions:**
```
queued → executing → [success: review_queued | failure: failed]
```

**Database Operations:**
```sql
-- Claim task (atomic operation)
UPDATE tasks 
SET status = 'executing',
    claimed_by = 'worker-001',
    claimed_at = datetime('now'),
    lease_expires_at = datetime('now', '+5 minutes')
WHERE id = 'task_001' 
  AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'));

-- Update on completion
UPDATE tasks 
SET status = 'review_queued',
    updated_at = datetime('now')
WHERE id = 'task_001';
```

**Payload Transformation:**
```javascript
// Task payload (from ActionPlan)
{
  "intent": "CODE_CHANGE",
  "repository": "myorg/myrepo",
  "branch": "feature/auth",
  "changes": [
    {
      "operation": "create",
      "file_path": "auth.py",
      "content": "..."
    }
  ],
  "run_tests": true,
  "test_framework": "pytest"
}

// Execution result
{
  "success": true,
  "files_changed": ["auth.py"],
  "test_results": {
    "success": true,
    "returncode": 0,
    "stdout": "..."
  },
  "metadata": {
    "intent": "CODE_CHANGE",
    "pr_url": "https://github.com/..."
  }
}
```

### Phase 4: PR Management (Symphony)

**Data Flow:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Receive     │────►│  Create/     │────►│  Add         │
│  Completion  │     │  Update PR   │     │  Labels      │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Trigger     │◄────│  Post        │◄────│  Update      │
│  Review      │     │  Comment     │     │  Status      │
└──────────────┘     └──────────────┘     └──────────────┘
```

**GitHub API Interactions:**
```python
# Create PR
created_pr = github_client.create_pull_request(
    owner="myorg",
    repo="myrepo",
    title="Add user authentication",
    body="...",
    head="feature/auth",
    base="main"
)

# Add labels
label_manager.add_label(
    owner="myorg",
    repo="myrepo",
    pr_number=created_pr["number"],
    label="openclaw"
)

# Post welcome comment
review_manager.post_comment(
    owner="myorg",
    repo="myrepo",
    pr_number=created_pr["number"],
    body="## 👋 Welcome to OpenClaw!..."
)
```

### Phase 5: Review Process (Symphony)

**Data Flow:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dequeue     │────►│  Fetch PR    │────►│  Analyze     │
│  Review Task │     │  Diff        │     │  Changes     │
└──────────────┘     └──────────────┘     └──────────────┘
                                                   │
                                                   ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Update      │◄────│  Record      │◄────│  Post        │
│  Task Status │     │  Review      │     │  Findings    │
└──────────────┘     └──────────────┘     └──────────────┘
```

**State Transitions:**
```
review_queued → [approve: approved | reject: review_failed | block: blocked]
```

**Review Checklist:**
1. Correctness — Does the code do what it claims?
2. Bugs — Are there obvious bugs or edge cases?
3. Security — Are there security concerns?
4. Style — Does it follow project conventions?
5. Tests — Are there adequate tests?
6. Scope — Is the change appropriately scoped?

**Database Operations:**
```sql
-- Record review
INSERT INTO reviews (
    id, task_id, result, summary, findings, reviewer_id
) VALUES (
    'review_001', 'task_001', 'approve',
    'Code looks good, tests pass',
    '{"issues": [], "suggestions": []}',
    'symphony-reviewer'
);

-- Update task status
UPDATE tasks 
SET status = 'approved',
    updated_at = datetime('now')
WHERE id = 'task_001';
```

### Phase 6: Resolution

**Approved Path:**
```
approved → merged
```

**Rejected Path (Remediation):**
```
review_failed → remediation_queued → executing → review_queued
```

**Blocked Path:**
```
review_queued → blocked [manual intervention required]
```

## Event Flow Diagrams

### GitHub Webhook Flow

```
GitHub ──► Webhook ──► n8n ──► Symphony
  │                      │         │
  │                      │         ├─► PR Opened → Add labels
  │                      │         ├─► PR Sync → Update labels
  │                      │         └─► Review Submitted → Update status
  │                      │
  │                      └─► Audit log
  │
  └─► Signature validation
```

### API Request Flow

```
Client ──► API ──► OpenClaw ──► n8n ──► Queue
  │         │         │          │        │
  │         │         │          │        ├─► Task created
  │         │         │          │        └─► Worker picks up
  │         │         │          │
  │         │         │          └─► Audit event
  │         │         │
  │         │         └─► Intent classification
  │         │         └─► Routing decision
  │         │         └─► Action plan
  │         │
  │         └─► API key validation
  │         └─► Rate limiting
  │
  └─► HTTP request
```

### Task Retry Flow

```
┌─────────┐    ┌──────────┐    ┌──────────┐
│  Task   │───►│  Failure │───►│  Retry?  │
│  Fails  │    │  Handler │    │ Count <  │
└─────────┘    └──────────┘    │  Max?    │
                               └────┬─────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │ Yes                           │ No
                    ▼                               ▼
            ┌──────────────┐              ┌──────────────┐
            │ Increment    │              │  Mark as     │
            │ Retry Count  │              │  Dead Letter │
            └──────┬───────┘              └──────────────┘
                   │
                   ▼
            ┌──────────────┐
            │ Re-queue     │
            │ with backoff │
            └──────────────┘
```

## Data Models

### Correlation ID Flow

The `correlation_id` is the primary tracing mechanism:

```
Request ──► OpenClaw ──► n8n ──► DevClaw ──► Symphony
   │            │          │          │           │
   │            │          │          │           │
   └────────────┴──────────┴──────────┴───────────┘
              correlation_id = "corr_abc123"
```

All audit events, logs, and database records include the correlation_id for end-to-end tracing.

### Idempotency Key Flow

```
Client ──► API ──► Check Key ──► [Exists: Return cached] 
  │                              [New: Process & store]
  │                                    │
  └────────────────────────────────────┘
          Same key = Same result
```

### Lease Management Flow

```
Worker ──► Claim Task ──► [Lease valid?] ──► [Yes: Proceed]
   │                          │                [No: Skip]
   │                          │
   │                    [Set expires_at]
   │                    [Set claimed_by]
   │
   └─── Heartbeat ──► [Extend lease]
   │
   └─── Complete ──► [Release lease]
   │
   └─── Crash ──► [Lease expires] ──► [Task re-queued]
```

## Error Handling Flow

### Routing Error

```
Request ──► Classify ──► [Ambiguous] ──► Error Response
                              │
                              └─► Log to audit
                              └─► Return 400
```

### Execution Error

```
Task ──► Execute ──► [Exception] ──► Catch ──► Log
  │                                    │
  │                                    ├─► Retry logic
  │                                    │
  │                                    └─► Update status: failed
  │
  └─► Audit event: task.failed
```

### GitHub API Error

```
API Call ──► [Rate limit] ──► Backoff ──► Retry
  │                              │
  └─► [Auth error] ──► Alert admin
  │
  └─► [Not found] ──► Mark task failed
```

## Audit Trail Flow

Every significant action is logged:

```
Action ──► Audit Logger ──► audit_events table
  │                              │
  ├─► request.received           ├─► correlation_id
  ├─► action_plan.created        ├─► timestamp
  ├─► task.created               ├─► actor
  ├─► task.claimed               ├─► action
  ├─► task.completed             └─► payload (JSON)
  ├─► review.started
  ├─► review.completed
  └─► task.merged
```

## Webhook Payload Flow

### PR Opened

```
GitHub ──► Webhook ──► Validate ──► Parse ──► Handler
  │           │           │          │         │
  │           │           │          │         ├─► Add labels
  │           │           │          │         ├─► Post comment
  │           │           │          │         └─► Audit log
  │           │           │          │
  │           │           │          └─► PREvent object
  │           │           │
  │           │           └─► HMAC signature
  │           │
  │           └─► X-GitHub-Event: pull_request
  │           └─► X-Hub-Signature-256
  │
  └─► JSON payload
```

## Data Retention

| Data Type | Retention | Cleanup Strategy |
|-----------|-----------|------------------|
| Tasks | 90 days | Archive to S3, delete from DB |
| Audit Events | 1 year | Partition by month |
| Reviews | Forever | Keep for compliance |
| Dead Letters | 30 days | Alert and archive |

## Performance Considerations

### Database Queries

**Optimized Queries:**
```sql
-- Get pending tasks (uses idx_tasks_assigned_status)
SELECT * FROM tasks 
WHERE assigned_to = ? AND status = 'queued'
AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'))
ORDER BY created_at
LIMIT ?;

-- Get audit trail (uses idx_audit_correlation_timestamp)
SELECT * FROM audit_events 
WHERE correlation_id = ? 
ORDER BY timestamp;
```

### Caching Strategy

- **Idempotency Keys** — In-memory cache with TTL
- **GitHub API** — ETag-based caching
- **Action Plans** — Short-term result caching

### Batch Processing

```python
# Batch ingest
POST /ingest/batch
Content-Type: application/json

[
  {"payload": {...}},
  {"payload": {...}},
  {"payload": {...}}
]

# Returns list of ActionPlans
```

## References

- [System Design](./system-design.md) — Architecture overview
- [State Machine](./state-machine.md) — Task state transitions
- [REST API](../api/rest-api.md) — API endpoints
- [Webhook Documentation](../api/webhooks.md) — Webhook payloads
