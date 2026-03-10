# Queue Leasing and Idempotency for OpenClaw Orchestration Stack

This module provides atomic task claiming, idempotency, deduplication, and dead letter queue functionality for the OpenClaw Orchestration Stack.

## Modules

### 1. lease_manager.py - Queue Leasing System

Provides atomic task claiming and lease management for distributed workers using SQLite atomic operations.

**Key Classes:**
- `LeaseManager` - Main lease management class
- `Lease` - Dataclass representing a task lease

**Key Methods:**
- `claim_task(task_id, worker_id, lease_duration)` - Atomically claim a task using UPDATE ... WHERE
- `claim_next_available(worker_id, assigned_to)` - Claim the next available task
- `extend_lease(task_id, worker_id, extension_duration)` - Extend an existing lease
- `release_lease(task_id, worker_id, new_status)` - Release lease on completion/failure
- `handle_expired_leases(max_retries)` - Reset expired leases to queued state
- `get_lease(task_id)` - Get current lease information
- `is_claimed_by(task_id, worker_id)` - Check if task is claimed by specific worker
- `get_stuck_tasks(older_than_seconds)` - Monitor stuck/expired leases
- `get_worker_tasks(worker_id)` - Get all tasks claimed by a worker

**Lease Format:**
```python
{
    "claimed_by": "worker-id",
    "claimed_at": "2026-03-09T12:00:00Z",
    "lease_expires_at": "2026-03-09T12:05:00Z"
}
```

### 2. idempotency.py - Idempotency Key System

Provides request deduplication using idempotency keys with TTL-based expiration.

**Key Classes:**
- `IdempotencyStore` - SQLite-based idempotency store
- `IdempotencyContext` - Context manager for idempotency operations
- `IdempotencyStatus` - Enum for key status (NEW, IN_PROGRESS, COMPLETED, EXPIRED)

**Key Methods:**
- `check_idempotency(key, request_data)` - Check if key exists and get status
- `start_processing(key, correlation_id, request_data)` - Mark key as being processed
- `store_response(key, response_data)` - Cache response for key
- `get_cached_response(key)` - Return cached result
- `complete(key, response_data)` - Complete request and cache response
- `fail(key, error_data, keep_for_retry)` - Mark request as failed
- `cleanup_expired()` - Clean up expired keys
- `generate_key(*components)` - Generate deterministic key from components

### 3. deduplication.py - Duplicate Request Handling

Manages request deduplication using correlation_id and idempotency_key with in-flight tracking.

**Key Classes:**
- `DeduplicationManager` - Main deduplication manager
- `DeduplicationContext` - Context manager for deduplication
- `DuplicateStatus` - Enum for duplicate status (NEW, IN_FLIGHT, COMPLETED, DUPLICATE)

**Key Methods:**
- `detect_duplicate(correlation_id, idempotency_key, request_data)` - Check if request is duplicate
- `track_in_flight(correlation_id, idempotency_key, worker_id)` - Track request being processed
- `return_cached(correlation_id, idempotency_key)` - Return cached result
- `complete_request(correlation_id, idempotency_key, response_data)` - Mark as completed
- `fail_request(correlation_id, idempotency_key, error_data, allow_retry)` - Mark as failed
- `get_in_flight_requests(worker_id)` - List in-flight requests
- `cleanup_expired()` - Clean up expired records

### 4. dead_letter.py - Dead Letter Queue

Handles tasks that have exceeded their maximum retry attempts.

**Key Classes:**
- `DeadLetterQueue` - Main DLQ manager
- `DLQEntry` - Dataclass for DLQ entries
- `DLQReason` - Enum for failure reasons

