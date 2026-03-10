"""
Opportunity filtering logic for arbitrage detection.

This module provides filters to identify high-quality arbitrage opportunities
by applying profitability, liquidity, timing, and confidence thresholds.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Callable

from .models import (
    ArbitrageOpportunity,
    NormalizedMarket,
    FeeConfig,
)


@dataclass
class OpportunityFilter:
    """
    Configuration for filtering arbitrage opportunities.
    
    Attributes:
        min_profit_pct: Minimum net profit percentage to alert
        min_match_score: Minimum event match confidence (0.0 to 1.0)
        min_resolution_confidence: Minimum resolution confidence (0.0 to 1.0)
        max_time_to_event_hours: Maximum hours until event start
        min_liquidity_usd: Minimum liquidity required
        max_freshness_seconds: Maximum age of price data
        max_total_fees_pct: Maximum acceptable total fees
        min_edge_over_fees_pct: Minimum edge above fees
        suspended_sources: List of sources to exclude
        blocked_categories: List of categories to exclude
    """
    min_profit_pct: Decimal = field(default_factory=lambda: Decimal("2.0"))
    min_match_score: Decimal = field(default_factory=lambda: Decimal("0.75"))
    min_resolution_confidence: Decimal = field(default_factory=lambda: Decimal("0.90"))
    max_time_to_event_hours: Optional[int] = 168  # 1 week
    min_liquidity_usd: Decimal = field(default_factory=lambda: Decimal("5000"))
    max_freshness_seconds: int = 120  # 2 minutes
    max_total_fees_pct: Decimal = field(default_factory=lambda: Decimal("5.0"))
    min_edge_over_fees_pct: Decimal = field(default_factory=lambda: Decimal("1.0"))
    suspended_sources: List[str] = field(default_factory=list)
    blocked_categories: List[str] = field(default_factory=list)
    
    @classmethod
    def conservative(cls) -> "OpportunityFilter":
        """Create a conservative filter with strict thresholds."""
        return cls(
            min_profit_pct=Decimal("3.0"),
            min_match_score=Decimal("0.85"),
            min_resolution_confidence=Decimal("0.95"),
            max_time_to_event_hours=72,
            min_liquidity_usd=Decimal("10000"),
            max_freshness_seconds=60,
        )
    
    @classmethod
    def aggressive(cls) -> "OpportunityFilter":
        """Create an aggressive filter with lenient thresholds."""
        return cls(
            min_profit_pct=Decimal("1.0"),
            min_match_score=Decimal("0.60"),
            min_resolution_confidence=Decimal("0.75"),
            max_time_to_event_hours=336,  # 2 weeks
            min_liquidity_usd=Decimal("1000"),
            max_freshness_seconds=300,  # 5 minutes
        )
    
    @classmethod
    def from_env(cls, prefix: str = "ARB_") -> "OpportunityFilter":
        """Create filter from environment variables."""
        import os
        
        def get_decimal(key: str, default: Decimal) -> Decimal:
            value = os.environ.get(f"{prefix}{key}")
            return Decimal(value) if value else default
        
        def get_int(key: str, default: int) -> int:
            value = os.environ.get(f"{prefix}{key}")
            return int(value) if value else default
        
        return cls(
            min_profit_pct=get_decimal("MIN_NET_EDGE_PCT", Decimal("2.0")),
            min_match_score=get_decimal("MATCH_CONFIDENCE_MIN", Decimal("0.75")),
            min_resolution_confidence=get_decimal("RESOLUTION_CONFIDENCE_MIN", Decimal("0.90")),
            max_time_to_event_hours=get_int("MAX_TIME_TO_EVENT_HOURS", 168),
            min_liquidity_usd=get_decimal("MIN_TOTAL_LIQUIDITY", Decimal("5000")),
            max_freshness_seconds=get_int("MAX_STALENESS_SECONDS", 120),
        )


def check_profitability(
    opportunity: ArbitrageOpportunity,
    min_profit_pct: Decimal,
) -> tuple[bool, Optional[str]]:
    """
    Check if opportunity meets profit threshold.
    
    Args:
        opportunity: Arbitrage opportunity to check
        min_profit_pct: Minimum profit percentage required
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if opportunity.net_edge_pct < min_profit_pct:
        return False, f"Net profit {opportunity.net_edge_pct:.2f}% below threshold {min_profit_pct}%"
    return True, None


