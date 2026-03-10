"""OpenClaw Arbitrage Hunter - Exchange/Bookie Adapters.

This module provides adapter interfaces for different data sources:
- Sportsbooks (DraftKings, FanDuel, Bet365, etc. via The Odds API)
- Prediction Markets (Polymarket, Kalshi, PredictIt)

All adapters implement the BaseAdapter interface for consistent usage.
"""

from .base import (
    BaseAdapter,
    AdapterConfig,
    MarketData,
    Outcome,
    SourceType,
    SourceType,
    AdapterHealth,
    AdapterStatus,
    AdapterError,
    MarketNotFoundError,
    RateLimitError,
    AuthenticationError,
)
from .sportsbook_adapter import (
    SportsbookAdapter,
    SportsbookMarket,
    OddsFormat,
    MarketType,
    DraftKingsAdapter,
    FanDuelAdapter,
    Bet365Adapter,
)
from .prediction_market_adapter import (
    PolymarketAdapter,
    KalshiAdapter,
    PredictItAdapter,
    PMMarket,
    PMOutcomeType,
    PMMarketStatus,
)
from .adapter_factory import (
    AdapterFactory,
    AdapterRegistry,
    create_adapter,
    get_adapter_factory,
)
from .adapter_manager import (
    AdapterManager,
    ManagedAdapterContext,
    FetchResult,
    AggregatedMarkets,
    fetch_from_all_sources,
    search_all_sources,
)

__all__ = [
    # Base
    "BaseAdapter",
    "AdapterConfig",
    "MarketData",
    "Outcome",
    "SourceType",
    "AdapterHealth",
    "AdapterStatus",
    # Errors
    "AdapterError",
    "MarketNotFoundError",
    "RateLimitError",
    "AuthenticationError",
    # Sportsbook
    "SportsbookAdapter",
    "SportsbookMarket",
    "OddsFormat",
    "MarketType",
    "DraftKingsAdapter",
    "FanDuelAdapter",
    "Bet365Adapter",
    # Prediction Market
    "PolymarketAdapter",
    "KalshiAdapter",
    "PredictItAdapter",
    "PMMarket",
    "PMOutcomeType",
    "PMMarketStatus",
    # Factory & Manager
    "AdapterFactory",
    "AdapterRegistry",
    "AdapterManager",
    "ManagedAdapterContext",
    "FetchResult",
    "AggregatedMarkets",
    "create_adapter",
    "get_adapter_factory",
    "fetch_from_all_sources",
    "search_all_sources",
]
