"""
Match Result Schema - Dataclasses for event matching results.

Module 2.1: Defines data structures for match results and matched opportunities.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional
from uuid import UUID, uuid4


class MappingType(str, Enum):
    """Type of mapping between prediction market and sportsbook events."""
    DIRECT = "direct"  # Same event, same outcomes
    INVERSE = "inverse"  # Same event, inverted outcomes (YES ↔ NO)
    IMPLIED = "implied"  # Derived from multiple outcomes
    COMPOSITE = "composite"  # Combination of multiple events
    UNKNOWN = "unknown"


class MatchStatus(str, Enum):
    """Status of a match attempt."""
    PENDING = "pending"
    MATCHED = "matched"
    REJECTED = "rejected"
    FAILED = "failed"
    VERIFIED = "verified"


class RejectionReason(str, Enum):
    """Reasons why a match was rejected."""
    NONE = "none"
    LOW_TITLE_SIMILARITY = "low_title_similarity"
    ENTITY_MISMATCH = "entity_mismatch"
    DATE_MISMATCH = "date_mismatch"
    CATEGORY_MISMATCH = "category_mismatch"
    RESOLUTION_SEMANTICS_MISMATCH = "resolution_semantics_mismatch"
    LOW_OVERALL_SCORE = "low_overall_score"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_DATA = "invalid_data"
    DUPLICATE_MATCH = "duplicate_match"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass(frozen=True)
class EntitySet:
    """Extracted entities from an event for comparison."""
    candidates: frozenset[str] = field(default_factory=frozenset)
    teams: frozenset[str] = field(default_factory=frozenset)
    players: frozenset[str] = field(default_factory=frozenset)
    dates: frozenset[str] = field(default_factory=frozenset)  # ISO format dates
    locations: frozenset[str] = field(default_factory=frozenset)
    organizations: frozenset[str] = field(default_factory=frozenset)
    
    def to_dict(self) -> dict[str, list[str]]:
        """Convert to dictionary for serialization."""
        return {
            "candidates": list(self.candidates),
            "teams": list(self.teams),
            "players": list(self.players),
            "dates": list(self.dates),
            "locations": list(self.locations),
            "organizations": list(self.organizations),
        }


@dataclass
class MatchScores:
    """Individual component scores for a match."""
    title_similarity: float = 0.0  # 0-1
    entity_match: float = 0.0  # 0-1
    date_match: float = 0.0  # 0-1
    category_match: float = 0.0  # 0-1
    resolution_semantics: float = 0.0  # 0-1
    
    # Weighted final score
    final_score: float = 0.0
    
    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary for serialization."""
        return {
            "title_similarity": self.title_similarity,
            "entity_match": self.entity_match,
            "date_match": self.date_match,
            "category_match": self.category_match,
            "resolution_semantics": self.resolution_semantics,
            "final_score": self.final_score,
        }


