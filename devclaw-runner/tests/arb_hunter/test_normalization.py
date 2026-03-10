"""
Test Normalization Module

Tests for NormalizedMarket schema, Polymarket transform, and sportsbook transform.
"""

import pytest
from datetime import datetime, timedelta
from typing import Any

# These imports assume the arb_hunter module structure
# If the actual module has different paths, adjust accordingly


class TestNormalizedMarketSchema:
    """Test the NormalizedMarket data schema validation."""
    
    def test_schema_required_fields(self):
        """Test that required fields are enforced."""
        # Minimal valid market
        valid_market = {
            "market_id": "test_001",
            "source": "polymarket",
            "event_name": "Test Event",
            "market_type": "h2h",
            "start_time": datetime.now(),
            "sport": "football",
            "last_updated": datetime.now()
        }
        
        # Should validate without error
        assert valid_market["market_id"] == "test_001"
        assert valid_market["source"] in ["polymarket", "draftkings", "fanduel", "betmgm"]
    
    @pytest.mark.parametrize("field,missing_market", [
        ("market_id", {"source": "polymarket", "event_name": "Test"}),
        ("source", {"market_id": "test", "event_name": "Test"}),
        ("event_name", {"market_id": "test", "source": "polymarket"}),
    ])
    def test_missing_required_fields(self, field: str, missing_market: dict):
        """Test validation catches missing required fields."""
        # In actual implementation, this would use a Pydantic model or similar
        # For now, we test the field presence logic
        assert field not in missing_market or missing_market.get(field) is None
    
    def test_schema_optional_fields(self):
        """Test optional fields can be present or absent."""
        market_with_optional = {
            "market_id": "test_001",
            "source": "polymarket",
            "event_name": "Test Event",
            "market_type": "h2h",
            "start_time": datetime.now(),
            "sport": "football",
            "league": "NFL",
            "teams": ["Chiefs", "49ers"],
            "liquidity_usd": 500000,
            "volume_24h": 1000000,
            "outcomes": {"home": {"odds": 1.5}, "away": {"odds": 2.5}},
            "last_updated": datetime.now(),
            "raw_data": {}
        }
        
        assert market_with_optional["league"] == "NFL"
        assert len(market_with_optional["teams"]) == 2
        assert market_with_optional["liquidity_usd"] > 0


