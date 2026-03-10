"""Fetcher for The Odds API (DraftKings, FanDuel, Bet365, etc.)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from .market_normalization_error import MarketNormalizationError

# API Configuration
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0
RATE_LIMIT_DELAY = 0.2  # Odds API has stricter limits

# Supported sportsbooks
SUPPORTED_BOOKMAKERS = {
    "draftkings",
    "fanduel",
    "bet365",
    "betmgm",
    "caesars",
    "bovada",
    "pinnacle",
    "williamhill",
    "unibet",
    "pointsbetus",
}

# Sport keys
SPORT_KEYS = {
    "americanfootball_nfl": "NFL",
    "americanfootball_ncaaf": "NCAA Football",
    "basketball_nba": "NBA",
    "basketball_ncaab": "NCAA Basketball",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_epl": "Premier League",
    "soccer_usa_mls": "MLS",
    "mma_mixed_martial_arts": "MMA",
    "tennis_atp": "Tennis ATP",
    "tennis_wta": "Tennis WTA",
    "golf_pga": "PGA Golf",
}


class OddsAPIFetcher:
    """Async fetcher for The Odds API data."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = ODDS_API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize the fetcher.

        Args:
            api_key: The Odds API key (or from ODDS_API_KEY env var)
            base_url: API base URL
            timeout: Request timeout
            max_retries: Maximum retry attempts
        """
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise MarketNormalizationError(
                "Odds API key required. Set ODDS_API_KEY env var or pass api_key.",
                source="odds_api",
            )

        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        async with self._lock:
            import time

            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < RATE_LIMIT_DELAY:
                await asyncio.sleep(RATE_LIMIT_DELAY - elapsed)
            self._last_request_time = time.time()

    async def _make_request(
        self,
        client: httpx.AsyncClient,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Make a rate-limited request with retries.

        Args:
            client: HTTPX async client
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response

        Raises:
            MarketNormalizationError: If request fails
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        params = params or {}
        params["apiKey"] = self.api_key

        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                response = await client.get(url, params=params, timeout=self.timeout)

                # Handle specific status codes
                if response.status_code == 401:
                    raise MarketNormalizationError(
                        "Invalid API key",
                        source="odds_api",
                    )
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(response.headers.get("Retry-After", 10))
                    await asyncio.sleep(retry_after)
                    continue
                elif response.status_code == 422:
                    raise MarketNormalizationError(
                        f"Invalid parameters: {response.text}",
                        source="odds_api",
                    )

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    wait_time = RETRY_DELAY * (2**attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise MarketNormalizationError(
                    f"HTTP error {e.response.status_code}: {e.response.text}",
                    source="odds_api",
                ) from e

            except httpx.TimeoutException as e:
                last_error = e
                wait_time = RETRY_DELAY * (2**attempt)
                await asyncio.sleep(wait_time)
                continue

            except httpx.RequestError as e:
                last_error = e
                wait_time = RETRY_DELAY * (2**attempt)
                await asyncio.sleep(wait_time)
                continue

        raise MarketNormalizationError(
            f"Request failed after {self.max_retries} attempts: {last_error}",
            source="odds_api",
        )

    async def get_sports(
        self,
        all_sports: bool = False,
    ) -> list[dict[str, Any]]:
        """Get available sports.

        Args:
            all_sports: Include out-of-season sports

        Returns:
            List of sport dictionaries
        """
        params: dict[str, Any] = {}
        if all_sports:
            params["all"] = "true"

        async with httpx.AsyncClient() as client:
            result = await self._make_request(client, "/sports", params)

        if isinstance(result, list):
            return result
        return []

    async def get_odds(
        self,
        sport: str,
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "decimal",
        date_format: str = "iso",
        bookmakers: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get odds for a sport.

        Args:
            sport: Sport key (e.g., 'americanfootball_nfl')
            regions: Region code (us, uk, eu, au)
            markets: Market type (h2h, spreads, totals, outrights)
            odds_format: Odds format (decimal, american)
            date_format: Date format (iso, unix)
            bookmakers: Comma-separated list of bookmakers to filter

        Returns:
            List of event odds data
        """
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }

        if bookmakers:
            params["bookmakers"] = bookmakers

        async with httpx.AsyncClient() as client:
            return await self._make_request(  # type: ignore
                client, f"/sports/{sport}/odds", params
            )

    async def get_events(
        self,
        sport: str,
        date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get events for a sport (without odds).

        Args:
            sport: Sport key
            date: Optional date filter (ISO format)

        Returns:
            List of events
        """
        params: dict[str, Any] = {}
        if date:
            params["date"] = date

        async with httpx.AsyncClient() as client:
            return await self._make_request(  # type: ignore
                client, f"/sports/{sport}/events", params
            )

    async def get_event_odds(
        self,
        sport: str,
        event_id: str,
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "decimal",
        date_format: str = "iso",
    ) -> dict[str, Any]:
        """Get odds for a specific event.

        Args:
            sport: Sport key
            event_id: Event ID
            regions: Region code
            markets: Market type
            odds_format: Odds format
            date_format: Date format

        Returns:
            Event odds data
        """
        params: dict[str, Any] = {
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }

        async with httpx.AsyncClient() as client:
            return await self._make_request(  # type: ignore
                client, f"/sports/{sport}/events/{event_id}/odds", params
            )

    async def get_all_sports_odds(
        self,
        sports: list[str] | None = None,
        regions: str = "us",
        markets: str = "h2h",
        bookmakers: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get odds for multiple sports.

        Args:
            sports: List of sport keys (None for default set)
            regions: Region code
            markets: Market type
            bookmakers: Filter by bookmakers

        Returns:
            Dict mapping sport key to odds data
        """
        if sports is None:
            sports = list(SPORT_KEYS.keys())

        results: dict[str, list[dict[str, Any]]] = {}

        async with httpx.AsyncClient() as client:
            for sport in sports:
                try:
                    odds = await self.get_odds(
                        sport=sport,
                        regions=regions,
                        markets=markets,
                        bookmakers=bookmakers,
                    )
                    results[sport] = odds
                except MarketNormalizationError:
                    # Skip failed sports but continue
                    results[sport] = []

        return results

    def get_api_usage(self) -> dict[str, Any]:
        """Get API usage info from response headers (if available).

        Returns:
            Usage info dict
        """
        # This would need to be populated from actual responses
        # For now, return placeholder
        return {
            "requests_remaining": None,
            "requests_used": None,
        }

    async def close(self) -> None:
        """Cleanup resources."""
        pass

    async def __aenter__(self) -> OddsAPIFetcher:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
