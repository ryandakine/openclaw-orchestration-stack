"""
Pytest Configuration and Fixtures for Arb Hunter Tests

Provides: event_loop, mock_http_client, temp_dirs, and shared fixtures
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

# Import fixtures from fixtures.py
from .fixtures import (
    mock_polymarket_response,
    mock_odds_api_response,
    mock_odds_api_eagles_cowboys,
    mock_odds_api_lakers_warriors,
    get_test_config,
    expected_true_arbitrage,
)


# =============================================================================
# Event Loop Fixture
# =============================================================================

@pytest_asyncio.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# HTTP Client Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def mock_http_client() -> AsyncGenerator[AsyncMock, None]:
    """Mock HTTP client for testing API calls."""
    client = AsyncMock(spec=AsyncClient)
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.close = AsyncMock()
    yield client


@pytest_asyncio.fixture
async def mock_httpx_response() -> AsyncGenerator[type[Response], None]:
    """Factory for creating mock httpx responses."""
    def _create_response(
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        raise_for_status: Exception | None = None
    ) -> Response:
        response = MagicMock(spec=Response)
        response.status_code = status_code
        response.json = MagicMock(return_value=json_data or {})
        response.text = text
        response.headers = headers or {}
        
        if raise_for_status:
            response.raise_for_status = MagicMock(side_effect=raise_for_status)
        else:
            response.raise_for_status = MagicMock()
            
        return response
    
    yield _create_response


@pytest.fixture
def mock_responses() -> dict[str, Any]:
    """Dictionary of mock API responses for testing."""
    return {
        "polymarket": mock_polymarket_response(),
        "odds_api_chiefs": mock_odds_api_response(),
        "odds_api_eagles": mock_odds_api_eagles_cowboys(),
        "odds_api_lakers": mock_odds_api_lakers_warriors(),
    }


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for test file operations."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def temp_cache_dir(temp_dir: Path) -> Path:
    """Provide a temporary cache directory."""
    cache_dir = temp_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir


@pytest.fixture
def temp_logs_dir(temp_dir: Path) -> Path:
    """Provide a temporary logs directory."""
    logs_dir = temp_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    return logs_dir


@pytest.fixture
def temp_state_dir(temp_dir: Path) -> Path:
    """Provide a temporary state directory for circuit breaker state."""
    state_dir = temp_dir / "state"
    state_dir.mkdir(exist_ok=True)
    return state_dir


# =============================================================================
# Configuration Fixtures
# =============================================================================

@pytest.fixture
def test_config() -> dict[str, Any]:
    """Test configuration with relaxed thresholds."""
    return get_test_config()


@pytest.fixture
def strict_test_config() -> dict[str, Any]:
    """Strict test configuration for filtering tests."""
    config = get_test_config()
    config["arbitrage"]["min_edge_percent"] = 5.0
    config["arbitrage"]["min_net_edge_percent"] = 3.0
    config["filters"]["min_liquidity_usd"] = 500000
    config["filters"]["max_odds_staleness_minutes"] = 5
    config["filters"]["min_match_confidence"] = 0.95
    return config


@pytest.fixture
def lenient_test_config() -> dict[str, Any]:
    """Lenient test configuration for edge cases."""
    config = get_test_config()
    config["arbitrage"]["min_edge_percent"] = 0.1
    config["arbitrage"]["min_net_edge_percent"] = 0.0
    config["filters"]["min_liquidity_usd"] = 100
    config["filters"]["max_odds_staleness_minutes"] = 120
    config["filters"]["min_match_confidence"] = 0.70
    return config


# =============================================================================
# Mock Data Fixtures
# =============================================================================

@pytest.fixture
def mock_polymarket_data() -> dict[str, Any]:
    """Standard mock Polymarket data."""
    return mock_polymarket_response()


@pytest.fixture
def mock_sportsbook_data() -> dict[str, Any]:
    """Standard mock sportsbook data."""
    return mock_odds_api_response()


@pytest.fixture
def true_arbitrage_data() -> list[dict[str, Any]]:
    """True arbitrage scenario data."""
    return expected_true_arbitrage()


# =============================================================================
# Service Mocks
# =============================================================================

@pytest.fixture
def mock_polymarket_service() -> MagicMock:
    """Mock Polymarket service."""
    service = MagicMock()
    service.fetch_markets = AsyncMock(return_value=mock_polymarket_response())
    service.get_market_by_id = AsyncMock(return_value=mock_polymarket_response()["markets"][0])
    service.get_market_orderbook = AsyncMock(return_value={
        "bids": [{"price": 0.65, "size": 1000}],
        "asks": [{"price": 0.66, "size": 1000}]
    })
    return service


@pytest.fixture
def mock_odds_api_service() -> MagicMock:
    """Mock Odds API service."""
    service = MagicMock()
    service.fetch_events = AsyncMock(return_value=[mock_odds_api_response()])
    service.fetch_odds_for_event = AsyncMock(return_value=mock_odds_api_response())
    return service


@pytest.fixture
def mock_telegram_service() -> MagicMock:
    """Mock Telegram alert service."""
    service = MagicMock()
    service.send_alert = AsyncMock(return_value={"message_id": 12345, "ok": True})
    service.send_batch_alerts = AsyncMock(return_value=[{"message_id": 12345, "ok": True}])
    service.format_arbitrage_message = MagicMock(return_value="Test arbitrage message")
    return service


@pytest.fixture
def mock_circuit_breaker() -> MagicMock:
    """Mock circuit breaker."""
    cb = MagicMock()
    cb.is_open = False
    cb.is_closed = True
    cb.can_execute = MagicMock(return_value=True)
    cb.record_success = MagicMock()
    cb.record_failure = MagicMock()
    cb.record_timeout = MagicMock()
    cb.get_state = MagicMock(return_value="CLOSED")
    return cb


# =============================================================================
# Pipeline Component Fixtures
# =============================================================================

@pytest.fixture
def mock_normalizer() -> MagicMock:
    """Mock market normalizer."""
    normalizer = MagicMock()
    normalizer.normalize_polymarket = MagicMock(return_value=[{
        "market_id": "test_pm_001",
        "source": "polymarket",
        "event_name": "Test Event",
        "normalized": True
    }])
    normalizer.normalize_sportsbook = MagicMock(return_value=[{
        "market_id": "test_sb_001",
        "source": "draftkings",
        "event_name": "Test Event",
        "normalized": True
    }])
    return normalizer


@pytest.fixture
def mock_matcher() -> MagicMock:
    """Mock market matcher."""
    matcher = MagicMock()
    matcher.find_matches = MagicMock(return_value=[{
        "match_id": "match_001",
        "confidence": 0.95,
        "polymarket_id": "test_pm_001",
        "sportsbook_id": "test_sb_001"
    }])
    matcher.calculate_similarity = MagicMock(return_value=0.95)
    return matcher


@pytest.fixture
def mock_arbitrage_calculator() -> MagicMock:
    """Mock arbitrage calculator."""
    calculator = MagicMock()
    calculator.calculate_opportunity = MagicMock(return_value={
        "is_arbitrage": True,
        "gross_edge_percent": 5.0,
        "net_edge_percent": 3.5,
        "side_a": {"stake": 500, "odds": 2.0},
        "side_b": {"stake": 476, "odds": 2.1},
        "net_profit": 35
    })
    return calculator


@pytest.fixture
def mock_filter_engine() -> MagicMock:
    """Mock filter engine."""
    engine = MagicMock()
    engine.apply_filters = MagicMock(return_value=[{
        "is_arbitrage": True,
        "net_edge_percent": 3.5,
        "passed_filters": True
    }])
    engine.check_liquidity = MagicMock(return_value=True)
    engine.check_staleness = MagicMock(return_value=True)
    engine.check_confidence = MagicMock(return_value=True)
    return engine


# =============================================================================
# State Management Fixtures
# =============================================================================

@pytest.fixture
def alert_deduplication_cache() -> dict[str, Any]:
    """In-memory cache for alert deduplication testing."""
    return {}


@pytest.fixture
def circuit_breaker_state(temp_state_dir: Path) -> dict[str, Any]:
    """Circuit breaker state storage."""
    return {
        "failures": 0,
        "successes": 0,
        "consecutive_failures": 0,
        "last_failure_time": None,
        "state": "CLOSED",
        "state_file": temp_state_dir / "circuit_breaker.json"
    }


# =============================================================================
# Test Data Generators
# =============================================================================

@pytest.fixture
def generate_test_market() -> Generator:
    """Factory fixture to generate test markets."""
    def _create_market(
        market_id: str = "test_001",
        source: str = "polymarket",
        event_name: str = "Test Event",
        teams: list[str] | None = None,
        odds: float = 2.0,
        liquidity: float = 100000,
        **kwargs
    ) -> dict[str, Any]:
        return {
            "market_id": market_id,
            "source": source,
            "event_name": event_name,
            "teams": teams or ["Team A", "Team B"],
            "market_type": "h2h",
            "outcomes": {
                "home": {"name": "Team A", "decimal_odds": odds},
                "away": {"name": "Team B", "decimal_odds": odds}
            },
            "start_time": __import__('datetime').datetime.now(),
            "sport": "football",
            "league": "NFL",
            "liquidity_usd": liquidity,
            **kwargs
        }
    
    yield _create_market


@pytest.fixture
def generate_test_arbitrage() -> Generator:
    """Factory fixture to generate test arbitrage opportunities."""
    def _create_arbitrage(
        edge: float = 5.0,
        net_edge: float = 3.0,
        liquidity_a: float = 100000,
        liquidity_b: float = 100000
    ) -> dict[str, Any]:
        return {
            "match_id": f"arb_{edge:.1f}",
            "is_arbitrage": True,
            "gross_edge_percent": edge,
            "net_edge_percent": net_edge,
            "side_a": {
                "venue": "polymarket",
                "odds_decimal": 2.0,
                "stake": 1000,
                "liquidity": liquidity_a
            },
            "side_b": {
                "venue": "sportsbook",
                "odds_decimal": 2.1,
                "stake": 952,
                "liquidity": liquidity_b
            },
            "net_profit": net_edge * 10,
            "roi_percent": net_edge
        }
    
    yield _create_arbitrage


# =============================================================================
# Pytest Hooks
# =============================================================================

def pytest_configure(config: pytest.Config) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end tests")
    config.addinivalue_line("markers", "api: marks tests as API-dependent tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list) -> None:
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Auto-mark tests based on name patterns
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)
        if "e2e" in item.nodeid.lower() or "end_to_end" in item.nodeid.lower():
            item.add_marker(pytest.mark.e2e)
        if "test_failure" in item.nodeid.lower():
            item.add_marker(pytest.mark.slow)
