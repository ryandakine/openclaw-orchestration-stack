"""Circuit breaker pattern implementation for API resilience."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Awaitable, Callable, TypeVar

from .errors import APIError, CircuitBreakerError


T = TypeVar("T")
logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing, rejecting requests
    HALF_OPEN = auto()   # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    
    # Number of failures before opening circuit
    failure_threshold: int = 5
    
    # Cooldown period in seconds before attempting reset
    cooldown_seconds: float = 60.0
    
    # Number of successes required to close circuit from half-open
    success_threshold: int = 3
    
    # Exceptions that count as failures
    failure_exceptions: set[type[Exception]] = field(default_factory=lambda: {
        APIError,
        ConnectionError,
        TimeoutError,
    })
    
    # Exceptions that should not count as failures
    ignore_exceptions: set[type[Exception]] = field(default_factory=set)


class CircuitBreaker:
    """Circuit breaker for API resilience.
    
    Opens after N consecutive failures, preventing cascade failures.
    Enters half-open state after cooldown to test recovery.
    Closes after successful test requests.
    """
    
    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Initialize circuit breaker.
        
        Args:
            name: Circuit breaker identifier
            config: Circuit breaker configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (rejecting requests)."""
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)."""
        return self._state == CircuitState.HALF_OPEN
    
    def _should_trip(self, exception: Exception) -> bool:
        """Check if an exception should trip the circuit."""
        # Check ignore list first
        for exc_type in self.config.ignore_exceptions:
            if isinstance(exception, exc_type):
                return False
        
        # Check failure list
        for exc_type in self.config.failure_exceptions:
            if isinstance(exception, exc_type):
                return True
        
        # Default: unknown exceptions don't trip
        return False
    
    def _can_attempt_reset(self) -> bool:
        """Check if enough time has passed to try resetting."""
        if self._last_failure_time is None:
            return True
        
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed >= self.config.cooldown_seconds
    
    async def _record_success(self) -> None:
        """Record a successful request."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    logger.info(
                        f"Circuit breaker '{self.name}' closed after "
                        f"{self._success_count} successes"
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                if self._failure_count > 0:
                    self._failure_count = 0
    
    async def _record_failure(self, exception: Exception) -> None:
        """Record a failed request."""
        if not self._should_trip(exception):
            return
        
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            
            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open goes back to open
                logger.warning(
                    f"Circuit breaker '{self.name}' re-opened after "
                    f"failure in half-open state"
                )
                self._state = CircuitState.OPEN
                self._success_count = 0
            
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    logger.error(
                        f"Circuit breaker '{self.name}' opened after "
                        f"{self._failure_count} consecutive failures"
                    )
                    self._state = CircuitState.OPEN
    
    async def _try_transition_to_half_open(self) -> bool:
        """Try to transition from open to half-open."""
        async with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._can_attempt_reset()
            ):
                logger.info(
                    f"Circuit breaker '{self.name}' entering half-open state"
                )
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return True
            return False
    
    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        """Execute an operation with circuit breaker protection.
        
        Args:
            operation: Async callable to execute
            
        Returns:
            Result of the operation
            
        Raises:
            CircuitBreakerError: If circuit is open
            Any exception raised by the operation
        """
        # Check if circuit is open
        if self._state == CircuitState.OPEN:
            if not await self._try_transition_to_half_open():
                raise CircuitBreakerError(
                    message=f"Circuit breaker '{self.name}' is open",
                    api_name=self.name,
                    cooldown_seconds=self.config.cooldown_seconds,
                )
        
        try:
            result = await operation()
            await self._record_success()
            return result
            
        except Exception as e:
            await self._record_failure(e)
            raise
    
    async def __aenter__(self) -> CircuitBreaker:
        """Async context manager entry."""
        if self._state == CircuitState.OPEN:
            if not await self._try_transition_to_half_open():
                raise CircuitBreakerError(
                    message=f"Circuit breaker '{self.name}' is open",
                    api_name=self.name,
                    cooldown_seconds=self.config.cooldown_seconds,
                )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        if exc_val is not None:
            await self._record_failure(exc_val)
        else:
            await self._record_success()
    
    def get_status(self) -> dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self._state.name,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.config.failure_threshold,
            "cooldown_seconds": self.config.cooldown_seconds,
            "last_failure_time": self._last_failure_time,
            "time_since_last_failure": (
                time.monotonic() - self._last_failure_time
                if self._last_failure_time
                else None
            ),
        }
    
    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        logger.info(f"Circuit breaker '{self.name}' manually reset")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers."""
    
    def __init__(self) -> None:
        """Initialize circuit breaker registry."""
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_breaker(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Get or create a circuit breaker.
        
        Args:
            name: Circuit breaker identifier
            config: Optional configuration
            
        Returns:
            CircuitBreaker instance
        """
        async with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config)
            return self._breakers[name]
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all circuit breakers."""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
        }
    
    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
    
    async def remove(self, name: str) -> None:
        """Remove a circuit breaker from registry."""
        async with self._lock:
            if name in self._breakers:
                del self._breakers[name]
