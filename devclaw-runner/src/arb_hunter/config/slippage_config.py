"""
Slippage Configuration Models.

Defines slippage estimation models for trading venues.
Slippage represents the difference between expected and actual execution price.
"""

from dataclasses import dataclass, field
from typing import Protocol, Self
import math


class SlippageModel(Protocol):
    """Protocol for slippage models."""
    
    def estimate_slippage_pct(
        self,
        trade_size_usd: float,
        available_liquidity_usd: float,
        **kwargs
    ) -> float:
        """Estimate slippage percentage for a trade."""
        ...


@dataclass(frozen=True, slots=True)
class LiquidityBasedSlippage:
    """
    Slippage model based on trade size relative to available liquidity.
    
    Slippage increases as trade size becomes a larger percentage of
    available liquidity. Uses an inverse relationship with liquidity.
    """
    
    base_bps: float = field(default=10.0)
    """Base slippage in basis points (bps = 0.01%)."""
    
    liquidity_factor: float = field(default=10000.0)
    """
    Factor controlling how quickly slippage increases with trade size.
    Higher values mean slippage increases faster as liquidity decreases.
    """
    
    max_slippage_bps: float = field(default=100.0)
    """Maximum slippage cap in basis points (1% default)."""
    
    min_slippage_bps: float = field(default=1.0)
    """Minimum slippage floor in basis points."""
    
    curve_exponent: float = field(default=1.5)
    """
    Exponent for the slippage curve.
    1.0 = linear, 1.5 = slightly convex, 2.0 = quadratic
    """
    
    def __post_init__(self) -> None:
        """Validate slippage parameters."""
        if self.base_bps < 0:
            raise ValueError(f"base_bps must be non-negative, got {self.base_bps}")
        if self.liquidity_factor < 0:
            raise ValueError(f"liquidity_factor must be non-negative, got {self.liquidity_factor}")
        if self.max_slippage_bps <= self.min_slippage_bps:
            raise ValueError("max_slippage_bps must be greater than min_slippage_bps")
        if not (0.5 <= self.curve_exponent <= 3.0):
            raise ValueError(f"curve_exponent should be 0.5-3.0, got {self.curve_exponent}")
    
    def estimate_slippage_pct(
        self,
        trade_size_usd: float,
        available_liquidity_usd: float,
        **kwargs
    ) -> float:
        """
        Estimate slippage percentage for a trade.
        
        Formula:
            slippage_bps = base_bps + liquidity_factor * (trade_size / liquidity) ^ exponent
        
        Args:
            trade_size_usd: Size of the trade in USD
            available_liquidity_usd: Available liquidity in the order book
            **kwargs: Additional parameters (ignored by this model)
            
        Returns:
            Estimated slippage as a percentage
        """
        if available_liquidity_usd <= 0:
            return self.max_slippage_bps / 100.0  # Return max if no liquidity
        
        if trade_size_usd <= 0:
            return self.min_slippage_bps / 100.0
        
        # Calculate trade size to liquidity ratio
        size_ratio = trade_size_usd / available_liquidity_usd
        
        # Apply curve exponent
        size_impact = math.pow(size_ratio, self.curve_exponent)
        
        # Calculate slippage in basis points
        slippage_bps = self.base_bps + (self.liquidity_factor * size_impact)
        
        # Apply min/max bounds
        slippage_bps = max(self.min_slippage_bps, min(slippage_bps, self.max_slippage_bps))
        
        # Convert to percentage
        return slippage_bps / 100.0
    
    def estimate_slippage_bps(
        self,
        trade_size_usd: float,
        available_liquidity_usd: float,
        **kwargs
    ) -> float:
        """
        Estimate slippage in basis points.
        
        Args:
            trade_size_usd: Size of the trade in USD
            available_liquidity_usd: Available liquidity
            **kwargs: Additional parameters
            
        Returns:
            Estimated slippage in basis points
        """
        return self.estimate_slippage_pct(trade_size_usd, available_liquidity_usd, **kwargs) * 100.0
    
    def estimate_cost_usd(
        self,
        trade_size_usd: float,
        available_liquidity_usd: float,
        **kwargs
    ) -> float:
        """
        Estimate slippage cost in USD.
        
        Args:
            trade_size_usd: Size of the trade in USD
            available_liquidity_usd: Available liquidity
            **kwargs: Additional parameters
            
        Returns:
            Estimated slippage cost in USD
        """
        slippage_pct = self.estimate_slippage_pct(trade_size_usd, available_liquidity_usd, **kwargs)
        return trade_size_usd * (slippage_pct / 100.0)
    
    def max_safe_trade_size(
        self,
        available_liquidity_usd: float,
        max_acceptable_slippage_bps: float,
    ) -> float:
        """
        Calculate maximum trade size for a given slippage tolerance.
        
        Args:
            available_liquidity_usd: Available liquidity
            max_acceptable_slippage_bps: Maximum acceptable slippage in bps
            
        Returns:
            Maximum recommended trade size in USD
        """
        if max_acceptable_slippage_bps <= self.base_bps:
            return 0.0
        
        # Inverse of the slippage formula
        remaining_bps = max_acceptable_slippage_bps - self.base_bps
        
        if remaining_bps <= 0:
            return 0.0
        
        # Solve for trade size: remaining_bps = liquidity_factor * (size / liq) ^ exponent
        # size = liq * (remaining_bps / liquidity_factor) ^ (1 / exponent)
        
        ratio = remaining_bps / self.liquidity_factor
        size_ratio = math.pow(ratio, 1.0 / self.curve_exponent)
        
        return available_liquidity_usd * size_ratio


