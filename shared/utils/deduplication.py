"""
Duplicate Request Handling for OpenClaw Orchestration Stack

Provides comprehensive deduplication using correlation_id and idempotency_key.
Tracks in-flight requests to handle concurrent duplicate submissions.
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, List, Set, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from functools import wraps

from ..db import get_connection, transaction, execute

logger = logging.getLogger(__name__)


class DuplicateStatus(Enum):
    """Status of a request for deduplication purposes."""
    NEW = "new"                    # Never seen before
    IN_FLIGHT = "in_flight"        # Currently being processed
    COMPLETED = "completed"        # Completed, result cached
    DUPLICATE = "duplicate"        # Exact duplicate detected


@dataclass
class RequestFingerprint:
    """Fingerprint of a request for deduplication."""
    correlation_id: str
    idempotency_key: str
    request_hash: str
    timestamp: datetime
    status: DuplicateStatus
    response: Optional[Dict[str, Any]] = None
    worker_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "request_hash": self.request_hash,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "response": self.response,
            "worker_id": self.worker_id
        }


class DeduplicationError(Exception):
    """Base exception for deduplication operations."""
    pass


class RequestMismatchError(DeduplicationError):
    """Raised when request doesn't match the deduplication record."""
    pass


class DeduplicationManager:
    """
    Manages request deduplication using correlation_id and idempotency_key.
    
    Features:
    - Detect duplicates using correlation_id + idempotency_key
    - Track in-flight requests
    - Return cached results for duplicates
    - Handle concurrent request detection
    """
    
    def __init__(
        self,
        in_flight_ttl: int = 300,
        cache_ttl: int = 86400
    ):
        """
        Initialize deduplication manager.
        
        Args:
            in_flight_ttl: TTL for in-flight tracking (seconds)
            cache_ttl: TTL for completed response caching (seconds)
        """
        self.in_flight_ttl = in_flight_ttl
        self.cache_ttl = cache_ttl
        self._in_flight_lock = threading.RLock()
        self._in_flight: Dict[str, Dict[str, Any]] = {}
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure required tables exist."""
        with get_connection() as conn:
            # Main deduplication table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS request_dedup (
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('in_flight', 'completed', 'failed')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    response_data JSON,
                    worker_id TEXT,
                    PRIMARY KEY (correlation_id, idempotency_key)
                )
            """)
            
            # Indexes for efficient lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_expires 
                ON request_dedup(expires_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_key 
                ON request_dedup(idempotency_key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_dedup_status 
                ON request_dedup(status)
            """)
            
            # Duplicate detection log (for audit)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS duplicate_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    original_created_at TIMESTAMP,
                    handled_as TEXT NOT NULL  -- 'cached_response', 'rejected', 'queued'
                )
            """)
            
            conn.commit()
    
    def detect_duplicate(
        self,
        correlation_id: str,
        idempotency_key: str,
        request_data: Optional[Dict[str, Any]] = None
    ) -> tuple[DuplicateStatus, Optional[Dict[str, Any]]]:
        """
        Detect if a request is a duplicate.
        
        Args:
            correlation_id: The correlation ID
            idempotency_key: The idempotency key
            request_data: Optional request data for verification
        
        Returns:
            Tuple of (status, cached_response)
            - NEW: Not a duplicate, proceed with processing
            - IN_FLIGHT: Request is being processed
            - COMPLETED: Request completed, cached response returned
            - DUPLICATE: Exact duplicate with mismatched data
        """
        now = datetime.utcnow()
        
        # First check in-memory in-flight tracking
        with self._in_flight_lock:
            in_flight_key = f"{correlation_id}:{idempotency_key}"
            if in_flight_key in self._in_flight:
                entry = self._in_flight[in_flight_key]
                if entry["expires_at"] > now:
                    logger.info(f"In-flight request detected: {in_flight_key}")
                    return (DuplicateStatus.IN_FLIGHT, None)
                else:
                    # Expired in-flight entry, clean up
                    del self._in_flight[in_flight_key]
        
        with get_connection() as conn:
            # Clean up expired entries
            conn.execute(
                "DELETE FROM request_dedup WHERE expires_at < ?",
                (now.isoformat(),)
            )
            
            # Check for existing record
            cursor = conn.execute(
                """
                SELECT status, response_data, request_hash, created_at
                FROM request_dedup
                WHERE correlation_id = ? AND idempotency_key = ?
                """,
                (correlation_id, idempotency_key)
            )
            row = cursor.fetchone()
            
            if not row:
                return (DuplicateStatus.NEW, None)
            
            # Verify request hash if data provided
            if request_data and row["request_hash"]:
                current_hash = self._hash_request(request_data)
                if current_hash != row["request_hash"]:
                    logger.warning(
                        f"Request mismatch for {correlation_id}/{idempotency_key}"
                    )
                    # Log the mismatch but treat as new to avoid blocking
                    return (DuplicateStatus.DUPLICATE, None)
            
            status = DuplicateStatus(row["status"])
            response = json.loads(row["response_data"]) if row["response_data"] else None
            
            # Log duplicate detection
            conn.execute(
                """
                INSERT INTO duplicate_requests 
                (correlation_id, idempotency_key, original_created_at, handled_as)
                VALUES (?, ?, ?, ?)
                """,
                (correlation_id, idempotency_key, row["created_at"],
                 "cached_response" if status == DuplicateStatus.COMPLETED else "queued")
            )
            conn.commit()
            
            return (status, response)
    
    def track_in_flight(
        self,
        correlation_id: str,
        idempotency_key: str,
        worker_id: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track a request as in-flight.
        
        Args:
            correlation_id: The correlation ID
            idempotency_key: The idempotency key
            worker_id: ID of worker processing the request
            request_data: Request data for verification
        
        Returns:
            True if successfully tracked, False if already exists
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.in_flight_ttl)
        request_hash = self._hash_request(request_data) if request_data else ""
        
        # Add to in-memory tracking
        with self._in_flight_lock:
            in_flight_key = f"{correlation_id}:{idempotency_key}"
            self._in_flight[in_flight_key] = {
                "worker_id": worker_id,
                "started_at": now,
                "expires_at": expires_at,
                "request_hash": request_hash
            }
        
        try:
            with transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO request_dedup 
                    (correlation_id, idempotency_key, request_hash, status,
                     created_at, updated_at, expires_at, worker_id)
                    VALUES (?, ?, ?, 'in_flight', ?, ?, ?, ?)
                    """,
                    (correlation_id, idempotency_key, request_hash,
                     now.isoformat(), now.isoformat(), expires_at.isoformat(),
                     worker_id)
                )
            return True
        except Exception as e:
            # Already exists, clean up in-memory tracking
            with self._in_flight_lock:
                in_flight_key = f"{correlation_id}:{idempotency_key}"
                self._in_flight.pop(in_flight_key, None)
            logger.debug(f"Failed to track in-flight: {e}")
            return False
    
    def return_cached(
        self,
        correlation_id: str,
        idempotency_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Return cached result for a completed request.
        
        Args:
            correlation_id: The correlation ID
            idempotency_key: The idempotency key
        
        Returns:
            Cached response if available, None otherwise
        """
        status, response = self.detect_duplicate(correlation_id, idempotency_key)
        
        if status == DuplicateStatus.COMPLETED:
            logger.info(f"Returning cached response for {correlation_id}/{idempotency_key}")
            return response
        
        return None
    
    def complete_request(
        self,
        correlation_id: str,
        idempotency_key: str,
        response_data: Dict[str, Any],
        worker_id: Optional[str] = None
    ) -> bool:
        """
        Mark an in-flight request as completed and cache the response.
        
        Args:
            correlation_id: The correlation ID
            idempotency_key: The idempotency key
            response_data: Response data to cache
            worker_id: Worker that completed the request
        
        Returns:
            True if updated successfully
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=self.cache_ttl)
        
        # Remove from in-memory tracking
        with self._in_flight_lock:
            in_flight_key = f"{correlation_id}:{idempotency_key}"
            self._in_flight.pop(in_flight_key, None)
        
        with transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE request_dedup
                SET status = 'completed',
                    response_data = ?,
                    updated_at = ?,
                    expires_at = ?,
                    worker_id = ?
                WHERE correlation_id = ? AND idempotency_key = ?
                """,
                (json.dumps(response_data), now.isoformat(),
                 expires_at.isoformat(), worker_id,
                 correlation_id, idempotency_key)
            )
            
            if cursor.rowcount == 0:
                logger.warning(
                    f"No in-flight record found for {correlation_id}/{idempotency_key}"
                )
                return False
            
            return True
    
    def fail_request(
        self,
        correlation_id: str,
        idempotency_key: str,
        error_data: Optional[Dict[str, Any]] = None,
        allow_retry: bool = True
    ) -> bool:
        """
        Mark an in-flight request as failed.
        
        Args:
            correlation_id: The correlation ID
            idempotency_key: The idempotency key
            error_data: Optional error information
            allow_retry: If True, remove the record to allow retry
        
        Returns:
            True if updated successfully
        """
        # Remove from in-memory tracking
        with self._in_flight_lock:
            in_flight_key = f"{correlation_id}:{idempotency_key}"
            self._in_flight.pop(in_flight_key, None)
        
        if allow_retry:
            # Delete the record to allow retry
            with transaction() as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM request_dedup
                    WHERE correlation_id = ? AND idempotency_key = ?
                    """,
                    (correlation_id, idempotency_key)
                )
                return cursor.rowcount > 0
        else:
            # Mark as failed but keep record
            now = datetime.utcnow()
            with transaction() as conn:
                cursor = conn.execute(
                    """
                    UPDATE request_dedup
                    SET status = 'failed',
                        updated_at = ?,
                        response_data = ?
                    WHERE correlation_id = ? AND idempotency_key = ?
                    """,
                    (now.isoformat(),
                     json.dumps({"error": error_data}) if error_data else None,
                     correlation_id, idempotency_key)
                )
                return cursor.rowcount > 0
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired deduplication records.
        
        Returns:
            Number of records cleaned
        """
        now = datetime.utcnow().isoformat()
        
        with transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM request_dedup WHERE expires_at < ?",
                (now,)
            )
            deleted = cursor.rowcount
        
        # Also clean in-memory tracking
        with self._in_flight_lock:
            expired_keys = [
                k for k, v in self._in_flight.items()
                if v["expires_at"] < datetime.utcnow()
            ]
            for key in expired_keys:
                del self._in_flight[key]
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired deduplication records")
        
        return deleted
    
    def get_in_flight_requests(
        self,
        worker_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all in-flight requests.
        
        Args:
            worker_id: Optional filter by worker
        
        Returns:
            List of in-flight request details
        """
        now = datetime.utcnow().isoformat()
        
        if worker_id:
            return execute(
                """
                SELECT correlation_id, idempotency_key, worker_id,
                       created_at, expires_at
                FROM request_dedup
                WHERE status = 'in_flight'
                  AND worker_id = ?
                  AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (worker_id, now)
            )
        else:
            return execute(
                """
                SELECT correlation_id, idempotency_key, worker_id,
                       created_at, expires_at
                FROM request_dedup
                WHERE status = 'in_flight'
                  AND expires_at > ?
                ORDER BY created_at DESC
                """,
                (now,)
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get deduplication statistics.
        
        Returns:
            Dictionary with statistics
        """
        now = datetime.utcnow().isoformat()
        
        with get_connection() as conn:
            # Status counts
            cursor = conn.execute(
                """
                SELECT status, COUNT(*) as count
                FROM request_dedup
                GROUP BY status
                """
            )
            status_counts = {row["status"]: row["count"] for row in cursor.fetchall()}
            
            # In-flight count
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM request_dedup
                WHERE status = 'in_flight' AND expires_at > ?
                """,
                (now,)
            )
            in_flight_count = cursor.fetchone()["count"]
            
            # Total duplicates detected
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM duplicate_requests"
            )
            duplicate_count = cursor.fetchone()["count"]
            
            # Recent duplicates (last hour)
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count 
                FROM duplicate_requests
                WHERE detected_at > datetime('now', '-1 hour')
                """
            )
            recent_duplicates = cursor.fetchone()["count"]
        
        return {
            "by_status": status_counts,
            "in_flight": in_flight_count,
            "total_duplicates_detected": duplicate_count,
            "recent_duplicates": recent_duplicates,
            "in_memory_in_flight": len(self._in_flight)
        }
    
    def _hash_request(self, request_data: Dict[str, Any]) -> str:
        """Create a hash of request data."""
        import hashlib
        normalized = json.dumps(request_data, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(normalized.encode()).hexdigest()


class DeduplicationContext:
    """
    Context manager for deduplication.
    
    Usage:
        with DeduplicationContext(manager, corr_id, key, request) as ctx:
            if ctx.should_execute:
                result = process(request)
                ctx.complete(result)
            else:
                return ctx.cached_response
    """
    
    def __init__(
        self,
        manager: DeduplicationManager,
        correlation_id: str,
        idempotency_key: str,
        request_data: Optional[Dict[str, Any]] = None,
        worker_id: Optional[str] = None
    ):
        self.manager = manager
        self.correlation_id = correlation_id
        self.idempotency_key = idempotency_key
        self.request_data = request_data
        self.worker_id = worker_id
        self.status = DuplicateStatus.NEW
        self.cached_response: Optional[Dict[str, Any]] = None
        self.should_execute = False
        self._completed = False
    
    def __enter__(self):
        """Enter context and check for duplicates."""
        self.status, self.cached_response = self.manager.detect_duplicate(
            self.correlation_id, self.idempotency_key, self.request_data
        )
        
        if self.status == DuplicateStatus.NEW:
            # Try to track as in-flight
            if self.manager.track_in_flight(
                self.correlation_id, self.idempotency_key,
                self.worker_id, self.request_data
            ):
                self.should_execute = True
            else:
                # Race condition, check again
                self.status, self.cached_response = self.manager.detect_duplicate(
                    self.correlation_id, self.idempotency_key, self.request_data
                )
                self.should_execute = False
        else:
            self.should_execute = False
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context, handling failures."""
        if exc_type and not self._completed:
            self.manager.fail_request(
                self.correlation_id, self.idempotency_key,
                {"error": str(exc_val)}, allow_retry=True
            )
        return False
    
    def complete(self, response_data: Dict[str, Any]):
        """Mark request as completed."""
        self.manager.complete_request(
            self.correlation_id, self.idempotency_key,
            response_data, self.worker_id
        )
        self._completed = True


