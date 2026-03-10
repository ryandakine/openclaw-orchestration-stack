"""
Data ingestion module for Sportsbook/Arbitrage Hunter.

Provides clients for fetching data from sportsbooks and prediction markets,
normalizing data, and scheduling ingestion jobs.
"""

from .sportsbook_client import (
    SportsbookClient,
    TheOddsAPIClient,
    MockSportsbookClient,
    create_sportsbook_client,
)
from .prediction_market_client import (
    PredictionMarketClient,
    PolymarketClient,
    KalshiClient,
    MockPredictionMarketClient,
    create_prediction_market_client,
)
from .normalizer import DataNormalizer, NormalizedEvent, normalize_data
from .scheduler import IngestionScheduler, IngestionJob, run_ingestion_job

__all__ = [
    # Sportsbook clients
    "SportsbookClient",
    "TheOddsAPIClient",
    "MockSportsbookClient",
    "create_sportsbook_client",
    # Prediction market clients
    "PredictionMarketClient",
    "PolymarketClient",
    "KalshiClient",
    "MockPredictionMarketClient",
    "create_prediction_market_client",
    # Normalization
    "DataNormalizer",
    "NormalizedEvent",
    "normalize_data",
    # Scheduling
    "IngestionScheduler",
    "IngestionJob",
    "run_ingestion_job",
]