def check_match_confidence(
    opportunity: ArbitrageOpportunity,
    min_match_score: Decimal,
    min_resolution_confidence: Decimal,
) -> tuple[bool, Optional[str]]:
    """
    Check if opportunity meets match confidence thresholds.
    
    Args:
        opportunity: Arbitrage opportunity to check
        min_match_score: Minimum match score required
        min_resolution_confidence: Minimum resolution confidence required
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if opportunity.match_score < min_match_score:
        return False, f"Match score {opportunity.match_score:.2f} below threshold {min_match_score}"
    
    if opportunity.resolution_confidence < min_resolution_confidence:
        return False, (
            f"Resolution confidence {opportunity.resolution_confidence:.2f} "
            f"below threshold {min_resolution_confidence}"
        )
    
    return True, None


def check_liquidity(
    opportunity: ArbitrageOpportunity,
    min_liquidity_usd: Decimal,
) -> tuple[bool, Optional[str]]:
    """
    Check if opportunity has sufficient liquidity.
    
    Args:
        opportunity: Arbitrage opportunity to check
        min_liquidity_usd: Minimum liquidity required
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if not opportunity.left_leg or not opportunity.right_leg:
        return False, "Missing leg information"
    
    left_liq = opportunity.left_leg.liquidity or Decimal("0")
    right_liq = opportunity.right_leg.liquidity or Decimal("0")
    
    if left_liq < min_liquidity_usd:
        return False, f"Left leg liquidity ${left_liq:,.2f} below threshold ${min_liquidity_usd:,.2f}"
    
    if right_liq < min_liquidity_usd:
        return False, f"Right leg liquidity ${right_liq:,.2f} below threshold ${min_liquidity_usd:,.2f}"
    
    return True, None


def check_freshness(
    opportunity: ArbitrageOpportunity,
    max_freshness_seconds: int,
) -> tuple[bool, Optional[str]]:
    """
    Check if opportunity data is fresh enough.
    
    Args:
        opportunity: Arbitrage opportunity to check
        max_freshness_seconds: Maximum age of data in seconds
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if opportunity.freshness_seconds > max_freshness_seconds:
        return False, (
            f"Data freshness {opportunity.freshness_seconds}s "
            f"exceeds maximum {max_freshness_seconds}s"
        )
    return True, None


def check_time_to_event(
    opportunity: ArbitrageOpportunity,
    max_hours: Optional[int],
) -> tuple[bool, Optional[str]]:
    """
    Check if there's enough time before event starts.
    
    Args:
        opportunity: Arbitrage opportunity to check
        max_hours: Maximum hours until event (None to disable)
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if max_hours is None:
        return True, None
    
    if not opportunity.expires_at:
        return True, None  # Can't check if no expiry time
    
    time_until = opportunity.expires_at - datetime.utcnow()
    hours_until = time_until.total_seconds() / 3600
    
    if hours_until < 0:
        return False, "Event has already started"
    
    if hours_until > max_hours:
        return False, f"Event starts in {hours_until:.1f}h, exceeds maximum {max_hours}h"
    
    return True, None


