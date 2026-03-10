"""
Tests for the data ingestion module.
"""

import os
import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from openclaw.src.ingestion.sportsbook_client import (
    MockSportsbookClient,
    TheOddsAPIClient,
    create_sportsbook_client,
)
from openclaw.src.ingestion.prediction_market_client import (
    MockPredictionMarketClient,
    PolymarketClient,
    KalshiClient,
    create_prediction_market_client,
)
from openclaw.src.ingestion.normalizer import DataNormalizer, NormalizedEvent, normalize_data
from openclaw.src.ingestion.scheduler import IngestionScheduler, IngestionJob, run_ingestion_job
from openclaw.src.database.connection import IngestionDatabase, init_database
from openclaw.src.database.models import Event, Odds, create_tables, drop_tables


class TestSportsbookClient(unittest.TestCase):
    """Tests for sportsbook clients."""
    
    def test_mock_client_fetch_odds(self):
        """Test that mock client generates odds correctly."""
        client = MockSportsbookClient()
        odds = client.fetch_odds(sport="NBA", num_events=5)
        
        self.assertEqual(len(odds), 5)
        
        # Check structure
        for event in odds:
            self.assertIn("id", event)
            self.assertIn("home_team", event)
            self.assertIn("away_team", event)
            self.assertIn("bookmakers", event)
            self.assertTrue(len(event["bookmakers"]) > 0)
    
    def test_mock_client_multiple_sports(self):
        """Test mock client with different sports."""
        client = MockSportsbookClient()
        
        for sport in ["NBA", "NFL", "MLB"]:
            odds = client.fetch_odds(sport=sport, num_events=3)
            self.assertTrue(len(odds) > 0)
            self.assertEqual(odds[0]["sport_title"], sport)
    
    def test_create_sportsbook_client_mock(self):
        """Test factory function for mock client."""
        client = create_sportsbook_client("mock")
        self.assertIsInstance(client, MockSportsbookClient)


class TestPredictionMarketClient(unittest.TestCase):
    """Tests for prediction market clients."""
    
    def test_mock_client_fetch_markets(self):
        """Test that mock PM client generates markets correctly."""
        client = MockPredictionMarketClient()
        markets = client.fetch_markets(category="sports", num_markets=5)
        
        self.assertEqual(len(markets), 5)
        
        # Check structure
        for market in markets:
            self.assertIn("id", market)
            self.assertIn("title", market)
            self.assertIn("outcomes", market)
            self.assertEqual(len(market["outcomes"]), 2)  # YES/NO
    
    def test_mock_client_binary_outcomes(self):
        """Test that markets have YES/NO outcomes."""
        client = MockPredictionMarketClient()
        markets = client.fetch_markets(category="politics", num_markets=3)
        
        for market in markets:
            outcome_names = [o["name"] for o in market["outcomes"]]
            self.assertIn("YES", outcome_names)
            self.assertIn("NO", outcome_names)
    
    def test_create_prediction_market_client_mock(self):
        """Test factory function for mock client."""
        client = create_prediction_market_client("mock")
        self.assertIsInstance(client, MockPredictionMarketClient)


