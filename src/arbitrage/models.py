"""
Data models for the Arbitrage Detection Engine.

This module defines the core data structures used throughout the arbitrage
system, including normalized market data, arbitrage opportunities, and match results.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
import uuid


class OddsFormat(Enum):
    """Supported odds formats."""
    DECIMAL = "decimal"      # European style: 2.5 (bet $100 to win $250)
    AMERICAN = "american"    # US style: +150 (bet $100 to win $150) or -200 (bet $200 to win $100)
    FRACTIONAL = "fractional"  # UK style: 3/2
    IMPLIED_PROBABILITY = "implied_probability"  # 0.0 to 1.0


class MarketType(Enum):
    """Types of betting markets."""
    BINARY = "binary"           # Yes/No outcomes (Polymarket style)
    MONEYLINE = "moneyline"     # Team A vs Team B
    SPREAD = "spread"           # Point spread
    TOTAL = "total"             # Over/Under
    FUTURES = "futures"         # Long-term bets


class SourceType(Enum):
    """Source types for market data."""
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"
    DRAFTKINGS = "draftkings"
    FANDUEL = "fanduel"
    BET365 = "bet365"
    ODDS_API = "odds_api"
    CUSTOM = "custom"


@dataclass
class MarketOutcome:
    """
    Represents a single outcome in a betting market.
    
    Attributes:
        label: Human-readable outcome label (e.g., "Yes", "Team A", "Over")
        price: Odds in decimal format (e.g., 2.5)
        american_odds: Odds in American format (e.g., +150, -200)
        implied_probability: Calculated implied probability (0.0 to 1.0)
        liquidity: Available liquidity in USD (if known)
        volume: Trading volume (if available)
    """
    label: str
    price: Optional[Decimal] = None  # Decimal odds
    american_odds: Optional[int] = None  # American odds
    implied_probability: Optional[Decimal] = None
    liquidity: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    
    def __post_init__(self):
        """Calculate implied probability if not provided."""
        if self.implied_probability is None and self.price is not None:
            from .calculator import calculate_implied_probability_decimal
            # Handle both decimal odds (>1) and direct probability prices (0-1 range)
            if self.price > 1:
                self.implied_probability = calculate_implied_probability_decimal(self.price)
            else:
                # Price is already an implied probability (e.g., 0.52 for 52%)
                self.implied_probability = self.price


@dataclass
class NormalizedMarket:
    """
    Normalized representation of a betting market from any source.
    
    This is the common format used throughout the arbitrage system,
    regardless of the original data source.
    
    Attributes:
        source: Source platform (e.g., "polymarket", "draftkings")
        source_event_id: Unique ID from the source platform
        title: Event/market title
        market_type: Type of market (binary, moneyline, etc.)
        category: Sport or category (e.g., "nba", "politics", "crypto")
        start_time: Event start time (ISO timestamp)
        outcomes: List of possible outcomes
        url: Direct link to the market
        last_updated: When this data was fetched
        metadata: Additional source-specific data
    """
    source: str
    source_event_id: str
    title: str
    market_type: MarketType
    category: str
    start_time: datetime
    outcomes: List[MarketOutcome]
    url: Optional[str] = None
    last_updated: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
    
    @property
    def is_binary(self) -> bool:
        """Check if this is a binary (two-outcome) market."""
        return len(self.outcomes) == 2
    
    def get_outcome_by_label(self, label: str) -> Optional[MarketOutcome]:
        """Find an outcome by its label (case-insensitive)."""
        label_lower = label.lower()
        for outcome in self.outcomes:
            if outcome.label.lower() == label_lower:
                return outcome
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "source_event_id": self.source_event_id,
            "title": self.title,
            "market_type": self.market_type.value,
            "category": self.category,
            "start_time": self.start_time.isoformat(),
            "outcomes": [
                {
                    "label": o.label,
                    "price": float(o.price) if o.price else None,
                    "american_odds": o.american_odds,
                    "implied_probability": float(o.implied_probability) if o.implied_probability else None,
                    "liquidity": float(o.liquidity) if o.liquidity else None,
                }
                for o in self.outcomes
            ],
            "url": self.url,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class ArbitrageLeg:
    """
    Represents one leg of an arbitrage opportunity.
    
    Attributes:
        source: Platform name
        source_event_id: Event ID on the source platform
        side: Which side being bet (e.g., "Yes", "Team A", "Over")
        price: Decimal odds
        american_odds: American odds format
        liquidity: Available liquidity
        url: Direct link
        fees_pct: Estimated fees for this leg (% of stake)
    """
    source: str
    source_event_id: str
    side: str
    price: Decimal
    american_odds: Optional[int] = None
    liquidity: Optional[Decimal] = None
    url: Optional[str] = None
    fees_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "source_event_id": self.source_event_id,
            "side": self.side,
            "price": float(self.price),
            "american_odds": self.american_odds,
            "liquidity": float(self.liquidity) if self.liquidity else None,
            "url": self.url,
            "fees_pct": float(self.fees_pct),
        }


@dataclass
class ArbitrageOpportunity:
    """
    Represents a complete arbitrage opportunity across two venues.
    
    Attributes:
        arb_id: Unique identifier for this opportunity
        event_title: Human-readable event title
        left_leg: First leg of the arbitrage
        right_leg: Second leg of the arbitrage
        gross_edge_pct: Raw profit margin before fees (%)
        fees_pct: Total fees/slippage (%)
        slippage_pct: Estimated execution slippage (%)
        net_edge_pct: Net profit margin after all costs (%)
        max_stake: Maximum recommended stake based on liquidity
        expected_profit: Expected profit at max_stake
        match_score: Confidence score for the event match (0.0 to 1.0)
        resolution_confidence: Confidence that outcomes resolve identically (0.0 to 1.0)
        freshness_seconds: Age of the price data
        alertable: Whether this opportunity should trigger an alert
        detected_at: When this opportunity was detected
        expires_at: When this opportunity likely expires (event start)
        metadata: Additional data and calculation details
    """
    arb_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_title: str = ""
    left_leg: Optional[ArbitrageLeg] = None
    right_leg: Optional[ArbitrageLeg] = None
    gross_edge_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    fees_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    net_edge_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    max_stake: Decimal = field(default_factory=lambda: Decimal("0"))
    expected_profit: Decimal = field(default_factory=lambda: Decimal("0"))
    match_score: Decimal = field(default_factory=lambda: Decimal("0"))
    resolution_confidence: Decimal = field(default_factory=lambda: Decimal("0"))
    freshness_seconds: int = 0
    alertable: bool = False
    detected_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "arb_id": self.arb_id,
            "event_title": self.event_title,
            "left_leg": self.left_leg.to_dict() if self.left_leg else None,
            "right_leg": self.right_leg.to_dict() if self.right_leg else None,
            "gross_edge_pct": float(self.gross_edge_pct),
            "fees_pct": float(self.fees_pct),
            "slippage_pct": float(self.slippage_pct),
            "net_edge_pct": float(self.net_edge_pct),
            "max_stake": float(self.max_stake),
            "expected_profit": float(self.expected_profit),
            "match_score": float(self.match_score),
            "resolution_confidence": float(self.resolution_confidence),
            "freshness_seconds": self.freshness_seconds,
            "alertable": self.alertable,
            "detected_at": self.detected_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }
    
    def get_stake_recommendations(self, stakes: List[Decimal] = None) -> Dict[Decimal, Decimal]:
        """
        Calculate expected profit for various stake sizes.
        
        Args:
            stakes: List of stake amounts to calculate (default: 1000, 5000, 10000)
            
        Returns:
            Dictionary mapping stake size to expected profit
        """
        if stakes is None:
            stakes = [Decimal("1000"), Decimal("5000"), Decimal("10000")]
        
        recommendations = {}
        for stake in stakes:
            if stake <= self.max_stake:
                profit = stake * (self.net_edge_pct / Decimal("100"))
                recommendations[stake] = profit
        return recommendations


@dataclass
class MatchedEvent:
    """
    Represents two events that have been matched across sources.
    
    Attributes:
        match_id: Unique identifier for this match
        left_market: First normalized market
        right_market: Second normalized market
        match_score: Fuzzy match confidence (0.0 to 1.0)
        resolution_confidence: Confidence that outcomes resolve the same way
        mapping_type: How outcomes map between markets (e.g., "yes_vs_no")
        status: Match status ("matched", "rejected", "pending_review")
        matched_at: When the match was created
        rejection_reason: Why this match was rejected (if applicable)
    """
    match_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    left_market: Optional[NormalizedMarket] = None
    right_market: Optional[NormalizedMarket] = None
    match_score: Decimal = field(default_factory=lambda: Decimal("0"))
    resolution_confidence: Decimal = field(default_factory=lambda: Decimal("0"))
    mapping_type: str = ""  # e.g., "yes_vs_no", "team_a_vs_team_b"
    status: str = "pending"  # matched, rejected, pending_review
    matched_at: datetime = field(default_factory=datetime.utcnow)
    rejection_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "match_id": self.match_id,
            "left_market": self.left_market.to_dict() if self.left_market else None,
            "right_market": self.right_market.to_dict() if self.right_market else None,
            "match_score": float(self.match_score),
            "resolution_confidence": float(self.resolution_confidence),
            "mapping_type": self.mapping_type,
            "status": self.status,
            "matched_at": self.matched_at.isoformat(),
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class MatchResult:
    """
    Result of attempting to match two events.
    
    Attributes:
        is_match: Whether the events are considered a match
        score: Match confidence score (0.0 to 1.0)
        reasons: List of reasons for the match decision
        title_similarity: Fuzzy title match score
        time_proximity_hours: Difference in event times
        entity_overlap: Score for overlapping entities (teams/players)
    """
    is_match: bool = False
    score: Decimal = field(default_factory=lambda: Decimal("0"))
    reasons: List[str] = field(default_factory=list)
    title_similarity: Decimal = field(default_factory=lambda: Decimal("0"))
    time_proximity_hours: Optional[float] = None
    entity_overlap: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "is_match": self.is_match,
            "score": float(self.score),
            "reasons": self.reasons,
            "title_similarity": float(self.title_similarity),
            "time_proximity_hours": self.time_proximity_hours,
            "entity_overlap": float(self.entity_overlap) if self.entity_overlap else None,
        }


@dataclass
class FeeConfig:
    """
    Configuration for fees by source/platform.
    
    Attributes:
        source: Platform name
        market_fee_pct: Trading fee percentage
        withdrawal_fee_pct: Withdrawal fee estimate
        slippage_estimate_pct: Default slippage estimate
        min_liquidity: Minimum liquidity threshold
    """
    source: str
    market_fee_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    withdrawal_fee_pct: Decimal = field(default_factory=lambda: Decimal("0"))
    slippage_estimate_pct: Decimal = field(default_factory=lambda: Decimal("0.5"))
    min_liquidity: Decimal = field(default_factory=lambda: Decimal("1000"))
    
    @classmethod
    def default_configs(cls) -> Dict[str, "FeeConfig"]:
        """Get default fee configurations for known sources."""
        return {
            "polymarket": cls(
                source="polymarket",
                market_fee_pct=Decimal("0.0"),  # No trading fees on Polymarket
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.3"),
                min_liquidity=Decimal("5000"),
            ),
            "kalshi": cls(
                source="kalshi",
                market_fee_pct=Decimal("0.0"),  # No trading fees on Kalshi
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.3"),
                min_liquidity=Decimal("5000"),
            ),
            "draftkings": cls(
                source="draftkings",
                market_fee_pct=Decimal("0"),  # Built into odds
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.1"),
                min_liquidity=Decimal("10000"),
            ),
            "fanduel": cls(
                source="fanduel",
                market_fee_pct=Decimal("0"),  # Built into odds
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.1"),
                min_liquidity=Decimal("10000"),
            ),
            "bet365": cls(
                source="bet365",
                market_fee_pct=Decimal("0"),  # Built into odds
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.1"),
                min_liquidity=Decimal("5000"),
            ),
            "odds_api": cls(
                source="odds_api",
                market_fee_pct=Decimal("0"),  # Aggregated, fees vary by book
                withdrawal_fee_pct=Decimal("0"),
                slippage_estimate_pct=Decimal("0.2"),
                min_liquidity=Decimal("5000"),
            ),
        }
