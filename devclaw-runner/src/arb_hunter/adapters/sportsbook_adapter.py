"""Sportsbook adapter for traditional betting platforms.

This adapter integrates with The Odds API to fetch data from multiple
sportsbooks including DraftKings, FanDuel, Bet365, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
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
)


class OddsFormat(Enum):
    """Odds format options."""
    DECIMAL = "decimal"
    AMERICAN = "american"


class MarketType(Enum):
    """Common sportsbook market types."""
    MONEYLINE = "h2h"
    SPREADS = "spreads"
    TOTALS = "totals"
    OUTRIGHTS = "outrights"


@dataclass
class SportsbookMarket:
    """Sportsbook-specific market data.
    
    Attributes:
        bookmaker_key: Bookmaker identifier (e.g., "draftkings", "fanduel")
        bookmaker_title: Human-readable bookmaker name
        sport_key: Sport identifier (e.g., "basketball_nba")
        home_team: Home team name
        away_team: Away team name
        market_key: Market type key
    """
    bookmaker_key: str
    bookmaker_title: str
    sport_key: str
    home_team: str
    away_team: str
    market_key: str


class SportsbookAdapter(BaseAdapter):
    """Adapter for sportsbook data via The Odds API.
    
    This adapter fetches betting odds from multiple sportsbooks
    (DraftKings, FanDuel, Bet365, etc.) through The Odds API.
    
    Example:
        config = AdapterConfig(api_key="your_odds_api_key")
        async with SportsbookAdapter(config) as adapter:
            # Get all NBA moneyline markets
            markets = await adapter.fetch_markets(
                category="basketball_nba",
                market_type=MarketType.MONEYLINE
            )
    """
    
    name = "sportsbook"
    source_type = SourceType.SPORTSBOOK
    
    # Supported bookmakers
    SUPPORTED_BOOKMAKERS = {
        "draftkings": "DraftKings",
        "fanduel": "FanDuel",
        "bet365": "Bet365",
        "betmgm": "BetMGM",
        "caesars": "Caesars",
        "pointsbetus": "PointsBet",
        "wynnbet": "WynnBet",
        "betrivers": "BetRivers",
        "unibet": "Unibet",
        "williamhill_us": "William Hill",
    }
    
    # Sport key mappings
    SPORT_CATEGORIES = {
        "basketball_nba": "basketball",
        "basketball_ncaab": "basketball",
        "americanfootball_nfl": "football",
        "americanfootball_ncaaf": "football",
        "baseball_mlb": "baseball",
        "icehockey_nhl": "hockey",
        "soccer_epl": "soccer",
        "soccer_usa_mls": "soccer",
        "tennis_atp": "tennis",
        "tennis_wta": "tennis",
        "mma_ufc": "mma",
        "boxing": "boxing",
        "politics": "politics",
    }
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        """Initialize the sportsbook adapter.
        
        Args:
            config: Adapter configuration (must include API key)
        """
        super().__init__(config)
        self._odds_api_client = None
        self._selected_bookmakers: list[str] = []
        self._odds_format = OddsFormat.DECIMAL
    
    async def initialize(self) -> None:
        """Initialize the adapter with Odds API client."""
        if self._initialized:
            return
        
        # Import here to avoid circular dependencies
        from ..apis.odds_api_client import OddsAPIClient
        
        if not self.config.api_key:
            raise AuthenticationError(
                "Odds API key is required. Get one at https://the-odds-api.com",
                adapter_name=self.name,
            )
        
        self._odds_api_client = OddsAPIClient(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
        )
        
        self._initialized = True
    
    async def close(self) -> None:
        """Close the adapter and release resources."""
        if self._odds_api_client:
            await self._odds_api_client.close()
            self._odds_api_client = None
        self._initialized = False
    
    def set_bookmakers(self, bookmakers: list[str]) -> None:
        """Set which bookmakers to include in results.
        
        Args:
            bookmakers: List of bookmaker keys (e.g., ["draftkings", "fanduel"])
        """
        self._selected_bookmakers = [
            bm for bm in bookmakers
            if bm in self.SUPPORTED_BOOKMAKERS
        ]
    
    def set_odds_format(self, format: OddsFormat) -> None:
        """Set the odds format for results.
        
        Args:
            format: Odds format (decimal or american)
        """
        self._odds_format = format
    
    async def fetch_markets(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
        market_type: MarketType = MarketType.MONEYLINE,
    ) -> list[MarketData]:
        """Fetch markets from sportsbooks.
        
        Args:
            category: Sport key (e.g., "basketball_nba")
            active_only: Only return active markets
            limit: Maximum number of markets
            market_type: Type of betting market
            
        Returns:
            List of normalized market data
        """
        if not self._odds_api_client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        if not category:
            # Fetch all supported sports
            sports = await self._odds_api_client.get_sports(all_sports=not active_only)
            category = sports[0].key if sports else "basketball_nba"
        
        bookmakers = ",".join(self._selected_bookmakers) if self._selected_bookmakers else None
        
        events = await self._odds_api_client.get_odds(
            sport=category,
            markets=market_type.value,
            odds_format=self._odds_format.value,
            bookmakers=bookmakers,
        )
        
        markets = []
        for event in events:
            for market in self._convert_event_to_markets(event, category):
                markets.append(market)
                if limit and len(markets) >= limit:
                    return markets
        
        return markets
    
    async def fetch_market(self, market_id: str) -> MarketData:
        """Fetch a specific market by ID.
        
        Format: "{sport_key}:{event_id}:{bookmaker_key}:{market_key}"
        """
        if not self._odds_api_client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        try:
            parts = market_id.split(":")
            if len(parts) != 4:
                raise ValueError("Invalid market ID format")
            
            sport_key, event_id, bookmaker_key, market_key = parts
            
            event = await self._odds_api_client.get_event_odds(
                sport=sport_key,
                event_id=event_id,
                markets=market_key,
                odds_format=self._odds_format.value,
            )
            
            for market in self._convert_event_to_markets(event, sport_key):
                if market.id == market_id:
                    return market
            
            raise MarketNotFoundError(
                f"Market {market_id} not found",
                adapter_name=self.name,
            )
            
        except Exception as e:
            if isinstance(e, MarketNotFoundError):
                raise
            raise AdapterError(
                f"Failed to fetch market: {e}",
                adapter_name=self.name,
            ) from e
    
    async def search_markets(
        self,
        query: str,
        category: str | None = None,
        limit: int = 20,
    ) -> list[MarketData]:
        """Search markets by team name or event."""
        # The Odds API doesn't have search, so we fetch and filter
        all_markets = await self.fetch_markets(category=category, limit=200)
        
        query_lower = query.lower()
        results = []
        
        for market in all_markets:
            # Search in title and team names stored in metadata
            searchable_text = market.title.lower()
            if "home_team" in market.raw_data:
                searchable_text += " " + str(market.raw_data.get("home_team", "")).lower()
            if "away_team" in market.raw_data:
                searchable_text += " " + str(market.raw_data.get("away_team", "")).lower()
            
            if query_lower in searchable_text:
                results.append(market)
                if len(results) >= limit:
                    break
        
        return results
    
    def normalize_market(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw Odds API data to MarketData format."""
        # Handle different raw data formats
        if "bookmakers" in raw_data:
            # Full event data
            return self._normalize_event(raw_data)
        else:
            # Already normalized or partial data
            return MarketData(
                id=raw_data.get("id", ""),
                source=raw_data.get("source", self.name),
                source_type=SourceType.SPORTSBOOK,
                title=raw_data.get("title", ""),
                description=raw_data.get("description", ""),
                category=raw_data.get("category", ""),
                market_type=raw_data.get("market_type", ""),
                outcomes=[
                    Outcome(
                        id=str(i),
                        name=o.get("name", ""),
                        price=o.get("price", 0.0),
                        implied_probability=self._odds_to_probability(o.get("price", 0.0)),
                    )
                    for i, o in enumerate(raw_data.get("outcomes", []))
                ],
                is_active=raw_data.get("is_active", True),
                raw_data=raw_data,
            )
    
    def _convert_event_to_markets(
        self,
        event,
        sport_key: str,
    ) -> list[MarketData]:
        """Convert Odds API event to MarketData objects."""
        markets = []
        
        for bookmaker in event.bookmakers:
            for market in bookmaker.markets:
                market_id = f"{sport_key}:{event.id}:{bookmaker.key}:{market.key}"
                
                outcomes = [
                    Outcome(
                        id=f"{market_id}:{outcome.name}",
                        name=outcome.name,
                        price=outcome.price,
                        implied_probability=self._odds_to_probability(outcome.price),
                        point=outcome.point,
                    )
                    for outcome in market.outcomes
                ]
                
                market_data = MarketData(
                    id=market_id,
                    source=bookmaker.key,
                    source_type=SourceType.SPORTSBOOK,
                    title=f"{event.away_team} @ {event.home_team}",
                    description=f"{bookmaker.title} - {market.key}",
                    category=self.SPORT_CATEGORIES.get(sport_key, sport_key),
                    market_type=market.key,
                    outcomes=outcomes,
                    start_time=event.commence_time,
                    is_active=True,
                    is_settled=False,
                    last_update=market.last_update,
                    fees={"vig": self._calculate_vig(outcomes)},
                    raw_data={
                        "event_id": event.id,
                        "sport_key": sport_key,
                        "home_team": event.home_team,
                        "away_team": event.away_team,
                        "bookmaker": bookmaker.key,
                        "bookmaker_title": bookmaker.title,
                        "market_key": market.key,
                    },
                )
                markets.append(market_data)
        
        return markets
    
    def _normalize_event(self, raw_data: dict[str, Any]) -> MarketData:
        """Normalize raw event data to MarketData."""
        event_id = raw_data.get("id", "")
        sport_key = raw_data.get("sport_key", "")
        home_team = raw_data.get("home_team", "")
        away_team = raw_data.get("away_team", "")
        
        return MarketData(
            id=event_id,
            source=self.name,
            source_type=SourceType.SPORTSBOOK,
            title=f"{away_team} @ {home_team}",
            description=raw_data.get("description", ""),
            category=self.SPORT_CATEGORIES.get(sport_key, sport_key),
            market_type="event",
            start_time=datetime.fromisoformat(
                raw_data.get("commence_time", "").replace("Z", "+00:00")
            ) if raw_data.get("commence_time") else None,
            is_active=raw_data.get("active", True),
            raw_data=raw_data,
        )
    
    def _odds_to_probability(self, odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if odds <= 0:
            return 0.0
        return 1.0 / odds
    
    def _calculate_vig(self, outcomes: list[Outcome]) -> float:
        """Calculate vig from implied probabilities."""
        total_prob = sum(o.implied_probability for o in outcomes)
        return max(0, total_prob - 1.0)
    
    async def get_supported_sports(self) -> list[dict[str, str]]:
        """Get list of supported sports."""
        if not self._odds_api_client:
            raise AdapterError(
                "Adapter not initialized. Use async context manager.",
                adapter_name=self.name,
            )
        
        sports = await self._odds_api_client.get_sports()
        return [
            {
                "key": sport.key,
                "group": sport.group,
                "title": sport.title,
            }
            for sport in sports
        ]
    
    async def check_health(self) -> AdapterHealth:
        """Check adapter health by fetching sports list."""
        try:
            await self.get_supported_sports()
            self._health = AdapterHealth(
                status=AdapterStatus.HEALTHY,
                last_successful_request=datetime.utcnow(),
            )
        except Exception as e:
            self._health.status = AdapterStatus.UNAVAILABLE
            self._health.error_message = str(e)
        
        return self._health


class DraftKingsAdapter(SportsbookAdapter):
    """Dedicated adapter for DraftKings sportsbook."""
    
    name = "draftkings"
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        super().__init__(config)
        self.set_bookmakers(["draftkings"])


class FanDuelAdapter(SportsbookAdapter):
    """Dedicated adapter for FanDuel sportsbook."""
    
    name = "fanduel"
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        super().__init__(config)
        self.set_bookmakers(["fanduel"])


class Bet365Adapter(SportsbookAdapter):
    """Dedicated adapter for Bet365 sportsbook."""
    
    name = "bet365"
    
    def __init__(self, config: AdapterConfig | None = None) -> None:
        super().__init__(config)
        self.set_bookmakers(["bet365"])
