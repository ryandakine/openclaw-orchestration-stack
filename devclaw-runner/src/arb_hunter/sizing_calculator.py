"""Sizing Calculator - Calculate profit scenarios for different position sizes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

try:
    from .arb_opportunity_schema import ArbOpportunity
except ImportError:
    from arb_opportunity_schema import ArbOpportunity


@dataclass
class SizingScenario:
    """Profit scenario for a specific position size."""
    
    position_size: float
    """Position size in USD."""
    
    gross_profit: float
    """Gross profit before costs."""
    
    fees: float
    """Estimated fees in USD."""
    
    slippage: float
    """Estimated slippage in USD."""
    
    net_profit: float
    """Net profit after all costs."""
    
    net_edge_pct: float
    """Net edge percentage at this size."""
    
    roi_pct: float
    """Return on investment percentage."""
    
    is_viable: bool
    """True if this size is viable (positive net profit)."""


@dataclass
class SizingResult:
    """Complete sizing analysis result."""
    
    max_size: float
    """Maximum recommended position size."""
    
    optimal_size: float
    """Optimal position size for best risk-adjusted return."""
    
    scenarios: list[SizingScenario]
    """Profit scenarios for different sizes."""
    
    at_1k: SizingScenario
    """Scenario at $1,000 position."""
    
    at_10k: Optional[SizingScenario]
    """Scenario at $10,000 position (if viable)."""
    
    at_max: SizingScenario
    """Scenario at maximum size."""
    
    liquidity_constraint: dict[str, float] = field(default_factory=dict)
    """Liquidity constraints applied."""


class SizingCalculator:
    """
    Calculate profit scenarios for various position sizes.
    
    Provides:
    - Profit on $1k, $10k, and max_size
    - Risk-adjusted sizing recommendations
    - Liquidity-aware constraints
    """
    
    # Standard sizes to evaluate
    STANDARD_SIZES: list[float] = [1000.0, 2500.0, 5000.0, 10000.0]
    
    # Risk parameters
    MIN_ROI_PCT: float = 2.0  # Minimum 2% ROI
    RISK_ADJUSTMENT_FACTOR: float = 0.8  # Size down by 20% for safety
    
    def __init__(
        self,
        standard_sizes: Optional[list[float]] = None,
        min_roi_pct: float = MIN_ROI_PCT,
    ) -> None:
        """
        Initialize sizing calculator.
        
        Args:
            standard_sizes: List of position sizes to evaluate
            min_roi_pct: Minimum acceptable ROI percentage
        """
        self.standard_sizes = standard_sizes or self.STANDARD_SIZES
        self.min_roi_pct = min_roi_pct
    
    async def calculate_sizing(
        self,
        opportunity: ArbOpportunity,
        custom_sizes: Optional[list[float]] = None,
    ) -> SizingResult:
        """
        Calculate sizing scenarios for an opportunity.
        
        Args:
            opportunity: The arbitrage opportunity
            custom_sizes: Optional custom sizes to evaluate
            
        Returns:
            SizingResult with all scenarios
        """
        sizes = custom_sizes or self.standard_sizes
        
        # Ensure max_size is included
        max_size = opportunity.max_size
        if max_size not in sizes:
            sizes = sorted(sizes + [max_size])
        
        # Calculate scenarios
        scenarios: list[SizingScenario] = []
        for size in sizes:
            scenario = self._calculate_scenario(opportunity, size)
            scenarios.append(scenario)
        
        # Find optimal size (best risk-adjusted return)
        optimal_size = self._find_optimal_size(scenarios)
        
        # Get specific scenarios
        at_1k = self._get_scenario_at_size(scenarios, 1000.0)
        at_10k = self._get_scenario_at_size(scenarios, 10000.0)
        at_max = self._get_scenario_at_size(scenarios, max_size)
        
        # Liquidity info
        liquidity_constraint = {
            "max_size": max_size,
            "left_liquidity": opportunity.left_leg.get("liquidity", 0),
            "right_liquidity": opportunity.right_leg.get("liquidity", 0),
            "constraint_reason": "liquidity_based",
        }
        
        return SizingResult(
            max_size=max_size,
            optimal_size=optimal_size,
            scenarios=scenarios,
            at_1k=at_1k,
            at_10k=at_10k,
            at_max=at_max,
            liquidity_constraint=liquidity_constraint,
        )
    
    def _calculate_scenario(
        self,
        opportunity: ArbOpportunity,
        position_size: float,
    ) -> SizingScenario:
        """Calculate profit scenario for a specific size."""
        # Cap at max_size
        effective_size = min(position_size, opportunity.max_size)
        
        # Calculate gross profit
        gross_edge = opportunity.gross_edge_pct
        gross_profit = effective_size * gross_edge
        
        # Calculate fees (scale with size)
        fees_pct = opportunity.fees_pct
        fees = effective_size * fees_pct
        
        # Calculate slippage (may increase with size)
        slippage_pct = opportunity.slippage_pct
        # Add size-based slippage increase for large orders
        if effective_size > 5000:
            slippage_pct *= 1.5  # 50% more slippage for large orders
        slippage = effective_size * slippage_pct
        
        # Net profit
        net_profit = gross_profit - fees - slippage
        
        # Net edge at this size
        net_edge_pct = net_profit / effective_size if effective_size > 0 else 0.0
        
        # ROI
        roi_pct = net_edge_pct * 100
        
        # Viability
        is_viable = net_profit > 0 and roi_pct >= self.min_roi_pct
        
        return SizingScenario(
            position_size=effective_size,
            gross_profit=gross_profit,
            fees=fees,
            slippage=slippage,
            net_profit=net_profit,
            net_edge_pct=net_edge_pct,
            roi_pct=roi_pct,
            is_viable=is_viable,
        )
    
    def _find_optimal_size(self, scenarios: list[SizingScenario]) -> float:
        """
        Find optimal position size based on risk-adjusted return.
        
        Prefers smaller sizes with good returns over max size.
        """
        viable_scenarios = [s for s in scenarios if s.is_viable]
        
        if not viable_scenarios:
            return 0.0
        
        # Score based on profit / risk
        # Risk increases with size, so we penalize larger positions
        best_score = -1.0
        best_size = viable_scenarios[0].position_size
        
        for scenario in viable_scenarios:
            # Risk-adjusted score: profit / sqrt(size)
            # This favors smaller positions with good returns
            import math
            risk_factor = math.sqrt(scenario.position_size)
            score = scenario.net_profit / risk_factor if risk_factor > 0 else 0
            
            if score > best_score:
                best_score = score
                best_size = scenario.position_size
        
        # Apply safety factor
        return best_size * self.RISK_ADJUSTMENT_FACTOR
    
    def _get_scenario_at_size(
        self,
        scenarios: list[SizingScenario],
        target_size: float,
    ) -> SizingScenario:
        """Get scenario closest to target size."""
        for scenario in scenarios:
            if abs(scenario.position_size - target_size) < 100:
                return scenario
        
        # Return last scenario if none match
        return scenarios[-1] if scenarios else SizingScenario(
            position_size=0.0,
            gross_profit=0.0,
            fees=0.0,
            slippage=0.0,
            net_profit=0.0,
            net_edge_pct=0.0,
            roi_pct=0.0,
            is_viable=False,
        )
    
    def calculate_position_splits(
        self,
        total_size: float,
        left_price: float,
        right_price: float,
    ) -> tuple[float, float]:
        """
        Calculate how to split position between two legs.
        
        Args:
            total_size: Total position size
            left_price: Price on left leg
            right_price: Price on right leg
            
        Returns:
            Tuple of (left_size, right_size)
        """
        # Split inversely proportional to price
        if left_price <= 0 or right_price <= 0:
            return (total_size / 2, total_size / 2)
        
        left_weight = (1 / left_price) / ((1 / left_price) + (1 / right_price))
        
        left_size = total_size * left_weight
        right_size = total_size - left_size
        
        return (left_size, right_size)
    
    async def get_quick_summary(
        self,
        opportunity: ArbOpportunity,
    ) -> dict[str, float]:
        """Get quick profit summary."""
        sizing = await self.calculate_sizing(opportunity)
        
        return {
            "profit_at_1k": sizing.at_1k.net_profit,
            "profit_at_10k": sizing.at_10k.net_profit if sizing.at_10k else 0.0,
            "profit_at_max": sizing.at_max.net_profit,
            "max_position_size": sizing.max_size,
            "optimal_position_size": sizing.optimal_size,
            "roi_pct": sizing.at_1k.roi_pct,
        }
