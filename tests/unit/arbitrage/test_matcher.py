"""
Unit tests for the event matcher module.

These tests verify:
- Team name normalization
- Entity extraction
- Fuzzy string matching
- Time proximity calculations
- Event matching logic
- Outcome mapping
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from src.arbitrage.matcher import (
    normalize_team_name,
    extract_entities,
    calculate_string_similarity,
    calculate_time_proximity,
    calculate_entity_overlap,
    fuzzy_match_events,
    map_outcomes,
    EventMatcher,
)
from src.arbitrage.models import (
    NormalizedMarket,
    MarketOutcome,
    MarketType,
)


class TestNormalizeTeamName:
    """Test team name normalization."""
    
    def test_basic_normalization(self):
        """Test basic name normalization."""
        assert normalize_team_name("Lakers") == "lakers"
        assert normalize_team_name("Los Angeles Lakers") == "los angeles lakers"
    
    def test_remove_suffixes(self):
        """Test removal of common suffixes."""
        assert normalize_team_name("Manchester United FC") == "manchester united"
        assert normalize_team_name("Real Madrid CF") == "madrid"
        assert normalize_team_name("LA Galaxy") == "los angeles galaxy"
    
    def test_remove_punctuation(self):
        """Test removal of punctuation."""
        assert normalize_team_name("A.C. Milan") == "ac milan"
        assert normalize_team_name("Bayern Munich!") == "bayern munich"
    
    def test_abbreviations(self):
        """Test abbreviation expansion."""
        assert normalize_team_name("Man United") == "manchester united"
        assert normalize_team_name("Man Utd") == "manchester united"
        assert normalize_team_name("Man City") == "manchester city"
        assert normalize_team_name("NY Giants") == "new york giants"
        assert normalize_team_name("LA Dodgers") == "los angeles dodgers"


class TestExtractEntities:
    """Test entity extraction from event titles."""
    
    def test_vs_separator(self):
        """Test extraction with 'vs' separator."""
        entities = extract_entities("Lakers vs Warriors")
        assert "lakers" in entities
        assert "warriors" in entities
    
    def test_at_separator(self):
        """Test extraction with '@' separator."""
        entities = extract_entities("Lakers @ Warriors")
        assert "lakers" in entities
        assert "warriors" in entities
    
    def test_multiple_separators(self):
        """Test extraction with various separators."""
        test_cases = [
            ("Team A vs Team B", {"team a", "team b"}),
            ("Team A vs. Team B", {"team a", "team b"}),
            ("Team A v Team B", {"team a", "team b"}),
            ("Team A @ Team B", {"team a", "team b"}),
            ("Team A - Team B", {"team a", "team b"}),
        ]
        
        for title, expected in test_cases:
            entities = extract_entities(title)
            # Check that expected entities are present (may have additional extracted words)
            for exp in expected:
                assert exp in entities, f"Failed for: {title} - missing {exp}"
    
    def test_remove_common_words(self):
        """Test removal of common non-entity words."""
        entities = extract_entities("Will Trump win vs Will Biden win")
        # "will" and "win" should be removed
        assert "will" not in entities
        assert "win" not in entities
        assert "trump" in entities
        assert "biden" in entities
    
    def test_complex_title(self):
        """Test extraction from complex titles."""
        entities = extract_entities("Manchester United vs Liverpool FC at Old Trafford")
        assert "manchester united" in entities
        assert "liverpool" in entities


class TestStringSimilarity:
    """Test fuzzy string matching."""
    
    def test_identical_strings(self):
        """Test identical strings have similarity 1.0."""
        assert calculate_string_similarity("Lakers vs Warriors", "Lakers vs Warriors") == 1.0
    
    def test_completely_different(self):
        """Test completely different strings."""
        sim = calculate_string_similarity("abcdef", "ghijkl")
        assert sim < 0.3  # Should be quite low
    
    def test_similar_strings(self):
        """Test similar but not identical strings."""
        sim = calculate_string_similarity(
            "Lakers vs Warriors",
            "Lakers @ Warriors"
        )
        assert 0.7 < sim < 1.0  # High but not perfect
    
    def test_case_insensitive(self):
        """Test case insensitivity."""
        sim = calculate_string_similarity("LAKERS VS WARRIORS", "lakers vs warriors")
        assert sim == 1.0
    
    def test_empty_strings(self):
        """Test handling of empty strings."""
        assert calculate_string_similarity("", "test") == 0.0
        assert calculate_string_similarity("test", "") == 0.0
        assert calculate_string_similarity("", "") == 0.0


class TestTimeProximity:
    """Test time proximity calculations."""
    
    def test_same_time(self):
        """Test identical times have score 1.0."""
        time1 = datetime(2024, 1, 15, 20, 0, 0)
        time2 = datetime(2024, 1, 15, 20, 0, 0)
        score = calculate_time_proximity(time1, time2)
        assert score == Decimal("1.0")
    
    def test_different_times(self):
        """Test different times have lower scores."""
        time1 = datetime(2024, 1, 15, 20, 0, 0)
        time2 = datetime(2024, 1, 15, 12, 0, 0)  # 8 hours difference
        
        score = calculate_time_proximity(time1, time2, max_diff_hours=24)
        # 8/24 = 0.333, so score = 1 - 0.333 = 0.667
        assert score.quantize(Decimal("0.01")) == Decimal("0.67")
    
    def test_beyond_maximum(self):
        """Test times beyond max difference have score 0."""
        time1 = datetime(2024, 1, 15, 20, 0, 0)
        time2 = datetime(2024, 1, 16, 22, 0, 0)  # 26 hours difference
        
        score = calculate_time_proximity(time1, time2, max_diff_hours=24)
        assert score == Decimal("0")
    
    def test_order_independence(self):
        """Test that order of times doesn't matter."""
        time1 = datetime(2024, 1, 15, 20, 0, 0)
        time2 = datetime(2024, 1, 15, 12, 0, 0)
        
        score1 = calculate_time_proximity(time1, time2)
        score2 = calculate_time_proximity(time2, time1)
        assert score1 == score2


