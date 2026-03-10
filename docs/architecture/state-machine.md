# Task State Machine

## Overview

The OpenClaw Orchestration Stack uses a comprehensive state machine to track tasks through their entire lifecycle. This ensures reliability, enables auditability, and provides clear visibility into the system.

## State Diagram

```
                         ┌─────────────┐
                    ┌───►│   MERGED    │◄────────────────────────┐
                    │    │  (terminal) │                         │
                    │    └─────────────┘                         │
                    │                                            │
┌─────────┐    ┌─────────┐    ┌─────────────┐    ┌─────────┐    │
│  QUEUED │───►│EXECUTING│───►│REVIEW_QUEUED│───►│APPROVED │────┘
└────┬────┘    └────┬────┘    └──────┬──────┘    └─────────┘
     │              │                │
     │              │                │
     ▼              ▼                ▼
┌─────────┐    ┌─────────────┐   ┌─────────┐
│  FAILED │    │REVIEW_FAILED│──►│ BLOCKED │
│(terminal)│   └──────┬──────┘   │(terminal)│
└─────────┘          │          └─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │REMEDIATION_QUEUED│
            └────────┬─────────┘
                     │
                     └───────────────────────┐
                                              │
                     ┌────────────────────────┘
                     ▼
              ┌─────────┐
              │EXECUTING│ (retry path)
              └─────────┘
```

## State Definitions

### Core States

| State | Description | Entry Conditions | Exit Conditions |
|-------|-------------|------------------|-----------------|
| `queued` | Task waiting to be picked up | Task created by n8n | Worker claims lease |
| `executing` | Task actively being worked on | Worker claims lease | Work completes or fails |
| `review_queued` | Awaiting code review | DevClaw reports completion | Review starts |
| `approved` | Review passed, ready for merge | Symphony approves | PR merged |
| `merged` | Successfully merged | PR merged to main | Terminal state |

### Failure States

| State | Description | Recovery Path |
|-------|-------------|---------------|
| `failed` | Execution failed | Manual retry or dead letter |
| `review_failed` | Review found issues | Remediation loop |
| `blocked` | Blocked pending information | Manual intervention |

### Transient States

| State | Description | Duration |
|-------|-------------|----------|
| `remediation_queued` | Fix queued after failed review | Until picked up |

## State Transitions

### Success Path

```
queued → executing → review_queued → approved → merged
```

**Trigger Events:**
1. `queued` → `executing`: Worker claims task lease
2. `executing` → `review_queued`: DevClaw reports success
3. `review_queued` → `approved`: Symphony approves changes
4. `approved` → `merged`: PR merged to main branch

### Failure Paths

#### Execution Failure

```
executing → failed
```

**Recovery Options:**
- Automatic retry (if retry_count < max_retries)
- Manual retry via API
- Dead letter queue (if max retries exceeded)

#### Review Failure (Remediation Loop)

```
review_queued → review_failed → remediation_queued → executing → review_queued
```

**Max Remediation Loops:** 3 (configurable)

After 3 failed remediation attempts:
```
review_failed → blocked
```

#### Blocked State

```
review_queued → blocked
review_failed → blocked (after max remediations)
```

**Exit:** Manual intervention only

### Timeout Transitions

| State | Timeout | Action |
|-------|---------|--------|
| `executing` | 5 minutes | Release lease, return to `queued` |
| `review_queued` | 24 hours | Escalate to admin |
| `remediation_queued` | 1 hour | Alert on-call |

## Lease Management

### Lease States

Tasks in `executing` state have associated lease metadata:

```json
{
  "claimed_by": "worker-001",
  "claimed_at": "2024-01-15T10:30:00Z",
  "lease_expires_at": "2024-01-15T10:35:00Z",
  "heartbeat_at": "2024-01-15T10:32:00Z"
}
```

### Lease Lifecycle

```
Claim Task ──► Set lease_expires_at ──► Heartbeat (extend) ──► Complete ──► Clear lease
   │                  │                       │                    │
   │                  │                       │                    └─► Task status updated
   │                  │                       └─► UPDATE lease_expires_at
   │                  │
   │                  └─► expires_at = now() + lease_duration
   │
   └─► UPDATE claimed_by, claimed_at, lease_expires_at
```

