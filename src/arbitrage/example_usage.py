"""
Example usage of the Arbitrage Detection Engine.

This script demonstrates how to use the arbitrage detection components
to find and evaluate arbitrage opportunities between sportsbooks and
prediction markets.
"""

from decimal import Decimal
from datetime import datetime, timedelta

from src.arbitrage.models import (
    NormalizedMarket,
    MarketOutcome,
    MarketType,
    ArbitrageOpportunity,
    ArbitrageLeg,
    FeeConfig,
)
from src.arbitrage.calculator import (
    calculate_implied_probability_decimal,
    detect_arbitrage,
    calculate_stakes,
    evaluate_opportunity,
    format_profit_percentage,
    format_currency,
    american_to_decimal,
    decimal_to_american,
)
from src.arbitrage.matcher import (
    EventMatcher,
    fuzzy_match_events,
    normalize_team_name,
    extract_entities,
)
from src.arbitrage.filters import (
    OpportunityFilter,
    filter_opportunity,
    OpportunityRanker,
)


def example_1_basic_arbitrage_math():
    """
    Example 1: Basic Arbitrage Math
    
    Demonstrates the core arbitrage calculation:
    - Converting odds to implied probabilities
    - Detecting when sum of inverse odds < 1.0
    - Calculating profit margin
    """
    print("=" * 60)
    print("Example 1: Basic Arbitrage Math")
    print("=" * 60)
    
    # Scenario: Lakers vs Warriors
    # Polymarket: Lakers YES at $0.48 (decimal odds = 1/0.48 = 2.083)
    # DraftKings: Warriors at +120 (decimal odds = 2.20)
    
    polymarket_odds = Decimal("2.083")  # $0.48 on Polymarket
    draftkings_odds = Decimal("2.20")   # +120 on DraftKings
    
    # Calculate implied probabilities
    prob_pm = calculate_implied_probability_decimal(polymarket_odds)
    prob_dk = calculate_implied_probability_decimal(draftkings_odds)
    
    print(f"\nPolymarket Odds: {polymarket_odds} (${float(1/polymarket_odds):.2f})")
    print(f"  Implied Probability: {float(prob_pm)*100:.2f}%")
    
    print(f"\nDraftKings Odds: {draftkings_odds} (+{int((draftkings_odds-1)*100)})")
    print(f"  Implied Probability: {float(prob_dk)*100:.2f}%")
    
    # Detect arbitrage
    is_arb, gross_margin, net_margin = detect_arbitrage(prob_pm, prob_dk)
    
    print(f"\nTotal Probability: {float(prob_pm + prob_dk)*100:.2f}%")
    print(f"Gross Margin: {float(gross_margin)*100:.2f}%")
    
    if is_arb:
        print(f"✓ ARBITRAGE DETECTED!")
        
        # Calculate stakes for $1000 total
        stake_pm, stake_dk = calculate_stakes(Decimal("1000"), polymarket_odds, draftkings_odds)
        
        print(f"\nOptimal Stakes (Total: $1000):")
        print(f"  Polymarket (Lakers): ${stake_pm}")
        print(f"  DraftKings (Warriors): ${stake_dk}")
        
        # Verify profit
        payout_pm = stake_pm * polymarket_odds
        payout_dk = stake_dk * draftkings_odds
        profit_pm = payout_pm - Decimal("1000")
        profit_dk = payout_dk - Decimal("1000")
        
        print(f"\nGuaranteed Payout:")
        print(f"  If Lakers win: ${payout_pm:.2f} (profit: ${profit_pm:.2f})")
        print(f"  If Warriors win: ${payout_dk:.2f} (profit: ${profit_dk:.2f})")
    else:
        print("✗ No arbitrage opportunity")
    
    print()


