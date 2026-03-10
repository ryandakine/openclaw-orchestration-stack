"""API health monitoring and performance tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .errors import APIError


logger = logging.getLogger(__name__)


class APIHealthStatus(Enum):
    """Health status levels for APIs."""
    HEALTHY = auto()      # Normal operation
    DEGRADED = auto()     # Reduced performance
    UNHEALTHY = auto()    # Significant issues
    DOWN = auto()         # Not responding


@dataclass
class APIMetrics:
    """Metrics for API performance."""
    
    # Request counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Timing (in milliseconds)
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    
    # Error tracking
    error_counts: dict[str, int] = field(default_factory=dict)
    last_error: str | None = None
    last_error_time: float | None = None
    
    # Recent latency history (circular buffer)
    latency_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=100)
    )
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100
    
    @property
    def average_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.total_requests == 0:
            return 0.0
        return self.total_latency_ms / self.total_requests
    
    @property
    def p95_latency_ms(self) -> float:
        """Calculate 95th percentile latency."""
        if not self.latency_history:
            return 0.0
        sorted_latencies = sorted(self.latency_history)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def p99_latency_ms(self) -> float:
        """Calculate 99th percentile latency."""
        if not self.latency_history:
            return 0.0
        sorted_latencies = sorted(self.latency_history)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]


@dataclass
class HealthThresholds:
    """Thresholds for determining health status."""
    
    # Success rate thresholds (%)
    healthy_success_rate: float = 95.0
    degraded_success_rate: float = 80.0
    unhealthy_success_rate: float = 50.0
    
    # Latency thresholds (ms)
    degraded_latency_ms: float = 1000.0
    unhealthy_latency_ms: float = 5000.0
    
    # Minimum requests before evaluating
    min_requests_for_eval: int = 10
    
    # Time window for evaluation (seconds)
    evaluation_window_seconds: float = 300.0


class APIMonitor:
    """Monitor for a single API."""
    
    def __init__(
        self,
        api_name: str,
        thresholds: HealthThresholds | None = None,
    ) -> None:
        """Initialize API monitor.
        
        Args:
            api_name: Name of the API being monitored
            thresholds: Health evaluation thresholds
        """
        self.api_name = api_name
        self.thresholds = thresholds or HealthThresholds()
        self.metrics = APIMetrics()
        self._start_time = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def record_request(
        self,
        latency_ms: float,
        success: bool,
        error: Exception | None = None,
    ) -> None:
        """Record a request result.
        
        Args:
            latency_ms: Request latency in milliseconds
            success: Whether the request succeeded
            error: Error information if request failed
        """
        async with self._lock:
            self.metrics.total_requests += 1
            self.metrics.total_latency_ms += latency_ms
            self.metrics.latency_history.append(latency_ms)
            
            # Update min/max latency
            self.metrics.min_latency_ms = min(
                self.metrics.min_latency_ms, latency_ms
            )
            self.metrics.max_latency_ms = max(
                self.metrics.max_latency_ms, latency_ms
            )
            
            if success:
                self.metrics.successful_requests += 1
            else:
                self.metrics.failed_requests += 1
                if error:
                    error_type = type(error).__name__
                    self.metrics.error_counts[error_type] = \
                        self.metrics.error_counts.get(error_type, 0) + 1
                    self.metrics.last_error = str(error)
                    self.metrics.last_error_time = time.monotonic()
    
    def evaluate_health(self) -> APIHealthStatus:
        """Evaluate current health status.
        
        Returns:
            Current health status
        """
        # Not enough data
        if self.metrics.total_requests < self.thresholds.min_requests_for_eval:
            return APIHealthStatus.HEALTHY
        
        success_rate = self.metrics.success_rate
        avg_latency = self.metrics.average_latency_ms
        
        # Check success rate
        if success_rate < self.thresholds.unhealthy_success_rate:
            return APIHealthStatus.UNHEALTHY
        if success_rate < self.thresholds.degraded_success_rate:
            return APIHealthStatus.DEGRADED
        
        # Check latency
        if avg_latency > self.thresholds.unhealthy_latency_ms:
            return APIHealthStatus.UNHEALTHY
        if avg_latency > self.thresholds.degraded_latency_ms:
            return APIHealthStatus.DEGRADED
        
        return APIHealthStatus.HEALTHY
    
    def get_status(self) -> dict[str, Any]:
        """Get current monitoring status."""
        health = self.evaluate_health()
        uptime_seconds = time.monotonic() - self._start_time
        
        return {
            "api_name": self.api_name,
            "health_status": health.name,
            "uptime_seconds": uptime_seconds,
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "successful_requests": self.metrics.successful_requests,
                "failed_requests": self.metrics.failed_requests,
                "success_rate_percent": round(self.metrics.success_rate, 2),
                "average_latency_ms": round(self.metrics.average_latency_ms, 2),
                "min_latency_ms": round(self.metrics.min_latency_ms, 2)
                if self.metrics.min_latency_ms != float("inf")
                else None,
                "max_latency_ms": round(self.metrics.max_latency_ms, 2),
                "p95_latency_ms": round(self.metrics.p95_latency_ms, 2),
                "p99_latency_ms": round(self.metrics.p99_latency_ms, 2),
            },
            "errors": {
                "error_counts": self.metrics.error_counts,
                "last_error": self.metrics.last_error,
                "last_error_time": self.metrics.last_error_time,
            },
            "thresholds": {
                "healthy_success_rate": self.thresholds.healthy_success_rate,
                "degraded_success_rate": self.thresholds.degraded_success_rate,
                "degraded_latency_ms": self.thresholds.degraded_latency_ms,
            },
        }
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.metrics = APIMetrics()
        self._start_time = time.monotonic()


class APIHealthMonitor:
    """Central health monitor for all APIs."""
    
    def __init__(self) -> None:
        """Initialize health monitor."""
        self._monitors: dict[str, APIMonitor] = {}
        self._lock = asyncio.Lock()
        self._alert_handlers: list[Callable[[str, APIHealthStatus], Any]] = []
    
    async def get_monitor(
        self,
        api_name: str,
        thresholds: HealthThresholds | None = None,
    ) -> APIMonitor:
        """Get or create monitor for an API.
        
        Args:
            api_name: Name of the API
            thresholds: Optional health thresholds
            
        Returns:
            APIMonitor instance
        """
        async with self._lock:
            if api_name not in self._monitors:
                self._monitors[api_name] = APIMonitor(api_name, thresholds)
            return self._monitors[api_name]
    
    async def record_request(
        self,
        api_name: str,
        latency_ms: float,
        success: bool,
        error: Exception | None = None,
    ) -> APIHealthStatus:
        """Record a request for an API.
        
        Args:
            api_name: Name of the API
            latency_ms: Request latency in milliseconds
            success: Whether request succeeded
            error: Error if request failed
            
        Returns:
            Current health status
        """
        monitor = await self.get_monitor(api_name)
        await monitor.record_request(latency_ms, success, error)
        
        health = monitor.evaluate_health()
        
        # Log degraded performance
        if health == APIHealthStatus.DEGRADED:
            logger.warning(
                f"API '{api_name}' performance degraded: "
                f"success_rate={monitor.metrics.success_rate:.1f}%, "
                f"avg_latency={monitor.metrics.average_latency_ms:.0f}ms"
            )
        elif health == APIHealthStatus.UNHEALTHY:
            logger.error(
                f"API '{api_name}' is unhealthy: "
                f"success_rate={monitor.metrics.success_rate:.1f}%, "
                f"avg_latency={monitor.metrics.average_latency_ms:.0f}ms"
            )
        
        return health
    
    async def track_request(
        self,
        api_name: str,
    ) -> RequestTracker:
        """Get a context manager for tracking a request.
        
        Usage:
            async with monitor.track_request("api") as tracker:
                result = await api.call()
                # Status auto-recorded on exit
        """
        return RequestTracker(self, api_name)
    
    def register_alert_handler(
        self,
        handler: Callable[[str, APIHealthStatus], Any],
    ) -> None:
        """Register a handler for health status changes."""
        self._alert_handlers.append(handler)
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all monitored APIs."""
        return {
            name: monitor.get_status()
            for name, monitor in self._monitors.items()
        }
    
    def get_unhealthy_apis(self) -> list[str]:
        """Get list of unhealthy API names."""
        return [
            name for name, monitor in self._monitors.items()
            if monitor.evaluate_health() in (
                APIHealthStatus.UNHEALTHY,
                APIHealthStatus.DOWN,
            )
        ]
    
    async def reset_api(self, api_name: str) -> None:
        """Reset metrics for a specific API."""
        async with self._lock:
            if api_name in self._monitors:
                self._monitors[api_name].reset()
    
    def reset_all(self) -> None:
        """Reset all monitors."""
        for monitor in self._monitors.values():
            monitor.reset()


class RequestTracker:
    """Context manager for tracking individual requests."""
    
    def __init__(
        self,
        monitor: APIHealthMonitor,
        api_name: str,
    ) -> None:
        """Initialize request tracker.
        
        Args:
            monitor: Health monitor instance
            api_name: Name of the API
        """
        self.monitor = monitor
        self.api_name = api_name
        self.start_time: float = 0.0
        self.success: bool = False
        self.error: Exception | None = None
    
    async def __aenter__(self) -> RequestTracker:
        """Start tracking request."""
        self.start_time = time.perf_counter()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """End tracking and record metrics."""
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        
        if exc_val is None:
            self.success = True
        else:
            self.success = False
            self.error = exc_val
        
        await self.monitor.record_request(
            api_name=self.api_name,
            latency_ms=elapsed_ms,
            success=self.success,
            error=self.error,
        )


# Global health monitor instance
_global_health_monitor: APIHealthMonitor | None = None


async def get_health_monitor() -> APIHealthMonitor:
    """Get global health monitor instance."""
    global _global_health_monitor
    if _global_health_monitor is None:
        _global_health_monitor = APIHealthMonitor()
    return _global_health_monitor
