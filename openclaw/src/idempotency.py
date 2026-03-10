"""
Idempotency Checking Module

Prevents duplicate processing of requests using idempotency keys.
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Set
from dataclasses import dataclass, asdict
import threading


@dataclass
class IdempotencyRecord:
    """Record of a processed idempotency key."""
    key: str
    correlation_id: str
    plan_id: str
    created_at: datetime
    response_data: Dict[str, Any]
    ttl_seconds: int = 86400  # 24 hours default
    
    def is_expired(self) -> bool:
        """Check if the record has expired."""
        expiry = self.created_at + timedelta(seconds=self.ttl_seconds)
        return datetime.utcnow() > expiry


class IdempotencyStore:
    """Abstract base class for idempotency stores."""
    
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get a record by key."""
        raise NotImplementedError
    
    def set(self, record: IdempotencyRecord) -> bool:
        """Store a record."""
        raise NotImplementedError
    
    def delete(self, key: str) -> bool:
        """Delete a record."""
        raise NotImplementedError
    
    def cleanup_expired(self) -> int:
        """Clean up expired records. Returns count deleted."""
        raise NotImplementedError
    
    def clear(self) -> bool:
        """Clear all records."""
        raise NotImplementedError


class MemoryIdempotencyStore(IdempotencyStore):
    """In-memory idempotency store (for development/testing)."""
    
    def __init__(self):
        self._store: Dict[str, IdempotencyRecord] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get a record by key."""
        with self._lock:
            record = self._store.get(key)
            if record and record.is_expired():
                del self._store[key]
                return None
            return record
    
    def set(self, record: IdempotencyRecord) -> bool:
        """Store a record."""
        with self._lock:
            self._store[record.key] = record
            return True
    
    def delete(self, key: str) -> bool:
        """Delete a record."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    def cleanup_expired(self) -> int:
        """Clean up expired records."""
        with self._lock:
            expired_keys = [
                key for key, record in self._store.items() 
                if record.is_expired()
            ]
            for key in expired_keys:
                del self._store[key]
            return len(expired_keys)
    
    def clear(self) -> bool:
        """Clear all records."""
        with self._lock:
            self._store.clear()
            return True


