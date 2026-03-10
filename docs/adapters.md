# OpenClaw Adapter Interfaces

This document describes the adapter interfaces for integrating with sportsbooks and prediction markets in the OpenClaw Arbitrage Hunter system.

## Overview

The adapter layer provides a unified interface for fetching market data from different sources:

- **Prediction Markets**: Polymarket, Kalshi, PredictIt
- **Sportsbooks**: DraftKings, FanDuel, Bet365 (via The Odds API)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Adapter Manager                          │
│              (coordinates multiple adapters)                │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
┌───────▼──────┐ ┌──────▼─────┐ ┌──────▼──────┐
│   Sportsbook │ │Prediction  │ │  Custom     │
│   Adapter    │ │Market      │ │  Adapters   │
└───────┬──────┘ │Adapter     │ └──────┬──────┘
        │        └──────┬─────┘        │
        │               │               │
┌───────▼──────┐ ┌──────▼─────┐ ┌──────▼──────┐
│  The Odds    │ │Polymarket  │ │   User      │
│    API       │ │   API      │ │  Defined    │
└──────────────┘ └────────────┘ └─────────────┘
```

## Base Adapter Interface

All adapters must inherit from `BaseAdapter` and implement the following methods:

```python
class BaseAdapter(ABC):
    name: str                    # Adapter identifier
    source_type: SourceType      # SPORTSBOOK or PREDICTION_MARKET
    
    async def initialize(self) -> None
    async def close(self) -> None
    async def fetch_markets(...) -> list[MarketData]
    async def fetch_market(market_id: str) -> MarketData
    async def search_markets(...) -> list[MarketData]
    def normalize_market(raw_data: dict) -> MarketData
    async def check_health() -> AdapterHealth
```

## Quick Start

### Basic Usage

```python
from arb_hunter.adapters import create_adapter

# Create and use a single adapter
async with create_adapter("polymarket") as adapter:
    markets = await adapter.fetch_markets(category="politics", limit=10)
    for market in markets:
        print(f"{market.title}: {market.outcomes[0].price}")
```

### Multiple Adapters

```python
from arb_hunter.adapters import AdapterManager

manager = AdapterManager()
manager.add_adapter("polymarket")
manager.add_adapter("kalshi")
manager.add_adapter("sportsbook")

async with manager:
    # Fetch from all adapters
    results = await manager.fetch_all(category="politics")
    
    for market in results.markets:
        print(f"[{market.source}] {market.title}")
    
    # Check for failures
    if results.failed_sources:
        print(f"Failed: {results.failed_sources}")
```

### Fetch from Specific Source

```python
async with manager:
    # Fetch only from Polymarket
    result = await manager.fetch_from("polymarket", category="crypto")
    if result.success:
        for market in result.markets:
            process(market)
```

## Available Adapters

### Prediction Markets

#### Polymarket Adapter

```python
from arb_hunter.adapters import PolymarketAdapter, AdapterConfig

# No API key required for public data
config = AdapterConfig(
    timeout_seconds=30,
    enable_caching=True,
)

async with PolymarketAdapter(config) as adapter:
    # Fetch active political markets
    markets = await adapter.fetch_markets(
        category="politics",
        active_only=True,
        limit=100
    )
    
    # Search for specific markets
    trump_markets = await adapter.search_markets(
        query="Trump",
        category="politics",
        limit=20
    )
```

**Configuration:**
- No API key required
- Optional: `POLYMARKET_API_BASE` for custom endpoint
- Rate limit: 100 requests/minute (built-in)

#### Kalshi Adapter

```python
from arb_hunter.adapters import KalshiAdapter, AdapterConfig

# API key recommended for higher rate limits
config = AdapterConfig(
    api_key="your_kalshi_api_key",
    api_secret="your_secret",  # Optional
)

async with KalshiAdapter(config) as adapter:
    markets = await adapter.fetch_markets(
        category="Economics",
        active_only=True
    )
```

**Configuration:**
- Environment: `KALSHI_API_KEY`, `KALSHI_API_SECRET`
- Rate limit: 100 requests/minute

#### PredictIt Adapter

```python
from arb_hunter.adapters import PredictItAdapter

# No API key required
async with PredictItAdapter() as adapter:
    markets = await adapter.fetch_markets(category="Politics")
