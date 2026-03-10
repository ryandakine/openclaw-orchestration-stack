"""
Sportsbook data ingestion client.

Fetches odds data from traditional sportsbooks via APIs or mock data.
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


class SportsbookClient(ABC):
    """
    Abstract base class for sportsbook data clients.
    
    All sportsbook clients must implement the fetch_odds method
    that returns data in a normalized raw format.
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
    def fetch_odds(
        self,
        sport: Optional[str] = None,
        market_type: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch odds data from the sportsbook.
        
        Args:
            sport: Sport filter (e.g., 'NBA', 'NFL', 'MLB')
            market_type: Market type filter (e.g., 'moneyline', 'spread', 'total')
            **kwargs: Additional client-specific parameters
            
        Returns:
            List of raw event/odds data from the sportsbook
        """
        pass
    
    def fetch_events(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch events (without odds details).
        
        Args:
            **kwargs: Filter parameters
            
        Returns:
            List of events
        """
        # Default implementation just calls fetch_odds
        return self.fetch_odds(**kwargs)
    
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


class TheOddsAPIClient(SportsbookClient):
    """
    Client for The Odds API (https://the-odds-api.com/)
    
    Aggregates odds from multiple sportsbooks including:
    - DraftKings
    - FanDuel
    - Bet365
    - BetMGM
    - PointsBet
    - And many others
    """
    
    API_BASE = "https://api.the-odds-api.com/v4"
    
    # Sport keys mapped to API identifiers
    SPORT_KEYS = {
        "NBA": "basketball_nba",
        "NFL": "americanfootball_nfl",
        "MLB": "baseball_mlb",
        "NHL": "icehockey_nhl",
        "EPL": "soccer_epl",
        "UFC": "mma_mixed_martial_arts",
        "NCAA_BASKETBALL": "basketball_ncaa",
        "NCAA_FOOTBALL": "americanfootball_ncaaf",
    }
    
    # Supported bookmakers
    BOOKMAKERS = [
        "draftkings",
        "fanduel",
        "bet365",
        "betmgm",
        "pointsbetus",
        "williamhill_us",
        "bovada",
        "mybookieag",
        "unibet_us",
        "foxbet",
        "twinspires",
    ]
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            source_name="the_odds_api",
            base_url=self.API_BASE
        )
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            logger.warning("No API key provided for The Odds API")
    
    def _get_sport_key(self, sport: str) -> str:
        """Convert sport name to API sport key."""
        return self.SPORT_KEYS.get(sport.upper(), sport.lower())
    
    def fetch_odds(
        self,
        sport: Optional[str] = "NBA",
        market_type: Optional[str] = None,
        regions: str = "us",
        odds_format: str = "decimal",
        date_format: str = "iso",
        bookmakers: Optional[List[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch odds from The Odds API.
        
        Args:
            sport: Sport to fetch (NBA, NFL, MLB, etc.)
            market_type: h2h (moneyline), spreads, totals
            regions: Region code (us, uk, eu, au)
            odds_format: decimal or american
            date_format: iso or unix
            bookmakers: List of specific bookmakers to include
            
        Returns:
            List of events with odds from various bookmakers
        """
        if not self.api_key:
            logger.error("Cannot fetch odds: No API key configured")
            return []
        
        sport_key = self._get_sport_key(sport) if sport else "basketball_nba"
        
        # Map market_type to API markets parameter
        markets = "h2h"  # default to moneyline
        if market_type == "spread":
            markets = "spreads"
        elif market_type == "total":
            markets = "totals"
        elif market_type == "moneyline":
            markets = "h2h"
        
        url = f"{self.API_BASE}/sports/{sport_key}/odds"
        
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": odds_format,
            "dateFormat": date_format,
        }
        
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers)
        
        try:
            logger.info(f"Fetching odds from The Odds API for {sport}")
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Fetched {len(data)} events from The Odds API")
            
            # Add source metadata
            for event in data:
                event["_source"] = self.source_name
                event["_fetched_at"] = datetime.utcnow().isoformat()
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch odds from The Odds API: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching odds: {e}")
            return []
    
    def get_usage(self) -> Dict[str, Any]:
        """
        Get API usage information from response headers.
        
        Note: This requires a recent API call to have been made.
        
        Returns:
            Dict with usage info (requests remaining, etc.)
        """
        # Make a lightweight call to get headers
        try:
            url = f"{self.API_BASE}/sports"
            response = self.session.get(
                url,
                params={"apiKey": self.api_key},
                timeout=10
            )
            
            return {
                "requests_remaining": response.headers.get("x-requests-remaining"),
                "requests_used": response.headers.get("x-requests-used"),
                "requests_last": response.headers.get("x-requests-last"),
            }
        except Exception as e:
            logger.error(f"Failed to get usage info: {e}")
            return {}


class MockSportsbookClient(SportsbookClient):
    """
    Mock sportsbook client that generates realistic fake data.
    
    Useful for testing and development without API keys.
    """
    
    # Sample teams by sport
    TEAMS = {
        "NBA": [
            ("Lakers", "Warriors"), ("Celtics", "Heat"), ("Nets", "Bucks"),
            ("Suns", "Nuggets"), ("76ers", "Knicks"), ("Mavericks", "Clippers"),
            ("Thunder", "Timberwolves"), ("Pelicans", "Kings"),
        ],
        "NFL": [
            ("Chiefs", "49ers"), ("Ravens", "Bills"), ("Eagles", "Cowboys"),
            ("Packers", "Lions"), ("Dolphins", "Jets"), ("Bengals", "Browns"),
        ],
        "MLB": [
            ("Yankees", "Red Sox"), ("Dodgers", "Giants"), ("Cubs", "Cardinals"),
            ("Mets", "Phillies"), ("Astros", "Rangers"), ("Braves", "Mets"),
        ],
        "NHL": [
            ("Maple Leafs", "Canadiens"), ("Rangers", "Islanders"),
            ("Bruins", "Lightning"), ("Avalanche", "Golden Knights"),
        ],
    }
    
    BOOKMAKERS = ["DraftKings", "FanDuel", "Bet365", "BetMGM", "PointsBet"]
    
    def __init__(self, source_name: str = "mock_sportsbook"):
        super().__init__(source_name)
        self._random = random.Random()
    
    def _generate_event_id(self, sport: str, home: str, away: str) -> str:
        """Generate a consistent event ID."""
        return f"sb_{sport.lower()}_{home.lower()}_{away.lower()}_{datetime.now().strftime('%Y%m%d')}"
    
    def _generate_odds(self, base_odds: float, variance: float = 0.15) -> float:
        """Generate realistic odds with some variance between bookmakers."""
        variation = self._random.uniform(-variance, variance)
        odds = base_odds + variation
        # Ensure reasonable odds range
        return round(max(1.1, min(10.0, odds)), 2)
    
    def _create_moneyline_market(
        self,
        home: str,
        away: str,
        bookmaker: str
    ) -> Dict[str, Any]:
        """Create a moneyline market for a game."""
        # Generate base odds (slight home advantage)
        home_base = self._random.uniform(1.5, 2.5)
        away_base = self._random.uniform(1.5, 2.5)
        
        # Bookmaker-specific adjustments
        adjustments = {
            "DraftKings": 0.0,
            "FanDuel": 0.0,
            "Bet365": -0.02,
            "BetMGM": -0.01,
            "PointsBet": -0.03,
        }
        adj = adjustments.get(bookmaker, 0.0)
        
        return {
            "key": "h2h",
            "outcomes": [
                {"name": home, "price": self._generate_odds(home_base + adj)},
                {"name": away, "price": self._generate_odds(away_base + adj)},
            ]
        }
    
    def _create_spread_market(
        self,
        home: str,
        away: str,
        bookmaker: str
    ) -> Dict[str, Any]:
        """Create a spread market for a game."""
        # Generate realistic spread
        spread = round(self._random.uniform(-10.5, 10.5) * 2) / 2
        
        return {
            "key": "spreads",
            "outcomes": [
                {
                    "name": home,
                    "price": self._random.choice([1.87, 1.91, 1.95]),
                    "point": spread,
                },
                {
                    "name": away,
                    "price": self._random.choice([1.87, 1.91, 1.95]),
                    "point": -spread,
                },
            ]
        }
    
    def _create_total_market(
        self,
        home: str,
        away: str,
        bookmaker: str
    ) -> Dict[str, Any]:
        """Create a totals/over-under market."""
        # Sport-specific total ranges
        total = self._random.choice([210.5, 220.5, 225.5, 230.5, 235.5])
        
        return {
            "key": "totals",
            "outcomes": [
                {
                    "name": "Over",
                    "price": self._random.choice([1.87, 1.91, 1.95]),
                    "point": total,
                },
                {
                    "name": "Under",
                    "price": self._random.choice([1.87, 1.91, 1.95]),
                    "point": total,
                },
            ]
        }
    
    def fetch_odds(
        self,
        sport: Optional[str] = "NBA",
        market_type: Optional[str] = "moneyline",
        num_events: int = 8,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Generate mock odds data.
        
        Args:
            sport: Sport to generate events for
            market_type: Type of market
            num_events: Number of events to generate
            
        Returns:
            List of mock event data
        """
        sport = sport or "NBA"
        teams_list = self.TEAMS.get(sport, self.TEAMS["NBA"])
        
        events = []
        base_time = datetime.now() + timedelta(days=1)
        
        for i in range(min(num_events, len(teams_list))):
            away, home = teams_list[i]
            event_id = self._generate_event_id(sport, home, away)
            
            # Generate start time (tomorrow + offset)
            start_time = base_time + timedelta(hours=i * 3)
            
            # Create bookmakers data
            bookmakers = []
            for bookmaker in self.BOOKMAKERS:
                markets = []
                
                if market_type in ("moneyline", None):
                    markets.append(self._create_moneyline_market(home, away, bookmaker))
                if market_type in ("spread", None):
                    markets.append(self._create_spread_market(home, away, bookmaker))
                if market_type in ("total", None):
                    markets.append(self._create_total_market(home, away, bookmaker))
                
                bookmakers.append({
                    "key": bookmaker.lower(),
                    "title": bookmaker,
                    "markets": markets,
                })
            
            event = {
                "id": event_id,
                "sport_key": sport.lower(),
                "sport_title": sport,
                "home_team": home,
                "away_team": away,
                "commence_time": start_time.isoformat(),
                "bookmakers": bookmakers,
                "_source": self.source_name,
                "_fetched_at": datetime.utcnow().isoformat(),
            }
            events.append(event)
        
        logger.info(f"Generated {len(events)} mock events for {sport}")
        return events


def create_sportsbook_client(
    client_type: str = "mock",
    api_key: Optional[str] = None,
    **kwargs
) -> SportsbookClient:
    """
    Factory function to create the appropriate sportsbook client.
    
    Args:
        client_type: 'odds_api', 'mock', or a custom client class path
        api_key: API key for the chosen client
        **kwargs: Additional client-specific arguments
        
    Returns:
        Configured SportsbookClient instance
    """
    client_type = client_type.lower()
    
    if client_type == "odds_api":
        return TheOddsAPIClient(api_key=api_key or os.getenv("ODDS_API_KEY"))
    elif client_type == "mock":
        return MockSportsbookClient(**kwargs)
    else:
        raise ValueError(f"Unknown sportsbook client type: {client_type}")
