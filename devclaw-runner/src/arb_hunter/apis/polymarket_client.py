"""Polymarket Gamma API client with pagination support."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator
from urllib.parse import urljoin

import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .errors import APIError, NotFoundError, ServerError, ValidationError
from .http_client import get_http_client
from .rate_limiter import RateLimiter
from .retry_handler import RetryConfig, RetryHandler


logger = logging.getLogger(__name__)


# Polymarket Gamma API configuration
GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


@dataclass
class Market:
    """Polymarket market data."""
    
    id: str
    slug: str
    question: str
    description: str
    outcome_names: list[str]
    outcomes: list[dict[str, Any]]
    active: bool
    closed: bool
    closed_time: str | None
    end_date: str
    liquidity: float
    volume: float
    category: str | None
    icon: str | None
    image: str | None
    creator_address: str | None
    condition_id: str | None
    market_factory_address: str | None
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Market:
        """Create Market from API response."""
        return cls(
            id=str(data.get("id", "")),
            slug=data.get("slug", ""),
            question=data.get("question", ""),
            description=data.get("description", ""),
            outcome_names=data.get("outcomeNames", []),
            outcomes=data.get("outcomes", []),
            active=data.get("active", False),
            closed=data.get("closed", False),
            closed_time=data.get("closedTime"),
            end_date=data.get("endDate", ""),
            liquidity=float(data.get("liquidity", 0) or 0),
            volume=float(data.get("volume", 0) or 0),
            category=data.get("category"),
            icon=data.get("icon"),
            image=data.get("image"),
            creator_address=data.get("creatorAddress"),
            condition_id=data.get("conditionId"),
            market_factory_address=data.get("marketFactoryAddress"),
            raw_data=data,
        )


@dataclass
class Event:
    """Polymarket event data (contains multiple markets)."""
    
    id: str
    slug: str
    title: str
    description: str
    markets: list[Market]
    active: bool
    closed: bool
    end_date: str
    liquidity: float
    volume: float
    category: str | None
    icon: str | None
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Event:
        """Create Event from API response."""
        markets_data = data.get("markets", [])
        markets = [Market.from_api_response(m) for m in markets_data]
        
        return cls(
            id=str(data.get("id", "")),
            slug=data.get("slug", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            markets=markets,
            active=data.get("active", False),
            closed=data.get("closed", False),
            end_date=data.get("endDate", ""),
            liquidity=float(data.get("liquidity", 0) or 0),
            volume=float(data.get("volume", 0) or 0),
            category=data.get("category"),
            icon=data.get("icon"),
            raw_data=data,
        )


class PolymarketClient:
    """Client for Polymarket Gamma API.
    
    Supports market and event retrieval with pagination.
    Rate limited to 100 requests per minute by default.
    """
    
    def __init__(
        self,
        base_url: str = GAMMA_API_BASE_URL,
        api_key: str | None = None,
    ) -> None:
        """Initialize Polymarket client.
        
        Args:
            base_url: API base URL
            api_key: Optional API key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        
        # Initialize rate limiter (100 requests per minute)
        self.rate_limiter = RateLimiter("polymarket")
        
        # Initialize retry handler with exponential backoff
        retry_config = RetryConfig(
            max_attempts=5,
            base_delay=1.0,
            backoff_factor=2.0,  # 1s, 2s, 4s, 8s, 16s
            max_delay=30.0,
        )
        self.retry_handler = RetryHandler(retry_config)
        
        # Initialize circuit breaker
        breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            cooldown_seconds=60.0,
        )
        self.circuit_breaker = CircuitBreaker("polymarket", breaker_config)
        
        self._http_client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client instance."""
        if self._http_client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            http_client = await get_http_client()
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=30.0,
            )
        return self._http_client
    
    def _handle_error(self, response: httpx.Response) -> None:
        """Handle API error responses."""
        status = response.status_code
        
        try:
            body = response.json()
        except Exception:
            body = response.text
        
        if status == 404:
            raise NotFoundError(
                message="Resource not found",
                status_code=status,
                response_body=body,
                api_name="polymarket",
            )
        elif status == 400:
            raise ValidationError(
                message="Invalid request",
                status_code=status,
                response_body=body,
                api_name="polymarket",
            )
        elif status >= 500:
            raise ServerError(
                message=f"Polymarket server error: {status}",
                status_code=status,
                response_body=body,
                api_name="polymarket",
            )
        else:
            raise APIError(
                message=f"Polymarket API error: {status}",
                status_code=status,
                response_body=body,
                api_name="polymarket",
            )
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make authenticated API request with retry and circuit breaker."""
        async def _do_request() -> dict[str, Any]:
            # Acquire rate limit
            await self.rate_limiter.acquire()
            
            client = await self._get_client()
            url = urljoin(self.base_url, path)
            
            response = await client.request(method, url, **kwargs)
            
            if response.status_code >= 400:
                self._handle_error(response)
            
            return response.json()
        
        # Execute with circuit breaker and retry
        return await self.circuit_breaker.call(
            lambda: self.retry_handler.execute(_do_request, f"polymarket.{method}")
        )
    
    async def get_market(self, market_id: str) -> Market:
        """Get a single market by ID.
        
        Args:
            market_id: Market identifier
            
        Returns:
            Market data
        """
        data = await self._make_request("GET", f"/markets/{market_id}")
        return Market.from_api_response(data)
    
    async def get_markets(
        self,
        active: bool | None = None,
        closed: bool | None = None,
        category: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Market]:
        """Get markets with optional filtering.
        
        Args:
            active: Filter by active status
            closed: Filter by closed status
            category: Filter by category
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of markets
        """
        params: dict[str, Any] = {
            "limit": min(limit, MAX_PAGE_SIZE),
            "offset": offset,
        }
        
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if category:
            params["category"] = category
        
        data = await self._make_request("GET", "/markets", params=params)
        
        if isinstance(data, list):
            return [Market.from_api_response(item) for item in data]
        elif isinstance(data, dict) and "markets" in data:
            return [Market.from_api_response(item) for item in data["markets"]]
        else:
            return []
    
    async def iter_markets(
        self,
        active: bool | None = None,
        closed: bool | None = None,
        category: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> AsyncGenerator[Market, None]:
        """Iterate through all markets with automatic pagination.
        
        Args:
            active: Filter by active status
            closed: Filter by closed status
            category: Filter by category
            page_size: Number of results per page
            max_pages: Maximum pages to fetch (None for all)
            
        Yields:
            Market objects
        """
        offset = 0
        page = 0
        
        while max_pages is None or page < max_pages:
            markets = await self.get_markets(
                active=active,
                closed=closed,
                category=category,
                limit=page_size,
                offset=offset,
            )
            
            if not markets:
                break
            
            for market in markets:
                yield market
            
            offset += len(markets)
            page += 1
            
            # Check if we got fewer results than requested (last page)
            if len(markets) < page_size:
                break
    
    async def get_event(self, event_id: str) -> Event:
        """Get a single event by ID.
        
        Args:
            event_id: Event identifier
            
        Returns:
            Event data
        """
        data = await self._make_request("GET", f"/events/{event_id}")
        return Event.from_api_response(data)
    
    async def get_events(
        self,
        active: bool | None = None,
        closed: bool | None = None,
        category: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> list[Event]:
        """Get events with optional filtering.
        
        Args:
            active: Filter by active status
            closed: Filter by closed status
            category: Filter by category
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of events
        """
        params: dict[str, Any] = {
            "limit": min(limit, MAX_PAGE_SIZE),
            "offset": offset,
        }
        
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if category:
            params["category"] = category
        
        data = await self._make_request("GET", "/events", params=params)
        
        if isinstance(data, list):
            return [Event.from_api_response(item) for item in data]
        elif isinstance(data, dict) and "events" in data:
            return [Event.from_api_response(item) for item in data["events"]]
        else:
            return []
    
    async def iter_events(
        self,
        active: bool | None = None,
        closed: bool | None = None,
        category: str | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int | None = None,
    ) -> AsyncGenerator[Event, None]:
        """Iterate through all events with automatic pagination.
        
        Args:
            active: Filter by active status
            closed: Filter by closed status
            category: Filter by category
            page_size: Number of results per page
            max_pages: Maximum pages to fetch (None for all)
            
        Yields:
            Event objects
        """
        offset = 0
        page = 0
        
        while max_pages is None or page < max_pages:
            events = await self.get_events(
                active=active,
                closed=closed,
                category=category,
                limit=page_size,
                offset=offset,
            )
            
            if not events:
                break
            
            for event in events:
                yield event
            
            offset += len(events)
            page += 1
            
            if len(events) < page_size:
                break
    
    async def search_markets(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Market]:
        """Search markets by query string.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching markets
        """
        params = {
            "query": query,
            "limit": limit,
        }
        
        data = await self._make_request("GET", "/search", params=params)
        
        if isinstance(data, list):
            return [Market.from_api_response(item) for item in data]
        elif isinstance(data, dict):
            markets = data.get("markets", [])
            return [Market.from_api_response(m) for m in markets]
        return []
    
    async def get_market_order_book(
        self,
        condition_id: str,
    ) -> dict[str, Any]:
        """Get order book for a market.
        
        Args:
            condition_id: Market condition ID
            
        Returns:
            Order book data
        """
        return await self._make_request(
            "GET",
            f"/order-books/{condition_id}",
        )
    
    async def close(self) -> None:
        """Close the client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def __aenter__(self) -> PolymarketClient:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.close()