@dataclass(frozen=True, slots=True)
class FixedSlippage:
    """Fixed slippage model for venues with predictable execution."""
    
    slippage_bps: float = field(default=5.0)
    """Fixed slippage in basis points."""
    
    def __post_init__(self) -> None:
        """Validate slippage."""
        if self.slippage_bps < 0:
            raise ValueError(f"slippage_bps must be non-negative, got {self.slippage_bps}")
    
    def estimate_slippage_pct(
        self,
        trade_size_usd: float,
        available_liquidity_usd: float = 0,
        **kwargs
    ) -> float:
        """Return fixed slippage percentage."""
        return self.slippage_bps / 100.0


@dataclass(frozen=True, slots=True)
class VenueSpecificSlippage:
    """
    Slippage configuration for specific venues.
    
    Different venues have different liquidity characteristics.
    """
    
    # Prediction markets typically have lower slippage due to CLOB structure
    polymarket: LiquidityBasedSlippage = field(
        default_factory=lambda: LiquidityBasedSlippage(
            base_bps=5.0,
            liquidity_factor=5000.0,
            max_slippage_bps=50.0,
            curve_exponent=1.2,
        )
    )
    
    kalshi: LiquidityBasedSlippage = field(
        default_factory=lambda: LiquidityBasedSlippage(
            base_bps=8.0,
            liquidity_factor=8000.0,
            max_slippage_bps=75.0,
            curve_exponent=1.3,
        )
    )
    
    predictit: LiquidityBasedSlippage = field(
        default_factory=lambda: LiquidityBasedSlippage(
            base_bps=15.0,
            liquidity_factor=15000.0,
            max_slippage_bps=150.0,
            curve_exponent=1.5,
        )
    )
    
    # Sportsbooks have wider spreads but fixed execution
    sportsbook: FixedSlippage = field(
        default_factory=lambda: FixedSlippage(slippage_bps=10.0)
    )
    
    def get_model(self, venue: str) -> LiquidityBasedSlippage | FixedSlippage:
        """
        Get slippage model for a specific venue.
        
        Args:
            venue: Venue name
            
        Returns:
            Slippage model for the venue
            
        Raises:
            ValueError: If venue is not recognized
        """
        venue_map: dict[str, LiquidityBasedSlippage | FixedSlippage] = {
            "polymarket": self.polymarket,
            "kalshi": self.kalshi,
            "predictit": self.predictit,
            "sportsbook": self.sportsbook,
        }
        
        venue_lower = venue.lower()
        if venue_lower not in venue_map:
            raise ValueError(f"Unknown venue: {venue}")
        
        return venue_map[venue_lower]
    
    def estimate_slippage(
        self,
        venue: str,
        trade_size_usd: float,
        available_liquidity_usd: float,
        **kwargs
    ) -> float:
        """
        Estimate slippage for a specific venue.
        
        Args:
            venue: Venue name
            trade_size_usd: Trade size
            available_liquidity_usd: Available liquidity
            **kwargs: Additional parameters
            
        Returns:
            Estimated slippage percentage
        """
        model = self.get_model(venue)
        return model.estimate_slippage_pct(trade_size_usd, available_liquidity_usd, **kwargs)


