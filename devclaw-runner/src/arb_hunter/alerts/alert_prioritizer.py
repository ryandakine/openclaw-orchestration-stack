"""Alert prioritization logic.

Sorts alerts by net edge and sends only the top N opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..arb_opportunity_schema import ArbOpportunity


@dataclass
class PrioritizedAlert:
    """A prioritized alert with ranking info."""
    
    opportunity: "ArbOpportunity"
    rank: int
    score: float


class AlertPrioritizer:
    """Prioritizes arbitrage opportunities for alerting.
    
    Sorts opportunities by a composite score and limits to top N.
    """
    
    DEFAULT_MAX_ALERTS = 5
    
    # Weights for composite scoring
    EDGE_WEIGHT = 0.5
    PROFIT_WEIGHT = 0.3
    LIQUIDITY_WEIGHT = 0.1
    MATCH_WEIGHT = 0.1
    
    def __init__(self, max_alerts: int = DEFAULT_MAX_ALERTS) -> None:
        """Initialize the prioritizer.
        
        Args:
            max_alerts: Maximum number of alerts to send per batch
        """
        self.max_alerts = max_alerts
    
    def prioritize(
        self,
        opportunities: list["ArbOpportunity"],
    ) -> list[PrioritizedAlert]:
        """Prioritize and rank opportunities.
        
        Args:
            opportunities: List of arbitrage opportunities
            
        Returns:
            List of prioritized alerts, sorted by rank
        """
        if not opportunities:
            return []
        
        # Calculate scores for each opportunity
        scored = [
            (opp, self._calculate_score(opp))
            for opp in opportunities
        ]
        
        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Create prioritized alerts with ranks
        prioritized = [
            PrioritizedAlert(opportunity=opp, rank=i + 1, score=score)
            for i, (opp, score) in enumerate(scored[:self.max_alerts])
        ]
        
        return prioritized
    
    def filter_and_prioritize(
        self,
        opportunities: list["ArbOpportunity"],
        min_net_edge_pct: float = 0.01,  # 1% minimum
        min_profit: float = 10.0,  # $10 minimum
    ) -> list[PrioritizedAlert]:
        """Filter opportunities and then prioritize.
        
        Args:
            opportunities: List of arbitrage opportunities
            min_net_edge_pct: Minimum net edge percentage
            min_profit: Minimum expected profit in USD
            
        Returns:
            List of prioritized alerts passing filters
        """
        # Filter by minimum thresholds
        filtered = [
            opp for opp in opportunities
            if opp.net_edge_pct >= min_net_edge_pct
            and opp.expected_profit >= min_profit
            and opp.alertable
        ]
        
        return self.prioritize(filtered)
    
    def _calculate_score(self, opportunity: "ArbOpportunity") -> float:
        """Calculate composite score for an opportunity.
        
        Higher scores indicate better alert priority.
        
        Args:
            opportunity: The arbitrage opportunity
            
        Returns:
            Composite score (higher is better)
        """
        # Normalize components to 0-1 scale
        edge_score = min(opportunity.net_edge_pct / 0.05, 1.0)  # 5% = max
        profit_score = min(opportunity.expected_profit / 1000, 1.0)  # $1000 = max
        
        # Liquidity score based on min liquidity
        left_liq = opportunity.left_leg.get("liquidity", 0)
        right_liq = opportunity.right_leg.get("liquidity", 0)
        min_liquidity = min(left_liq or 0, right_liq or 0)
        liquidity_score = min(min_liquidity / 100_000, 1.0)  # $100k = max
        
        match_score = opportunity.match_score
        
        # Calculate weighted composite
        composite = (
            self.EDGE_WEIGHT * edge_score +
            self.PROFIT_WEIGHT * profit_score +
            self.LIQUIDITY_WEIGHT * liquidity_score +
            self.MATCH_WEIGHT * match_score
        )
        
        return composite
    
    def get_tier(self, alert: PrioritizedAlert) -> str:
        """Get the tier/quality level for an alert.
        
        Args:
            alert: The prioritized alert
            
        Returns:
            Tier string: "S", "A", "B", or "C"
        """
        opp = alert.opportunity
        
        # S tier: Exceptional opportunity
        if (opp.net_edge_pct >= 0.03 and  # 3%+
            opp.expected_profit >= 100 and  # $100+
            opp.match_score >= 0.95):
            return "S"
        
        # A tier: Great opportunity
        if (opp.net_edge_pct >= 0.02 and  # 2%+
            opp.expected_profit >= 50 and  # $50+
            opp.match_score >= 0.90):
            return "A"
        
        # B tier: Good opportunity
        if (opp.net_edge_pct >= 0.015 and  # 1.5%+
            opp.expected_profit >= 25 and  # $25+
            opp.match_score >= 0.85):
            return "B"
        
        # C tier: Decent opportunity
        return "C"
    
    def get_batch_summary(
        self,
        alerts: list[PrioritizedAlert],
    ) -> dict[str, any]:
        """Get a summary of the prioritized batch.
        
        Args:
            alerts: List of prioritized alerts
            
        Returns:
            Summary dictionary
        """
        if not alerts:
            return {
                "total": 0,
                "tiers": {},
                "avg_edge_pct": 0.0,
                "total_profit": 0.0,
            }
        
        tiers = {}
        total_edge = 0.0
        total_profit = 0.0
        
        for alert in alerts:
            tier = self.get_tier(alert)
            tiers[tier] = tiers.get(tier, 0) + 1
            total_edge += alert.opportunity.net_edge_pct
            total_profit += alert.opportunity.expected_profit
        
        return {
            "total": len(alerts),
            "tiers": tiers,
            "avg_edge_pct": round((total_edge / len(alerts)) * 100, 2),
            "total_profit": round(total_profit, 2),
        }
