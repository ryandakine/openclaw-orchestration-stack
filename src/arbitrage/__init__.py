"""
Arbitrage Detection Engine for Sportsbook/Prediction Market Arbitrage Hunter.

This module provides tools for:
- Matching equivalent events across sportsbooks and prediction markets
- Calculating arbitrage opportunities with proper fee accounting
- Filtering opportunities based on confidence and profitability thresholds
"""

from .models import (
    ArbitrageOpportunity,
    ArbitrageLeg,
    NormalizedMarket,
    MarketOutcome,
    MatchedEvent,
    MatchResult,
)
from .calculator import (
    calculate_implied_probability,
    calculate_implied_probability_american,
    calculate_implied_probability_decimal,
    detect_arbitrage,
    calculate_stakes,
    calculate_profit_margin,
    american_to_decimal,
    decimal_to_american,
)
from .matcher import (
    EventMatcher,
    fuzzy_match_events,
    normalize_team_name,
)
from .filters import (
    OpportunityFilter,
    filter_opportunity,
    check_liquidity,
    check_freshness,
)

__all__ = [
    # Models
    "ArbitrageOpportunity",
    "ArbitrageLeg",
    "NormalizedMarket",
    "MarketOutcome",
    "MatchedEvent",
    "MatchResult",
    # Calculator
    "calculate_implied_probability",
    "calculate_implied_probability_american",
    "calculate_implied_probability_decimal",
    "detect_arbitrage",
    "calculate_stakes",
    "calculate_profit_margin",
    "american_to_decimal",
    "decimal_to_american",
    # Matcher
    "EventMatcher",
    "fuzzy_match_events",
    "normalize_team_name",
    # Filters
    "OpportunityFilter",
    "filter_opportunity",
    "check_liquidity",
    "check_freshness",
]

__version__ = "1.0.0"