class SQLiteIdempotencyStore(IdempotencyStore):
    """SQLite-based idempotency store."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.environ.get("OPENCLAW_DB_PATH", "data/openclaw.db")
        self._ensure_table()
    
    def _ensure_table(self):
        """Ensure the idempotency table exists."""
        from shared.db import execute
        
        execute("""
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                key TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                response_data JSON,
                ttl_seconds INTEGER DEFAULT 86400
            )
        """)
        
        # Create index for cleanup
        execute("""
            CREATE INDEX IF NOT EXISTS idx_idempotency_created_at 
            ON idempotency_keys(created_at)
        """)
    
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get a record by key."""
        from shared.db import execute
        
        result = execute(
            "SELECT * FROM idempotency_keys WHERE key = ?",
            (key,),
            fetch_one=True
        )
        
        if not result:
            return None
        
        record = IdempotencyRecord(
            key=result["key"],
            correlation_id=result["correlation_id"],
            plan_id=result["plan_id"],
            created_at=datetime.fromisoformat(result["created_at"]),
            response_data=json.loads(result["response_data"]) if result["response_data"] else {},
            ttl_seconds=result["ttl_seconds"]
        )
        
        if record.is_expired():
            self.delete(key)
            return None
        
        return record
    
    def set(self, record: IdempotencyRecord) -> bool:
        """Store a record."""
        from shared.db import insert
        
        try:
            insert("idempotency_keys", {
                "key": record.key,
                "correlation_id": record.correlation_id,
                "plan_id": record.plan_id,
                "created_at": record.created_at.isoformat(),
                "response_data": json.dumps(record.response_data),
                "ttl_seconds": record.ttl_seconds
            })
            return True
        except Exception as e:
            print(f"Failed to store idempotency record: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete a record."""
        from shared.db import delete
        
        rows = delete("idempotency_keys", "key = ?", (key,))
        return rows > 0
    
    def cleanup_expired(self) -> int:
        """Clean up expired records."""
        from shared.db import delete
        
        # Delete records where created_at + ttl_seconds < now
        return delete(
            "idempotency_keys",
            "datetime(created_at, '+' || ttl_seconds || ' seconds') < datetime('now')",
            ()
        )
    
    def clear(self) -> bool:
        """Clear all records."""
        from shared.db import execute
        
        try:
            execute("DELETE FROM idempotency_keys")
            return True
        except Exception:
            return False


class RedisIdempotencyStore(IdempotencyStore):
    """Redis-based idempotency store (for production)."""
    
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost")
        self._redis = None
    
    def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            try:
                import redis as redis_lib
                self._redis = redis_lib.from_url(self.redis_url, decode_responses=True)
            except ImportError:
                raise ImportError("redis package required for RedisIdempotencyStore")
        return self._redis
    
    def get(self, key: str) -> Optional[IdempotencyRecord]:
        """Get a record by key."""
        r = self._get_redis()
        
        data = r.get(f"idempotency:{key}")
        if not data:
            return None
        
        record_data = json.loads(data)
        return IdempotencyRecord(**record_data)
    
    def set(self, record: IdempotencyRecord) -> bool:
        """Store a record."""
        r = self._get_redis()
        
        key = f"idempotency:{record.key}"
        data = json.dumps({
            "key": record.key,
            "correlation_id": record.correlation_id,
            "plan_id": record.plan_id,
            "created_at": record.created_at.isoformat(),
            "response_data": record.response_data,
            "ttl_seconds": record.ttl_seconds
        })
        
        r.setex(key, record.ttl_seconds, data)
        return True
    
    def delete(self, key: str) -> bool:
        """Delete a record."""
        r = self._get_redis()
        return r.delete(f"idempotency:{key}") > 0
    
    def cleanup_expired(self) -> int:
        """Redis handles expiration automatically."""
        return 0
    
    def clear(self) -> bool:
        """Clear all idempotency keys."""
        r = self._get_redis()
        pattern = "idempotency:*"
        
        # Use scan to find and delete keys
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match=pattern)
            if keys:
                r.delete(*keys)
            if cursor == 0:
                break
        
        return True


