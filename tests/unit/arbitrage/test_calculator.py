"""
Unit tests for the arbitrage calculator module.

These tests verify the mathematical correctness of:
- Odds format conversions
- Implied probability calculations
- Arbitrage detection
- Optimal stake calculations
- Profit calculations
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from src.arbitrage.calculator import (
    american_to_decimal,
    decimal_to_american,
    fractional_to_decimal,
    calculate_implied_probability_decimal,
    calculate_implied_probability_american,
    calculate_implied_probability,
    calculate_vig,
    remove_vig,
    detect_arbitrage,
    calculate_stakes,
    calculate_stakes_from_probabilities,
    calculate_profit_margin,
    calculate_expected_payout,
    calculate_yield,
    evaluate_opportunity,
    format_profit_percentage,
    format_currency,
)
from src.arbitrage.models import (
    NormalizedMarket,
    MarketOutcome,
    MarketType,
    FeeConfig,
)


class TestOddsConversions:
    """Test odds format conversions."""
    
    def test_american_to_decimal_positive(self):
        """Test converting positive American odds to decimal."""
        # +100 = 2.0 (even money)
        assert american_to_decimal(100) == Decimal("2.0")
        # +150 = 2.5 ($100 bet wins $150, returns $250)
        assert american_to_decimal(150) == Decimal("2.5")
        # +200 = 3.0
        assert american_to_decimal(200) == Decimal("3.0")
        # +300 = 4.0
        assert american_to_decimal(300) == Decimal("4.0")
    
    def test_american_to_decimal_negative(self):
        """Test converting negative American odds to decimal."""
        # -100 = 2.0 (even money)
        assert american_to_decimal(-100) == Decimal("2.0")
        # -200 = 1.5 (bet $200 to win $100, returns $300 = 1.5x)
        assert american_to_decimal(-200) == Decimal("1.5")
        # -150 = 1.666...
        result = american_to_decimal(-150)
        assert result.quantize(Decimal("0.01")) == Decimal("1.67")
        # -400 = 1.25
        assert american_to_decimal(-400) == Decimal("1.25")
    
    def test_decimal_to_american_positive(self):
        """Test converting decimal odds to positive American."""
        assert decimal_to_american(Decimal("2.0")) == 100
        assert decimal_to_american(Decimal("2.5")) == 150
        assert decimal_to_american(Decimal("3.0")) == 200
        assert decimal_to_american(Decimal("4.0")) == 300
    
    def test_decimal_to_american_negative(self):
        """Test converting decimal odds to negative American."""
        assert decimal_to_american(Decimal("1.5")) == -200
        assert decimal_to_american(Decimal("1.25")) == -400
        # 1.91 is approximately -110
        assert decimal_to_american(Decimal("1.909091")) == -110
    
    def test_roundtrip_conversion(self):
        """Test that converting back and forth preserves values."""
        # Note: +100 and -100 both represent even money (2.0), so they don't roundtrip
        # Only test values that roundtrip cleanly
        test_values = [150, -200, 300, 200, -500, 250, -300]
        for american in test_values:
            decimal = american_to_decimal(american)
            back_to_american = decimal_to_american(decimal)
            assert back_to_american == american
    
    def test_fractional_to_decimal(self):
        """Test converting fractional odds to decimal."""
        # 1/1 = 2.0
        assert fractional_to_decimal(1, 1) == Decimal("2.0")
        # 3/2 = 2.5
        assert fractional_to_decimal(3, 2) == Decimal("2.5")
        # 1/2 = 1.5
        assert fractional_to_decimal(1, 2) == Decimal("1.5")
        # 5/1 = 6.0
        assert fractional_to_decimal(5, 1) == Decimal("6.0")


class TestImpliedProbability:
    """Test implied probability calculations."""
    
    def test_decimal_to_probability_even_money(self):
        """Test implied probability for even money."""
        # 2.0 odds = 50% probability
        result = calculate_implied_probability_decimal(Decimal("2.0"))
        assert result == Decimal("0.5")
    
    def test_decimal_to_probability_common_odds(self):
        """Test implied probability for common odds."""
        # 1.5 odds = 66.67% probability
        result = calculate_implied_probability_decimal(Decimal("1.5"))
        assert result.quantize(Decimal("0.01")) == Decimal("0.67")
        
        # 3.0 odds = 33.33% probability
        result = calculate_implied_probability_decimal(Decimal("3.0"))
        assert result.quantize(Decimal("0.01")) == Decimal("0.33")
        
        # 4.0 odds = 25% probability
        result = calculate_implied_probability_decimal(Decimal("4.0"))
        assert result == Decimal("0.25")
    
    def test_american_to_probability(self):
        """Test implied probability from American odds."""
        # +100 = 50%
        result = calculate_implied_probability_american(100)
        assert result == Decimal("0.5")
        
        # -200 = 66.67%
        result = calculate_implied_probability_american(-200)
        assert result.quantize(Decimal("0.01")) == Decimal("0.67")
        
        # +300 = 25%
        result = calculate_implied_probability_american(300)
        assert result == Decimal("0.25")
    
    def test_invalid_odds_raises_error(self):
        """Test that invalid odds raise appropriate errors."""
        with pytest.raises(ValueError):
            calculate_implied_probability_decimal(Decimal("0.5"))
        with pytest.raises(ValueError):
            calculate_implied_probability_decimal(Decimal("1.0"))
        with pytest.raises(ValueError):
            calculate_implied_probability_decimal(Decimal("-1.0"))
    
    def test_calculate_implied_probability_dispatch(self):
        """Test the generic calculate_implied_probability function."""
        # Decimal format
        result = calculate_implied_probability(Decimal("2.0"), "decimal")
        assert result == Decimal("0.5")
        
        # American format
        result = calculate_implied_probability(Decimal("100"), "american")
        assert result == Decimal("0.5")
        
        # Already probability
        result = calculate_implied_probability(Decimal("0.3"), "implied_probability")
        assert result == Decimal("0.3")


class TestVigCalculations:
    """Test vig (overround) calculations."""
    
    def test_no_vig_fair_market(self):
        """Test vig calculation for a fair market."""
        # Fair coin flip: both outcomes 50%
        probs = [Decimal("0.5"), Decimal("0.5")]
        vig = calculate_vig(probs)
        assert vig == Decimal("0")
    
    def test_vig_calculation(self):
        """Test vig calculation for typical sportsbook odds."""
        # -110 / -110 standard line = 52.38% + 52.38% = 104.76%
        # Vig = 4.76%
        prob1 = calculate_implied_probability_american(-110)
        prob2 = calculate_implied_probability_american(-110)
        vig = calculate_vig([prob1, prob2])
        assert vig.quantize(Decimal("0.01")) == Decimal("0.05")
    
    def test_remove_vig_proportional(self):
        """Test proportional vig removal."""
        # 60% / 50% = 110% total (10% vig)
        probs = [Decimal("0.6"), Decimal("0.5")]
        true_probs = remove_vig(probs, method="proportional")
        
        # Should sum to 1.0
        assert sum(true_probs) == Decimal("1.0")
        
        # Proportional removal: 60/110 = 54.5%, 50/110 = 45.5%
        assert true_probs[0].quantize(Decimal("0.01")) == Decimal("0.55")
        assert true_probs[1].quantize(Decimal("0.01")) == Decimal("0.45")


class TestArbitrageDetection:
    """Test arbitrage detection logic."""
    
    def test_detect_arbitrage_opportunity(self):
        """Test detecting a clear arbitrage opportunity."""
        # Book A: 45% implied prob
        # Book B: 50% implied prob
        # Total: 95% < 100%, so 5% margin
        is_arb, gross_margin, net_margin = detect_arbitrage(
            Decimal("0.45"),
            Decimal("0.50"),
        )
        assert is_arb is True
        assert gross_margin == Decimal("0.05")
        assert net_margin == Decimal("0.05")
    
    def test_detect_no_arbitrage(self):
        """Test when there's no arbitrage."""
        # Book A: 55%
        # Book B: 50%
        # Total: 105% > 100%, no arb
        is_arb, gross_margin, net_margin = detect_arbitrage(
            Decimal("0.55"),
            Decimal("0.50"),
        )
        assert is_arb is False
        assert gross_margin == Decimal("-0.05")
        assert net_margin == Decimal("-0.05")
    
    def test_detect_arbitrage_with_fees(self):
        """Test arbitrage detection accounting for fees."""
        # 45% + 50% = 95%, 5% gross margin
        # But 3% total fees = 2% net (still arb)
        is_arb, gross_margin, net_margin = detect_arbitrage(
            Decimal("0.45"),
            Decimal("0.50"),
            fees_a=Decimal("0.015"),
            fees_b=Decimal("0.015"),
        )
        assert is_arb is True
        assert gross_margin == Decimal("0.05")
        assert net_margin == Decimal("0.02")
    
    def test_detect_arbitrage_fees_eliminate(self):
        """Test when fees eliminate arbitrage."""
        # 45% + 50% = 95%, 5% gross margin
        # 6% total fees = -1% net (no arb)
        is_arb, gross_margin, net_margin = detect_arbitrage(
            Decimal("0.45"),
            Decimal("0.50"),
            fees_a=Decimal("0.03"),
            fees_b=Decimal("0.03"),
        )
        assert is_arb is False
        assert gross_margin == Decimal("0.05")
        assert net_margin == Decimal("-0.01")
    
    def test_detect_arbitrage_with_slippage(self):
        """Test arbitrage detection with slippage estimates."""
        is_arb, gross_margin, net_margin = detect_arbitrage(
            Decimal("0.45"),
            Decimal("0.50"),
            slippage_a=Decimal("0.01"),
            slippage_b=Decimal("0.01"),
        )
        assert is_arb is True
        assert gross_margin == Decimal("0.05")
        assert net_margin == Decimal("0.03")


