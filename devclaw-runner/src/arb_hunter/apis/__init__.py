"""OpenClaw Arbitrage Hunter - API Integration Module."""

from .http_client import HTTPClient, get_http_client
from .rate_limiter import RateLimiter, TokenBucket
from .retry_handler import RetryHandler, RetryConfig
from .circuit_breaker import CircuitBreaker, CircuitState
from .api_health_monitor import APIHealthMonitor, APIHealthStatus
from .errors import APIError, RateLimitError, TimeoutError, CircuitBreakerError, AuthenticationError
from .polymarket_client import PolymarketClient
from .kalshi_client import KalshiClient
from .odds_api_client import OddsAPIClient
from .predictit_client import PredictItClient

__all__ = [
    # HTTP Client
    "HTTPClient",
    "get_http_client",
    # Rate Limiting
    "RateLimiter",
    "TokenBucket",
    # Retry Handling
    "RetryHandler",
    "RetryConfig",
    # Circuit Breaker
    "CircuitBreaker",
    "CircuitState",
    # Health Monitor
    "APIHealthMonitor",
    "APIHealthStatus",
    # Errors
    "APIError",
    "RateLimitError",
    "TimeoutError",
    "CircuitBreakerError",
    "AuthenticationError",
    # Clients
    "PolymarketClient",
    "KalshiClient",
    "OddsAPIClient",
    "PredictItClient",
]
