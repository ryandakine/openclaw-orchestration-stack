"""
Fixtures for Arb Hunter Tests

Sample data: mock Polymarket response, mock Odds API response, expected matches
"""

from datetime import datetime, timedelta
from typing import Any


# =============================================================================
# Sample Polymarket Data
# =============================================================================

def mock_polymarket_response() -> dict[str, Any]:
    """Mock Polymarket API response for NFL game."""
    return {
        "markets": [
            {
                "id": "0xabc123def456",
                "question": "Will the Chiefs win Super Bowl 2024?",
                "description": "Resolves Yes if Chiefs win, No otherwise",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=7)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.65", "0.35"],
                "volume": "1500000",
                "liquidity": "500000",
                "min_investment": "5",
                "max_investment": "5000",
                "creator_address": "0x1234567890abcdef",
                "condition_id": "cond_001",
                "token_ids": {
                    "Yes": "0x111",
                    "No": "0x222"
                },
                "created_at": (datetime.now() - timedelta(days=30)).isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "0xdef789ghi012",
                "question": "Will Eagles beat Cowboys in Week 14?",
                "description": "Resolves Yes if Eagles win",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=3)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.58", "0.42"],
                "volume": "800000",
                "liquidity": "200000",
                "min_investment": "5",
                "max_investment": "10000",
                "creator_address": "0xabcdef123456",
                "condition_id": "cond_002",
                "token_ids": {
                    "Yes": "0x333",
                    "No": "0x444"
                },
                "created_at": (datetime.now() - timedelta(days=15)).isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "0xghi345jkl678",
                "question": "NBA: Lakers vs Warriors - Will Lakers win?",
                "description": "Regular season game",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.52", "0.48"],
                "volume": "2500000",
                "liquidity": "800000",
                "min_investment": "10",
                "max_investment": "15000",
                "creator_address": "0x789abc456def",
                "condition_id": "cond_003",
                "token_ids": {
                    "Yes": "0x555",
                    "No": "0x666"
                },
                "created_at": (datetime.now() - timedelta(days=7)).isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            # Inactive market (should be filtered)
            {
                "id": "0xinactive1234",
                "question": "Closed Market Example",
                "description": "This market is closed",
                "category": "Sports",
                "active": False,
                "closed": True,
                "end_date": (datetime.now() - timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.50", "0.50"],
                "volume": "1000",
                "liquidity": "500",
                "min_investment": "5",
                "max_investment": "1000",
                "creator_address": "0xoldmarket",
                "condition_id": "cond_inactive",
                "token_ids": {"Yes": "0x000", "No": "0x999"},
                "created_at": (datetime.now() - timedelta(days=60)).isoformat(),
                "updated_at": (datetime.now() - timedelta(days=2)).isoformat(),
            },
        ]
    }


def mock_polymarket_low_liquidity() -> dict[str, Any]:
    """Polymarket market with insufficient liquidity."""
    return {
        "markets": [
            {
                "id": "0xlowliq123456",
                "question": "Will Underdog Team Win?",
                "description": "Low liquidity market",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=2)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.20", "0.80"],
                "volume": "500",
                "liquidity": "100",
                "min_investment": "5",
                "max_investment": "50",
                "creator_address": "0xlowliq",
                "condition_id": "cond_low",
                "token_ids": {"Yes": "0xlow1", "No": "0xlow2"},
                "created_at": (datetime.now() - timedelta(days=10)).isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        ]
    }


# =============================================================================
# Sample Sportsbook (Odds API) Data
# =============================================================================

def mock_odds_api_response() -> dict[str, Any]:
    """Mock The Odds API response for NFL games."""
    return {
        "id": "event_nfl_001",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "commence_time": (datetime.now() + timedelta(days=7)).isoformat(),
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
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 1.54},  # -185 American
                            {"name": "San Francisco 49ers", "price": 2.85}  # +185 American
                        ]
                    }
                ]
            },
            {
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 1.53},  # -189 American
                            {"name": "San Francisco 49ers", "price": 2.90}  # +190 American
                        ]
                    }
                ]
            },
            {
                "key": "betmgm",
                "title": "BetMGM",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Kansas City Chiefs", "price": 1.55},
                            {"name": "San Francisco 49ers", "price": 2.80}
                        ]
                    }
                ]
            }
        ]
    }


