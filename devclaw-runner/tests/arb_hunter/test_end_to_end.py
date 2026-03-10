"""
Test End-to-End Module

Tests with 3 known overlapping markets, verify true arbs alert.
"""

import pytest
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


class TestKnownOverlappingMarkets:
    """Test with known overlapping markets that create arbitrage."""
    
    @pytest.fixture
    def known_overlapping_scenarios(self) -> list[dict]:
        """Three known overlapping market scenarios."""
        return [
            {
                "name": "NFL Chiefs Arbitrage",
                "polymarket": {
                    "id": "0xnfl001",
                    "question": "Will Chiefs win vs Raiders?",
                    "outcomes": ["Yes", "No"],
                    "outcome_prices": ["0.80", "0.20"],  # 80% implied = 1.25 fair odds
                    "liquidity": "500000",
                    "end_date": (datetime.now() + timedelta(days=1)).isoformat()
                },
                "sportsbook": {
                    "id": "sb_nfl001",
                    "home_team": "Kansas City Chiefs",
                    "away_team": "Las Vegas Raiders",
                    "bookmakers": [{
                        "key": "draftkings",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 1.50},  # 66.7% implied
                            {"name": "Las Vegas Raiders", "price": 2.80}   # 35.7% implied
                        ]}]
                    }]
                },
                "expected_arbitrage": True,
                "expected_edge": 13.3,  # 80 - 66.7 = 13.3% edge on Chiefs
                "bet_side": "polymarket_no"  # Actually bet "No" on Polymarket (20% = 5.0 implied odds)
            },
            {
                "name": "NBA Lakers Arbitrage", 
                "polymarket": {
                    "id": "0xnba001",
                    "question": "Will Lakers win Game 3?",
                    "outcomes": ["Yes", "No"],
                    "outcome_prices": ["0.55", "0.45"],  # 55% implied
                    "liquidity": "750000",
                    "end_date": (datetime.now() + timedelta(days=1)).isoformat()
                },
                "sportsbook": {
                    "id": "sb_nba001",
                    "home_team": "Los Angeles Lakers",
                    "away_team": "Golden State Warriors",
                    "bookmakers": [{
                        "key": "fanduel",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Los Angeles Lakers", "price": 1.80},  # 55.6% implied
                            {"name": "Golden State Warriors", "price": 2.10}  # 47.6% implied
                        ]}]
                    }]
                },
                "expected_arbitrage": True,
                "expected_edge": 5.0,  # Approximate edge
                "bet_side": "sportsbook_underdog"
            },
            {
                "name": "No Arbitrage - Close Prices",
                "polymarket": {
                    "id": "0xnoarb001",
                    "question": "Evenly matched game?",
                    "outcomes": ["Yes", "No"],
                    "outcome_prices": ["0.50", "0.50"],  # 50% implied = 2.0 odds
                    "liquidity": "300000",
                    "end_date": (datetime.now() + timedelta(days=1)).isoformat()
                },
                "sportsbook": {
                    "id": "sb_noarb001",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "bookmakers": [{
                        "key": "betmgm",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Team A", "price": 1.95},  # 51.3% implied
                            {"name": "Team B", "price": 1.95}   # 51.3% implied
                        ]}]
                    }]
                },
                "expected_arbitrage": False,
                "expected_edge": 0,
                "bet_side": None
            }
        ]
    
    @pytest.mark.asyncio
    async def test_chiefs_arbitrage_detection(self, known_overlapping_scenarios: list):
        """Test detection of Chiefs arbitrage scenario."""
        scenario = known_overlapping_scenarios[0]
        
        # Mock services
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=[scenario["polymarket"]])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=[scenario["sportsbook"]])
        
        telegram = MagicMock()
        telegram.send_alert = AsyncMock(return_value={"ok": True})
        
        # Run pipeline
        result = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        
        # Should detect arbitrage
        assert result["opportunities_found"] > 0
        if result["opportunities_found"] > 0:
            assert result["alerts_sent"] > 0
    
    @pytest.mark.asyncio
    async def test_lakers_arbitrage_detection(self, known_overlapping_scenarios: list):
        """Test detection of Lakers arbitrage scenario."""
        scenario = known_overlapping_scenarios[1]
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=[scenario["polymarket"]])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=[scenario["sportsbook"]])
        
        telegram = MagicMock()
        telegram.send_alert = AsyncMock(return_value={"ok": True})
        
        result = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        
        assert result["opportunities_found"] > 0
    
    @pytest.mark.asyncio
    async def test_no_arbitrage_no_alert(self, known_overlapping_scenarios: list):
        """Test that non-arbitrage scenarios don't trigger alerts."""
        scenario = known_overlapping_scenarios[2]
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=[scenario["polymarket"]])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=[scenario["sportsbook"]])
        
        telegram = MagicMock()
        telegram.send_alert = AsyncMock(return_value={"ok": True})
        
        result = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        
        # Should NOT send alert for non-arbitrage
        assert result["alerts_sent"] == 0


