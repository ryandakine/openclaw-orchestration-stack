"""Net Edge Calculator - Calculate net edge after all costs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NetEdgeResult:
    """Result of net edge calculation."""
    
    gross_edge_pct: float
    """Original gross edge."""
    
    fees_pct: float
    """Total fees as percentage."""
    
    slippage_pct: float
    """Slippage as percentage."""
    
    freshness_penalty_pct: float
    """Freshness penalty applied."""
    
    net_edge_pct: float
    """Net edge after all costs."""
    
    net_edge_bps: float
    """Net edge in basis points."""
    
    is_alertable: bool
    """True if net edge exceeds alert threshold."""
    
    alert_threshold_pct: float
    """Threshold for alerting."""
    
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    """Detailed cost breakdown."""
    
    rejection_reason: Optional[str] = None
    """Reason if not alertable."""


class NetEdgeCalculator:
    """
    Calculate net arbitrage edge after all costs.
    
    Formula: net_edge = gross_edge - fees - slippage - freshness_penalty
    
    Conservative: Only alert if net_edge > 2.0%
    """
    
    DEFAULT_ALERT_THRESHOLD: float = 0.02  # 2.0%
    MIN_NET_EDGE: float = 0.005  # 0.5% absolute minimum
    
    def __init__(
        self,
        alert_threshold_pct: float = DEFAULT_ALERT_THRESHOLD,
        min_net_edge_pct: float = MIN_NET_EDGE,
    ) -> None:
        """
        Initialize net edge calculator.
        
        Args:
            alert_threshold_pct: Minimum net edge to trigger alert
            min_net_edge_pct: Absolute minimum edge to consider valid
        """
        self.alert_threshold_pct = alert_threshold_pct
        self.min_net_edge_pct = min_net_edge_pct
    
    def calculate_net_edge(
        self,
        gross_edge_pct: float,
        fees_pct: float,
        slippage_pct: float,
        freshness_penalty_pct: float = 0.0,
    ) -> NetEdgeResult:
        """
        Calculate net edge from gross edge and costs.
        
        Args:
            gross_edge_pct: Gross arbitrage edge
            fees_pct: Total fees as percentage
            slippage_pct: Slippage estimate
            freshness_penalty_pct: Penalty for stale prices
            
        Returns:
            NetEdgeResult with full breakdown
        """
        # Calculate net edge
        total_costs = fees_pct + slippage_pct + freshness_penalty_pct
        net_edge_pct = gross_edge_pct - total_costs
        
        # Determine if alertable
        is_alertable = (
            net_edge_pct >= self.alert_threshold_pct and
            net_edge_pct >= self.min_net_edge_pct and
            gross_edge_pct > 0
        )
        
        # Determine rejection reason
        rejection_reason: Optional[str] = None
        if not is_alertable:
            if net_edge_pct < 0:
                rejection_reason = f"Negative net edge: {net_edge_pct:.4%}"
            elif net_edge_pct < self.min_net_edge_pct:
                rejection_reason = f"Net edge below minimum: {net_edge_pct:.4%} < {self.min_net_edge_pct:.4%}"
            elif net_edge_pct < self.alert_threshold_pct:
                rejection_reason = (
                    f"Net edge below alert threshold: {net_edge_pct:.4%} < "
                    f"{self.alert_threshold_pct:.4%}"
                )
            else:
                rejection_reason = "Unknown"
        
        # Cost breakdown
        cost_breakdown = {
            "gross_edge_usd": gross_edge_pct,
            "fees_usd": fees_pct,
            "slippage_usd": slippage_pct,
            "freshness_penalty_usd": freshness_penalty_pct,
            "total_costs_usd": total_costs,
            "net_edge_usd": net_edge_pct,
            "fees_pct_of_gross": (fees_pct / gross_edge_pct * 100) if gross_edge_pct > 0 else 0,
            "slippage_pct_of_gross": (slippage_pct / gross_edge_pct * 100) if gross_edge_pct > 0 else 0,
        }
        
        return NetEdgeResult(
            gross_edge_pct=gross_edge_pct,
            fees_pct=fees_pct,
            slippage_pct=slippage_pct,
            freshness_penalty_pct=freshness_penalty_pct,
            net_edge_pct=net_edge_pct,
            net_edge_bps=net_edge_pct * 10000,
            is_alertable=is_alertable,
            alert_threshold_pct=self.alert_threshold_pct,
            cost_breakdown=cost_breakdown,
            rejection_reason=rejection_reason,
        )
    
    def calculate_with_components(
        self,
        gross_edge_pct: float,
        left_venue: str,
        right_venue: str,
        left_notional: float,
        right_notional: float,
        slippage_estimate: float,
        freshness_penalty_pct: float = 0.0,
        fee_calculator: Optional["FeeCalculator"] = None,  # type: ignore # noqa: F821
    ) -> NetEdgeResult:
        """
        Calculate net edge using component calculators.
        
        Args:
            gross_edge_pct: Gross arbitrage edge
            left_venue: Left leg venue name
            right_venue: Right leg venue name
            left_notional: Left leg position size
            right_notional: Right leg position size
            slippage_estimate: Slippage estimate from SlippageModel
            freshness_penalty_pct: Freshness penalty
            fee_calculator: Optional FeeCalculator instance
            
        Returns:
            NetEdgeResult
        """
        from .fee_calculator import FeeCalculator
        
        fee_calc = fee_calculator or FeeCalculator()
        
        # Calculate fees
        fee_result = fee_calc.calculate_total_fees(
            left_venue=left_venue,
            right_venue=right_venue,
            left_notional=left_notional,
            right_notional=right_notional,
        )
        fees_pct = fee_result["total_fees_pct"]
        
        return self.calculate_net_edge(
            gross_edge_pct=gross_edge_pct,
            fees_pct=fees_pct,
            slippage_pct=slippage_estimate,
            freshness_penalty_pct=freshness_penalty_pct,
        )
    
    def quick_check(
        self,
        gross_edge_pct: float,
        fees_pct: float,
        slippage_pct: float,
    ) -> bool:
        """
        Quick check if opportunity is alertable.
        
        Returns True only if net edge > threshold.
        """
        net_edge = gross_edge_pct - fees_pct - slippage_pct
        return net_edge >= self.alert_threshold_pct
    
    def set_alert_threshold(self, threshold_pct: float) -> None:
        """Update alert threshold."""
        self.alert_threshold_pct = threshold_pct