class TestDataNormalizer(unittest.TestCase):
    """Tests for data normalizer."""
    
    def setUp(self):
        self.normalizer = DataNormalizer()
    
    def test_normalize_mock_sportsbook(self):
        """Test normalizing mock sportsbook data."""
        client = MockSportsbookClient()
        raw_data = client.fetch_odds(sport="NBA", num_events=2)
        
        normalized = self.normalizer.normalize(raw_data, source="mock_sportsbook")
        
        # Each event has multiple bookmakers, each with multiple markets
        self.assertTrue(len(normalized) > 0)
        
        # Check normalized structure
        for event in normalized:
            self.assertIsInstance(event, NormalizedEvent)
            self.assertIn(event.market_type, ["moneyline", "spread", "total"])
            self.assertEqual(len(event.teams), 2)
            self.assertTrue(len(event.outcomes) >= 2)
    
    def test_normalize_mock_prediction_market(self):
        """Test normalizing mock prediction market data."""
        client = MockPredictionMarketClient()
        raw_data = client.fetch_markets(category="sports", num_markets=3)
        
        normalized = self.normalizer.normalize(raw_data, source="mock_prediction_market")
        
        self.assertEqual(len(normalized), 3)
        
        for event in normalized:
            self.assertIsInstance(event, NormalizedEvent)
            self.assertEqual(event.market_type, "binary")
            self.assertEqual(len(event.outcomes), 2)
            
            # Check YES/NO outcomes
            outcome_names = [o.name for o in event.outcomes]
            self.assertIn("YES", outcome_names)
            self.assertIn("NO", outcome_names)
    
    def test_american_to_decimal_conversion(self):
        """Test American odds to decimal conversion."""
        # -110 should be ~1.91
        self.assertAlmostEqual(
            self.normalizer._american_to_decimal(-110),
            1.91,
            places=1
        )
        
        # +150 should be 2.50
        self.assertEqual(
            self.normalizer._american_to_decimal(150),
            2.50
        )
    
    def test_probability_to_decimal(self):
        """Test probability to decimal odds conversion."""
        # 50% should be 2.0
        self.assertEqual(self.normalizer._probability_to_decimal(0.5), 2.0)
        
        # 25% should be 4.0
        self.assertEqual(self.normalizer._probability_to_decimal(0.25), 4.0)