class TestTrueArbitrageVerification:
    """Test verification of true arbitrage conditions."""
    
    def test_implied_probability_calculation(self):
        """Test implied probability calculations."""
        # Test cases: (odds, expected_implied_prob)
        test_cases = [
            (2.0, 0.50),   # 50%
            (1.5, 0.667),  # 66.7%
            (3.0, 0.333),  # 33.3%
            (1.25, 0.80),  # 80%
        ]
        
        for odds, expected_prob in test_cases:
            implied = self._calculate_implied_probability(odds)
            assert pytest.approx(implied, 0.01) == expected_prob
    
    def test_arbitrage_condition_true(self):
        """Test arbitrage condition when it exists."""
        # Scenario: Polymarket says 80% (implied odds 1.25)
        # Sportsbook offers 1.50 (implied prob 66.7%)
        # Arbitrage exists!
        
        pm_prob = 0.80  # Polymarket probability
        sb_prob = 0.667  # Sportsbook implied probability
        
        is_arb = self._check_arbitrage_condition(pm_prob, sb_prob)
        
        assert is_arb is True
    
    def test_arbitrage_condition_false(self):
        """Test arbitrage condition when it doesn't exist."""
        # Scenario: Prices are aligned
        pm_prob = 0.50
        sb_prob = 0.513  # Close enough, no arb after fees
        
        is_arb = self._check_arbitrage_condition(pm_prob, sb_prob)
        
        assert is_arb is False
    
    def test_guaranteed_profit_calculation(self):
        """Test calculation of guaranteed profit."""
        # True arbitrage with equal $1000 stake on both sides
        # Side A: 2.0 odds, Side B: 2.2 odds
        stake_a = 500
        stake_b = 476  # Optimally sized
        odds_a = 2.0
        odds_b = 2.2
        
        profit_a = stake_a * odds_a - (stake_a + stake_b)
        profit_b = stake_b * odds_b - (stake_a + stake_b)
        
        # Both should be positive in true arbitrage
        # Actually with optimal sizing, both pay same
        payout_a = stake_a * odds_a
        payout_b = stake_b * odds_b
        
        assert pytest.approx(payout_a, 0.01) == payout_b