@dataclass(frozen=True, slots=True)
class SlippageConfig:
    """
    Complete slippage configuration.
    
    Combines general slippage parameters with venue-specific models.
    """
    
    # Default slippage model parameters
    base_bps: float = field(default=10.0)
    liquidity_factor: float = field(default=10000.0)
    max_slippage_bps: float = field(default=100.0)
    min_slippage_bps: float = field(default=1.0)
    
    # Venue-specific configurations
    venue_slippage: VenueSpecificSlippage = field(
        default_factory=VenueSpecificSlippage
    )
    
    # Safety factor for estimates (multiply slippage by this for conservative estimates)
    safety_factor: float = field(default=1.2)
    """Safety multiplier for slippage estimates (1.2 = 20% buffer)."""
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.safety_factor < 1.0:
            raise ValueError(f"safety_factor should be >= 1.0, got {self.safety_factor}")
    
    def estimate_slippage(
        self,
        venue: str,
        trade_size_usd: float,
        available_liquidity_usd: float,
        apply_safety: bool = True,
        **kwargs
    ) -> float:
        """
        Estimate slippage for a trade with optional safety buffer.
        
        Args:
            venue: Venue name
            trade_size_usd: Trade size in USD
            available_liquidity_usd: Available liquidity
            apply_safety: Whether to apply safety factor
            **kwargs: Additional parameters
            
        Returns:
            Estimated slippage percentage
        """
        base_slippage = self.venue_slippage.estimate_slippage(
            venue, trade_size_usd, available_liquidity_usd, **kwargs
        )
        
        if apply_safety:
            return base_slippage * self.safety_factor
        return base_slippage
    
    def estimate_total_cost(
        self,
        venue: str,
        trade_size_usd: float,
        available_liquidity_usd: float,
        apply_safety: bool = True,
        **kwargs
    ) -> float:
        """
        Estimate total slippage cost in USD.
        
        Args:
            venue: Venue name
            trade_size_usd: Trade size
            available_liquidity_usd: Available liquidity
            apply_safety: Whether to apply safety factor
            **kwargs: Additional parameters
            
        Returns:
            Estimated slippage cost in USD
        """
        slippage_pct = self.estimate_slippage(
            venue, trade_size_usd, available_liquidity_usd, apply_safety, **kwargs
        )
        return trade_size_usd * (slippage_pct / 100.0)
    
    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "base_bps": self.base_bps,
            "liquidity_factor": self.liquidity_factor,
            "max_slippage_bps": self.max_slippage_bps,
            "min_slippage_bps": self.min_slippage_bps,
            "safety_factor": self.safety_factor,
            "venue_slippage": {
                "polymarket": {
                    "base_bps": self.venue_slippage.polymarket.base_bps,
                    "liquidity_factor": self.venue_slippage.polymarket.liquidity_factor,
                },
                "kalshi": {
                    "base_bps": self.venue_slippage.kalshi.base_bps,
                    "liquidity_factor": self.venue_slippage.kalshi.liquidity_factor,
                },
                "predictit": {
                    "base_bps": self.venue_slippage.predictit.base_bps,
                    "liquidity_factor": self.venue_slippage.predictit.liquidity_factor,
                },
                "sportsbook": {
                    "slippage_bps": self.venue_slippage.sportsbook.slippage_bps,
                },
            },
        }


def get_default_slippage() -> SlippageConfig:
    """
    Get default slippage configuration.
    
    Returns:
        SlippageConfig with default values
    """
    return SlippageConfig()


def get_conservative_slippage() -> SlippageConfig:
    """
    Get conservative slippage configuration with higher safety factors.
    
    Returns:
        SlippageConfig with conservative estimates
    """
    return SlippageConfig(
        base_bps=15.0,
        liquidity_factor=12000.0,
        max_slippage_bps=150.0,
        safety_factor=1.5,
        venue_slippage=VenueSpecificSlippage(
            polymarket=LiquidityBasedSlippage(
                base_bps=8.0,
                liquidity_factor=6000.0,
                max_slippage_bps=75.0,
            ),
            kalshi=LiquidityBasedSlippage(
                base_bps=12.0,
                liquidity_factor=10000.0,
                max_slippage_bps=100.0,
            ),
            predictit=LiquidityBasedSlippage(
                base_bps=25.0,
                liquidity_factor=20000.0,
                max_slippage_bps=200.0,
            ),
            sportsbook=FixedSlippage(slippage_bps=15.0),
        ),
    )