def mock_odds_api_eagles_cowboys() -> dict[str, Any]:
    """Mock Odds API for Eagles vs Cowboys."""
    return {
        "id": "event_nfl_002",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "commence_time": (datetime.now() + timedelta(days=3)).isoformat(),
        "home_team": "Dallas Cowboys",
        "away_team": "Philadelphia Eagles",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Philadelphia Eagles", "price": 1.72},  # -139 American
                            {"name": "Dallas Cowboys", "price": 2.20}  # +120 American
                        ]
                    }
                ]
            },
            {
                "key": "fanduel",
                "title": "FanDuel",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Philadelphia Eagles", "price": 1.70},
                            {"name": "Dallas Cowboys", "price": 2.25}
                        ]
                    }
                ]
            }
        ]
    }


def mock_odds_api_lakers_warriors() -> dict[str, Any]:
    """Mock Odds API for Lakers vs Warriors."""
    return {
        "id": "event_nba_001",
        "sport_key": "basketball_nba",
        "sport_title": "NBA",
        "commence_time": (datetime.now() + timedelta(days=1)).isoformat(),
        "home_team": "Los Angeles Lakers",
        "away_team": "Golden State Warriors",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": 1.92},  # -109 American
                            {"name": "Golden State Warriors", "price": 1.95}  # -105 American
                        ]
                    }
                ]
            },
            {
                "key": "betmgm",
                "title": "BetMGM",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Los Angeles Lakers", "price": 1.87},
                            {"name": "Golden State Warriors", "price": 2.00}
                        ]
                    }
                ]
            }
        ]
    }


def mock_odds_api_stale() -> dict[str, Any]:
    """Stale odds data (old timestamp)."""
    return {
        "id": "event_stale_001",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "commence_time": (datetime.now() + timedelta(days=2)).isoformat(),
        "home_team": "Old Team A",
        "away_team": "Old Team B",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": (datetime.now() - timedelta(hours=2)).isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": (datetime.now() - timedelta(hours=2)).isoformat(),
                        "outcomes": [
                            {"name": "Old Team A", "price": 2.00},
                            {"name": "Old Team B", "price": 2.00}
                        ]
                    }
                ]
            }
        ]
    }


# =============================================================================
# Expected Normalized Data
# =============================================================================

def expected_normalized_polymarket() -> list[dict[str, Any]]:
    """Expected normalized Polymarket data."""
    return [
        {
            "market_id": "0xabc123def456",
            "source": "polymarket",
            "event_name": "Chiefs win Super Bowl 2024",
            "teams": ["Chiefs", "San Francisco 49ers"],
            "market_type": "winner",
            "outcomes": {
                "yes": {"probability": 0.65, "decimal_odds": 1.538},
                "no": {"probability": 0.35, "decimal_odds": 2.857}
            },
            "start_time": datetime.now() + timedelta(days=7),
            "sport": "football",
            "league": "NFL",
            "liquidity_usd": 500000,
            "volume_24h": 1500000,
            "last_updated": datetime.now(),
            "raw_data": {}
        },
        {
            "market_id": "0xdef789ghi012",
            "source": "polymarket",
            "event_name": "Eagles beat Cowboys in Week 14",
            "teams": ["Eagles", "Cowboys"],
            "market_type": "h2h",
            "outcomes": {
                "yes": {"probability": 0.58, "decimal_odds": 1.724},
                "no": {"probability": 0.42, "decimal_odds": 2.381}
            },
            "start_time": datetime.now() + timedelta(days=3),
            "sport": "football",
            "league": "NFL",
            "liquidity_usd": 200000,
            "volume_24h": 800000,
            "last_updated": datetime.now(),
            "raw_data": {}
        }
    ]


