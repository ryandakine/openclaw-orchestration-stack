#!/usr/bin/env python3
"""
Adapter Demo - Example usage of OpenClaw Exchange/Bookie Adapters

This script demonstrates how to use the adapter interfaces to fetch
market data from multiple sources.

Usage:
    export ODDS_API_KEY="your_key"
    export KALSHI_API_KEY="your_key"  # optional
    python adapter_demo.py
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project to path
sys.path.insert(0, '/home/ryan/openclaw-orchestration-stack')
sys.path.insert(0, '/home/ryan/openclaw-orchestration-stack/devclaw-runner/src')

from arb_hunter.adapters import (
    create_adapter,
    AdapterManager,
    ManagedAdapterContext,
    PolymarketAdapter,
    KalshiAdapter,
    SportsbookAdapter,
    AdapterConfig,
)


async def demo_single_adapter():
    """Demo: Using a single adapter."""
    print("\n" + "="*60)
    print("DEMO 1: Single Adapter (Polymarket)")
    print("="*60)
    
    # Create adapter with default config
    async with create_adapter("polymarket") as adapter:
        print(f"Adapter: {adapter.name}")
        print(f"Source Type: {adapter.source_type.name}")
        print(f"Health: {adapter.health.status.name}")
        
        # Fetch markets
        print("\nFetching politics markets...")
        markets = await adapter.fetch_markets(
            category="politics",
            active_only=True,
            limit=5
        )
        
        print(f"Found {len(markets)} markets\n")
        
        for market in markets[:3]:
            print(f"  📊 {market.title[:60]}...")
            print(f"     Source: {market.source}")
            print(f"     Outcomes: {len(market.outcomes)}")
            if market.outcomes:
                print(f"     Price: {market.outcomes[0].price:.2%}")
            print()


async def demo_search():
    """Demo: Searching markets."""
    print("\n" + "="*60)
    print("DEMO 2: Search Markets")
    print("="*60)
    
    async with create_adapter("polymarket") as adapter:
        print("\nSearching for 'Trump'...")
        results = await adapter.search_markets(
            query="Trump",
            category="politics",
            limit=5
        )
        
        print(f"Found {len(results)} results\n")
        
        for market in results[:3]:
            print(f"  🔍 {market.title[:60]}...")
            print(f"     URL: {market.url}")
            print()


async def demo_adapter_manager():
    """Demo: Using AdapterManager for multiple sources."""
    print("\n" + "="*60)
    print("DEMO 3: Multiple Adapters with AdapterManager")
    print("="*60)
    
    manager = AdapterManager()
    
    # Add prediction market adapters
    manager.add_adapter("polymarket")
    
    # Add Kalshi if API key available
    if os.getenv("KALSHI_API_KEY"):
        manager.add_adapter("kalshi")
    else:
        print("\n(Note: Set KALSHI_API_KEY to include Kalshi)")
    
    # Add sportsbook if API key available
    if os.getenv("ODDS_API_KEY"):
        manager.add_adapter("sportsbook")
    else:
        print("(Note: Set ODDS_API_KEY to include sportsbooks)")
    
    if len(manager.list_adapters()) == 1:
        print("\nOnly Polymarket available (no other API keys)")
    
    async with manager:
        print(f"\nActive adapters: {manager.list_adapters()}")
        
        # Fetch from all
        print("\nFetching from all sources...")
        results = await manager.fetch_all(
            category="politics",
            limit_per_source=3
        )
        
        print(f"\nTotal markets: {len(results.markets)}")
        print(f"Sources: {list(results.by_source.keys())}")
        
        if results.failed_sources:
            print(f"Failed: {results.failed_sources}")
        
        # Show markets by source
        for source, markets in results.by_source.items():
            print(f"\n  [{source.upper()}]")
            for market in markets[:2]:
                print(f"    • {market.title[:50]}...")


async def demo_managed_context():
    """Demo: Using ManagedAdapterContext."""
    print("\n" + "="*60)
    print("DEMO 4: Managed Adapter Context")
    print("="*60)
    
    # Simple context manager approach
    adapters = ["polymarket"]
    
    if os.getenv("KALSHI_API_KEY"):
        adapters.append("kalshi")
    
    async with ManagedAdapterContext(adapters) as manager:
        print(f"\nUsing adapters: {adapters}")
        
        # Search across all
        print("\nSearching for 'election' across all sources...")
        results = await manager.search_all(
            query="election",
            limit_per_source=3
        )
        
        print(f"Found {len(results.markets)} total markets")
        
        for source, markets in results.by_source.items():
            print(f"\n  {source}: {len(markets)} markets")
            for m in markets[:2]:
                print(f"    - {m.title[:45]}...")


async def demo_health_check():
    """Demo: Health monitoring."""
    print("\n" + "="*60)
    print("DEMO 5: Health Monitoring")
    print("="*60)
    
    manager = AdapterManager()
    manager.add_adapter("polymarket")
    
    if os.getenv("ODDS_API_KEY"):
        manager.add_adapter("sportsbook")
    
    async with manager:
        print("\nChecking health of all adapters...")
        health = await manager.check_all_health()
        
        for name, status in health.items():
            status_icon = "✅" if status["status"] == "HEALTHY" else "❌"
            print(f"\n  {status_icon} {name}")
            print(f"     Status: {status['status']}")
            if status['error']:
                print(f"     Error: {status['error']}")


async def demo_explicit_config():
    """Demo: Using explicit adapter configuration."""
    print("\n" + "="*60)
    print("DEMO 6: Explicit Configuration")
    print("="*60)
    
    # Create config with custom settings
    config = AdapterConfig(
        timeout_seconds=45,
        max_retries=3,
        enable_caching=True,
        cache_ttl_seconds=120,
    )
    
    print("\nCustom configuration:")
    print(f"  Timeout: {config.timeout_seconds}s")
    print(f"  Max retries: {config.max_retries}")
    print(f"  Caching: {config.enable_caching}")
    print(f"  Cache TTL: {config.cache_ttl_seconds}s")
    
    async with PolymarketAdapter(config) as adapter:
        markets = await adapter.fetch_markets(limit=3)
        print(f"\nFetched {len(markets)} markets with custom config")


async def main():
    """Run all demos."""
    print("\n" + "="*60)
    print("OPENC LAW ADAPTER DEMO")
    print("="*60)
    print(f"\nTime: {datetime.now().isoformat()}")
    
    try:
        await demo_single_adapter()
    except Exception as e:
        print(f"Demo 1 failed: {e}")
    
    try:
        await demo_search()
    except Exception as e:
        print(f"Demo 2 failed: {e}")
    
    try:
        await demo_adapter_manager()
    except Exception as e:
        print(f"Demo 3 failed: {e}")
    
    try:
        await demo_managed_context()
    except Exception as e:
        print(f"Demo 4 failed: {e}")
    
    try:
        await demo_health_check()
    except Exception as e:
        print(f"Demo 5 failed: {e}")
    
    try:
        await demo_explicit_config()
    except Exception as e:
        print(f"Demo 6 failed: {e}")
    
    print("\n" + "="*60)
    print("DEMO COMPLETE")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
