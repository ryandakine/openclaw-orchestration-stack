"""Pipeline orchestrating fetch → transform → validate → output."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from .category_mapper import CategoryMapper
from .liquidity_normalizer import LiquidityNormalizer, apply_liquidity_normalization
from .market_cache import MarketCache
from .market_normalization_error import MarketNormalizationError
from .normalized_market_schema import NormalizedMarket
from .odds_api_fetcher import OddsAPIFetcher
from .polymarket_fetcher import PolymarketFetcher
from .polymarket_transformer import PolymarketTransformer
from .sportsbook_transformer import SportsbookTransformer
from .timestamp_validator import TimestampValidator


@dataclass
class PipelineConfig:
    """Configuration for the normalizer pipeline."""

    # Fetch settings
    enable_polymarket: bool = True
    enable_sportsbooks: bool = True
    sportsbook_targets: set[str] = field(
        default_factory=lambda: {"draftkings", "fanduel", "bet365"}
    )
    sports: list[str] = field(
        default_factory=lambda: [
            "americanfootball_nfl",
            "basketball_nba",
            "baseball_mlb",
            "icehockey_nhl",
        ]
    )

    # Validation settings
    freshness_threshold: float = 120.0
    reject_stale: bool = True

    # Processing settings
    normalize_liquidity: bool = True
    auto_categorize: bool = True
    cache_raw_data: bool = True

    # Rate limiting
    max_concurrent_requests: int = 5


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    markets: list[NormalizedMarket]
    errors: list[MarketNormalizationError]
    stats: PipelineStats


@dataclass
class PipelineStats:
    """Statistics from pipeline execution."""

    total_fetched: int = 0
    polymarket_count: int = 0
    sportsbook_count: int = 0
    validation_rejected: int = 0
    transform_errors: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary."""
        return {
            "total_fetched": self.total_fetched,
            "polymarket_count": self.polymarket_count,
            "sportsbook_count": self.sportsbook_count,
            "validation_rejected": self.validation_rejected,
            "transform_errors": self.transform_errors,
            "duration_seconds": self.duration_seconds,
        }


