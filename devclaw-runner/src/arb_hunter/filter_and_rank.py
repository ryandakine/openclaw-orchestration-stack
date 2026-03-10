"""
Filter and rank module.

Filters arbitrage opportunities to only alertable ones,
sorts by net_edge, and takes top N.
"""

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

import structlog

from .config_loader import Config
from .job_context import JobContext
from .calculate_all_arbs import ArbOpportunity, ArbStatus

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ArbAlert:
    """An arbitrage opportunity ready for alerting."""
    
    # Copy of arb data
    arb: ArbOpportunity
    
    # Ranking info
    rank: int
    rank_score: float  # Composite score for ranking
    
    # Alert metadata
    alert_priority: str  # high, medium, low
    alert_reason: str  # Why this arb is notable


@dataclass
class FilterResult:
    """Result of filtering and ranking."""
    
    total_filtered: int = 0
    alerts: list[ArbAlert] = field(default_factory=list)
    filtered_out: list[tuple[str, str]] = field(default_factory=list)  # (arb_id, reason)
    
    def add_alert(self, alert: ArbAlert) -> None:
        self.alerts.append(alert)
        self.total_filtered = len(self.alerts) + len(self.filtered_out)
    
    def add_filtered(self, arb_id: str, reason: str) -> None:
        self.filtered_out.append((arb_id, reason))
        self.total_filtered = len(self.alerts) + len(self.filtered_out)


def calculate_rank_score(arb: ArbOpportunity) -> float:
    """
    Calculate a composite ranking score for an arbitrage.
    
    Higher is better. Considers:
    - Net edge (primary)
    - Guaranteed profit
    - Match quality score
    - ROI
    """
    # Normalize components to 0-1 scale
    edge_component = min(arb.edge_percent / 10, 1.0)  # Cap at 10%
    profit_component = min(arb.guaranteed_profit / 100, 1.0)  # Cap at $100
    match_component = arb.match_score
    roi_component = min(arb.return_on_investment / 5, 1.0)  # Cap at 5% ROI
    
    # Weighted sum
    score = (
        edge_component * 0.4 +
        profit_component * 0.25 +
        match_component * 0.2 +
        roi_component * 0.15
    )
    
    return round(score, 4)


def determine_alert_priority(arb: ArbOpportunity) -> str:
    """Determine alert priority based on arb characteristics."""
    if arb.edge_percent >= 5 and arb.guaranteed_profit >= 50:
        return "high"
    elif arb.edge_percent >= 3 or arb.guaranteed_profit >= 30:
        return "medium"
    else:
        return "low"


def generate_alert_reason(arb: ArbOpportunity) -> str:
    """Generate human-readable reason for the alert."""
    reasons: list[str] = []
    
    if arb.edge_percent >= 5:
        reasons.append(f"high_edge({arb.edge_percent:.1f}%)")
    elif arb.edge_percent >= 3:
        reasons.append(f"good_edge({arb.edge_percent:.1f}%)")
    
    if arb.guaranteed_profit >= 50:
        reasons.append(f"high_profit(${arb.guaranteed_profit:.0f})")
    elif arb.guaranteed_profit >= 20:
        reasons.append(f"good_profit(${arb.guaranteed_profit:.0f})")
    
    if arb.return_on_investment >= 2:
        reasons.append(f"strong_roi({arb.return_on_investment:.1f}%)")
    
    if arb.match_score >= 0.9:
        reasons.append("high_confidence_match")
    
    return ", ".join(reasons) if reasons else "standard_arbitrage"