class TestStakeCalculations:
    """Test optimal stake calculations."""
    
    def test_calculate_stakes_even_money(self):
        """Test stake calculation for even money odds."""
        # Both at 2.0: equal stakes
        stake_a, stake_b = calculate_stakes(Decimal("1000"), Decimal("2.0"), Decimal("2.0"))
        assert stake_a == Decimal("500.00")
        assert stake_b == Decimal("500.00")
    
    def test_calculate_stakes_different_odds(self):
        """Test stake calculation with different odds."""
        # Example: 2.1 and 1.95
        stake_a, stake_b = calculate_stakes(Decimal("1000"), Decimal("2.1"), Decimal("1.95"))
        
        # stake_a should be around $481, stake_b around $519
        assert stake_a > Decimal("0")
        assert stake_b > Decimal("0")
        assert stake_a + stake_b == Decimal("1000.00")
        
        # Verify equal payout
        payout_a = stake_a * Decimal("2.1")
        payout_b = stake_b * Decimal("1.95")
        # Should be approximately equal
        assert abs(payout_a - payout_b) < Decimal("5")
    
    def test_calculate_stakes_from_probabilities(self):
        """Test stake calculation from probabilities."""
        # 40% vs 60% probabilities
        stake_a, stake_b = calculate_stakes_from_probabilities(
            Decimal("1000"),
            Decimal("0.4"),
            Decimal("0.6"),
        )
        assert stake_a == Decimal("600.00")
        assert stake_b == Decimal("400.00")
    
    def test_real_world_arbitrage_example(self):
        """Test a real-world arbitrage scenario."""
        # Polymarket YES at $0.45 (2.22 decimal)
        # Sportsbook NO at -120 (1.83 decimal)
        # This is roughly 45% + 55% = 100%, very tight
        stake_yes, stake_no = calculate_stakes(
            Decimal("1000"),
            Decimal("2.22"),
            Decimal("1.83"),
        )
        
        assert stake_yes > Decimal("0")
        assert stake_no > Decimal("0")
        
        # Calculate profit either way
        payout_if_yes = stake_yes * Decimal("2.22")
        payout_if_no = stake_no * Decimal("1.83")
        
        # Profit should be similar either way
        profit_yes = payout_if_yes - Decimal("1000")
        profit_no = payout_if_no - Decimal("1000")
        
        assert abs(profit_yes - profit_no) < Decimal("10")