def example_2_odds_conversions():
    """
    Example 2: Odds Format Conversions
    
    Shows how to convert between American, Decimal, and Implied Probability.
    """
    print("=" * 60)
    print("Example 2: Odds Format Conversions")
    print("=" * 60)
    
    test_odds = [+150, -200, +300, -110, +500, -500]
    
    print("\n{:<15} {:<15} {:<20}".format("American", "Decimal", "Implied Prob"))
    print("-" * 50)
    
    for american in test_odds:
        decimal = american_to_decimal(american)
        prob = calculate_implied_probability_decimal(decimal)
        
        print("{:<+15} {:<15.3f} {:<19.2%}".format(american, float(decimal), float(prob)))
    
    print()


def example_3_event_matching():
    """
    Example 3: Event Matching
    
    Demonstrates fuzzy matching of events across different sources.
    """
    print("=" * 60)
    print("Example 3: Event Matching")
    print("=" * 60)
    
    # Create example markets
    polymarket_market = NormalizedMarket(
        source="polymarket",
        source_event_id="pm-123",
        title="Will Lakers defeat Warriors on Jan 15?",
        market_type=MarketType.BINARY,
        category="nba",
        start_time=datetime(2024, 1, 15, 20, 0, 0),
        outcomes=[
            MarketOutcome(label="Yes", price=Decimal("2.1")),
            MarketOutcome(label="No", price=Decimal("1.9")),
        ],
        url="https://polymarket.com/market/lakers-warriors",
    )
    
    draftkings_market = NormalizedMarket(
        source="draftkings",
        source_event_id="dk-456",
        title="Lakers @ Warriors",
        market_type=MarketType.BINARY,
        category="nba",
        start_time=datetime(2024, 1, 15, 20, 0, 0),
        outcomes=[
            MarketOutcome(label="Lakers", price=Decimal("2.05")),
            MarketOutcome(label="Warriors", price=Decimal("1.95")),
        ],
        url="https://draftkings.com/sportsbook/nba/lakers-warriors",
    )
    
    # Show entity extraction
    print("\nEntity Extraction:")
    print(f"  Polymarket: {extract_entities(polymarket_market.title)}")
    print(f"  DraftKings: {extract_entities(draftkings_market.title)}")
    
    # Perform fuzzy matching
    result = fuzzy_match_events(polymarket_market, draftkings_market)
    
    print(f"\nMatch Result:")
    print(f"  Is Match: {result.is_match}")
    print(f"  Score: {float(result.score):.2%}")
    print(f"  Title Similarity: {float(result.title_similarity):.2%}")
    print(f"  Entity Overlap: {float(result.entity_overlap):.2%}")
    print(f"  Time Proximity: {result.time_proximity_hours:.1f} hours")
    print(f"  Reasons: {result.reasons}")
    
    # Use EventMatcher class
    print("\nUsing EventMatcher:")
    matcher = EventMatcher(min_match_score=Decimal("0.70"))
    match = matcher.match(polymarket_market, draftkings_market)
    
    if match.status == "matched":
        print(f"  ✓ Matched with score: {float(match.match_score):.2%}")
        print(f"  Resolution confidence: {float(match.resolution_confidence):.2%}")
    else:
        print(f"  ✗ Rejected: {match.rejection_reason}")
    
    print()