### Lease Expiration

When a lease expires:
1. Task remains in `executing` state temporarily
2. Other workers can claim it (atomic compare-and-swap)
3. Previous worker's updates are rejected
4. Audit event: `task.lease_expired`

## State Persistence

### Database Schema

```sql
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'executing', 'review_queued', 'approved', 
        'merged', 'failed', 'blocked', 'review_failed', 'remediation_queued'
    )),
    assigned_to TEXT NOT NULL CHECK (assigned_to IN ('DEVCLAW', 'SYMPHONY')),
    claimed_by TEXT,
    claimed_at TIMESTAMP,
    lease_expires_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    remediation_count INTEGER DEFAULT 0,
    payload JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- State history for audit
CREATE TABLE task_state_history (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### State History

Every state change is recorded:

```sql
INSERT INTO task_state_history (task_id, from_status, to_status, changed_by, reason)
VALUES ('task_001', 'queued', 'executing', 'worker-001', 'Lease claimed');
```

## Event Hooks

### State Change Callbacks

Register callbacks for state transitions:

```python
from openclaw.src.state_machine import StateMachine

sm = StateMachine()

@sm.on_transition(to='review_queued')
def notify_reviewers(task):
    """Notify reviewers when task is ready for review."""
    send_notification(f"Task {task.id} ready for review")

@sm.on_transition(from_='executing', to='failed')
def handle_failure(task):
    """Handle task failure."""
    if task.retry_count < MAX_RETRIES:
        task.retry()
    else:
        task.dead_letter()
```

### Webhook Notifications

Configure webhooks for state changes:

```yaml
webhooks:
  - url: https://myapp.com/webhooks/openclaw
    events:
      - task.completed
      - task.failed
      - review.approved
    secret: ${WEBHOOK_SECRET}
```

## State Queries

### Common Queries

**Queue depth by status:**
```sql
SELECT status, COUNT(*) as count 
FROM tasks 
GROUP BY status;
```

**Tasks stuck in executing:**
```sql
SELECT * FROM tasks 
WHERE status = 'executing' 
AND lease_expires_at < datetime('now');
```

**Review backlog:**
```sql
SELECT * FROM tasks 
WHERE status = 'review_queued'
ORDER BY created_at;
```

**Failed tasks requiring attention:**
```sql
SELECT * FROM tasks 
WHERE status = 'failed' 
AND retry_count >= 3;
```

## State Machine Implementation

### Python Implementation

```python
from enum import Enum, auto
from dataclasses import dataclass
from typing import Optional, Callable, List
from datetime import datetime, timedelta

class TaskState(Enum):
    QUEUED = "queued"
    EXECUTING = "executing"
    REVIEW_QUEUED = "review_queued"
    APPROVED = "approved"
    MERGED = "merged"
    FAILED = "failed"
    BLOCKED = "blocked"
    REVIEW_FAILED = "review_failed"
    REMEDIATION_QUEUED = "remediation_queued"

class StateMachineError(Exception):
    pass

class InvalidTransitionError(StateMachineError):
    pass

@dataclass
class Task:
    id: str
    state: TaskState
    correlation_id: str
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    retry_count: int = 0
    remediation_count: int = 0

