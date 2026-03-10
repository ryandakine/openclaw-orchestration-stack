"""Kalshi API client for prediction market data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator
from urllib.parse import urljoin

import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .errors import APIError, AuthenticationError, NotFoundError, ServerError, ValidationError
from .http_client import get_http_client
from .rate_limiter import RateLimiter
from .retry_handler import RetryConfig, RetryHandler


logger = logging.getLogger(__name__)


# Kalshi API configuration
KALSHI_API_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


@dataclass
class KalshiMarket:
    """Kalshi market data."""
    
    ticker: str
    title: str
    description: str
    category: str
    status: str
    close_date: str | None
    settlement_date: str | None
    yes_bid: float
    yes_ask: float
    no_bid: float
    no_ask: float
    volume: int
    open_interest: int
    liquidity: float
    rules_primary: str
    rules_secondary: str | None
    raw_data: dict[str, Any]
    
    @property
    def yes_mid(self) -> float:
        """Calculate mid price for YES."""
        return (self.yes_bid + self.yes_ask) / 2
    
    @property
    def no_mid(self) -> float:
        """Calculate mid price for NO."""
        return (self.no_bid + self.no_ask) / 2
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> KalshiMarket:
        """Create KalshiMarket from API response."""
        market_data = data.get("market", data)
        
        return cls(
            ticker=market_data.get("ticker", ""),
            title=market_data.get("title", ""),
            description=market_data.get("description", ""),
            category=market_data.get("category", ""),
            status=market_data.get("status", ""),
            close_date=market_data.get("close_date"),
            settlement_date=market_data.get("settlement_date"),
            yes_bid=float(market_data.get("yes_bid", 0) or 0),
            yes_ask=float(market_data.get("yes_ask", 0) or 0),
            no_bid=float(market_data.get("no_bid", 0) or 0),
            no_ask=float(market_data.get("no_ask", 0) or 0),
            volume=int(market_data.get("volume", 0) or 0),
            open_interest=int(market_data.get("open_interest", 0) or 0),
            liquidity=float(market_data.get("liquidity", 0) or 0),
            rules_primary=market_data.get("rules_primary", ""),
            rules_secondary=market_data.get("rules_secondary"),
            raw_data=data,
        )


@dataclass
class KalshiEvent:
    """Kalshi event data (contains multiple markets)."""
    
    ticker: str
    title: str
    category: str
    status: str
    markets: list[KalshiMarket]
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> KalshiEvent:
        """Create KalshiEvent from API response."""
        event_data = data.get("event", data)
        markets_data = event_data.get("markets", [])
        markets = [
            KalshiMarket.from_api_response({"market": m})
            for m in markets_data
        ]
        
        return cls(
            ticker=event_data.get("ticker", ""),
            title=event_data.get("title", ""),
            category=event_data.get("category", ""),
            status=event_data.get("status", ""),
            markets=markets,
            raw_data=data,
        )


class KalshiClient:
    """Client for Kalshi Trading API.
    
    Supports both public endpoints and authenticated trading.
    Rate limited based on account tier (default: 100/min).
    """
    
    def __init__(
        self,
        base_url: str = KALSHI_API_BASE_URL,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> None:
        """Initialize Kalshi client."""
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self._authenticated = bool(api_key and api_secret)
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter("kalshi")
        
        # Initialize retry handler
        retry_config = RetryConfig(
            max_attempts=5,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=30.0,
        )
        self.retry_handler = RetryHandler(retry_config)
        
        # Initialize circuit breaker
        breaker_config = CircuitBreakerConfig(
            failure_threshold=5,
            cooldown_seconds=60.0,
        )
        self.circuit_breaker = CircuitBreaker("kalshi", breaker_config)
        
        self._http_client: httpx.AsyncClient | None = None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if client has authentication credentials."""
        return self._authenticated
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client instance."""
        if self._http_client is None or self._http_client.is_closed:
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            
            if self._authenticated:
                headers["KALSHI-API-KEY-ID"] = self.api_key or ""
            
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
        
        if status == 401:
            raise AuthenticationError(
                message="Invalid API credentials",
                status_code=status,
                response_body=body,
                api_name="kalshi",
            )
        elif status == 404:
            raise NotFoundError(
                message="Resource not found",
                status_code=status,
                response_body=body,
                api_name="kalshi",
            )
        elif status == 400:
            raise ValidationError(
                message="Invalid request",
                status_code=status,
                response_body=body,
                api_name="kalshi",
            )
        elif status >= 500:
            raise ServerError(
                message=f"Kalshi server error: {status}",
                status_code=status,
                response_body=body,
                api_name="kalshi",
            )
        else:
            raise APIError(
                message=f"Kalshi API error: {status}",
                status_code=status,
                response_body=body,
                api_name="kalshi",
            )
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make authenticated API request."""
        async def _do_request() -> dict[str, Any]:
            await self.rate_limiter.acquire()
            
            client = await self._get_client()
            url = urljoin(self.base_url, path)
            
            response = await client.request(method, url, **kwargs)
            
            if response.status_code >= 400:
                self._handle_error(response)
            
            return response.json()
        
        return await self.circuit_breaker.call(
            lambda: self.retry_handler.execute(_do_request, f"kalshi.{method}")
        )
    
    async def get_markets(
        self,
        status: str | None = None,
        category: str | None = None,
        series_ticker: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Get markets with optional filtering."""
        params: dict[str, Any] = {
            "limit": min(limit, MAX_PAGE_SIZE),
        }
        
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        
        return await self._make_request("GET", "/markets", params=params)
    
    async def iter_markets(
        self,
        status: str | None = None,
        category: str | None = None,
        max_pages: int | None = None,
    ) -> AsyncGenerator[KalshiMarket, None]:
        """Iterate through all markets with pagination."""
        cursor: str | None = None
        page = 0
        
        while max_pages is None or page < max_pages:
            response = await self.get_markets(
                status=status,
                category=category,
                cursor=cursor,
            )
            
            markets_data = response.get("markets", [])
            if not markets_data:
                break
            
            for market_data in markets_data:
                yield KalshiMarket.from_api_response({"market": market_data})
            
            cursor = response.get("cursor")
            if not cursor:
                break
            
            page += 1
    
    async def get_market(self, ticker: str) -> KalshiMarket:
        """Get a single market by ticker."""
        data = await self._make_request("GET", f"/markets/{ticker}")
        return KalshiMarket.from_api_response(data)
    
    async def get_events(
        self,
        status: str | None = None,
        category: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """Get events with optional filtering."""
        params: dict[str, Any] = {
            "limit": min(limit, MAX_PAGE_SIZE),
        }
        
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor
        
        return await self._make_request("GET", "/events", params=params)
    
    async def iter_events(
        self,
        status: str | None = None,
        category: str | None = None,
        max_pages: int | None = None,
    ) -> AsyncGenerator[KalshiEvent, None]:
        """Iterate through all events with pagination."""
        cursor: str | None = None
        page = 0
        
        while max_pages is None or page < max_pages:
            response = await self.get_events(
                status=status,
                category=category,
                cursor=cursor,
            )
            
            events_data = response.get("events", [])
            if not events_data:
                break
            
            for event_data in events_data:
                yield KalshiEvent.from_api_response({"event": event_data})
            
            cursor = response.get("cursor")
            if not cursor:
                break
            
            page += 1
    
    async def get_event(self, ticker: str) -> KalshiEvent:
        """Get a single event by ticker."""
        data = await self._make_request("GET", f"/events/{ticker}")
        return KalshiEvent.from_api_response(data)
    
    async def get_exchange_status(self) -> dict[str, Any]:
        """Get exchange status and maintenance information."""
        return await self._make_request("GET", "/exchange/status")
    
    async def close(self) -> None:
        """Close the client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def __aenter__(self) -> KalshiClient:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.close()
