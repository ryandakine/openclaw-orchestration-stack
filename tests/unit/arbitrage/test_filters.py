"""
Unit tests for the opportunity filters module.

These tests verify:
- Profitability filtering
- Match confidence filtering
- Liquidity filtering
- Data freshness filtering
- Time to event filtering
- Fee filtering
- Source filtering
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from src.arbitrage.filters import (
    OpportunityFilter,
    check_profitability,
    check_match_confidence,
    check_liquidity,
    check_freshness,
    check_time_to_event,
    check_fees,
    check_sources,
    filter_opportunity,
    filter_opportunities,
    OpportunityRanker,
)
from src.arbitrage.models import (
    ArbitrageOpportunity,
    ArbitrageLeg,
)


class TestOpportunityFilterConfig:
    """Test OpportunityFilter configuration."""
    
    def test_default_config(self):
        """Test default filter configuration."""
        config = OpportunityFilter()
        
        assert config.min_profit_pct == Decimal("2.0")
        assert config.min_match_score == Decimal("0.75")
        assert config.min_resolution_confidence == Decimal("0.90")
        assert config.max_time_to_event_hours == 168
        assert config.min_liquidity_usd == Decimal("5000")
        assert config.max_freshness_seconds == 120
    
    def test_conservative_config(self):
        """Test conservative filter preset."""
        config = OpportunityFilter.conservative()
        
        assert config.min_profit_pct == Decimal("3.0")
        assert config.min_match_score == Decimal("0.85")
        assert config.min_resolution_confidence == Decimal("0.95")
        assert config.max_time_to_event_hours == 72
        assert config.min_liquidity_usd == Decimal("10000")
    
    def test_aggressive_config(self):
        """Test aggressive filter preset."""
        config = OpportunityFilter.aggressive()
        
        assert config.min_profit_pct == Decimal("1.0")
        assert config.min_match_score == Decimal("0.60")
        assert config.min_resolution_confidence == Decimal("0.75")
        assert config.max_time_to_event_hours == 336
        assert config.min_liquidity_usd == Decimal("1000")


class TestCheckProfitability:
    """Test profitability checks."""
    
    def test_profit_above_threshold(self):
        """Test opportunity above profit threshold passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            net_edge_pct=Decimal("3.0"),
        )
        
        passed, reason = check_profitability(opp, Decimal("2.0"))
        assert passed is True
        assert reason is None
    
    def test_profit_below_threshold(self):
        """Test opportunity below profit threshold fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            net_edge_pct=Decimal("1.5"),
        )
        
        passed, reason = check_profitability(opp, Decimal("2.0"))
        assert passed is False
        assert "1.50%" in reason
        assert "2.0%" in reason
    
    def test_profit_at_threshold(self):
        """Test opportunity at exactly threshold passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            net_edge_pct=Decimal("2.0"),
        )
        
        passed, reason = check_profitability(opp, Decimal("2.0"))
        # At threshold should pass (>=)
        assert passed is True