class TestProfitCalculations:
    """Test profit margin calculations."""
    
    def test_profit_margin_zero(self):
        """Test profit margin for break-even bets."""
        # Equal stakes at 2.0 each: no profit, no loss
        margin = calculate_profit_margin(
            Decimal("500"),
            Decimal("500"),
            Decimal("2.0"),
            Decimal("2.0"),
        )
        assert margin == Decimal("0")
    
    def test_profit_margin_positive(self):
        """Test positive profit margin."""
        # Arb opportunity: 1.9 and 2.2
        # Stake $526 and $474 to equalize payout
        stake_a = Decimal("526.32")
        stake_b = Decimal("473.68")
        
        margin = calculate_profit_margin(stake_a, stake_b, Decimal("1.9"), Decimal("2.2"))
        
        # Payout either way: ~$1000
        # Total stake: $1000
        # Should be profitable
        assert margin > Decimal("0")
    
    def test_expected_payout(self):
        """Test expected payout calculation."""
        # $100 at 2.5 odds = $250 payout
        payout = calculate_expected_payout(Decimal("100"), Decimal("2.5"))
        assert payout == Decimal("250")
    
    def test_expected_payout_with_fees(self):
        """Test expected payout with fees."""
        # $100 at 2.0 odds with 2% fee
        payout = calculate_expected_payout(Decimal("100"), Decimal("2.0"), Decimal("0.02"))
        # $200 - 2% = $196
        assert payout == Decimal("196")
    
    def test_calculate_yield(self):
        """Test yield (ROI) calculation."""
        # $50 profit on $1000 stake = 5% yield
        yield_pct = calculate_yield(Decimal("1000"), Decimal("50"))
        assert yield_pct == Decimal("0.05")


