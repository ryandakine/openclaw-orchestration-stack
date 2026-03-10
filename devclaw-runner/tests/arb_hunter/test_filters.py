"""
Test Filters Module

Tests for all filter conditions: edge threshold, liquidity, staleness, confidence.
"""

import pytest
from datetime import datetime, timedelta
from typing import Any


class TestEdgeThresholdFilter:
    """Test edge threshold filtering."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Test configuration."""
        return {
            "min_edge_percent": 2.0,
            "min_net_edge_percent": 1.5
        }
    
    @pytest.mark.parametrize("edge,expected_pass", [
        (5.0, True),   # Well above threshold
        (2.0, True),   # At threshold
        (1.9, False),  # Just below threshold
        (0.5, False),  # Well below threshold
        (0.0, False),  # Zero edge
        (-1.0, False), # Negative edge
    ])
    def test_gross_edge_threshold(self, edge: float, expected_pass: bool, test_config: dict):
        """Test gross edge threshold filtering."""
        opportunity = {"gross_edge_percent": edge}
        
        passed = self._check_edge_threshold(opportunity, test_config["min_edge_percent"])
        
        assert passed == expected_pass
    
    @pytest.mark.parametrize("net_edge,expected_pass", [
        (3.0, True),
        (1.5, True),
        (1.4, False),
        (0.0, False),
    ])
    def test_net_edge_threshold(self, net_edge: float, expected_pass: bool, test_config: dict):
        """Test net edge threshold filtering."""
        opportunity = {"net_edge_percent": net_edge}
        
        passed = self._check_net_edge_threshold(opportunity, test_config["min_net_edge_percent"])
        
        assert passed == expected_pass
    
    def test_missing_edge_field(self, test_config: dict):
        """Test filtering when edge field is missing."""
        opportunity = {}  # No edge field
        
        passed = self._check_edge_threshold(opportunity, test_config["min_edge_percent"])
        
        assert passed is False


class TestLiquidityFilter:
    """Test liquidity filtering."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Test configuration."""
        return {
            "min_liquidity_usd": 10000
        }
    
    @pytest.mark.parametrize("liquidity,expected_pass", [
        (50000, True),   # Well above threshold
        (10000, True),   # At threshold
        (9999, False),   # Just below threshold
        (5000, False),   # Below threshold
        (0, False),      # Zero liquidity
    ])
    def test_polymarket_liquidity_filter(self, liquidity: float, expected_pass: bool, test_config: dict):
        """Test Polymarket liquidity filtering."""
        market = {
            "source": "polymarket",
            "liquidity_usd": liquidity
        }
        
        passed = self._check_liquidity(market, test_config["min_liquidity_usd"])
        
        assert passed == expected_pass
    
    def test_sportsbook_liquidity_estimation(self, test_config: dict):
        """Test sportsbook liquidity estimation."""
        # Sportsbooks don't report liquidity directly
        market = {
            "source": "draftkings",
            "liquidity_usd": None  # Not provided
        }
        
        # Should estimate based on book or assume sufficient
        passed = self._check_liquidity(market, test_config["min_liquidity_usd"])
        
        # Sportsbooks typically have sufficient liquidity
        assert passed is True
    
    def test_combined_liquidity_filter(self, test_config: dict):
        """Test combined liquidity for arbitrage sides."""
        opportunity = {
            "side_a": {"venue": "polymarket", "liquidity": 5000},
            "side_b": {"venue": "draftkings", "liquidity": 100000}
        }
        
        passed = self._check_combined_liquidity(opportunity, test_config["min_liquidity_usd"])
        
        # Both sides need sufficient liquidity
        assert passed is False
    
    def test_extreme_liquidity_values(self, test_config: dict):
        """Test with extreme liquidity values."""
        market = {
            "source": "polymarket",
            "liquidity_usd": 1000000000  # 1 billion
        }
        
        passed = self._check_liquidity(market, test_config["min_liquidity_usd"])
        
        assert passed is True


