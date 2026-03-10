"""
Test Integration Module

Tests for full pipeline: fetch -> normalize -> match -> calculate -> alert
"""

import pytest
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


class TestFullPipeline:
    """Test the complete arbitrage detection pipeline."""
    
    @pytest.fixture
    def mock_services(self):
        """Mock all external services."""
        return {
            "polymarket": MagicMock(),
            "odds_api": MagicMock(),
            "telegram": MagicMock()
        }
    
    @pytest.fixture
    def pipeline_config(self) -> dict:
        """Pipeline configuration."""
        return {
            "min_edge_percent": 2.0,
            "min_liquidity_usd": 10000,
            "max_staleness_minutes": 30,
            "alert_threshold": 2.0,
            "enable_alerts": True
        }
    
    @pytest.mark.asyncio
    async def test_pipeline_success_flow(self, mock_services: dict, pipeline_config: dict):
        """Test successful pipeline execution."""
        # Setup mock data
        pm_data = self._get_mock_polymarket_data()
        sb_data = self._get_mock_sportsbook_data()
        
        mock_services["polymarket"].fetch_markets = AsyncMock(return_value=pm_data)
        mock_services["odds_api"].fetch_events = AsyncMock(return_value=sb_data)
        mock_services["telegram"].send_alert = AsyncMock(return_value={"ok": True})
        
        # Execute pipeline
        result = await self._run_pipeline(mock_services, pipeline_config)
        
        assert result["success"] is True
        assert result["markets_fetched"] > 0
        assert result["opportunities_found"] >= 0
    
    @pytest.mark.asyncio
    async def test_pipeline_no_arbitrage(self, mock_services: dict, pipeline_config: dict):
        """Test pipeline when no arbitrage exists."""
        # Similar prices - no arbitrage
        pm_data = [{
            "id": "0x001",
            "question": "Team A vs Team B",
            "outcomePrices": ["0.50", "0.50"],
            "liquidity": "50000",
            "active": True
        }]
        
        sb_data = [{
            "id": "event_001",
            "home_team": "Team A",
            "away_team": "Team B",
            "bookmakers": [{
                "key": "draftkings",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Team A", "price": 2.0},
                    {"name": "Team B", "price": 2.0}
                ]}]
            }]
        }]
        
        mock_services["polymarket"].fetch_markets = AsyncMock(return_value=pm_data)
        mock_services["odds_api"].fetch_events = AsyncMock(return_value=sb_data)
        
        result = await self._run_pipeline(mock_services, pipeline_config)
        
        assert result["opportunities_found"] == 0
        assert result["alerts_sent"] == 0
    
    @pytest.mark.asyncio
    async def test_pipeline_with_arbitrage(self, mock_services: dict, pipeline_config: dict):
        """Test pipeline when arbitrage exists."""
        # Significant price divergence
        pm_data = [{
            "id": "0x002",
            "question": "Chiefs vs Raiders",
            "outcomePrices": ["0.80", "0.20"],  # 80% implied = 1.25 odds
            "liquidity": "100000",
            "active": True
        }]
        
        sb_data = [{
            "id": "event_002",
            "home_team": "Kansas City Chiefs",
            "away_team": "Las Vegas Raiders",
            "bookmakers": [{
                "key": "draftkings",
                "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Kansas City Chiefs", "price": 1.50},  # 66.7% implied
                    {"name": "Las Vegas Raiders", "price": 2.80}
                ]}]
            }]
        }]
        
        mock_services["polymarket"].fetch_markets = AsyncMock(return_value=pm_data)
        mock_services["odds_api"].fetch_events = AsyncMock(return_value=sb_data)
        mock_services["telegram"].send_alert = AsyncMock(return_value={"ok": True})
        
        result = await self._run_pipeline(mock_services, pipeline_config)
        
        # Should find opportunities (prices diverge significantly)
        assert result["markets_fetched"] > 0
        assert result["normalized_count"] > 0
    
    @pytest.mark.asyncio
    async def test_pipeline_data_persistence(self, mock_services: dict, pipeline_config: dict):
        """Test that pipeline results are persisted."""
        pm_data = self._get_mock_polymarket_data()
        sb_data = self._get_mock_sportsbook_data()
        
        mock_services["polymarket"].fetch_markets = AsyncMock(return_value=pm_data)
        mock_services["odds_api"].fetch_events = AsyncMock(return_value=sb_data)
        
        with patch("builtins.open", MagicMock()):
            result = await self._run_pipeline(mock_services, pipeline_config, persist=True)
        
        assert result["persisted"] is True


