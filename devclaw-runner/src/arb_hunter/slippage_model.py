"""Slippage Model - Estimate price slippage based on order size vs liquidity."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class SlippageEstimate:
    """Slippage estimate result."""
    
    slippage_pct: float
    """Estimated slippage as percentage."""
    
    slippage_bps: float
    """Estimated slippage in basis points."""
    
    confidence: float
    """Confidence in estimate (0-1)."""
    
    recommended_max_size: float
    """Recommended maximum position size."""
    
    market_impact_warning: bool
    """True if position may cause significant market impact."""


class SlippageModel:
    """
    Square-root slippage model for CLOB and AMM markets.
    
    Based on the observation that slippage scales with the square root of
    order size relative to liquidity depth.
    """
    
    # Conservative slippage parameters
    DEFAULT_K: float = 0.5  # Slippage coefficient
    MAX_SLIPPAGE_PCT: float = 0.02  # 2% max acceptable slippage
    IMPACT_THRESHOLD: float = 0.1  # 10% of liquidity = warning
    
    def __init__(
        self,
        k: float = DEFAULT_K,
        max_slippage_pct: float = MAX_SLIPPAGE_PCT,
    ) -> None:
        """
        Initialize slippage model.
        
        Args:
            k: Slippage coefficient (higher = more slippage)
            max_slippage_pct: Maximum acceptable slippage
        """
        self.k = k
        self.max_slippage_pct = max_slippage_pct
    
    def estimate_slippage(
        self,
        order_size: float,
        available_liquidity: float,
        market_type: str = "clob",
    ) -> SlippageEstimate:
        """
        Estimate slippage for an order.
        
        Uses square root model: slippage ≈ k * sqrt(order_size / liquidity)
        
        Args:
            order_size: Order size in USD
            available_liquidity: Available liquidity at current price level
            market_type: "clob" (order book) or "amm" (automated market maker)
            
        Returns:
            SlippageEstimate with detailed breakdown
        """
        if available_liquidity <= 0:
            return SlippageEstimate(
                slippage_pct=1.0,  # 100% slippage - no liquidity
                slippage_bps=10000,
                confidence=0.0,
                recommended_max_size=0.0,
                market_impact_warning=True,
            )
        
        if order_size <= 0:
            return SlippageEstimate(
                slippage_pct=0.0,
                slippage_bps=0.0,
                confidence=1.0,
                recommended_max_size=available_liquidity * self.IMPACT_THRESHOLD,
                market_impact_warning=False,
            )
        
        # Calculate ratio of order to liquidity
        size_liquidity_ratio = order_size / available_liquidity
        
        # Square root slippage model
        # More conservative for AMMs than CLOBs
        market_multiplier = 1.5 if market_type == "amm" else 1.0
        
        slippage_pct = self.k * market_multiplier * math.sqrt(size_liquidity_ratio)
        
        # Add conservative buffer for volatility
        slippage_pct *= 1.2  # 20% buffer
        
        # Cap at reasonable maximum
        slippage_pct = min(slippage_pct, 0.5)  # Max 50%
        
        # Calculate confidence based on data quality
        confidence = self._calculate_confidence(order_size, available_liquidity)
        
        # Determine market impact warning
        market_impact_warning = size_liquidity_ratio > self.IMPACT_THRESHOLD
        
        # Calculate recommended max size
        recommended_max_size = self._calculate_recommended_max_size(
            available_liquidity, market_type
        )
        
        return SlippageEstimate(
            slippage_pct=slippage_pct,
            slippage_bps=slippage_pct * 10000,
            confidence=confidence,
            recommended_max_size=recommended_max_size,
            market_impact_warning=market_impact_warning,
        )
    
    def estimate_two_leg_slippage(
        self,
        left_size: float,
        left_liquidity: float,
        right_size: float,
        right_liquidity: float,
        left_market_type: str = "clob",
        right_market_type: str = "amm",
    ) -> SlippageEstimate:
        """
        Estimate combined slippage for both legs of arbitrage.
        
        Args:
            left_size: Left leg order size
            left_liquidity: Left leg available liquidity
            right_size: Right leg order size
            right_liquidity: Right leg available liquidity
            left_market_type: Left leg market type
            right_market_type: Right leg market type
            
        Returns:
            Combined slippage estimate
        """
        left_estimate = self.estimate_slippage(
            left_size, left_liquidity, left_market_type
        )
        right_estimate = self.estimate_slippage(
            right_size, right_liquidity, right_market_type
        )
        
        # Combined slippage (conservative: sum them)
        total_slippage_pct = left_estimate.slippage_pct + right_estimate.slippage_pct
        
        # Average confidence
        avg_confidence = (left_estimate.confidence + right_estimate.confidence) / 2
        
        # Min recommended size
        recommended_max = min(
            left_estimate.recommended_max_size,
            right_estimate.recommended_max_size,
        )
        
        # Market impact if either leg has impact
        market_impact = (
            left_estimate.market_impact_warning or 
            right_estimate.market_impact_warning
        )
        
        return SlippageEstimate(
            slippage_pct=total_slippage_pct,
            slippage_bps=total_slippage_pct * 10000,
            confidence=avg_confidence,
            recommended_max_size=recommended_max,
            market_impact_warning=market_impact,
        )
    
    def _calculate_confidence(
        self,
        order_size: float,
        liquidity: float,
    ) -> float:
        """
        Calculate confidence in slippage estimate.
        
        Lower confidence for very large orders relative to liquidity.
        """
        ratio = order_size / liquidity if liquidity > 0 else 1.0
        
        if ratio < 0.01:
            return 0.95  # High confidence for small orders
        elif ratio < 0.05:
            return 0.85
        elif ratio < 0.1:
            return 0.75
        elif ratio < 0.2:
            return 0.60
        elif ratio < 0.5:
            return 0.40
        else:
            return 0.20  # Low confidence for very large orders
    
    def _calculate_recommended_max_size(
        self,
        liquidity: float,
        market_type: str,
    ) -> float:
        """
        Calculate recommended maximum position size.
        
        Conservative: 10% of liquidity for CLOB, 5% for AMM
        """
        if market_type == "amm":
            return liquidity * 0.05
        return liquidity * self.IMPACT_THRESHOLD
    
    def get_safe_order_size(
        self,
        desired_size: float,
        available_liquidity: float,
        max_slippage: Optional[float] = None,
    ) -> float:
        """
        Get safe order size given slippage constraints.
        
        Args:
            desired_size: Desired order size
            available_liquidity: Available liquidity
            max_slippage: Maximum acceptable slippage (default: self.max_slippage_pct)
            
        Returns:
            Safe order size
        """
        max_slippage = max_slippage or self.max_slippage_pct
        
        if available_liquidity <= 0:
            return 0.0
        
        # From slippage = k * sqrt(size / liquidity)
        # Solve for size: size = liquidity * (slippage / k)^2
        safe_ratio = (max_slippage / self.k) ** 2
        max_safe_size = available_liquidity * safe_ratio
        
        return min(desired_size, max_safe_size)
