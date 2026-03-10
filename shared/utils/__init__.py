"""
Shared utilities for OpenClaw Orchestration Stack.

This module provides:
- Lease management for distributed task processing
- Idempotency key handling for request deduplication
- Request deduplication with in-flight tracking
- Dead letter queue for failed tasks
"""

from .lease_manager import (
    LeaseManager,
    Lease,
    LeaseError,
    TaskAlreadyClaimedError,
    LeaseExpiredError,
    TaskNotFoundError,
    get_lease_manager,
    configure_lease_manager,
)

from .idempotency import (
    IdempotencyStore,
    IdempotencyContext,
    IdempotencyStatus,
    KeyMismatchError,
    IdempotencyError,
    get_idempotency_store,
    configure_idempotency_store,
    check_idempotency,
    store_response,
    get_cached_response,
    cleanup_expired_keys,
    generate_key,
)

from .deduplication import (
    DeduplicationManager,
    DeduplicationContext,
    DuplicateStatus,
    RequestMismatchError,
    DeduplicationError,
    get_deduplication_manager,
    configure_deduplication_manager,
    detect_duplicate,
    return_cached,
    track_in_flight,
)

from .dead_letter import (
    DeadLetterQueue,
    DLQEntry,
    DLQReason,
    DLQError,
    TaskNotInDLQError,
    get_dead_letter_queue,
    configure_dead_letter_queue,
    move_to_dlq,
    get_dlq_items,
    retry_from_dlq,
)

__all__ = [
    # Lease Manager
    "LeaseManager",
    "Lease",
    "LeaseError",
    "TaskAlreadyClaimedError",
    "LeaseExpiredError",
    "TaskNotFoundError",
    "get_lease_manager",
    "configure_lease_manager",
    
    # Idempotency
    "IdempotencyStore",
    "IdempotencyContext",
    "IdempotencyStatus",
    "KeyMismatchError",
    "IdempotencyError",
    "get_idempotency_store",
    "configure_idempotency_store",
    "check_idempotency",
    "store_response",
    "get_cached_response",
    "cleanup_expired_keys",
    "generate_key",
    
    # Deduplication
    "DeduplicationManager",
    "DeduplicationContext",
    "DuplicateStatus",
    "RequestMismatchError",
    "DeduplicationError",
    "get_deduplication_manager",
    "configure_deduplication_manager",
    "detect_duplicate",
    "return_cached",
    "track_in_flight",
    
    # Dead Letter Queue
    "DeadLetterQueue",
    "DLQEntry",
    "DLQReason",
    "DLQError",
    "TaskNotInDLQError",
    "get_dead_letter_queue",
    "configure_dead_letter_queue",
    "move_to_dlq",
    "get_dlq_items",
    "retry_from_dlq",
]