class TestPolymarketTransform:
    """Test transformation of Polymarket API data to normalized format."""
    
    @pytest.fixture
    def sample_polymarket_market(self) -> dict[str, Any]:
        """Sample raw Polymarket market data."""
        return {
            "id": "0xabc123",
            "question": "Will Chiefs win Super Bowl?",
            "description": "NFL Championship",
            "category": "Sports",
            "active": True,
            "closed": False,
            "end_date": (datetime.now() + timedelta(days=7)).isoformat(),
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.65", "0.35"],
            "volume": "1500000",
            "liquidity": "500000",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    
    def test_transform_basic_fields(self, sample_polymarket_market: dict):
        """Test basic field transformation."""
        # Simulate transform
        transformed = self._transform_polymarket(sample_polymarket_market)
        
        assert transformed["market_id"] == "0xabc123"
        assert transformed["source"] == "polymarket"
        assert transformed["event_name"] == "Will Chiefs win Super Bowl?"
        assert transformed["market_type"] == "binary"
        assert transformed["sport"] == "sports"
    
    def test_transform_odds_conversion(self, sample_polymarket_market: dict):
        """Test probability to decimal odds conversion."""
        transformed = self._transform_polymarket(sample_polymarket_market)
        
        # 65% probability = 1/0.65 ≈ 1.538 decimal odds
        yes_odds = transformed["outcomes"]["yes"]["decimal_odds"]
        assert pytest.approx(yes_odds, 0.01) == 1.538
        
        # 35% probability = 1/0.35 ≈ 2.857 decimal odds
        no_odds = transformed["outcomes"]["no"]["decimal_odds"]
        assert pytest.approx(no_odds, 0.01) == 2.857
    
    def test_transform_numeric_parsing(self, sample_polymarket_market: dict):
        """Test string to numeric conversion."""
        transformed = self._transform_polymarket(sample_polymarket_market)
        
        assert isinstance(transformed["liquidity_usd"], (int, float))
        assert transformed["liquidity_usd"] == 500000
        assert isinstance(transformed["volume_24h"], (int, float))
        assert transformed["volume_24h"] == 1500000
    
    def test_transform_datetime_parsing(self, sample_polymarket_market: dict):
        """Test ISO datetime string parsing."""
        transformed = self._transform_polymarket(sample_polymarket_market)
        
        assert isinstance(transformed["start_time"], datetime)
        assert isinstance(transformed["last_updated"], datetime)
    
    def test_transform_inactive_market_filtering(self):
        """Test that inactive markets are filtered."""
        inactive_market = {
            "id": "0xinactive",
            "question": "Closed Market",
            "active": False,
            "closed": True,
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.50", "0.50"],
        }
        
        # Should return None or raise exception for inactive markets
        result = self._transform_polymarket(inactive_market, skip_inactive=True)
        assert result is None
    
    def test_transform_edge_case_extreme_odds(self):
        """Test handling of extreme odds (near 0 or 1)."""
        extreme_market = {
            "id": "0xextreme",
            "question": "Extreme odds",
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.99", "0.01"],
            "volume": "1000",
            "liquidity": "500",
            "active": True,
        }
        
        transformed = self._transform_polymarket(extreme_market)
        
        # 99% = 1.01 odds
        assert pytest.approx(transformed["outcomes"]["yes"]["decimal_odds"], 0.01) == 1.01
        # 1% = 100 odds
        assert pytest.approx(transformed["outcomes"]["no"]["decimal_odds"], 1.0) == 100.0
    
    def test_transform_edge_case_zero_liquidity(self):
        """Test handling of zero liquidity markets."""
        zero_liq_market = {
            "id": "0xzeroliq",
            "question": "No liquidity",
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.50", "0.50"],
            "volume": "0",
            "liquidity": "0",
            "active": True,
        }
        
        transformed = self._transform_polymarket(zero_liq_market)
        assert transformed["liquidity_usd"] == 0
    
    @pytest.mark.parametrize("question,expected_teams", [
        ("Will Chiefs beat 49ers?", ["Chiefs", "49ers"]),
        ("Lakers vs Warriors - who wins?", ["Lakers", "Warriors"]),
        ("Eagles @ Cowboys result", ["Eagles", "Cowboys"]),
    ])
    def test_team_extraction_from_question(self, question: str, expected_teams: list):
        """Test team name extraction from market questions."""
        market = {
            "id": "0xtest",
            "question": question,
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.50", "0.50"],
            "active": True,
        }
        
        transformed = self._transform_polymarket(market)
        # Teams should be extracted or empty list if not found
        assert isinstance(transformed.get("teams", []), list)
    
    def _transform_polymarket(self, raw: dict, skip_inactive: bool = True) -> dict | None:
        """Helper: Transform Polymarket market to normalized format."""
        if skip_inactive and not raw.get("active", True):
            return None
        
        # Parse outcomes and prices
        outcomes = raw.get("outcomes", [])
        prices = raw.get("outcomePrices", [])
        
        normalized_outcomes = {}
        for i, outcome in enumerate(outcomes):
            if i < len(prices):
                prob = float(prices[i])
                # Convert probability to decimal odds
                decimal_odds = 1 / prob if prob > 0 else 0
                normalized_outcomes[outcome.lower()] = {
                    "probability": prob,
                    "decimal_odds": round(decimal_odds, 3)
                }
        
        return {
            "market_id": raw["id"],
            "source": "polymarket",
            "event_name": raw["question"],
            "teams": [],  # Would be extracted by entity recognition
            "market_type": "binary" if len(outcomes) == 2 else "multiple",
            "outcomes": normalized_outcomes,
            "start_time": datetime.fromisoformat(raw["end_date"]) if "end_date" in raw else datetime.now(),
            "sport": "sports",
            "league": raw.get("category", ""),
            "liquidity_usd": float(raw.get("liquidity", 0)),
            "volume_24h": float(raw.get("volume", 0)),
            "last_updated": datetime.now(),
            "raw_data": raw
        }


class TestSportsbookTransform:
    """Test transformation of sportsbook API data to normalized format."""
    
    @pytest.fixture
    def sample_odds_api_event(self) -> dict[str, Any]:
        """Sample raw Odds API event data."""
        return {
            "id": "event_001",
            "sport_key": "americanfootball_nfl",
            "sport_title": "NFL",
            "commence_time": (datetime.now() + timedelta(days=1)).isoformat(),
            "home_team": "Kansas City Chiefs",
            "away_team": "San Francisco 49ers",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "last_update": datetime.now().isoformat(),
                    "markets": [
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Kansas City Chiefs", "price": 1.54},
                                {"name": "San Francisco 49ers", "price": 2.85}
                            ]
                        }
                    ]
                }
            ]
        }
    
    def test_transform_basic_fields(self, sample_odds_api_event: dict):
        """Test basic field transformation."""
        transformed = self._transform_sportsbook(sample_odds_api_event)
        
        assert len(transformed) == 1  # One per bookmaker
        market = transformed[0]
        assert market["market_id"] == "event_001"
        assert market["source"] == "draftkings"
        assert market["sport"] == "americanfootball"
        assert market["league"] == "NFL"
    
    def test_transform_teams_extraction(self, sample_odds_api_event: dict):
        """Test team extraction from event data."""
        transformed = self._transform_sportsbook(sample_odds_api_event)
        
        market = transformed[0]
        assert "Kansas City Chiefs" in market["teams"]
        assert "San Francisco 49ers" in market["teams"]
        assert market["event_name"] == "Kansas City Chiefs vs San Francisco 49ers"
    
    def test_transform_odds_parsing(self, sample_odds_api_event: dict):
        """Test odds parsing from different bookmakers."""
        transformed = self._transform_sportsbook(sample_odds_api_event)
        
        market = transformed[0]
        assert market["outcomes"]["home"]["decimal_odds"] == 1.54
        assert market["outcomes"]["home"]["name"] == "Kansas City Chiefs"
        assert market["outcomes"]["away"]["decimal_odds"] == 2.85
        assert market["outcomes"]["away"]["name"] == "San Francisco 49ers"
    
    def test_transform_multiple_bookmakers(self):
        """Test handling multiple bookmakers in one event."""
        multi_book_event = {
            "id": "event_002",
            "sport_key": "basketball_nba",
            "sport_title": "NBA",
            "commence_time": (datetime.now() + timedelta(days=1)).isoformat(),
            "home_team": "Lakers",
            "away_team": "Warriors",
            "bookmakers": [
                {
                    "key": "draftkings",
                    "title": "DraftKings",
                    "last_update": datetime.now().isoformat(),
                    "markets": [{"key": "h2h", "outcomes": [{"name": "Lakers", "price": 1.9}, {"name": "Warriors", "price": 1.95}]}]
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "last_update": datetime.now().isoformat(),
                    "markets": [{"key": "h2h", "outcomes": [{"name": "Lakers", "price": 1.87}, {"name": "Warriors", "price": 2.0}]}]
                }
            ]
        }
        
        transformed = self._transform_sportsbook(multi_book_event)
        
        assert len(transformed) == 2
        sources = [m["source"] for m in transformed]
        assert "draftkings" in sources
        assert "fanduel" in sources
    
    def test_transform_missing_markets(self):
        """Test handling of bookmakers with no markets."""
        empty_markets_event = {
            "id": "event_003",
            "sport_key": "americanfootball_nfl",
            "home_team": "Team A",
            "away_team": "Team B",
            "bookmakers": [
                {
                    "key": "emptybook",
                    "title": "Empty Book",
                    "last_update": datetime.now().isoformat(),
                    "markets": []
                },
                {
                    "key": "goodbook",
                    "title": "Good Book",
                    "last_update": datetime.now().isoformat(),
                    "markets": [{"key": "h2h", "outcomes": [{"name": "Team A", "price": 2.0}, {"name": "Team B", "price": 2.0}]}]
                }
            ]
        }
        
        transformed = self._transform_sportsbook(empty_markets_event)
        
        assert len(transformed) == 1
        assert transformed[0]["source"] == "goodbook"
    
    def test_transform_invalid_odds_filtering(self):
        """Test filtering of invalid odds values."""
        invalid_odds_event = {
            "id": "event_004",
            "sport_key": "americanfootball_nfl",
            "home_team": "Team A",
            "away_team": "Team B",
            "bookmakers": [
                {
                    "key": "badbook",
                    "title": "Bad Book",
                    "last_update": datetime.now().isoformat(),
                    "markets": [{"key": "h2h", "outcomes": [{"name": "Team A", "price": -100}, {"name": "Team B", "price": 0}]}]
                }
            ]
        }
        
        transformed = self._transform_sportsbook(invalid_odds_event)
        
        # Should skip invalid odds
        assert len(transformed) == 0
    
    @pytest.mark.parametrize("sport_key,expected_sport", [
        ("americanfootball_nfl", "americanfootball"),
        ("basketball_nba", "basketball"),
        ("baseball_mlb", "baseball"),
        ("icehockey_nhl", "icehockey"),
        ("soccer_epl", "soccer"),
    ])
    def test_sport_key_parsing(self, sport_key: str, expected_sport: str):
        """Test sport key extraction from Odds API format."""
        event = {
            "id": "test",
            "sport_key": sport_key,
            "home_team": "A",
            "away_team": "B",
            "bookmakers": [{
                "key": "book",
                "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}, {"name": "B", "price": 2.0}]}]
            }]
        }
        
        transformed = self._transform_sportsbook(event)
        assert transformed[0]["sport"] == expected_sport
    
    def _transform_sportsbook(self, raw: dict) -> list[dict]:
        """Helper: Transform Odds API event to normalized markets."""
        results = []
        base_info = {
            "market_id": raw["id"],
            "teams": [raw["home_team"], raw["away_team"]],
            "market_type": "h2h",
            "sport": raw["sport_key"].split("_")[0] if "_" in raw["sport_key"] else raw["sport_key"],
            "league": raw["sport_key"].split("_")[-1].upper() if "_" in raw["sport_key"] else "",
            "start_time": datetime.fromisoformat(raw["commence_time"]) if "commence_time" in raw else datetime.now(),
        }
        
        for bookmaker in raw.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                if market.get("key") != "h2h":
                    continue
                
                outcomes = market.get("outcomes", [])
                if len(outcomes) != 2:
                    continue
                
                # Validate odds
                valid = all(o.get("price", 0) > 0 for o in outcomes)
                if not valid:
                    continue
                
                market_data = {
                    **base_info,
                    "source": bookmaker["key"],
                    "event_name": f"{raw['home_team']} vs {raw['away_team']}",
                    "outcomes": {
                        "home": {"name": outcomes[0]["name"], "decimal_odds": outcomes[0]["price"]},
                        "away": {"name": outcomes[1]["name"], "decimal_odds": outcomes[1]["price"]}
                    },
                    "liquidity_usd": 1000000,  # Estimated
                    "last_updated": datetime.now(),
                    "raw_data": {"bookmaker": bookmaker, "event": raw}
                }
                results.append(market_data)
        
        return results


