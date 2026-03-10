"""
Idempotency Key System for OpenClaw Orchestration Stack

Provides request deduplication using idempotency keys with TTL-based expiration.
All operations use SQLite atomic operations for thread safety.
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, asdict
from enum import Enum

from ..db import get_connection, transaction, execute

logger = logging.getLogger(__name__)


class IdempotencyStatus(Enum):
    """Status of an idempotency key."""
    NEW = "new"                    # Key doesn't exist
    IN_PROGRESS = "in_progress"    # Request is being processed
    COMPLETED = "completed"        # Request completed, response cached
    EXPIRED = "expired"            # Key has expired


@dataclass
class IdempotencyRecord:
    """Record of an idempotency key."""
    key: str
    correlation_id: str
    status: IdempotencyStatus
    created_at: datetime
    expires_at: datetime
    response_data: Optional[Dict[str, Any]] = None
    request_hash: Optional[str] = None  # Hash of request for verification
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert record to dictionary."""
        return {
            "key": self.key,
            "correlation_id": self.correlation_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "response_data": self.response_data,
            "request_hash": self.request_hash
        }
    
    def is_expired(self) -> bool:
        """Check if the record has expired."""
        return datetime.utcnow() > self.expires_at


class IdempotencyError(Exception):
    """Base exception for idempotency operations."""
    pass


class KeyMismatchError(IdempotencyError):
    """Raised when request doesn't match cached idempotency key."""
    pass