```

**Configuration:**
- No API key required
- Rate limit: 60 requests/minute

### Sportsbook Adapters

#### Sportsbook Adapter (The Odds API)

```python
from arb_hunter.adapters import SportsbookAdapter, AdapterConfig, MarketType

config = AdapterConfig(api_key="your_odds_api_key")

async with SportsbookAdapter(config) as adapter:
    # Select specific bookmakers
    adapter.set_bookmakers(["draftkings", "fanduel", "bet365"])
    
    # Fetch NBA moneyline odds
    markets = await adapter.fetch_markets(
        category="basketball_nba",
        market_type=MarketType.MONEYLINE,
        limit=50
    )
```

**Configuration:**
- Required: `ODDS_API_KEY` environment variable
- Get key at: https://the-odds-api.com

#### Individual Bookmaker Adapters

```python
from arb_hunter.adapters import DraftKingsAdapter, FanDuelAdapter

# These use The Odds API internally but filter to specific bookmakers
async with DraftKingsAdapter(config) as dk:
    markets = await dk.fetch_markets(category="americanfootball_nfl")

async with FanDuelAdapter(config) as fd:
    markets = await fd.fetch_markets(category="americanfootball_nfl")
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POLYMARKET_API_BASE` | Custom Polymarket endpoint | No |
| `KALSHI_API_KEY` | Kalshi API key | Recommended |
| `KALSHI_API_SECRET` | Kalshi API secret | Optional |
| `ODDS_API_KEY` | The Odds API key | Yes (for sportsbooks) |
| `PREDICTIT_TIMEOUT` | Request timeout | No (default: 30s) |

### AdapterConfig Options

```python
@dataclass
class AdapterConfig:
    api_key: str | None = None           # API key
    api_secret: str | None = None        # API secret
    base_url: str | None = None          # Custom endpoint
    timeout_seconds: float = 30.0        # Request timeout
    max_retries: int = 5                 # Retry attempts
    enable_caching: bool = True          # Enable response caching
    cache_ttl_seconds: int = 60          # Cache TTL
    rate_limit_requests_per_minute: int | None = None
    additional_headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
```

## Data Models

### MarketData

```python
@dataclass
class MarketData:
    id: str                          # Unique market ID
    source: str                      # Source name (e.g., "polymarket")
    source_type: SourceType          # SPORTSBOOK or PREDICTION_MARKET
    title: str                       # Market title
    description: str                 # Market description
    category: str                    # Category (e.g., "politics")
    market_type: str                 # Type (e.g., "binary", "moneyline")
    outcomes: list[Outcome]          # Possible outcomes
    start_time: datetime | None      # Event start time
    close_time: datetime | None      # Betting close time
    is_active: bool                  # Whether market is active
    is_settled: bool                 # Whether market is settled
    last_update: datetime | None     # Last price update
    url: str                         # Direct market link
    fees: dict[str, float]           # Fee structure
    raw_data: dict[str, Any]         # Original API response
```

### Outcome

```python
@dataclass
class Outcome:
    id: str                    # Unique outcome ID
    name: str                  # Outcome name (e.g., "Yes", "Trump")
    price: float              # Current price/probability
    implied_probability: float # Implied probability (0.0-1.0)
    volume: float | None      # Trading volume
    liquidity: float | None   # Available liquidity
    metadata: dict[str, Any]  # Additional data
```

## Error Handling

All adapters use a consistent error hierarchy:

```python
AdapterError              # Base error
├── MarketNotFoundError   # Market doesn't exist
├── RateLimitError        # Rate limit exceeded
├── AuthenticationError   # Invalid credentials
└── TimeoutError          # Request timeout
```

Example:

```python
from arb_hunter.adapters import MarketNotFoundError, RateLimitError

async with adapter:
    try:
        market = await adapter.fetch_market("invalid-id")
    except MarketNotFoundError:
        print("Market not found")
    except RateLimitError as e:
        print(f"Rate limited. Retry after: {e.retry_after}s")
    except AdapterError as e:
        print(f"Adapter error: {e.adapter_name} - {e}")
```

## Rate Limiting

Adapters include built-in rate limiting with token bucket algorithm:

```python
from arb_hunter.adapters import AdapterConfig