class TestEntityOverlap:
    """Test entity overlap calculations."""
    
    def test_identical_entities(self):
        """Test identical entity sets."""
        entities1 = {"lakers", "warriors"}
        entities2 = {"lakers", "warriors"}
        overlap = calculate_entity_overlap(entities1, entities2)
        assert overlap == Decimal("1.0")
    
    def test_no_overlap(self):
        """Test completely different entity sets."""
        entities1 = {"lakers", "warriors"}
        entities2 = {"celtics", "nets"}
        overlap = calculate_entity_overlap(entities1, entities2)
        assert overlap == Decimal("0")
    
    def test_partial_overlap(self):
        """Test partial overlap."""
        entities1 = {"lakers", "warriors", "celtics"}
        entities2 = {"lakers", "nets", "knicks"}
        # Intersection: 1 (lakers)
        # Union: 5
        # Jaccard: 1/5 = 0.2
        overlap = calculate_entity_overlap(entities1, entities2)
        assert overlap == Decimal("0.2")
    
    def test_empty_sets(self):
        """Test handling of empty sets."""
        assert calculate_entity_overlap(set(), {"lakers"}) == Decimal("0")
        assert calculate_entity_overlap({"lakers"}, set()) == Decimal("0")
        assert calculate_entity_overlap(set(), set()) == Decimal("0")