class IdempotencyStore:
    """
    SQLite-based idempotency key store.
    
    Provides atomic operations for:
    - Checking idempotency key status
    - Storing responses for completed requests
    - TTL-based expiration cleanup
    """
    
    def __init__(self, default_ttl: int = 86400):
        """
        Initialize idempotency store.
        
        Args:
            default_ttl: Default TTL in seconds (default: 24 hours)
        """
        self.default_ttl = default_ttl
        self._ensure_table()
    
    def _ensure_table(self):
        """Ensure the idempotency table exists."""
        with get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS idempotency_store (
                    key TEXT PRIMARY KEY,
                    correlation_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('new', 'in_progress', 'completed', 'expired')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    response_data JSON,
                    request_hash TEXT
                )
            """)
            
            # Create indexes for efficient queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_idempotency_expires 
                ON idempotency_store(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_idempotency_correlation 
                ON idempotency_store(correlation_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_idempotency_status 
                ON idempotency_store(status)
            """)
            conn.commit()
    
    def check_idempotency(
        self,
        key: str,
        request_data: Optional[Dict[str, Any]] = None
    ) -> tuple[IdempotencyStatus, Optional[Dict[str, Any]]]:
        """
        Check if an idempotency key exists and get its status.
        
        Args:
            key: The idempotency key
            request_data: Optional request data for verification
        
        Returns:
            Tuple of (status, cached_response)
            - If NEW: status=NEW, response=None
            - If IN_PROGRESS: status=IN_PROGRESS, response=None
            - If COMPLETED: status=COMPLETED, response=cached_data
            - If EXPIRED: status=EXPIRED, response=None
        """
        now = datetime.utcnow().isoformat()
        
        with get_connection() as conn:
            # First, clean up expired records
            conn.execute(
                "DELETE FROM idempotency_store WHERE expires_at < ?",
                (now,)
            )
            
            # Check for existing key
            cursor = conn.execute(
                """
                SELECT key, correlation_id, status, created_at, expires_at,
                       response_data, request_hash
                FROM idempotency_store
                WHERE key = ?
                """,
                (key,)
            )
            row = cursor.fetchone()
            
            if not row:
                return (IdempotencyStatus.NEW, None)
            
            # Check request hash if provided
            if request_data and row["request_hash"]:
                current_hash = self._hash_request(request_data)
                if current_hash != row["request_hash"]:
                    logger.warning(f"Idempotency key {key} request mismatch")
                    raise KeyMismatchError(
                        f"Request data doesn't match cached request for key {key}"
                    )
            
            status = IdempotencyStatus(row["status"])
            response = json.loads(row["response_data"]) if row["response_data"] else None
            
            return (status, response)
    
    def start_processing(
        self,
        key: str,
        correlation_id: str,
        request_data: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Mark an idempotency key as being processed.
        
        Should be called when starting request processing.
        
        Args:
            key: The idempotency key
            correlation_id: Correlation ID for tracking
            request_data: Request data for verification
            ttl_seconds: TTL for the in-progress record
        
        Returns:
            True if successfully marked, False if key already exists
        """
        ttl = ttl_seconds or self.default_ttl
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl)
        request_hash = self._hash_request(request_data) if request_data else None
        
        try:
            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO idempotency_store 
                    (key, correlation_id, status, created_at, expires_at, request_hash)
                    VALUES (?, ?, 'in_progress', ?, ?, ?)
                    """,
                    (key, correlation_id, now.isoformat(), 
                     expires_at.isoformat(), request_hash)
                )
            return True
        except Exception as e:
            # Key already exists (UNIQUE constraint violation)
            logger.debug(f"Failed to start processing for key {key}: {e}")
            return False
    
    def store_response(
        self,
        key: str,
        response_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Store the response for a completed request.
        
        Args:
            key: The idempotency key
            response_data: Response data to cache
            ttl_seconds: Optional new TTL (uses default if not specified)
        
        Returns:
            True if stored successfully
        """
        ttl = ttl_seconds or self.default_ttl
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        with transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE idempotency_store
                SET status = 'completed',
                    response_data = ?,
                    expires_at = ?
                WHERE key = ?
                """,
                (json.dumps(response_data), expires_at.isoformat(), key)
            )
            
            if cursor.rowcount == 0:
                logger.warning(f"No idempotency record found for key {key}")
                return False
            
            return True
    
    def get_cached_response(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached response for an idempotency key.
        
        Args:
            key: The idempotency key
        
        Returns:
            Cached response if key exists and is completed, None otherwise
        """
        status, response = self.check_idempotency(key)
        
        if status == IdempotencyStatus.COMPLETED:
            return response
        return None
    
    def complete(
        self,
        key: str,
        response_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Complete an idempotency request and cache the response.
        
        Convenience method that calls store_response.
        
        Args:
            key: The idempotency key
            response_data: Response data to cache
            ttl_seconds: Optional TTL extension
        
        Returns:
            True if completed successfully
        """
        return self.store_response(key, response_data, ttl_seconds)
    
    def fail(
        self,
        key: str,
        error_data: Dict[str, Any],
        keep_for_retry: bool = True
    ) -> bool:
        """
        Mark an idempotency request as failed.
        
        Args:
            key: The idempotency key
            error_data: Error information
            keep_for_retry: If False, delete the key to allow retry
        
        Returns:
            True if updated successfully
        """
        if not keep_for_retry:
            return self.delete(key)
        
        with transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE idempotency_store
                SET status = 'expired',
                    response_data = ?
                WHERE key = ?
                """,
                (json.dumps({"error": error_data}), key)
            )
            return cursor.rowcount > 0
    
    def delete(self, key: str) -> bool:
        """
        Delete an idempotency key.
        
        Args:
            key: The idempotency key to delete
        
        Returns:
            True if deleted, False if not found
        """
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM idempotency_store WHERE key = ?",
                (key,)
            )
            return cursor.rowcount > 0
    
    def cleanup_expired(self) -> int:
        """
        Clean up all expired idempotency keys.
        
        Returns:
            Number of keys deleted
        """
        now = datetime.utcnow().isoformat()
        
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM idempotency_store WHERE expires_at < ?",
                (now,)
            )
            deleted = cursor.rowcount
            
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired idempotency keys")
        
        return deleted
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about idempotency keys.
        
        Returns:
            Dictionary with statistics
        """
        now = datetime.utcnow().isoformat()
        
        with get_connection() as conn:
            # Total count by status
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM idempotency_store
                GROUP BY status
                """
            )
            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            # Expired count
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM idempotency_store
                WHERE expires_at < ?
                """,
                (now,)
            )
            expired_count = cursor.fetchone()["count"]
            
            # Total count
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM idempotency_store"
            )
            total_count = cursor.fetchone()["count"]
        
        return {
            "total": total_count,
            "by_status": status_counts,
            "expired": expired_count,
            "active": total_count - expired_count
        }
    
    def _hash_request(self, request_data: Dict[str, Any]) -> str:
        """
        Create a hash of request data for verification.
        
        Args:
            request_data: Request data to hash
        
        Returns:
            SHA256 hash of the request
        """
        # Normalize the request data
        normalized = json.dumps(request_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(normalized.encode()).hexdigest()


class IdempotencyContext:
    """
    Context manager for idempotency operations.
    
    Usage:
        with IdempotencyContext(store, key, correlation_id, request) as ctx:
            if ctx.should_execute:
                result = process_request(request)
                ctx.complete(result)
            else:
                return ctx.cached_response
    """
    
    def __init__(
        self,
        store: IdempotencyStore,
        key: str,
        correlation_id: str,
        request_data: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None
    ):
        self.store = store
        self.key = key
        self.correlation_id = correlation_id
        self.request_data = request_data
        self.ttl_seconds = ttl_seconds
        self.status = IdempotencyStatus.NEW
        self.cached_response: Optional[Dict[str, Any]] = None
        self.should_execute = False
        self._completed = False
    
    def __enter__(self):
        """Enter the context and check idempotency."""
        self.status, self.cached_response = self.store.check_idempotency(
            self.key, self.request_data
        )
        
        if self.status == IdempotencyStatus.NEW:
            # Try to mark as in-progress
            if self.store.start_processing(
                self.key, self.correlation_id, 
                self.request_data, self.ttl_seconds
            ):
                self.should_execute = True
            else:
                # Another process just claimed it, check again
                self.status, self.cached_response = self.store.check_idempotency(
                    self.key, self.request_data
                )
                self.should_execute = False
        elif self.status == IdempotencyStatus.IN_PROGRESS:
            self.should_execute = False
        elif self.status == IdempotencyStatus.COMPLETED:
            self.should_execute = False
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context, handling failures if needed."""
        if exc_type and not self._completed:
            # An exception occurred, mark as failed
            self.store.fail(self.key, {"error": str(exc_val)}, keep_for_retry=True)
        return False  # Don't suppress exceptions
    
    def complete(self, response_data: Dict[str, Any]):
        """Mark the request as completed with the response."""
        self.store.complete(self.key, response_data, self.ttl_seconds)
        self._completed = True


# Global instance
_idempotency_store: Optional[IdempotencyStore] = None


def get_idempotency_store(default_ttl: int = 86400) -> IdempotencyStore:
    """Get or create global idempotency store."""
    global _idempotency_store
    if _idempotency_store is None:
        _idempotency_store = IdempotencyStore(default_ttl)
    return _idempotency_store


def configure_idempotency_store(store: IdempotencyStore):
    """Configure the global idempotency store."""
    global _idempotency_store
    _idempotency_store = store


# Convenience functions

def check_idempotency(
    key: str,
    request_data: Optional[Dict[str, Any]] = None
) -> tuple[IdempotencyStatus, Optional[Dict[str, Any]]]:
    """Check idempotency status using global store."""
    store = get_idempotency_store()
    return store.check_idempotency(key, request_data)


def store_response(
    key: str,
    response_data: Dict[str, Any],
    ttl_seconds: Optional[int] = None
) -> bool:
    """Store response using global store."""
    store = get_idempotency_store()
    return store.store_response(key, response_data, ttl_seconds)


def get_cached_response(key: str) -> Optional[Dict[str, Any]]:
    """Get cached response using global store."""
    store = get_idempotency_store()
    return store.get_cached_response(key)


def cleanup_expired_keys() -> int:
    """Clean up expired keys using global store."""
    store = get_idempotency_store()
    return store.cleanup_expired()


def generate_key(*components: str) -> str:
    """
    Generate a deterministic idempotency key from components.
    
    Args:
        *components: String components to include in key
    
    Returns:
        Deterministic idempotency key
    """
    combined = "|".join(str(c) for c in components)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]