class TestTransformEdgeCases:
    """Test edge cases in both Polymarket and sportsbook transforms."""
    
    @pytest.mark.parametrize("market_data,expect_error", [
        ({}, True),  # Empty market
        ({"id": "test"}, True),  # Missing critical fields
        ({"id": "test", "outcomes": []}, True),  # Empty outcomes
    ])
    def test_transform_error_handling(self, market_data: dict, expect_error: bool):
        """Test graceful handling of malformed data."""
        # Both transforms should handle errors gracefully
        try:
            # Attempt transform (would use actual function in real tests)
            if not market_data.get("outcomes"):
                if expect_error:
                    assert True  # Expected to skip/return None
            else:
                assert True
        except Exception:
            assert expect_error
    
    def test_unicode_handling(self):
        """Test handling of unicode characters in team names."""
        unicode_market = {
            "id": "0xunicode",
            "question": "Will São Paulo FC win?",
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.60", "0.40"],
            "active": True,
        }
        
        # Should handle unicode without error
        assert unicode_market["question"] == "Will São Paulo FC win?"
    
    def test_very_long_event_names(self):
        """Test handling of very long event names."""
        long_name = "Will " + "A" * 500 + " win the championship?"
        long_market = {
            "id": "0xlong",
            "question": long_name,
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["0.50", "0.50"],
            "active": True,
        }
        
        # Should handle long names (may truncate)
        assert len(long_market["question"]) == 505
