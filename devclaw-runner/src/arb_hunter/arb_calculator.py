"""Arbitrage Calculator - Core arbitrage mathematics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ArbCalculationResult:
    """Result of arbitrage calculation."""
    
    is_arbitrage: bool
    """True if arbitrage opportunity exists."""
    
    gross_edge_pct: float
    """Gross edge percentage (before costs)."""
    
    gross_edge_bps: float
    """Gross edge in basis points."""
    
    cost_of_position: float
    """Total cost to enter position (should be < 1.0 for arb)."""
    
    implied_prob_a: float
    """Implied probability from leg A."""
    
    implied_prob_b: float
    """Implied probability from leg B."""
    
    total_implied_prob: float
    """Sum of implied probabilities."""
    
    profit_per_unit: float
    """Profit per $1 invested."""
    
    recommended_stake_a: float
    """Recommended stake for leg A (for $1 total stake)."""
    
    recommended_stake_b: float
    """Recommended stake for leg B (for $1 total stake)."""


class ArbCalculator:
    """
    Core arbitrage mathematics for binary outcome markets.
    
    For binary markets (YES/NO):
    - YES @ 0.42 + NO @ 0.61 = cost 1.03 → No arb (cost > 1.0)
    - YES @ 0.42 + NO @ 0.55 = cost 0.97 → Arb exists (cost < 1.0)
    
    Edge = 1.0 - cost (for cost < 1.0)
    """
    
    MIN_EDGE_PCT: float = 0.005  # 0.5% minimum to consider
    
    def __init__(self, min_edge_pct: float = MIN_EDGE_PCT) -> None:
        """
        Initialize arbitrage calculator.
        
        Args:
            min_edge_pct: Minimum edge to consider as arbitrage
        """
        self.min_edge_pct = min_edge_pct
    
    def calculate_from_prices(
        self,
        yes_price: float,
        no_price: float,
    ) -> ArbCalculationResult:
        """
        Calculate arbitrage from YES/NO prices.
        
        Args:
            yes_price: Price of YES (0.0 to 1.0)
            no_price: Price of NO (0.0 to 1.0)
            
        Returns:
            ArbCalculationResult
            
        Example:
            >>> calc = ArbCalculator()
            >>> result = calc.calculate_from_prices(0.42, 0.55)
            >>> result.is_arbitrage
            True
            >>> result.gross_edge_pct
            0.03  # 3% edge
        """
        # Normalize prices to be positive
        yes_price = max(0.0, min(1.0, yes_price))
        no_price = max(0.0, min(1.0, no_price))
        
        # Cost of position
        cost = yes_price + no_price
        
        # Check for arbitrage
        is_arbitrage = cost < 1.0
        
        # Calculate edge
        if is_arbitrage:
            gross_edge_pct = 1.0 - cost
        else:
            gross_edge_pct = 0.0
        
        # Calculate recommended stakes for $1 total position
        # Stake ratio inversely proportional to price
        if cost > 0:
            stake_a = no_price / cost  # Stake on YES
            stake_b = yes_price / cost  # Stake on NO
        else:
            stake_a = 0.5
            stake_b = 0.5
        
        # Profit per unit
        profit_per_unit = gross_edge_pct if is_arbitrage else 0.0
        
        return ArbCalculationResult(
            is_arbitrage=is_arbitrage and gross_edge_pct >= self.min_edge_pct,
            gross_edge_pct=gross_edge_pct,
            gross_edge_bps=gross_edge_pct * 10000,
            cost_of_position=cost,
            implied_prob_a=yes_price,
            implied_prob_b=no_price,
            total_implied_prob=cost,
            profit_per_unit=profit_per_unit,
            recommended_stake_a=stake_a,
            recommended_stake_b=stake_b,
        )
    
    def calculate_from_american_odds(
        self,
        odds_a: float,
        odds_b: float,
    ) -> ArbCalculationResult:
        """
        Calculate arbitrage from American odds.
        
        Args:
            odds_a: American odds for outcome A (e.g., -150, +200)
            odds_b: American odds for outcome B
            
        Returns:
            ArbCalculationResult
        """
        # Convert American odds to implied probability
        prob_a = self._american_to_implied_prob(odds_a)
        prob_b = self._american_to_implied_prob(odds_b)
        
        # Use price calculation
        result = self.calculate_from_prices(prob_a, prob_b)
        
        return result
    
    def calculate_cross_market_arb(
        self,
        left_price: float,
        left_side: str,  # "yes" or "no"
        right_price: float,
        right_side: str,  # "yes" or "no"
    ) -> ArbCalculationResult:
        """
        Calculate arbitrage for cross-market opportunities.
        
        Args:
            left_price: Price on left venue
            left_side: Side on left venue ("yes" or "no")
            right_price: Price on right venue
            right_side: Side on right venue ("yes" or "no")
            
        Returns:
            ArbCalculationResult
        """
        # Normalize to YES/NO prices
        if left_side.lower() == "yes":
            yes_price = left_price
            no_price = right_price if right_side.lower() == "no" else (1 - right_price)
        else:
            no_price = left_price
            yes_price = right_price if right_side.lower() == "yes" else (1 - right_price)
        
        return self.calculate_from_prices(yes_price, no_price)
    
    def _american_to_implied_prob(self, odds: float) -> float:
        """Convert American odds to implied probability."""
        if odds > 0:
            return 100 / (odds + 100)
        else:
            return abs(odds) / (abs(odds) + 100)
    
    def _decimal_to_implied_prob(self, odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if odds <= 1.0:
            return 1.0
        return 1.0 / odds
    
    def calculate_stake_weights(
        self,
        price_a: float,
        price_b: float,
    ) -> tuple[float, float]:
        """
        Calculate optimal stake weights for arbitrage.
        
        Returns weights that sum to 1.0 for equal profit either way.
        
        Args:
            price_a: Price/probability for outcome A
            price_b: Price/probability for outcome B
            
        Returns:
            Tuple of (weight_a, weight_b)
        """
        if price_a <= 0 or price_b <= 0:
            return (0.5, 0.5)
        
        # Weight inversely proportional to price
        inv_a = 1.0 / price_a
        inv_b = 1.0 / price_b
        total_inv = inv_a + inv_b
        
        weight_a = inv_a / total_inv
        weight_b = inv_b / total_inv
        
        return (weight_a, weight_b)
    
    def expected_profit(
        self,
        stake: float,
        gross_edge_pct: float,
    ) -> float:
        """Calculate expected profit for a given stake."""
        return stake * gross_edge_pct
