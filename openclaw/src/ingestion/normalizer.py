"""
Data normalizer for sportsbook and prediction market data.

Converts raw data from various sources into a common normalized format.
"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class NormalizedOutcome:
    """Normalized outcome structure."""
    name: str
    odds: float  # Decimal odds (e.g., 1.85 for -118 American)
    source: str
    probability: Optional[float] = None  # For prediction markets (0-1)
    price: Optional[float] = None  # Raw price from source
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "odds": self.odds,
            "source": self.source,
            "probability": self.probability,
            "price": self.price,
            "liquidity": self.liquidity,
            "volume": self.volume,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedOutcome":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            odds=data["odds"],
            source=data["source"],
            probability=data.get("probability"),
            price=data.get("price"),
            liquidity=data.get("liquidity"),
            volume=data.get("volume"),
            metadata=data.get("metadata"),
        )


@dataclass
class NormalizedEvent:
    """
    Standardized event format for arbitrage detection.
    
    This is the common format that all data sources are converted to.
    """
    event_id: str
    sport: str
    teams: List[str]
    start_time: str  # ISO8601
    market_type: str  # moneyline, spread, total, binary
    outcomes: List[NormalizedOutcome]
    source: str
    timestamp: str  # ISO8601 when data was fetched
    
    # Optional fields
    title: Optional[str] = None
    category: Optional[str] = None
    source_event_id: Optional[str] = None
    url: Optional[str] = None
    is_live: bool = False
    spread: Optional[float] = None  # For spread markets
    total: Optional[float] = None  # For total markets
    liquidity: Optional[float] = None
    volume: Optional[float] = None
    freshness_seconds: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "teams": self.teams,
            "start_time": self.start_time,
            "market_type": self.market_type,
            "outcomes": [o.to_dict() for o in self.outcomes],
            "source": self.source,
            "timestamp": self.timestamp,
            "title": self.title,
            "category": self.category,
            "source_event_id": self.source_event_id,
            "url": self.url,
            "is_live": self.is_live,
            "spread": self.spread,
            "total": self.total,
            "liquidity": self.liquidity,
            "volume": self.volume,
            "freshness_seconds": self.freshness_seconds,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NormalizedEvent":
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            sport=data["sport"],
            teams=data["teams"],
            start_time=data["start_time"],
            market_type=data["market_type"],
            outcomes=[NormalizedOutcome.from_dict(o) for o in data["outcomes"]],
            source=data["source"],
            timestamp=data["timestamp"],
            title=data.get("title"),
            category=data.get("category"),
            source_event_id=data.get("source_event_id"),
            url=data.get("url"),
            is_live=data.get("is_live", False),
            spread=data.get("spread"),
            total=data.get("total"),
            liquidity=data.get("liquidity"),
            volume=data.get("volume"),
            freshness_seconds=data.get("freshness_seconds"),
            metadata=data.get("metadata"),
        )
    
    def get_best_outcome_odds(self, outcome_name: str) -> Optional[float]:
        """Get the best odds for a specific outcome."""
        for outcome in self.outcomes:
            if outcome.name.lower() == outcome_name.lower():
                return outcome.odds
        return None
    
    def to_database_event(self) -> Dict[str, Any]:
        """Convert to format suitable for database insertion."""
        return {
            "event_id": self.event_id,
            "sport": self.sport,
            "teams": json.dumps(self.teams),
            "start_time": self.start_time,
            "market_type": self.market_type,
            "source": self.source,
            "source_event_id": self.source_event_id or self.event_id,
            "title": self.title or f"{self.teams[0]} vs {self.teams[1]}" if len(self.teams) >= 2 else "Unknown",
            "category": self.category or self.sport,
            "status": "upcoming",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }
    
    def to_database_odds(self) -> Dict[str, Any]:
        """Convert to format suitable for odds table insertion."""
        return {
            "event_id": self.event_id,
            "market_type": self.market_type,
            "outcomes": json.dumps([o.to_dict() for o in self.outcomes]),
            "source": self.source,
            "source_type": "sportsbook" if self.market_type in ("moneyline", "spread", "total") else "prediction_market",
            "timestamp": self.timestamp,
            "url": self.url,
            "liquidity": self.liquidity,
            "volume": self.volume,
            "spread": self.spread,
            "total": self.total,
            "is_live": self.is_live,
            "freshness_seconds": self.freshness_seconds,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }


class DataNormalizer:
    """
    Normalizes data from various sources into the common format.
    
    Supports:
    - The Odds API (sportsbooks)
    - Polymarket
    - Kalshi
    - Mock/test data
    """
    
    # Sport name mappings
    SPORT_MAPPINGS = {
        "basketball_nba": "NBA",
        "americanfootball_nfl": "NFL",
        "baseball_mlb": "MLB",
        "icehockey_nhl": "NHL",
        "soccer_epl": "EPL",
        "mma_mixed_martial_arts": "UFC",
        "basketball_ncaa": "NCAA_BASKETBALL",
        "americanfootball_ncaaf": "NCAA_FOOTBALL",
    }
    
    def __init__(self):
        self._normalizers = {
            "the_odds_api": self._normalize_odds_api_event,
            "polymarket": self._normalize_polymarket_market,
            "kalshi": self._normalize_kalshi_market,
            "mock_sportsbook": self._normalize_odds_api_event,  # Same format
            "mock_prediction_market": self._normalize_polymarket_market,  # Same format
        }
    
    def normalize(
        self,
        raw_data: Union[Dict[str, Any], List[Dict[str, Any]]],
        source: Optional[str] = None
    ) -> List[NormalizedEvent]:
        """
        Normalize raw data from a source.
        
        Args:
            raw_data: Raw API response data
            source: Source identifier (auto-detected if not provided)
            
        Returns:
            List of normalized events
        """
        if isinstance(raw_data, dict):
            raw_data = [raw_data]
        
        normalized = []
        
        for item in raw_data:
            # Auto-detect source if not provided
            item_source = source or item.get("_source", "unknown")
            
            normalizer = self._normalizers.get(item_source)
            if normalizer:
                try:
                    result = normalizer(item)
                    if isinstance(result, list):
                        normalized.extend(result)
                    else:
                        normalized.append(result)
                except Exception as e:
                    logger.error(f"Failed to normalize item from {item_source}: {e}")
            else:
                logger.warning(f"No normalizer found for source: {item_source}")
        
        return normalized
    
    def _get_sport(self, sport_key: str) -> str:
        """Map sport key to standardized sport name."""
        return self.SPORT_MAPPINGS.get(sport_key, sport_key.upper())
    
    def _american_to_decimal(self, american_odds: Union[int, float]) -> float:
        """
        Convert American odds to decimal odds.
        
        Args:
            american_odds: American odds (e.g., -110, +150)
            
        Returns:
            Decimal odds (e.g., 1.91, 2.50)
        """
        if american_odds >= 0:
            return round((american_odds / 100) + 1, 2)
        else:
            return round((100 / abs(american_odds)) + 1, 2)
    
    def _probability_to_decimal(self, probability: float) -> float:
        """
        Convert probability (0-1) to decimal odds.
        
        Args:
            probability: Probability between 0 and 1
            
        Returns:
            Decimal odds
        """
        if probability <= 0 or probability >= 1:
            return 1.0
        return round(1 / probability, 2)
    
    def _normalize_odds_api_event(
        self,
        raw_event: Dict[str, Any]
    ) -> List[NormalizedEvent]:
        """
        Normalize an event from The Odds API.
        
        Each event may have multiple bookmakers, each with multiple markets.
        Returns one NormalizedEvent per bookmaker/market combination.
        """
        normalized_events = []
        
        event_id = raw_event.get("id", str(uuid.uuid4()))
        sport = self._get_sport(raw_event.get("sport_key", ""))
        home_team = raw_event.get("home_team", "")
        away_team = raw_event.get("away_team", "")
        start_time = raw_event.get("commence_time", datetime.utcnow().isoformat())
        fetched_at = raw_event.get("_fetched_at", datetime.utcnow().isoformat())
        
        bookmakers = raw_event.get("bookmakers", [])
        
        for bookmaker in bookmakers:
            bookmaker_name = bookmaker.get("title", "Unknown")
            markets = bookmaker.get("markets", [])
            
            for market in markets:
                market_key = market.get("key", "h2h")
                outcomes = market.get("outcomes", [])
                
                # Map market types
                if market_key == "h2h":
                    market_type = "moneyline"
                elif market_key == "spreads":
                    market_type = "spread"
                elif market_key == "totals":
                    market_type = "total"
                else:
                    market_type = market_key
                
                # Build normalized outcomes
                normalized_outcomes = []
                spread = None
                total = None
                
                for outcome in outcomes:
                    price = outcome.get("price", 0)
                    
                    # Convert American odds to decimal if needed
                    if isinstance(price, (int, float)) and price > 10:
                        price = self._american_to_decimal(price)
                    
                    normalized_outcome = NormalizedOutcome(
                        name=outcome.get("name", ""),
                        odds=round(price, 2) if price else 0,
                        source=bookmaker_name,
                        price=outcome.get("price"),
                    )
                    normalized_outcomes.append(normalized_outcome)
                    
                    # Extract spread/total if present
                    if "point" in outcome:
                        if market_type == "spread":
                            spread = outcome["point"]
                        elif market_type == "total":
                            total = outcome["point"]
                
                # Create normalized event
                norm_event = NormalizedEvent(
                    event_id=f"{event_id}_{bookmaker_name.lower().replace(' ', '_')}_{market_type}",
                    sport=sport,
                    teams=[home_team, away_team],
                    start_time=start_time,
                    market_type=market_type,
                    outcomes=normalized_outcomes,
                    source=bookmaker_name,
                    timestamp=fetched_at,
                    title=f"{away_team} @ {home_team}",
                    source_event_id=event_id,
                    url=bookmaker.get("url"),
                    spread=spread,
                    total=total,
                )
                
                normalized_events.append(norm_event)
        
        return normalized_events
    
    def _normalize_polymarket_market(
        self,
        raw_market: Dict[str, Any]
    ) -> NormalizedEvent:
        """
        Normalize a market from Polymarket.
        """
        market_id = raw_market.get("id") or raw_market.get("market_id", str(uuid.uuid4()))
        title = raw_market.get("title", "")
        category = raw_market.get("category", "Unknown")
        
        # Extract teams/participants from title if possible
        teams = self._extract_teams_from_title(title)
        
        # Normalize outcomes
        raw_outcomes = raw_market.get("outcomes", [])
        normalized_outcomes = []
        
        for outcome in raw_outcomes:
            prob = outcome.get("probability") or outcome.get("price", 0)
            normalized_outcome = NormalizedOutcome(
                name=outcome.get("name", ""),
                odds=self._probability_to_decimal(prob),
                source="Polymarket",
                probability=prob,
                price=outcome.get("price"),
                liquidity=raw_market.get("liquidity"),
                volume=raw_market.get("volume"),
            )
            normalized_outcomes.append(normalized_outcome)
        
        return NormalizedEvent(
            event_id=market_id,
            sport=category,  # Polymarket uses categories like sports, politics
            teams=teams if teams else ["YES", "NO"],
            start_time=raw_market.get("resolution_time", datetime.utcnow().isoformat()),
            market_type="binary",
            outcomes=normalized_outcomes,
            source="Polymarket",
            timestamp=raw_market.get("_fetched_at", datetime.utcnow().isoformat()),
            title=title,
            category=category,
            source_event_id=market_id,
            url=raw_market.get("url"),
            liquidity=raw_market.get("liquidity"),
            volume=raw_market.get("volume"),
            metadata={
                "description": raw_market.get("description"),
                "traders": raw_market.get("traders"),
                "volume_24h": raw_market.get("volume_24h"),
            },
        )
    
    def _normalize_kalshi_market(
        self,
        raw_market: Dict[str, Any]
    ) -> NormalizedEvent:
        """
        Normalize a market from Kalshi.
        """
        market_id = raw_market.get("id") or raw_market.get("market_id", str(uuid.uuid4()))
        title = raw_market.get("title", "")
        category = raw_market.get("category", "Unknown")
        
        # Extract teams/participants
        teams = self._extract_teams_from_title(title)
        
        # Kalshi markets are typically YES/NO
        yes_price = raw_market.get("yes_price", 0.5)
        no_price = raw_market.get("no_price", 0.5) or (1 - yes_price)
        
        normalized_outcomes = [
            NormalizedOutcome(
                name="YES",
                odds=self._probability_to_decimal(yes_price),
                source="Kalshi",
                probability=yes_price,
                price=yes_price,
            ),
            NormalizedOutcome(
                name="NO",
                odds=self._probability_to_decimal(no_price),
                source="Kalshi",
                probability=no_price,
                price=no_price,
            ),
        ]
        
        return NormalizedEvent(
            event_id=market_id,
            sport=category,
            teams=teams if teams else ["YES", "NO"],
            start_time=raw_market.get("close_time") or raw_market.get("resolution_time", datetime.utcnow().isoformat()),
            market_type="binary",
            outcomes=normalized_outcomes,
            source="Kalshi",
            timestamp=datetime.utcnow().isoformat(),
            title=title,
            category=category,
            source_event_id=market_id,
            url=raw_market.get("url"),
            liquidity=raw_market.get("liquidity"),
            volume=raw_market.get("volume"),
        )
    
    def _extract_teams_from_title(self, title: str) -> List[str]:
        """
        Try to extract team names from a market title.
        
        This is a simple heuristic and may need improvement.
        """
        # Common patterns
        separators = [" vs ", " vs. ", " - ", " @ ", " @ ", " beat ", " defeat "]
        
        for sep in separators:
            if sep in title.lower():
                parts = title.lower().split(sep)
                if len(parts) == 2:
                    return [parts[0].strip().title(), parts[1].strip().title()]
        
        # Check for common team names
        common_teams = [
            "Lakers", "Warriors", "Celtics", "Heat", "Nets", "Bucks",
            "Chiefs", "49ers", "Ravens", "Bills", "Eagles", "Cowboys",
            "Yankees", "Red Sox", "Dodgers", "Giants",
            "Trump", "Biden", "Harris", "DeSantis",
        ]
        
        found_teams = []
        for team in common_teams:
            if team.lower() in title.lower():
                found_teams.append(team)
        
        return found_teams if found_teams else []


def normalize_data(
    raw_data: Union[Dict[str, Any], List[Dict[str, Any]]],
    source: Optional[str] = None
) -> List[NormalizedEvent]:
    """
    Convenience function to normalize data.
    
    Args:
        raw_data: Raw data from any supported source
        source: Source identifier (auto-detected if not provided)
        
    Returns:
        List of normalized events
    """
    normalizer = DataNormalizer()
    return normalizer.normalize(raw_data, source)