def example_4_opportunity_evaluation():
    """
    Example 4: Full Opportunity Evaluation
    
    Shows the complete flow from markets to evaluated opportunity.
    """
    print("=" * 60)
    print("Example 4: Full Opportunity Evaluation")
    print("=" * 60)
    
    # Create markets with an arbitrage opportunity
    polymarket = NormalizedMarket(
        source="polymarket",
        source_event_id="pm-789",
        title="Trump wins 2024 election?",
        market_type=MarketType.BINARY,
        category="politics",
        start_time=datetime(2024, 11, 5, 0, 0, 0),
        outcomes=[
            MarketOutcome(label="Yes", price=Decimal("2.22"), liquidity=Decimal("50000")),
            MarketOutcome(label="No", price=Decimal("1.82"), liquidity=Decimal("45000")),
        ],
        url="https://polymarket.com/market/trump-2024",
        last_updated=datetime.utcnow(),
    )
    
    kalshi = NormalizedMarket(
        source="kalshi",
        source_event_id="k-101",
        title="Trump to win 2024 Presidential Election",
        market_type=MarketType.BINARY,
        category="politics",
        start_time=datetime(2024, 11, 5, 0, 0, 0),
        outcomes=[
            MarketOutcome(label="Yes", price=Decimal("1.85"), liquidity=Decimal("30000")),
            MarketOutcome(label="No", price=Decimal("2.17"), liquidity=Decimal("28000")),
        ],
        url="https://kalshi.com/markets/trump-2024",
        last_updated=datetime.utcnow(),
    )
    
    # Evaluate opportunity: Polymarket YES vs Kalshi NO
    opp = evaluate_opportunity(
        polymarket,
        kalshi,
        polymarket.outcomes[0],  # YES at 2.22
        kalshi.outcomes[1],      # NO at 2.17
    )
    
    if opp:
        print(f"\n✓ Arbitrage Opportunity Found!")
        print(f"\nEvent: {opp.event_title}")
        print(f"\nLeg 1:")
        print(f"  Source: {opp.left_leg.source}")
        print(f"  Side: {opp.left_leg.side}")
        print(f"  Price: {opp.left_leg.price} ({opp.left_leg.american_odds:+d})")
        print(f"  Liquidity: ${opp.left_leg.liquidity:,.0f}")
        
        print(f"\nLeg 2:")
        print(f"  Source: {opp.right_leg.source}")
        print(f"  Side: {opp.right_leg.side}")
        print(f"  Price: {opp.right_leg.price} ({opp.right_leg.american_odds:+d})")
        print(f"  Liquidity: ${opp.right_leg.liquidity:,.0f}")
        
        print(f"\nProfitability:")
        print(f"  Gross Edge: {format_profit_percentage(opp.gross_edge_pct / 100)}")
        print(f"  Fees: {format_profit_percentage(opp.fees_pct / 100)}")
        print(f"  Slippage: {format_profit_percentage(opp.slippage_pct / 100)}")
        print(f"  Net Edge: {format_profit_percentage(opp.net_edge_pct / 100)}")
        
        print(f"\nStaking:")
        print(f"  Max Stake: {format_currency(opp.max_stake)}")
        print(f"  Expected Profit: {format_currency(opp.expected_profit)}")
        
        # Get recommendations
        recommendations = opp.get_stake_recommendations()
        print(f"\nProfit at Different Stakes:")
        for stake, profit in recommendations.items():
            print(f"  {format_currency(stake)} → {format_currency(profit)} profit")
        
        print(f"\nMatch Quality:")
        print(f"  Match Score: {float(opp.match_score):.1%}")
        print(f"  Resolution Confidence: {float(opp.resolution_confidence):.1%}")
        print(f"  Data Freshness: {opp.freshness_seconds}s")
        print(f"  Alertable: {opp.alertable}")
    else:
        print("\n✗ No arbitrage opportunity found")
    
    print()


