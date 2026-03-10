"""
Calculate all arbitrages module.

Calculates arbitrage opportunities for each matched pair through
the arb_math pipeline.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
from enum import Enum

import structlog

from .config_loader import Config
from .job_context import JobContext
from .match_all import MarketMatch

logger = structlog.get_logger(__name__)


class ArbType(str, Enum):
    """Type of arbitrage opportunity."""
    DIRECT = "direct"  # Simple two-way arb
    IMPLIED = "implied"  # Based on implied probabilities
    SCALP = "scalp"  # Short-term price discrepancy


class ArbStatus(str, Enum):
    """Status of arbitrage calculation."""
    VALID = "valid"
    INSUFFICIENT_EDGE = "insufficient_edge"
    STAKE_LIMIT_EXCEEDED = "stake_limit_exceeded"
    EXPOSURE_LIMIT_EXCEEDED = "exposure_limit_exceeded"
    LIQUIDITY_TOO_LOW = "liquidity_too_low"
    ERROR = "error"


@dataclass(frozen=True)
class ArbOpportunity:
    """Represents a calculated arbitrage opportunity."""
    
    # Identification
    arb_id: str
    match_id: str
    
    # Market references
    polymarket_market_id: str
    sportsbook_market_id: str
    sportsbook: str
    
    # Event info
    event_title: str
    outcome_name: str
    
    # Arb details
    arb_type: ArbType
    
    # Odds/Prices
    polymarket_probability: float  # 0-1
    polymarket_decimal_odds: float
    sportsbook_probability: float  # Implied from decimal odds
    sportsbook_decimal_odds: float
    
    # Calculated values
    edge_percent: float  # Net edge after fees
    gross_edge_percent: float  # Edge before fees
    
    # Stake calculations
    recommended_pm_stake: float
    recommended_sb_stake: float
    total_exposure: float
    
    # Profit calculations
    guaranteed_profit: float
    profit_if_pm_wins: float
    profit_if_sb_wins: float
    return_on_investment: float  # Percentage
    
    # Fees
    polymarket_fee_percent: float  # Typically 2%
    sportsbook_fee_percent: float  # Varies
    total_fees: float
    
    # Status
    status: ArbStatus
    status_reason: str | None
    
    # Metadata
    calculated_at: datetime
    match_score: float


@dataclass
class ArbCalculationResult:
    """Result of arbitrage calculations."""
    
    total_calculated: int = 0
    valid_arbs: list[ArbOpportunity] = field(default_factory=list)
    rejected: list[tuple[str, str]] = field(default_factory=list)  # (match_id, reason)
    
    def add_arb(self, arb: ArbOpportunity) -> None:
        self.valid_arbs.append(arb)
        self.total_calculated = len(self.valid_arbs) + len(self.rejected)
    
    def add_reject(self, match_id: str, reason: str) -> None:
        self.rejected.append((match_id, reason))
        self.total_calculated = len(self.valid_arbs) + len(self.rejected)


def calculate_implied_probability(decimal_odds: float) -> float:
    """Calculate implied probability from decimal odds."""
    if decimal_odds <= 1:
        return 0.0
    return 1 / decimal_odds


def calculate_edge(
    pm_prob: float,
    sb_prob: float,
    pm_fee: float = 0.02,
    sb_fee: float = 0.0,
) -> tuple[float, float]:
    """
    Calculate arbitrage edge.
    
    Returns (gross_edge_percent, net_edge_percent).
    """
    # Gross edge is the raw difference in implied probabilities
    gross_edge = abs(pm_prob - sb_prob)
    gross_edge_percent = gross_edge * 100
    
    # Net edge accounts for fees
    # Assuming we bet on the side with lower implied probability (higher odds)
    if pm_prob < sb_prob:
        # Bet on Polymarket (higher odds on PM side)
        # PM fee applies to winnings
        effective_pm_return = (1 / pm_prob - 1) * (1 - pm_fee) + 1
        effective_pm_prob = 1 / effective_pm_return
        net_edge = sb_prob - effective_pm_prob
    else:
        # Bet on sportsbook
        effective_sb_return = (1 / sb_prob - 1) * (1 - sb_fee) + 1
        effective_sb_prob = 1 / effective_sb_return
        net_edge = pm_prob - effective_sb_prob
    
    net_edge_percent = net_edge * 100
    
    return gross_edge_percent, net_edge_percent


def calculate_optimal_stakes(
    pm_prob: float,
    sb_prob: float,
    total_budget: float,
) -> tuple[float, float]:
    """
    Calculate optimal stakes to maximize guaranteed profit.
    
    Returns (pm_stake, sb_stake).
    """
    # Convert probabilities to decimal odds
    pm_odds = 1 / pm_prob if pm_prob > 0 else 0
    sb_odds = 1 / sb_prob if sb_prob > 0 else 0
    
    if pm_odds <= 1 or sb_odds <= 1:
        return 0.0, 0.0
    
    # Kelly-inspired sizing based on edge
    # Stake proportionally to the inverse odds
    pm_weight = 1 / pm_odds
    sb_weight = 1 / sb_odds
    total_weight = pm_weight + sb_weight
    
    if total_weight == 0:
        return 0.0, 0.0
    
    pm_stake = total_budget * (pm_weight / total_weight)
    sb_stake = total_budget * (sb_weight / total_weight)
    
    return pm_stake, sb_stake


def calculate_guaranteed_profit(
    pm_stake: float,
    sb_stake: float,
    pm_prob: float,
    sb_prob: float,
    pm_fee: float = 0.02,
    sb_fee: float = 0.0,
) -> tuple[float, float, float, float]:
    """
    Calculate profit scenarios.
    
    Returns (guaranteed_profit, profit_if_pm_wins, profit_if_sb_wins, roi_percent).
    """
    pm_odds = 1 / pm_prob if pm_prob > 0 else 0
    sb_odds = 1 / sb_prob if sb_prob > 0 else 0
    
    total_stake = pm_stake + sb_stake
    
    if total_stake == 0:
        return 0.0, 0.0, 0.0, 0.0
    
    # Calculate winnings on each side (minus fees)
    pm_winnings = pm_stake * (pm_odds - 1) * (1 - pm_fee)
    sb_winnings = sb_stake * (sb_odds - 1) * (1 - sb_fee)
    
    # Profit if PM outcome wins (lose SB stake, win on PM)
    profit_pm_wins = pm_winnings - sb_stake
    
    # Profit if SB outcome wins (lose PM stake, win on SB)
    profit_sb_wins = sb_winnings - pm_stake
    
    # Guaranteed profit is the minimum (this should be positive for a true arb)
    guaranteed = min(profit_pm_wins, profit_sb_wins)
    
    # ROI
    roi = (guaranteed / total_stake) * 100 if total_stake > 0 else 0
    
    return guaranteed, profit_pm_wins, profit_sb_wins, roi


def generate_arb_id(match: MarketMatch) -> str:
    """Generate unique arb ID."""
    import hashlib
    combined = f"arb:{match.match_id}:{datetime.utcnow().timestamp()}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]


def get_sportsbook_fees(sportsbook: str) -> float:
    """Get typical fees for a sportsbook."""
    # Most sportsbooks don't charge explicit fees but have built-in vig
    # We use 0 as default but this could be configured
    fees = {
        "draftkings": 0.0,
        "fanduel": 0.0,
        "betmgm": 0.0,
        "caesars": 0.0,
    }
    return fees.get(sportsbook.lower(), 0.0)


def calculate_arbitrage(
    match: MarketMatch,
    config: Config,
) -> ArbOpportunity | None:
    """
    Calculate arbitrage opportunity for a single market match.
    
    Returns None if no viable arb exists.
    """
    try:
        # Get probabilities
        pm_prob = match.polymarket_outcome.implied_probability
        sb_prob = match.sportsbook_outcome.implied_probability
        
        pm_odds = match.polymarket_outcome.decimal_odds
        sb_odds = match.sportsbook_outcome.decimal_odds
        
        # Get fees
        pm_fee = 0.02  # Polymarket 2% fee on winnings
        sb_fee = get_sportsbook_fees(match.sportsbook)
        
        # Calculate edges
        gross_edge, net_edge = calculate_edge(pm_prob, sb_prob, pm_fee, sb_fee)
        
        # Check minimum edge threshold
        if net_edge < config.min_edge_percent:
            return ArbOpportunity(
                arb_id=generate_arb_id(match),
                match_id=match.match_id,
                polymarket_market_id=match.polymarket_market.normalized_id,
                sportsbook_market_id=match.sportsbook_market.normalized_id,
                sportsbook=match.sportsbook,
                event_title=match.polymarket_market.event_title,
                outcome_name=match.polymarket_outcome.name,
                arb_type=ArbType.DIRECT,
                polymarket_probability=pm_prob,
                polymarket_decimal_odds=pm_odds,
                sportsbook_probability=sb_prob,
                sportsbook_decimal_odds=sb_odds,
                edge_percent=net_edge,
                gross_edge_percent=gross_edge,
                recommended_pm_stake=0,
                recommended_sb_stake=0,
                total_exposure=0,
                guaranteed_profit=0,
                profit_if_pm_wins=0,
                profit_if_sb_wins=0,
                return_on_investment=0,
                polymarket_fee_percent=pm_fee * 100,
                sportsbook_fee_percent=sb_fee * 100,
                total_fees=0,
                status=ArbStatus.INSUFFICIENT_EDGE,
                status_reason=f"Net edge {net_edge:.2f}% below threshold {config.min_edge_percent}%",
                calculated_at=datetime.utcnow(),
                match_score=match.match_score,
            )
        
        # Calculate optimal stakes
        total_budget = min(
            config.max_stake_per_leg * 2,
            config.max_total_exposure,
        )
        pm_stake, sb_stake = calculate_optimal_stakes(pm_prob, sb_prob, total_budget)
        
        # Check stake limits
        if pm_stake > config.max_stake_per_leg or sb_stake > config.max_stake_per_leg:
            return ArbOpportunity(
                arb_id=generate_arb_id(match),
                match_id=match.match_id,
                polymarket_market_id=match.polymarket_market.normalized_id,
                sportsbook_market_id=match.sportsbook_market.normalized_id,
                sportsbook=match.sportsbook,
                event_title=match.polymarket_market.event_title,
                outcome_name=match.polymarket_outcome.name,
                arb_type=ArbType.DIRECT,
                polymarket_probability=pm_prob,
                polymarket_decimal_odds=pm_odds,
                sportsbook_probability=sb_prob,
                sportsbook_decimal_odds=sb_odds,
                edge_percent=net_edge,
                gross_edge_percent=gross_edge,
                recommended_pm_stake=pm_stake,
                recommended_sb_stake=sb_stake,
                total_exposure=pm_stake + sb_stake,
                guaranteed_profit=0,
                profit_if_pm_wins=0,
                profit_if_sb_wins=0,
                return_on_investment=0,
                polymarket_fee_percent=pm_fee * 100,
                sportsbook_fee_percent=sb_fee * 100,
                total_fees=0,
                status=ArbStatus.STAKE_LIMIT_EXCEEDED,
                status_reason="Calculated stakes exceed configured limits",
                calculated_at=datetime.utcnow(),
                match_score=match.match_score,
            )
        
        total_exposure = pm_stake + sb_stake
        
        # Check exposure limit
        if total_exposure > config.max_total_exposure:
            return ArbOpportunity(
                arb_id=generate_arb_id(match),
                match_id=match.match_id,
                polymarket_market_id=match.polymarket_market.normalized_id,
                sportsbook_market_id=match.sportsbook_market.normalized_id,
                sportsbook=match.sportsbook,
                event_title=match.polymarket_market.event_title,
                outcome_name=match.polymarket_outcome.name,
                arb_type=ArbType.DIRECT,
                polymarket_probability=pm_prob,
                polymarket_decimal_odds=pm_odds,
                sportsbook_probability=sb_prob,
                sportsbook_decimal_odds=sb_odds,
                edge_percent=net_edge,
                gross_edge_percent=gross_edge,
                recommended_pm_stake=pm_stake,
                recommended_sb_stake=sb_stake,
                total_exposure=total_exposure,
                guaranteed_profit=0,
                profit_if_pm_wins=0,
                profit_if_sb_wins=0,
                return_on_investment=0,
                polymarket_fee_percent=pm_fee * 100,
                sportsbook_fee_percent=sb_fee * 100,
                total_fees=0,
                status=ArbStatus.EXPOSURE_LIMIT_EXCEEDED,
                status_reason="Total exposure exceeds configured limit",
                calculated_at=datetime.utcnow(),
                match_score=match.match_score,
            )
        
        # Calculate profit
        guaranteed, profit_pm, profit_sb, roi = calculate_guaranteed_profit(
            pm_stake, sb_stake, pm_prob, sb_prob, pm_fee, sb_fee
        )
        
        # Check minimum profit
        if guaranteed < config.min_profit_per_unit:
            return ArbOpportunity(
                arb_id=generate_arb_id(match),
                match_id=match.match_id,
                polymarket_market_id=match.polymarket_market.normalized_id,
                sportsbook_market_id=match.sportsbook_market.normalized_id,
                sportsbook=match.sportsbook,
                event_title=match.polymarket_market.event_title,
                outcome_name=match.polymarket_outcome.name,
                arb_type=ArbType.DIRECT,
                polymarket_probability=pm_prob,
                polymarket_decimal_odds=pm_odds,
                sportsbook_probability=sb_prob,
                sportsbook_decimal_odds=sb_odds,
                edge_percent=net_edge,
                gross_edge_percent=gross_edge,
                recommended_pm_stake=pm_stake,
                recommended_sb_stake=sb_stake,
                total_exposure=total_exposure,
                guaranteed_profit=guaranteed,
                profit_if_pm_wins=profit_pm,
                profit_if_sb_wins=profit_sb,
                return_on_investment=roi,
                polymarket_fee_percent=pm_fee * 100,
                sportsbook_fee_percent=sb_fee * 100,
                total_fees=(pm_stake * pm_odds * pm_fee) + (sb_stake * sb_odds * sb_fee),
                status=ArbStatus.INSUFFICIENT_EDGE,
                status_reason=f"Guaranteed profit ${guaranteed:.2f} below threshold ${config.min_profit_per_unit}",
                calculated_at=datetime.utcnow(),
                match_score=match.match_score,
            )
        
        # Valid arbitrage!
        return ArbOpportunity(
            arb_id=generate_arb_id(match),
            match_id=match.match_id,
            polymarket_market_id=match.polymarket_market.normalized_id,
            sportsbook_market_id=match.sportsbook_market.normalized_id,
            sportsbook=match.sportsbook,
            event_title=match.polymarket_market.event_title,
            outcome_name=match.polymarket_outcome.name,
            arb_type=ArbType.DIRECT,
            polymarket_probability=pm_prob,
            polymarket_decimal_odds=pm_odds,
            sportsbook_probability=sb_prob,
            sportsbook_decimal_odds=sb_odds,
            edge_percent=net_edge,
            gross_edge_percent=gross_edge,
            recommended_pm_stake=pm_stake,
            recommended_sb_stake=sb_stake,
            total_exposure=total_exposure,
            guaranteed_profit=guaranteed,
            profit_if_pm_wins=profit_pm,
            profit_if_sb_wins=profit_sb,
            return_on_investment=roi,
            polymarket_fee_percent=pm_fee * 100,
            sportsbook_fee_percent=sb_fee * 100,
            total_fees=(pm_stake * pm_odds * pm_fee) + (sb_stake * sb_odds * sb_fee),
            status=ArbStatus.VALID,
            status_reason=None,
            calculated_at=datetime.utcnow(),
            match_score=match.match_score,
        )
        
    except Exception as e:
        logger.warning("arbitrage_calculation_failed", match_id=match.match_id, error=str(e))
        return ArbOpportunity(
            arb_id=generate_arb_id(match),
            match_id=match.match_id,
            polymarket_market_id=match.polymarket_market.normalized_id,
            sportsbook_market_id=match.sportsbook_market.normalized_id,
            sportsbook=match.sportsbook,
            event_title=match.polymarket_market.event_title,
            outcome_name=match.polymarket_outcome.name,
            arb_type=ArbType.DIRECT,
            polymarket_probability=0,
            polymarket_decimal_odds=0,
            sportsbook_probability=0,
            sportsbook_decimal_odds=0,
            edge_percent=0,
            gross_edge_percent=0,
            recommended_pm_stake=0,
            recommended_sb_stake=0,
            total_exposure=0,
            guaranteed_profit=0,
            profit_if_pm_wins=0,
            profit_if_sb_wins=0,
            return_on_investment=0,
            polymarket_fee_percent=0,
            sportsbook_fee_percent=0,
            total_fees=0,
            status=ArbStatus.ERROR,
            status_reason=f"Calculation error: {str(e)}",
            calculated_at=datetime.utcnow(),
            match_score=match.match_score,
        )


async def calculate_arbs_batch(
    matches: list[MarketMatch],
    config: Config,
    ctx: JobContext,
) -> ArbCalculationResult:
    """Calculate arbitrages for a batch of matches."""
    result = ArbCalculationResult()
    
    for match in matches:
        try:
            arb = calculate_arbitrage(match, config)
            if arb:
                if arb.status == ArbStatus.VALID:
                    result.add_arb(arb)
                else:
                    result.add_reject(match.match_id, arb.status_reason or str(arb.status))
        except Exception as e:
            result.add_reject(match.match_id, f"exception: {str(e)}")
    
    return result


async def calculate_all_arbs(
    matches: list[MarketMatch],
    config: Config,
    ctx: JobContext,
) -> tuple[list[ArbOpportunity], JobContext, ArbCalculationResult]:
    """
    Calculate arbitrage opportunities for all matched pairs.
    
    Returns:
        Tuple of (valid_arbs, updated_context, calculation_result)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("starting_arbitrage_calculations", match_count=len(matches))
    
    if not matches:
        log.info("no_matches_to_calculate")
        return [], ctx, ArbCalculationResult()
    
    # Process in batches for better concurrency control
    batch_size = 100
    batches = [matches[i:i + batch_size] for i in range(0, len(matches), batch_size)]
    
    log.debug("batches_created", batch_count=len(batches), batch_size=batch_size)
    
    # Process batches concurrently
    tasks = [calculate_arbs_batch(batch, config, ctx) for batch in batches]
    results = await asyncio.gather(*tasks)
    
    # Combine results
    combined = ArbCalculationResult()
    for result in results:
        combined.valid_arbs.extend(result.valid_arbs)
        combined.rejected.extend(result.rejected)
    
    combined.total_calculated = len(combined.valid_arbs) + len(combined.rejected)
    
    # Update context
    updated_ctx = ctx.with_arbs_calculated(combined.total_calculated)
    
    log.info(
        "arbitrage_calculations_complete",
        valid_arbs=len(combined.valid_arbs),
        rejected=len(combined.rejected),
        avg_edge=round(sum(a.edge_percent for a in combined.valid_arbs) / len(combined.valid_arbs), 2) if combined.valid_arbs else 0,
        total_potential_profit=round(sum(a.guaranteed_profit for a in combined.valid_arbs), 2),
    )
    
    return combined.valid_arbs, updated_ctx, combined
