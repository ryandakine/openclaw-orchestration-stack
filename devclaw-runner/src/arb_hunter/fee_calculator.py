"""Fee Calculator - Venue-specific fee models for arbitrage calculations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class VenueType(Enum):
    """Supported venue types."""
    POLYMARKET = "polymarket"
    DRAFTKINGS = "draftkings"
    FANDUEL = "fanduel"
    BETMGM = "betmgm"
    CAESARS = "caesars"
    GENERIC_SPORTSBOOK = "generic_sportsbook"


@dataclass
class VenueFeeModel:
    """Fee model configuration for a venue."""
    
    venue_type: VenueType
    maker_fee_pct: float = 0.0
    taker_fee_pct: float = 0.0
    withdrawal_fee_pct: float = 0.0
    withdrawal_fee_fixed: float = 0.0
    min_withdrawal: float = 0.0
    includes_vig_in_odds: bool = False
    
    # Polymarket specific
    polymarket_fee_bps: float = 75.0  # 0.75%
    
    # Sportsbook vig estimation
    default_vig_pct: float = 0.045  # 4.5% typical sportsbook vig


class FeeCalculator:
    """
    Calculate fees for various trading venues.
    
    Conservative approach: always assume taker fees unless specified.
    """
    
    # Venue fee configurations
    VENUE_CONFIGS: dict[VenueType, VenueFeeModel] = {
        VenueType.POLYMARKET: VenueFeeModel(
            venue_type=VenueType.POLYMARKET,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0075,  # 0.75%
            withdrawal_fee_pct=0.0,
            withdrawal_fee_fixed=0.0,
            includes_vig_in_odds=False,
            polymarket_fee_bps=75.0,
        ),
        VenueType.DRAFTKINGS: VenueFeeModel(
            venue_type=VenueType.DRAFTKINGS,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0,
            includes_vig_in_odds=True,
            default_vig_pct=0.045,
        ),
        VenueType.FANDUEL: VenueFeeModel(
            venue_type=VenueType.FANDUEL,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0,
            includes_vig_in_odds=True,
            default_vig_pct=0.045,
        ),
        VenueType.BETMGM: VenueFeeModel(
            venue_type=VenueType.BETMGM,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0,
            includes_vig_in_odds=True,
            default_vig_pct=0.05,
        ),
        VenueType.CAESARS: VenueFeeModel(
            venue_type=VenueType.CAESARS,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0,
            includes_vig_in_odds=True,
            default_vig_pct=0.048,
        ),
        VenueType.GENERIC_SPORTSBOOK: VenueFeeModel(
            venue_type=VenueType.GENERIC_SPORTSBOOK,
            maker_fee_pct=0.0,
            taker_fee_pct=0.0,
            includes_vig_in_odds=True,
            default_vig_pct=0.05,
        ),
    }
    
    def __init__(self) -> None:
        """Initialize fee calculator."""
        self._custom_configs: dict[str, VenueFeeModel] = {}
    
    def get_venue_config(self, venue: str) -> VenueFeeModel:
        """Get fee configuration for a venue."""
        venue_lower = venue.lower()
        
        # Map string names to enum
        venue_map = {
            "polymarket": VenueType.POLYMARKET,
            "draftkings": VenueType.DRAFTKINGS,
            "fanduel": VenueType.FANDUEL,
            "betmgm": VenueType.BETMGM,
            "caesars": VenueType.CAESARS,
        }
        
        venue_type = venue_map.get(venue_lower, VenueType.GENERIC_SPORTSBOOK)
        
        # Check for custom config
        if venue_lower in self._custom_configs:
            return self._custom_configs[venue_lower]
        
        return self.VENUE_CONFIGS[venue_type]
    
    def calculate_polymarket_fee(
        self,
        notional: float,
        is_maker: bool = False,
    ) -> float:
        """
        Calculate Polymarket trading fee.
        
        Args:
            notional: Position size in USD
            is_maker: Whether order is maker (false = taker/conservative)
            
        Returns:
            Fee amount in USD
        """
        config = self.VENUE_CONFIGS[VenueType.POLYMARKET]
        fee_rate = config.maker_fee_pct if is_maker else config.taker_fee_pct
        return notional * fee_rate
    
    def extract_vig_from_odds(
        self,
        odds_a: float,
        odds_b: float,
    ) -> float:
        """
        Extract implied vig from two-sided odds.
        
        For American odds, convert to implied probabilities.
        Vig = sum of implied probabilities - 1.0
        
        Args:
            odds_a: Odds for side A (American format)
            odds_b: Odds for side B (American format)
            
        Returns:
            Vig as percentage (e.g., 0.045 = 4.5%)
        """
        # Convert American odds to implied probability
        def american_to_implied_prob(odds: float) -> float:
            if odds > 0:
                return 100 / (odds + 100)
            else:
                return abs(odds) / (abs(odds) + 100)
        
        prob_a = american_to_implied_prob(odds_a)
        prob_b = american_to_implied_prob(odds_b)
        
        total_implied_prob = prob_a + prob_b
        vig = total_implied_prob - 1.0
        
        return max(0.0, vig)  # Vig can't be negative
    
    def calculate_sportsbook_vig(
        self,
        venue: str,
        odds: Optional[tuple[float, float]] = None,
    ) -> float:
        """
        Get sportsbook vig (built into odds).
        
        Args:
            venue: Sportsbook name
            odds: Optional (odds_a, odds_b) to extract actual vig
            
        Returns:
            Vig as percentage
        """
        config = self.get_venue_config(venue)
        
        if odds and config.includes_vig_in_odds:
            return self.extract_vig_from_odds(odds[0], odds[1])
        
        return config.default_vig_pct
    
    def calculate_total_fees(
        self,
        left_venue: str,
        right_venue: str,
        left_notional: float,
        right_notional: float,
        left_odds: Optional[tuple[float, float]] = None,
        right_odds: Optional[tuple[float, float]] = None,
    ) -> dict[str, float]:
        """
        Calculate total fees for both legs of arbitrage.
        
        Args:
            left_venue: Name of left leg venue
            right_venue: Name of right leg venue
            left_notional: Position size for left leg
            right_notional: Position size for right leg
            left_odds: Optional odds for vig extraction
            right_odds: Optional odds for vig extraction
            
        Returns:
            Dictionary with fee breakdown
        """
        left_config = self.get_venue_config(left_venue)
        right_config = self.get_venue_config(right_venue)
        
        # Calculate trading fees
        left_trading_fee = 0.0
        right_trading_fee = 0.0
        
        if left_config.venue_type == VenueType.POLYMARKET:
            left_trading_fee = self.calculate_polymarket_fee(left_notional)
        else:
            # Sportsbook vig is baked into odds, but we track it
            left_trading_fee = left_notional * left_config.default_vig_pct
        
        if right_config.venue_type == VenueType.POLYMARKET:
            right_trading_fee = self.calculate_polymarket_fee(right_notional)
        else:
            right_trading_fee = right_notional * right_config.default_vig_pct
        
        total_trading_fees = left_trading_fee + right_trading_fee
        total_notional = left_notional + right_notional
        
        # Conservative: assume withdrawal fees on exit
        withdrawal_fee = self.estimate_withdrawal_fee(left_venue, right_venue)
        
        total_fees_usd = total_trading_fees + withdrawal_fee
        total_fees_pct = total_fees_usd / total_notional if total_notional > 0 else 0.0
        
        return {
            "left_trading_fee": left_trading_fee,
            "right_trading_fee": right_trading_fee,
            "total_trading_fees": total_trading_fees,
            "withdrawal_fee": withdrawal_fee,
            "total_fees_usd": total_fees_usd,
            "total_fees_pct": total_fees_pct,
            "left_venue": left_venue,
            "right_venue": right_venue,
        }
    
    def estimate_withdrawal_fee(
        self,
        left_venue: str,
        right_venue: str,
    ) -> float:
        """
        Estimate withdrawal fees (conservative estimate).
        
        Args:
            left_venue: Left leg venue
            right_venue: Right leg venue
            
        Returns:
            Estimated withdrawal fee in USD
        """
        total_withdrawal = 0.0
        
        for venue in [left_venue, right_venue]:
            config = self.get_venue_config(venue)
            # Conservative: assume one withdrawal per venue
            total_withdrawal += config.withdrawal_fee_fixed
        
        return total_withdrawal
    
    def set_custom_config(
        self,
        venue: str,
        config: VenueFeeModel,
    ) -> None:
        """Set a custom fee configuration for a venue."""
        self._custom_configs[venue.lower()] = config