# Custom rate limit
config = AdapterConfig(
    rate_limit_requests_per_minute=50,
)

async with SomeAdapter(config) as adapter:
    # Requests will be automatically throttled
    for i in range(100):
        await adapter.fetch_market(f"market-{i}")
```

Default rate limits:

| Source | Requests/Minute | Burst |
|--------|-----------------|-------|
| Polymarket | 100 | 100 |
| Kalshi | 100 | 50 |
| PredictIt | 60 | 20 |
| The Odds API | 500/month | 10 |

## Retry Logic

All adapters implement exponential backoff with jitter:

- **Max attempts**: 5 (configurable)
- **Base delay**: 1 second
- **Backoff factor**: 2x
- **Max delay**: 30 seconds
- **Jitter**: 0-1 second random delay

Retryable errors:
- 5xx server errors
- 429 rate limit
- Network timeouts
- Connection errors

Non-retryable errors:
- 4xx client errors (except 429)
- Authentication failures
- Validation errors

## Health Monitoring

Check adapter health status:

```python
async with adapter:
    health = await adapter.check_health()
    print(f"Status: {health.status}")
    print(f"Last success: {health.last_successful_request}")
    print(f"Consecutive failures: {health.consecutive_failures}")
```

With AdapterManager:

```python
async with manager:
    health_status = await manager.check_all_health()
    for name, status in health_status.items():
        print(f"{name}: {status['status']}")
```

## Creating Custom Adapters

Implement a custom adapter by inheriting from `BaseAdapter`:

```python
from arb_hunter.adapters import BaseAdapter, MarketData, SourceType

class MyCustomAdapter(BaseAdapter):
    name = "my_custom"
    source_type = SourceType.PREDICTION_MARKET
    
    async def initialize(self) -> None:
        # Setup connections, authenticate
        self._client = MyAPIClient()
        self._initialized = True
    
    async def close(self) -> None:
        # Cleanup resources
        await self._client.close()
        self._initialized = False
    
    async def fetch_markets(...) -> list[MarketData]:
        # Fetch and normalize data
        raw_data = await self._client.get_markets()
        return [self.normalize_market(d) for d in raw_data]
    
    async def fetch_market(self, market_id: str) -> MarketData:
        raw_data = await self._client.get_market(market_id)
        return self.normalize_market(raw_data)
    
    async def search_markets(...) -> list[MarketData]:
        # Implement search
        pass
    
    def normalize_market(self, raw_data: dict) -> MarketData:
        # Convert to standard format
        return MarketData(
            id=raw_data["id"],
            source=self.name,
            source_type=self.source_type,
            title=raw_data["title"],
            # ... other fields
        )
```

Register custom adapter:

```python
from arb_hunter.adapters import get_adapter_factory

factory = get_adapter_factory()
factory.register_adapter("my_custom", MyCustomAdapter)

# Now use like any other adapter
adapter = factory.create("my_custom")
```

## Testing

Run adapter tests:

```bash
# Test specific adapter
pytest tests/unit/adapters/test_polymarket_adapter.py -v

# Test all adapters
pytest tests/unit/adapters/ -v

# Test with real API calls (requires API keys)
pytest tests/integration/adapters/ -v --live
```

## Troubleshooting

### Common Issues

**Adapter not initialized**
```
AdapterError: Adapter not initialized. Use async context manager.
```
Solution: Use `async with` statement or call `await adapter.initialize()`

**Rate limit exceeded**
```
RateLimitError: Rate limit exceeded
```
Solution: The adapter will automatically retry. Consider reducing request frequency.

**Market not found**
```
MarketNotFoundError: Market XYZ not found
```
Solution: Verify the market ID format for the specific adapter.

### Debug Logging

Enable debug logging to see API calls:

```python
import logging
logging.getLogger('arb_hunter.adapters').setLevel(logging.DEBUG)
```

## API Reference

See the module docstrings for detailed API documentation:

- `arb_hunter.adapters.base` - Base adapter interface
- `arb_hunter.adapters.prediction_market_adapter` - PM adapters
- `arb_hunter.adapters.sportsbook_adapter` - Sportsbook adapters
- `arb_hunter.adapters.adapter_factory` - Factory and registry
- `arb_hunter.adapters.adapter_manager` - Manager for multiple adapters
