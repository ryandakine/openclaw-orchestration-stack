"""
Match all module.

Generates all matched pairs of markets between Polymarket and sportsbooks
through the event_matcher pipeline.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timedelta

import structlog

from .config_loader import Config
from .job_context import JobContext
from .normalize_all import NormalizedMarket, NormalizedOutcome

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MarketMatch:
    """Represents a matched pair of markets."""
    
    # Match identification
    match_id: str
    
    # Polymarket side
    polymarket_market: NormalizedMarket
    polymarket_outcome: NormalizedOutcome
    
    # Sportsbook side
    sportsbook_market: NormalizedMarket
    sportsbook_outcome: NormalizedOutcome
    
    # Match metadata
    sportsbook: str
    match_score: float  # 0-1 similarity score
    match_reason: str  # Why these were matched
    
    # Event alignment check
    event_aligned: bool
    time_aligned: bool  # Start times within reasonable window


@dataclass
class MatchResult:
    """Result of matching markets."""
    
    total_matches: int = 0
    matches: list[MarketMatch] = field(default_factory=list)
    rejects: list[dict[str, Any]] = field(default_factory=list)  # Rejected match attempts
    
    def add_match(self, match: MarketMatch) -> None:
        self.matches.append(match)
        self.total_matches = len(self.matches)
    
    def add_reject(self, pm_market: NormalizedMarket, sb_market: NormalizedMarket, reason: str) -> None:
        self.rejects.append({
            "polymarket_id": pm_market.normalized_id,
            "sportsbook_id": sb_market.normalized_id,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        })


def calculate_string_similarity(s1: str, s2: str) -> float:
    """Calculate similarity between two strings using simple approach."""
    # Convert to sets of words for simple comparison
    words1 = set(s1.lower().split())
    words2 = set(s2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.0


def calculate_event_similarity(pm_market: NormalizedMarket, sb_market: NormalizedMarket) -> float:
    """Calculate similarity between two events for matching."""
    # Compare event titles
    title_sim = calculate_string_similarity(pm_market.event_title, sb_market.event_title)
    
    # Compare slugs (often cleaner)
    slug_sim = calculate_string_similarity(pm_market.event_slug, sb_market.event_slug)
    
    # Weight slug similarity higher as it's normalized
    return (title_sim * 0.3) + (slug_sim * 0.7)


def normalize_outcome_name(name: str) -> str:
    """Normalize outcome name for matching."""
    import re
    name = name.lower().strip()
    # Remove common suffixes/prefixes
    name = re.sub(r'\s+\([^)]+\)', '', name)  # Remove parentheticals
    name = re.sub(r'^[\-–]\s*', '', name)  # Remove leading dashes
    return name


def match_outcomes(
    pm_market: NormalizedMarket,
    sb_market: NormalizedMarket,
) -> list[tuple[NormalizedOutcome, NormalizedOutcome, float]]:
    """
    Find matching outcome pairs between two markets.
    
    Returns list of (pm_outcome, sb_outcome, similarity_score) tuples.
    """
    matches: list[tuple[NormalizedOutcome, NormalizedOutcome, float]] = []
    
    for pm_outcome in pm_market.outcomes:
        pm_name_norm = normalize_outcome_name(pm_outcome.normalized_name)
        pm_position = pm_outcome.position
        
        for sb_outcome in sb_market.outcomes:
            sb_name_norm = normalize_outcome_name(sb_outcome.normalized_name)
            sb_position = sb_outcome.position
            
            # Calculate name similarity
            name_sim = calculate_string_similarity(pm_name_norm, sb_name_norm)
            
            # Check position alignment (strong signal)
            position_match = 1.0 if (pm_position == sb_position and pm_position != "unknown") else 0.0
            
            # Combined score - position match is strong evidence
            if position_match > 0:
                score = 0.7 + (0.3 * name_sim)  # High base if positions match
            else:
                score = name_sim * 0.8  # Lower ceiling without position match
            
            if score >= 0.6:  # Minimum threshold
                matches.append((pm_outcome, sb_outcome, score))
    
    # Sort by score descending and return best matches
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches


def check_time_alignment(
    pm_market: NormalizedMarket,
    sb_market: NormalizedMarket,
    tolerance_hours: float = 24.0,
) -> bool:
    """Check if two markets have aligned start times."""
    if not pm_market.start_time or not sb_market.start_time:
        return True  # Assume aligned if unknown
    
    diff = abs((pm_market.start_time - sb_market.start_time).total_seconds())
    return diff <= (tolerance_hours * 3600)


def generate_match_id(pm_market: NormalizedMarket, sb_market: NormalizedMarket) -> str:
    """Generate a unique match ID."""
    import hashlib
    combined = f"{pm_market.normalized_id}:{sb_market.normalized_id}"
    return hashlib.md5(combined.encode()).hexdigest()[:12]


def match_market_pair(
    pm_market: NormalizedMarket,
    sb_market: NormalizedMarket,
    config: Config,
) -> list[MarketMatch]:
    """
    Attempt to match a Polymarket market with a sportsbook market.
    
    Returns list of matches (can be multiple if multiple outcomes align).
    """
    matches: list[MarketMatch] = []
    
    # Check event similarity
    event_sim = calculate_event_similarity(pm_market, sb_market)
    if event_sim < 0.5:  # Minimum event match threshold
        return matches
    
    # Check time alignment
    time_aligned = check_time_alignment(pm_market, sb_market)
    
    # Check sport/category alignment
    sport_aligned = False
    if pm_market.sport and sb_market.sport:
        sport_sim = calculate_string_similarity(pm_market.sport, sb_market.sport)
        sport_aligned = sport_sim >= 0.5
    elif pm_market.category and sb_market.category:
        cat_sim = calculate_string_similarity(pm_market.category, sb_market.category)
        sport_aligned = cat_sim >= 0.5
    else:
        sport_aligned = True  # Assume aligned if no data
    
    if not sport_aligned:
        return matches
    
    # Match outcomes
    outcome_matches = match_outcomes(pm_market, sb_market)
    
    for pm_outcome, sb_outcome, outcome_score in outcome_matches:
        # Require good outcome match or good event + position match
        if outcome_score >= 0.6:
            match = MarketMatch(
                match_id=generate_match_id(pm_market, sb_market),
                polymarket_market=pm_market,
                polymarket_outcome=pm_outcome,
                sportsbook_market=sb_market,
                sportsbook_outcome=sb_outcome,
                sportsbook=sb_market.source,
                match_score=min(1.0, (event_sim * 0.4) + (outcome_score * 0.6)),
                match_reason=f"event_sim={event_sim:.2f},outcome_sim={outcome_score:.2f}",
                event_aligned=(event_sim >= 0.7),
                time_aligned=time_aligned,
            )
            matches.append(match)
    
    return matches


async def match_markets_for_sportsbook(
    polymarket_markets: list[NormalizedMarket],
    sportsbook_markets: list[NormalizedMarket],
    sportsbook: str,
    config: Config,
    ctx: JobContext,
) -> MatchResult:
    """Match all Polymarket markets against a single sportsbook's markets."""
    log = logger.bind(sportsbook=sportsbook, run_id=ctx.run_id)
    log.info(
        "matching_sportsbook",
        polymarket_count=len(polymarket_markets),
        sportsbook_count=len(sportsbook_markets),
    )
    
    result = MatchResult()
    
    # Compare each PM market with each sportsbook market
    for pm_market in polymarket_markets:
        for sb_market in sportsbook_markets:
            # Quick filter: skip if sports don't match
            if pm_market.sport and sb_market.sport:
                sport_sim = calculate_string_similarity(pm_market.sport, sb_market.sport)
                if sport_sim < 0.3:
                    result.add_reject(pm_market, sb_market, "sport_mismatch")
                    continue
            
            # Attempt match
            matches = match_market_pair(pm_market, sb_market, config)
            
            if matches:
                for match in matches:
                    result.add_match(match)
            else:
                result.add_reject(pm_market, sb_market, "no_outcome_match")
    
    log.info(
        "sportsbook_matching_complete",
        matches=len(result.matches),
        rejects=len(result.rejects),
    )
    
    return result