def expected_normalized_sportsbook() -> list[dict[str, Any]]:
    """Expected normalized sportsbook data."""
    return [
        {
            "market_id": "event_nfl_001",
            "source": "draftkings",
            "event_name": "Kansas City Chiefs vs San Francisco 49ers",
            "teams": ["Kansas City Chiefs", "San Francisco 49ers"],
            "market_type": "h2h",
            "outcomes": {
                "home": {"name": "Kansas City Chiefs", "decimal_odds": 1.54, "american_odds": -185},
                "away": {"name": "San Francisco 49ers", "decimal_odds": 2.85, "american_odds": 185}
            },
            "start_time": datetime.now() + timedelta(days=7),
            "sport": "americanfootball",
            "league": "NFL",
            "liquidity_usd": 1000000,  # Estimated
            "last_updated": datetime.now(),
            "raw_data": {}
        },
        {
            "market_id": "event_nfl_001",
            "source": "fanduel",
            "event_name": "Kansas City Chiefs vs San Francisco 49ers",
            "teams": ["Kansas City Chiefs", "San Francisco 49ers"],
            "market_type": "h2h",
            "outcomes": {
                "home": {"name": "Kansas City Chiefs", "decimal_odds": 1.53, "american_odds": -189},
                "away": {"name": "San Francisco 49ers", "decimal_odds": 2.90, "american_odds": 190}
            },
            "start_time": datetime.now() + timedelta(days=7),
            "sport": "americanfootball",
            "league": "NFL",
            "liquidity_usd": 1200000,
            "last_updated": datetime.now(),
            "raw_data": {}
        }
    ]


# =============================================================================
# Expected Matches
# =============================================================================

def expected_arbitrage_matches() -> list[dict[str, Any]]:
    """Expected arbitrage match results."""
    return [
        {
            "match_id": "match_001",
            "confidence": 0.95,
            "polymarket_market": {
                "id": "0xabc123def456",
                "event_name": "Chiefs win Super Bowl 2024"
            },
            "sportsbook_market": {
                "id": "event_nfl_001",
                "source": "draftkings",
                "event_name": "Kansas City Chiefs vs San Francisco 49ers"
            },
            "teams_matched": ["Chiefs", "49ers"],
            "outcome_mapping": {
                "polymarket_yes": "sportsbook_chiefs_win",
                "polymarket_no": "sportsbook_49ers_win"
            },
            "matched_outcome": "Chiefs to win",
            "polymarket_odds": 1.538,  # 65% implied
            "sportsbook_odds": 1.54,  # DraftKings
            "price_divergence": 0.002,
            "arbitrage_opportunity": False,  # No arb, just similar prices
            "timestamp": datetime.now()
        },
        {
            "match_id": "match_002",
            "confidence": 0.92,
            "polymarket_market": {
                "id": "0xdef789ghi012",
                "event_name": "Eagles beat Cowboys in Week 14"
            },
            "sportsbook_market": {
                "id": "event_nfl_002",
                "source": "draftkings",
                "event_name": "Dallas Cowboys vs Philadelphia Eagles"
            },
            "teams_matched": ["Eagles", "Cowboys"],
            "outcome_mapping": {
                "polymarket_yes": "sportsbook_eagles_win",
                "polymarket_no": "sportsbook_cowboys_win"
            },
            "matched_outcome": "Eagles to win",
            "polymarket_odds": 1.724,  # 58% implied
            "sportsbook_odds": 1.72,  # DraftKings
            "price_divergence": 0.004,
            "arbitrage_opportunity": False,
            "timestamp": datetime.now()
        }
    ]


