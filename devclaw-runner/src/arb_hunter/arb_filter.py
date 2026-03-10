"""Arb Filter - Apply all filters to determine alertable opportunities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    from .arb_opportunity_schema import ArbOpportunity
except ImportError:
    from arb_opportunity_schema import ArbOpportunity


@dataclass
class FilterResult:
    """Result of filter application."""
    
    passed: bool
    """True if all filters passed."""
    
    alertable: bool
    """True if opportunity should be alerted."""
    
    failed_filters: list[str] = field(default_factory=list)
    """List of filters that failed."""
    
    filter_scores: dict[str, float] = field(default_factory=dict)
    """Scores for each filter."""
    
    final_score: float = 0.0
    """Overall quality score."""
    
    rejection_reason: Optional[str] = None
    """Primary rejection reason."""


class ArbFilter:
    """
    Apply comprehensive filters to arbitrage opportunities.
    
    Conservative filter criteria:
    - Net edge > 2.0%
    - Liquidity > $10k on both legs
    - Match confidence > 0.85
    - Freshness < 120s
    - Resolution confidence > 0.90
    """
    
    # Filter thresholds (conservative defaults)
    MIN_NET_EDGE_PCT: float = 0.02  # 2.0%
    MIN_LIQUIDITY_USD: float = 10000.0  # $10k
    MIN_MATCH_SCORE: float = 0.85
    MAX_FRESHNESS_SECONDS: int = 120
    MIN_RESOLUTION_CONFIDENCE: float = 0.90
    
    def __init__(
        self,
        min_net_edge_pct: float = MIN_NET_EDGE_PCT,
        min_liquidity_usd: float = MIN_LIQUIDITY_USD,
        min_match_score: float = MIN_MATCH_SCORE,
        max_freshness_seconds: int = MAX_FRESHNESS_SECONDS,
        min_resolution_confidence: float = MIN_RESOLUTION_CONFIDENCE,
    ) -> None:
        """
        Initialize arb filter.
        
        Args:
            min_net_edge_pct: Minimum net edge for alerting
            min_liquidity_usd: Minimum liquidity per leg
            min_match_score: Minimum event match confidence
            max_freshness_seconds: Maximum acceptable price age
            min_resolution_confidence: Minimum resolution match confidence
        """
        self.min_net_edge_pct = min_net_edge_pct
        self.min_liquidity_usd = min_liquidity_usd
        self.min_match_score = min_match_score
        self.max_freshness_seconds = max_freshness_seconds
        self.min_resolution_confidence = min_resolution_confidence
    
    async def apply_filters(
        self,
        opportunity: ArbOpportunity,
    ) -> FilterResult:
        """
        Apply all filters to an opportunity.
        
        Args:
            opportunity: The arbitrage opportunity to filter
            
        Returns:
            FilterResult with detailed results
        """
        failed_filters: list[str] = []
        filter_scores: dict[str, float] = {}
        
        # Filter 1: Net edge
        net_edge_pass = opportunity.net_edge_pct >= self.min_net_edge_pct
        filter_scores["net_edge"] = opportunity.net_edge_pct
        if not net_edge_pass:
            failed_filters.append(
                f"net_edge ({opportunity.net_edge_pct:.4%} < {self.min_net_edge_pct:.4%})"
            )
        
        # Filter 2: Liquidity
        left_liq = opportunity.left_leg.get("liquidity", 0)
        right_liq = opportunity.right_leg.get("liquidity", 0)
        min_liq = min(left_liq, right_liq)
        liquidity_pass = (
            left_liq >= self.min_liquidity_usd and 
            right_liq >= self.min_liquidity_usd
        )
        filter_scores["liquidity"] = min_liq / self.min_liquidity_usd
        if not liquidity_pass:
            failed_filters.append(
                f"liquidity (min: ${min_liq:,.2f} < ${self.min_liquidity_usd:,.2f})"
            )
        
        # Filter 3: Match confidence
        match_pass = opportunity.match_score >= self.min_match_score
        filter_scores["match_score"] = opportunity.match_score
        if not match_pass:
            failed_filters.append(
                f"match_score ({opportunity.match_score:.4f} < {self.min_match_score:.4f})"
            )
        
        # Filter 4: Freshness
        freshness_pass = opportunity.freshness_seconds < self.max_freshness_seconds
        filter_scores["freshness"] = 1.0 - (
            opportunity.freshness_seconds / self.max_freshness_seconds
        )
        if not freshness_pass:
            failed_filters.append(
                f"freshness ({opportunity.freshness_seconds}s >= {self.max_freshness_seconds}s)"
            )
        
        # Filter 5: Resolution confidence
        resolution_pass = opportunity.resolution_confidence >= self.min_resolution_confidence
        filter_scores["resolution"] = opportunity.resolution_confidence
        if not resolution_pass:
            failed_filters.append(
                f"resolution_confidence ({opportunity.resolution_confidence:.4f} < "
                f"{self.min_resolution_confidence:.4f})"
            )
        
        # Filter 6: Max size must be positive
        size_pass = opportunity.max_size > 0
        filter_scores["max_size"] = 1.0 if size_pass else 0.0
        if not size_pass:
            failed_filters.append("max_size (zero or negative)")
        
        # Filter 7: Expected profit must be positive
        profit_pass = opportunity.expected_profit > 0
        filter_scores["expected_profit"] = 1.0 if profit_pass else 0.0
        if not profit_pass:
            failed_filters.append("expected_profit (zero or negative)")
        
        # Calculate final score (geometric mean of filter scores)
        import math
        if filter_scores:
            final_score = math.exp(
                sum(math.log(max(s, 0.001)) for s in filter_scores.values()) 
                / len(filter_scores)
            )
        else:
            final_score = 0.0
        
        # Determine pass/fail
        all_passed = (
            net_edge_pass and 
            liquidity_pass and 
            match_pass and 
            freshness_pass and 
            resolution_pass and
            size_pass and
            profit_pass
        )
        
        # Rejection reason
        rejection_reason = failed_filters[0] if failed_filters else None
        
        # Update opportunity
        opportunity.alertable = all_passed
        
        return FilterResult(
            passed=all_passed,
            alertable=all_passed,
            failed_filters=failed_filters,
            filter_scores=filter_scores,
            final_score=final_score,
            rejection_reason=rejection_reason,
        )
    
    async def quick_filter(
        self,
        opportunity: ArbOpportunity,
    ) -> bool:
        """
        Quick filter check - returns True only if all critical filters pass.
        
        This is the fast path for high-volume filtering.
        """
        # Critical filters only
        if opportunity.net_edge_pct < self.min_net_edge_pct:
            return False
        
        if opportunity.freshness_seconds >= self.max_freshness_seconds:
            return False
        
        if opportunity.match_score < self.min_match_score:
            return False
        
        left_liq = opportunity.left_leg.get("liquidity", 0)
        right_liq = opportunity.right_leg.get("liquidity", 0)
        if left_liq < self.min_liquidity_usd or right_liq < self.min_liquidity_usd:
            return False
        
        return True
    
    def filter_batch(
        self,
        opportunities: list[ArbOpportunity],
    ) -> tuple[list[ArbOpportunity], list[ArbOpportunity]]:
        """
        Filter a batch of opportunities.
        
        Returns:
            Tuple of (alertable, rejected)
        """
        alertable = []
        rejected = []
        
        for opp in opportunities:
            if opp.alertable:
                alertable.append(opp)
            else:
                rejected.append(opp)
        
        return alertable, rejected
    
    def update_thresholds(
        self,
        min_net_edge_pct: Optional[float] = None,
        min_liquidity_usd: Optional[float] = None,
        min_match_score: Optional[float] = None,
        max_freshness_seconds: Optional[int] = None,
    ) -> None:
        """Update filter thresholds."""
        if min_net_edge_pct is not None:
            self.min_net_edge_pct = min_net_edge_pct
        if min_liquidity_usd is not None:
            self.min_liquidity_usd = min_liquidity_usd
        if min_match_score is not None:
            self.min_match_score = min_match_score
        if max_freshness_seconds is not None:
            self.max_freshness_seconds = max_freshness_seconds