# Global instance
_dedup_manager: Optional[DeduplicationManager] = None


def get_deduplication_manager(
    in_flight_ttl: int = 300,
    cache_ttl: int = 86400
) -> DeduplicationManager:
    """Get or create global deduplication manager."""
    global _dedup_manager
    if _dedup_manager is None:
        _dedup_manager = DeduplicationManager(in_flight_ttl, cache_ttl)
    return _dedup_manager


def configure_deduplication_manager(manager: DeduplicationManager):
    """Configure the global deduplication manager."""
    global _dedup_manager
    _dedup_manager = manager


# Convenience functions

def detect_duplicate(
    correlation_id: str,
    idempotency_key: str,
    request_data: Optional[Dict[str, Any]] = None
) -> tuple[DuplicateStatus, Optional[Dict[str, Any]]]:
    """Detect duplicate using global manager."""
    manager = get_deduplication_manager()
    return manager.detect_duplicate(correlation_id, idempotency_key, request_data)


def return_cached(correlation_id: str, idempotency_key: str) -> Optional[Dict[str, Any]]:
    """Return cached response using global manager."""
    manager = get_deduplication_manager()
    return manager.return_cached(correlation_id, idempotency_key)


def track_in_flight(
    correlation_id: str,
    idempotency_key: str,
    worker_id: Optional[str] = None,
    request_data: Optional[Dict[str, Any]] = None
) -> bool:
    """Track in-flight request using global manager."""
    manager = get_deduplication_manager()
    return manager.track_in_flight(correlation_id, idempotency_key, worker_id, request_data)