def example_5_opportunity_filtering():
    """
    Example 5: Opportunity Filtering
    
    Demonstrates filtering opportunities based on various criteria.
    """
    print("=" * 60)
    print("Example 5: Opportunity Filtering")
    print("=" * 60)
    
    # Create some example opportunities
    opportunities = [
        ArbitrageOpportunity(
            event_title="High Quality Arb",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm1",
                side="Yes",
                price=Decimal("2.1"),
                liquidity=Decimal("20000"),
            ),
            right_leg=ArbitrageLeg(
                source="draftkings",
                source_event_id="dk1",
                side="No",
                price=Decimal("2.0"),
                liquidity=Decimal("30000"),
            ),
            net_edge_pct=Decimal("3.5"),
            gross_edge_pct=Decimal("4.0"),
            fees_pct=Decimal("0.3"),
            slippage_pct=Decimal("0.2"),
            match_score=Decimal("0.90"),
            resolution_confidence=Decimal("0.95"),
            freshness_seconds=30,
            expires_at=datetime.utcnow() + timedelta(hours=48),
        ),
        ArbitrageOpportunity(
            event_title="Low Profit Arb",
            left_leg=ArbitrageLeg(
                source="polymarket",
                source_event_id="pm2",
                side="Yes",
                price=Decimal("1.95"),
                liquidity=Decimal("15000"),
            ),
            right_leg=ArbitrageLeg(
                source="fanduel",
                source_event_id="fd2",
                side="No",
                price=Decimal("1.98"),
                liquidity=Decimal("20000"),
            ),
            net_edge_pct=Decimal("1.2"),  # Below threshold
            gross_edge_pct=Decimal("1.5"),
            fees_pct=Decimal("0.2"),
            slippage_pct=Decimal("0.1"),
            match_score=Decimal("0.85"),
            resolution_confidence=Decimal("0.92"),
            freshness_seconds=45,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        ),
        ArbitrageOpportunity(
            event_title="Low Liquidity Arb",
            left_leg=ArbitrageLeg(
                source="kalshi",
                source_event_id="k3",
                side="Yes",
                price=Decimal("2.5"),
                liquidity=Decimal("500"),  # Too low
            ),
            right_leg=ArbitrageLeg(
                source="bet365",
                source_event_id="b365",
                side="No",
                price=Decimal("1.71"),
                liquidity=Decimal("50000"),
            ),
            net_edge_pct=Decimal("4.5"),
            gross_edge_pct=Decimal("5.0"),
            fees_pct=Decimal("0.3"),
            slippage_pct=Decimal("0.2"),
            match_score=Decimal("0.80"),
            resolution_confidence=Decimal("0.90"),
            freshness_seconds=60,
            expires_at=datetime.utcnow() + timedelta(hours=12),
        ),
    ]
    
    # Create filter with default (moderate) settings
    filter_config = OpportunityFilter(
        min_profit_pct=Decimal("2.0"),
        min_match_score=Decimal("0.75"),
        min_liquidity_usd=Decimal("5000"),
    )
    
    print(f"\nFilter Configuration:")
    print(f"  Min Profit: {filter_config.min_profit_pct}%")
    print(f"  Min Match Score: {filter_config.min_match_score}")
    print(f"  Min Liquidity: ${filter_config.min_liquidity_usd:,.0f}")
    
    print(f"\nEvaluating {len(opportunities)} opportunities...")
    
    for opp in opportunities:
        is_valid, failures = filter_opportunity(opp, filter_config)
        
        print(f"\n{opp.event_title}:")
        print(f"  Net Edge: {opp.net_edge_pct}%")
        print(f"  Liquidity: ${opp.left_leg.liquidity:,.0f} / ${opp.right_leg.liquidity:,.0f}")
        
        if is_valid:
            print(f"  ✓ PASSED")
        else:
            print(f"  ✗ REJECTED:")
            for failure in failures:
                print(f"    - {failure}")
    
    # Use ranker to sort valid opportunities
    print("\nRanking opportunities by quality...")
    ranker = OpportunityRanker()
    ranked = ranker.rank(opportunities)
    
    print("\nRanked by Quality Score:")
    for opp, score in ranked:
        print(f"  {opp.event_title}: {float(score):.3f}")
    
    print()


def example_6_team_name_normalization():
    """
    Example 6: Team Name Normalization
    
    Shows how team names are normalized for matching.
    """
    print("=" * 60)
    print("Example 6: Team Name Normalization")
    print("=" * 60)
    
    test_names = [
        "Manchester United FC",
        "Man Utd",
        "LA Lakers",
        "Los Angeles Lakers",
        "NY Giants",
        "New York Giants",
        "Green Bay Packers",
        "GB Packers",
    ]
    
    print("\n{:<30} {:<30}".format("Original", "Normalized"))
    print("-" * 60)
    
    for name in test_names:
        normalized = normalize_team_name(name)
        print("{:<30} {:<30}".format(name, normalized))
    
    print()


def run_all_examples():
    """Run all examples."""
    examples = [
        example_1_basic_arbitrage_math,
        example_2_odds_conversions,
        example_3_event_matching,
        example_4_opportunity_evaluation,
        example_5_opportunity_filtering,
        example_6_team_name_normalization,
    ]
    
    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")
            print()


if __name__ == "__main__":
    run_all_examples()
