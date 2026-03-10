"""
Feature Flags Configuration.

Controls feature toggles for enabling/disabling venues, modes,
and experimental features without code changes.
"""

from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class VenueFlags:
    """Feature flags for individual venues."""
    
    polymarket: bool = field(default=True)
    """Enable Polymarket integration."""
    
    kalshi: bool = field(default=True)
    """Enable Kalshi integration."""
    
    predictit: bool = field(default=True)
    """Enable PredictIt integration."""
    
    sportsbooks: bool = field(default=True)
    """Enable sportsbook integration via The Odds API."""
    
    def get_enabled_venues(self) -> list[str]:
        """Get list of enabled venue names."""
        venues = []
        if self.polymarket:
            venues.append("polymarket")
        if self.kalshi:
            venues.append("kalshi")
        if self.predictit:
            venues.append("predictit")
        if self.sportsbooks:
            venues.append("sportsbook")
        return venues
    
    def is_venue_enabled(self, venue: str) -> bool:
        """Check if a specific venue is enabled."""
        venue_map = {
            "polymarket": self.polymarket,
            "kalshi": self.kalshi,
            "predictit": self.predictit,
            "sportsbook": self.sportsbooks,
        }
        return venue_map.get(venue.lower(), False)


@dataclass(frozen=True, slots=True)
class TradingModeFlags:
    """Feature flags for trading modes."""
    
    mock_data: bool = field(default=False)
    """
    Use mock/fake data instead of real API calls.
    Useful for testing without hitting rate limits.
    """
    
    paper_trading: bool = field(default=True)
    """
    Simulate trades without actual execution.
    Records what trades would have been made.
    """
    
    dry_run: bool = field(default=True)
    """
    Run the full pipeline but don't execute any trades.
    More comprehensive than paper_trading - logs all decisions.
    """
    
    backtest_mode: bool = field(default=False)
    """Run in backtest mode using historical data."""


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """
    Complete feature flag configuration.
    
    Centralizes all feature toggles for the application,
    allowing runtime control over enabled functionality.
    """
    
    # Venue enablement
    venues: VenueFlags = field(default_factory=VenueFlags)
    """Flags for individual venue integrations."""
    
    # Trading modes
    trading: TradingModeFlags = field(default_factory=TradingModeFlags)
    """Flags for trading behavior modes."""
    
    # Feature toggles
    enable_advanced_analytics: bool = field(default=False)
    """Enable advanced analytics and ML-based predictions."""
    
    enable_ml_predictions: bool = field(default=False)
    """Enable machine learning-based price predictions."""
    
    enable_correlation_analysis: bool = field(default=True)
    """Enable cross-venue market correlation analysis."""
    
    enable_sentiment_analysis: bool = field(default=False)
    """Enable social media/news sentiment analysis."""
    
    enable_auto_hedging: bool = field(default=False)
    """Enable automatic hedging of positions."""
    
    enable_notifications: bool = field(default=True)
    """Enable notification systems (Telegram, etc.)."""
    
    enable_metrics: bool = field(default=True)
    """Enable Prometheus metrics export."""
    
    enable_caching: bool = field(default=True)
    """Enable Redis caching for API responses."""
    
    # Experimental features
    enable_experimental_features: bool = field(default=False)
    """Enable experimental/unstable features."""
    
    enable_websocket_feeds: bool = field(default=False)
    """Enable real-time websocket feeds (experimental)."""
    
    enable_cross_chain_arb: bool = field(default=False)
    """Enable cross-chain arbitrage detection (experimental)."""
    
    # Debug features
    enable_debug_logging: bool = field(default=False)
    """Enable verbose debug logging."""
    
    enable_request_logging: bool = field(default=False)
    """Log all HTTP requests and responses."""
    
    enable_profiling: bool = field(default=False)
    """Enable performance profiling."""
    
    def __post_init__(self) -> None:
        """Validate feature flag combinations."""
        self._validate_trading_modes()
    
    def _validate_trading_modes(self) -> None:
        """Ensure trading mode flags are consistent."""
        # If mock_data is enabled, paper_trading should also be enabled
        if self.trading.mock_data and not self.trading.paper_trading:
            raise ValueError("paper_trading must be enabled when mock_data is enabled")
    
    # =========================================================================
    # Convenience Properties
    # =========================================================================
    
    @property
    def any_venue_enabled(self) -> bool:
        """Check if at least one venue is enabled."""
        return len(self.venues.get_enabled_venues()) > 0
    
    @property
    def live_trading_enabled(self) -> bool:
        """
        Check if live trading is enabled.
        
        Returns True only if not in mock, paper, or dry-run mode.
        """
        return not (
            self.trading.mock_data or
            self.trading.paper_trading or
            self.trading.dry_run
        )
    
    @property
    def is_simulation_mode(self) -> bool:
        """Check if running in any simulation mode."""
        return self.trading.mock_data or self.trading.paper_trading
    
    # =========================================================================
    # Venue Checks
    # =========================================================================
    
    def is_venue_enabled(self, venue: str) -> bool:
        """Check if a specific venue is enabled."""
        return self.venues.is_venue_enabled(venue)
    
    def require_venue(self, venue: str) -> None:
        """
        Assert that a venue is enabled.
        
        Raises:
            ValueError: If venue is not enabled
        """
        if not self.is_venue_enabled(venue):
            raise ValueError(f"Venue '{venue}' is not enabled")
    
    def get_enabled_venues(self) -> list[str]:
        """Get list of all enabled venue names."""
        return self.venues.get_enabled_venues()
    
    # =========================================================================
    # Feature Checks
    # =========================================================================
    
    def require_feature(self, feature: str) -> None:
        """
        Assert that a feature is enabled.
        
        Args:
            feature: Feature name (attribute name)
            
        Raises:
            ValueError: If feature is not enabled
            AttributeError: If feature doesn't exist
        """
        if not getattr(self, feature, False):
            raise ValueError(f"Feature '{feature}' is not enabled")
    
    def can_use_ml(self) -> bool:
        """Check if ML features can be used."""
        return self.enable_ml_predictions and self.enable_advanced_analytics
    
    def can_use_websockets(self) -> bool:
        """Check if websocket features can be used."""
        return self.enable_websocket_feeds and self.enable_experimental_features
    
    # =========================================================================
    # Factory Methods
    # =========================================================================
    
    @classmethod
    def development_defaults(cls) -> Self:
        """Get feature flags suitable for development."""
        return cls(
            venues=VenueFlags(
                polymarket=True,
                kalshi=True,
                predictit=True,
                sportsbooks=True,
            ),
            trading=TradingModeFlags(
                mock_data=True,
                paper_trading=True,
                dry_run=True,
                backtest_mode=False,
            ),
            enable_advanced_analytics=True,
            enable_ml_predictions=False,
            enable_debug_logging=True,
            enable_request_logging=True,
        )
    
    @classmethod
    def production_defaults(cls) -> Self:
        """Get feature flags suitable for production."""
        return cls(
            venues=VenueFlags(
                polymarket=True,
                kalshi=True,
                predictit=False,  # Disabled by default due to withdrawal fees
                sportsbooks=True,
            ),
            trading=TradingModeFlags(
                mock_data=False,
                paper_trading=False,
                dry_run=False,
                backtest_mode=False,
            ),
            enable_advanced_analytics=True,
            enable_ml_predictions=True,
            enable_debug_logging=False,
            enable_request_logging=False,
        )
    
    @classmethod
    def testing_defaults(cls) -> Self:
        """Get feature flags suitable for testing."""
        return cls(
            venues=VenueFlags(
                polymarket=True,
                kalshi=True,
                predictit=True,
                sportsbooks=True,
            ),
            trading=TradingModeFlags(
                mock_data=True,
                paper_trading=True,
                dry_run=True,
                backtest_mode=False,
            ),
            enable_notifications=False,
            enable_metrics=False,
            enable_caching=False,
            enable_debug_logging=True,
        )
    
    # =========================================================================
    # Environment Loading
    # =========================================================================
    
    @classmethod
    def from_env(cls) -> Self:
        """
        Create from environment variables.
        
        Environment variables (all prefixed with ENABLE_):
        - ENABLE_POLYMARKET
        - ENABLE_KALSHI
        - ENABLE_PREDICTIT
        - ENABLE_SPORTSBOOKS
        - ENABLE_MOCK_DATA
        - ENABLE_PAPER_TRADING
        - etc.
        
        Returns:
            FeatureFlags instance
        """
        import os
        
        def env_bool(name: str, default: bool = False) -> bool:
            value = os.getenv(f"ENABLE_{name.upper()}", str(default).lower())
            return value.lower() in ("true", "1", "yes", "on")
        
        return cls(
            venues=VenueFlags(
                polymarket=env_bool("POLYMARKET", True),
                kalshi=env_bool("KALSHI", True),
                predictit=env_bool("PREDICTIT", True),
                sportsbooks=env_bool("SPORTSBOOKS", True),
            ),
            trading=TradingModeFlags(
                mock_data=env_bool("MOCK_DATA", False),
                paper_trading=env_bool("PAPER_TRADING", True),
                dry_run=env_bool("DRY_RUN", True),
                backtest_mode=env_bool("BACKTEST_MODE", False),
            ),
            enable_advanced_analytics=env_bool("ADVANCED_ANALYTICS", False),
            enable_ml_predictions=env_bool("ML_PREDICTIONS", False),
            enable_correlation_analysis=env_bool("CORRELATION_ANALYSIS", True),
            enable_sentiment_analysis=env_bool("SENTIMENT_ANALYSIS", False),
            enable_auto_hedging=env_bool("AUTO_HEDGING", False),
            enable_notifications=env_bool("NOTIFICATIONS", True),
            enable_metrics=env_bool("METRICS", True),
            enable_caching=env_bool("CACHING", True),
            enable_experimental_features=env_bool("EXPERIMENTAL_FEATURES", False),
            enable_websocket_feeds=env_bool("WEBSOCKET_FEEDS", False),
            enable_cross_chain_arb=env_bool("CROSS_CHAIN_ARB", False),
            enable_debug_logging=env_bool("DEBUG_LOGGING", False),
            enable_request_logging=env_bool("REQUEST_LOGGING", False),
            enable_profiling=env_bool("PROFILING", False),
        )
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "venues": {
                "polymarket": self.venues.polymarket,
                "kalshi": self.venues.kalshi,
                "predictit": self.venues.predictit,
                "sportsbooks": self.venues.sportsbooks,
            },
            "trading": {
                "mock_data": self.trading.mock_data,
                "paper_trading": self.trading.paper_trading,
                "dry_run": self.trading.dry_run,
                "backtest_mode": self.trading.backtest_mode,
            },
            "enable_advanced_analytics": self.enable_advanced_analytics,
            "enable_ml_predictions": self.enable_ml_predictions,
            "enable_correlation_analysis": self.enable_correlation_analysis,
            "enable_sentiment_analysis": self.enable_sentiment_analysis,
            "enable_auto_hedging": self.enable_auto_hedging,
            "enable_notifications": self.enable_notifications,
            "enable_metrics": self.enable_metrics,
            "enable_caching": self.enable_caching,
            "enable_experimental_features": self.enable_experimental_features,
            "enable_websocket_feeds": self.enable_websocket_feeds,
            "enable_cross_chain_arb": self.enable_cross_chain_arb,
            "enable_debug_logging": self.enable_debug_logging,
            "enable_request_logging": self.enable_request_logging,
            "enable_profiling": self.enable_profiling,
        }


def get_default_features() -> FeatureFlags:
    """
    Get default feature flags (safe for most deployments).
    
    Returns:
        FeatureFlags with conservative defaults
    """
    return FeatureFlags()
