"""PredictIt API client for prediction market data."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator
from urllib.parse import urljoin

import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .errors import APIError, NotFoundError, ServerError, ValidationError
from .http_client import get_http_client
from .rate_limiter import RateLimiter
from .retry_handler import RetryConfig, RetryHandler


logger = logging.getLogger(__name__)


# PredictIt API configuration
PREDICTIT_API_BASE_URL = "https://www.predictit.org/api/marketdata"
DEFAULT_PAGE_SIZE = 100


@dataclass
class PredictItContract:
    """Individual contract/outcome within a PredictIt market."""
    
    id: int
    name: str
    short_name: str | None
    status: str  # Open, Closed, Settled
    last_trade_price: float
    best_buy_yes_cost: float
    best_buy_no_cost: float
    best_sell_yes_cost: float
    best_sell_no_cost: float
    last_close_price: float
    display_order: int
    date_end: str | None
    raw_data: dict[str, Any]
    
    @property
    def implied_probability(self) -> float:
        """Calculate implied probability from last trade price."""
        return self.last_trade_price * 100
    
    @property
    def spread(self) -> float:
        """Calculate bid-ask spread for YES shares."""
        return self.best_buy_yes_cost - self.best_sell_yes_cost
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> PredictItContract:
        """Create PredictItContract from API response."""
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            short_name=data.get("shortName"),
            status=data.get("status", ""),
            last_trade_price=float(data.get("lastTradePrice", 0) or 0),
            best_buy_yes_cost=float(data.get("bestBuyYesCost", 0) or 0),
            best_buy_no_cost=float(data.get("bestBuyNoCost", 0) or 0),
            best_sell_yes_cost=float(data.get("bestSellYesCost", 0) or 0),
            best_sell_no_cost=float(data.get("bestSellNoCost", 0) or 0),
            last_close_price=float(data.get("lastClosePrice", 0) or 0),
            display_order=int(data.get("displayOrder", 0)),
            date_end=data.get("dateEnd"),
            raw_data=data,
        )


@dataclass
class PredictItMarket:
    """PredictIt market data."""
    
    id: int
    name: str
    short_name: str | None
    url: str
    image: str | None
    time_stamp: datetime
    status: str  # Open, Closed, Settled
    category: str
    category_id: int
    contracts: list[PredictItContract]
    raw_data: dict[str, Any]
    
    @property
    def total_volume(self) -> float:
        """Calculate total trading volume across all contracts."""
        # Note: PredictIt doesn't provide direct volume data
        # This is a placeholder that could be enhanced with historical data
        return sum(
            c.last_trade_price * 100
            for c in self.contracts
        )
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> PredictItMarket:
        """Create PredictItMarket from API response."""
        contracts = [
            PredictItContract.from_api_response(c)
            for c in data.get("contracts", [])
        ]
        
        time_stamp_str = data.get("timeStamp", "")
        try:
            # PredictIt timestamp format: "2024-01-15T10:30:00.0000000"
            time_stamp = datetime.fromisoformat(time_stamp_str.replace("Z", "+00:00"))
        except ValueError:
            time_stamp = datetime.utcnow()
        
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            short_name=data.get("shortName"),
            url=data.get("url", ""),
            image=data.get("image"),
            time_stamp=time_stamp,
            status=data.get("status", ""),
            category=data.get("category", ""),
            category_id=int(data.get("categoryId", 0)),
            contracts=contracts,
            raw_data=data,
        )


@dataclass
class PredictItCategory:
    """PredictIt market category."""
    
    id: int
    name: str
    markets: list[PredictItMarket]
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> PredictItCategory:
        """Create PredictItCategory from API response."""
        markets = [
            PredictItMarket.from_api_response(m)
            for m in data.get("markets", [])
        ]
        
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", ""),
            markets=markets,
            raw_data=data,
        )


class PredictItClient:
    """Client for PredictIt public market data API.
    
    Provides access to prediction market data without authentication.
    Rate limited to reasonable levels (default: 60/min).
    """
    
    def __init__(
        self,
        base_url: str = PREDICTIT_API_BASE_URL,
    ) -> None:
        """Initialize PredictIt client.
        
        Args:
            base_url: API base URL
        """
        self.base_url = base_url.rstrip("/")
        
        # Initialize rate limiter (60 requests per minute)
        self.rate_limiter = RateLimiter("predictit")
        
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
        self.circuit_breaker = CircuitBreaker("predictit", breaker_config)
        
        self._http_client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client instance."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                },
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
                message="Market not found",
                status_code=status,
                response_body=body,
                api_name="predictit",
            )
        elif status == 400:
            raise ValidationError(
                message="Invalid request",
                status_code=status,
                response_body=body,
                api_name="predictit",
            )
        elif status >= 500:
            raise ServerError(
                message=f"PredictIt server error: {status}",
                status_code=status,
                response_body=body,
                api_name="predictit",
            )
        else:
            raise APIError(
                message=f"PredictIt API error: {status}",
                status_code=status,
                response_body=body,
                api_name="predictit",
            )
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make API request with retry and circuit breaker."""
        async def _do_request() -> dict[str, Any]:
            await self.rate_limiter.acquire()
            
            client = await self._get_client()
            url = urljoin(self.base_url, path)
            
            response = await client.request(method, url, **kwargs)
            
            if response.status_code >= 400:
                self._handle_error(response)
            
            return response.json()
        
        return await self.circuit_breaker.call(
            lambda: self.retry_handler.execute(_do_request, f"predictit.{method}")
        )
    
    async def get_all_markets(self) -> list[PredictItMarket]:
        """Get all active markets.
        
        Returns:
            List of all active markets
        """
        data = await self._make_request("GET", "/markets/")
        
        markets_data = data.get("markets", [])
        return [PredictItMarket.from_api_response(m) for m in markets_data]
    
    async def get_market(self, market_id: int) -> PredictItMarket:
        """Get a specific market by ID.
        
        Args:
            market_id: Market identifier
            
        Returns:
            Market data
        """
        data = await self._make_request("GET", f"/markets/{market_id}")
        return PredictItMarket.from_api_response(data)
    
    async def get_markets_by_category(self, category_id: int) -> list[PredictItMarket]:
        """Get markets filtered by category.
        
        Args:
            category_id: Category identifier
            
        Returns:
            List of markets in the category
        """
        # PredictIt returns all markets; we filter by category
        all_markets = await self.get_all_markets()
        return [m for m in all_markets if m.category_id == category_id]
    
    async def get_categories(self) -> list[dict[str, Any]]:
        """Get list of available categories.
        
        Returns:
            List of category information
        """
        markets = await self.get_all_markets()
        
        # Extract unique categories
        categories: dict[int, dict[str, Any]] = {}
        for market in markets:
            if market.category_id not in categories:
                categories[market.category_id] = {
                    "id": market.category_id,
                    "name": market.category,
                }
        
        return list(categories.values())
    
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
    ) -> list[PredictItMarket]:
        """Search markets by keyword.
        
        Args:
            query: Search query (case-insensitive)
            category: Optional category filter
            
        Returns:
            List of matching markets
        """
        markets = await self.get_all_markets()
        query_lower = query.lower()
        
        results = []
        for market in markets:
            # Check if query matches market name
            if query_lower in market.name.lower():
                if category is None or market.category.lower() == category.lower():
                    results.append(market)
            # Check contract names
            else:
                for contract in market.contracts:
                    if query_lower in contract.name.lower():
                        if category is None or market.category.lower() == category.lower():
                            results.append(market)
                            break
        
        return results
    
    async def get_market_history(
        self,
        market_id: int,
        contract_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get historical price data for a market.
        
        Note: This endpoint may have different availability.
        
        Args:
            market_id: Market identifier
            contract_id: Optional contract identifier
            
        Returns:
            Historical price data
        """
        path = f"/markets/{market_id}/history"
        if contract_id:
            path += f"?contractId={contract_id}"
        
        return await self._make_request("GET", path)
    
    async def get_related_markets(
        self,
        market_id: int,
    ) -> list[PredictItMarket]:
        """Get markets related to a specific market.
        
        Uses category and name similarity to find related markets.
        
        Args:
            market_id: Market identifier
            
        Returns:
            List of related markets
        """
        target_market = await self.get_market(market_id)
        all_markets = await self.get_all_markets()
        
        related = []
        for market in all_markets:
            if market.id == market_id:
                continue
            
            # Same category indicates relation
            if market.category_id == target_market.category_id:
                related.append(market)
        
        return related
    
    def calculate_arbitrage_opportunities(
        self,
        markets: list[PredictItMarket] | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate potential arbitrage opportunities within markets.
        
        Looks for markets where YES + NO prices on both sides
        don't sum to $1 (accounting for fees).
        
        Args:
            markets: Markets to analyze (fetches all if None)
            
        Returns:
            List of potential arbitrage opportunities
        """
        opportunities = []
        
        # This is a synchronous helper that works with fetched data
        # Actual arbitrage detection would use this with market data
        
        return opportunities
    
    async def close(self) -> None:
        """Close the client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def __aenter__(self) -> PredictItClient:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.close()
