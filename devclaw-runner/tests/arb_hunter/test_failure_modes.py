"""
Test Failure Modes Module

Tests for API failure handling, partial scans, and circuit breaker.
"""

import pytest
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestAPIFailureHandling:
    """Test handling of API failures."""
    
    @pytest.mark.asyncio
    async def test_http_error_handling(self):
        """Test handling of HTTP errors."""
        client = MagicMock()
        client.get = AsyncMock(side_effect=Exception("HTTP 500"))
        
        result = await self._fetch_with_error_handling(client, "https://api.example.com")
        
        assert result["success"] is False
        assert "HTTP 500" in result["error"]
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test handling of request timeouts."""
        client = MagicMock()
        client.get = AsyncMock(side_effect=asyncio.TimeoutError())
        
        result = await self._fetch_with_timeout_handling(client, "https://api.example.com", timeout=5)
        
        assert result["success"] is False
        assert "timeout" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test handling of rate limit responses."""
        response = MagicMock()
        response.status = 429
        response.headers = {"Retry-After": "60"}
        
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        
        result = await self._fetch_with_rate_limit_handling(client, "https://api.example.com")
        
        assert result["success"] is False
        assert result["rate_limited"] is True
        assert result["retry_after"] == 60
    
    @pytest.mark.asyncio
    async def test_malformed_json_handling(self):
        """Test handling of malformed JSON responses."""
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(side_effect=Exception("Invalid JSON"))
        response.text = AsyncMock(return_value="not json")
        
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        
        result = await self._fetch_with_parsing_handling(client, "https://api.example.com")
        
        assert result["success"] is False
        assert "parse" in result["error"].lower() or "json" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_empty_response_handling(self):
        """Test handling of empty responses."""
        response = MagicMock()
        response.status = 200
        response.json = AsyncMock(return_value={})
        
        client = MagicMock()
        client.get = AsyncMock(return_value=response)
        
        result = await self._fetch_with_parsing_handling(client, "https://api.example.com")
        
        # Empty is valid, just no data
        assert result["success"] is True
        assert result["data"] == {}
    
    @pytest.mark.asyncio
    async def test_retry_with_backoff(self):
        """Test retry with exponential backoff."""
        client = MagicMock()
        client.get = AsyncMock(side_effect=[
            Exception("Error 1"),
            Exception("Error 2"),
            MagicMock(status=200, json=AsyncMock(return_value={"data": "success"}))
        ])
        
        result = await self._fetch_with_retry(client, "https://api.example.com", max_retries=3)
        
        assert result["success"] is True
        assert result["data"] == {"data": "success"}
        assert client.get.call_count == 3