@dataclass
class MatchResult:
    """
    Result of matching a single prediction market event against a sportsbook event.
    
    This is the core output of the matching pipeline, containing all metadata
    needed to determine if an arbitrage opportunity exists.
    """
    # Unique identifiers
    match_id: str = field(default_factory=lambda: str(uuid4()))
    
    # Source information
    left_source: str = ""  # Prediction market source (e.g., "polymarket")
    left_event_id: str = ""
    left_event_title: str = ""
    left_category: str = ""
    left_resolution_rules: str = ""
    left_entities: EntitySet = field(default_factory=EntitySet)
    left_outcome: str = ""  # YES, NO, or specific outcome
    left_odds: float = 0.0  # Decimal odds
    
    right_source: str = ""  # Sportsbook source (e.g., "draftkings")
    right_event_id: str = ""
    right_event_title: str = ""
    right_category: str = ""
    right_resolution_rules: str = ""
    right_entities: EntitySet = field(default_factory=EntitySet)
    right_outcome: str = ""  # Sportsbook outcome description
    right_odds: float = 0.0  # Decimal odds
    
    # Match quality
    match_score: float = 0.0  # Overall 0-1 confidence
    resolution_confidence: float = 0.0  # Confidence that outcomes resolve the same way
    mapping_type: MappingType = MappingType.UNKNOWN
    
    # Component scores for transparency
    scores: MatchScores = field(default_factory=MatchScores)
    
    # Match status
    status: MatchStatus = MatchStatus.PENDING
    rejection_reason: RejectionReason = RejectionReason.NONE
    rejection_details: str = ""
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    
    # Arbitrage-specific fields (populated later in pipeline)
    implied_probability_left: float = 0.0
    implied_probability_right: float = 0.0
    
    def is_valid_match(self, min_score: float = 0.85) -> bool:
        """Check if this match meets the minimum score threshold."""
        return (
            self.status == MatchStatus.MATCHED
            and self.match_score >= min_score
            and self.resolution_confidence >= 0.9
        )
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "match_id": self.match_id,
            "left_source": self.left_source,
            "left_event_id": self.left_event_id,
            "left_event_title": self.left_event_title,
            "left_category": self.left_category,
            "left_outcome": self.left_outcome,
            "left_odds": self.left_odds,
            "right_source": self.right_source,
            "right_event_id": self.right_event_id,
            "right_event_title": self.right_event_title,
            "right_category": self.right_category,
            "right_outcome": self.right_outcome,
            "right_odds": self.right_odds,
            "match_score": self.match_score,
            "resolution_confidence": self.resolution_confidence,
            "mapping_type": self.mapping_type.value,
            "scores": self.scores.to_dict(),
            "status": self.status.value,
            "rejection_reason": self.rejection_reason.value,
            "rejection_details": self.rejection_details,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


@dataclass
class MatchedOpportunity:
    """
    A validated arbitrage opportunity between prediction market and sportsbook.
    
    This is created when a MatchResult passes all validation and is ready
    for the arbitrage calculation phase.
    """
    # Reference to the original match
    match_result: MatchResult
    
    # Arbitrage calculation fields
    stake_left: float = 0.0  # Suggested stake on prediction market
    stake_right: float = 0.0  # Suggested stake on sportsbook
    total_stake: float = 0.0
    
    # Profit metrics
    guaranteed_profit: float = 0.0
    profit_percentage: float = 0.0
    roi_percentage: float = 0.0
    
    # Risk assessment
    risk_factors: list[str] = field(default_factory=list)
    confidence_tier: str = "unknown"  # A, B, C based on match quality
    
    # Execution metadata
    opportunity_id: str = field(default_factory=lambda: str(uuid4()))
    discovered_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Bookkeeping
    execution_status: str = "pending"  # pending, executing, executed, failed, expired
    execution_notes: str = ""
    
    def calculate_implied_probabilities(self) -> tuple[float, float]:
        """Calculate implied probabilities from decimal odds."""
        self.match_result.implied_probability_left = (
            1.0 / self.match_result.left_odds if self.match_result.left_odds > 0 else 0.0
        )
        self.match_result.implied_probability_right = (
            1.0 / self.match_result.right_odds if self.match_result.right_odds > 0 else 0.0
        )
        return (
            self.match_result.implied_probability_left,
            self.match_result.implied_probability_right,
        )
    
    def is_arbitrage(self, min_profit_pct: float = 0.5) -> bool:
        """Check if this opportunity meets minimum profit threshold."""
        return self.profit_percentage >= min_profit_pct
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "opportunity_id": self.opportunity_id,
            "match_result": self.match_result.to_dict(),
            "stake_left": self.stake_left,
            "stake_right": self.stake_right,
            "total_stake": self.total_stake,
            "guaranteed_profit": self.guaranteed_profit,
            "profit_percentage": self.profit_percentage,
            "roi_percentage": self.roi_percentage,
            "risk_factors": self.risk_factors,
            "confidence_tier": self.confidence_tier,
            "discovered_at": self.discovered_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "execution_status": self.execution_status,
            "execution_notes": self.execution_notes,
        }