class TaskStateMachine:
    """State machine for task lifecycle management."""
    
    # Valid state transitions
    TRANSITIONS = {
        TaskState.QUEUED: {TaskState.EXECUTING},
        TaskState.EXECUTING: {
            TaskState.REVIEW_QUEUED, 
            TaskState.FAILED,
            TaskState.QUEUED  # Lease expiration
        },
        TaskState.REVIEW_QUEUED: {
            TaskState.APPROVED,
            TaskState.REVIEW_FAILED,
            TaskState.BLOCKED
        },
        TaskState.APPROVED: {TaskState.MERGED},
        TaskState.REVIEW_FAILED: {
            TaskState.REMEDIATION_QUEUED,
            TaskState.BLOCKED
        },
        TaskState.REMEDIATION_QUEUED: {TaskState.EXECUTING},
        TaskState.MERGED: set(),  # Terminal
        TaskState.FAILED: set(),  # Terminal (manual retry only)
        TaskState.BLOCKED: set(),  # Terminal (manual only)
    }
    
    def __init__(self, task: Task):
        self.task = task
        self._callbacks: List[Callable] = []
    
    def can_transition(self, new_state: TaskState) -> bool:
        """Check if transition is valid."""
        return new_state in self.TRANSITIONS.get(self.task.state, set())
    
    def transition(self, new_state: TaskState, actor: str, reason: str = ""):
        """Execute state transition."""
        if not self.can_transition(new_state):
            raise InvalidTransitionError(
                f"Cannot transition from {self.task.state} to {new_state}"
            )
        
        old_state = self.task.state
        self.task.state = new_state
        self._record_transition(old_state, new_state, actor, reason)
        self._trigger_callbacks(old_state, new_state)
    
    def _record_transition(self, from_state: TaskState, to_state: TaskState, 
                          actor: str, reason: str):
        """Record state change in history."""
        # Insert into task_state_history table
        pass
    
    def _trigger_callbacks(self, from_state: TaskState, to_state: TaskState):
        """Trigger registered callbacks."""
        for callback in self._callbacks:
            callback(self.task, from_state, to_state)
```

## Metrics and Monitoring

### State Distribution

```python
# Gauge metric
task_state_distribution = {
    'queued': 15,
    'executing': 5,
    'review_queued': 8,
    'approved': 3,
    'merged': 42,
    'failed': 2,
    'blocked': 1
}
```

### Transition Rates

```
transitions_per_minute = {
    'queued→executing': 10,
    'executing→review_queued': 8,
    'executing→failed': 2,
    'review_queued→approved': 7,
    'review_queued→review_failed': 1
}
```

### Time in State

```
avg_time_in_state = {
    'queued': '30s',
    'executing': '5m',
    'review_queued': '15m',
    'approved→merged': '2h'
}
```

## Best Practices

### 1. Always Record State History

```python
# Good
task.transition('executing', actor='worker-001', reason='Lease claimed')

# Bad
task.state = 'executing'  # No audit trail
```

### 2. Handle Lease Expiration

```python
# Worker must heartbeat
while executing:
    extend_lease(task.id)
    do_work()
```

### 3. Idempotent State Changes

```python
# State change should be safe to retry
try:
    transition_task(task_id, 'approved')
except TaskAlreadyInState:
    pass  # Idempotent success
```

### 4. Clear Failure Reasons

```python
task.transition('failed', actor='devclaw', 
                reason='Test failure: test_auth.py::test_login')
```

## Troubleshooting

### Tasks Stuck in Executing

**Symptoms:** Tasks in `executing` state with expired leases

**Causes:**
- Worker crashed
- Worker stuck in infinite loop
- Network partition

**Resolution:**
```sql
-- Reset stuck tasks
UPDATE tasks 
SET status = 'queued',
    claimed_by = NULL,
    claimed_at = NULL,
    lease_expires_at = NULL
WHERE status = 'executing' 
AND lease_expires_at < datetime('now', '-5 minutes');
```

### Review Queue Backlog

**Symptoms:** Many tasks in `review_queued` state

**Causes:**
- Insufficient review capacity
- Reviewers unavailable
- Complex changes taking longer

**Resolution:**
- Add more reviewers
- Increase review timeout
- Implement priority queue

### Remediation Loop

**Symptoms:** Task cycling between `review_queued` → `review_failed` → `remediation_queued`

**Causes:**
- Unclear requirements
- Fundamental design issues
- Flaky tests

**Resolution:**
- After 3 loops, transition to `blocked`
- Manual intervention required

## References

- [System Design](./system-design.md) — Architecture overview
- [Data Flow](./data-flow.md) — Request lifecycle
- [Troubleshooting Guide](../guides/troubleshooting.md) — Common issues
