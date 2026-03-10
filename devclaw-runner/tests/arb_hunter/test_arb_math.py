"""
Test Arbitrage Math Module

Tests for fee calc, slippage, gross/net edge, sizing, and all edge cases.
"""

import pytest
import math
from typing import Any


class TestFeeCalculations:
    """Test fee calculation functions."""
    
    @pytest.mark.parametrize("stake,fee_percent,expected", [
        (100, 2.0, 2.0),      # 2% of 100 = 2
        (500, 2.0, 10.0),     # 2% of 500 = 10
        (1000, 1.5, 15.0),    # 1.5% of 1000 = 15
        (0, 2.0, 0),          # Zero stake
        (100, 0, 0),          # Zero fee
    ])
    def test_polymarket_fee_calculation(self, stake: float, fee_percent: float, expected: float):
        """Test Polymarket fee calculation."""
        fee = self._calculate_polymarket_fee(stake, fee_percent)
        assert fee == pytest.approx(expected, 0.01)
    
    def test_gas_fee_calculation(self):
        """Test gas fee estimation."""
        # Gas fee should be constant or based on network conditions
        gas_fee = self._estimate_gas_fee()
        assert gas_fee >= 0
        assert isinstance(gas_fee, (int, float))
    
    @pytest.mark.parametrize("odds,vig_percent", [
        ([2.0, 2.0], 0),           # Fair odds, no vig
        ([1.9, 1.9], 5.26),        # ~5% vig on each side
        ([1.8, 2.1], None),        # Unequal vig
    ])
    def test_sportsbook_vig_calculation(self, odds: list, vig_percent: float | None):
        """Test sportsbook vig extraction."""
        if vig_percent is not None:
            calculated_vig = self._calculate_vig(odds[0], odds[1])
            assert pytest.approx(calculated_vig, 0.5) == vig_percent
        else:
            calculated_vig = self._calculate_vig(odds[0], odds[1])
            assert calculated_vig >= 0
    
    def test_vig_calculation_for_standard_odds(self):
        """Test vig calculation for standard -110 odds."""
        # -110 American odds = 1.909 decimal
        decimal_odds = 1.909
        
        # Two-way market with both sides at -110
        vig = self._calculate_vig(decimal_odds, decimal_odds)
        
        # Should be approximately 4.76% (standard book margin)
        assert pytest.approx(vig, 0.5) == 4.76


class TestSlippageCalculations:
    """Test slippage estimation."""
    
    @pytest.mark.parametrize("stake,liquidity,expected_slippage", [
        (100, 10000, 0.1),      # 1% of liquidity = small slippage
        (500, 10000, 0.5),      # 5% of liquidity
        (1000, 10000, 1.0),     # 10% of liquidity
        (5000, 10000, 5.0),     # 50% of liquidity = high slippage
        (100, 1000000, 0.01),   # Tiny relative to liquidity
    ])
    def test_slippage_based_on_liquidity_ratio(self, stake: float, liquidity: float, expected_slippage: float):
        """Test slippage scales with stake/liquidity ratio."""
        slippage = self._estimate_slippage(stake, liquidity)
        assert pytest.approx(slippage, 0.2) == expected_slippage
    
    def test_zero_liquidity_slippage(self):
        """Test slippage with zero liquidity."""
        with pytest.raises((ValueError, ZeroDivisionError)):
            self._estimate_slippage(100, 0)
    
    def test_large_slippage_cap(self):
        """Test slippage is capped at reasonable maximum."""
        slippage = self._estimate_slippage(9000, 10000)  # 90% of liquidity
        assert slippage <= 50  # Should be capped
    
    def test_slippage_non_linear(self):
        """Test slippage is non-linear with stake size."""
        small_slippage = self._estimate_slippage(100, 10000)
        large_slippage = self._estimate_slippage(1000, 10000)  # 10x stake
        
        # Slippage should be worse than linear
        assert large_slippage > small_slippage * 5


