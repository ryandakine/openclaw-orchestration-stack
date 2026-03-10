"""Base adapter interface for all data sources.

This module defines the abstract base class that all adapters must implement,
along with shared data models and enums.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, AsyncIterator


class SourceType(Enum):
    """Types of data sources."""
    SPORTSBOOK = auto()
    PREDICTION_MARKET = auto()


class AdapterStatus(Enum):
    """Adapter operational status."""
    HEALTHY = auto()
    DEGRADED = auto()
    UNAVAILABLE = auto()
    DISABLED = auto()


@dataclass
class AdapterConfig:
    """Configuration for an adapter.
    
    Attributes:
        api_key: API key for authentication (if required)
        api_secret: API secret for authentication (if required)
        base_url: Custom base URL (optional)
        timeout_seconds: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        enable_caching: Whether to cache responses
        cache_ttl_seconds: Cache time-to-live in seconds
        rate_limit_requests_per_minute: Custom rate limit (optional)
        additional_headers: Additional HTTP headers to send
        verify_ssl: Whether to verify SSL certificates
    """
    api_key: str | None = None
    api_secret: str | None = None
    base_url: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 5
    enable_caching: bool = True
    cache_ttl_seconds: int = 60
    rate_limit_requests_per_minute: int | None = None
    additional_headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True


@dataclass
class Outcome:
    """A single betting outcome/option.
    
    Attributes:
        id: Unique identifier for this outcome
        name: Human-readable name (e.g., "Trump", "Lakers")
        price: Current price/probability (decimal: 0.0-1.0 for PM, odds for sportsbooks)
        implied_probability: Implied probability (0.0-1.0)
        volume: Trading volume if available
        liquidity: Available liquidity if available
        metadata: Additional source-specific data
    """
    id: str
    name: str
    price: float
    implied_probability: float
    volume: float | None = None
    liquidity: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketData:
    """Normalized market data from any source.
    
    Attributes:
        id: Unique market identifier from the source
        source: Source identifier (e.g., "polymarket", "draftkings")
        source_type: Type of data source
        title: Market/event title
        description: Market description
        category: Category (e.g., "politics", "sports", "crypto")
        market_type: Type of market (e.g., "binary", "moneyline", "spread")
        outcomes: List of possible outcomes
        start_time: When the event starts/resolves
        close_time: When betting closes
        is_active: Whether the market is currently active
        is_settled: Whether the market has been settled
        last_update: When the data was last updated
        url: Direct link to the market
        fees: Fee structure (e.g., {"maker": 0.0, "taker": 0.02})
        raw_data: Original source data
    """
    id: str
    source: str
    source_type: SourceType
    title: str
    description: str = ""
    category: str = ""
    market_type: str = ""
    outcomes: list[Outcome] = field(default_factory=list)
    start_time: datetime | None = None
    close_time: datetime | None = None
    is_active: bool = True
    is_settled: bool = False
    last_update: datetime | None = None
    url: str = ""
    fees: dict[str, float] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class AdapterHealth:
    """Health status of an adapter.
    
    Attributes:
        status: Current operational status
        last_successful_request: When the last successful request was made
        consecutive_failures: Number of consecutive failures
        average_response_time_ms: Average response time
        requests_in_last_minute: Request count for rate limiting
        error_message: Latest error message if unhealthy
    """
    status: AdapterStatus
    last_successful_request: datetime | None = None
    consecutive_failures: int = 0
    average_response_time_ms: float = 0.0
    requests_in_last_minute: int = 0
    error_message: str | None = None


class BaseAdapter(ABC):
    """Abstract base class for all data source adapters.
    
    All adapters must implement this interface to provide a consistent
    way to fetch and normalize data from different sources.
    
    Example:
        async with SomeAdapter(config) as adapter:
            markets = await adapter.fetch_markets(category="politics")
            async for market in adapter.iter_markets():
                process(market)
    """
    
    # Class attributes that subclasses must define
    name: str = ""  # Source identifier (e.g., "polymarket")
    source_type: SourceType = SourceType.PREDICTION_MARKET
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        """Initialize the adapter.
        
        Args:
            config: Adapter configuration
        """
        self.config = config or AdapterConfig()
        self._health = AdapterHealth(status=AdapterStatus.HEALTHY)
        self._initialized = False
    
    @property
    def health(self) -> AdapterHealth:
        """Get current health status."""
        return self._health
    
    @property
    def is_healthy(self) -> bool:
        """Check if adapter is healthy."""
        return self._health.status in (AdapterStatus.HEALTHY, AdapterStatus.DEGRADED)
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the adapter (authenticate, setup connections, etc.).
        
        This method is called automatically when using the adapter as
        an async context manager.
        """
        self._initialized = True
    
    @abstractmethod
    async def close(self) -> None:
        """Close the adapter and release resources."""
        self._initialized = False
    
    @abstractmethod
    async def fetch_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[MarketData]:
        """Fetch markets from the source.
        
        Args:
            category: Optional category filter
            active_only: Only return active markets
            limit: Maximum number of markets to return
            
        Returns:
            List of normalized market data
            
        Raises:
            AdapterError: If the request fails
        """
        pass
    
    @abstractmethod
    async def fetch_market(self, market_id: str) -> MarketData:
        """Fetch a specific market by ID.
        
        Args:
            market_id: Market identifier
            
        Returns:
            Normalized market data
            
        Raises:
            MarketNotFoundError: If market doesn't exist
            AdapterError: If the request fails
        """
        pass
    
    async def iter_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
    ) -> AsyncIterator[MarketData]:
        """Iterate through all markets (with pagination handled automatically).
        
        Args:
            category: Optional category filter
            active_only: Only return active markets
            
        Yields:
            MarketData objects
        """
        # Default implementation uses fetch_markets with pagination
        offset = 0
        limit = 100
        
        while True:
            markets = await self.fetch_markets(
                category=category,
                active_only=active_only,
                limit=limit,
            )
            
            if not markets:
                break
            
            for market in markets:
                yield market
            
            if len(markets) < limit:
                break
            
            offset += limit
    
    @abstractmethod
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MarketData]:
        """Search for markets by query string.
        
        Args:
            query: Search query
            category: Optional category filter
            limit: Maximum results
            
        Returns:
            List of matching markets
        """
        pass
    
    @abstractmethod
    def normalize_market(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw API data to MarketData format.
        
        Args:
            raw_data: Raw data from the source API
            
        Returns:
            Normalized MarketData
        """
        pass
    
    async def check_health(self) -> AdapterHealth:
        """Check and update the adapter's health status.
        
        Returns:
            Current health status
        """
        try:
            # Try a lightweight operation
            await self.search_markets("test", limit=1)
            self._health.status = AdapterStatus.HEALTHY
            self._health.consecutive_failures = 0
            self._health.last_successful_request = datetime.utcnow()
        except Exception as e:
            self._health.consecutive_failures += 1
            self._health.error_message = str(e)
            
            if self._health.consecutive_failures >= 5:
                self._health.status = AdapterStatus.UNAVAILABLE
            else:
                self._health.status = AdapterStatus.DEGRADED
        
        return self._health
    
    def _update_health_on_success(self, response_time_ms: float) -> None:
        """Update health metrics after a successful request."""
        self._health.last_successful_request = datetime.utcnow()
        self._health.consecutive_failures = 0
        self._health.status = AdapterStatus.HEALTHY
        
        # Update average response time (exponential moving average)
        alpha = 0.3
        self._health.average_response_time_ms = (
            alpha * response_time_ms +
            (1 - alpha) * self._health.average_response_time_ms
        )
        
        self._health.requests_in_last_minute += 1
    
    def _update_health_on_failure(self, error: Exception) -> None:
        """Update health metrics after a failed request."""
        self._health.consecutive_failures += 1
        self._health.error_message = str(error)
        
        if self._health.consecutive_failures >= 5:
            self._health.status = AdapterStatus.UNAVAILABLE
        elif self._health.consecutive_failures >= 2:
            self._health.status = AdapterStatus.DEGRADED
    
    async def __aenter__(self) -> BaseAdapter:
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


class AdapterError(Exception):
    """Base exception for adapter errors."""
    
    def __init__(
        self,
        message: str,
        adapter_name: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.adapter_name = adapter_name
        self.status_code = status_code


class MarketNotFoundError(AdapterError):
    """Raised when a market is not found."""
    pass


class RateLimitError(AdapterError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str,
        adapter_name: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, adapter_name)
        self.retry_after = retry_after


class AuthenticationError(AdapterError):
    """Raised when authentication fails."""
    pass