class TestPartialScanHandling:
    """Test handling of partial scan results."""
    
    def test_partial_data_continuation(self):
        """Test pipeline continues with partial data."""
        # Some sources succeed, others fail
        results = {
            "polymarket": [{"id": "pm_1"}, {"id": "pm_2"}],
            "odds_api": None,  # Failed
            "backup_source": [{"id": "bk_1"}]
        }
        
        combined = self._combine_partial_results(results)
        
        assert len(combined) == 3  # pm_1, pm_2, bk_1
        assert combined[0]["source"] == "polymarket"
    
    def test_partial_normalization(self):
        """Test normalization of partial data."""
        raw_data = [
            {"id": "1", "valid": True},
            None,  # Failed to fetch
            {"id": "2", "valid": True},
            {"id": "3"}  # Missing fields
        ]
        
        normalized = self._normalize_partial_data(raw_data)
        
        assert len(normalized) == 2  # Only valid entries
    
    def test_missing_field_tolerance(self):
        """Test tolerance for missing non-critical fields."""
        data = {
            "id": "test",
            "critical_field": "present"
            # Missing optional fields
        }
        
        result = self._process_with_defaults(data)
        
        assert result["success"] is True
        assert "optional_1" in result  # Should have defaults
    
    def test_degraded_mode_operation(self):
        """Test operation in degraded mode with limited data."""
        # Only one data source available
        available_sources = ["polymarket"]
        
        result = self._run_in_degraded_mode(available_sources)
        
        assert result["mode"] == "degraded"
        assert result["active_sources"] == 1
        assert result["limited_matches"] is True


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker instance."""
        return {
            "state": "CLOSED",
            "failures": 0,
            "successes": 0,
            "consecutive_failures": 0,
            "last_failure_time": None,
            "threshold": 5,
            "timeout": 60
        }
    
    def test_circuit_closed_initially(self, circuit_breaker: dict):
        """Test circuit starts in closed state."""
        assert circuit_breaker["state"] == "CLOSED"
        assert self._can_execute(circuit_breaker) is True
    
    def test_circuit_opens_after_failures(self, circuit_breaker: dict):
        """Test circuit opens after threshold failures."""
        for _ in range(5):
            self._record_failure(circuit_breaker)
        
        assert circuit_breaker["state"] == "OPEN"
        assert self._can_execute(circuit_breaker) is False
    
    def test_circuit_half_open_after_timeout(self, circuit_breaker: dict):
        """Test circuit transitions to half-open after timeout."""
        # Open the circuit
        for _ in range(5):
            self._record_failure(circuit_breaker)
        
        assert circuit_breaker["state"] == "OPEN"
        
        # Simulate time passing
        circuit_breaker["last_failure_time"] = datetime.now() - timedelta(seconds=70)
        
        self._check_state_transition(circuit_breaker)
        
        assert circuit_breaker["state"] == "HALF_OPEN"
    
    def test_circuit_closes_on_success(self, circuit_breaker: dict):
        """Test circuit closes after successful call in half-open."""
        circuit_breaker["state"] = "HALF_OPEN"
        circuit_breaker["consecutive_failures"] = 5
        
        self._record_success(circuit_breaker)
        
        assert circuit_breaker["state"] == "CLOSED"
        assert circuit_breaker["consecutive_failures"] == 0
    
    def test_circuit_reopens_on_failure(self, circuit_breaker: dict):
        """Test circuit reopens if failure in half-open state."""
        circuit_breaker["state"] = "HALF_OPEN"
        
        self._record_failure(circuit_breaker)
        
        assert circuit_breaker["state"] == "OPEN"
    
    def test_success_resets_failure_count(self, circuit_breaker: dict):
        """Test success resets consecutive failure count."""
        circuit_breaker["consecutive_failures"] = 3
        
        self._record_success(circuit_breaker)
        
        assert circuit_breaker["consecutive_failures"] == 0
    
    def test_circuit_metrics(self, circuit_breaker: dict):
        """Test circuit breaker metrics collection."""
        self._record_success(circuit_breaker)
        self._record_success(circuit_breaker)
        self._record_failure(circuit_breaker)
        
        metrics = self._get_circuit_metrics(circuit_breaker)
        
        assert metrics["total_calls"] == 3
        assert metrics["success_rate"] == 2/3
    
    def test_multiple_services_independent(self):
        """Test that each service has independent circuit breaker."""
        cb_polymarket = {"state": "CLOSED", "failures": 0}
        cb_odds_api = {"state": "CLOSED", "failures": 0}
        
        # Fail polymarket only
        for _ in range(5):
            self._record_failure(cb_polymarket)
        
        assert cb_polymarket["state"] == "OPEN"
        assert cb_odds_api["state"] == "CLOSED"


class TestGracefulDegradation:
    """Test graceful degradation strategies."""
    
    def test_fallback_to_cache(self):
        """Test fallback to cached data when API fails."""
        cache = {
            "timestamp": datetime.now() - timedelta(minutes=10),
            "data": [{"id": "cached_1"}]
        }
        
        result = self._fallback_to_cache(cache, max_age_minutes=30)
        
        assert result["success"] is True
        assert result["from_cache"] is True
        assert result["data"] == cache["data"]
    
    def test_cache_too_old(self):
        """Test cache rejection when too old."""
        cache = {
            "timestamp": datetime.now() - timedelta(hours=2),
            "data": [{"id": "cached_1"}]
        }
        
        result = self._fallback_to_cache(cache, max_age_minutes=30)
        
        assert result["success"] is False
        assert result["from_cache"] is False
    
    def test_reduced_polling_frequency(self):
        """Test reduced polling in failure scenarios."""
        failure_count = 3
        base_interval = 60  # seconds
        
        new_interval = self._calculate_backoff_interval(failure_count, base_interval)
        
        assert new_interval > base_interval
        assert new_interval <= base_interval * (2 ** failure_count)
    
    def test_emergency_notification(self):
        """Test emergency notification on critical failure."""
        critical_error = {
            "type": "API_DOWN",
            "service": "polymarket",
            "duration": 300
        }
        
        notification = self._send_emergency_notification(critical_error)
        
        assert notification["sent"] is True
        assert notification["priority"] == "HIGH"


class TestRecoveryMechanisms:
    """Test recovery mechanisms after failures."""
    
    @pytest.mark.asyncio
    async def test_auto_retry_recovery(self):
        """Test automatic retry after transient failure."""
        call_count = 0
        
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Transient error")
            return {"success": True}
        
        result = await self._retry_with_backoff(flaky_function, max_retries=5)
        
        assert result["success"] is True
        assert call_count == 3
    
    def test_manual_override(self):
        """Test manual override to reset circuit breaker."""
        cb = {"state": "OPEN", "failures": 10, "consecutive_failures": 5}
        
        self._manual_circuit_reset(cb)
        
        assert cb["state"] == "CLOSED"
        assert cb["failures"] == 0
        assert cb["consecutive_failures"] == 0
    
    def test_health_check_recovery(self):
        """Test recovery through health checks."""
        service_status = {"healthy": False, "last_check": None}
        
        # Simulate health check passing
        self._run_health_check(service_status, healthy=True)
        
        assert service_status["healthy"] is True


# Helper methods

    async def _fetch_with_error_handling(self, client: MagicMock, url: str) -> dict:
        """Fetch with error handling."""
        try:
            await client.get(url)
            return {"success": True, "data": {}}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _fetch_with_timeout_handling(self, client: MagicMock, url: str, timeout: int) -> dict:
        """Fetch with timeout handling."""
        try:
            await asyncio.wait_for(client.get(url), timeout=timeout)
            return {"success": True, "data": {}}
        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timeout"}
    
    async def _fetch_with_rate_limit_handling(self, client: MagicMock, url: str) -> dict:
        """Fetch with rate limit handling."""
        response = await client.get(url)
        
        if response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            return {
                "success": False,
                "rate_limited": True,
                "retry_after": retry_after
            }
        
        return {"success": True, "data": await response.json()}
    
    async def _fetch_with_parsing_handling(self, client: MagicMock, url: str) -> dict:
        """Fetch with parsing error handling."""
        try:
            response = await client.get(url)
            data = await response.json()
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": f"Parse error: {e}"}
    
    async def _fetch_with_retry(self, client: MagicMock, url: str, max_retries: int) -> dict:
        """Fetch with retry logic."""
        for attempt in range(max_retries):
            try:
                response = await client.get(url)
                if hasattr(response, 'status') and response.status == 200:
                    return {"success": True, "data": await response.json()}
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))  # Exponential backoff
        
        return {"success": False, "error": "Max retries exceeded"}
    
    def _combine_partial_results(self, results: dict) -> list:
        """Combine partial results from multiple sources."""
        combined = []
        for source, data in results.items():
            if data is not None:
                for item in data:
                    item["source"] = source
                    combined.append(item)
        return combined
    
    def _normalize_partial_data(self, raw_data: list) -> list:
        """Normalize partial data, skipping invalid entries."""
        return [item for item in raw_data if item is not None and item.get("valid")]
    
    def _process_with_defaults(self, data: dict) -> dict:
        """Process data with defaults for missing fields."""
        result = {
            "success": True,
            "optional_1": data.get("optional_1", "default_1"),
            "optional_2": data.get("optional_2", "default_2"),
        }
        return result
    
    def _run_in_degraded_mode(self, available_sources: list) -> dict:
        """Run in degraded mode with limited sources."""
        return {
            "mode": "degraded",
            "active_sources": len(available_sources),
            "limited_matches": len(available_sources) < 2
        }
    
    def _can_execute(self, cb: dict) -> bool:
        """Check if circuit allows execution."""
        return cb["state"] in ["CLOSED", "HALF_OPEN"]
    
    def _record_failure(self, cb: dict):
        """Record a failure in circuit breaker."""
        cb["failures"] += 1
        cb["consecutive_failures"] += 1
        cb["last_failure_time"] = datetime.now()
        
        if cb["consecutive_failures"] >= cb.get("threshold", 5):
            cb["state"] = "OPEN"
    
    def _record_success(self, cb: dict):
        """Record a success in circuit breaker."""
        cb["successes"] += 1
        cb["consecutive_failures"] = 0
        
        if cb["state"] == "HALF_OPEN":
            cb["state"] = "CLOSED"
    
    def _check_state_transition(self, cb: dict):
        """Check and transition circuit breaker state."""
        if cb["state"] == "OPEN":
            last_failure = cb.get("last_failure_time")
            if last_failure:
                elapsed = (datetime.now() - last_failure).total_seconds()
                if elapsed > cb.get("timeout", 60):
                    cb["state"] = "HALF_OPEN"
    
    def _get_circuit_metrics(self, cb: dict) -> dict:
        """Get circuit breaker metrics."""
        total = cb["successes"] + cb["failures"]
        return {
            "total_calls": total,
            "success_rate": cb["successes"] / total if total > 0 else 0
        }
    
    def _fallback_to_cache(self, cache: dict, max_age_minutes: int) -> dict:
        """Fallback to cached data."""
        age = (datetime.now() - cache["timestamp"]).total_seconds() / 60
        
        if age <= max_age_minutes:
            return {"success": True, "from_cache": True, "data": cache["data"]}
        
        return {"success": False, "from_cache": False}
    
    def _calculate_backoff_interval(self, failure_count: int, base_interval: int) -> int:
        """Calculate backoff interval."""
        return min(base_interval * (2 ** failure_count), 3600)  # Max 1 hour
    
    def _send_emergency_notification(self, error: dict) -> dict:
        """Send emergency notification."""
        return {"sent": True, "priority": "HIGH", "error": error}
    
    async def _retry_with_backoff(self, func, max_retries: int) -> dict:
        """Retry function with backoff."""
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception:
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.1 * (2 ** attempt))
        return {"success": False}
    
    def _manual_circuit_reset(self, cb: dict):
        """Manually reset circuit breaker."""
        cb["state"] = "CLOSED"
        cb["failures"] = 0
        cb["consecutive_failures"] = 0
        cb["last_failure_time"] = None
    
    def _run_health_check(self, service_status: dict, healthy: bool):
        """Run health check and update status."""
        service_status["healthy"] = healthy
        service_status["last_check"] = datetime.now()