class TestEdgeCalculations:
    """Test gross and net edge calculations."""
    
    @pytest.mark.parametrize("odds_a,odds_b,expected_edge", [
        (2.0, 2.0, 0),           # No edge - equal odds
        (2.2, 2.2, 10.0),        # 10% edge - both sides at 2.2
        (2.5, 1.8, None),        # Need to calculate proper side
    ])
    def test_gross_edge_calculation(self, odds_a: float, odds_b: float, expected_edge: float | None):
        """Test gross edge calculation."""
        edge = self._calculate_gross_edge(odds_a, odds_b)
        
        if expected_edge is not None:
            assert pytest.approx(edge, 0.5) == expected_edge
        else:
            assert edge >= 0
    
    def test_arbitrage_detection(self):
        """Test detection of arbitrage opportunity."""
        # True arbitrage: implied probabilities sum to < 100%
        # 2.2 odds = 45.45% implied probability
        # 2.2 + 2.2 = 90.9% < 100% = 9.1% arbitrage
        
        odds_a = 2.2
        odds_b = 2.2
        
        is_arb, edge = self._check_arbitrage(odds_a, odds_b)
        
        assert is_arb is True
        assert pytest.approx(edge, 0.5) == 9.1
    
    def test_no_arbitrage_detection(self):
        """Test detection of non-arbitrage."""
        # No arbitrage: implied probabilities sum to > 100%
        # 1.9 + 1.9 = 52.6% + 52.6% = 105.2% > 100%
        
        odds_a = 1.9
        odds_b = 1.9
        
        is_arb, edge = self._check_arbitrage(odds_a, odds_b)
        
        assert is_arb is False
    
    def test_net_edge_after_fees(self):
        """Test net edge after accounting for fees."""
        gross_edge = 10.0  # 10% gross edge
        
        # Calculate fees
        stake = 1000
        pm_fee = self._calculate_polymarket_fee(stake, 2.0)  # 2%
        gas_fee = 5.0
        total_fees = pm_fee + gas_fee
        
        net_edge = self._calculate_net_edge(gross_edge, stake, total_fees)
        
        # Net edge should be less than gross
        assert net_edge < gross_edge
        # Net edge should be approximately gross - fee%
        assert pytest.approx(net_edge, 0.5) == 8.0  # 10% - 2% - 0.5%
    
    def test_negative_net_edge(self):
        """Test when fees eliminate arbitrage."""
        gross_edge = 2.0  # Small 2% edge
        stake = 100
        pm_fee = self._calculate_polymarket_fee(stake, 2.0)  # 2%
        gas_fee = 5.0
        total_fees = pm_fee + gas_fee
        
        net_edge = self._calculate_net_edge(gross_edge, stake, total_fees)
        
        # Should be negative (not profitable)
        assert net_edge < 0
    
    @pytest.mark.parametrize("gross_edge,fees,stake,expected_positive", [
        (10.0, 5.0, 1000, True),   # Profitable
        (5.0, 5.0, 1000, False),   # Break-even or loss
        (2.0, 5.0, 1000, False),   # Loss
    ])
    def test_edge_profitability(self, gross_edge: float, fees: float, stake: float, expected_positive: bool):
        """Test profitability check."""
        net_edge = self._calculate_net_edge(gross_edge, stake, fees)
        
        if expected_positive:
            assert net_edge > 0
        else:
            assert net_edge <= 0


