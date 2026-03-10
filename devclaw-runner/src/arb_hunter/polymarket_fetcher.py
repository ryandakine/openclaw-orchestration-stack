"""Fetcher for Polymarket Gamma API data."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from .market_normalization_error import MarketNormalizationError

# API Configuration
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES = 3
RETRY_DELAY = 1.0
RATE_LIMIT_DELAY = 0.5  # Be nice to the API


class PolymarketFetcher:
    """Async fetcher for Polymarket market data."""

    def __init__(
        self,
        base_url: str = GAMMA_API_BASE,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Initialize the fetcher.

        Args:
            base_url: Gamma API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
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
    ) -> dict[str, Any]:
        """Make a rate-limited request with retries.

        Args:
            client: HTTPX async client
            endpoint: API endpoint (without base URL)
            params: Query parameters

        Returns:
            JSON response as dict

        Raises:
            MarketNormalizationError: If request fails after retries
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                await self._rate_limit()
                response = await client.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    # Server error, retry
                    wait_time = RETRY_DELAY * (2**attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise MarketNormalizationError(
                    f"HTTP error {e.response.status_code}: {e.response.text}",
                    source="polymarket",
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
            source="polymarket",
        )

    async def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch markets from Polymarket.

        Args:
            limit: Number of markets to fetch
            offset: Pagination offset
            active: Include active markets
            closed: Include closed markets
            category: Filter by category slug

        Returns:
            List of raw market data dicts
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        # Polymarket uses 'active' and 'closed' boolean params
        if active:
            params["active"] = "true"
        if closed:
            params["closed"] = "true"
        if category:
            params["category"] = category

        async with httpx.AsyncClient() as client:
            data = await self._make_request(client, "/markets", params)

        # Handle both list and dict (wrapped) responses
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Some endpoints return { "markets": [...] }
            if "markets" in data:
                return data["markets"]
            elif "data" in data:
                return data["data"]
            else:
                return [data]
        else:
            raise MarketNormalizationError(
                f"Unexpected response format: {type(data)}",
                source="polymarket",
            )

    async def get_market_by_id(self, market_id: str) -> dict[str, Any]:
        """Fetch a specific market by ID.

        Args:
            market_id: Polymarket market ID

        Returns:
            Raw market data dict
        """
        async with httpx.AsyncClient() as client:
            return await self._make_request(client, f"/markets/{market_id}")

    async def get_events(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
    ) -> list[dict[str, Any]]:
        """Fetch events from Polymarket.

        Events can contain multiple markets.

        Args:
            limit: Number of events to fetch
            offset: Pagination offset
            active: Only active events

        Returns:
            List of raw event data dicts
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if active:
            params["active"] = "true"

        async with httpx.AsyncClient() as client:
            data = await self._make_request(client, "/events", params)

        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            if "events" in data:
                return data["events"]
            elif "data" in data:
                return data["data"]
            else:
                return [data]
        else:
            raise MarketNormalizationError(
                f"Unexpected response format: {type(data)}",
                source="polymarket",
            )

    async def get_all_active_markets(
        self,
        batch_size: int = 100,
        max_markets: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all active markets with pagination.

        Args:
            batch_size: Markets per request
            max_markets: Maximum markets to fetch (None for all)

        Returns:
            List of all raw market data dicts
        """
        all_markets: list[dict[str, Any]] = []
        offset = 0

        while True:
            markets = await self.get_markets(
                limit=batch_size,
                offset=offset,
                active=True,
                closed=False,
            )

            if not markets:
                break

            all_markets.extend(markets)

            if max_markets and len(all_markets) >= max_markets:
                all_markets = all_markets[:max_markets]
                break

            if len(markets) < batch_size:
                break

            offset += batch_size

        return all_markets

    async def close(self) -> None:
        """Cleanup resources (placeholder for future use)."""
        pass

    async def __aenter__(self) -> PolymarketFetcher:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