def expected_true_arbitrage() -> list[dict[str, Any]]:
    """Expected true arbitrage opportunity (guaranteed profit)."""
    # This represents a scenario where implied probabilities sum to < 100%
    return [
        {
            "match_id": "arb_001",
            "confidence": 0.98,
            "polymarket_market": {
                "id": "0xtruearb123",
                "event_name": "Team A vs Team B"
            },
            "sportsbook_market": {
                "id": "sb_truearb",
                "source": "draftkings",
                "event_name": "Team A vs Team B"
            },
            "teams_matched": ["Team A", "Team B"],
            "side_a": {
                "venue": "polymarket",
                "outcome": "Team A wins",
                "odds_decimal": 2.10,  # 47.6% implied prob
                "implied_probability": 0.476,
                "stake": 476.19,
                "payout": 1000.00
            },
            "side_b": {
                "venue": "sportsbook",
                "outcome": "Team B wins",
                "odds_decimal": 2.20,  # 45.5% implied prob
                "implied_probability": 0.455,
                "stake": 454.55,
                "payout": 1000.00
            },
            "total_invested": 930.74,
            "guaranteed_payout": 1000.00,
            "gross_profit": 69.26,
            "gross_edge_percent": 7.44,
            "fees": {
                "polymarket_fee": 2.00,
                "gas_estimate": 5.00,
                "sportsbook_vig": 0.00
            },
            "net_profit": 62.26,
            "net_edge_percent": 6.69,
            "roi_percent": 6.69,
            "timestamp": datetime.now()
        }
    ]


# =============================================================================
# Edge Cases and Special Cases
# =============================================================================

def mock_polymarket_edge_cases() -> dict[str, Any]:
    """Edge cases for Polymarket data."""
    return {
        "markets": [
            {
                "id": "0xedge_empty",
                "question": "",
                "description": "Empty question",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.50", "0.50"],
                "volume": "0",
                "liquidity": "0",
                "min_investment": "5",
                "max_investment": "5000",
                "creator_address": "0xempty",
                "condition_id": "cond_empty",
                "token_ids": {"Yes": "0xe1", "No": "0xe2"},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "0xedge_missing_fields",
                "question": "Missing some fields",
                # Missing description, category
                "active": True,
                "end_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.50", "0.50"],
                # Missing volume, liquidity
            },
            {
                "id": "0xedge_extreme_odds",
                "question": "Extreme odds market",
                "description": "Market with very skewed odds",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No"],
                "outcomePrices": ["0.99", "0.01"],  # Extreme 99/1 split
                "volume": "5000000",
                "liquidity": "1000000",
                "min_investment": "5",
                "max_investment": "5000",
                "creator_address": "0xextreme",
                "condition_id": "cond_extreme",
                "token_ids": {"Yes": "0xex1", "No": "0xex2"},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "id": "0xedge_invalid_odds",
                "question": "Invalid odds sum",
                "description": "Odds don't sum to 1",
                "category": "Sports",
                "active": True,
                "closed": False,
                "end_date": (datetime.now() + timedelta(days=1)).isoformat(),
                "outcomes": ["Yes", "No", "Maybe"],
                "outcomePrices": ["0.40", "0.40", "0.40"],  # Sums to 1.2
                "volume": "100000",
                "liquidity": "50000",
                "min_investment": "5",
                "max_investment": "5000",
                "creator_address": "0xinvalid",
                "condition_id": "cond_invalid",
                "token_ids": {"Yes": "0xi1", "No": "0xi2", "Maybe": "0xi3"},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        ]
    }


def mock_sportsbook_edge_cases() -> dict[str, Any]:
    """Edge cases for sportsbook data."""
    return {
        "id": "event_edge_001",
        "sport_key": "americanfootball_nfl",
        "sport_title": "NFL",
        "commence_time": (datetime.now() + timedelta(days=1)).isoformat(),
        "home_team": "Team A",
        "away_team": "Team B",
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "last_update": datetime.now().isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": datetime.now().isoformat(),
                        "outcomes": [
                            {"name": "Team A", "price": 1.01},  # Very heavy favorite
                            {"name": "Team B", "price": 50.00}  # Very long underdog
                        ]
                    }
                ]
            },
            {
                "key": "problematic_book",
                "title": "Problematic Book",
                "last_update": (datetime.now() - timedelta(minutes=1)).isoformat(),
                "markets": [
                    {
                        "key": "h2h",
                        "last_update": (datetime.now() - timedelta(minutes=1)).isoformat(),
                        "outcomes": [
                            {"name": "Team A", "price": -999999},  # Invalid negative price
                            {"name": "Team B", "price": 0}  # Invalid zero price
                        ]
                    }
                ]
            },
            {
                "key": "empty_book",
                "title": "Empty Book",
                "last_update": datetime.now().isoformat(),
                "markets": []  # Empty markets
            }
        ]
    }