**Key Methods:**
- `move_to_dlq(task_id, correlation_id, reason, error_details)` - Move failed task to DLQ
- `get_dlq_items(include_archived, reason, limit)` - List DLQ items
- `get_dlq_item(dlq_id)` - Get specific DLQ item
- `retry_from_dlq(dlq_id, new_worker_id)` - Manual retry from DLQ
- `retry_all_from_dlq(reason, max_age_hours)` - Retry all eligible items
- `archive_dlq_item(dlq_id)` - Archive item without retry
- `delete_dlq_item(dlq_id)` - Permanently delete DLQ item
- `analyze_failures(start_date, end_date)` - Analyze failure patterns
- `cleanup_old_items(older_than_days)` - Clean up old archived items

## Usage Examples

### Task Claiming

```python
from shared.utils.lease_manager import LeaseManager

manager = LeaseManager(default_lease_duration=300)

# Claim a specific task
lease = manager.claim_task("task-123", "worker-1")
if lease:
    try:
        # Process task
        process_task("task-123")
        manager.release_lease("task-123", "worker-1", "completed")
    except Exception as e:
        manager.release_lease("task-123", "worker-1", "failed")

# Or claim next available
result = manager.claim_next_available("worker-1", assigned_to="DEVCLAW")
if result:
    task_id, lease = result
    # Process task...
```

### Idempotency

```python
from shared.utils.idempotency import IdempotencyStore

store = IdempotencyStore(default_ttl=86400)

# Check and process
status, cached = store.check_idempotency("key-123")
if status.value == "completed":
    return cached

# Start processing
if store.start_processing("key-123", "corr-456"):
    try:
        result = process_request()
        store.complete("key-123", result)
        return result
    except Exception as e:
        store.fail("key-123", {"error": str(e)})
        raise
```

### Using Context Managers

```python
from shared.utils.idempotency import IdempotencyContext
from shared.utils.deduplication import DeduplicationContext

# Idempotency context
with IdempotencyContext(store, "key-123", "corr-456") as ctx:
    if ctx.should_execute:
        result = process_request()
        ctx.complete(result)
    else:
        return ctx.cached_response

# Deduplication context
with DeduplicationContext(manager, "corr-456", "key-123") as ctx:
    if ctx.should_execute:
        result = process_request()
        ctx.complete(result)
    else:
        return ctx.cached_response
```

### Dead Letter Queue

```python
from shared.utils.dead_letter import DeadLetterQueue, DLQReason

dlq = DeadLetterQueue(max_dlq_age_days=30)

# Move failed task to DLQ
dlq_id = dlq.move_to_dlq(
    task_id="task-123",
    correlation_id="corr-456",
    reason=DLQReason.MAX_RETRIES_EXCEEDED,
    error_details={"error": "Max retries exceeded"}
)

# List DLQ items
items = dlq.get_dlq_items()

# Retry from DLQ
new_task_id = dlq.retry_from_dlq(dlq_id, new_worker_id="worker-2")

# Analyze failures
analysis = dlq.analyze_failures()
```

## Testing

Run the test suite:

```bash
cd /home/ryan/openclaw-orchestration-stack
python3 -m pytest shared/utils/tests/ -v
```

Test coverage includes:
- Concurrent claiming tests
- Lease expiry tests
- Idempotency tests
- Duplicate prevention tests
- DLQ operations tests

## Key Features

1. **Atomic Operations**: Uses SQLite `UPDATE ... WHERE` for atomic task claiming
2. **Worker Crash Recovery**: Expired leases are automatically detected and reset
3. **Duplicate Prevention**: Multiple layers (idempotency keys + correlation IDs)
4. **TTL-based Expiration**: Automatic cleanup of expired records
5. **In-flight Tracking**: Prevents concurrent processing of same request
6. **Dead Letter Queue**: Handles permanent failures with manual retry capability
7. **Audit Trail**: All operations logged to audit_events table

## Integration with Existing Code

The modules integrate with the existing database schema defined in `shared/schemas/schema.sql`:

- Uses existing `tasks` table with lease fields
- Uses existing `audit_events` table for logging
- Creates additional tables for idempotency, deduplication, and DLQ

All modules use the shared `shared.db` connection pool for thread-safe database access.