async def match_all(
    normalized_markets: list[NormalizedMarket],
    config: Config,
    ctx: JobContext,
) -> tuple[list[MarketMatch], JobContext, MatchResult]:
    """
    Generate all matched pairs between Polymarket and sportsbook markets.
    
    Returns:
        Tuple of (all_matches, updated_context, combined_result)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("starting_market_matching", total_markets=len(normalized_markets))
    
    # Separate markets by source
    polymarket_markets = [m for m in normalized_markets if m.source == "polymarket"]
    sportsbook_markets_by_source: dict[str, list[NormalizedMarket]] = {}
    
    for market in normalized_markets:
        if market.source != "polymarket":
            if market.source not in sportsbook_markets_by_source:
                sportsbook_markets_by_source[market.source] = []
            sportsbook_markets_by_source[market.source].append(market)
    
    log.info(
        "markets_separated",
        polymarket_count=len(polymarket_markets),
        sportsbook_sources=list(sportsbook_markets_by_source.keys()),
    )
    
    if not polymarket_markets:
        log.warning("no_polymarket_markets_to_match")
        return [], ctx, MatchResult()
    
    if not sportsbook_markets_by_source:
        log.warning("no_sportsbook_markets_to_match")
        return [], ctx, MatchResult()
    
    # Match each sportsbook against Polymarket concurrently
    tasks = [
        match_markets_for_sportsbook(
            polymarket_markets,
            sb_markets,
            sportsbook,
            config,
            ctx,
        )
        for sportsbook, sb_markets in sportsbook_markets_by_source.items()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Combine results
    all_matches: list[MarketMatch] = []
    combined_result = MatchResult()
    
    for result in results:
        if isinstance(result, Exception):
            log.error("matching_task_failed", error=str(result))
            continue
        
        all_matches.extend(result.matches)
        combined_result.matches.extend(result.matches)
        combined_result.rejects.extend(result.rejects)
    
    combined_result.total_matches = len(combined_result.matches)
    
    # Update context
    updated_ctx = ctx.with_matches_found(len(all_matches))
    
    # Log summary by sportsbook
    by_sportsbook: dict[str, int] = {}
    for match in all_matches:
        by_sportsbook[match.sportsbook] = by_sportsbook.get(match.sportsbook, 0) + 1
    
    log.info(
        "market_matching_complete",
        total_matches=len(all_matches),
        rejects=len(combined_result.rejects),
        by_sportsbook=by_sportsbook,
    )
    
    return all_matches, updated_ctx, combined_result
