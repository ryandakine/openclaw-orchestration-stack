#!/usr/bin/env python3
"""
Example usage of the data ingestion module.

This script demonstrates how to:
1. Fetch data from sportsbooks and prediction markets
2. Normalize the data
3. Store it in the database
4. Query the stored data
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))

from openclaw.src.ingestion import (
    create_sportsbook_client,
    create_prediction_market_client,
    DataNormalizer,
    run_ingestion_job,
)
from openclaw.src.database import init_database


def example_1_fetch_and_normalize():
    """Example 1: Fetch data and normalize it."""
    print("=" * 60)
    print("Example 1: Fetch and Normalize Data")
    print("=" * 60)
    
    # Create mock clients (use real clients with API keys in production)
    sportsbook = create_sportsbook_client("mock")
    prediction_market = create_prediction_market_client("mock")
    
    # Fetch data
    print("\n1. Fetching sportsbook odds...")
    odds_data = sportsbook.fetch_odds(sport="NBA", num_events=2)
    print(f"   Fetched {len(odds_data)} events")
    
    print("\n2. Fetching prediction market data...")
    market_data = prediction_market.fetch_markets(category="sports", num_markets=2)
    print(f"   Fetched {len(market_data)} markets")
    
    # Normalize data
    print("\n3. Normalizing data...")
    normalizer = DataNormalizer()
    
    normalized_odds = normalizer.normalize(odds_data, source="mock_sportsbook")
    print(f"   Normalized {len(normalized_odds)} sportsbook events")
    
    normalized_markets = normalizer.normalize(market_data, source="mock_prediction_market")
    print(f"   Normalized {len(normalized_markets)} prediction markets")
    
    # Show sample
    if normalized_odds:
        print("\n4. Sample normalized sportsbook event:")
        sample = normalized_odds[0]
        print(f"   Event: {sample.title}")
        print(f"   Sport: {sample.sport}")
        print(f"   Market: {sample.market_type}")
        print(f"   Source: {sample.source}")
        print(f"   Outcomes:")
        for outcome in sample.outcomes:
            print(f"     - {outcome.name}: {outcome.odds}")
    
    if normalized_markets:
        print("\n5. Sample normalized prediction market:")
        sample = normalized_markets[0]
        print(f"   Event: {sample.title}")
        print(f"   Category: {sample.sport}")
        print(f"   Source: {sample.source}")
        print(f"   Outcomes:")
        for outcome in sample.outcomes:
            print(f"     - {outcome.name}: {outcome.odds} (prob: {outcome.probability})")


def example_2_store_in_database():
    """Example 2: Store normalized data in the database."""
    print("\n" + "=" * 60)
    print("Example 2: Store Data in Database")
    print("=" * 60)
    
    # Initialize database
    db_path = "data/example_ingestion.db"
    db = init_database(db_path)
    print(f"\n1. Initialized database at {db_path}")
    
    # Create normalizer
    normalizer = DataNormalizer()
    
    # Fetch and normalize some data
    sportsbook = create_sportsbook_client("mock")
    odds_data = sportsbook.fetch_odds(sport="NBA", num_events=2)
    normalized = normalizer.normalize(odds_data, source="mock_sportsbook")
    
    print(f"\n2. Fetched and normalized {len(normalized)} events")
    
    # Store in database
    print("\n3. Storing in database...")
    stored_count = 0
    for event in normalized:
        try:
            # Insert event
            event_data = event.to_database_event()
            db.insert("events", event_data, return_id=False)
            
            # Insert odds
            odds_data = event.to_database_odds()
            db.insert("odds", odds_data, return_id=False)
            
            stored_count += 1
        except Exception as e:
            print(f"   Error storing {event.event_id}: {e}")
    
    print(f"   Stored {stored_count} events")
    
    # Query database
    print("\n4. Querying database...")
    events = db.execute("SELECT COUNT(*) as count FROM events")
    odds = db.execute("SELECT COUNT(*) as count FROM odds")
    
    print(f"   Total events: {events[0]['count']}")
    print(f"   Total odds records: {odds[0]['count']}")
    
    # Show sample query
    print("\n5. Sample query - Events by sport:")
    sports = db.execute("SELECT sport, COUNT(*) as count FROM events GROUP BY sport")
    for row in sports:
        print(f"   {row['sport']}: {row['count']} events")


def example_3_run_scheduler():
    """Example 3: Run the ingestion scheduler."""
    print("\n" + "=" * 60)
    print("Example 3: Run Ingestion Scheduler")
    print("=" * 60)
    
    # Run a complete ingestion job
    print("\n1. Running complete ingestion job...")
    result = run_ingestion_job(
        sportsbook_client="mock",
        prediction_market_client="mock",
        sport="NBA",
        category="sports",
        db_path="data/example_scheduler.db",
    )
    
    print(f"\n2. Results:")
    print(f"   Jobs run: {result['jobs_run']}")
    
    for job_result in result['results']:
        print(f"\n   Job: {job_result['job_name']}")
        print(f"     Status: {job_result['status']}")
        print(f"     Fetched: {job_result['events_fetched']}")
        print(f"     Normalized: {job_result['events_normalized']}")
        print(f"     Stored: {job_result['events_stored']}")


def example_4_query_data():
    """Example 4: Query the stored data."""
    print("\n" + "=" * 60)
    print("Example 4: Query Stored Data")
    print("=" * 60)
    
    # Initialize database
    db = init_database("data/example_scheduler.db")
    
    # Get active events
    print("\n1. Active events (starting in next 24 hours):")
    from datetime import datetime, timedelta
    future = datetime.utcnow() + timedelta(days=1)
    events = db.get_active_events(before_start_time=future)
    
    for event in events[:3]:  # Show first 3
        print(f"   - {event['title']} ({event['sport']})")
        print(f"     Starts: {event['start_time']}")
        print(f"     Source: {event['source']}")
    
    # Get odds for a specific event
    if events:
        print("\n2. Odds for first event:")
        event_id = events[0]['event_id']
        odds = db.get_odds_by_event(event_id)
        
        for odd in odds[:3]:  # Show first 3
            print(f"   Source: {odd['source']}")
            print(f"   Market: {odd['market_type']}")
            print(f"   Timestamp: {odd['timestamp']}")
            print()


def main():
    """Run all examples."""
    print("\n")
    print("*" * 60)
    print("* Data Ingestion Module - Usage Examples")
    print("*" * 60)
    
    try:
        example_1_fetch_and_normalize()
        example_2_store_in_database()
        example_3_run_scheduler()
        example_4_query_data()
        
        print("\n" + "=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