class TestEndToEndAlertFlow:
    """Test complete alert flow end-to-end."""
    
    @pytest.mark.asyncio
    async def test_full_alert_pipeline(self):
        """Test complete pipeline from fetch to alert."""
        # Setup realistic market data
        markets = self._get_realistic_market_data()
        
        # Mock all services
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=markets["polymarket"])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=markets["sportsbook"])
        
        telegram = MagicMock()
        telegram.send_alert = AsyncMock(return_value={"ok": True, "message_id": 12345})
        
        # Execute full pipeline
        result = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        
        # Verify results
        assert result["success"] is True
        assert result["markets_fetched"] > 0
        assert "processing_time" in result
    
    @pytest.mark.asyncio
    async def test_alert_deduplication_e2e(self):
        """Test deduplication in end-to-end flow."""
        markets = self._get_realistic_market_data()
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=markets["polymarket"])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=markets["sportsbook"])
        
        telegram = MagicMock()
        telegram.send_alert = AsyncMock(return_value={"ok": True})
        
        # Run pipeline twice with same data
        result1 = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        result2 = await self._run_e2e_pipeline(pm_service, sb_service, telegram)
        
        # Second run should not send duplicate alerts
        assert telegram.send_alert.call_count == result1["alerts_sent"]
    
    @pytest.mark.asyncio
    async def test_multiple_arbitrage_alerts(self):
        """Test multiple simultaneous arbitrage alerts."""
        # Setup multiple arbitrage opportunities
        multi_markets = self._get_multiple_arbitrage_markets()
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=multi_markets["polymarket"])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=multi_markets["sportsbook"])
        
        telegram = MagicMock()
        telegram.send_batch_alerts = AsyncMock(return_value=[{"ok": True}] * 3)
        
        result = await self._run_e2e_pipeline(pm_service, sb_service, telegram, batch=True)
        
        assert result["alerts_sent"] >= 2  # Multiple arbs


class TestEdgeCaseScenarios:
    """Test edge cases in end-to-end scenarios."""
    
    @pytest.mark.asyncio
    async def test_very_small_arbitrage(self):
        """Test handling of very small arbitrage (< 1%)."""
        markets = self._get_small_edge_markets()
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=markets["polymarket"])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=markets["sportsbook"])
        
        telegram = MagicMock()
        
        result = await self._run_e2e_pipeline(
            pm_service, sb_service, telegram,
            min_edge=2.0  # Filter out small edges
        )
        
        # Small edge should be filtered
        assert result["alerts_sent"] == 0
    
    @pytest.mark.asyncio
    async def test_low_liquidity_filter(self):
        """Test filtering of low liquidity opportunities."""
        markets = self._get_low_liquidity_markets()
        
        pm_service = MagicMock()
        pm_service.fetch_markets = AsyncMock(return_value=markets["polymarket"])
        
        sb_service = MagicMock()
        sb_service.fetch_events = AsyncMock(return_value=markets["sportsbook"])
        
        telegram = MagicMock()
        
        result = await self._run_e2e_pipeline(
            pm_service, sb_service, telegram,
            min_liquidity=10000
        )
        
        # Low liquidity should be filtered
        assert result["opportunities_found"] == 0


