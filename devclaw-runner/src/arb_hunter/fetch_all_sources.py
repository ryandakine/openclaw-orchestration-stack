"""
Fetch all sources module.

Fetches market data from Polymarket and sportsbooks in parallel using asyncio.gather.
Implements graceful degradation - continues if one API fails.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp
import structlog

from .config_loader import Config
from .job_context import JobContext

logger = structlog.get_logger(__name__)


@dataclass
class FetchResult:
    """Result of fetching from a single source."""
    
    source: str  # e.g., "polymarket", "draftkings", etc.
    success: bool
    markets: list[dict[str, Any]] = None  # type: ignore
    error: Exception | None = None
    duration_seconds: float = 0.0
    market_count: int = 0

    def __post_init__(self):
        if self.markets is None:
            self.markets = []
        self.market_count = len(self.markets)


async def fetch_polymarket(
    session: aiohttp.ClientSession,
    config: Config,
    ctx: JobContext,
) -> FetchResult:
    """Fetch active markets from Polymarket API."""
    log = logger.bind(source="polymarket", run_id=ctx.run_id)
    log.info("fetching_polymarket")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        # Polymarket Gamma API endpoint for active markets
        url = "https://gamma-api.polymarket.com/markets"
        params = {
            "active": "true",
            "closed": "false",
            "archived": "false",
        }
        
        headers: dict[str, str] = {}
        if config.polymarket_api_key:
            headers["Authorization"] = f"Bearer {config.polymarket_api_key}"
        
        timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
        
        async with session.get(url, params=params, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            # Transform Polymarket data to common format
            markets = []
            for market in data.get("markets", data if isinstance(data, list) else []):
                markets.append({
                    "source": "polymarket",
                    "source_id": str(market.get("id", "")),
                    "event_title": market.get("question", ""),
                    "market_slug": market.get("slug", ""),
                    "category": market.get("category", ""),
                    "outcomes": [
                        {
                            "name": outcome.get("name", ""),
                            "probability": outcome.get("probability", 0),
                            "price": outcome.get("price", 0),
                        }
                        for outcome in market.get("outcomes", [])
                    ],
                    "volume_24h": market.get("volume24h", 0),
                    "liquidity": market.get("liquidity", 0),
                    "end_date": market.get("endDate", ""),
                    "raw_data": market,
                })
            
            duration = asyncio.get_event_loop().time() - start_time
            log.info(
                "polymarket_fetch_complete",
                market_count=len(markets),
                duration_seconds=round(duration, 2),
            )
            
            return FetchResult(
                source="polymarket",
                success=True,
                markets=markets,
                duration_seconds=duration,
            )
            
    except asyncio.TimeoutError as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("polymarket_fetch_timeout", duration_seconds=round(duration, 2))
        return FetchResult(
            source="polymarket",
            success=False,
            error=e,
            duration_seconds=duration,
        )
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("polymarket_fetch_failed", error=str(e), error_type=type(e).__name__)
        return FetchResult(
            source="polymarket",
            success=False,
            error=e,
            duration_seconds=duration,
        )


async def fetch_draftkings(
    session: aiohttp.ClientSession,
    config: Config,
    ctx: JobContext,
) -> FetchResult:
    """Fetch markets from DraftKings Sportsbook API."""
    log = logger.bind(source="draftkings", run_id=ctx.run_id)
    log.info("fetching_draftkings")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        if not config.draftkings_api_key:
            raise ValueError("DraftKings API key not configured")
        
        # DraftKings API endpoint (placeholder - actual URL may differ)
        url = "https://sportsbook.draftkings.com/api/sports/v3/events"
        
        headers = {
            "Authorization": f"Bearer {config.draftkings_api_key}",
        }
        
        timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
        
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            markets = []
            for event in data.get("events", []):
                for market in event.get("markets", []):
                    markets.append({
                        "source": "draftkings",
                        "source_id": f"{event.get('id')}_{market.get('id')}",
                        "event_title": event.get("name", ""),
                        "market_type": market.get("marketType", ""),
                        "sport": event.get("sport", ""),
                        "outcomes": [
                            {
                                "name": selection.get("label", ""),
                                "odds_american": selection.get("oddsAmerican", 0),
                                "odds_decimal": american_to_decimal(selection.get("oddsAmerican", 0)),
                                "probability": american_to_probability(selection.get("oddsAmerican", 0)),
                            }
                            for selection in market.get("selections", [])
                        ],
                        "start_time": event.get("startDate", ""),
                        "raw_data": {"event": event, "market": market},
                    })
            
            duration = asyncio.get_event_loop().time() - start_time
            log.info(
                "draftkings_fetch_complete",
                market_count=len(markets),
                duration_seconds=round(duration, 2),
            )
            
            return FetchResult(
                source="draftkings",
                success=True,
                markets=markets,
                duration_seconds=duration,
            )
            
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("draftkings_fetch_failed", error=str(e), error_type=type(e).__name__)
        return FetchResult(
            source="draftkings",
            success=False,
            error=e,
            duration_seconds=duration,
        )


async def fetch_fanduel(
    session: aiohttp.ClientSession,
    config: Config,
    ctx: JobContext,
) -> FetchResult:
    """Fetch markets from FanDuel Sportsbook API."""
    log = logger.bind(source="fanduel", run_id=ctx.run_id)
    log.info("fetching_fanduel")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        if not config.fanduel_api_key:
            raise ValueError("FanDuel API key not configured")
        
        # FanDuel API endpoint (placeholder)
        url = "https://sportsbook.fanduel.com/api/events"
        
        headers = {
            "Authorization": f"Bearer {config.fanduel_api_key}",
        }
        
        timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
        
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            markets = []
            for event in data.get("events", []):
                for market in event.get("markets", []):
                    markets.append({
                        "source": "fanduel",
                        "source_id": f"{event.get('id')}_{market.get('id')}",
                        "event_title": event.get("name", ""),
                        "market_type": market.get("marketType", ""),
                        "sport": event.get("sport", ""),
                        "outcomes": [
                            {
                                "name": runner.get("name", ""),
                                "odds_american": runner.get("americanOdds", 0),
                                "odds_decimal": american_to_decimal(runner.get("americanOdds", 0)),
                                "probability": american_to_probability(runner.get("americanOdds", 0)),
                            }
                            for runner in market.get("runners", [])
                        ],
                        "start_time": event.get("startTime", ""),
                        "raw_data": {"event": event, "market": market},
                    })
            
            duration = asyncio.get_event_loop().time() - start_time
            log.info(
                "fanduel_fetch_complete",
                market_count=len(markets),
                duration_seconds=round(duration, 2),
            )
            
            return FetchResult(
                source="fanduel",
                success=True,
                markets=markets,
                duration_seconds=duration,
            )
            
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("fanduel_fetch_failed", error=str(e), error_type=type(e).__name__)
        return FetchResult(
            source="fanduel",
            success=False,
            error=e,
            duration_seconds=duration,
        )


async def fetch_betmgm(
    session: aiohttp.ClientSession,
    config: Config,
    ctx: JobContext,
) -> FetchResult:
    """Fetch markets from BetMGM Sportsbook API."""
    log = logger.bind(source="betmgm", run_id=ctx.run_id)
    log.info("fetching_betmgm")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        if not config.betmgm_api_key:
            raise ValueError("BetMGM API key not configured")
        
        # BetMGM API endpoint (placeholder)
        url = "https://sports.betmgm.com/api/sports/v2/events"
        
        headers = {
            "Authorization": f"Bearer {config.betmgm_api_key}",
        }
        
        timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
        
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            markets = []
            for competition in data.get("competitions", []):
                for event in competition.get("events", []):
                    for market in event.get("markets", []):
                        markets.append({
                            "source": "betmgm",
                            "source_id": f"{event.get('id')}_{market.get('id')}",
                            "event_title": event.get("name", ""),
                            "market_type": market.get("name", ""),
                            "sport": competition.get("sport", {}).get("name", ""),
                            "outcomes": [
                                {
                                    "name": outcome.get("name", ""),
                                    "odds_american": outcome.get("odds", {}).get("american", 0),
                                    "odds_decimal": american_to_decimal(outcome.get("odds", {}).get("american", 0)),
                                    "probability": american_to_probability(outcome.get("odds", {}).get("american", 0)),
                                }
                                for outcome in market.get("outcomes", [])
                            ],
                            "start_time": event.get("startTime", ""),
                            "raw_data": {"event": event, "market": market},
                        })
            
            duration = asyncio.get_event_loop().time() - start_time
            log.info(
                "betmgm_fetch_complete",
                market_count=len(markets),
                duration_seconds=round(duration, 2),
            )
            
            return FetchResult(
                source="betmgm",
                success=True,
                markets=markets,
                duration_seconds=duration,
            )
            
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("betmgm_fetch_failed", error=str(e), error_type=type(e).__name__)
        return FetchResult(
            source="betmgm",
            success=False,
            error=e,
            duration_seconds=duration,
        )


async def fetch_caesars(
    session: aiohttp.ClientSession,
    config: Config,
    ctx: JobContext,
) -> FetchResult:
    """Fetch markets from Caesars Sportsbook API."""
    log = logger.bind(source="caesars", run_id=ctx.run_id)
    log.info("fetching_caesars")
    
    start_time = asyncio.get_event_loop().time()
    
    try:
        if not config.caesars_api_key:
            raise ValueError("Caesars API key not configured")
        
        # Caesars API endpoint (placeholder)
        url = "https://api.caesars.com/sportsbook/v1/events"
        
        headers = {
            "Authorization": f"Bearer {config.caesars_api_key}",
        }
        
        timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
        
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            markets = []
            for event in data.get("events", []):
                for market in event.get("markets", []):
                    markets.append({
                        "source": "caesars",
                        "source_id": f"{event.get('id')}_{market.get('id')}",
                        "event_title": event.get("name", ""),
                        "market_type": market.get("type", ""),
                        "sport": event.get("sport", ""),
                        "outcomes": [
                            {
                                "name": selection.get("name", ""),
                                "odds_american": selection.get("odds", {}).get("american", 0),
                                "odds_decimal": american_to_decimal(selection.get("odds", {}).get("american", 0)),
                                "probability": american_to_probability(selection.get("odds", {}).get("american", 0)),
                            }
                            for selection in market.get("selections", [])
                        ],
                        "start_time": event.get("startTime", ""),
                        "raw_data": {"event": event, "market": market},
                    })
            
            duration = asyncio.get_event_loop().time() - start_time
            log.info(
                "caesars_fetch_complete",
                market_count=len(markets),
                duration_seconds=round(duration, 2),
            )
            
            return FetchResult(
                source="caesars",
                success=True,
                markets=markets,
                duration_seconds=duration,
            )
            
    except Exception as e:
        duration = asyncio.get_event_loop().time() - start_time
        log.error("caesars_fetch_failed", error=str(e), error_type=type(e).__name__)
        return FetchResult(
            source="caesars",
            success=False,
            error=e,
            duration_seconds=duration,
        )


def american_to_decimal(american_odds: int | float) -> float:
    """Convert American odds to decimal odds."""
    if american_odds == 0:
        return 1.0
    if american_odds > 0:
        return 1 + (american_odds / 100)
    else:
        return 1 + (100 / abs(american_odds))


def american_to_probability(american_odds: int | float) -> float:
    """Convert American odds to implied probability."""
    if american_odds == 0:
        return 0.5
    decimal = american_to_decimal(american_odds)
    return 1 / decimal


async def fetch_all_sources(
    config: Config,
    ctx: JobContext,
) -> tuple[list[dict[str, Any]], JobContext, list[FetchResult]]:
    """
    Fetch markets from all configured sources in parallel.
    
    Returns:
        Tuple of (all_markets, updated_context, fetch_results)
    """
    log = logger.bind(run_id=ctx.run_id)
    log.info("fetching_all_sources", sources=["polymarket"] + config.get_enabled_sportsbooks())
    
    # Create aiohttp session with rate limiting
    timeout = aiohttp.ClientTimeout(total=config.fetch_timeout_seconds)
    connector = aiohttp.TCPConnector(limit=config.max_concurrent_requests)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Build list of fetch tasks
        tasks: list[asyncio.Task[FetchResult]] = []
        
        # Always try to fetch Polymarket
        tasks.append(asyncio.create_task(
            fetch_polymarket(session, config, ctx),
            name="polymarket"
        ))
        
        # Add enabled sportsbooks
        if config.is_sportsbook_enabled("draftkings"):
            tasks.append(asyncio.create_task(
                fetch_draftkings(session, config, ctx),
                name="draftkings"
            ))
        
        if config.is_sportsbook_enabled("fanduel"):
            tasks.append(asyncio.create_task(
                fetch_fanduel(session, config, ctx),
                name="fanduel"
            ))
        
        if config.is_sportsbook_enabled("betmgm"):
            tasks.append(asyncio.create_task(
                fetch_betmgm(session, config, ctx),
                name="betmgm"
            ))
        
        if config.is_sportsbook_enabled("caesars"):
            tasks.append(asyncio.create_task(
                fetch_caesars(session, config, ctx),
                name="caesars"
            ))
        
        # Execute all fetches in parallel with graceful degradation
        results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process results
    all_markets: list[dict[str, Any]] = []
    fetch_results: list[FetchResult] = []
    success_count = 0
    fail_count = 0
    
    for result in results:
        if isinstance(result, Exception):
            log.error("fetch_task_failed_unexpectedly", error=str(result))
            fail_count += 1
            continue
        
        fetch_results.append(result)
        
        if result.success:
            all_markets.extend(result.markets)
            success_count += 1
            log.info(
                "source_fetch_success",
                source=result.source,
                markets=len(result.markets),
                duration=round(result.duration_seconds, 2),
            )
        else:
            fail_count += 1
            log.warning(
                "source_fetch_failed",
                source=result.source,
                error=str(result.error) if result.error else None,
            )
    
    # Update context
    updated_ctx = ctx.with_markets_fetched(len(all_markets))
    
    log.info(
        "fetch_all_sources_complete",
        total_markets=len(all_markets),
        success_count=success_count,
        fail_count=fail_count,
        total_duration=round(sum(r.duration_seconds for r in fetch_results), 2),
    )
    
    return all_markets, updated_ctx, fetch_results
