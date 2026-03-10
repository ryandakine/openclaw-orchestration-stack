"""
Normalize all markets module.

Runs all fetched markets through the market_normalizer pipeline
to convert them to a standardized format.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Callable
from datetime import datetime

import structlog

from .config_loader import Config
from .job_context import JobContext

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class NormalizedMarket:
    """Standardized market format used throughout the pipeline."""
    
    # Identification
    normalized_id: str
    source: str  # polymarket, draftkings, fanduel, etc.
    source_market_id: str
    
    # Event info
    event_title: str
    event_slug: str  # URL-friendly version of title
    sport: str | None
    category: str | None
    
    # Market details
    market_type: str  # moneyline, spread, total, etc.
    market_key: str  # Unique key for matching (e.g., "nba:lakers:celtics:moneyline")
    
    # Outcomes
    outcomes: list["NormalizedOutcome"]
    
    # Metadata
    start_time: datetime | None
    end_time: datetime | None
    is_live: bool
    volume_24h: float | None
    liquidity: float | None
    
    # Raw data reference (for debugging)
    raw_source_data: dict[str, Any]
    
    # Normalization metadata
    normalized_at: datetime
    normalization_version: str = "1.0.0"


@dataclass(frozen=True)
class NormalizedOutcome:
    """Standardized outcome format."""
    
    outcome_id: str
    name: str
    normalized_name: str  # Standardized name for matching
    
    # Probabilities/Odds
    implied_probability: float  # 0-1 range
    decimal_odds: float
    american_odds: int | None
    
    # Position mapping
    position: str  # home, away, over, under, yes, no, etc.


@dataclass
class NormalizeResult:
    """Result of normalizing markets from a single source."""
    
    source: str
    success: bool
    normalized: list[NormalizedMarket]
    rejected: list[tuple[dict[str, Any], str]]  # (raw_market, reason)
    error: Exception | None = None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text.strip('-')


def normalize_team_name(name: str) -> str:
    """Normalize team/player names for matching."""
    import re
    # Remove common suffixes
    name = re.sub(r'\s+(FC|CF|United|City|FC|Basketball|Hockey)$', '', name, flags=re.I)
    # Remove articles
    name = re.sub(r'^(the|a|an)\s+', '', name, flags=re.I)
    # Remove special chars and normalize spaces
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip().lower()


def detect_market_type(raw_market: dict[str, Any]) -> str:
    """Detect the type of market from raw data."""
    market_type = raw_market.get("market_type", "").lower()
    
    if any(x in market_type for x in ["moneyline", "head to head", "winner"]):
        return "moneyline"
    elif any(x in market_type for x in ["spread", "handicap", "line"]):
        return "spread"
    elif any(x in market_type for x in ["total", "over/under", "o/u"]):
        return "total"
    elif any(x in market_type for x in ["outright", "futures"]):
        return "outright"
    else:
        return "unknown"


def detect_position(outcome_name: str, market_type: str) -> str:
    """Detect the position (home/away/over/under/etc) of an outcome."""
    name_lower = outcome_name.lower()
    
    if market_type == "total":
        if any(x in name_lower for x in ["over", "o"]):
            return "over"
        elif any(x in name_lower for x in ["under", "u"]):
            return "under"
    
    if market_type == "moneyline":
        # Try to infer from common patterns
        if any(x in name_lower for x in ["yes", "win", "victory"]):
            return "yes"
        elif any(x in name_lower for x in ["no", "lose", "loss"]):
            return "no"
    
    return "unknown"


def parse_datetime(date_str: str | None) -> datetime | None:
    """Parse various datetime formats."""
    if not date_str:
        return None
    
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def normalize_polymarket_market(raw: dict[str, Any]) -> NormalizedMarket | None:
    """Normalize a Polymarket market to standard format."""
    try:
        event_title = raw.get("event_title", "")
        if not event_title:
            return None
        
        # Build outcomes
        outcomes: list[NormalizedOutcome] = []
        for idx, outcome in enumerate(raw.get("outcomes", [])):
            prob = outcome.get("probability", 0)
            if prob <= 0:
                continue
            
            outcomes.append(NormalizedOutcome(
                outcome_id=f"{raw['source_id']}_{idx}",
                name=outcome.get("name", ""),
                normalized_name=normalize_team_name(outcome.get("name", "")),
                implied_probability=prob,
                decimal_odds=1 / prob if prob > 0 else 0,
                american_odds=None,  # Polymarket uses probabilities directly
                position=detect_position(outcome.get("name", ""), "moneyline"),
            ))
        
        if len(outcomes) < 2:
            return None
        
        return NormalizedMarket(
            normalized_id=f"pm_{raw['source_id']}",
            source="polymarket",
            source_market_id=raw["source_id"],
            event_title=event_title,
            event_slug=slugify(event_title),
            sport=raw.get("category"),
            category=raw.get("category"),
            market_type="moneyline",
            market_key=f"{slugify(event_title)}:moneyline",
            outcomes=outcomes,
            start_time=parse_datetime(raw.get("end_date")),
            end_time=parse_datetime(raw.get("end_date")),
            is_live=False,
            volume_24h=raw.get("volume_24h"),
            liquidity=raw.get("liquidity"),
            raw_source_data=raw,
            normalized_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.warning("polymarket_normalization_failed", error=str(e), source_id=raw.get("source_id"))
        return None


def normalize_sportsbook_market(raw: dict[str, Any]) -> NormalizedMarket | None:
    """Normalize a sportsbook market to standard format."""
    try:
        event_title = raw.get("event_title", "")
        if not event_title:
            return None
        
        source = raw.get("source", "")
        market_type = detect_market_type(raw)
        
        # Build outcomes
        outcomes: list[NormalizedOutcome] = []
        for idx, outcome in enumerate(raw.get("outcomes", [])):
            prob = outcome.get("probability")
            decimal_odds = outcome.get("odds_decimal")
            american_odds = outcome.get("odds_american")
            
            # Calculate probability if not provided
            if prob is None and decimal_odds and decimal_odds > 0:
                prob = 1 / decimal_odds
            
            if not prob or prob <= 0:
                continue
            
            outcome_name = outcome.get("name", "")
            outcomes.append(NormalizedOutcome(
                outcome_id=f"{raw['source_id']}_{idx}",
                name=outcome_name,
                normalized_name=normalize_team_name(outcome_name),
                implied_probability=prob,
                decimal_odds=decimal_odds or (1 / prob),
                american_odds=american_odds,
                position=detect_position(outcome_name, market_type),
            ))
        
        if len(outcomes) < 2:
            return None
        
        return NormalizedMarket(
            normalized_id=f"{source[:2]}_{raw['source_id']}",
            source=source,
            source_market_id=raw["source_id"],
            event_title=event_title,
            event_slug=slugify(event_title),
            sport=raw.get("sport"),
            category=raw.get("sport"),
            market_type=market_type,
            market_key=f"{slugify(event_title)}:{market_type}",
            outcomes=outcomes,
            start_time=parse_datetime(raw.get("start_time")),
            end_time=None,
            is_live=False,
            volume_24h=None,
            liquidity=None,
            raw_source_data=raw,
            normalized_at=datetime.utcnow(),
        )
    except Exception as e:
        logger.warning("sportsbook_normalization_failed", error=str(e), source=raw.get("source"), source_id=raw.get("source_id"))
        return None


def normalize_market(raw: dict[str, Any]) -> NormalizedMarket | None:
    """Route market to appropriate normalizer based on source."""
    source = raw.get("source", "").lower()
    
    if source == "polymarket":
        return normalize_polymarket_market(raw)
    elif source in ["draftkings", "fanduel", "betmgm", "caesars"]:
        return normalize_sportsbook_market(raw)
    else:
        logger.warning("unknown_market_source", source=source)
        return None


async def normalize_source_markets(
    source: str,
    markets: list[dict[str, Any]],
    config: Config,
    ctx: JobContext,
) -> NormalizeResult:
    """Normalize all markets from a single source."""
    log = logger.bind(source=source, run_id=ctx.run_id)
    log.info("normalizing_source_markets", count=len(markets))
    
    normalized: list[NormalizedMarket] = []
    rejected: list[tuple[dict[str, Any], str]] = []
    
    for raw_market in markets:
        try:
            result = normalize_market(raw_market)
            if result:
                normalized.append(result)
            else:
                rejected.append((raw_market, "normalization_returned_none"))
        except Exception as e:
            rejected.append((raw_market, f"exception: {str(e)}"))
            log.debug("market_normalization_error", error=str(e), market_id=raw_market.get("source_id"))
    
    log.info(
        "source_normalization_complete",
        normalized=len(normalized),
        rejected=len(rejected),
    )
    
    return NormalizeResult(
        source=source,
        success=True,
        normalized=normalized,
        rejected=rejected,
    )


async def normalize_all(
    all_markets: list[dict[str, Any]],
    config: Config,
    ctx: JobContext,
) -> tuple[list[NormalizedMarket], JobContext, list[NormalizeResult]]:
    """
    Normalize all markets from all sources.
    
    Returns:
        Tuple of (normalized_markets, updated_context, normalize_results)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("starting_normalization", total_markets=len(all_markets))
    
    # Group markets by source
    markets_by_source: dict[str, list[dict[str, Any]]] = {}
    for market in all_markets:
        source = market.get("source", "unknown")
        if source not in markets_by_source:
            markets_by_source[source] = []
        markets_by_source[source].append(market)
    
    log.info("markets_grouped_by_source", sources=list(markets_by_source.keys()))
    
    # Normalize each source concurrently
    tasks = [
        normalize_source_markets(source, markets, config, ctx)
        for source, markets in markets_by_source.items()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    all_normalized: list[NormalizedMarket] = []
    normalize_results: list[NormalizeResult] = []
    total_rejected = 0
    
    for result in results:
        if isinstance(result, Exception):
            log.error("normalization_task_failed", error=str(result))
            continue
        
        normalize_results.append(result)
        all_normalized.extend(result.normalized)
        total_rejected += len(result.rejected)
    
    # Update context
    updated_ctx = ctx.with_markets_normalized(len(all_normalized))
    
    log.info(
        "normalization_complete",
        total_normalized=len(all_normalized),
        total_rejected=total_rejected,
        sources_processed=len(normalize_results),
    )
    
    return all_normalized, updated_ctx, normalize_results