class TestCheckMatchConfidence:
    """Test match confidence checks."""
    
    def test_high_confidence_passes(self):
        """Test high match confidence passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            match_score=Decimal("0.85"),
            resolution_confidence=Decimal("0.95"),
        )
        
        passed, reason = check_match_confidence(
            opp,
            Decimal("0.75"),
            Decimal("0.90"),
        )
        assert passed is True
    
    def test_low_match_score_fails(self):
        """Test low match score fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            match_score=Decimal("0.60"),
            resolution_confidence=Decimal("0.95"),
        )
        
        passed, reason = check_match_confidence(
            opp,
            Decimal("0.75"),
            Decimal("0.90"),
        )
        assert passed is False
        assert "Match score" in reason
    
    def test_low_resolution_confidence_fails(self):
        """Test low resolution confidence fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            match_score=Decimal("0.85"),
            resolution_confidence=Decimal("0.80"),
        )
        
        passed, reason = check_match_confidence(
            opp,
            Decimal("0.75"),
            Decimal("0.90"),
        )
        assert passed is False
        assert "Resolution confidence" in reason


class TestCheckLiquidity:
    """Test liquidity checks."""
    
    def test_sufficient_liquidity(self):
        """Test opportunity with sufficient liquidity passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("20000"),
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is True
    
    def test_insufficient_left_liquidity(self):
        """Test opportunity with insufficient left leg liquidity fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=Decimal("1000"),  # Too low
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("20000"),
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is False
        assert "Left leg liquidity" in reason
    
    def test_insufficient_right_liquidity(self):
        """Test opportunity with insufficient right leg liquidity fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("2000"),  # Too low
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is False
        assert "Right leg liquidity" in reason
    
    def test_missing_leg(self):
        """Test opportunity with missing leg fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=None,
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("20000"),
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is False
        assert "Missing leg" in reason


class TestCheckFreshness:
    """Test data freshness checks."""
    
    def test_fresh_data(self):
        """Test fresh data passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            freshness_seconds=30,  # 30 seconds old
        )
        
        passed, reason = check_freshness(opp, 120)
        assert passed is True
    
    def test_stale_data(self):
        """Test stale data fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            freshness_seconds=300,  # 5 minutes old
        )
        
        passed, reason = check_freshness(opp, 120)
        assert passed is False
        assert "300s" in reason
        assert "120s" in reason


class TestCheckTimeToEvent:
    """Test time to event checks."""
    
    def test_event_in_future(self):
        """Test event in the future passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        
        passed, reason = check_time_to_event(opp, 48)
        assert passed is True
    
    def test_event_too_far_in_future(self):
        """Test event too far in future fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            expires_at=datetime.utcnow() + timedelta(days=10),
        )
        
        passed, reason = check_time_to_event(opp, 168)  # 1 week max
        assert passed is False
        assert "exceeds maximum" in reason
    
    def test_event_already_started(self):
        """Test event that already started fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        
        passed, reason = check_time_to_event(opp, 168)
        assert passed is False
        assert "already started" in reason
    
    def test_no_expiry_time(self):
        """Test opportunity without expiry time passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            expires_at=None,
        )
        
        passed, reason = check_time_to_event(opp, 168)
        assert passed is True
    
    def test_disabled_check(self):
        """Test disabled time check always passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        
        passed, reason = check_time_to_event(opp, None)
        assert passed is True


class TestCheckFees:
    """Test fee checks."""
    
    def test_acceptable_fees(self):
        """Test acceptable fees pass."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            gross_edge_pct=Decimal("5.0"),
            fees_pct=Decimal("2.0"),
            slippage_pct=Decimal("0.5"),
        )
        
        passed, reason = check_fees(
            opp,
            max_total_fees_pct=Decimal("5.0"),
            min_edge_over_fees_pct=Decimal("1.0"),
        )
        assert passed is True
    
    def test_excessive_fees(self):
        """Test excessive fees fail."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            gross_edge_pct=Decimal("10.0"),
            fees_pct=Decimal("4.0"),
            slippage_pct=Decimal("2.0"),
        )
        
        passed, reason = check_fees(
            opp,
            max_total_fees_pct=Decimal("5.0"),
            min_edge_over_fees_pct=Decimal("1.0"),
        )
        assert passed is False
        assert "6.00%" in reason  # 4 + 2
    
    def test_low_edge_over_fees(self):
        """Test when edge over fees is too small."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            gross_edge_pct=Decimal("3.0"),
            fees_pct=Decimal("2.0"),
            slippage_pct=Decimal("0.5"),
        )
        # Edge over fees = 3.0 - 2.5 = 0.5%, below 1% threshold
        
        passed, reason = check_fees(
            opp,
            max_total_fees_pct=Decimal("5.0"),
            min_edge_over_fees_pct=Decimal("1.0"),
        )
        assert passed is False
        assert "0.50%" in reason


class TestCheckSources:
    """Test source suspension checks."""
    
    def test_allowed_sources(self):
        """Test opportunity with allowed sources passes."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
            ),
        )
        
        passed, reason = check_sources(opp, ["suspended_book"])
        assert passed is True
    
    def test_suspended_left_source(self):
        """Test opportunity with suspended left source fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
            ),
        )
        
        passed, reason = check_sources(opp, ["polymarket"])
        assert passed is False
        assert "polymarket" in reason.lower()
    
    def test_suspended_right_source(self):
        """Test opportunity with suspended right source fails."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
            ),
        )
        
        passed, reason = check_sources(opp, ["draftkings"])
        assert passed is False
        assert "draftkings" in reason.lower()


