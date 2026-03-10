"""Prediction market adapter for Polymarket, Kalshi, PredictIt.

This module provides adapters for prediction market platforms with
support for binary and multi-outcome markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from typing import Any

from .base import (
    BaseAdapter,
    AdapterConfig,
    AdapterHealth,
    AdapterStatus,
    MarketData,
    Outcome,
    SourceType,
    MarketNotFoundError,
    AdapterError,
    RateLimitError,
    AuthenticationError,
)


class PMOutcomeType(Enum):
    """Prediction market outcome types."""
    BINARY = auto()  # YES/NO
    MULTIPLE = auto()  # Multiple choice
    SCALAR = auto()  # Numerical range


class PMMarketStatus(Enum):
    """Prediction market statuses."""
    ACTIVE = "active"
    CLOSED = "closed"
    RESOLVED = "resolved"
    PAUSED = "paused"


@dataclass
class PMMarket:
    """Prediction market specific data.
    
    Attributes:
        outcome_type: Type of outcome (binary, multiple, scalar)
        volume: Total trading volume
        liquidity: Market liquidity
        resolution_source: Source for resolution
        resolution_time: Expected resolution time
    """
    outcome_type: PMOutcomeType
    volume: float
    liquidity: float
    resolution_source: str | None = None
    resolution_time: datetime | None = None


class PolymarketAdapter(BaseAdapter):
    """Adapter for Polymarket prediction market.
    
    Polymarket is a decentralized prediction market platform built on Polygon.
    It offers binary (YES/NO) markets on various topics including politics,
    crypto, sports, and current events.
    
    Example:
        config = AdapterConfig()  # No API key required for public data
        async with PolymarketAdapter(config) as adapter:
            markets = await adapter.fetch_markets(category="politics")
            for market in markets:
                print(f"{market.title}: {market.outcomes[0].price}")
    """
    
    name = "polymarket"
    source_type = SourceType.PREDICTION_MARKET
    
    # Category mappings
    CATEGORIES = {
        "politics": "Politics",
        "crypto": "Crypto",
        "sports": "Sports",
        "tech": "Tech",
        "entertainment": "Entertainment",
        "science": "Science",
        "business": "Business",
    }
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        """Initialize Polymarket adapter.
        
        Args:
            config: Adapter configuration (API key optional)
        """
        super().__init__(config)
        self._client = None
    
    async def initialize(self) -> None:
        """Initialize the Polymarket API client."""
        if self._initialized:
            return
        
        from ..apis.polymarket_client import PolymarketClient
        
        self._client = PolymarketClient(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        
        self._initialized = True
    
    async def close(self) -> None:
        """Close the adapter and release resources."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
    
    async def fetch_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[MarketData]:
        """Fetch markets from Polymarket.
        
        Args:
            category: Category filter (e.g., "politics", "crypto")
            active_only: Only return active markets
            limit: Maximum number of markets
            
        Returns:
            List of normalized market data
        """
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        # Map category if needed
        pm_category = self.CATEGORIES.get(category, category)
        
        markets = []
        count = 0
        
        async for event in self._client.iter_events(
            active=active_only if active_only else None,
            closed=not active_only if not active_only else None,
            category=pm_category,
        ):
            for market in event.markets:
                market_data = self._normalize_polymarket_market(market, event)
                markets.append(market_data)
                count += 1
                
                if limit and count >= limit:
                    return markets
        
        return markets
    
    async def fetch_market(self, market_id: str) -> MarketData:
        """Fetch a specific market by ID."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        try:
            market = await self._client.get_market(market_id)
            
            # Get parent event for context
            # Note: Polymarket API doesn't provide direct event lookup from market
            # so we construct minimal event data
            from ..apis.polymarket_client import Event
            event = Event(
                id="",
                slug="",
                title=market.question,
                description=market.description,
                markets=[market],
                active=market.active,
                closed=market.closed,
                end_date=market.end_date,
                liquidity=market.liquidity,
                volume=market.volume,
                category=market.category,
                icon=market.icon,
                raw_data={},
            )
            
            return self._normalize_polymarket_market(market, event)
            
        except Exception as e:
            raise MarketNotFoundError(
                f"Market {market_id} not found: {e}",
                adapter_name=self.name,
            ) from e
    
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MarketData]:
        """Search markets by query string."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        pm_markets = await self._client.search_markets(query, limit=limit)
        
        markets = []
        for pm_market in pm_markets:
            # Create minimal event for context
            from ..apis.polymarket_client import Event
            event = Event(
                id="",
                slug="",
                title=pm_market.question,
                description=pm_market.description,
                markets=[pm_market],
                active=pm_market.active,
                closed=pm_market.closed,
                end_date=pm_market.end_date,
                liquidity=pm_market.liquidity,
                volume=pm_market.volume,
                category=pm_market.category,
                icon=pm_market.icon,
                raw_data={},
            )
            
            market_data = self._normalize_polymarket_market(pm_market, event)
            markets.append(market_data)
        
        return markets
    
    def normalize_market(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw Polymarket data to MarketData format."""
        # Handle both raw API response and dataclass
        if "question" in raw_data:
            # Raw API response format
            market_id = str(raw_data.get("id", ""))
            outcomes_data = raw_data.get("outcomes", [])
            outcome_names = raw_data.get("outcomeNames", [])
            
            outcomes = []
            for i, (outcome, name) in enumerate(zip(outcomes_data, outcome_names)):
                price = float(outcome.get("price", 0)) if isinstance(outcome, dict) else float(outcome)
                outcomes.append(Outcome(
                    id=f"{market_id}:{i}",
                    name=name,
                    price=price,
                    implied_probability=price,
                ))
            
            return MarketData(
                id=market_id,
                source=self.name,
                source_type=SourceType.PREDICTION_MARKET,
                title=raw_data.get("question", ""),
                description=raw_data.get("description", ""),
                category=raw_data.get("category", ""),
                market_type="binary" if len(outcomes) == 2 else "multiple",
                outcomes=outcomes,
                start_time=datetime.fromisoformat(
                    raw_data.get("endDate", "").replace("Z", "+00:00")
                ) if raw_data.get("endDate") else None,
                is_active=raw_data.get("active", False),
                is_settled=raw_data.get("closed", False),
                url=f"https://polymarket.com/market/{raw_data.get('slug', '')}",
                fees={"maker": 0.0, "taker": 0.02},  # 2% taker fee
                raw_data=raw_data,
            )
        else:
            # Already normalized or partial
            return MarketData(
                id=raw_data.get("id", ""),
                source=self.name,
                source_type=SourceType.PREDICTION_MARKET,
                title=raw_data.get("title", ""),
                outcomes=[
                    Outcome(
                        id=str(i),
                        name=o.get("name", ""),
                        price=o.get("price", 0.0),
                        implied_probability=o.get("price", 0.0),
                    )
                    for i, o in enumerate(raw_data.get("outcomes", []))
                ],
                raw_data=raw_data,
            )
    
    def _normalize_polymarket_market(self, market, event) -> MarketData:
        """Normalize Polymarket Market and Event objects."""
        outcomes = []
        for i, (outcome_data, name) in enumerate(zip(market.outcomes, market.outcome_names)):
            price = float(outcome_data.get("price", 0)) if isinstance(outcome_data, dict) else float(outcome_data)
            outcomes.append(Outcome(
                id=f"{market.id}:{i}",
                name=name,
                price=price,
                implied_probability=price,
            ))
        
        return MarketData(
            id=str(market.id),
            source=self.name,
            source_type=SourceType.PREDICTION_MARKET,
            title=market.question,
            description=market.description,
            category=market.category or "",
            market_type="binary" if len(outcomes) == 2 else "multiple",
            outcomes=outcomes,
            start_time=datetime.fromisoformat(
                market.end_date.replace("Z", "+00:00")
            ) if market.end_date else None,
            is_active=market.active and not market.closed,
            is_settled=market.closed,
            last_update=datetime.utcnow(),
            url=f"https://polymarket.com/market/{market.slug}",
            fees={"maker": 0.0, "taker": 0.02},  # Standard Polymarket fees
            raw_data={
                "event": event.raw_data,
                "market": market.raw_data,
                "volume": market.volume,
                "liquidity": market.liquidity,
                "condition_id": market.condition_id,
            },
        )
    
    async def check_health(self) -> AdapterHealth:
        """Check Polymarket API health."""
        try:
            await self.search_markets("test", limit=1)
            self._health = AdapterHealth(
                status=AdapterStatus.HEALTHY,
                last_successful_request=datetime.utcnow(),
            )
        except Exception as e:
            self._health.status = AdapterStatus.UNAVAILABLE
            self._health.error_message = str(e)
        
        return self._health


class KalshiAdapter(BaseAdapter):
    """Adapter for Kalshi prediction market.
    
    Kalshi is a regulated prediction market exchange in the US.
    It offers binary (YES/NO) markets on various topics.
    
    Example:
        config = AdapterConfig(api_key="your_kalshi_key")
        async with KalshiAdapter(config) as adapter:
            markets = await adapter.fetch_markets(category="Economics")
    """
    
    name = "kalshi"
    source_type = SourceType.PREDICTION_MARKET
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        """Initialize Kalshi adapter.
        
        Args:
            config: Adapter configuration (API key recommended)
        """
        super().__init__(config)
        self._client = None
    
    async def initialize(self) -> None:
        """Initialize the Kalshi API client."""
        if self._initialized:
            return
        
        from ..apis.kalshi_client import KalshiClient
        
        self._client = KalshiClient(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        )
        
        self._initialized = True
    
    async def close(self) -> None:
        """Close the adapter and release resources."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
    
    async def fetch_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[MarketData]:
        """Fetch markets from Kalshi.
        
        Args:
            category: Category filter (e.g., "Economics", "Politics")
            active_only: Only return active markets
            limit: Maximum number of markets
            
        Returns:
            List of normalized market data
        """
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        status = "active" if active_only else None
        
        markets = []
        count = 0
        
        async for market in self._client.iter_markets(
            status=status,
            category=category,
        ):
            markets.append(self._normalize_kalshi_market(market))
            count += 1
            
            if limit and count >= limit:
                break
        
        return markets
    
    async def fetch_market(self, ticker: str) -> MarketData:
        """Fetch a specific market by ticker."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        try:
            market = await self._client.get_market(ticker)
            return self._normalize_kalshi_market(market)
        except Exception as e:
            raise MarketNotFoundError(
                f"Market {ticker} not found: {e}",
                adapter_name=self.name,
            ) from e
    
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MarketData]:
        """Search markets by query string."""
        # Kalshi doesn't have search API, so we fetch and filter
        all_markets = await self.fetch_markets(category=category, limit=500)
        
        query_lower = query.lower()
        results = []
        
        for market in all_markets:
            if query_lower in market.title.lower():
                results.append(market)
                if len(results) >= limit:
                    break
        
        return results
    
    def normalize_market(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw Kalshi data to MarketData format."""
        market_data = raw_data.get("market", raw_data)
        ticker = market_data.get("ticker", "")
        
        yes_price = (market_data.get("yes_bid", 0) + market_data.get("yes_ask", 100)) / 200
        no_price = (market_data.get("no_bid", 0) + market_data.get("no_ask", 100)) / 200
        
        return MarketData(
            id=ticker,
            source=self.name,
            source_type=SourceType.PREDICTION_MARKET,
            title=market_data.get("title", ""),
            description=market_data.get("description", ""),
            category=market_data.get("category", ""),
            market_type="binary",
            outcomes=[
                Outcome(
                    id=f"{ticker}:yes",
                    name="Yes",
                    price=yes_price,
                    implied_probability=yes_price,
                ),
                Outcome(
                    id=f"{ticker}:no",
                    name="No",
                    price=no_price,
                    implied_probability=no_price,
                ),
            ],
            close_time=datetime.fromisoformat(
                market_data.get("close_date", "").replace("Z", "+00:00")
            ) if market_data.get("close_date") else None,
            is_active=market_data.get("status") == "active",
            url=f"https://kalshi.com/markets/{ticker}",
            fees={"maker": 0.0, "taker": 0.05},  # 5% taker fee on settlement
            raw_data=raw_data,
        )
    
    def _normalize_kalshi_market(self, market) -> MarketData:
        """Normalize Kalshi Market dataclass."""
        yes_price = (market.yes_bid + market.yes_ask) / 200
        no_price = (market.no_bid + market.no_ask) / 200
        
        return MarketData(
            id=market.ticker,
            source=self.name,
            source_type=SourceType.PREDICTION_MARKET,
            title=market.title,
            description=market.description,
            category=market.category,
            market_type="binary",
            outcomes=[
                Outcome(
                    id=f"{market.ticker}:yes",
                    name="Yes",
                    price=yes_price,
                    implied_probability=yes_price,
                ),
                Outcome(
                    id=f"{market.ticker}:no",
                    name="No",
                    price=no_price,
                    implied_probability=no_price,
                ),
            ],
            close_time=datetime.fromisoformat(
                market.close_date.replace("Z", "+00:00")
            ) if market.close_date else None,
            is_active=market.status == "active",
            url=f"https://kalshi.com/markets/{market.ticker}",
            fees={"maker": 0.0, "taker": 0.05},
            raw_data={
                "volume": market.volume,
                "open_interest": market.open_interest,
                "liquidity": market.liquidity,
                "rules_primary": market.rules_primary,
            },
        )
    
    async def check_health(self) -> AdapterHealth:
        """Check Kalshi API health."""
        try:
            await self._client.get_exchange_status()
            self._health = AdapterHealth(
                status=AdapterStatus.HEALTHY,
                last_successful_request=datetime.utcnow(),
            )
        except Exception as e:
            self._health.status = AdapterStatus.UNAVAILABLE
            self._health.error_message = str(e)
        
        return self._health


class PredictItAdapter(BaseAdapter):
    """Adapter for PredictIt prediction market.
    
    PredictIt is a prediction market platform focused primarily on
    political events. It operates under a no-action letter from the CFTC.
    
    Example:
        config = AdapterConfig()  # No API key required
        async with PredictItAdapter(config) as adapter:
            markets = await adapter.fetch_markets(category="Politics")
    """
    
    name = "predictit"
    source_type = SourceType.PREDICTION_MARKET
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        """Initialize PredictIt adapter."""
        super().__init__(config)
        self._client = None
    
    async def initialize(self) -> None:
        """Initialize the PredictIt API client."""
        if self._initialized:
            return
        
        from ..apis.predictit_client import PredictItClient
        
        self._client = PredictItClient(
            base_url=self.config.base_url,
        )
        
        self._initialized = True
    
    async def close(self) -> None:
        """Close the adapter and release resources."""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
    
    async def fetch_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> list[MarketData]:
        """Fetch markets from PredictIt."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        all_markets = await self._client.get_all_markets()
        
        markets = []
        for pm_market in all_markets:
            if active_only and pm_market.status != "Open":
                continue
            
            if category and pm_market.category.lower() != category.lower():
                continue
            
            markets.append(self._normalize_predictit_market(pm_market))
            
            if limit and len(markets) >= limit:
                break
        
        return markets
    
    async def fetch_market(self, market_id: str) -> MarketData:
        """Fetch a specific market by ID."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        try:
            market = await self._client.get_market(int(market_id))
            return self._normalize_predictit_market(market)
        except Exception as e:
            raise MarketNotFoundError(
                f"Market {market_id} not found: {e}",
                adapter_name=self.name,
            ) from e
    
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MarketData]:
        """Search markets by query string."""
        if not self._client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        pm_markets = await self._client.search_markets(query, category)
        
        markets = []
        for pm_market in pm_markets[:limit]:
            markets.append(self._normalize_predictit_market(pm_market))
        
        return markets
    
    def normalize_market(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw PredictIt data to MarketData format."""
        market_id = str(raw_data.get("id", ""))
        contracts = raw_data.get("contracts", [])
        
        outcomes = []
        for contract in contracts:
            price = contract.get("lastTradePrice", 0)
            outcomes.append(Outcome(
                id=str(contract.get("id", "")),
                name=contract.get("name", ""),
                price=price,
                implied_probability=price,
            ))
        
        return MarketData(
            id=market_id,
            source=self.name,
            source_type=SourceType.PREDICTION_MARKET,
            title=raw_data.get("name", ""),
            description="",
            category=raw_data.get("category", ""),
            market_type="binary" if len(outcomes) == 2 else "multiple",
            outcomes=outcomes,
            is_active=raw_data.get("status") == "Open",
            url=raw_data.get("url", ""),
            fees={"commission": 0.10},  # 10% on profits
            raw_data=raw_data,
        )
    
    def _normalize_predictit_market(self, market) -> MarketData:
        """Normalize PredictIt Market dataclass."""
        outcomes = []
        for contract in market.contracts:
            outcomes.append(Outcome(
                id=str(contract.id),
                name=contract.name,
                price=contract.last_trade_price,
                implied_probability=contract.last_trade_price,
            ))
        
        return MarketData(
            id=str(market.id),
            source=self.name,
            source_type=SourceType.PREDICTION_MARKET,
            title=market.name,
            description="",
            category=market.category,
            market_type="binary" if len(outcomes) == 2 else "multiple",
            outcomes=outcomes,
            is_active=market.status == "Open",
            url=market.url,
            fees={"commission": 0.10},  # 10% on profits
            raw_data={
                "time_stamp": market.time_stamp.isoformat(),
                "contracts": [c.raw_data for c in market.contracts],
            },
        )
    
    async def check_health(self) -> AdapterHealth:
        """Check PredictIt API health."""
        try:
            await self._client.get_all_markets()
            self._health = AdapterHealth(
                status=AdapterStatus.HEALTHY,
                last_successful_request=datetime.utcnow(),
            )
        except Exception as e:
            self._health.status = AdapterStatus.UNAVAILABLE
            self._health.error_message = str(e)
        
        return self._health