def check_fees(
    opportunity: ArbitrageOpportunity,
    max_total_fees_pct: Decimal,
    min_edge_over_fees_pct: Decimal,
) -> tuple[bool, Optional[str]]:
    """
    Check if fees are acceptable.
    
    Args:
        opportunity: Arbitrage opportunity to check
        max_total_fees_pct: Maximum total fees allowed
        min_edge_over_fees_pct: Minimum edge above fees required
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    total_fees = opportunity.fees_pct + opportunity.slippage_pct
    
    if total_fees > max_total_fees_pct:
        return False, f"Total fees {total_fees:.2f}% exceed maximum {max_total_fees_pct}%"
    
    # Check that gross edge is sufficiently above fees
    edge_over_fees = opportunity.gross_edge_pct - total_fees
    if edge_over_fees < min_edge_over_fees_pct:
        return False, f"Edge over fees {edge_over_fees:.2f}% below minimum {min_edge_over_fees_pct}%"
    
    return True, None


def check_sources(
    opportunity: ArbitrageOpportunity,
    suspended_sources: List[str],
) -> tuple[bool, Optional[str]]:
    """
    Check that neither source is suspended.
    
    Args:
        opportunity: Arbitrage opportunity to check
        suspended_sources: List of suspended source names
        
    Returns:
        Tuple of (passed, reason_if_failed)
    """
    if not opportunity.left_leg or not opportunity.right_leg:
        return False, "Missing leg information"
    
    if opportunity.left_leg.source.lower() in [s.lower() for s in suspended_sources]:
        return False, f"Source {opportunity.left_leg.source} is suspended"
    
    if opportunity.right_leg.source.lower() in [s.lower() for s in suspended_sources]:
        return False, f"Source {opportunity.right_leg.source} is suspended"
    
    return True, None


def filter_opportunity(
    opportunity: ArbitrageOpportunity,
    filter_config: OpportunityFilter,
) -> tuple[bool, List[str]]:
    """
    Apply all filters to an arbitrage opportunity.
    
    Args:
        opportunity: Arbitrage opportunity to filter
        filter_config: Filter configuration
        
    Returns:
        Tuple of (is_valid, list_of_rejection_reasons)
    """
    failures = []
    
    checks = [
        check_profitability(opportunity, filter_config.min_profit_pct),
        check_match_confidence(
            opportunity,
            filter_config.min_match_score,
            filter_config.min_resolution_confidence,
        ),
        check_liquidity(opportunity, filter_config.min_liquidity_usd),
        check_freshness(opportunity, filter_config.max_freshness_seconds),
        check_time_to_event(opportunity, filter_config.max_time_to_event_hours),
        check_fees(
            opportunity,
            filter_config.max_total_fees_pct,
            filter_config.min_edge_over_fees_pct,
        ),
        check_sources(opportunity, filter_config.suspended_sources),
    ]
    
    for passed, reason in checks:
        if not passed:
            failures.append(reason)
    
    return len(failures) == 0, failures


def filter_opportunities(
    opportunities: List[ArbitrageOpportunity],
    filter_config: OpportunityFilter,
) -> tuple[List[ArbitrageOpportunity], List[tuple[ArbitrageOpportunity, List[str]]]]:
    """
    Filter multiple opportunities and return valid ones with rejections.
    
    Args:
        opportunities: List of arbitrage opportunities
        filter_config: Filter configuration
        
    Returns:
        Tuple of (valid_opportunities, rejected_with_reasons)
    """
    valid = []
    rejected = []
    
    for opp in opportunities:
        is_valid, reasons = filter_opportunity(opp, filter_config)
        if is_valid:
            valid.append(opp)
        else:
            rejected.append((opp, reasons))
    
    return valid, rejected


class OpportunityRanker:
    """
    Ranks arbitrage opportunities by quality score.
    
    Quality score considers:
    - Net profit margin (higher is better)
    - Match confidence (higher is better)
    - Liquidity (higher is better)
    - Data freshness (newer is better)
    - Time to event (more time is better)
    """
    
    def __init__(
        self,
        profit_weight: Decimal = Decimal("0.35"),
        confidence_weight: Decimal = Decimal("0.25"),
        liquidity_weight: Decimal = Decimal("0.20"),
        freshness_weight: Decimal = Decimal("0.10"),
        time_weight: Decimal = Decimal("0.10"),
    ):
        """
        Initialize ranker with weights (should sum to 1.0).
        
        Args:
            profit_weight: Weight for profit margin
            confidence_weight: Weight for match confidence
            liquidity_weight: Weight for liquidity score
            freshness_weight: Weight for data freshness
            time_weight: Weight for time until event
        """
        self.profit_weight = profit_weight
        self.confidence_weight = confidence_weight
        self.liquidity_weight = liquidity_weight
        self.freshness_weight = freshness_weight
        self.time_weight = time_weight
    
    def calculate_score(self, opportunity: ArbitrageOpportunity) -> Decimal:
        """
        Calculate quality score for an opportunity.
        
        Args:
            opportunity: Arbitrage opportunity to score
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        # Normalize profit (cap at 10% for scoring)
        profit_score = min(opportunity.net_edge_pct / Decimal("10"), Decimal("1"))
        
        # Match confidence (already 0-1)
        confidence_score = opportunity.match_score
        
        # Liquidity score (log scale, cap at $100k)
        if opportunity.left_leg and opportunity.right_leg:
            min_liq = min(
                opportunity.left_leg.liquidity or Decimal("0"),
                opportunity.right_leg.liquidity or Decimal("0"),
            )
            liquidity_score = min(
                (min_liq / Decimal("100000")).ln() / Decimal("100").ln(),
                Decimal("1"),
            )
        else:
            liquidity_score = Decimal("0")
        
        # Freshness score (newer is better, cap at 5 minutes)
        freshness_score = max(
            Decimal("0"),
            Decimal("1") - (Decimal(opportunity.freshness_seconds) / Decimal("300")),
        )
        
        # Time score (more time is better, ideal is 24-72 hours)
        if opportunity.expires_at:
            hours_until = Decimal(
                (opportunity.expires_at - datetime.utcnow()).total_seconds() / 3600
            )
            if hours_until <= 0:
                time_score = Decimal("0")
            elif hours_until < 24:
                time_score = hours_until / Decimal("24")
            elif hours_until < 72:
                time_score = Decimal("1")
            else:
                time_score = max(Decimal("0"), Decimal("1") - (hours_until - 72) / 168)
        else:
            time_score = Decimal("0.5")
        
        # Calculate weighted score
        score = (
            profit_score * self.profit_weight +
            confidence_score * self.confidence_weight +
            liquidity_score * self.liquidity_weight +
            freshness_score * self.freshness_weight +
            time_score * self.time_weight
        )
        
        return score
    
    def rank(
        self,
        opportunities: List[ArbitrageOpportunity],
    ) -> List[tuple[ArbitrageOpportunity, Decimal]]:
        """
        Rank opportunities by quality score.
        
        Args:
            opportunities: List of opportunities to rank
            
        Returns:
            List of (opportunity, score) tuples, sorted by score descending
        """
        scored = [(opp, self.calculate_score(opp)) for opp in opportunities]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
