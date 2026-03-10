"""
Unit tests for idempotency.py

Tests idempotency key system including:
- Checking idempotency status
- Storing and retrieving responses
- TTL expiration cleanup
- Request hash verification
"""

import pytest
import uuid
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from shared.utils.idempotency import (
    IdempotencyStore, IdempotencyContext,
    IdempotencyStatus, KeyMismatchError,
    get_idempotency_store, configure_idempotency_store,
    check_idempotency, store_response, get_cached_response,
    cleanup_expired_keys, generate_key
)


class TestIdempotencyStatus:
    """Test IdempotencyStatus enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert IdempotencyStatus.NEW.value == "new"
        assert IdempotencyStatus.IN_PROGRESS.value == "in_progress"
        assert IdempotencyStatus.COMPLETED.value == "completed"
        assert IdempotencyStatus.EXPIRED.value == "expired"


class TestIdempotencyStore:
    """Test IdempotencyStore class."""
    
    def test_init(self, mock_db_connection, cleanup_utils):
        """Test store initialization."""
        store = IdempotencyStore(default_ttl=3600)
        assert store.default_ttl == 3600
    
    def test_check_idempotency_new_key(self, mock_db_connection, cleanup_utils):
        """Test checking a new (non-existent) key."""
        store = IdempotencyStore(default_ttl=3600)
        
        status, response = store.check_idempotency("new-key-123")
        
        assert status == IdempotencyStatus.NEW
        assert response is None
    
    def test_check_idempotency_completed(self, mock_db_connection, cleanup_utils):
        """Test checking a completed key."""
        store = IdempotencyStore(default_ttl=3600)
        
        # Start and complete a request
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id, ttl_seconds=3600)
        store.complete("key-123", {"result": "success"})
        
        # Check the key
        status, response = store.check_idempotency("key-123")
        
        assert status == IdempotencyStatus.COMPLETED
        assert response == {"result": "success"}
    
    def test_check_idempotency_expired(self, mock_db_connection, cleanup_utils):
        """Test checking an expired key."""
        store = IdempotencyStore(default_ttl=1)
        
        # Start a request with short TTL
        correlation_id = str(uuid.uuid4())
        store.start_processing("expired-key", correlation_id, ttl_seconds=1)
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Check the key - should be cleaned up and treated as NEW
        status, response = store.check_idempotency("expired-key")
        
        assert status == IdempotencyStatus.NEW
        assert response is None
    
    def test_start_processing_success(self, mock_db_connection, cleanup_utils):
        """Test starting processing for a new key."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        result = store.start_processing("key-123", correlation_id)
        
        assert result is True
        
        # Verify in DB
        status, _ = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.IN_PROGRESS
    
    def test_start_processing_duplicate(self, mock_db_connection, cleanup_utils):
        """Test starting processing for an existing key."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        # Try to start again
        result = store.start_processing("key-123", correlation_id)
        assert result is False
    
    def test_store_response(self, mock_db_connection, cleanup_utils):
        """Test storing a response."""
        store = IdempotencyStore(default_ttl=3600)
        
        # Start processing
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        # Store response
        result = store.store_response("key-123", {"result": "success"})
        assert result is True
        
        # Verify
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.COMPLETED
        assert response == {"result": "success"}
    
    def test_store_response_not_found(self, mock_db_connection, cleanup_utils):
        """Test storing response for non-existent key."""
        store = IdempotencyStore(default_ttl=3600)
        
        result = store.store_response("non-existent", {"result": "success"})
        assert result is False
    
    def test_get_cached_response(self, mock_db_connection, cleanup_utils):
        """Test getting cached response."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        store.complete("key-123", {"result": "success"})
        
        cached = store.get_cached_response("key-123")
        assert cached == {"result": "success"}
    
    def test_get_cached_response_not_completed(self, mock_db_connection, cleanup_utils):
        """Test getting cached response for non-completed key."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        cached = store.get_cached_response("key-123")
        assert cached is None
    
    def test_complete(self, mock_db_connection, cleanup_utils):
        """Test completing a request."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        result = store.complete("key-123", {"result": "success"})
        assert result is True
        
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.COMPLETED
    
    def test_fail_keep_for_retry(self, mock_db_connection, cleanup_utils):
        """Test failing a request and keeping for retry."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        result = store.fail("key-123", {"error": "failed"}, keep_for_retry=True)
        assert result is True
        
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.EXPIRED
    
    def test_fail_allow_retry(self, mock_db_connection, cleanup_utils):
        """Test failing a request and allowing retry."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        result = store.fail("key-123", {"error": "failed"}, keep_for_retry=False)
        assert result is True
        
        # Key should be deleted
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.NEW
    
    def test_delete(self, mock_db_connection, cleanup_utils):
        """Test deleting a key."""
        store = IdempotencyStore(default_ttl=3600)
        
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id)
        
        result = store.delete("key-123")
        assert result is True
        
        # Verify deleted
        status, _ = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.NEW
    
    def test_cleanup_expired(self, mock_db_connection, cleanup_utils):
        """Test cleaning up expired keys."""
        store = IdempotencyStore(default_ttl=1)
        
        # Create expired keys
        for i in range(3):
            correlation_id = str(uuid.uuid4())
            store.start_processing(f"expired-key-{i}", correlation_id, ttl_seconds=1)
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Create non-expired key
        correlation_id = str(uuid.uuid4())
        store.start_processing("active-key", correlation_id, ttl_seconds=3600)
        
        # Cleanup
        deleted = store.cleanup_expired()
        
        assert deleted == 3
    
    def test_get_stats(self, mock_db_connection, cleanup_utils):
        """Test getting statistics."""
        store = IdempotencyStore(default_ttl=3600)
        
        # Create some keys
        for i in range(3):
            correlation_id = str(uuid.uuid4())
            store.start_processing(f"in-progress-{i}", correlation_id)
        
        for i in range(2):
            correlation_id = str(uuid.uuid4())
            store.start_processing(f"completed-{i}", correlation_id)
            store.complete(f"completed-{i}", {"result": i})
        
        stats = store.get_stats()
        
        assert stats["total"] == 5
        assert stats["by_status"]["in_progress"] == 3
        assert stats["by_status"]["completed"] == 2
    
    def test_request_hash_verification(self, mock_db_connection, cleanup_utils):
        """Test request hash verification."""
        store = IdempotencyStore(default_ttl=3600)
        
        # Start with request data
        request_data = {"action": "create", "data": "test"}
        correlation_id = str(uuid.uuid4())
        store.start_processing("key-123", correlation_id, request_data=request_data)
        
        # Check with same request - should work
        status, _ = store.check_idempotency("key-123", request_data)
        assert status == IdempotencyStatus.IN_PROGRESS
        
        # Check with different request - should raise error
        different_request = {"action": "delete", "data": "test"}
        with pytest.raises(KeyMismatchError):
            store.check_idempotency("key-123", different_request)