class NormalizerPipeline:
    """Orchestrates the complete market normalization pipeline.

    Pipeline stages:
    1. Fetch: Retrieve data from Polymarket and/or sportsbooks
    2. Cache: Store raw responses (if enabled)
    3. Transform: Convert to NormalizedMarket format
    4. Validate: Check data freshness
    5. Normalize: Liquidity and category normalization
    6. Output: Return list of valid NormalizedMarket objects
    """

    def __init__(
        self,
        config: PipelineConfig | None = None,
        cache: MarketCache | None = None,
        polymarket_fetcher: PolymarketFetcher | None = None,
        odds_api_fetcher: OddsAPIFetcher | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            config: Pipeline configuration
            cache: Cache instance (created if None)
            polymarket_fetcher: Polymarket fetcher (created if None)
            odds_api_fetcher: Odds API fetcher (created if None)
        """
        self.config = config or PipelineConfig()
        self.cache = cache or MarketCache()
        self.polymarket_fetcher = polymarket_fetcher or PolymarketFetcher()
        self.odds_api_fetcher = odds_api_fetcher
        self.polymarket_transformer = PolymarketTransformer()
        self.sportsbook_transformer = SportsbookTransformer()
        self.liquidity_normalizer = LiquidityNormalizer()
        self.category_mapper = CategoryMapper()
        self.validator = TimestampValidator(
            threshold_seconds=self.config.freshness_threshold,
            reject_stale=self.config.reject_stale,
        )

        # Semaphore for rate limiting concurrent requests
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

    async def fetch_polymarket(self) -> list[NormalizedMarket]:
        """Fetch and transform Polymarket data.

        Returns:
            List of normalized markets
        """
        if not self.config.enable_polymarket:
            return []

        try:
            # Fetch markets
            raw_markets = await self.polymarket_fetcher.get_markets(
                limit=100,
                active=True,
            )

            # Cache raw data if enabled
            if self.config.cache_raw_data:
                for market in raw_markets:
                    market_id = str(market.get("id", "unknown"))
                    await self.cache.store(
                        f"polymarket:{market_id}",
                        market,
                    )

            # Transform
            normalized = self.polymarket_transformer.transform_many(raw_markets)
            return normalized

        except MarketNormalizationError as e:
            return []

    async def fetch_sportsbooks(self) -> list[NormalizedMarket]:
        """Fetch and transform sportsbook data.

        Returns:
            List of normalized markets
        """
        if not self.config.enable_sportsbooks:
            return []

        if not self.odds_api_fetcher:
            try:
                self.odds_api_fetcher = OddsAPIFetcher()
            except MarketNormalizationError:
                return []

        all_markets: list[NormalizedMarket] = []

        for sport in self.config.sports:
            try:
                # Fetch odds for this sport
                bookmakers = ",".join(self.config.sportsbook_targets)
                raw_events = await self.odds_api_fetcher.get_odds(
                    sport=sport,
                    bookmakers=bookmakers,
                )

                # Cache raw data
                if self.config.cache_raw_data:
                    for event in raw_events:
                        event_id = str(event.get("id", "unknown"))
                        await self.cache.store(
                            f"oddsapi:{sport}:{event_id}",
                            event,
                        )

                # Transform
                markets = self.sportsbook_transformer.transform_many_events(
                    events=raw_events,
                    sport=sport,
                    target_bookmakers=self.config.sportsbook_targets,
                )
                all_markets.extend(markets)

            except MarketNormalizationError:
                continue

        return all_markets

    async def run(
        self,
        progress_callback: Callable[[str], None] | None = None,
    ) -> PipelineResult:
        """Run the complete pipeline.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Pipeline result with markets and stats
        """
        import time

        start_time = time.time()
        stats = PipelineStats()
        errors: list[MarketNormalizationError] = []

        def report(stage: str) -> None:
            if progress_callback:
                progress_callback(stage)

        # Stage 1: Fetch
        report("fetching")
        polymarket_task = asyncio.create_task(self.fetch_polymarket())
        sportsbook_task = asyncio.create_task(self.fetch_sportsbooks())

        polymarket_markets = await polymarket_task
        sportsbook_markets = await sportsbook_task

        stats.polymarket_count = len(polymarket_markets)
        stats.sportsbook_count = len(sportsbook_markets)
        stats.total_fetched = stats.polymarket_count + stats.sportsbook_count

        all_markets = polymarket_markets + sportsbook_markets

        # Stage 2: Validate freshness
        report("validating")
        if self.config.reject_stale:
            accepted, rejected = self.validator.filter_markets(all_markets)
            stats.validation_rejected = len(rejected)
            all_markets = accepted

        # Stage 3: Normalize liquidity
        if self.config.normalize_liquidity:
            report("normalizing_liquidity")
            all_markets = apply_liquidity_normalization(all_markets)

        # Stage 4: Auto-categorize
        if self.config.auto_categorize:
            report("categorizing")
            all_markets = self.category_mapper.apply_to_markets(
                all_markets,
                override=False,
            )

        # Update stats
        stats.duration_seconds = time.time() - start_time

        report("complete")

        return PipelineResult(
            markets=all_markets,
            errors=errors,
            stats=stats,
        )

    async def run_single_source(
        self,
        source: str,
        **kwargs: dict[str, Any],
    ) -> PipelineResult:
        """Run pipeline for a single source.

        Args:
            source: 'polymarket' or 'sportsbooks'
            **kwargs: Additional arguments for fetcher

        Returns:
            Pipeline result
        """
        stats = PipelineStats()
        errors: list[MarketNormalizationError] = []

        if source == "polymarket":
            markets = await self.fetch_polymarket()
            stats.polymarket_count = len(markets)
        elif source == "sportsbooks":
            markets = await self.fetch_sportsbooks()
            stats.sportsbook_count = len(markets)
        else:
            raise MarketNormalizationError(f"Unknown source: {source}")

        stats.total_fetched = len(markets)

        # Apply validation and normalization
        if self.config.reject_stale:
            accepted, _ = self.validator.filter_markets(markets)
            stats.validation_rejected = len(markets) - len(accepted)
            markets = accepted

        if self.config.normalize_liquidity:
            markets = apply_liquidity_normalization(markets)

        if self.config.auto_categorize:
            markets = self.category_mapper.apply_to_markets(markets)

        return PipelineResult(
            markets=markets,
            errors=errors,
            stats=stats,
        )

    def get_stats(self) -> dict[str, Any]:
        """Get combined pipeline statistics.

        Returns:
            Stats dictionary
        """
        return {
            "validator": self.validator.get_stats(),
            "polymarket_transformer": self.polymarket_transformer.get_stats(),
            "sportsbook_transformer": self.sportsbook_transformer.get_stats(),
            "category_mapper": self.category_mapper.get_mapping_stats(),
        }

    async def close(self) -> None:
        """Cleanup resources."""
        await self.polymarket_fetcher.close()
        if self.odds_api_fetcher:
            await self.odds_api_fetcher.close()

    async def __aenter__(self) -> NormalizerPipeline:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