class TestDatabase(unittest.TestCase):
    """Tests for database operations."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = init_database(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_tables(self):
        """Test that tables are created."""
        # Check that we can query the events table
        result = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [r["name"] for r in result]
        
        self.assertIn("events", table_names)
        self.assertIn("odds", table_names)
        self.assertIn("ingestion_log", table_names)
    
    def test_insert_event(self):
        """Test inserting an event."""
        event = Event.create(
            sport="NBA",
            teams=["Lakers", "Warriors"],
            start_time=datetime.now() + timedelta(days=1),
            market_type="moneyline",
            source="test",
            source_event_id="test_123",
            title="Lakers vs Warriors",
        )
        
        event_id = self.db.insert("events", event.to_dict())
        self.assertIsNotNone(event_id)
        
        # Verify insertion
        fetched = self.db.get_event_by_id(event.event_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["sport"], "NBA")
        self.assertEqual(json.loads(fetched["teams"]), ["Lakers", "Warriors"])
    
    def test_insert_odds(self):
        """Test inserting odds."""
        # First create an event with unique ID
        event = Event.create(
            sport="NBA",
            teams=["Lakers", "Warriors"],
            start_time=datetime.now() + timedelta(days=1),
            market_type="moneyline",
            source="test_odds",
            source_event_id="test_odds_456",
            title="Lakers vs Warriors",
        )
        self.db.insert("events", event.to_dict())
        
        # Then create odds
        odds = Odds(
            event_id=event.event_id,
            market_type="moneyline",
            outcomes=[
                {"name": "Lakers", "odds": 1.85, "source": "DraftKings"},
                {"name": "Warriors", "odds": 2.10, "source": "DraftKings"},
            ],
            source="DraftKings",
        )
        
        odds_id = self.db.insert("odds", odds.to_dict())
        self.assertIsNotNone(odds_id)
        
        # Verify insertion
        fetched_odds = self.db.get_odds_by_event(event.event_id)
        self.assertEqual(len(fetched_odds), 1)
        self.assertEqual(fetched_odds[0]["source"], "DraftKings")


class TestIngestionScheduler(unittest.TestCase):
    """Tests for ingestion scheduler."""
    
    def setUp(self):
        """Create temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.scheduler = IngestionScheduler(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up."""
        import shutil
        self.scheduler.stop_scheduler()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_sportsbook_job(self):
        """Test adding a sportsbook job."""
        self.scheduler.add_sportsbook_job(
            name="test_sportsbook",
            client_type="mock",
            sport="NBA",
        )
        
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.assertEqual(self.scheduler.jobs[0].name, "test_sportsbook")
    
    def test_add_prediction_market_job(self):
        """Test adding a prediction market job."""
        self.scheduler.add_prediction_market_job(
            name="test_pm",
            client_type="mock",
            category="sports",
        )
        
        self.assertEqual(len(self.scheduler.jobs), 1)
        self.assertEqual(self.scheduler.jobs[0].name, "test_pm")
    
    def test_run_job(self):
        """Test running a single job."""
        job = IngestionJob(
            name="test_job",
            client=MockSportsbookClient(),
            fetch_params={"sport": "NBA", "num_events": 3},
        )
        
        result = self.scheduler.run_job(job)
        
        self.assertEqual(result["job_name"], "test_job")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["events_fetched"], 3)
        self.assertTrue(result["events_normalized"] > 0)
        self.assertTrue(result["events_stored"] > 0)
    
    def test_run_all_jobs(self):
        """Test running all configured jobs."""
        self.scheduler.add_sportsbook_job(
            name="sportsbook_test",
            client_type="mock",
            sport="NBA",
            num_events=2,
        )
        self.scheduler.add_prediction_market_job(
            name="pm_test",
            client_type="mock",
            category="sports",
            num_markets=2,
        )
        
        results = self.scheduler.run_all_jobs()
        
        self.assertEqual(len(results), 2)
        
        for result in results:
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["events_fetched"] > 0)


def run_integration_test():
    """
    Run a full integration test.
    
    This demonstrates the complete data flow from fetching to storage.
    """
    print("=" * 60)
    print("INTEGRATION TEST: Full Data Ingestion Flow")
    print("=" * 60)
    
    # Create temp database
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "integration_test.db")
        
        # Create scheduler
        scheduler = IngestionScheduler(db_path=db_path)
        
        # Add jobs
        scheduler.add_sportsbook_job(
            name="sportsbook_demo",
            client_type="mock",
            sport="NBA",
            num_events=3,
        )
        scheduler.add_prediction_market_job(
            name="polymarket_demo",
            client_type="mock",
            category="sports",
            num_markets=3,
        )
        
        # Run all jobs
        print("\n1. Running ingestion jobs...")
        results = scheduler.run_all_jobs()
        
        for result in results:
            print(f"\n  Job: {result['job_name']}")
            print(f"    Status: {result['status']}")
            print(f"    Fetched: {result['events_fetched']}")
            print(f"    Normalized: {result['events_normalized']}")
            print(f"    Stored: {result['events_stored']}")
        
        # Check database
        print("\n2. Verifying database contents...")
        db = IngestionDatabase(db_path)
        
        events = db.execute("SELECT COUNT(*) as count FROM events")
        odds = db.execute("SELECT COUNT(*) as count FROM odds")
        
        print(f"    Events in database: {events[0]['count']}")
        print(f"    Odds records: {odds[0]['count']}")
        
        # Show sample data
        print("\n3. Sample normalized events:")
        sample_events = db.execute(
            "SELECT event_id, sport, title, source FROM events LIMIT 3"
        )
        for event in sample_events:
            print(f"    - {event['title']} ({event['sport']}) from {event['source']}")
        
        print("\n4. Ingestion stats:")
        stats = scheduler.get_ingestion_stats(hours=1)
        print(f"    Total runs: {stats['total_runs']}")
        print(f"    Total events stored: {stats['total_events_stored']}")
        
        print("\n" + "=" * 60)
        print("INTEGRATION TEST COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    # Run unit tests
    print("Running unit tests...\n")
    unittest.main(argv=[''], verbosity=2, exit=False)
    
    # Run integration test
    print("\n")
    run_integration_test()