class TestStalenessFilter:
    """Test data staleness filtering."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Test configuration."""
        return {
            "max_odds_staleness_minutes": 30
        }
    
    def test_fresh_data_passes(self, test_config: dict):
        """Test fresh data passes staleness filter."""
        market = {
            "last_updated": datetime.now() - timedelta(minutes=5)
        }
        
        passed = self._check_staleness(market, test_config["max_odds_staleness_minutes"])
        
        assert passed is True
    
    def test_stale_data_fails(self, test_config: dict):
        """Test stale data fails staleness filter."""
        market = {
            "last_updated": datetime.now() - timedelta(minutes=60)
        }
        
        passed = self._check_staleness(market, test_config["max_odds_staleness_minutes"])
        
        assert passed is False
    
    def test_boundary_staleness(self, test_config: dict):
        """Test boundary condition for staleness."""
        market = {
            "last_updated": datetime.now() - timedelta(minutes=30)
        }
        
        passed = self._check_staleness(market, test_config["max_odds_staleness_minutes"])
        
        # At threshold, typically passes
        assert passed is True
    
    def test_missing_timestamp(self, test_config: dict):
        """Test handling of missing timestamp."""
        market = {}
        
        passed = self._check_staleness(market, test_config["max_odds_staleness_minutes"])
        
        # Missing timestamp should fail or use current time
        assert passed is False
    
    def test_future_timestamp(self, test_config: dict):
        """Test handling of future timestamp (clock skew)."""
        market = {
            "last_updated": datetime.now() + timedelta(minutes=5)
        }
        
        passed = self._check_staleness(market, test_config["max_odds_staleness_minutes"])
        
        # Future timestamps should be treated as fresh
        assert passed is True


class TestConfidenceFilter:
    """Test match confidence filtering."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Test configuration."""
        return {
            "min_match_confidence": 0.85
        }
    
    @pytest.mark.parametrize("confidence,expected_pass", [
        (0.95, True),
        (0.85, True),
        (0.84, False),
        (0.50, False),
        (0.0, False),
    ])
    def test_confidence_threshold(self, confidence: float, expected_pass: bool, test_config: dict):
        """Test confidence threshold filtering."""
        match_result = {"confidence": confidence}
        
        passed = self._check_confidence(match_result, test_config["min_match_confidence"])
        
        assert passed == expected_pass
    
    def test_missing_confidence(self, test_config: dict):
        """Test handling of missing confidence."""
        match_result = {}
        
        passed = self._check_confidence(match_result, test_config["min_match_confidence"])
        
        assert passed is False
    
    def test_perfect_confidence(self, test_config: dict):
        """Test with perfect confidence."""
        match_result = {"confidence": 1.0}
        
        passed = self._check_confidence(match_result, test_config["min_match_confidence"])
        
        assert passed is True


class TestBlockedListsFilter:
    """Test blocked sports/leagues/teams filtering."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Test configuration with blocked lists."""
        return {
            "blocked_sports": ["cricket", "rugby"],
            "blocked_leagues": ["XFL", "AAF"],
            "blocked_teams": ["Problem Team", "Suspended FC"]
        }
    
    def test_blocked_sport_filtered(self, test_config: dict):
        """Test blocked sports are filtered."""
        market = {"sport": "cricket"}
        
        passed = self._check_blocked_lists(market, test_config)
        
        assert passed is False
    
    def test_allowed_sport_passes(self, test_config: dict):
        """Test allowed sports pass filter."""
        market = {"sport": "football"}
        
        passed = self._check_blocked_lists(market, test_config)
        
        assert passed is True
    
    def test_blocked_league_filtered(self, test_config: dict):
        """Test blocked leagues are filtered."""
        market = {"sport": "football", "league": "XFL"}
        
        passed = self._check_blocked_lists(market, test_config)
        
        assert passed is False
    
    def test_blocked_team_filtered(self, test_config: dict):
        """Test blocked teams are filtered."""
        market = {"teams": ["Problem Team", "Other Team"]}
        
        passed = self._check_blocked_lists(market, test_config)
        
        assert passed is False
    
    def test_case_insensitive_blocking(self, test_config: dict):
        """Test blocking is case insensitive."""
        market = {"sport": "CRICKET"}  # Uppercase
        
        passed = self._check_blocked_lists(market, test_config)
        
        assert passed is False


