"""
Fee Configuration Models.

Defines fee structures for various trading venues including prediction markets
and sportsbooks. Supports both maker/taker fees and vig-based models.
"""

from dataclasses import dataclass, field
from typing import Protocol, Self
from enum import Enum, auto


class FeeModelType(Enum):
    """Types of fee models supported."""
    MAKER_TAKER = auto()  # Separate maker and taker fees
    VIG = auto()           # Built into odds (sportsbook style)
    FLAT = auto()          # Flat fee per trade
    TIERED = auto()        # Volume-based tiered fees


class FeeCalculator(Protocol):
    """Protocol for fee calculators."""
    
    def calculate_fee(self, notional: float, is_maker: bool = False) -> float:
        """Calculate fee for a given notional amount."""
        ...
    
    def effective_cost(self, notional: float, is_maker: bool = False) -> float:
        """Calculate total cost including fees."""
        ...


@dataclass(frozen=True, slots=True)
class MakerTakerFees:
    """
    Standard maker/taker fee structure.
    
    Common in prediction markets like Polymarket and Kalshi.
    """
    
    maker_fee_pct: float = field(default=0.0)
    """Fee percentage for maker orders (providing liquidity)."""
    
    taker_fee_pct: float = field(default=0.0)
    """Fee percentage for taker orders (taking liquidity)."""
    
    def __post_init__(self) -> None:
        """Validate fee percentages."""
        if not (0 <= self.maker_fee_pct <= 100):
            raise ValueError(f"maker_fee_pct must be 0-100, got {self.maker_fee_pct}")
        if not (0 <= self.taker_fee_pct <= 100):
            raise ValueError(f"taker_fee_pct must be 0-100, got {self.taker_fee_pct}")
    
    def calculate_fee(self, notional: float, is_maker: bool = False) -> float:
        """
        Calculate fee for a trade.
        
        Args:
            notional: Trade notional amount in USD
            is_maker: Whether this is a maker order
            
        Returns:
            Fee amount in USD
        """
        fee_pct = self.maker_fee_pct if is_maker else self.taker_fee_pct
        return notional * (fee_pct / 100.0)
    
    def effective_cost(self, notional: float, is_maker: bool = False) -> float:
        """Calculate total cost including fees."""
        return notional + self.calculate_fee(notional, is_maker)


@dataclass(frozen=True, slots=True)
class VigModel:
    """
    Sportsbook vig (vigorish) model.
    
    Sportsbooks build profit margin into the odds rather than charging
    explicit fees. The vig represents the bookmaker's edge.
    """
    
    vig_pct: float = field(default=4.5)
    """Built-in vig percentage (typical range: 3.5% - 6%)."""
    
    def __post_init__(self) -> None:
        """Validate vig percentage."""
        if not (0 <= self.vig_pct <= 20):
            raise ValueError(f"vig_pct must be 0-20, got {self.vig_pct}")
    
    def remove_vig(self, odds: float) -> float:
        """
        Remove vig from odds to get true implied probability.
        
        Args:
            odds: American odds (e.g., -110, +150)
            
        Returns:
            Vig-free implied probability
        """
        # Convert to implied probability
        if odds < 0:
            implied_prob = abs(odds) / (abs(odds) + 100)
        else:
            implied_prob = 100 / (odds + 100)
        
        # Remove vig
        return implied_prob / (1 + self.vig_pct / 100)
    
    def fair_odds(self, odds: float) -> float:
        """
        Calculate fair odds with vig removed.
        
        Args:
            odds: American odds
            
        Returns:
            Fair American odds
        """
        true_prob = self.remove_vig(odds)
        
        if true_prob > 0.5:
            return round(-100 * true_prob / (1 - true_prob))
        else:
            return round(100 * (1 - true_prob) / true_prob)
    
    def calculate_fee(self, notional: float, is_maker: bool = False) -> float:
        """
        Calculate implicit fee from vig.
        
        The vig is already priced into the odds, so this represents
        the expected cost compared to fair odds.
        """
        return notional * (self.vig_pct / 100.0)
    
    def effective_cost(self, notional: float, is_maker: bool = False) -> float:
        """For vig model, cost is just the notional (fees are in odds)."""
        return notional


