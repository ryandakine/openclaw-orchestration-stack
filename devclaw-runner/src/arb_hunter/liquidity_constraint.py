"""Liquidity Constraint - Calculate maximum position sizes based on liquidity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class LiquidityResult:
    """Result of liquidity constraint calculation."""
    
    max_position_size: float
    """Maximum position size in USD."""
    
    left_leg_max: float
    """Maximum for left leg based on its liquidity."""
    
    right_leg_max: float
    """Maximum for right leg based on its liquidity."""
    
    constraint_reason: str
    """Which constraint is binding."""
    
    left_utilization_pct: float
    """Percentage of left leg liquidity used at max size."""
    
    right_utilization_pct: float
    """Percentage of right leg liquidity used at max size."""
    
    sufficient_liquidity: bool
    """True if both legs have sufficient liquidity."""


class LiquidityConstraint:
    """
    Liquidity-based position sizing constraints.
    
    Conservative approach:
    - Max position = min(leg_liquidity × 0.1, $10k)
    - Avoid market impact by keeping orders small relative to book depth
    - $10k hard cap to limit exposure
    """
    
    # Hard limits
    ABSOLUTE_MAX_SIZE: float = 10000.0  # $10k hard cap
    LIQUIDITY_UTILIZATION_MAX: float = 0.10  # 10% of available liquidity
    MIN_LIQUIDITY_THRESHOLD: float = 10000.0  # $10k minimum per leg
    
    def __init__(
        self,
        absolute_max: float = ABSOLUTE_MAX_SIZE,
        utilization_max: float = LIQUIDITY_UTILIZATION_MAX,
        min_liquidity: float = MIN_LIQUIDITY_THRESHOLD,
    ) -> None:
        """
        Initialize liquidity constraint calculator.
        
        Args:
            absolute_max: Hard cap on position size
            utilization_max: Max percentage of liquidity to use
            min_liquidity: Minimum liquidity required per leg
        """
        self.absolute_max = absolute_max
        self.utilization_max = utilization_max
        self.min_liquidity = min_liquidity
    
    def calculate_max_position(
        self,
        left_liquidity: float,
        right_liquidity: float,
        left_price: float = 0.5,
        right_price: float = 0.5,
    ) -> LiquidityResult:
        """
        Calculate maximum position size based on liquidity constraints.
        
        Args:
            left_liquidity: Available liquidity on left leg
            right_liquidity: Available liquidity on right leg
            left_price: Current price on left leg (for notional calc)
            right_price: Current price on right leg (for notional calc)
            
        Returns:
            LiquidityResult with constraints
        """
        # Calculate max based on liquidity utilization
        left_max_from_liq = left_liquidity * self.utilization_max
        right_max_from_liq = right_liquidity * self.utilization_max
        
        # The limiting leg determines max position
        liquidity_constrained_max = min(left_max_from_liq, right_max_from_liq)
        
        # Apply hard cap
        max_position = min(liquidity_constrained_max, self.absolute_max)
        
        # Determine which constraint is binding
        if max_position >= self.absolute_max:
            constraint_reason = "absolute_cap"
        elif left_max_from_liq <= right_max_from_liq:
            constraint_reason = "left_leg_liquidity"
        else:
            constraint_reason = "right_leg_liquidity"
        
        # Calculate utilization at max position
        left_utilization = (
            max_position / left_liquidity if left_liquidity > 0 else 1.0
        )
        right_utilization = (
            max_position / right_liquidity if right_liquidity > 0 else 1.0
        )
        
        # Check sufficient liquidity
        sufficient = (
            left_liquidity >= self.min_liquidity and
            right_liquidity >= self.min_liquidity
        )
        
        return LiquidityResult(
            max_position_size=max_position,
            left_leg_max=left_max_from_liq,
            right_leg_max=right_max_from_liq,
            constraint_reason=constraint_reason,
            left_utilization_pct=left_utilization,
            right_utilization_pct=right_utilization,
            sufficient_liquidity=sufficient,
        )
    
    def calculate_for_odds(
        self,
        left_liquidity: float,
        left_odds: float,
        right_liquidity: float,
        right_odds: float,
    ) -> LiquidityResult:
        """
        Calculate max position for American odds format.
        
        Converts odds to implied probability for notional sizing.
        """
        # Convert American odds to probability
        def odds_to_prob(odds: float) -> float:
            if odds > 0:
                return 100 / (odds + 100)
            else:
                return abs(odds) / (abs(odds) + 100)
        
        left_prob = odds_to_prob(left_odds)
        right_prob = odds_to_prob(right_odds)
        
        return self.calculate_max_position(
            left_liquidity=left_liquidity,
            right_liquidity=right_liquidity,
            left_price=left_prob,
            right_price=right_prob,
        )
    
    def has_sufficient_liquidity(
        self,
        left_liquidity: float,
        right_liquidity: float,
    ) -> bool:
        """Quick check if both legs have sufficient liquidity."""
        return (
            left_liquidity >= self.min_liquidity and
            right_liquidity >= self.min_liquidity
        )
    
    def get_liquidity_score(
        self,
        left_liquidity: float,
        right_liquidity: float,
    ) -> float:
        """
        Calculate a liquidity quality score (0-1).
        
        Higher is better. Based on how much above minimum each leg is.
        """
        if left_liquidity < self.min_liquidity or right_liquidity < self.min_liquidity:
            return 0.0
        
        # Score based on geometric mean relative to minimum
        import math
        geo_mean = math.sqrt(left_liquidity * right_liquidity)
        score = min(geo_mean / (self.min_liquidity * 2), 1.0)
        
        return score
    
    def estimate_market_impact(
        self,
        order_size: float,
        left_liquidity: float,
        right_liquidity: float,
    ) -> dict[str, float]:
        """
        Estimate market impact for a given order size.
        
        Returns impact metrics for both legs.
        """
        left_impact = order_size / left_liquidity if left_liquidity > 0 else 1.0
        right_impact = order_size / right_liquidity if right_liquidity > 0 else 1.0
        
        return {
            "left_impact_pct": left_impact * 100,
            "right_impact_pct": right_impact * 100,
            "max_impact_pct": max(left_impact, right_impact) * 100,
            "impact_warning": max(left_impact, right_impact) > self.utilization_max,
        }