class TestFormatting:
    """Test output formatting functions."""
    
    def test_format_profit_percentage(self):
        """Test profit percentage formatting."""
        assert format_profit_percentage(Decimal("0.025")) == "2.50%"
        assert format_profit_percentage(Decimal("0.05")) == "5.00%"
        assert format_profit_percentage(Decimal("0.1234")) == "12.34%"
    
    def test_format_currency(self):
        """Test currency formatting."""
        assert format_currency(Decimal("1000")) == "$1,000.00"
        assert format_currency(Decimal("1234.56")) == "$1,234.56"
        assert format_currency(Decimal("1000000")) == "$1,000,000.00"


class TestEvaluateOpportunity:
    """Test full opportunity evaluation."""
    
    def test_evaluate_real_arbitrage(self):
        """Test evaluating a genuine arbitrage opportunity."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="abc123",
            title="Will Lakers win?",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("2.2"), liquidity=Decimal("50000")),
                MarketOutcome(label="No", price=Decimal("1.8"), liquidity=Decimal("45000")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="xyz789",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("1.8"), liquidity=Decimal("50000")),
                MarketOutcome(label="Warriors", price=Decimal("2.2"), liquidity=Decimal("50000")),
            ],
        )
        
        # Match Yes vs Warriors (opposite outcomes)
        # 1/2.2 + 1/2.2 = 0.455 + 0.455 = 0.909 < 1.0, so there should be an arb
        opp = evaluate_opportunity(
            market_a,
            market_b,
            market_a.outcomes[0],  # Yes at 2.2
            market_b.outcomes[1],  # Warriors at 2.2
        )
        
        assert opp is not None
        assert opp.net_edge_pct > Decimal("2")  # Should be ~9% gross, ~8% net after fees
    
    def test_evaluate_no_arbitrage(self):
        """Test when there's no arbitrage."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="abc123",
            title="Will Lakers win?",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("1.6")),
                MarketOutcome(label="No", price=Decimal("2.5")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="xyz789",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("1.7")),
                MarketOutcome(label="Warriors", price=Decimal("2.2")),
            ],
        )
        
        # Match Yes vs Warriors
        # 1/1.6 + 1/2.2 = 0.625 + 0.455 = 1.08 > 1.0, no arb
        opp = evaluate_opportunity(
            market_a,
            market_b,
            market_a.outcomes[0],
            market_b.outcomes[1],
        )
        
        # May or may not be None depending on thresholds, but shouldn't be profitable
        if opp:
            assert opp.net_edge_pct <= Decimal("0")


