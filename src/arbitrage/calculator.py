"""
Arbitrage calculation functions.

This module provides mathematical functions for:
- Converting between odds formats
- Calculating implied probabilities
- Detecting arbitrage opportunities
- Calculating optimal bet sizing
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple, Optional, List
from datetime import datetime

from .models import (
    ArbitrageOpportunity,
    ArbitrageLeg,
    NormalizedMarket,
    MarketOutcome,
    FeeConfig,
)


# Decimal precision context for financial calculations
DECIMAL_CONTEXT = {
    "precision": 28,
    "rounding": ROUND_HALF_UP,
}


def american_to_decimal(american_odds: int) -> Decimal:
    """
    Convert American odds to decimal odds.
    
    American odds:
    - Positive (+150): Win $150 on a $100 bet
    - Negative (-200): Need to bet $200 to win $100
    
    Decimal odds represent total return per unit staked (including stake).
    
    Args:
        american_odds: American odds (e.g., +150, -200)
        
    Returns:
        Decimal odds (e.g., 2.5, 1.5)
        
    Examples:
        >>> american_to_decimal(150)
        Decimal('2.5')
        >>> american_to_decimal(-200)
        Decimal('1.5')
    """
    if american_odds > 0:
        # Positive odds: (american / 100) + 1
        return Decimal(american_odds) / Decimal("100") + Decimal("1")
    else:
        # Negative odds: (100 / |american|) + 1
        return Decimal("100") / Decimal(abs(american_odds)) + Decimal("1")


def decimal_to_american(decimal_odds: Decimal) -> int:
    """
    Convert decimal odds to American odds.
    
    Args:
        decimal_odds: Decimal odds (e.g., 2.5, 1.5)
        
    Returns:
        American odds (e.g., +150, -200)
        
    Examples:
        >>> decimal_to_american(Decimal('2.5'))
        150
        >>> decimal_to_american(Decimal('1.5'))
        -200
    """
    if decimal_odds >= Decimal("2"):
        # Positive American odds: (decimal - 1) * 100
        return int((decimal_odds - Decimal("1")) * Decimal("100"))
    else:
        # Negative American odds: -100 / (decimal - 1)
        # Use proper rounding
        result = Decimal("-100") / (decimal_odds - Decimal("1"))
        return int(result.quantize(Decimal("1")))


def fractional_to_decimal(numerator: int, denominator: int) -> Decimal:
    """
    Convert fractional odds to decimal odds.
    
    Args:
        numerator: First number in fraction (e.g., 3 in 3/2)
        denominator: Second number in fraction (e.g., 2 in 3/2)
        
    Returns:
        Decimal odds
        
    Example:
        >>> fractional_to_decimal(3, 2)
        Decimal('2.5')
    """
    return Decimal(numerator) / Decimal(denominator) + Decimal("1")


def calculate_implied_probability_decimal(decimal_odds: Decimal) -> Decimal:
    """
    Calculate implied probability from decimal odds.
    
    Formula: 1 / decimal_odds
    
    Args:
        decimal_odds: Decimal odds (e.g., 2.5)
        
    Returns:
        Implied probability as Decimal (0.0 to 1.0)
        
    Examples:
        >>> calculate_implied_probability_decimal(Decimal('2.0'))
        Decimal('0.5')
        >>> calculate_implied_probability_decimal(Decimal('4.0'))
        Decimal('0.25')
    """
    if decimal_odds <= Decimal("1"):
        raise ValueError(f"Decimal odds must be > 1, got {decimal_odds}")
    return Decimal("1") / decimal_odds


def calculate_implied_probability_american(american_odds: int) -> Decimal:
    """
    Calculate implied probability from American odds.
    
    Args:
        american_odds: American odds (e.g., +150, -200)
        
    Returns:
        Implied probability as Decimal (0.0 to 1.0)
        
    Examples:
        >>> calculate_implied_probability_american(100)
        Decimal('0.5')
        >>> calculate_implied_probability_american(-200)
        Decimal('0.6666666666666666666666666667')
    """
    decimal_odds = american_to_decimal(american_odds)
    return calculate_implied_probability_decimal(decimal_odds)


def calculate_implied_probability(odds: Decimal, format: str = "decimal") -> Decimal:
    """
    Calculate implied probability from odds in various formats.
    
    Args:
        odds: The odds value
        format: Format of odds - "decimal", "american", or "implied_probability"
        
    Returns:
        Implied probability as Decimal (0.0 to 1.0)
    """
    if format == "decimal":
        return calculate_implied_probability_decimal(odds)
    elif format == "american":
        return calculate_implied_probability_american(int(odds))
    elif format == "implied_probability":
        return odds
    else:
        raise ValueError(f"Unknown odds format: {format}")


def calculate_vig(probabilities: List[Decimal]) -> Decimal:
    """
    Calculate the vig (overround) from a set of implied probabilities.
    
    In a fair market, probabilities sum to 1.0. The excess is the bookmaker's edge.
    
    Args:
        probabilities: List of implied probabilities
        
    Returns:
        Vig as Decimal (0.0 = no vig, 0.05 = 5% vig)
        
    Example:
        >>> calculate_vig([Decimal('0.6'), Decimal('0.5')])
        Decimal('0.1')
    """
    return sum(probabilities, Decimal("0")) - Decimal("1")


def remove_vig(probabilities: List[Decimal], method: str = "proportional") -> List[Decimal]:
    """
    Remove vig from implied probabilities to get true probabilities.
    
    Args:
        probabilities: List of implied probabilities with vig
        method: Method for removing vig - "proportional" or "equal"
        
    Returns:
        List of vig-free probabilities
    """
    total = sum(probabilities, Decimal("0"))
    
    if method == "proportional":
        # Distribute vig proportionally
        return [p / total for p in probabilities]
    elif method == "equal":
        # Remove equal amount from each
        vig = total - Decimal("1")
        vig_per_outcome = vig / len(probabilities)
        return [p - vig_per_outcome for p in probabilities]
    else:
        raise ValueError(f"Unknown vig removal method: {method}")


def detect_arbitrage(
    probability_a: Decimal,
    probability_b: Decimal,
    fees_a: Decimal = Decimal("0"),
    fees_b: Decimal = Decimal("0"),
    slippage_a: Decimal = Decimal("0"),
    slippage_b: Decimal = Decimal("0"),
) -> Tuple[bool, Decimal, Decimal]:
    """
    Detect if there's an arbitrage opportunity between two mutually exclusive outcomes.
    
    For a binary market where you can bet on both sides:
    - If prob_a + prob_b < 1.0, there's an arbitrage opportunity
    - The arbitrage margin = 1.0 - (prob_a + prob_b)
    
    Args:
        probability_a: Implied probability of outcome A (0.0 to 1.0)
        probability_b: Implied probability of outcome B (0.0 to 1.0)
        fees_a: Fees for betting on outcome A (% as decimal)
        fees_b: Fees for betting on outcome B (% as decimal)
        slippage_a: Estimated slippage for outcome A (% as decimal)
        slippage_b: Estimated slippage for outcome B (% as decimal)
        
    Returns:
        Tuple of (is_arbitrage, gross_margin, net_margin)
        - is_arbitrage: True if arbitrage exists after fees
        - gross_margin: Raw arbitrage margin before fees (as decimal)
        - net_margin: Net margin after fees and slippage (as decimal)
        
    Examples:
        >>> detect_arbitrage(Decimal('0.45'), Decimal('0.50'))
        (True, Decimal('0.05'), Decimal('0.05'))
        >>> detect_arbitrage(Decimal('0.55'), Decimal('0.50'))
        (False, Decimal('-0.05'), Decimal('-0.05'))
    """
    # Gross arbitrage margin (before fees)
    total_probability = probability_a + probability_b
    gross_margin = Decimal("1") - total_probability
    
    # Calculate total cost (fees + slippage)
    total_fees = fees_a + fees_b
    total_slippage = slippage_a + slippage_b
    
    # Net margin after all costs
    net_margin = gross_margin - total_fees - total_slippage
    
    is_arbitrage = net_margin > Decimal("0")
    
    return is_arbitrage, gross_margin, net_margin


def calculate_stakes(
    total_stake: Decimal,
    odds_a: Decimal,
    odds_b: Decimal,
) -> Tuple[Decimal, Decimal]:
    """
    Calculate optimal stake distribution for an arbitrage bet.
    
    The goal is to win the same amount regardless of which outcome occurs.
    
    Formula:
    - stake_a = total_stake * (odds_b / (odds_a + odds_b))
    - stake_b = total_stake - stake_a
    
    Args:
        total_stake: Total amount to bet
        odds_a: Decimal odds for outcome A
        odds_b: Decimal odds for outcome B
        
    Returns:
        Tuple of (stake_a, stake_b)
        
    Example:
        >>> calculate_stakes(Decimal('1000'), Decimal('2.1'), Decimal('1.95'))
        (Decimal('481.48'), Decimal('518.52'))
    """
    # Calculate stake weights to equalize payout
    # stake_a * odds_a = stake_b * odds_b
    # stake_a + stake_b = total_stake
    # stake_a = total_stake * odds_b / (odds_a + odds_b)
    
    stake_a = total_stake * odds_b / (odds_a + odds_b)
    stake_b = total_stake - stake_a
    
    # Round to 2 decimal places for currency
    stake_a = stake_a.quantize(Decimal("0.01"))
    stake_b = stake_b.quantize(Decimal("0.01"))
    
    return stake_a, stake_b


def calculate_stakes_from_probabilities(
    total_stake: Decimal,
    prob_a: Decimal,
    prob_b: Decimal,
) -> Tuple[Decimal, Decimal]:
    """
    Calculate optimal stake distribution from probabilities.
    
    Args:
        total_stake: Total amount to bet
        prob_a: Implied probability of outcome A
        prob_b: Implied probability of outcome B
        
    Returns:
        Tuple of (stake_a, stake_b)
    """
    # Stake proportional to the opposite probability
    # More money on the lower probability (higher odds) outcome
    total_prob = prob_a + prob_b
    
    stake_a = total_stake * (prob_b / total_prob)
    stake_b = total_stake * (prob_a / total_prob)
    
    stake_a = stake_a.quantize(Decimal("0.01"))
    stake_b = stake_b.quantize(Decimal("0.01"))
    
    return stake_a, stake_b


def calculate_profit_margin(
    stake_a: Decimal,
    stake_b: Decimal,
    odds_a: Decimal,
    odds_b: Decimal,
) -> Decimal:
    """
    Calculate the guaranteed profit margin for an arbitrage bet.
    
    Args:
        stake_a: Amount bet on outcome A
        stake_b: Amount bet on outcome B
        odds_a: Decimal odds for outcome A
        odds_b: Decimal odds for outcome B
        
    Returns:
        Profit margin as a decimal (e.g., 0.02 = 2% profit)
        
    Example:
        >>> calculate_profit_margin(Decimal('500'), Decimal('500'), Decimal('2.1'), Decimal('2.1'))
        Decimal('0.05')
    """
    total_stake = stake_a + stake_b
    
    # Payout if A wins
    payout_a = stake_a * odds_a
    # Payout if B wins
    payout_b = stake_b * odds_b
    
    # Guaranteed profit is the minimum payout minus total stake
    min_payout = min(payout_a, payout_b)
    profit = min_payout - total_stake
    
    # Return as percentage
    return profit / total_stake


def calculate_expected_payout(
    stake: Decimal,
    odds: Decimal,
    fees_pct: Decimal = Decimal("0"),
) -> Decimal:
    """
    Calculate expected payout after fees.
    
    Args:
        stake: Amount staked
        odds: Decimal odds
        fees_pct: Fees as percentage of stake or winnings
        
    Returns:
        Expected payout amount
    """
    gross_payout = stake * odds
    fees = gross_payout * fees_pct
    return gross_payout - fees


def calculate_yield(
    stake: Decimal,
    profit: Decimal,
) -> Decimal:
    """
    Calculate yield (ROI) on a bet.
    
    Args:
        stake: Amount staked
        profit: Profit amount
        
    Returns:
        Yield as decimal
    """
    return profit / stake


def evaluate_opportunity(
    market_a: NormalizedMarket,
    market_b: NormalizedMarket,
    outcome_a: MarketOutcome,
    outcome_b: MarketOutcome,
    fee_config: Optional[dict] = None,
    min_profit_threshold: Decimal = Decimal("0.02"),  # 2%
) -> Optional[ArbitrageOpportunity]:
    """
    Evaluate whether two outcomes form an arbitrage opportunity.
    
    Args:
        market_a: First normalized market
        market_b: Second normalized market
        outcome_a: Outcome from market_a to bet on
        outcome_b: Outcome from market_b to bet on
        fee_config: Dictionary of FeeConfig by source name
        min_profit_threshold: Minimum profit threshold (% as decimal)
        
    Returns:
        ArbitrageOpportunity if one exists, None otherwise
    """
    if fee_config is None:
        fee_config = FeeConfig.default_configs()
    
    # Get fee configs for each source
    fees_a = fee_config.get(market_a.source, FeeConfig(source=market_a.source))
    fees_b = fee_config.get(market_b.source, FeeConfig(source=market_b.source))
    
    # Calculate implied probabilities
    prob_a = outcome_a.implied_probability or calculate_implied_probability_decimal(outcome_a.price)
    prob_b = outcome_b.implied_probability or calculate_implied_probability_decimal(outcome_b.price)
    
    # Detect arbitrage
    is_arb, gross_margin, net_margin = detect_arbitrage(
        probability_a=prob_a,
        probability_b=prob_b,
        fees_a=fees_a.market_fee_pct / Decimal("100"),
        fees_b=fees_b.market_fee_pct / Decimal("100"),
        slippage_a=fees_a.slippage_estimate_pct / Decimal("100"),
        slippage_b=fees_b.slippage_estimate_pct / Decimal("100"),
    )
    
    if not is_arb or net_margin < min_profit_threshold:
        return None
    
    # Calculate optimal stakes
    total_stake = Decimal("10000")  # Base calculation on $10k
    stake_a, stake_b = calculate_stakes(total_stake, outcome_a.price, outcome_b.price)
    
    # Calculate max stake based on liquidity
    liquidity_a = outcome_a.liquidity or Decimal("0")
    liquidity_b = outcome_b.liquidity or Decimal("0")
    
    # Max stake is limited by the smaller liquidity pool
    # Conservative: assume we can use at most 20% of available liquidity
    max_liquidity_stake = min(
        liquidity_a * Decimal("0.2"),
        liquidity_b * Decimal("0.2"),
    )
    max_stake = min(total_stake, max_liquidity_stake) if max_liquidity_stake > 0 else total_stake
    
    # Recalculate stakes for max stake
    if max_stake < total_stake:
        stake_a, stake_b = calculate_stakes(max_stake, outcome_a.price, outcome_b.price)
    
    # Calculate expected profit
    expected_profit = max_stake * net_margin
    
    # Calculate freshness
    freshness_seconds = 0
    if market_a.last_updated and market_b.last_updated:
        freshness_a = (datetime.utcnow() - market_a.last_updated).total_seconds()
        freshness_b = (datetime.utcnow() - market_b.last_updated).total_seconds()
        freshness_seconds = int(max(freshness_a, freshness_b))
    
    # Create arbitrage legs
    leg_a = ArbitrageLeg(
        source=market_a.source,
        source_event_id=market_a.source_event_id,
        side=outcome_a.label,
        price=outcome_a.price,
        american_odds=outcome_a.american_odds or decimal_to_american(outcome_a.price),
        liquidity=outcome_a.liquidity,
        url=market_a.url,
        fees_pct=fees_a.market_fee_pct + fees_a.slippage_estimate_pct,
    )
    
    leg_b = ArbitrageLeg(
        source=market_b.source,
        source_event_id=market_b.source_event_id,
        side=outcome_b.label,
        price=outcome_b.price,
        american_odds=outcome_b.american_odds or decimal_to_american(outcome_b.price),
        liquidity=outcome_b.liquidity,
        url=market_b.url,
        fees_pct=fees_b.market_fee_pct + fees_b.slippage_estimate_pct,
    )
    
    # Create opportunity
    opportunity = ArbitrageOpportunity(
        event_title=market_a.title,
        left_leg=leg_a,
        right_leg=leg_b,
        gross_edge_pct=gross_margin * Decimal("100"),
        fees_pct=(fees_a.market_fee_pct + fees_b.market_fee_pct),
        slippage_pct=(fees_a.slippage_estimate_pct + fees_b.slippage_estimate_pct),
        net_edge_pct=net_margin * Decimal("100"),
        max_stake=max_stake,
        expected_profit=expected_profit,
        freshness_seconds=freshness_seconds,
        alertable=True,
        expires_at=market_a.start_time,
        metadata={
            "market_a_id": market_a.source_event_id,
            "market_b_id": market_b.source_event_id,
            "prob_a": float(prob_a),
            "prob_b": float(prob_b),
            "stake_a": float(stake_a),
            "stake_b": float(stake_b),
        },
    )
    
    return opportunity


def format_profit_percentage(profit_decimal: Decimal) -> str:
    """
    Format a profit decimal as a percentage string.
    
    Args:
        profit_decimal: Profit as decimal (e.g., 0.025 for 2.5%)
        
    Returns:
        Formatted percentage string
    """
    percentage = profit_decimal * Decimal("100")
    return f"{percentage:.2f}%"


def format_currency(amount: Decimal, currency: str = "$") -> str:
    """
    Format a decimal amount as currency.
    
    Args:
        amount: Amount to format
        currency: Currency symbol
        
    Returns:
        Formatted currency string
    """
    return f"{currency}{amount:,.2f}"