class TestIdempotencyContext:
    """Test IdempotencyContext context manager."""
    
    def test_context_new_request(self, mock_db_connection, cleanup_utils):
        """Test context with new request."""
        store = IdempotencyStore(default_ttl=3600)
        
        with IdempotencyContext(store, "key-123", "corr-123") as ctx:
            assert ctx.should_execute is True
            assert ctx.status == IdempotencyStatus.NEW
            
            # Complete the request
            ctx.complete({"result": "success"})
        
        # Verify completed
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.COMPLETED
        assert response == {"result": "success"}
    
    def test_context_completed_request(self, mock_db_connection, cleanup_utils):
        """Test context with already completed request."""
        store = IdempotencyStore(default_ttl=3600)
        
        # Pre-complete a request
        store.start_processing("key-123", "corr-123")
        store.complete("key-123", {"result": "cached"})
        
        with IdempotencyContext(store, "key-123", "corr-123") as ctx:
            assert ctx.should_execute is False
            assert ctx.status == IdempotencyStatus.COMPLETED
            assert ctx.cached_response == {"result": "cached"}
    
    def test_context_exception_rollback(self, mock_db_connection, cleanup_utils):
        """Test context with exception during processing."""
        store = IdempotencyStore(default_ttl=3600)
        
        try:
            with IdempotencyContext(store, "key-123", "corr-123") as ctx:
                assert ctx.should_execute is True
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Should be marked as failed (expired status with error)
        status, response = store.check_idempotency("key-123")
        assert status == IdempotencyStatus.EXPIRED