def filter_single_arb(
    arb: ArbOpportunity,
    config: Config,
    seen_arb_ids: set[str],
) -> ArbAlert | str:
    """
    Filter a single arb opportunity.
    
    Returns ArbAlert if passes, or rejection reason string if filtered out.
    """
    # Check if already seen (deduplication)
    if arb.arb_id in seen_arb_ids:
        return "duplicate"
    
    # Must be valid status
    if arb.status != ArbStatus.VALID:
        return f"invalid_status:{arb.status}"
    
    # Check minimum edge
    if arb.edge_percent < config.min_edge_percent:
        return f"edge_too_low:{arb.edge_percent:.2f}<{config.min_edge_percent}"
    
    # Check minimum profit
    if arb.guaranteed_profit < config.min_profit_per_unit:
        return f"profit_too_low:${arb.guaranteed_profit:.2f}<${config.min_profit_per_unit}"
    
    # Check exposure limits
    if arb.total_exposure > config.max_total_exposure:
        return f"exposure_too_high:${arb.total_exposure:.2f}>${config.max_total_exposure}"
    
    # Check for reasonable odds (avoid extreme outliers that may be errors)
    if arb.polymarket_decimal_odds > 100 or arb.sportsbook_decimal_odds > 100:
        return "extreme_odds_suspected_error"
    
    if arb.polymarket_decimal_odds < 1.01 or arb.sportsbook_decimal_odds < 1.01:
        return "odds_too_low"
    
    # Passed all filters - create alert
    score = calculate_rank_score(arb)
    priority = determine_alert_priority(arb)
    reason = generate_alert_reason(arb)
    
    # We'll assign rank later after sorting
    return ArbAlert(
        arb=arb,
        rank=0,  # Placeholder
        rank_score=score,
        alert_priority=priority,
        alert_reason=reason,
    )


def filter_and_rank_arbs(
    arbs: list[ArbOpportunity],
    config: Config,
    ctx: JobContext,
) -> FilterResult:
    """
    Filter and rank arbitrage opportunities.
    
    Returns FilterResult with top N alerts.
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("starting_filter_and_rank", arb_count=len(arbs))
    
    result = FilterResult()
    seen_ids: set[str] = set()
    passed_alerts: list[ArbAlert] = []
    
    # Filter each arb
    for arb in arbs:
        filter_result = filter_single_arb(arb, config, seen_ids)
        
        if isinstance(filter_result, ArbAlert):
            passed_alerts.append(filter_result)
            seen_ids.add(arb.arb_id)
        else:
            result.add_filtered(arb.arb_id, filter_result)
    
    log.info(
        "filtering_complete",
        passed=len(passed_alerts),
        filtered_out=len(result.filtered_out),
    )
    
    # Sort by rank_score descending
    passed_alerts.sort(key=lambda a: a.rank_score, reverse=True)
    
    # Take top N and assign ranks
    top_n = config.top_n_alerts
    final_alerts: list[ArbAlert] = []
    
    for rank, alert in enumerate(passed_alerts[:top_n], 1):
        final_alert = ArbAlert(
            arb=alert.arb,
            rank=rank,
            rank_score=alert.rank_score,
            alert_priority=alert.alert_priority,
            alert_reason=alert.alert_reason,
        )
        final_alerts.append(final_alert)
        result.add_alert(final_alert)
    
    # Add remaining to filtered out
    for alert in passed_alerts[top_n:]:
        result.add_filtered(alert.arb.arb_id, f"outside_top_{top_n}")
    
    log.info(
        "ranking_complete",
        final_alert_count=len(final_alerts),
        top_edge=round(final_alerts[0].arb.edge_percent, 2) if final_alerts else 0,
        avg_edge=round(sum(a.arb.edge_percent for a in final_alerts) / len(final_alerts), 2) if final_alerts else 0,
    )
    
    return result


async def filter_and_rank(
    arbs: list[ArbOpportunity],
    config: Config,
    ctx: JobContext,
) -> tuple[list[ArbAlert], JobContext, FilterResult]:
    """
    Filter alertable arbs, sort by net_edge, take top N.
    
    Returns:
        Tuple of (alerts, updated_context, filter_result)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("filter_and_rank_starting", total_arbs=len(arbs))
    
    if not arbs:
        log.info("no_arbs_to_filter")
        return [], ctx, FilterResult()
    
    # Run filtering (CPU-bound, but fast enough to not need executor)
    result = filter_and_rank_arbs(arbs, config, ctx)
    
    # Update context
    updated_ctx = ctx.with_arbs_filtered(len(result.alerts))
    
    log.info(
        "filter_and_rank_complete",
        alerts_generated=len(result.alerts),
        top_rank_score=round(result.alerts[0].rank_score, 4) if result.alerts else 0,
    )
    
    return result.alerts, updated_ctx, result
