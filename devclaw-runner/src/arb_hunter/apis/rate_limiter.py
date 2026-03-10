"""Token bucket rate limiter for API rate limiting."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar

from .errors import RateLimitError


class RateLimitStrategy(Enum):
    """Rate limiting strategies."""
    TOKEN_BUCKET = "token_bucket"
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    
    # Requests per time window
    requests_per_minute: int = 100
    requests_per_hour: int | None = None
    requests_per_day: int | None = None
    requests_per_month: int | None = None
    
    # Burst allowance
    burst_size: int | None = None
    
    # Strategy
    strategy: RateLimitStrategy = RateLimitStrategy.TOKEN_BUCKET
    
    def __post_init__(self) -> None:
        """Set default burst size if not specified."""
        if self.burst_size is None:
            self.burst_size = self.requests_per_minute


class TokenBucket:
    """Token bucket implementation for rate limiting."""
    
    def __init__(
        self,
        rate: float,  # tokens per second
        capacity: float,  # maximum tokens
        initial_tokens: float | None = None,
    ) -> None:
        """Initialize token bucket.
        
        Args:
            rate: Token refill rate (tokens per second)
            capacity: Maximum number of tokens in bucket
            initial_tokens: Starting token count (defaults to capacity)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens from the bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            Time waited for tokens
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            
            # Refill tokens based on elapsed time
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            
            # Calculate wait time
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.rate
            
            # Consume all available tokens
            self.tokens = 0.0
            
            return wait_time
    
    async def wait(self, tokens: float = 1.0) -> None:
        """Wait until tokens are available and acquire them.
        
        Args:
            tokens: Number of tokens to acquire
        """
        wait_time = await self.acquire(tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
    
    def get_status(self) -> dict[str, float]:
        """Get current bucket status."""
        now = time.monotonic()
        elapsed = now - self.last_update
        current_tokens = min(
            self.capacity,
            self.tokens + elapsed * self.rate
        )
        return {
            "tokens": current_tokens,
            "capacity": self.capacity,
            "rate": self.rate,
            "utilization": 1.0 - (current_tokens / self.capacity),
        }


class RateLimiter:
    """API rate limiter supporting multiple time windows."""
    
    # Predefined rate limits for known APIs
    DEFAULT_LIMITS: ClassVar[dict[str, RateLimitConfig]] = {
        "polymarket": RateLimitConfig(
            requests_per_minute=100,
            burst_size=100,
        ),
        "odds_api": RateLimitConfig(
            requests_per_minute=500,
            requests_per_month=500,
            burst_size=10,
        ),
        "kalshi": RateLimitConfig(
            requests_per_minute=100,
            burst_size=50,
        ),
        "predictit": RateLimitConfig(
            requests_per_minute=60,
            burst_size=20,
        ),
    }
    
    def __init__(
        self,
        api_name: str,
        config: RateLimitConfig | None = None,
    ) -> None:
        """Initialize rate limiter for an API.
        
        Args:
            api_name: Name of the API
            config: Rate limit configuration (uses defaults if None)
        """
        self.api_name = api_name
        self.config = config or self.DEFAULT_LIMITS.get(
            api_name, RateLimitConfig()
        )
        
        # Initialize token buckets for each time window
        self._buckets: dict[str, TokenBucket] = {}
        self._monthly_counter: dict[str, int] = {}
        self._monthly_lock = asyncio.Lock()
        
        # Per-minute bucket
        minute_rate = self.config.requests_per_minute / 60.0
        self._buckets["per_minute"] = TokenBucket(
            rate=minute_rate,
            capacity=float(self.config.burst_size or self.config.requests_per_minute),
        )
        
        # Per-hour bucket (if configured)
        if self.config.requests_per_hour:
            hour_rate = self.config.requests_per_hour / 3600.0
            self._buckets["per_hour"] = TokenBucket(
                rate=hour_rate,
                capacity=float(self.config.requests_per_hour),
            )
        
        # Per-day bucket (if configured)
        if self.config.requests_per_day:
            day_rate = self.config.requests_per_day / 86400.0
            self._buckets["per_day"] = TokenBucket(
                rate=day_rate,
                capacity=float(self.config.requests_per_day),
            )
        
        # Track request timestamps for sliding window
        self._request_times: asyncio.Queue[float] = asyncio.Queue()
        self._cleanup_task: asyncio.Task | None = None
    
    async def acquire(self) -> None:
        """Acquire permission to make a request.
        
        Waits if necessary to respect rate limits.
        
        Raises:
            RateLimitError: If monthly limit exceeded
        """
        # Check monthly limit first
        if self.config.requests_per_month:
            async with self._monthly_lock:
                current_month = time.strftime("%Y-%m")
                monthly_count = self._monthly_counter.get(current_month, 0)
                if monthly_count >= self.config.requests_per_month:
                    raise RateLimitError(
                        message=f"Monthly rate limit exceeded for {self.api_name}",
                        api_name=self.api_name,
                    )
        
        # Wait for all applicable buckets
        for bucket_name, bucket in self._buckets.items():
            await bucket.wait(1.0)
        
        # Record request for monthly tracking
        if self.config.requests_per_month:
            async with self._monthly_lock:
                current_month = time.strftime("%Y-%m")
                self._monthly_counter[current_month] = \
                    self._monthly_counter.get(current_month, 0) + 1
        
        # Record request time
        await self._request_times.put(time.monotonic())
    
    async def try_acquire(self) -> bool:
        """Try to acquire permission without waiting.
        
        Returns:
            True if permission granted, False otherwise
        """
        try:
            await asyncio.wait_for(self.acquire(), timeout=0.001)
            return True
        except (asyncio.TimeoutError, RateLimitError):
            return False
    
    def get_status(self) -> dict[str, Any]:
        """Get current rate limiter status."""
        status = {
            "api_name": self.api_name,
            "buckets": {
                name: bucket.get_status()
                for name, bucket in self._buckets.items()
            },
        }
        
        if self.config.requests_per_month:
            current_month = time.strftime("%Y-%m")
            status["monthly_usage"] = {
                "month": current_month,
                "used": self._monthly_counter.get(current_month, 0),
                "limit": self.config.requests_per_month,
            }
        
        return status
    
    async def __aenter__(self) -> RateLimiter:
        """Async context manager entry."""
        await self.acquire()
        return self
    
    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        pass


class CompositeRateLimiter:
    """Rate limiter that manages multiple APIs."""
    
    def __init__(self) -> None:
        """Initialize composite rate limiter."""
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()
    
    async def get_limiter(
        self,
        api_name: str,
        config: RateLimitConfig | None = None,
    ) -> RateLimiter:
        """Get or create rate limiter for an API.
        
        Args:
            api_name: Name of the API
            config: Optional rate limit configuration
            
        Returns:
            RateLimiter instance for the API
        """
        async with self._lock:
            if api_name not in self._limiters:
                self._limiters[api_name] = RateLimiter(api_name, config)
            return self._limiters[api_name]
    
    async def acquire(self, api_name: str) -> None:
        """Acquire permission for an API."""
        limiter = await self.get_limiter(api_name)
        await limiter.acquire()
    
    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """Get status for all rate limiters."""
        return {
            name: limiter.get_status()
            for name, limiter in self._limiters.items()
        }