class TestGenerateKey:
    """Test key generation function."""
    
    def test_generate_key_single_component(self, cleanup_utils):
        """Test generating key from single component."""
        key1 = generate_key("component1")
        key2 = generate_key("component1")
        
        # Same components should produce same key
        assert key1 == key2
        assert len(key1) == 32  # SHA256 truncated to 32 chars
    
    def test_generate_key_multiple_components(self, cleanup_utils):
        """Test generating key from multiple components."""
        key1 = generate_key("action", "user123", "data456")
        key2 = generate_key("action", "user123", "data456")
        key3 = generate_key("action", "user123", "data789")
        
        assert key1 == key2
        assert key1 != key3
    
    def test_generate_key_different_order(self, cleanup_utils):
        """Test that order matters in key generation."""
        key1 = generate_key("a", "b", "c")
        key2 = generate_key("c", "b", "a")
        
        assert key1 != key2


class TestGlobalInstance:
    """Test global instance functions."""
    
    def test_get_idempotency_store_singleton(self, cleanup_utils):
        """Test that get_idempotency_store returns singleton."""
        store1 = get_idempotency_store()
        store2 = get_idempotency_store()
        
        assert store1 is store2
    
    def test_configure_idempotency_store(self, cleanup_utils):
        """Test configuring global store."""
        custom_store = IdempotencyStore(default_ttl=7200)
        configure_idempotency_store(custom_store)
        
        assert get_idempotency_store() is custom_store
    
    def test_convenience_functions(self, mock_db_connection, cleanup_utils):
        """Test convenience functions use global store."""
        # Reset global store
        configure_idempotency_store(IdempotencyStore(default_ttl=3600))
        
        # Test check_idempotency
        status, response = check_idempotency("test-key")
        assert status == IdempotencyStatus.NEW
        
        # Test store_response flow
        correlation_id = str(uuid.uuid4())
        store = get_idempotency_store()
        store.start_processing("test-key", correlation_id)
        
        result = store_response("test-key", {"result": "success"})
        assert result is True
        
        cached = get_cached_response("test-key")
        assert cached == {"result": "success"}


class TestConcurrentAccess:
    """Test concurrent access to idempotency store.
    
    Note: These tests verify the atomic insert logic but may not fully test
    concurrency in the mock database environment. In production, SQLite's
    UNIQUE constraint ensures only one insert succeeds.
    """
    
    def test_concurrent_start_processing(self, mock_db_connection, cleanup_utils):
        """Test that only one thread can start processing."""
        import concurrent.futures
        
        store = IdempotencyStore(default_ttl=3600)
        correlation_id = str(uuid.uuid4())
        results = []
        lock = threading.Lock()
        
        def try_start(worker_id):
            result = store.start_processing("shared-key", correlation_id)
            with lock:
                results.append((worker_id, result))
        
        # Try from multiple threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_start, f"worker-{i}") for i in range(5)]
            concurrent.futures.wait(futures)
        
        # In a proper SQLite environment, only one succeeds due to UNIQUE constraint
        # In mock environment, behavior may vary due to single connection
        successful = [r for r in results if r[1] is True]
        failed = [r for r in results if r[1] is False]
        
        # At most one should succeed (atomic guarantee)
        assert len(successful) <= 1
        assert len(successful) + len(failed) == 5
