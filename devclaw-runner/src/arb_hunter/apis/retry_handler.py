"""Exponential backoff retry handler for API requests."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

import httpx

from .errors import APIError, RateLimitError, ServerError, TimeoutError


T = TypeVar("T")
logger = logging.getLogger(__name__)


class RetryableError(Enum):
    """Types of errors that can trigger retries."""
    TIMEOUT = "timeout"
    SERVER_ERROR = "server_error"
    RATE_LIMIT = "rate_limit"
    CONNECTION_ERROR = "connection_error"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    
    # Number of retry attempts
    max_attempts: int = 5
    
    # Base delay for exponential backoff (seconds)
    base_delay: float = 1.0
    
    # Maximum delay between retries (seconds)
    max_delay: float = 60.0
    
    # Exponential backoff multiplier
    backoff_factor: float = 2.0
    
    # Add jitter to avoid thundering herd
    jitter: bool = True
    jitter_max: float = 1.0
    
    # Retry on specific status codes
    retry_status_codes: set[int] | None = None
    
    # Retry on exceptions
    retry_exceptions: set[type[Exception]] | None = None
    
    # Don't retry on these status codes
    no_retry_status_codes: set[int] | None = None
    
    def __post_init__(self) -> None:
        """Set default retry conditions."""
        if self.retry_status_codes is None:
            # Retry 5xx server errors and 429 rate limit
            self.retry_status_codes = {429, 500, 502, 503, 504}
        
        if self.retry_exceptions is None:
            self.retry_exceptions = {
                TimeoutError,
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.NetworkError,
            }
        
        if self.no_retry_status_codes is None:
            # Don't retry client errors (4xx except 429)
            self.no_retry_status_codes = {400, 401, 403, 404, 405, 422}


class RetryHandler:
    """Handles retries with exponential backoff."""
    
    def __init__(self, config: RetryConfig | None = None) -> None:
        """Initialize retry handler.
        
        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()
        self._attempt_counts: dict[str, int] = {}
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt.
        
        Uses exponential backoff: base * factor^attempt
        
        Args:
            attempt: Current attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        delay = self.config.base_delay * (self.config.backoff_factor ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            # Add random jitter to avoid thundering herd
            jitter = random.uniform(0, self.config.jitter_max)
            delay += jitter
        
        return delay
    
    def _should_retry(
        self,
        exception: Exception | None,
        status_code: int | None,
    ) -> bool:
        """Determine if an error should trigger a retry.
        
        Args:
            exception: The exception that occurred
            status_code: HTTP status code if available
            
        Returns:
            True if should retry, False otherwise
        """
        # Don't retry if max attempts reached
        # Check status codes first
        if status_code is not None:
            if status_code in self.config.no_retry_status_codes:
                return False
            if status_code in self.config.retry_status_codes:
                return True
            # Don't retry 4xx errors (client errors)
            if 400 <= status_code < 500:
                return False
            # Retry 5xx errors (server errors)
            if status_code >= 500:
                return True
        
        # Check exception type
        if exception is not None:
            for exc_type in self.config.retry_exceptions:
                if isinstance(exception, exc_type):
                    return True
        
        return False
    
    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str = "operation",
    ) -> T:
        """Execute an operation with retry logic.
        
        Args:
            operation: Async callable to execute
            operation_name: Name of the operation for logging
            
        Returns:
            Result of the operation
            
        Raises:
            The last exception if all retries fail
        """
        last_exception: Exception | None = None
        status_code: int | None = None
        
        for attempt in range(self.config.max_attempts):
            try:
                result = await operation()
                
                # Log success after retries
                if attempt > 0:
                    logger.info(
                        f"{operation_name} succeeded after {attempt + 1} attempts"
                    )
                
                return result
                
            except APIError as e:
                last_exception = e
                status_code = e.status_code
                
                # Check if we should retry
                if not self._should_retry(e, status_code):
                    logger.warning(
                        f"{operation_name} failed with non-retryable error: {e}"
                    )
                    raise
                
                # Check if this was the last attempt
                if attempt >= self.config.max_attempts - 1:
                    logger.error(
                        f"{operation_name} failed after {self.config.max_attempts} attempts"
                    )
                    raise
                
                # Calculate and wait for delay
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"{operation_name} failed (attempt {attempt + 1}/{self.config.max_attempts}): "
                    f"{e}. Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                
            except Exception as e:
                last_exception = e
                
                # Check if we should retry this exception
                if not self._should_retry(e, None):
                    raise
                
                # Check if this was the last attempt
                if attempt >= self.config.max_attempts - 1:
                    logger.error(
                        f"{operation_name} failed after {self.config.max_attempts} attempts: {e}"
                    )
                    raise
                
                # Calculate and wait for delay
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"{operation_name} failed (attempt {attempt + 1}/{self.config.max_attempts}): "
                    f"{e}. Retrying in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
        
        # This should not be reached, but just in case
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected end of retry loop")
    
    def get_stats(self) -> dict[str, Any]:
        """Get retry statistics."""
        return {
            "max_attempts": self.config.max_attempts,
            "base_delay": self.config.base_delay,
            "backoff_factor": self.config.backoff_factor,
            "attempt_counts": self._attempt_counts.copy(),
        }


class ConditionalRetryHandler(RetryHandler):
    """Retry handler with conditional logic based on API responses."""
    
    def __init__(
        self,
        config: RetryConfig | None = None,
        retry_condition: Callable[[Any], bool] | None = None,
    ) -> None:
        """Initialize conditional retry handler.
        
        Args:
            config: Retry configuration
            retry_condition: Optional function to check if result needs retry
        """
        super().__init__(config)
        self.retry_condition = retry_condition
    
    async def execute(
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str = "operation",
    ) -> T:
        """Execute with conditional retry based on result."""
        last_exception: Exception | None = None
        
        for attempt in range(self.config.max_attempts):
            try:
                result = await operation()
                
                # Check if result indicates need for retry
                if self.retry_condition and self.retry_condition(result):
                    if attempt >= self.config.max_attempts - 1:
                        logger.error(
                            f"{operation_name} result still not valid after "
                            f"{self.config.max_attempts} attempts"
                        )
                        return result
                    
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"{operation_name} result invalid (attempt {attempt + 1}). "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                    continue
                
                return result
                
            except Exception as e:
                last_exception = e
                
                if not self._should_retry(e, getattr(e, "status_code", None)):
                    raise
                
                if attempt >= self.config.max_attempts - 1:
                    raise
                
                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)
        
        if last_exception:
            raise last_exception
        raise RuntimeError("Unexpected end of retry loop")


# Default retry configurations for different scenarios
DEFAULT_RETRY_CONFIG = RetryConfig()

AGGRESSIVE_RETRY_CONFIG = RetryConfig(
    max_attempts=10,
    base_delay=0.5,
    max_delay=30.0,
)

CONSERVATIVE_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=2.0,
    max_delay=120.0,
)

NO_RETRY_CONFIG = RetryConfig(
    max_attempts=1,
)
