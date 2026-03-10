"""
Arbitrage Thresholds Configuration.

Defines the thresholds used to filter and validate arbitrage opportunities.
These values determine which opportunities are considered viable for execution.
"""

from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class ArbThresholds:
    """
    Immutable thresholds for arbitrage opportunity filtering.
    
    All thresholds must be met for an opportunity to be considered valid.
    Using frozen dataclass ensures these values don't change unexpectedly.
    
    Attributes:
        min_net_edge_pct: Minimum net edge percentage after all fees
        min_liquidity: Minimum available liquidity in USD
        max_staleness_seconds: Maximum age of price data in seconds
        min_confidence: Minimum confidence score (0.0 - 1.0)
        max_exposure_pct: Maximum exposure as percentage of bankroll
        min_profit_usd: Minimum absolute profit in USD
    """
    
    min_net_edge_pct: float = field(default=2.0)
    """Minimum net edge percentage after accounting for all fees."""
    
    min_liquidity: float = field(default=1000.0)
    """Minimum available liquidity in USD on each leg of the trade."""
    
    max_staleness_seconds: float = field(default=60.0)
    """Maximum acceptable age of price data in seconds."""
    
    min_confidence: float = field(default=0.7)
    """Minimum confidence score from 0.0 to 1.0 based on data quality."""
    
    max_exposure_pct: float = field(default=5.0)
    """Maximum exposure as percentage of total bankroll per position."""
    
    min_profit_usd: float = field(default=5.0)
    """Minimum absolute profit in USD to consider opportunity viable."""
    
    max_total_risk_pct: float = field(default=20.0)
    """Maximum total portfolio risk percentage across all open positions."""
    
    correlation_threshold: float = field(default=0.95)
    """Minimum correlation score to consider two markets as equivalent."""
    
    def __post_init__(self) -> None:
        """Validate threshold values after initialization."""
        self._validate()
    
    def _validate(self) -> None:
        """Run all validation checks."""
        self._validate_range("min_net_edge_pct", self.min_net_edge_pct, 0.0, 100.0)
        self._validate_range("min_liquidity", self.min_liquidity, 0.0, float("inf"))
        self._validate_range("max_staleness_seconds", self.max_staleness_seconds, 1.0, float("inf"))
        self._validate_range("min_confidence", self.min_confidence, 0.0, 1.0)
        self._validate_range("max_exposure_pct", self.max_exposure_pct, 0.0, 100.0)
        self._validate_range("min_profit_usd", self.min_profit_usd, 0.0, float("inf"))
        self._validate_range("max_total_risk_pct", self.max_total_risk_pct, 0.0, 100.0)
        self._validate_range("correlation_threshold", self.correlation_threshold, 0.0, 1.0)
    
    def _validate_range(self, name: str, value: float, min_val: float, max_val: float) -> None:
        """Validate a value is within acceptable range."""
        if not (min_val <= value <= max_val):
            raise ValueError(
                f"{name} must be between {min_val} and {max_val}, got {value}"
            )
    
    def with_adjustments(
        self,
        volatility_factor: float = 1.0,
        liquidity_factor: float = 1.0,
        market_regime: Literal["normal", "volatile", "crisis"] = "normal",
    ) -> Self:
        """
        Create adjusted thresholds based on market conditions.
        
        Args:
            volatility_factor: Multiplier for edge requirements (higher = stricter)
            liquidity_factor: Multiplier for liquidity requirements (higher = stricter)
            market_regime: Current market regime affecting thresholds
            
        Returns:
            New ArbThresholds with adjusted values
        """
        regime_multipliers = {
            "normal": 1.0,
            "volatile": 1.5,
            "crisis": 2.0,
        }
        regime_mult = regime_multipliers.get(market_regime, 1.0)
        
        return self.__class__(
            min_net_edge_pct=self.min_net_edge_pct * volatility_factor * regime_mult,
            min_liquidity=self.min_liquidity * liquidity_factor,
            max_staleness_seconds=self.max_staleness_seconds / regime_mult,
            min_confidence=self.min_confidence * regime_mult,
            max_exposure_pct=self.max_exposure_pct / regime_mult,
            min_profit_usd=self.min_profit_usd,
            max_total_risk_pct=self.max_total_risk_pct / regime_mult,
            correlation_threshold=self.correlation_threshold,
        )
    
    def check_opportunity(
        self,
        net_edge_pct: float,
        liquidity_usd: float,
        data_age_seconds: float,
        confidence: float,
        estimated_profit_usd: float,
    ) -> tuple[bool, list[str]]:
        """
        Check if an opportunity meets all thresholds.
        
        Args:
            net_edge_pct: Calculated net edge percentage
            liquidity_usd: Available liquidity in USD
            data_age_seconds: Age of the price data
            confidence: Confidence score from 0.0 to 1.0
            estimated_profit_usd: Estimated absolute profit
            
        Returns:
            Tuple of (is_valid, list_of_failure_reasons)
        """
        failures: list[str] = []
        
        if net_edge_pct < self.min_net_edge_pct:
            failures.append(
                f"Net edge {net_edge_pct:.2f}% below threshold {self.min_net_edge_pct:.2f}%"
            )
        
        if liquidity_usd < self.min_liquidity:
            failures.append(
                f"Liquidity ${liquidity_usd:,.2f} below threshold ${self.min_liquidity:,.2f}"
            )
        
        if data_age_seconds > self.max_staleness_seconds:
            failures.append(
                f"Data age {data_age_seconds:.1f}s exceeds max {self.max_staleness_seconds:.1f}s"
            )
        
        if confidence < self.min_confidence:
            failures.append(
                f"Confidence {confidence:.2f} below threshold {self.min_confidence:.2f}"
            )
        
        if estimated_profit_usd < self.min_profit_usd:
            failures.append(
                f"Profit ${estimated_profit_usd:.2f} below minimum ${self.min_profit_usd:.2f}"
            )
        
        return len(failures) == 0, failures
    
    def to_dict(self) -> dict[str, float]:
        """Convert thresholds to dictionary for serialization."""
        return {
            "min_net_edge_pct": self.min_net_edge_pct,
            "min_liquidity": self.min_liquidity,
            "max_staleness_seconds": self.max_staleness_seconds,
            "min_confidence": self.min_confidence,
            "max_exposure_pct": self.max_exposure_pct,
            "min_profit_usd": self.min_profit_usd,
            "max_total_risk_pct": self.max_total_risk_pct,
            "correlation_threshold": self.correlation_threshold,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, float]) -> Self:
        """Create thresholds from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def get_default_thresholds() -> ArbThresholds:
    """
    Get default conservative thresholds suitable for most markets.
    
    Returns:
        ArbThresholds with default values
    """
    return ArbThresholds()


def get_aggressive_thresholds() -> ArbThresholds:
    """
    Get aggressive thresholds for high-frequency, lower-margin trading.
    
    Returns:
        ArbThresholds with relaxed constraints
    """
    return ArbThresholds(
        min_net_edge_pct=0.5,
        min_liquidity=500.0,
        max_staleness_seconds=30.0,
        min_confidence=0.5,
        max_exposure_pct=10.0,
        min_profit_usd=1.0,
        max_total_risk_pct=50.0,
        correlation_threshold=0.85,
    )


def get_conservative_thresholds() -> ArbThresholds:
    """
    Get conservative thresholds for risk-averse trading.
    
    Returns:
        ArbThresholds with strict constraints
    """
    return ArbThresholds(
        min_net_edge_pct=5.0,
        min_liquidity=5000.0,
        max_staleness_seconds=30.0,
        min_confidence=0.9,
        max_exposure_pct=2.0,
        min_profit_usd=25.0,
        max_total_risk_pct=10.0,
        correlation_threshold=0.98,
    )


# Type hint for market regime
from typing import Literal
