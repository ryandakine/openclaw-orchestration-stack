"""Adapter manager for coordinating multiple adapters.

This module provides high-level management of multiple adapters,
including parallel fetching, health monitoring, and error handling.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .base import BaseAdapter, MarketData, AdapterConfig, AdapterStatus
from .adapter_factory import AdapterFactory


logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """Result of a fetch operation from an adapter.
    
    Attributes:
        adapter_name: Name of the adapter
        success: Whether the fetch succeeded
        markets: List of fetched markets (empty if failed)
        error: Error message if failed
        fetch_time_ms: Time taken to fetch
        timestamp: When the fetch occurred
    """
    adapter_name: str
    success: bool
    markets: list[MarketData] = field(default_factory=list)
    error: str | None = None
    fetch_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AggregatedMarkets:
    """Markets aggregated from multiple sources.
    
    Attributes:
        markets: Combined list of all markets
        by_source: Markets grouped by source
        failed_sources: List of sources that failed
        fetch_metadata: Metadata about the fetch operation
    """
    markets: list[MarketData] = field(default_factory=list)
    by_source: dict[str, list[MarketData]] = field(default_factory=dict)
    failed_sources: list[str] = field(default_factory=list)
    fetch_metadata: dict[str, Any] = field(default_factory=dict)


class AdapterManager:
    """Manager for coordinating multiple adapters.
    
    This class provides a unified interface for fetching data from
    multiple sources in parallel, with error handling and health monitoring.
    
    Example:
        manager = AdapterManager()
        
        # Add adapters
        manager.add_adapter("polymarket")
        manager.add_adapter("kalshi")
        manager.add_adapter("sportsbook")
        
        # Fetch from all
        async with manager:
            results = await manager.fetch_all(category="politics")
            
        # Or use specific adapters
        async with manager:
            polymarket_markets = await manager.fetch_from("polymarket")
    """
    
    def __init__(self) -> None:
        """Initialize the adapter manager."""
        self._factory = AdapterFactory()
        self._adapters: dict[str, BaseAdapter] = {}
        self._configs: dict[str, AdapterConfig] = {}
        self._initialized = False
    
    def add_adapter(
        self,
        name: str,
        config: AdapterConfig | None = None,
    ) -> None:
        """Add an adapter to the manager.
        
        Args:
            name: Adapter identifier
            config: Optional configuration (auto-loaded if None)
        """
        self._configs[name] = config or self._factory._load_config(name)
        # Create on initialization to catch config errors early
        if name not in self._adapters:
            self._adapters[name] = self._factory.create(name, self._configs[name])
    
    def add_adapters(self, names: list[str]) -> None:
        """Add multiple adapters.
        
        Args:
            names: List of adapter identifiers
        """
        for name in names:
            self.add_adapter(name)
    
    def remove_adapter(self, name: str) -> None:
        """Remove an adapter from the manager.
        
        Args:
            name: Adapter identifier
        """
        if name in self._adapters:
            if self._initialized:
                # Need to close if initialized
                asyncio.create_task(self._adapters[name].close())
            del self._adapters[name]
            del self._configs[name]
    
    def list_adapters(self) -> list[str]:
        """List all managed adapter names."""
        return list(self._adapters.keys())
    
    def get_adapter(self, name: str) -> BaseAdapter:
        """Get a specific adapter instance.
        
        Args:
            name: Adapter identifier
            
        Returns:
            Adapter instance
            
        Raises:
            KeyError: If adapter not found
        """
        if name not in self._adapters:
            raise KeyError(f"Adapter not found: {name}")
        return self._adapters[name]
    
    async def initialize(self) -> None:
        """Initialize all managed adapters."""
        if self._initialized:
            return
        
        init_tasks = [
            adapter.initialize()
            for adapter in self._adapters.values()
        ]
        
        # Initialize all concurrently
        results = await asyncio.gather(*init_tasks, return_exceptions=True)
        
        # Log any failures
        for name, result in zip(self._adapters.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"Failed to initialize {name}: {result}")
        
        self._initialized = True
    
    async def close(self) -> None:
        """Close all managed adapters."""
        close_tasks = [
            adapter.close()
            for adapter in self._adapters.values()
        ]
        
        await asyncio.gather(*close_tasks, return_exceptions=True)
        self._initialized = False
    
    async def fetch_from(
        self,
        name: str,
        category: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
    ) -> FetchResult:
        """Fetch markets from a specific adapter.
        
        Args:
            name: Adapter identifier
            category: Optional category filter
            active_only: Only return active markets
            limit: Maximum number of markets
            
        Returns:
            FetchResult with markets or error
        """
        if name not in self._adapters:
            return FetchResult(
                adapter_name=name,
                success=False,
                error=f"Adapter not found: {name}",
            )
        
        adapter = self._adapters[name]
        start_time = asyncio.get_event_loop().time()
        
        try:
            markets = await adapter.fetch_markets(
                category=category,
                active_only=active_only,
                limit=limit,
            )
            
            fetch_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            return FetchResult(
                adapter_name=name,
                success=True,
                markets=markets,
                fetch_time_ms=fetch_time,
            )
            
        except Exception as e:
            fetch_time = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.error(f"Failed to fetch from {name}: {e}")
            
            return FetchResult(
                adapter_name=name,
                success=False,
                error=str(e),
                fetch_time_ms=fetch_time,
            )
    
    async def fetch_all(
        self,
        category: str | None = None,
        active_only: bool = True,
        limit_per_source: int | None = None,
        timeout_seconds: float = 60.0,
    ) -> AggregatedMarkets:
        """Fetch markets from all adapters in parallel.
        
        Args:
            category: Optional category filter
            active_only: Only return active markets
            limit_per_source: Max markets per source
            timeout_seconds: Maximum time to wait
            
        Returns:
            AggregatedMarkets with all results
        """
        if not self._adapters:
            return AggregatedMarkets()
        
        # Create fetch tasks
        tasks = {
            name: asyncio.create_task(
                self.fetch_from(
                    name,
                    category=category,
                    active_only=active_only,
                    limit=limit_per_source,
                )
            )
            for name in self._adapters.keys()
        }
        
        # Wait for all with timeout
        results: dict[str, FetchResult] = {}
        
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=timeout_seconds,
            )
            
            for name, task in tasks.items():
                if task.done():
                    result = task.result()
                    if isinstance(result, Exception):
                        results[name] = FetchResult(
                            adapter_name=name,
                            success=False,
                            error=str(result),
                        )
                    else:
                        results[name] = result
                else:
                    results[name] = FetchResult(
                        adapter_name=name,
                        success=False,
                        error="Timeout",
                    )
                    
        except asyncio.TimeoutError:
            # Cancel remaining tasks
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            
            # Process completed results
            for name, task in tasks.items():
                if task.done() and not task.cancelled():
                    try:
                        results[name] = task.result()
                    except Exception as e:
                        results[name] = FetchResult(
                            adapter_name=name,
                            success=False,
                            error=str(e),
                        )
                elif name not in results:
                    results[name] = FetchResult(
                        adapter_name=name,
                        success=False,
                        error="Timeout",
                    )
        
        # Aggregate results
        all_markets: list[MarketData] = []
        by_source: dict[str, list[MarketData]] = {}
        failed_sources: list[str] = []
        
        for name, result in results.items():
            if result.success:
                all_markets.extend(result.markets)
                by_source[name] = result.markets
            else:
                failed_sources.append(name)
        
        return AggregatedMarkets(
            markets=all_markets,
            by_source=by_source,
            failed_sources=failed_sources,
            fetch_metadata={
                "total_sources": len(self._adapters),
                "successful_sources": len(by_source),
                "failed_sources": failed_sources,
                "results": {
                    name: {
                        "success": r.success,
                        "market_count": len(r.markets),
                        "fetch_time_ms": r.fetch_time_ms,
                        "error": r.error,
                    }
                    for name, r in results.items()
                },
            },
        )
    
    async def search_all(
        self,
        query: str,
        category: str | None = None,
        limit_per_source: int = 10,
    ) -> AggregatedMarkets:
        """Search markets across all adapters.
        
        Args:
            query: Search query
            category: Optional category filter
            limit_per_source: Max results per source
            
        Returns:
            AggregatedMarkets with search results
        """
        search_tasks = []
        adapter_names = []
        
        for name, adapter in self._adapters.items():
            search_tasks.append(
                adapter.search_markets(query, category, limit_per_source)
            )
            adapter_names.append(name)
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        all_markets: list[MarketData] = []
        by_source: dict[str, list[MarketData]] = {}
        failed_sources: list[str] = []
        
        for name, result in zip(adapter_names, results):
            if isinstance(result, Exception):
                failed_sources.append(name)
                logger.error(f"Search failed for {name}: {result}")
            else:
                all_markets.extend(result)
                by_source[name] = result
        
        return AggregatedMarkets(
            markets=all_markets,
            by_source=by_source,
            failed_sources=failed_sources,
        )
    
    async def check_all_health(self) -> dict[str, Any]:
        """Check health of all adapters.
        
        Returns:
            Dictionary with health status for each adapter
        """
        health_tasks = [
            adapter.check_health()
            for adapter in self._adapters.values()
        ]
        
        results = await asyncio.gather(*health_tasks, return_exceptions=True)
        
        return {
            name: {
                "status": r.status.name if not isinstance(r, Exception) else "ERROR",
                "error": str(r) if isinstance(r, Exception) else None,
                "details": r.__dict__ if not isinstance(r, Exception) else None,
            }
            for name, r in zip(self._adapters.keys(), results)
        }
    
    def get_healthy_adapters(self) -> list[str]:
        """Get list of healthy adapter names."""
        return [
            name for name, adapter in self._adapters.items()
            if adapter.is_healthy
        ]
    
    async def __aenter__(self) -> AdapterManager:
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


class ManagedAdapterContext:
    """Context manager for using adapters with automatic cleanup.
    
    Example:
        async with ManagedAdapterContext(["polymarket", "kalshi"]) as ctx:
            results = await ctx.fetch_all(category="politics")
            for market in results.markets:
                process(market)
    """
    
    def __init__(
        self,
        adapter_names: list[str],
        configs: dict[str, AdapterConfig] | None = None,
    ) -> None:
        """Initialize the context.
        
        Args:
            adapter_names: List of adapters to use
            configs: Optional configurations per adapter
        """
        self._manager = AdapterManager()
        self._adapter_names = adapter_names
        self._configs = configs or {}
    
    async def __aenter__(self) -> AdapterManager:
        """Enter context and initialize adapters."""
        for name in self._adapter_names:
            self._manager.add_adapter(name, self._configs.get(name))
        
        await self._manager.initialize()
        return self._manager
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context and cleanup."""
        await self._manager.close()


# Convenience functions for common use cases

async def fetch_from_all_sources(
    sources: list[str] | None = None,
    category: str | None = None,
) -> AggregatedMarkets:
    """Fetch markets from multiple sources.
    
    Convenience function for one-off fetches without managing
    the adapter lifecycle.
    
    Args:
        sources: List of source names (defaults to all PMs)
        category: Optional category filter
        
    Returns:
        Aggregated markets from all sources
        
    Example:
        results = await fetch_from_all_sources(
            sources=["polymarket", "kalshi"],
            category="politics"
        )
    """
    if sources is None:
        sources = ["polymarket", "kalshi", "predictit"]
    
    async with ManagedAdapterContext(sources) as manager:
        return await manager.fetch_all(category=category)


async def search_all_sources(
    query: str,
    sources: list[str] | None = None,
) -> AggregatedMarkets:
    """Search markets across multiple sources.
    
    Args:
        query: Search query
        sources: List of source names
        
    Returns:
        Aggregated search results
    """
    if sources is None:
        sources = ["polymarket", "kalshi", "predictit", "sportsbook"]
    
    async with ManagedAdapterContext(sources) as manager:
        return await manager.search_all(query)