@dataclass(frozen=True, slots=True)
class FlatFee:
    """Flat fee per trade regardless of size."""
    
    fee_usd: float = field(default=0.0)
    """Flat fee in USD per trade."""
    
    max_fee_cap_usd: float | None = None
    """Optional maximum fee cap."""
    
    def __post_init__(self) -> None:
        """Validate flat fee."""
        if self.fee_usd < 0:
            raise ValueError(f"fee_usd must be non-negative, got {self.fee_usd}")
    
    def calculate_fee(self, notional: float, is_maker: bool = False) -> float:
        """Calculate flat fee (independent of notional)."""
        fee = self.fee_usd
        if self.max_fee_cap_usd is not None:
            fee = min(fee, self.max_fee_cap_usd)
        return fee
    
    def effective_cost(self, notional: float, is_maker: bool = False) -> float:
        """Calculate total cost including flat fee."""
        return notional + self.calculate_fee(notional, is_maker)


@dataclass(frozen=True, slots=True)
class FeeConfig:
    """
    Complete fee configuration for all supported venues.
    
    This is the main configuration class that aggregates fee structures
    for all trading venues used by the arbitrage hunter.
    """
    
    # Prediction Markets - Maker/Taker Fee Models
    polymarket: MakerTakerFees = field(
        default_factory=lambda: MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=2.0)
    )
    
    kalshi: MakerTakerFees = field(
        default_factory=lambda: MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=0.5)
    )
    
    predictit: MakerTakerFees = field(
        default_factory=lambda: MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=10.0)
    )
    
    # Sportsbooks - Vig Model
    sportsbook: VigModel = field(
        default_factory=lambda: VigModel(vig_pct=4.5)
    )
    
    # Withdrawal Fees (flat fees)
    withdrawal_fees: dict[str, float] = field(
        default_factory=lambda: {
            "polymarket": 0.0,
            "kalshi": 0.0,
            "predictit": 5.0,
        }
    )
    
    # Deposit fees (usually 0 but some venues charge)
    deposit_fees: dict[str, float] = field(
        default_factory=lambda: {
            "polymarket": 0.0,
            "kalshi": 0.0,
            "predictit": 0.0,
        }
    )
    
    def __post_init__(self) -> None:
        """Validate withdrawal and deposit fee dictionaries."""
        for venue, fee in self.withdrawal_fees.items():
            if fee < 0:
                raise ValueError(f"Withdrawal fee for {venue} cannot be negative")
        for venue, fee in self.deposit_fees.items():
            if fee < 0:
                raise ValueError(f"Deposit fee for {venue} cannot be negative")
    
    def get_trading_fees(self, venue: str) -> MakerTakerFees | VigModel:
        """
        Get trading fee model for a specific venue.
        
        Args:
            venue: Venue name (polymarket, kalshi, predictit, sportsbook)
            
        Returns:
            Fee model for the venue
            
        Raises:
            ValueError: If venue is not recognized
        """
        venue_map: dict[str, MakerTakerFees | VigModel] = {
            "polymarket": self.polymarket,
            "kalshi": self.kalshi,
            "predictit": self.predictit,
            "sportsbook": self.sportsbook,
        }
        
        venue_lower = venue.lower()
        if venue_lower not in venue_map:
            raise ValueError(f"Unknown venue: {venue}")
        
        return venue_map[venue_lower]
    
    def calculate_roundtrip_fees(
        self,
        venue_a: str,
        venue_b: str,
        notional_a: float,
        notional_b: float,
        is_maker_a: bool = False,
        is_maker_b: bool = False,
    ) -> dict[str, float]:
        """
        Calculate total fees for a roundtrip arbitrage trade.
        
        Args:
            venue_a: First venue name
            venue_b: Second venue name
            notional_a: Notional amount for venue A
            notional_b: Notional amount for venue B
            is_maker_a: Whether venue A order is maker
            is_maker_b: Whether venue B order is maker
            
        Returns:
            Dictionary with fee breakdown
        """
        fees_a = self.get_trading_fees(venue_a)
        fees_b = self.get_trading_fees(venue_b)
        
        fee_a = fees_a.calculate_fee(notional_a, is_maker_a)
        fee_b = fees_b.calculate_fee(notional_b, is_maker_b)
        
        return {
            "venue_a_fee": fee_a,
            "venue_b_fee": fee_b,
            "total_trading_fees": fee_a + fee_b,
            "venue_a_withdrawal": self.withdrawal_fees.get(venue_a.lower(), 0.0),
            "venue_b_withdrawal": self.withdrawal_fees.get(venue_b.lower(), 0.0),
            "total_withdrawal_fees": (
                self.withdrawal_fees.get(venue_a.lower(), 0.0) +
                self.withdrawal_fees.get(venue_b.lower(), 0.0)
            ),
            "total_fees": fee_a + fee_b +
                         self.withdrawal_fees.get(venue_a.lower(), 0.0) +
                         self.withdrawal_fees.get(venue_b.lower(), 0.0),
        }
    
    def estimate_total_cost_pct(
        self,
        venue: str,
        notional: float,
        include_withdrawal: bool = True,
        is_maker: bool = False,
    ) -> float:
        """
        Estimate total cost as percentage of notional.
        
        Args:
            venue: Venue name
            notional: Trade notional
            include_withdrawal: Whether to include withdrawal fees
            is_maker: Whether order is maker
            
        Returns:
            Total cost as percentage
        """
        fees = self.get_trading_fees(venue)
        trading_fee = fees.calculate_fee(notional, is_maker)
        
        total_cost = trading_fee
        if include_withdrawal:
            total_cost += self.withdrawal_fees.get(venue.lower(), 0.0)
        
        return (total_cost / notional) * 100.0 if notional > 0 else 0.0
    
    def to_dict(self) -> dict:
        """Convert fee config to dictionary."""
        return {
            "polymarket": {
                "maker_fee_pct": self.polymarket.maker_fee_pct,
                "taker_fee_pct": self.polymarket.taker_fee_pct,
            },
            "kalshi": {
                "maker_fee_pct": self.kalshi.maker_fee_pct,
                "taker_fee_pct": self.kalshi.taker_fee_pct,
            },
            "predictit": {
                "maker_fee_pct": self.predictit.maker_fee_pct,
                "taker_fee_pct": self.predictit.taker_fee_pct,
            },
            "sportsbook": {
                "vig_pct": self.sportsbook.vig_pct,
            },
            "withdrawal_fees": self.withdrawal_fees,
            "deposit_fees": self.deposit_fees,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create fee config from dictionary."""
        return cls(
            polymarket=MakerTakerFees(**data.get("polymarket", {})),
            kalshi=MakerTakerFees(**data.get("kalshi", {})),
            predictit=MakerTakerFees(**data.get("predictit", {})),
            sportsbook=VigModel(**data.get("sportsbook", {})),
            withdrawal_fees=data.get("withdrawal_fees", {}),
            deposit_fees=data.get("deposit_fees", {}),
        )


def get_default_fees() -> FeeConfig:
    """
    Get default fee configuration with industry-standard rates.
    
    Returns:
        FeeConfig with default values
    """
    return FeeConfig()


def get_low_fee_config() -> FeeConfig:
    """
    Get fee configuration assuming VIP/maker status on all venues.
    
    Returns:
        FeeConfig with reduced fees
    """
    return FeeConfig(
        polymarket=MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=2.0),
        kalshi=MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=0.0),  # VIP
        predictit=MakerTakerFees(maker_fee_pct=0.0, taker_fee_pct=10.0),
        sportsbook=VigModel(vig_pct=3.5),  # Reduced vig
    )
