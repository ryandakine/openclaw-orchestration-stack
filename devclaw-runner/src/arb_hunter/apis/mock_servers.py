"""Mock API servers for testing API integrations."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Callable
from urllib.parse import urlparse

import pytest

logger = logging.getLogger(__name__)


@dataclass
class MockResponse:
    """Mock API response configuration."""
    status_code: int = 200
    json_data: dict[str, Any] | list[Any] | None = None
    text: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0


@dataclass
class MockEndpoint:
    """Mock API endpoint configuration."""
    method: str
    path: str
    response: MockResponse
    callback: Callable[..., MockResponse] | None = None


class MockAPIServer:
    """Mock API server for testing."""
    
    def __init__(self, base_url: str = "https://mock.api") -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoints: dict[str, MockEndpoint] = {}
        self._call_counts: dict[str, int] = defaultdict(int)
    
    def register(
        self,
        method: str,
        path: str,
        response: MockResponse | None = None,
        callback: Callable[..., MockResponse] | None = None,
    ) -> None:
        key = f"{method.upper()}:{path}"
        self.endpoints[key] = MockEndpoint(
            method=method.upper(),
            path=path,
            response=response or MockResponse(),
            callback=callback,
        )
    
    def _match_endpoint(self, method: str, path: str) -> MockEndpoint | None:
        key = f"{method.upper()}:{path}"
        if key in self.endpoints:
            return self.endpoints[key]
        
        for endpoint in self.endpoints.values():
            if endpoint.method != method.upper():
                continue
            endpoint_pattern = endpoint.path.replace("*", "")
            if path.startswith(endpoint_pattern) or endpoint.path == "*":
                return endpoint
        return None
    
    def get_response(self, method: str, path: str, **kwargs: Any) -> MockResponse:
        self._call_counts[f"{method}:{path}"] += 1
        endpoint = self._match_endpoint(method, path)
        
        if endpoint is None:
            return MockResponse(
                status_code=404,
                json_data={"error": "Not found"},
            )
        
        if endpoint.callback:
            return endpoint.callback(method=method, path=path, **kwargs)
        return endpoint.response
    
    @property
    def call_count(self) -> int:
        return sum(self._call_counts.values())
    
    def reset(self) -> None:
        self._call_counts.clear()
    
    def setup_polymarket(self) -> None:
        self.register(
            "GET",
            "/markets",
            MockResponse(
                status_code=200,
                json_data=[{
                    "id": "market-1",
                    "slug": "btc-100k",
                    "question": "Will BTC hit 100K?",
                    "active": True,
                    "liquidity": 150000.50,
                }],
            ),
        )
    
    def setup_kalshi(self) -> None:
        self.register(
            "GET",
            "/markets",
            MockResponse(
                status_code=200,
                json_data={
                    "markets": [{
                        "ticker": "BTC-100K",
                        "title": "BTC $100K",
                        "status": "active",
                    }],
                    "cursor": None,
                },
            ),
        )
    
    def setup_odds_api(self) -> None:
        self.register(
            "GET",
            "/sports",
            MockResponse(
                status_code=200,
                json_data=[
                    {"key": "soccer_epl", "group": "Soccer", "active": True},
                    {"key": "basketball_nba", "group": "Basketball", "active": True},
                ],
            ),
        )
    
    def setup_predictit(self) -> None:
        self.register(
            "GET",
            "/markets/",
            MockResponse(
                status_code=200,
                json_data={
                    "markets": [{"id": 1234, "name": "BTC 100K?", "status": "Open"}]
                },
            ),
        )
    
    def setup_error_scenarios(self) -> None:
        self.register(
            "GET",
            "/rate-limited",
            MockResponse(
                status_code=429,
                json_data={"error": "Rate limit exceeded"},
            ),
        )
        self.register(
            "GET",
            "/server-error",
            MockResponse(
                status_code=500,
                json_data={"error": "Server error"},
            ),
        )


@pytest.fixture
def mock_api_server():
    server = MockAPIServer()
    yield server
    server.reset()