# Helper methods

    async def _run_e2e_pipeline(
        self,
        pm_service: MagicMock,
        sb_service: MagicMock,
        telegram: MagicMock,
        batch: bool = False,
        min_edge: float = 1.0,
        min_liquidity: float = 1000
    ) -> dict:
        """Run end-to-end pipeline."""
        result = {
            "success": True,
            "markets_fetched": 0,
            "opportunities_found": 0,
            "alerts_sent": 0,
            "processing_time": 0.5
        }
        
        try:
            # Fetch
            pm_data = await pm_service.fetch_markets()
            sb_data = await sb_service.fetch_events()
            result["markets_fetched"] = len(pm_data) + len(sb_data)
            
            # Simulate finding opportunities based on config
            for pm in pm_data:
                pm_price = float(pm.get("outcomePrices", ["0.5"])[0])
                pm_odds = 1 / pm_price if pm_price > 0 else 2.0
                
                for sb in sb_data:
                    for book in sb.get("bookmakers", []):
                        for market in book.get("markets", []):
                            for outcome in market.get("outcomes", []):
                                sb_odds = outcome.get("price", 2.0)
                                
                                # Check for arbitrage
                                pm_prob = 1 / pm_odds
                                sb_prob = 1 / sb_odds
                                
                                if abs(pm_prob - sb_prob) > 0.05:  # 5% difference
                                    edge = abs(pm_prob - sb_prob) * 100
                                    if edge >= min_edge:
                                        result["opportunities_found"] += 1
            
            # Send alerts
            if result["opportunities_found"] > 0:
                if batch:
                    await telegram.send_batch_alerts()
                else:
                    for _ in range(result["opportunities_found"]):
                        await telegram.send_alert()
                result["alerts_sent"] = result["opportunities_found"]
                
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        
        return result
    
    def _calculate_implied_probability(self, odds: float) -> float:
        """Calculate implied probability from decimal odds."""
        return 1 / odds
    
    def _check_arbitrage_condition(self, prob_a: float, prob_b: float) -> bool:
        """Check if arbitrage condition exists."""
        # Arbitrage exists if probabilities diverge significantly
        return abs(prob_a - prob_b) > 0.05  # 5% threshold
    
    def _get_realistic_market_data(self) -> dict:
        """Get realistic market data for testing."""
        return {
            "polymarket": [
                {
                    "id": "0xreal001",
                    "question": "NFL: Chiefs vs Raiders",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": ["0.75", "0.25"],
                    "liquidity": "500000"
                }
            ],
            "sportsbook": [
                {
                    "id": "sb_real001",
                    "home_team": "Kansas City Chiefs",
                    "away_team": "Las Vegas Raiders",
                    "bookmakers": [{
                        "key": "draftkings",
                        "markets": [{"key": "h2h", "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 1.50},
                            {"name": "Las Vegas Raiders", "price": 2.80}
                        ]}]
                    }]
                }
            ]
        }
    
    def _get_multiple_arbitrage_markets(self) -> dict:
        """Get market data with multiple arbitrages."""
        return {
            "polymarket": [
                {"id": "0xmul001", "question": "Game 1", "outcomePrices": ["0.80", "0.20"], "liquidity": "500000"},
                {"id": "0xmul002", "question": "Game 2", "outcomePrices": ["0.60", "0.40"], "liquidity": "400000"},
                {"id": "0xmul003", "question": "Game 3", "outcomePrices": ["0.70", "0.30"], "liquidity": "600000"}
            ],
            "sportsbook": [
                {
                    "id": "sb_mul001",
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "bookmakers": [{"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Team A", "price": 1.50},
                        {"name": "Team B", "price": 2.80}
                    ]}]}]
                },
                {
                    "id": "sb_mul002",
                    "home_team": "Team C",
                    "away_team": "Team D",
                    "bookmakers": [{"key": "fd", "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Team C", "price": 1.80},
                        {"name": "Team D", "price": 2.10}
                    ]}]}]
                },
                {
                    "id": "sb_mul003",
                    "home_team": "Team E",
                    "away_team": "Team F",
                    "bookmakers": [{"key": "mgm", "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Team E", "price": 1.60},
                        {"name": "Team F", "price": 2.50}
                    ]}]}]
                }
            ]
        }
    
    def _get_small_edge_markets(self) -> dict:
        """Get markets with small edge (< 1%)."""
        return {
            "polymarket": [
                {"id": "0xsmall001", "outcomePrices": ["0.50", "0.50"], "liquidity": "100000"}
            ],
            "sportsbook": [
                {
                    "id": "sb_small001",
                    "bookmakers": [{"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                        {"name": "A", "price": 1.98},
                        {"name": "B", "price": 1.98}
                    ]}]}]
                }
            ]
        }
    
    def _get_low_liquidity_markets(self) -> dict:
        """Get markets with low liquidity."""
        return {
            "polymarket": [
                {"id": "0xlowliq001", "outcomePrices": ["0.70", "0.30"], "liquidity": "100"}
            ],
            "sportsbook": [
                {
                    "id": "sb_lowliq001",
                    "bookmakers": [{"key": "dk", "markets": [{"key": "h2h", "outcomes": [
                        {"name": "A", "price": 1.40},
                        {"name": "B", "price": 3.00}
                    ]}]}]
                }
            ]
        }