class IdempotencyChecker:
    """Main idempotency checking class."""
    
    def __init__(self, store: Optional[IdempotencyStore] = None):
        self.store = store or self._create_default_store()
        self._key_prefix = os.environ.get("IDEMPOTENCY_KEY_PREFIX", "openclaw")
    
    def _create_default_store(self) -> IdempotencyStore:
        """Create default store based on environment."""
        backend = os.environ.get("IDEMPOTENCY_BACKEND", "sqlite")
        
        if backend == "redis":
            return RedisIdempotencyStore()
        elif backend == "memory":
            return MemoryIdempotencyStore()
        else:
            return SQLiteIdempotencyStore()
    
    def _generate_key(self, key: str) -> str:
        """Generate a normalized key."""
        # Normalize the key
        normalized = f"{self._key_prefix}:{key}"
        
        # Hash if too long
        if len(normalized) > 255:
            return hashlib.sha256(normalized.encode()).hexdigest()
        
        return normalized
    
    def check(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Check if a key has been processed.
        
        Args:
            key: The idempotency key
        
        Returns:
            Previous response data if found and not expired, None otherwise
        """
        normalized_key = self._generate_key(key)
        record = self.store.get(normalized_key)
        
        if record:
            return record.response_data
        
        return None
    
    def store(
        self,
        key: str,
        correlation_id: str,
        plan_id: str,
        response_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> bool:
        """
        Store an idempotency record.
        
        Args:
            key: The idempotency key
            correlation_id: The correlation ID
            plan_id: The action plan ID
            response_data: Response data to cache
            ttl_seconds: TTL in seconds (uses default if not specified)
        
        Returns:
            True if stored successfully
        """
        normalized_key = self._generate_key(key)
        
        record = IdempotencyRecord(
            key=normalized_key,
            correlation_id=correlation_id,
            plan_id=plan_id,
            created_at=datetime.utcnow(),
            response_data=response_data,
            ttl_seconds=ttl_seconds or int(os.environ.get("IDEMPOTENCY_TTL", "86400"))
        )
        
        return self.store.set(record)
    
    def cleanup(self) -> int:
        """Clean up expired records."""
        return self.store.cleanup_expired()
    
    def clear(self) -> bool:
        """Clear all records."""
        return self.store.clear()


# Global checker instance
_checker: Optional[IdempotencyChecker] = None
_checker_lock = threading.Lock()


def get_checker() -> IdempotencyChecker:
    """Get or create the global idempotency checker."""
    global _checker
    
    with _checker_lock:
        if _checker is None:
            _checker = IdempotencyChecker()
    
    return _checker


def configure_checker(store: IdempotencyStore):
    """Configure the global checker with a specific store."""
    global _checker
    
    with _checker_lock:
        _checker = IdempotencyChecker(store)
    
    return _checker


def init_idempotency_store():
    """Initialize the idempotency store (creates tables if needed)."""
    checker = get_checker()
    # The store is initialized automatically on first use
    return checker


# Convenience functions

def check_idempotency(key: str) -> Optional[Dict[str, Any]]:
    """
    Check if a request has already been processed.
    
    Args:
        key: The idempotency key (typically from header)
    
    Returns:
        Cached response if found, None otherwise
    
    Example:
        >>> cached = check_idempotency("key-123")
        >>> if cached:
        >>>     return cached  # Return cached response
        >>> # Process new request
    """
    if not key:
        return None
    
    checker = get_checker()
    return checker.check(key)


def store_idempotency_key(
    key: str,
    response_data: Dict[str, Any],
    correlation_id: str,
    plan_id: str
) -> bool:
    """
    Store an idempotency key with its response.
    
    Args:
        key: The idempotency key
        response_data: The response to cache
        correlation_id: The correlation ID
        plan_id: The action plan ID
    
    Returns:
        True if stored successfully
    
    Example:
        >>> response = process_request(request)
        >>> store_idempotency_key("key-123", response.dict(), "corr-123", "plan-456")
    """
    if not key:
        return False
    
    checker = get_checker()
    return checker.store(key, correlation_id, plan_id, response_data)


def generate_idempotency_key(*components: str) -> str:
    """
    Generate a deterministic idempotency key from components.
    
    Args:
        *components: String components to hash
    
    Returns:
        A deterministic idempotency key
    
    Example:
        >>> key = generate_idempotency_key(
        ...     request.body,
        ...     request.headers.get("X-Request-Type", ""),
        ...     str(request.timestamp)
        ... )
    """
    combined = "|".join(components)
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def cleanup_expired_keys() -> int:
    """Clean up all expired idempotency keys."""
    checker = get_checker()
    return checker.cleanup()


def clear_all_keys() -> bool:
    """Clear all idempotency keys (use with caution)."""
    checker = get_checker()
    return checker.clear()


# Decorator for idempotent operations

def idempotent(
    key_func: Optional[callable] = None,
    ttl_seconds: Optional[int] = None
):
    """
    Decorator to make a function idempotent.
    
    Args:
        key_func: Function to extract idempotency key from arguments
        ttl_seconds: TTL for cached results
    
    Example:
        @idempotent(key_func=lambda req: req.headers.get("Idempotency-Key"))
        async def process_request(request):
            # This will only execute once per idempotency key
            return await do_processing(request)
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default: use first argument
                key = str(args[0]) if args else None
            
            if not key:
                # No key provided, execute normally
                return await func(*args, **kwargs)
            
            checker = get_checker()
            
            # Check for existing result
            cached = checker.check(key)
            if cached:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store result
            correlation_id = getattr(result, 'correlation_id', 'unknown')
            plan_id = getattr(result, 'plan_id', 'unknown')
            
            checker.store(
                key,
                correlation_id,
                plan_id,
                result if isinstance(result, dict) else result.dict(),
                ttl_seconds
            )
            
            return result
        
        return wrapper
    return decorator