class TestFuzzyMatchEvents:
    """Test fuzzy matching of market events."""
    
    @pytest.fixture
    def base_time(self):
        return datetime(2024, 1, 15, 20, 0, 0)
    
    @pytest.fixture
    def lakers_warriors_market(self, base_time):
        return NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Will Lakers defeat Warriors?",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("2.0")),
                MarketOutcome(label="No", price=Decimal("2.0")),
            ],
        )
    
    @pytest.fixture
    def matching_sportsbook_market(self, base_time):
        return NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
    
    def test_matching_events(self, lakers_warriors_market, matching_sportsbook_market):
        """Test that similar events match."""
        result = fuzzy_match_events(
            lakers_warriors_market,
            matching_sportsbook_market,
        )
        
        assert result.is_match is True
        assert result.score > Decimal("0.7")
        assert "All matching criteria passed" in result.reasons
    
    def test_different_categories(self, lakers_warriors_market, base_time):
        """Test that different categories don't match."""
        nfl_market = NormalizedMarket(
            source="draftkings",
            source_event_id="dk789",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nfl",  # Different category
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        result = fuzzy_match_events(lakers_warriors_market, nfl_market)
        assert result.is_match is False
        assert "Categories don't match" in result.reasons
    
    def test_different_times(self, lakers_warriors_market, base_time):
        """Test that events too far apart don't match."""
        different_time_market = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time + timedelta(days=2),  # 48 hours later
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        result = fuzzy_match_events(
            lakers_warriors_market,
            different_time_market,
            max_time_diff_hours=24,
        )
        assert result.is_match is False
        assert "Time difference exceeds" in result.reasons[0]
    
    def test_different_teams(self, base_time):
        """Test that events with different teams don't match."""
        market1 = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Will Lakers defeat Warriors?",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("2.0")),
                MarketOutcome(label="No", price=Decimal("2.0")),
            ],
        )
        
        market2 = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Celtics vs Nets",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Celtics", price=Decimal("2.0")),
                MarketOutcome(label="Nets", price=Decimal("2.0")),
            ],
        )
        
        result = fuzzy_match_events(market1, market2)
        assert result.is_match is False
        assert result.title_similarity < Decimal("0.6")