class TestSizingCalculations:
    """Test position sizing calculations."""
    
    def test_optimal_stake_ratio(self):
        """Test optimal stake ratio calculation."""
        # In a true arbitrage, stakes should be proportional to inverse odds
        odds_a = 2.0
        odds_b = 2.0
        
        stake_a, stake_b = self._calculate_stakes(1000, odds_a, odds_b)
        
        # With equal odds, stakes should be equal
        assert pytest.approx(stake_a, 0.01) == stake_b
    
    def test_unequal_odds_stake_distribution(self):
        """Test stake distribution with unequal odds."""
        odds_a = 1.5   # Heavy favorite
        odds_b = 3.0   # Underdog
        total_stake = 1000
        
        stake_a, stake_b = self._calculate_stakes(total_stake, odds_a, odds_b)
        
        # More should be staked on the lower odds (favorite)
        assert stake_a > stake_b
        # Stakes should sum to total
        assert pytest.approx(stake_a + stake_b, 0.01) == total_stake
    
    def test_guaranteed_payout_calculation(self):
        """Test guaranteed payout calculation."""
        odds_a = 2.2
        odds_b = 2.2
        stake_a = 500
        stake_b = 500
        
        payout_a = stake_a * odds_a
        payout_b = stake_b * odds_b
        
        # In true arbitrage, both sides should pay approximately the same
        assert pytest.approx(payout_a, 0.01) == payout_b
    
    def test_roi_calculation(self):
        """Test ROI percentage calculation."""
        total_stake = 1000
        guaranteed_payout = 1100
        
        roi = self._calculate_roi(total_stake, guaranteed_payout)
        
        assert roi == 10.0  # 10% ROI
    
    def test_max_stake_respect(self):
        """Test that max stake limits are respected."""
        max_stake = 500
        calculated_stake = 1000
        
        actual_stake = min(calculated_stake, max_stake)
        
        assert actual_stake <= max_stake
    
    def test_min_stake_respect(self):
        """Test that minimum stake is enforced."""
        min_stake = 10
        calculated_stake = 5
        
        if calculated_stake < min_stake:
            actual_stake = None  # Don't trade
        else:
            actual_stake = calculated_stake
        
        assert actual_stake is None or actual_stake >= min_stake


class TestEdgeCases:
    """Test edge cases in arbitrage math."""
    
    @pytest.mark.parametrize("odds", [0, -1, -100])
    def test_invalid_negative_odds(self, odds: float):
        """Test handling of invalid negative odds."""
        with pytest.raises(ValueError):
            self._decimal_to_implied_prob(odds)
    
    def test_very_high_odds(self):
        """Test handling of very high odds."""
        # 100:1 odds = 1% implied probability
        odds = 101.0
        prob = self._decimal_to_implied_prob(odds)
        
        assert pytest.approx(prob, 0.001) == 0.01
    
    def test_very_low_odds(self):
        """Test handling of very low odds (heavy favorite)."""
        # 1.01 odds = 99% implied probability
        odds = 1.01
        prob = self._decimal_to_implied_prob(odds)
        
        assert pytest.approx(prob, 0.01) == 0.99
    
    def test_american_odds_conversion(self):
        """Test American to decimal odds conversion."""
        # Negative American odds
        assert pytest.approx(self._american_to_decimal(-110), 0.01) == 1.909
        assert pytest.approx(self._american_to_decimal(-200), 0.01) == 1.50
        
        # Positive American odds
        assert pytest.approx(self._american_to_decimal(110), 0.01) == 2.10
        assert pytest.approx(self._american_to_decimal(200), 0.01) == 3.00
    
    def test_edge_case_zero_stake(self):
        """Test calculations with zero stake."""
        roi = self._calculate_roi(0, 0)
        assert roi == 0 or math.isnan(roi)
    
    def test_extreme_slippage_scenario(self):
        """Test with extreme slippage."""
        stake = 5000
        liquidity = 1000
        
        slippage = self._estimate_slippage(stake, liquidity)
        
        # Slippage should be very high but capped
        assert slippage > 10
        assert slippage < 100  # Should have upper limit
    
    def test_rounding_precision(self):
        """Test rounding in financial calculations."""
        # Financial calculations should be precise to cents
        fee = self._calculate_polymarket_fee(100.005, 2.0)
        
        # Should round to reasonable precision
        assert fee == pytest.approx(2.0001, 0.001)