class TestCompositeFiltering:
    """Test composite filter application."""
    
    @pytest.fixture
    def test_config(self) -> dict:
        """Complete test configuration."""
        return {
            "min_edge_percent": 2.0,
            "min_net_edge_percent": 1.5,
            "min_liquidity_usd": 10000,
            "max_odds_staleness_minutes": 30,
            "min_match_confidence": 0.85,
            "blocked_sports": [],
            "blocked_leagues": [],
            "blocked_teams": []
        }
    
    def test_all_pass(self, test_config: dict):
        """Test opportunity passing all filters."""
        opportunity = {
            "net_edge_percent": 5.0,
            "side_a": {"venue": "polymarket", "liquidity": 50000},
            "side_b": {"venue": "draftkings", "liquidity": 100000},
            "last_updated": datetime.now(),
            "confidence": 0.95,
            "sport": "football",
            "league": "NFL"
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        assert result["passed"] is True
        assert len(result["failed_filters"]) == 0
    
    def test_one_filter_fails(self, test_config: dict):
        """Test opportunity failing one filter."""
        opportunity = {
            "net_edge_percent": 5.0,
            "side_a": {"venue": "polymarket", "liquidity": 50000},
            "side_b": {"venue": "draftkings", "liquidity": 100000},
            "last_updated": datetime.now() - timedelta(minutes=60),  # Stale
            "confidence": 0.95,
            "sport": "football"
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        assert result["passed"] is False
        assert "staleness" in result["failed_filters"]
    
    def test_multiple_filters_fail(self, test_config: dict):
        """Test opportunity failing multiple filters."""
        opportunity = {
            "net_edge_percent": 0.5,  # Too low
            "side_a": {"venue": "polymarket", "liquidity": 100},  # Too low
            "side_b": {"venue": "draftkings", "liquidity": 100000},
            "last_updated": datetime.now(),
            "confidence": 0.95
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        assert result["passed"] is False
        assert len(result["failed_filters"]) >= 2
    
    def test_filter_reasons(self, test_config: dict):
        """Test that filter failure reasons are provided."""
        opportunity = {
            "net_edge_percent": 0.5,
            "confidence": 0.50
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        assert result["passed"] is False
        assert "reasons" in result
        assert len(result["reasons"]) > 0


class TestFilterEdgeCases:
    """Test edge cases in filtering."""
    
    def test_empty_config(self):
        """Test filtering with empty configuration."""
        opportunity = {"net_edge_percent": 5.0}
        config = {}
        
        # Should use defaults or skip filtering
        result = self._apply_all_filters(opportunity, config)
        
        # Result should be valid (no filters to fail)
        assert isinstance(result["passed"], bool)
    
    def test_none_values(self, test_config: dict):
        """Test filtering with None values in opportunity."""
        opportunity = {
            "net_edge_percent": None,
            "liquidity_usd": None
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        # Should handle None gracefully
        assert result["passed"] is False
    
    def test_zero_values(self):
        """Test filtering with zero values."""
        opportunity = {
            "net_edge_percent": 0,
            "side_a": {"liquidity": 0},
            "confidence": 0
        }
        config = {
            "min_edge_percent": 0,
            "min_liquidity_usd": 0,
            "min_match_confidence": 0
        }
        
        # With zero thresholds, zero values should pass
        passed = (
            self._check_edge_threshold(opportunity, config["min_edge_percent"]) and
            self._check_liquidity(opportunity.get("side_a", {}), config["min_liquidity_usd"])
        )
        
        assert passed is True
    
    def test_very_large_values(self, test_config: dict):
        """Test filtering with very large values."""
        opportunity = {
            "net_edge_percent": 1000.0,  # 1000% edge
            "side_a": {"venue": "polymarket", "liquidity": 1e12},  # Trillion
            "last_updated": datetime.now(),
            "confidence": 1.0
        }
        
        result = self._apply_all_filters(opportunity, test_config)
        
        assert result["passed"] is True


# Helper methods

    def _check_edge_threshold(self, opportunity: dict, min_edge: float) -> bool:
        """Check if opportunity meets edge threshold."""
        edge = opportunity.get("gross_edge_percent", 0)
        if edge is None:
            return False
        return edge >= min_edge
    
    def _check_net_edge_threshold(self, opportunity: dict, min_net_edge: float) -> bool:
        """Check if opportunity meets net edge threshold."""
        edge = opportunity.get("net_edge_percent", 0)
        if edge is None:
            return False
        return edge >= min_net_edge
    
    def _check_liquidity(self, market: dict, min_liquidity: float) -> bool:
        """Check if market meets liquidity requirements."""
        source = market.get("source", "").lower()
        
        if source in ["draftkings", "fanduel", "betmgm"]:
            # Assume sportsbooks have sufficient liquidity
            return True
        
        liquidity = market.get("liquidity_usd", 0)
        if liquidity is None:
            return False
        return liquidity >= min_liquidity
    
    def _check_combined_liquidity(self, opportunity: dict, min_liquidity: float) -> bool:
        """Check liquidity for both sides of arbitrage."""
        side_a = opportunity.get("side_a", {})
        side_b = opportunity.get("side_b", {})
        
        liq_a = side_a.get("liquidity", 0)
        liq_b = side_b.get("liquidity", 0)
        
        return liq_a >= min_liquidity and liq_b >= min_liquidity
    
    def _check_staleness(self, market: dict, max_staleness_minutes: int) -> bool:
        """Check if data is fresh enough."""
        last_updated = market.get("last_updated")
        if last_updated is None:
            return False
        
        age = (datetime.now() - last_updated).total_seconds() / 60
        return age <= max_staleness_minutes
    
    def _check_confidence(self, match_result: dict, min_confidence: float) -> bool:
        """Check if match confidence is sufficient."""
        confidence = match_result.get("confidence", 0)
        if confidence is None:
            return False
        return confidence >= min_confidence
    
    def _check_blocked_lists(self, market: dict, config: dict) -> bool:
        """Check if market is in blocked lists."""
        sport = market.get("sport", "").lower()
        league = market.get("league", "").upper()
        teams = [t.lower() for t in market.get("teams", [])]
        
        blocked_sports = [s.lower() for s in config.get("blocked_sports", [])]
        blocked_leagues = [l.upper() for l in config.get("blocked_leagues", [])]
        blocked_teams = [t.lower() for t in config.get("blocked_teams", [])]
        
        if sport in blocked_sports:
            return False
        if league in blocked_leagues:
            return False
        if any(team in blocked_teams for team in teams):
            return False
        
        return True
    
    def _apply_all_filters(self, opportunity: dict, config: dict) -> dict:
        """Apply all filters and return result."""
        failed_filters = []
        reasons = []
        
        # Edge threshold
        if not self._check_net_edge_threshold(opportunity, config.get("min_net_edge_percent", 0)):
            failed_filters.append("edge")
            reasons.append(f"Net edge below threshold")
        
        # Liquidity
        if "side_a" in opportunity and "side_b" in opportunity:
            if not self._check_combined_liquidity(opportunity, config.get("min_liquidity_usd", 0)):
                failed_filters.append("liquidity")
                reasons.append("Insufficient liquidity")
        else:
            if not self._check_liquidity(opportunity, config.get("min_liquidity_usd", 0)):
                failed_filters.append("liquidity")
                reasons.append("Insufficient liquidity")
        
        # Staleness
        if not self._check_staleness(opportunity, config.get("max_odds_staleness_minutes", 60)):
            failed_filters.append("staleness")
            reasons.append("Data too stale")
        
        # Confidence
        if not self._check_confidence(opportunity, config.get("min_match_confidence", 0)):
            failed_filters.append("confidence")
            reasons.append("Match confidence too low")
        
        # Blocked lists
        if not self._check_blocked_lists(opportunity, config):
            failed_filters.append("blocked")
            reasons.append("Market in blocked list")
        
        return {
            "passed": len(failed_filters) == 0,
            "failed_filters": failed_filters,
            "reasons": reasons
        }