# =============================================================================
# Test Configuration
# =============================================================================

def get_test_config() -> dict[str, Any]:
    """Test configuration with relaxed thresholds."""
    return {
        "arbitrage": {
            "min_edge_percent": 1.0,
            "min_net_edge_percent": 0.5,
            "max_stake_usd": 1000,
            "min_stake_usd": 10,
            "target_stake_usd": 500
        },
        "filters": {
            "min_liquidity_usd": 1000,
            "max_odds_staleness_minutes": 60,
            "min_match_confidence": 0.80,
            "blocked_sports": [],
            "blocked_leagues": [],
            "blocked_teams": []
        },
        "polymarket": {
            "api_endpoint": "https://api.polymarket.com",
            "min_liquidity": 1000,
            "fee_percent": 2.0
        },
        "sportsbooks": {
            "draftkings": {"enabled": True, "priority": 1},
            "fanduel": {"enabled": True, "priority": 2},
            "betmgm": {"enabled": True, "priority": 3}
        },
        "telegram": {
            "enabled": False,
            "alert_cooldown_minutes": 5
        }
    }


# =============================================================================
# Historical Known Arbitrages for End-to-End Testing
# =============================================================================

def get_known_arbitrage_scenarios() -> list[dict[str, Any]]:
    """Known historical or synthetic arbitrage scenarios for testing."""
    return [
        {
            "name": "Classic NFL Arbitrage",
            "description": "Known arb opportunity from historical data",
            "polymarket": {
                "id": "0xhist001",
                "question": "Will Chiefs beat Raiders?",
                "outcome_prices": ["0.75", "0.25"],  # 75% implied
                "liquidity": "500000"
            },
            "sportsbook": {
                "source": "draftkings",
                "event": "Chiefs vs Raiders",
                "team_a_odds": 1.60,  # 62.5% implied
                "team_b_odds": 2.50   # 40% implied
            },
            "expected": {
                "is_arbitrage": True,
                "expected_edge": 2.5,  # 62.5 + 25 = 87.5%, 12.5% arb space
                "side_to_bet": "Team B on Polymarket"
            }
        },
        {
            "name": "NBA Playoff Arbitrage",
            "description": "Playoff game with divergent odds",
            "polymarket": {
                "id": "0xhist002",
                "question": "Will Lakers win Game 3?",
                "outcome_prices": ["0.60", "0.40"],  # 60% implied
                "liquidity": "750000"
            },
            "sportsbook": {
                "source": "fanduel",
                "event": "Lakers vs Warriors",
                "team_a_odds": 1.50,  # 66.7% implied
                "team_b_odds": 2.80   # 35.7% implied
            },
            "expected": {
                "is_arbitrage": True,
                "expected_edge": 2.4,  # 66.7 + 40 = 106.7%, but check the other side
                "side_to_bet": "Team A on Polymarket"
            }
        },
        {
            "name": "No Arbitrage - Close Prices",
            "description": "Markets with similar prices, no arb",
            "polymarket": {
                "id": "0xhist003",
                "question": "Will favored team win?",
                "outcome_prices": ["0.65", "0.35"],  # 65% implied
                "liquidity": "300000"
            },
            "sportsbook": {
                "source": "betmgm",
                "event": "Matchup",
                "team_a_odds": 1.55,  # 64.5% implied
                "team_b_odds": 2.75   # 36.4% implied
            },
            "expected": {
                "is_arbitrage": False,
                "expected_edge": 0.0,
                "side_to_bet": None
            }
        }
    ]