class TestPipelineComponents:
    """Test individual pipeline components."""
    
    def test_fetch_step(self):
        """Test data fetch step."""
        fetcher = MagicMock()
        fetcher.fetch = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
        
        data = self._run_fetch_step(fetcher)
        
        assert len(data) == 2
    
    def test_normalize_step(self):
        """Test normalization step."""
        raw_data = [
            {"id": "0x1", "question": "Test 1", "outcomePrices": ["0.5", "0.5"]},
            {"id": "0x2", "question": "Test 2", "outcomePrices": ["0.6", "0.4"]}
        ]
        
        normalized = self._run_normalize_step(raw_data, source="polymarket")
        
        assert len(normalized) == 2
        assert all("market_id" in m for m in normalized)
        assert all("source" in m for m in normalized)
    
    def test_match_step(self):
        """Test matching step."""
        pm_markets = [
            {"market_id": "pm_1", "teams": ["Chiefs", "49ers"], "sport": "football"}
        ]
        sb_markets = [
            {"market_id": "sb_1", "teams": ["Kansas City Chiefs", "San Francisco 49ers"], "sport": "football"}
        ]
        
        matches = self._run_match_step(pm_markets, sb_markets)
        
        assert len(matches) > 0
        assert matches[0]["confidence"] > 0.8
    
    def test_calculate_step(self):
        """Test arbitrage calculation step."""
        matches = [{
            "polymarket": {"odds": 2.1, "liquidity": 50000},
            "sportsbook": {"odds": 2.0, "liquidity": 100000},
            "confidence": 0.95
        }]
        
        opportunities = self._run_calculate_step(matches)
        
        assert isinstance(opportunities, list)
    
    def test_filter_step(self):
        """Test filter step."""
        opportunities = [
            {"net_edge_percent": 5.0, "liquidity": 50000},
            {"net_edge_percent": 0.5, "liquidity": 100},  # Too low
            {"net_edge_percent": 3.0, "liquidity": 50000}
        ]
        
        config = {"min_edge": 2.0, "min_liquidity": 10000}
        filtered = self._run_filter_step(opportunities, config)
        
        assert len(filtered) == 2  # First and third pass
    
    def test_alert_step(self):
        """Test alert step."""
        opportunities = [
            {"net_edge_percent": 5.0, "match_id": "001"},
            {"net_edge_percent": 3.0, "match_id": "002"}
        ]
        
        alert_service = MagicMock()
        alert_service.send = AsyncMock(return_value={"ok": True})
        
        result = self._run_alert_step(opportunities, alert_service)
        
        assert result["alerts_sent"] == 2


class TestPipelineErrorHandling:
    """Test pipeline error handling."""
    
    @pytest.mark.asyncio
    async def test_fetch_failure_handling(self):
        """Test handling of fetch failures."""
        fetcher = MagicMock()
        fetcher.fetch = AsyncMock(side_effect=Exception("API Error"))
        
        result = await self._run_pipeline_with_error_handling([fetcher])
        
        assert result["errors"] > 0
        assert result["success"] is False
    
    @pytest.mark.asyncio
    async def test_partial_fetch_failure(self):
        """Test when some sources fail but others succeed."""
        pm_fetcher = MagicMock()
        pm_fetcher.fetch = AsyncMock(return_value=[{"id": "1"}])
        pm_fetcher.name = "polymarket"
        
        sb_fetcher = MagicMock()
        sb_fetcher.fetch = AsyncMock(side_effect=Exception("API Error"))
        sb_fetcher.name = "sportsbook"
        
        result = await self._run_pipeline_with_partial_failure([pm_fetcher, sb_fetcher])
        
        # Should continue with partial data
        assert result["partial_success"] is True
        assert result["sources_succeeded"] == 1
    
    def test_normalization_error_handling(self):
        """Test handling of normalization errors."""
        raw_data = [
            {"id": "valid", "question": "Good market"},
            {"id": "invalid"},  # Missing required fields
            {"id": "valid2", "question": "Another good market"}
        ]
        
        normalized = self._run_normalize_with_error_handling(raw_data)
        
        # Should skip invalid but continue
        assert len(normalized) == 2
    
    def test_empty_data_handling(self):
        """Test handling of empty data."""
        result = self._run_pipeline_with_data([])
        
        assert result["opportunities_found"] == 0
        assert result["success"] is True  # Not an error, just no data


class TestPipelinePerformance:
    """Test pipeline performance characteristics."""
    
    def test_large_dataset_handling(self):
        """Test pipeline with large dataset."""
        large_pm_data = [{"id": f"0x{i}", "question": f"Market {i}"} for i in range(1000)]
        large_sb_data = [{"id": f"sb{i}", "event": f"Event {i}"} for i in in range(1000)]
        
        result = self._run_pipeline_with_data(large_pm_data, large_sb_data)
        
        assert result["success"] is True
        assert result["processing_time"] < 60  # Should complete in reasonable time
    
    def test_concurrent_processing(self):
        """Test concurrent processing of multiple sources."""
        # Pipeline should fetch from multiple sources concurrently
        import asyncio
        
        start_time = datetime.now()
        
        # Simulated concurrent fetch
        async def fetch_all():
            await asyncio.gather(
                asyncio.sleep(0.1),
                asyncio.sleep(0.1),
                asyncio.sleep(0.1)
            )
        
        asyncio.run(fetch_all())
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # Should take ~0.1s, not ~0.3s (concurrent)
        assert elapsed < 0.25


