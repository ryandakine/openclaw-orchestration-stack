"""Factory and registry for creating adapter instances.

This module provides a centralized way to create and manage adapters
for different data sources.
"""

from __future__ import annotations

import os
from typing import Type

from .base import BaseAdapter, AdapterConfig
from .sportsbook_adapter import (
    SportsbookAdapter,
    DraftKingsAdapter,
    FanDuelAdapter,
    Bet365Adapter,
)
from .prediction_market_adapter import (
    PolymarketAdapter,
    KalshiAdapter,
    PredictItAdapter,
)


class AdapterRegistry:
    """Registry of available adapters.
    
    This class maintains a mapping of adapter names to their classes,
    allowing dynamic adapter creation.
    
    Example:
        registry = AdapterRegistry()
        registry.register("custom", MyCustomAdapter)
        
        adapter_class = registry.get("polymarket")
        adapter = adapter_class(config)
    """
    
    def __init__(self) -> None:
        """Initialize the registry with built-in adapters."""
        self._adapters: dict[str, Type[BaseAdapter]] = {}
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        """Register default adapters."""
        # Prediction Markets
        self.register("polymarket", PolymarketAdapter)
        self.register("kalshi", KalshiAdapter)
        self.register("predictit", PredictItAdapter)
        
        # Sportsbooks (via The Odds API)
        self.register("sportsbook", SportsbookAdapter)
        self.register("draftkings", DraftKingsAdapter)
        self.register("fanduel", FanDuelAdapter)
        self.register("bet365", Bet365Adapter)
    
    def register(
        self,
        name: str,
        adapter_class: Type[BaseAdapter],
    ) -> None:
        """Register an adapter class.
        
        Args:
            name: Adapter identifier
            adapter_class: Adapter class (must inherit from BaseAdapter)
            
        Raises:
            ValueError: If adapter_class is not a valid adapter
        """
        if not issubclass(adapter_class, BaseAdapter):
            raise ValueError(
                f"Adapter class must inherit from BaseAdapter: {adapter_class}"
            )
        
        self._adapters[name.lower()] = adapter_class
    
    def get(self, name: str) -> Type[BaseAdapter]:
        """Get an adapter class by name.
        
        Args:
            name: Adapter identifier
            
        Returns:
            Adapter class
            
        Raises:
            KeyError: If adapter is not registered
        """
        name = name.lower()
        if name not in self._adapters:
            raise KeyError(f"Adapter not found: {name}")
        return self._adapters[name]
    
    def create(
        self,
        name: str,
        config: AdapterConfig | None = None,
    ) -> BaseAdapter:
        """Create an adapter instance.
        
        Args:
            name: Adapter identifier
            config: Optional configuration
            
        Returns:
            Initialized adapter instance
        """
        adapter_class = self.get(name)
        return adapter_class(config)
    
    def list_adapters(self) -> list[str]:
        """List all registered adapter names."""
        return list(self._adapters.keys())
    
    def list_by_type(self, source_type: str) -> list[str]:
        """List adapters by source type.
        
        Args:
            source_type: "sportsbook" or "prediction_market"
            
        Returns:
            List of adapter names
        """
        from .base import SourceType
        
        result = []
        target_type = SourceType[source_type.upper()]
        
        for name, adapter_class in self._adapters.items():
            if adapter_class.source_type == target_type:
                result.append(name)
        
        return result
    
    def is_registered(self, name: str) -> bool:
        """Check if an adapter is registered."""
        return name.lower() in self._adapters
    
    def unregister(self, name: str) -> None:
        """Unregister an adapter.
        
        Args:
            name: Adapter identifier
        """
        name = name.lower()
        if name in self._adapters:
            del self._adapters[name]


