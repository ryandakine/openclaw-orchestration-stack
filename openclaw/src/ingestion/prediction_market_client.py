"""
Prediction market data ingestion client.

Fetches market data from Polymarket, Kalshi, and other prediction markets.
"""

import os
import uuid
import random
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
import httpx

logger = logging.getLogger(__name__)


class PredictionMarketClient(ABC):
    """
    Abstract base class for prediction market clients.
    
    All prediction market clients must implement the fetch_markets method
    that returns market data in a normalized raw format.
    """
    
    def __init__(self, source_name: str, base_url: Optional[str] = None):
        self.source_name = source_name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "OpenClaw-ArbHunter/1.0"
        })
    
    @abstractmethod
    def fetch_markets(
        self,
        category: Optional[str] = None,
        status: str = "open",
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch market data from the prediction market.
        
        Args:
            category: Market category filter (e.g., 'sports', 'politics')
            status: Market status filter (open, closed, resolved)
            **kwargs: Additional client-specific parameters
            
        Returns:
            List of raw market data
        """
        pass
    
    def fetch_market_by_id(self, market_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a specific market by ID.
        
        Args:
            market_id: Unique market identifier
            
        Returns:
            Market data or None if not found
        """
        # Default implementation filters from fetch_markets
        markets = self.fetch_markets()
        for market in markets:
            if market.get("id") == market_id or market.get("market_id") == market_id:
                return market
        return None
    
    def health_check(self) -> bool:
        """Check if the API is accessible."""
        try:
            if self.base_url:
                response = self.session.get(
                    f"{self.base_url}/health",
                    timeout=5
                )
                return response.status_code == 200
            return True
        except Exception as e:
            logger.warning(f"Health check failed for {self.source_name}: {e}")
            return False


class PolymarketClient(PredictionMarketClient):
    """
    Client for Polymarket (https://polymarket.com)
    
    Polymarket is a decentralized prediction market platform.
    Uses the Gamma API (Polymarket's public API).
    """
    
    GAMMA_API_BASE = "https://gamma-api.polymarket.com"
    
    # Category mappings
    CATEGORIES = {
        "sports": "Sports",
        "politics": "Politics",
        "crypto": "Crypto",
        "entertainment": "Entertainment",
        "science": "Science",
        "business": "Business",
        "technology": "Technology",
    }
    
    def __init__(self):
        super().__init__(
            source_name="polymarket",
            base_url=self.GAMMA_API_BASE
        )
    
    def fetch_markets(
        self,
        category: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
        offset: int = 0,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets from Polymarket.
        
        Args:
            category: Market category (sports, politics, crypto, etc.)
            status: Market status (open, closed, resolved)
            limit: Maximum number of markets to fetch
            offset: Pagination offset
            
        Returns:
            List of Polymarket markets
        """
        url = f"{self.GAMMA_API_BASE}/markets"
        
        params = {
            "limit": limit,
            "offset": offset,
            "active": status == "open",
            "closed": status == "closed",
            "archived": False,
        }
        
        if category:
            params["category"] = self.CATEGORIES.get(category.lower(), category)
        
        try:
            logger.info(f"Fetching markets from Polymarket (category={category})")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            markets = data if isinstance(data, list) else data.get("markets", [])
            
            logger.info(f"Fetched {len(markets)} markets from Polymarket")
            
            # Add source metadata
            for market in markets:
                market["_source"] = self.source_name
                market["_fetched_at"] = datetime.utcnow().isoformat()
            
            return markets
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch markets from Polymarket: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Polymarket markets: {e}")
            return []
    
    def fetch_market_orderbook(
        self,
        market_id: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch order book for a specific market.
        
        Args:
            market_id: Polymarket market ID
            
        Returns:
            Order book data with bids/asks
        """
        url = f"{self.GAMMA_API_BASE}/markets/{market_id}/orderbook"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch orderbook for {market_id}: {e}")
            return None
    
    def fetch_events(
        self,
        category: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch events from Polymarket.
        
        Events are groups of related markets.
        
        Args:
            category: Event category filter
            
        Returns:
            List of events
        """
        url = f"{self.GAMMA_API_BASE}/events"
        
        params = {"active": True, "closed": False}
        if category:
            params["category"] = self.CATEGORIES.get(category.lower(), category)
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch events from Polymarket: {e}")
            return []


class KalshiClient(PredictionMarketClient):
    """
    Client for Kalshi (https://kalshi.com)
    
    Kalshi is a regulated prediction market exchange in the US.
    Requires API key for access.
    """
    
    API_BASE = "https://trading-api.kalshi.com/v1"
    
    # Market categories
    CATEGORIES = {
        "sports": "Sports",
        "politics": "Politics",
        "economics": "Economics",
        "crypto": "Crypto",
        "weather": "Weather",
        "culture": "Culture",
        "science": "Science",
    }
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            source_name="kalshi",
            base_url=self.API_BASE
        )
        self.api_key = api_key or os.getenv("KALSHI_API_KEY")
        if self.api_key:
            self.session.headers["Authorization"] = f"Bearer {self.api_key}"
    
    def fetch_markets(
        self,
        category: Optional[str] = None,
        status: str = "open",
        limit: int = 100,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch markets from Kalshi.
        
        Args:
            category: Market category
            status: Market status
            limit: Maximum number of results
            
        Returns:
            List of Kalshi markets
        """
        if not self.api_key:
            logger.error("Cannot fetch Kalshi markets: No API key configured")
            return []
        
        url = f"{self.API_BASE}/markets"
        
        params = {"limit": limit}
        if status == "open":
            params["status"] = "active"
        elif status == "closed":
            params["status"] = "closed"
        
        if category:
            params["category"] = self.CATEGORIES.get(category.lower(), category)
        
        try:
            logger.info(f"Fetching markets from Kalshi (category={category})")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            markets = data.get("markets", [])
            
            logger.info(f"Fetched {len(markets)} markets from Kalshi")
            
            # Add source metadata
            for market in markets:
                market["_source"] = self.source_name
                market["_fetched_at"] = datetime.utcnow().isoformat()
            
            return markets
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch markets from Kalshi: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Kalshi markets: {e}")
            return []


class MockPredictionMarketClient(PredictionMarketClient):
    """
    Mock prediction market client that generates realistic fake data.
    
    Useful for testing and development without API access.
    """
    
    # Sample market templates by category
    MARKET_TEMPLATES = {
        "sports": [
            "Will the {team} win the {championship} in {year}?",
            "Will {player} score over {points} points in the next game?",
            "Will {team} make the playoffs in {year}?",
            "Will the total score of {team1} vs {team2} be over {total}?",
        ],
        "politics": [
            "Will {candidate} win the {election} in {year}?",
            "Will the {party} control the {chamber} after {year} elections?",
            "Will {bill} pass by {date}?",
            "Will {leader} still be in office by {date}?",
        ],
        "crypto": [
            "Will Bitcoin be above ${price} on {date}?",
            "Will Ethereum reach ${price} by {date}?",
            "Will {coin} be in the top 10 by market cap on {date}?",
        ],
        "entertainment": [
            "Will {movie} gross over ${amount} million opening weekend?",
            "Will {show} win Best Drama at the Emmys {year}?",
        ],
    }
    
    SPORTS_TEAMS = ["Lakers", "Warriors", "Chiefs", "49ers", "Yankees", "Red Sox"]
    PLAYERS = ["LeBron James", "Steph Curry", "Patrick Mahomes", "Aaron Judge"]
    CANDIDATES = ["Trump", "Biden", "Harris", "DeSantis"]
    PARTIES = ["Democratic", "Republican"]
    COINS = ["Bitcoin", "Ethereum", "Solana", "Cardano"]
    
    def __init__(self, source_name: str = "mock_prediction_market"):
        super().__init__(source_name)
        self._random = random.Random()
    
    def _generate_market_id(self, category: str, index: int) -> str:
        """Generate a consistent market ID."""
        return f"pm_{category}_{index}_{datetime.now().strftime('%Y%m%d')}"
    
    def _generate_price(self, trend: Optional[str] = None) -> float:
        """Generate a realistic prediction market price (0-1)."""
        if trend == "likely_yes":
            return round(self._random.uniform(0.6, 0.95), 4)
        elif trend == "likely_no":
            return round(self._random.uniform(0.05, 0.4), 4)
        else:
            return round(self._random.uniform(0.1, 0.9), 4)
    
    def _generate_liquidity(self) -> float:
        """Generate realistic liquidity amount."""
        return round(self._random.uniform(1000, 500000), 2)
    
    def _create_market(
        self,
        category: str,
        index: int,
        resolution_time: datetime
    ) -> Dict[str, Any]:
        """Create a single mock market."""
        templates = self.MARKET_TEMPLATES.get(category, self.MARKET_TEMPLATES["sports"])
        template = self._random.choice(templates)
        
        # Fill in template variables
        year = datetime.now().year
        title = template.format(
            team=self._random.choice(self.SPORTS_TEAMS),
            team1=self._random.choice(self.SPORTS_TEAMS),
            team2=self._random.choice(self.SPORTS_TEAMS),
            player=self._random.choice(self.PLAYERS),
            candidate=self._random.choice(self.CANDIDATES),
            party=self._random.choice(self.PARTIES),
            coin=self._random.choice(self.COINS),
            championship=f"{year} Championship",
            election=f"{year} Election",
            chamber=self._random.choice(["House", "Senate"]),
            year=year,
            date=(datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
            points=self._random.randint(20, 40),
            total=self._random.randint(200, 250),
            price=self._random.randint(20000, 100000),
            amount=self._random.randint(50, 200),
            bill="Infrastructure Bill",
            leader="President",
            movie="Blockbuster Movie",
            show="Popular Show",
        )
        
        yes_price = self._generate_price()
        no_price = round(1 - yes_price, 4)
        
        market_id = self._generate_market_id(category, index)
        
        return {
            "id": market_id,
            "market_id": market_id,
            "title": title,
            "description": f"This market resolves to YES if {title.split('Will ')[-1] if 'Will ' in title else title}",
            "category": category,
            "status": "open",
            "resolution_time": resolution_time.isoformat(),
            "outcomes": [
                {
                    "name": "YES",
                    "probability": yes_price,
                    "price": yes_price,
                },
                {
                    "name": "NO",
                    "probability": no_price,
                    "price": no_price,
                },
            ],
            "liquidity": self._generate_liquidity(),
            "volume": self._random.uniform(10000, 1000000),
            "volume_24h": self._random.uniform(1000, 100000),
            "traders": self._random.randint(50, 5000),
            "spread": round(abs(yes_price - no_price), 4),
            "url": f"https://polymarket.com/market/{market_id}",
            "created_at": (datetime.now() - timedelta(days=self._random.randint(1, 30))).isoformat(),
            "_source": self.source_name,
            "_fetched_at": datetime.utcnow().isoformat(),
        }
    
    def fetch_markets(
        self,
        category: Optional[str] = "sports",
        status: str = "open",
        num_markets: int = 10,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generate mock prediction market data.
        
        Args:
            category: Market category
            status: Market status
            num_markets: Number of markets to generate
            
        Returns:
            List of mock market data
        """
        category = category or "sports"
        markets = []
        
        base_resolution = datetime.now() + timedelta(days=7)
        
        for i in range(num_markets):
            resolution_time = base_resolution + timedelta(days=i)
            market = self._create_market(category, i, resolution_time)
            markets.append(market)
        
        logger.info(f"Generated {len(markets)} mock prediction markets for {category}")
        return markets
    
    def fetch_events(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Generate mock events (groups of related markets).
        
        Returns:
            List of mock events
        """
        events = []
        categories = ["sports", "politics", "crypto"]
        
        for i, category in enumerate(categories):
            events.append({
                "id": f"event_{category}_{i}",
                "title": f"{category.title()} Event {i+1}",
                "category": category,
                "markets": self.fetch_markets(category=category, num_markets=3),
                "_source": self.source_name,
                "_fetched_at": datetime.utcnow().isoformat(),
            })
        
        return events


def create_prediction_market_client(
    client_type: str = "mock",
    api_key: Optional[str] = None,
    **kwargs
) -> PredictionMarketClient:
    """
    Factory function to create the appropriate prediction market client.
    
    Args:
        client_type: 'polymarket', 'kalshi', 'mock', or custom class path
        api_key: API key for the chosen client
        **kwargs: Additional client-specific arguments
        
    Returns:
        Configured PredictionMarketClient instance
    """
    client_type = client_type.lower()
    
    if client_type == "polymarket":
        return PolymarketClient()
    elif client_type == "kalshi":
        return KalshiClient(api_key=api_key or os.getenv("KALSHI_API_KEY"))
    elif client_type == "mock":
        return MockPredictionMarketClient(**kwargs)
    else:
        raise ValueError(f"Unknown prediction market client type: {client_type}")
