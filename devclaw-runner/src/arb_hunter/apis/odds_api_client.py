"""The Odds API client for sports betting odds."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncGenerator
from urllib.parse import urljoin

import httpx

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .errors import APIError, AuthenticationError, NotFoundError, RateLimitError, ServerError, ValidationError
from .http_client import get_http_client
from .rate_limiter import RateLimiter
from .retry_handler import RetryConfig, RetryHandler


logger = logging.getLogger(__name__)


# The Odds API configuration
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_REGIONS = "us"
DEFAULT_MARKETS = "h2h"
DEFAULT_ODDS_FORMAT = "decimal"


@dataclass
class Sport:
    """Sports available for betting."""
    
    key: str
    group: str
    title: str
    description: str
    active: bool
    has_outrights: bool
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Sport:
        """Create Sport from API response."""
        return cls(
            key=data.get("key", ""),
            group=data.get("group", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            active=data.get("active", False),
            has_outrights=data.get("has_outrights", False),
            raw_data=data,
        )


@dataclass
class Outcome:
    """Betting outcome (team/player and price)."""
    
    name: str
    price: float
    point: float | None = None
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Outcome:
        """Create Outcome from API response."""
        return cls(
            name=data.get("name", ""),
            price=float(data.get("price", 0) or 0),
            point=data.get("point"),
        )


@dataclass
class Market:
    """Betting market with outcomes."""
    
    key: str
    last_update: datetime
    outcomes: list[Outcome]
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Market:
        """Create Market from API response."""
        outcomes = [
            Outcome.from_api_response(o)
            for o in data.get("outcomes", [])
        ]
        
        last_update_str = data.get("last_update", "")
        try:
            last_update = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
        except ValueError:
            last_update = datetime.utcnow()
        
        return cls(
            key=data.get("key", ""),
            last_update=last_update,
            outcomes=outcomes,
            raw_data=data,
        )


@dataclass
class Bookmaker:
    """Bookmaker/sportsbook data."""
    
    key: str
    title: str
    last_update: datetime
    markets: list[Market]
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> Bookmaker:
        """Create Bookmaker from API response."""
        markets = [
            Market.from_api_response(m)
            for m in data.get("markets", [])
        ]
        
        last_update_str = data.get("last_update", "")
        try:
            last_update = datetime.fromisoformat(last_update_str.replace("Z", "+00:00"))
        except ValueError:
            last_update = datetime.utcnow()
        
        return cls(
            key=data.get("key", ""),
            title=data.get("title", ""),
            last_update=last_update,
            markets=markets,
            raw_data=data,
        )


@dataclass
class OddsEvent:
    """Sports event with odds from multiple bookmakers."""
    
    id: str
    sport_key: str
    sport_title: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: list[Bookmaker]
    raw_data: dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OddsEvent:
        """Create OddsEvent from API response."""
        bookmakers = [
            Bookmaker.from_api_response(b)
            for b in data.get("bookmakers", [])
        ]
        
        commence_str = data.get("commence_time", "")
        try:
            commence_time = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
        except ValueError:
            commence_time = datetime.utcnow()
        
        return cls(
            id=data.get("id", ""),
            sport_key=data.get("sport_key", ""),
            sport_title=data.get("sport_title", ""),
            commence_time=commence_time,
            home_team=data.get("home_team", ""),
            away_team=data.get("away_team", ""),
            bookmakers=bookmakers,
            raw_data=data,
        )


class OddsAPIClient:
    """Client for The Odds API.
    
    Provides sports betting odds from multiple bookmakers.
    Rate limited to 500 requests per month on free tier.
    """
    
    def __init__(
        self,
        api_key: str,
        base_url: str = ODDS_API_BASE_URL,
    ) -> None:
        """Initialize Odds API client.
        
        Args:
            api_key: API key from the-odds-api.com
            base_url: API base URL
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        
        # Initialize rate limiter (500/month for free tier)
        self.rate_limiter = RateLimiter("odds_api")
        
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
        self.circuit_breaker = CircuitBreaker("odds_api", breaker_config)
        
        self._http_client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client instance."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
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
                message="Invalid API key",
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
        elif status == 429:
            # Get retry-after header if available
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message="Rate limit exceeded (500 requests/month)",
                retry_after=float(retry_after) if retry_after else None,
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
        elif status == 404:
            raise NotFoundError(
                message="Resource not found",
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
        elif status == 422:
            raise ValidationError(
                message="Invalid request parameters",
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
        elif status >= 500:
            raise ServerError(
                message=f"Odds API server error: {status}",
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
        else:
            raise APIError(
                message=f"Odds API error: {status}",
                status_code=status,
                response_body=body,
                api_name="odds_api",
            )
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any] | list[Any]:
        """Make authenticated API request."""
        async def _do_request() -> dict[str, Any] | list[Any]:
            await self.rate_limiter.acquire()
            
            # Add API key to params
            params = kwargs.pop("params", {})
            params["apiKey"] = self.api_key
            
            client = await self._get_client()
            url = urljoin(self.base_url, path)
            
            response = await client.request(
                method, url, params=params, **kwargs
            )
            
            if response.status_code >= 400:
                self._handle_error(response)
            
            return response.json()
        
        return await self.circuit_breaker.call(
            lambda: self.retry_handler.execute(_do_request, f"odds_api.{method}")
        )
    
    async def get_sports(self, all_sports: bool = False) -> list[Sport]:
        """Get available sports.
        
        Args:
            all_sports: Include inactive sports
            
        Returns:
            List of available sports
        """
        params: dict[str, Any] = {}
        if all_sports:
            params["all"] = "true"
        
        data = await self._make_request("GET", "/sports", params=params)
        
        if isinstance(data, list):
            return [Sport.from_api_response(s) for s in data]
        return []
    
    async def get_odds(
        self,
        sport: str,
        regions: str = DEFAULT_REGIONS,
        markets: str = DEFAULT_MARKETS,
        odds_format: str = DEFAULT_ODDS_FORMAT,
        date_format: str = "iso",
        commence_time_from: str | None = None,
        commence_time_to: str | None = None,
        bookmakers: str | None = None,
    ) -> list[OddsEvent]:
        """Get odds for a sport.
        
        Args:
            sport: Sport key (e.g., 'soccer_epl', 'basketball_nba')
            regions: Comma-separated region codes (us, uk, eu, au)
            markets: Comma-separated market types (h2h, spreads, totals)
            odds_format: decimal or american
            date_format: iso or unix
            commence_time_from: ISO 8601 timestamp
            commence_time_to: ISO 8601 timestamp
            bookmakers: Comma-separated bookmaker keys
            
        Returns:
            List of events with odds
        """
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        
        if commence_time_from:
            params["commenceTimeFrom"] = commence_time_from
        if commence_time_to:
            params["commenceTimeTo"] = commence_time_to
        if bookmakers:
            params["bookmakers"] = bookmakers
        
        data = await self._make_request(
            "GET", f"/sports/{sport}/odds", params=params
        )
        
        if isinstance(data, list):
            return [OddsEvent.from_api_response(e) for e in data]
        return []
    
    async def get_event_odds(
        self,
        sport: str,
        event_id: str,
        regions: str = DEFAULT_REGIONS,
        markets: str = DEFAULT_MARKETS,
        odds_format: str = DEFAULT_ODDS_FORMAT,
        date_format: str = "iso",
    ) -> OddsEvent:
        """Get odds for a specific event.
        
        Args:
            sport: Sport key
            event_id: Event identifier
            regions: Comma-separated region codes
            markets: Comma-separated market types
            odds_format: decimal or american
            date_format: iso or unix
            
        Returns:
            Event with odds from all bookmakers
        """
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        
        data = await self._make_request(
            "GET",
            f"/sports/{sport}/events/{event_id}/odds",
            params=params,
        )
        
        return OddsEvent.from_api_response(data)
    
    async def get_scores(
        self,
        sport: str,
        days_from: int | None = None,
        date_format: str = "iso",
    ) -> list[dict[str, Any]]:
        """Get scores for completed and in-progress events.
        
        Args:
            sport: Sport key
            days_from: Number of days in the past to include
            date_format: iso or unix
            
        Returns:
            List of events with scores
        """
        params: dict[str, Any] = {"dateFormat": date_format}
        
        if days_from is not None:
            params["daysFrom"] = days_from
        
        return await self._make_request(
            "GET", f"/sports/{sport}/scores", params=params
        )
    
    async def get_usage(self) -> dict[str, Any]:
        """Get API usage information from response headers.
        
        Note: This requires making a request and checking headers.
        
        Returns:
            Usage information dict
        """
        # Make a lightweight request to get headers
        try:
            await self.get_sports()
        except Exception:
            pass
        
        # Return rate limiter status as proxy
        return self.rate_limiter.get_status()
    
    async def close(self) -> None:
        """Close the client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def __aenter__(self) -> OddsAPIClient:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args) -> None:
        """Async context manager exit."""
        await self.close()