class AdapterFactory:
    """Factory for creating pre-configured adapters.
    
    This factory creates adapters with configuration loaded from
    environment variables or passed explicitly.
    
    Example:
        factory = AdapterFactory()
        
        # Create with auto-loaded config from env
        polymarket = factory.create("polymarket")
        
        # Create with explicit config
        kalshi = factory.create("kalshi", AdapterConfig(api_key="..."))
    """
    
    def __init__(self) -> None:
        """Initialize the factory."""
        self._registry = AdapterRegistry()
    
    def create(
        self,
        name: str,
        config: AdapterConfig | None = None,
    ) -> BaseAdapter:
        """Create an adapter with configuration.
        
        If config is not provided, it will be loaded from environment
        variables based on the adapter name.
        
        Args:
            name: Adapter identifier
            config: Optional configuration (auto-loaded if None)
            
        Returns:
            Configured adapter instance
        """
        if config is None:
            config = self._load_config(name)
        
        return self._registry.create(name, config)
    
    def create_all(
        self,
        names: list[str] | None = None,
    ) -> dict[str, BaseAdapter]:
        """Create multiple adapters.
        
        Args:
            names: List of adapter names (all if None)
            
        Returns:
            Dictionary of name -> adapter
        """
        if names is None:
            names = self._registry.list_adapters()
        
        return {
            name: self.create(name)
            for name in names
        }
    
    def create_prediction_markets(
        self,
    ) -> dict[str, BaseAdapter]:
        """Create all prediction market adapters.
        
        Returns:
            Dictionary of name -> adapter
        """
        pm_names = self._registry.list_by_type("prediction_market")
        return self.create_all(pm_names)
    
    def create_sportsbooks(
        self,
    ) -> dict[str, BaseAdapter]:
        """Create all sportsbook adapters.
        
        Returns:
            Dictionary of name -> adapter
        """
        sb_names = self._registry.list_by_type("sportsbook")
        return self.create_all(sb_names)
    
    def _load_config(self, name: str) -> AdapterConfig:
        """Load adapter configuration from environment variables.
        
        Environment variable naming:
        - {NAME}_API_KEY - API key
        - {NAME}_API_SECRET - API secret
        - {NAME}_BASE_URL - Custom base URL
        - {NAME}_TIMEOUT - Timeout in seconds
        
        Args:
            name: Adapter name
            
        Returns:
            Loaded configuration
        """
        name_upper = name.upper()
        
        # Load from environment
        api_key = os.getenv(f"{name_upper}_API_KEY")
        api_secret = os.getenv(f"{name_upper}_API_SECRET")
        base_url = os.getenv(f"{name_upper}_BASE_URL")
        
        # Timeout with default
        timeout_str = os.getenv(f"{name_upper}_TIMEOUT", "30")
        try:
            timeout = float(timeout_str)
        except ValueError:
            timeout = 30.0
        
        # Rate limit (optional)
        rate_limit_str = os.getenv(f"{name_upper}_RATE_LIMIT")
        rate_limit = int(rate_limit_str) if rate_limit_str else None
        
        return AdapterConfig(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            timeout_seconds=timeout,
            rate_limit_requests_per_minute=rate_limit,
        )
    
    def register_adapter(
        self,
        name: str,
        adapter_class: Type[BaseAdapter],
    ) -> None:
        """Register a custom adapter.
        
        Args:
            name: Adapter identifier
            adapter_class: Adapter class
        """
        self._registry.register(name, adapter_class)
    
    def list_available(self) -> list[str]:
        """List all available adapter names."""
        return self._registry.list_adapters()


# Global factory instance
_default_factory: AdapterFactory | None = None


def get_adapter_factory() -> AdapterFactory:
    """Get the global adapter factory instance."""
    global _default_factory
    if _default_factory is None:
        _default_factory = AdapterFactory()
    return _default_factory


def create_adapter(
    name: str,
    config: AdapterConfig | None = None,
) -> BaseAdapter:
    """Create an adapter using the global factory.
    
    Convenience function for quick adapter creation.
    
    Example:
        adapter = create_adapter("polymarket")
        async with adapter:
            markets = await adapter.fetch_markets()
    """
    return get_adapter_factory().create(name, config)