class TestMapOutcomes:
    """Test outcome mapping between markets."""
    
    def test_binary_yes_no_mapping(self):
        """Test mapping yes/no outcomes."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Will it rain?",
            market_type=MarketType.BINARY,
            category="weather",
            start_time=datetime.utcnow(),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("0.6")),
                MarketOutcome(label="No", price=Decimal("0.4")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="kalshi",
            source_event_id="k456",
            title="Rain today?",
            market_type=MarketType.BINARY,
            category="weather",
            start_time=datetime.utcnow(),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("0.58")),
                MarketOutcome(label="No", price=Decimal("0.42")),
            ],
        )
        
        mappings = map_outcomes(market_a, market_b)
        
        # Should map Yes to Yes and No to No
        assert len(mappings) == 2
        mapping_types = [m[2] for m in mappings]
        assert "yes_vs_yes" in mapping_types
        assert "no_vs_no" in mapping_types
    
    def test_team_mapping(self):
        """Test mapping team-based outcomes."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow(),
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("1.8")),
                MarketOutcome(label="Warriors", price=Decimal("2.1")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Lakers @ Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow(),
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("1.85")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        mappings = map_outcomes(market_a, market_b)
        
        # Should map Lakers to Lakers (direct match)
        direct_mappings = [m for m in mappings if m[2] == "direct_match"]
        assert len(direct_mappings) >= 1


class TestEventMatcher:
    """Test the EventMatcher class."""
    
    @pytest.fixture
    def matcher(self):
        return EventMatcher(
            min_match_score=Decimal("0.70"),
            min_title_similarity=0.6,
            min_entity_overlap=0.5,
            max_time_diff_hours=24,
        )
    
    @pytest.fixture
    def base_time(self):
        return datetime(2024, 1, 15, 20, 0, 0)
    
    def test_successful_match(self, matcher, base_time):
        """Test successful event matching."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Lakers @ Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        result = matcher.match(market_a, market_b)
        
        assert result is not None
        assert result.status == "matched"
        assert result.match_score >= Decimal("0.70")
    
    def test_rejected_match_low_score(self, matcher, base_time):
        """Test rejection when match score is too low."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Lakers vs Warriors",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Completely Different Event",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("2.0")),
                MarketOutcome(label="No", price=Decimal("2.0")),
            ],
        )
        
        result = matcher.match(market_a, market_b)
        
        assert result is not None
        assert result.status == "rejected"
        assert result.rejection_reason is not None
    
    def test_different_market_types(self, matcher, base_time):
        """Test rejection for different market types."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Lakers vs Warriors",
            market_type=MarketType.MONEYLINE,
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers", price=Decimal("2.0")),
                MarketOutcome(label="Warriors", price=Decimal("2.0")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="draftkings",
            source_event_id="dk456",
            title="Lakers @ Warriors",
            market_type=MarketType.SPREAD,  # Different type
            category="nba",
            start_time=base_time,
            outcomes=[
                MarketOutcome(label="Lakers +5.5", price=Decimal("1.91")),
                MarketOutcome(label="Warriors -5.5", price=Decimal("1.91")),
            ],
        )
        
        result = matcher.match(market_a, market_b)
        assert result is None  # Different market types, no match attempted
    
    def test_find_matches(self, matcher, base_time):
        """Test finding matches between two lists."""
        markets_a = [
            NormalizedMarket(
                source="polymarket",
                source_event_id="pm1",
                title="Lakers vs Warriors",
                market_type=MarketType.BINARY,
                category="nba",
                start_time=base_time,
                outcomes=[
                    MarketOutcome(label="Lakers", price=Decimal("2.0")),
                    MarketOutcome(label="Warriors", price=Decimal("2.0")),
                ],
            ),
            NormalizedMarket(
                source="polymarket",
                source_event_id="pm2",
                title="Celtics vs Nets",
                market_type=MarketType.BINARY,
                category="nba",
                start_time=base_time,
                outcomes=[
                    MarketOutcome(label="Celtics", price=Decimal("2.0")),
                    MarketOutcome(label="Nets", price=Decimal("2.0")),
                ],
            ),
        ]
        
        markets_b = [
            NormalizedMarket(
                source="draftkings",
                source_event_id="dk1",
                title="Lakers @ Warriors",
                market_type=MarketType.BINARY,
                category="nba",
                start_time=base_time,
                outcomes=[
                    MarketOutcome(label="Lakers", price=Decimal("2.0")),
                    MarketOutcome(label="Warriors", price=Decimal("2.0")),
                ],
            ),
            NormalizedMarket(
                source="draftkings",
                source_event_id="dk2",
                title="Celtics vs Nets",
                market_type=MarketType.BINARY,
                category="nba",
                start_time=base_time,
                outcomes=[
                    MarketOutcome(label="Celtics", price=Decimal("2.0")),
                    MarketOutcome(label="Nets", price=Decimal("2.0")),
                ],
            ),
        ]
        
        matches = matcher.find_matches(markets_a, markets_b)
        
        assert len(matches) == 2
        # Each market should be matched once
        matched_ids = [(m.left_market.source_event_id, m.right_market.source_event_id) for m in matches]
        assert ("pm1", "dk1") in matched_ids or ("pm1", "dk2") in matched_ids


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""
    
    def test_political_market_matching(self):
        """Test matching political markets with different phrasings."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm123",
            title="Will Trump win the 2024 election?",
            market_type=MarketType.BINARY,
            category="politics",
            start_time=datetime(2024, 11, 5, 0, 0, 0),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("0.52")),
                MarketOutcome(label="No", price=Decimal("0.48")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="kalshi",
            source_event_id="k456",
            title="Trump to win 2024 Presidential Election",
            market_type=MarketType.BINARY,
            category="politics",
            start_time=datetime(2024, 11, 5, 0, 0, 0),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("0.51")),
                MarketOutcome(label="No", price=Decimal("0.49")),
            ],
        )
        
        result = fuzzy_match_events(market_a, market_b)
        
        assert result.is_match is True
        assert result.title_similarity > Decimal("0.6")  # Similar titles
        # Should extract "trump" and "2024" from both
        assert result.entity_overlap >= Decimal("0.5")
    
    def test_player_prop_matching(self):
        """Test matching player prop markets."""
        market_a = NormalizedMarket(
            source="polymarket",
            source_event_id="pm789",
            title="Will LeBron James score 30+ points?",
            market_type=MarketType.BINARY,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Yes", price=Decimal("0.55")),
                MarketOutcome(label="No", price=Decimal("0.45")),
            ],
        )
        
        market_b = NormalizedMarket(
            source="fanduel",
            source_event_id="fd101",
            title="LeBron James Over/Under 29.5 Points",
            market_type=MarketType.TOTAL,
            category="nba",
            start_time=datetime.utcnow() + timedelta(days=1),
            outcomes=[
                MarketOutcome(label="Over", price=Decimal("1.91")),
                MarketOutcome(label="Under", price=Decimal("1.91")),
            ],
        )
        
        result = fuzzy_match_events(market_a, market_b)
        
        # These should match on "lebron james" entity
        assert "lebron james" in extract_entities(market_a.title)
        assert "lebron james" in extract_entities(market_b.title)