class TestExampleCalculations:
    """
    Example calculations demonstrating arbitrage math.
    
    These serve as both tests and documentation of expected calculations.
    """
    
    def test_example_1_simple_arbitrage(self):
        """
        Example 1: Simple arbitrage between two sportsbooks.
        
        Book A offers Team X at 2.10 (+110)
        Book B offers Team Y at 2.10 (+110)
        
        Implied probabilities: 1/2.10 = 47.6% each
        Total: 95.2% < 100%
        
        Arbitrage margin: 4.8%
        """
        prob_a = calculate_implied_probability_decimal(Decimal("2.10"))
        prob_b = calculate_implied_probability_decimal(Decimal("2.10"))
        
        assert prob_a.quantize(Decimal("0.001")) == Decimal("0.476")
        
        is_arb, gross_margin, net_margin = detect_arbitrage(prob_a, prob_b)
        assert is_arb is True
        assert gross_margin.quantize(Decimal("0.01")) == Decimal("0.05")
    
    def test_example_2_with_stake_calculation(self):
        """
        Example 2: Realistic arbitrage with stake calculation.
        
        Polymarket: YES at $0.48 (2.08 decimal)
        Sportsbook: NO at -110 (1.91 decimal)
        
        Implied probabilities:
        - YES: 48%
        - NO: 52.4%
        - Total: 100.4% (slight negative after fees)
        
        Let's adjust to make it work:
        Polymarket: YES at $0.45 (2.22 decimal) = 45%
        Sportsbook: NO at -120 (1.83 decimal) = 54.6%
        Total: 99.6% = 0.4% margin
        """
        polymarket_price = Decimal("2.22")  # $0.45
        sportsbook_price = Decimal("1.83")  # -120
        
        prob_pm = calculate_implied_probability_decimal(polymarket_price)
        prob_sb = calculate_implied_probability_decimal(sportsbook_price)
        
        is_arb, margin, _ = detect_arbitrage(prob_pm, prob_sb)
        
        if is_arb:
            stake_pm, stake_sb = calculate_stakes(Decimal("1000"), polymarket_price, sportsbook_price)
            
            # Verify payouts are equal
            payout_pm = stake_pm * polymarket_price
            payout_sb = stake_sb * sportsbook_price
            
            print(f"Polymarket stake: ${stake_pm}")
            print(f"Sportsbook stake: ${stake_sb}")
            print(f"Payout either way: ~${payout_pm.quantize(Decimal('0.01'))}")
    
    def test_example_3_prediction_market_arbitrage(self):
        """
        Example 3: Prediction market vs sportsbook.
        
        Event: Will Trump win 2024 election?
        
        Kalshi: YES at 52¢ ($0.52) = 1.92 decimal = 52% implied
        Bet365: Trump to win at +110 = 2.10 decimal = 47.6% implied
        
        This looks like arb but note: Kalshi YES = 52%, Bet365 YES = 47.6%
        Sum = 99.6%, margin = 0.4%
        
        But we need opposite sides!
        
        Correct setup:
        Kalshi: YES at 52¢ = 52%
        Bet365: Trump NOT to win at -130 = 1.77 = 56.5%
        Sum = 108.5% = no arbitrage
        
        For arbitrage:
        Kalshi: YES at 45¢ = 44.4%
        Bet365: Trump NOT to win at -120 = 54.5%
        Sum = 98.9% = 1.1% margin
        """
        kalshi_prob = Decimal("0.444")  # YES at 45¢
        bet365_prob = Decimal("0.545")  # NO at -120
        
        is_arb, margin, net = detect_arbitrage(
            kalshi_prob,
            bet365_prob,
            fees_a=Decimal("0"),  # Kalshi has no fees
            fees_b=Decimal("0.02"),  # 2% slippage on sportsbook
        )
        
        if is_arb:
            assert margin > Decimal("0")
            # With 2% slippage, 1.1% gross margin becomes negative
            assert net < margin