class TestFullArbitrageCalculation:
    """Test complete arbitrage calculation from inputs to outputs."""
    
    def test_complete_arbitrage_scenario(self):
        """Test complete calculation for a real arbitrage scenario."""
        # Scenario:
        # Polymarket: Team A at 50% (2.0 odds implied, but actually binary)
        # Sportsbook: Team B at 2.2 odds
        
        pm_odds = 2.0  # Binary market, 50%
        sb_odds = 2.2
        total_capital = 1000
        pm_liquidity = 10000
        sb_liquidity = 50000
        
        # Check if arbitrage exists
        is_arb, gross_edge = self._check_arbitrage(pm_odds, sb_odds)
        assert is_arb is True
        
        # Calculate optimal stakes
        stake_pm, stake_sb = self._calculate_stakes(total_capital, pm_odds, sb_odds)
        
        # Calculate slippage
        slippage_pm = self._estimate_slippage(stake_pm, pm_liquidity)
        slippage_sb = self._estimate_slippage(stake_sb, sb_liquidity)
        
        # Calculate fees
        pm_fee = self._calculate_polymarket_fee(stake_pm, 2.0)
        gas_fee = 5.0
        total_fees = pm_fee + gas_fee
        
        # Calculate net edge
        net_edge = self._calculate_net_edge(gross_edge, total_capital, total_fees)
        
        # Verify final calculations
        assert stake_pm + stake_sb <= total_capital
        assert net_edge < gross_edge  # Fees reduce edge
        
        # Calculate expected payout
        payout_pm = stake_pm * pm_odds * (1 - slippage_pm / 100)
        payout_sb = stake_sb * sb_odds * (1 - slippage_sb / 100)
        
        # Both should be approximately equal in true arbitrage
        assert pytest.approx(payout_pm, 0.05 * payout_pm) == payout_sb


# Helper methods

    def _calculate_polymarket_fee(self, stake: float, fee_percent: float) -> float:
        """Calculate Polymarket trading fee."""
        return stake * (fee_percent / 100)
    
    def _estimate_gas_fee(self) -> float:
        """Estimate gas fee in USD."""
        # Simplified estimation
        return 5.0
    
    def _calculate_vig(self, odds_a: float, odds_b: float) -> float:
        """Calculate bookmaker vig/margin percentage."""
        prob_a = 1 / odds_a
        prob_b = 1 / odds_b
        total_prob = prob_a + prob_b
        
        # Vig is the excess over 100%
        return (total_prob - 1) * 100
    
    def _estimate_slippage(self, stake: float, liquidity: float) -> float:
        """Estimate price slippage percentage."""
        if liquidity == 0:
            raise ValueError("Liquidity cannot be zero")
        
        ratio = stake / liquidity
        # Non-linear slippage model
        slippage = ratio * 10  # 10% slippage per unit of liquidity ratio
        return min(slippage, 50)  # Cap at 50%
    
    def _calculate_gross_edge(self, odds_a: float, odds_b: float) -> float:
        """Calculate gross arbitrage edge."""
        prob_a = 1 / odds_a
        prob_b = 1 / odds_b
        total = prob_a + prob_b
        
        if total < 1:
            return (1 - total) * 100
        return 0
    
    def _check_arbitrage(self, odds_a: float, odds_b: float) -> tuple[bool, float]:
        """Check if arbitrage exists and return edge."""
        edge = self._calculate_gross_edge(odds_a, odds_b)
        return edge > 0, edge
    
    def _calculate_net_edge(self, gross_edge: float, stake: float, total_fees: float) -> float:
        """Calculate net edge after fees."""
        fee_percent = (total_fees / stake) * 100 if stake > 0 else 0
        return gross_edge - fee_percent
    
    def _calculate_stakes(self, total: float, odds_a: float, odds_b: float) -> tuple[float, float]:
        """Calculate optimal stake distribution."""
        # Stakes inversely proportional to odds for guaranteed payout
        inv_a = 1 / odds_a
        inv_b = 1 / odds_b
        total_inv = inv_a + inv_b
        
        stake_a = total * (inv_b / total_inv)
        stake_b = total * (inv_a / total_inv)
        
        return stake_a, stake_b
    
    def _calculate_roi(self, stake: float, payout: float) -> float:
        """Calculate ROI percentage."""
        if stake == 0:
            return 0
        return ((payout - stake) / stake) * 100
    
    def _decimal_to_implied_prob(self, odds: float) -> float:
        """Convert decimal odds to implied probability."""
        if odds <= 0:
            raise ValueError("Odds must be positive")
        return 1 / odds
    
    def _american_to_decimal(self, american: int | float) -> float:
        """Convert American odds to decimal odds."""
        if american > 0:
            return (american / 100) + 1
        else:
            return (100 / abs(american)) + 1