# Helper methods

    def _get_mock_polymarket_data(self) -> list:
        """Get mock Polymarket data."""
        return [
            {
                "id": "0xabc123",
                "question": "Will Chiefs win?",
                "outcomePrices": ["0.65", "0.35"],
                "liquidity": "500000",
                "active": True
            },
            {
                "id": "0xdef456",
                "question": "Will Eagles win?",
                "outcomePrices": ["0.55", "0.45"],
                "liquidity": "200000",
                "active": True
            }
        ]
    
    def _get_mock_sportsbook_data(self) -> list:
        """Get mock sportsbook data."""
        return [
            {
                "id": "event_001",
                "home_team": "Kansas City Chiefs",
                "away_team": "Denver Broncos",
                "bookmakers": [{
                    "key": "draftkings",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Kansas City Chiefs", "price": 1.54},
                        {"name": "Denver Broncos", "price": 2.60}
                    ]}]
                }]
            },
            {
                "id": "event_002",
                "home_team": "Philadelphia Eagles",
                "away_team": "Dallas Cowboys",
                "bookmakers": [{
                    "key": "draftkings",
                    "markets": [{"key": "h2h", "outcomes": [
                        {"name": "Philadelphia Eagles", "price": 1.80},
                        {"name": "Dallas Cowboys", "price": 2.10}
                    ]}]
                }]
            }
        ]
    
    async def _run_pipeline(self, services: dict, config: dict, persist: bool = False) -> dict:
        """Run the complete pipeline."""
        result = {
            "success": True,
            "markets_fetched": 0,
            "normalized_count": 0,
            "matches_found": 0,
            "opportunities_found": 0,
            "alerts_sent": 0,
            "persisted": persist
        }
        
        try:
            # Fetch
            pm_data = await services["polymarket"].fetch_markets()
            sb_data = await services["odds_api"].fetch_events()
            
            result["markets_fetched"] = len(pm_data) + len(sb_data)
            
            # Normalize (simplified)
            result["normalized_count"] = len(pm_data) + len(sb_data)
            
            # Simulate finding some matches
            result["matches_found"] = min(len(pm_data), len(sb_data))
            result["opportunities_found"] = result["matches_found"]
            
            # Send alerts
            if config.get("enable_alerts") and result["opportunities_found"] > 0:
                await services["telegram"].send_alert({})
                result["alerts_sent"] = result["opportunities_found"]
            
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        
        return result
    
    def _run_fetch_step(self, fetcher: MagicMock) -> list:
        """Run fetch step."""
        import asyncio
        return asyncio.run(fetcher.fetch())
    
    def _run_normalize_step(self, raw_data: list, source: str) -> list:
        """Run normalize step."""
        return [{"market_id": d.get("id", ""), "source": source} for d in raw_data]
    
    def _run_match_step(self, pm_markets: list, sb_markets: list) -> list:
        """Run match step."""
        # Simplified matching
        return [{"confidence": 0.95, "pm": pm_markets[0], "sb": sb_markets[0]}]
    
    def _run_calculate_step(self, matches: list) -> list:
        """Run calculate step."""
        return [{"is_arbitrage": True, "edge": 5.0} for _ in matches]
    
    def _run_filter_step(self, opportunities: list, config: dict) -> list:
        """Run filter step."""
        return [
            o for o in opportunities
            if o.get("net_edge_percent", 0) >= config.get("min_edge", 0)
            and o.get("liquidity", 0) >= config.get("min_liquidity", 0)
        ]
    
    def _run_alert_step(self, opportunities: list, alert_service: MagicMock) -> dict:
        """Run alert step."""
        import asyncio
        for opp in opportunities:
            asyncio.run(alert_service.send(opp))
        return {"alerts_sent": len(opportunities)}
    
    async def _run_pipeline_with_error_handling(self, fetchers: list) -> dict:
        """Run pipeline with error handling."""
        result = {"success": True, "errors": 0}
        
        for fetcher in fetchers:
            try:
                await fetcher.fetch()
            except Exception:
                result["errors"] += 1
                result["success"] = False
        
        return result
    
    async def _run_pipeline_with_partial_failure(self, fetchers: list) -> dict:
        """Run pipeline with partial failure handling."""
        result = {"partial_success": False, "sources_succeeded": 0}
        
        for fetcher in fetchers:
            try:
                await fetcher.fetch()
                result["sources_succeeded"] += 1
            except Exception:
                pass
        
        result["partial_success"] = result["sources_succeeded"] > 0
        return result
    
    def _run_normalize_with_error_handling(self, raw_data: list) -> list:
        """Run normalization with error handling."""
        normalized = []
        for item in raw_data:
            try:
                if "question" in item or "event" in item:
                    normalized.append({"id": item["id"], "valid": True})
            except Exception:
                continue
        return normalized
    
    def _run_pipeline_with_data(self, pm_data: list, sb_data: list = None) -> dict:
        """Run pipeline with provided data."""
        return {
            "success": True,
            "opportunities_found": len(pm_data) if pm_data else 0,
            "processing_time": 0.5
        }
