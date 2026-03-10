# Data Ingestion Module

The data ingestion module for the Sportsbook/Arbitrage Hunter project fetches odds and market data from multiple sources, normalizes it into a common format, and stores it in a SQLite database.

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Sportsbook     │     │  Prediction     │     │  Database       │
│  Client         │     │  Market Client  │     │  (SQLite)       │
│                 │     │                 │     │                 │
│ • TheOddsAPI    │     │ • Polymarket    │────▶│ • events        │
│ • DraftKings    │────▶│ • Kalshi        │     │ • odds          │
│ • FanDuel       │     │ • Mock          │     │ • ingestion_log │
│ • Mock          │     │                 │     │                 │
└────────┬────────┘     └────────┬────────┘     └─────────────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
            ┌─────────────────┐
            │   Normalizer    │
            │                 │
            │ • Standardize   │
            │ • Convert odds  │
            │ • Map fields    │
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │   Scheduler     │
            │                 │
            │ • Manual runs   │
            │ • Scheduled     │
            │ • Logging       │
            └─────────────────┘
```

## Quick Start

### 1. Install Dependencies

```bash
# Using poetry (recommended)
pip install requests apscheduler

# Or using the requirements file
pip install -r openclaw/src/ingestion/requirements.txt
```

### 2. Configure Environment

Add to your `.env` file:

```env
# Arbitrage Hunter
ARB_HUNTER_ENABLED=true
ARB_HUNTER_DB_PATH=data/arb_hunter.db

# API Keys (for real data)
ODDS_API_KEY=your_odds_api_key_here
KALSHI_API_KEY=your_kalshi_api_key_here
```

### 3. Run Ingestion

```python
from openclaw.src.ingestion import run_ingestion_job

# Run once with mock data
result = run_ingestion_job(
    sportsbook_client="mock",
    prediction_market_client="mock",
    sport="NBA",
    category="sports",
)
```

## Components

### Sportsbook Client (`sportsbook_client.py`)

Fetches odds data from traditional sportsbooks.

**Supported Sources:**
- `the_odds_api` - The Odds API (aggregates DraftKings, FanDuel, Bet365, etc.)
- `mock` - Generates realistic fake data for testing

**Usage:**
```python
from openclaw.src.ingestion import create_sportsbook_client

# Real API
client = create_sportsbook_client("odds_api", api_key="your_key")
odds = client.fetch_odds(sport="NBA", market_type="moneyline")

# Mock data
mock_client = create_sportsbook_client("mock")
mock_odds = mock_client.fetch_odds(sport="NFL", num_events=5)
```

### Prediction Market Client (`prediction_market_client.py`)

Fetches market data from prediction markets.

**Supported Sources:**
- `polymarket` - Polymarket (no API key required)
- `kalshi` - Kalshi (API key required)
- `mock` - Generates realistic fake data

**Usage:**
```python
from openclaw.src.ingestion import create_prediction_market_client

# Polymarket
pm_client = create_prediction_market_client("polymarket")
markets = pm_client.fetch_markets(category="sports", limit=50)

# Mock data
mock_pm = create_prediction_market_client("mock")
mock_markets = mock_pm.fetch_markets(category="politics", num_markets=10)
```

### Normalizer (`normalizer.py`)

Converts raw data from various sources into a standardized format.

**Normalized Format:**
```python
{
    "event_id": "uuid",
    "sport": "NBA",
    "teams": ["Lakers", "Warriors"],
    "start_time": "2024-01-15T20:00:00Z",
    "market_type": "moneyline",
    "outcomes": [
        {"name": "Lakers", "odds": 1.85, "source": "DraftKings"},
        {"name": "Warriors", "odds": 2.10, "source": "DraftKings"}
    ],
    "source": "DraftKings",
    "timestamp": "2024-01-14T12:00:00Z",
    "url": "https://...",
    "liquidity": 50000.00,
}
```

**Usage:**
```python
from openclaw.src.ingestion import DataNormalizer

normalizer = DataNormalizer()
normalized = normalizer.normalize(raw_data, source="the_odds_api")
```

### Scheduler (`scheduler.py`)

Manages ingestion jobs and scheduling.

**Usage:**
```python
from openclaw.src.ingestion import IngestionScheduler

scheduler = IngestionScheduler()

# Add jobs
scheduler.add_sportsbook_job("dk", "mock", sport="NBA")
scheduler.add_prediction_market_job("pm", "mock", category="sports")

# Run once
results = scheduler.run_all_jobs()

# Run on schedule (every hour)
scheduler.start_scheduler(interval_seconds=3600)
```

### Database (`database/`)

SQLite database with SQLAlchemy-style models.

**Models:**
- `Event` - Sporting events/prediction markets
- `Odds` - Price/odds records with timestamps
- `IngestionLog` - Audit trail of ingestion runs

**Usage:**
```python
from openclaw.src.database import init_database, Event

db = init_database("data/arb_hunter.db")

# Query events
events = db.get_events_by_sport("NBA", limit=10)

# Get latest odds
odds = db.get_latest_odds_by_source(event_id, "DraftKings")
```

## CLI Usage

Run ingestion from command line:

```bash
# Run once with mock data
python -m openclaw.src.ingestion.scheduler --sportsbook mock --prediction-market mock

# Run with specific sport/category
python -m openclaw.src.ingestion.scheduler \
    --sportsbook mock \
    --sport NBA \
    --prediction-market mock \
    --category sports

# Run on schedule (every hour)
python -m openclaw.src.ingestion.scheduler \
    --sportsbook mock \
    --prediction-market mock \
    --schedule 3600
```

## Testing

Run the test suite:

```bash
# Run all tests
python openclaw/src/ingestion/test_ingestion.py

# Run with pytest
pytest openclaw/src/ingestion/test_ingestion.py -v
```

## Data Flow

1. **Fetch**: Client fetches raw data from source API
2. **Normalize**: Normalizer converts to common format
3. **Store**: Scheduler saves to database
4. **Log**: Ingestion run is logged for audit

## Configuration Options

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ARB_HUNTER_DB_PATH` | `data/arb_hunter.db` | Database file path |
| `ODDS_API_KEY` | - | The Odds API key |
| `KALSHI_API_KEY` | - | Kalshi API key |
| `INGESTION_INTERVAL_SECONDS` | `3600` | Schedule interval |

## API Response Examples

### The Odds API Response
```json
{
  "id": "abc123",
  "sport_key": "basketball_nba",
  "home_team": "Lakers",
  "away_team": "Warriors",
  "commence_time": "2024-01-15T20:00:00Z",
  "bookmakers": [
    {
      "key": "draftkings",
      "title": "DraftKings",
      "markets": [
        {
          "key": "h2h",
          "outcomes": [
            {"name": "Lakers", "price": -118},
            {"name": "Warriors", "price": +110}
          ]
        }
      ]
    }
  ]
}
```

### Polymarket Response
```json
{
  "id": "0x123...",
  "title": "Will Lakers win vs Warriors?",
  "category": "Sports",
  "outcomes": [
    {"name": "YES", "probability": 0.54, "price": 0.54},
    {"name": "NO", "probability": 0.46, "price": 0.46}
  ],
  "liquidity": 45000.00,
  "volume": 125000.00
}
```

## Future Enhancements

- [ ] WebSocket support for real-time odds
- [ ] Redis caching layer
- [ ] More sportsbook integrations (direct APIs)
- [ ] Historical odds tracking
- [ ] Odds change alerts
- [ ] Multi-sport concurrent fetching