class TestFilterOpportunity:
    """Test comprehensive opportunity filtering."""
    
    @pytest.fixture
    def valid_opportunity(self):
        """Create a valid arbitrage opportunity."""
        return ArbitrageOpportunity(
            event_title="Lakers vs Warriors",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.1"),
                liquidity=Decimal("15000"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("25000"),
            ),
            net_edge_pct=Decimal("3.5"),
            gross_edge_pct=Decimal("4.0"),
            fees_pct=Decimal("0.3"),
            slippage_pct=Decimal("0.2"),
            match_score=Decimal("0.85"),
            resolution_confidence=Decimal("0.95"),
            freshness_seconds=30,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
    
    @pytest.fixture
    def filter_config(self):
        return OpportunityFilter(
            min_profit_pct=Decimal("2.0"),
            min_match_score=Decimal("0.75"),
            min_resolution_confidence=Decimal("0.90"),
            max_time_to_event_hours=48,
            min_liquidity_usd=Decimal("5000"),
            max_freshness_seconds=120,
            max_total_fees_pct=Decimal("5.0"),
            min_edge_over_fees_pct=Decimal("1.0"),
        )
    
    def test_valid_opportunity_passes(self, valid_opportunity, filter_config):
        """Test that a valid opportunity passes all filters."""
        is_valid, failures = filter_opportunity(valid_opportunity, filter_config)
        
        assert is_valid is True
        assert len(failures) == 0
    
    def test_multiple_failures(self, valid_opportunity, filter_config):
        """Test that all failures are reported."""
        # Make opportunity fail multiple checks
        valid_opportunity.net_edge_pct = Decimal("1.0")  # Too low profit
        valid_opportunity.match_score = Decimal("0.50")  # Too low confidence
        valid_opportunity.left_leg.liquidity = Decimal("100")  # Too low liquidity
        
        is_valid, failures = filter_opportunity(valid_opportunity, filter_config)
        
        assert is_valid is False
        assert len(failures) >= 3
    
    def test_profit_failure_only(self, valid_opportunity, filter_config):
        """Test specific profit failure."""
        valid_opportunity.net_edge_pct = Decimal("1.0")
        
        is_valid, failures = filter_opportunity(valid_opportunity, filter_config)
        
        assert is_valid is False
        assert any("Net profit" in f for f in failures)


class TestFilterOpportunities:
    """Test batch filtering of opportunities."""
    
    def test_filter_multiple(self):
        """Test filtering a list of opportunities."""
        opps = [
            ArbitrageOpportunity(
                event_title="Good Arb",
                net_edge_pct=Decimal("3.0"),
                gross_edge_pct=Decimal("3.5"),
                fees_pct=Decimal("0.3"),
                slippage_pct=Decimal("0.2"),
                match_score=Decimal("0.85"),
                resolution_confidence=Decimal("0.95"),
                left_leg=ArbitrageLeg(
                    source="polymarket",
                    source_event_id="pm1",
                    side="Yes",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
                right_leg=ArbitrageLeg(
                    source="draftkings",
                    source_event_id="dk1",
                    side="No",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
            ),
            ArbitrageOpportunity(
                event_title="Bad Arb - Low Profit",
                net_edge_pct=Decimal("1.0"),
                gross_edge_pct=Decimal("1.5"),
                fees_pct=Decimal("0.3"),
                slippage_pct=Decimal("0.2"),
                match_score=Decimal("0.85"),
                resolution_confidence=Decimal("0.95"),
                left_leg=ArbitrageLeg(
                    source="polymarket",
                    source_event_id="pm2",
                    side="Yes",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
                right_leg=ArbitrageLeg(
                    source="draftkings",
                    source_event_id="dk2",
                    side="No",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
            ),
            ArbitrageOpportunity(
                event_title="Bad Arb - Low Confidence",
                net_edge_pct=Decimal("4.0"),
                gross_edge_pct=Decimal("4.5"),
                fees_pct=Decimal("0.3"),
                slippage_pct=Decimal("0.2"),
                match_score=Decimal("0.50"),
                resolution_confidence=Decimal("0.95"),
                left_leg=ArbitrageLeg(
                    source="polymarket",
                    source_event_id="pm3",
                    side="Yes",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
                right_leg=ArbitrageLeg(
                    source="draftkings",
                    source_event_id="dk3",
                    side="No",
                    price=Decimal("2.0"),
                    liquidity=Decimal("10000"),
                ),
            ),
        ]
        
        # Use a simple filter config that only checks profit and match score
        config = OpportunityFilter(
            min_profit_pct=Decimal("2.0"),
            min_match_score=Decimal("0.75"),
            min_resolution_confidence=Decimal("0.90"),
            min_liquidity_usd=Decimal("1000"),  # Lower threshold
            max_freshness_seconds=3600,  # Higher threshold
        )
        
        valid, rejected = filter_opportunities(opps, config)
        
        assert len(valid) == 1, f"Expected 1 valid, got {len(valid)}"
        assert valid[0].event_title == "Good Arb"
        assert len(rejected) == 2


class TestOpportunityRanker:
    """Test opportunity ranking."""
    
    @pytest.fixture
    def ranker(self):
        return OpportunityRanker()
    
    @pytest.fixture
    def base_opp(self):
        return ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
            net_edge_pct=Decimal("3.0"),
            match_score=Decimal("0.80"),
            freshness_seconds=60,
            expires_at=datetime.utcnow() + timedelta(hours=48),
        )
    
    def test_rank_single(self, ranker, base_opp):
        """Test ranking a single opportunity."""
        score = ranker.calculate_score(base_opp)
        
        assert score > Decimal("0")
        assert score <= Decimal("1")
    
    def test_rank_multiple(self, ranker):
        """Test ranking multiple opportunities."""
        opps = [
            ArbitrageOpportunity(
                event_title="High Profit",
                left_leg=ArbitrageLeg(
                    source="polymarket",
                    source_event_id="pm1",
                    side="Yes",
                    price=Decimal("2.0"),
                    liquidity=Decimal("50000"),
                ),
                right_leg=ArbitrageLeg(
                    source="draftkings",
                    source_event_id="dk1",
                    side="No",
                    price=Decimal("2.0"),
                    liquidity=Decimal("50000"),
                ),
                net_edge_pct=Decimal("5.0"),
                match_score=Decimal("0.90"),
                freshness_seconds=30,
                expires_at=datetime.utcnow() + timedelta(hours=48),
            ),
            ArbitrageOpportunity(
                event_title="Low Profit",
                left_leg=ArbitrageLeg(
                    source="polymarket",
                    source_event_id="pm2",
                    side="Yes",
                    price=Decimal("2.0"),
                    liquidity=Decimal("5000"),
                ),
                right_leg=ArbitrageLeg(
                    source="draftkings",
                    source_event_id="dk2",
                    side="No",
                    price=Decimal("2.0"),
                    liquidity=Decimal("5000"),
                ),
                net_edge_pct=Decimal("2.0"),
                match_score=Decimal("0.75"),
                freshness_seconds=120,
                expires_at=datetime.utcnow() + timedelta(hours=12),
            ),
        ]
        
        ranked = ranker.rank(opps)
        
        # High profit should rank higher
        assert ranked[0][0].event_title == "High Profit"
        assert ranked[1][0].event_title == "Low Profit"
        assert ranked[0][1] > ranked[1][1]
    
    def test_higher_profit_scores_higher(self, ranker, base_opp):
        """Test that higher profit margin increases score."""
        score_3pct = ranker.calculate_score(base_opp)
        
        base_opp.net_edge_pct = Decimal("8.0")
        score_8pct = ranker.calculate_score(base_opp)
        
        assert score_8pct > score_3pct
    
    def test_fresher_data_scores_higher(self, ranker, base_opp):
        """Test that fresher data increases score."""
        base_opp.freshness_seconds = 10
        score_fresh = ranker.calculate_score(base_opp)
        
        base_opp.freshness_seconds = 200
        score_stale = ranker.calculate_score(base_opp)
        
        assert score_fresh > score_stale


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_zero_liquidity(self):
        """Test handling of zero liquidity."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=Decimal("0"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is False
    
    def test_none_liquidity(self):
        """Test handling of None liquidity."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.0"),
                liquidity=None,
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("10000"),
            ),
        )
        
        passed, reason = check_liquidity(opp, Decimal("5000"))
        assert passed is False
    
    def test_very_high_profit(self):
        """Test handling of unusually high profit margins."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            net_edge_pct=Decimal("50.0"),  # Unrealistically high
        )
        
        passed, reason = check_profitability(opp, Decimal("2.0"))
        assert passed is True
    
    def test_negative_profit(self):
        """Test handling of negative profit."""
        opp = ArbitrageOpportunity(
            event_title="Test",
            net_edge_pct=Decimal("-5.0"),
        )
        
        passed, reason = check_profitability(opp, Decimal("2.0"))
        assert passed is False
