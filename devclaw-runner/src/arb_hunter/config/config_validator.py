"""
Configuration Validator.

Validates the complete configuration on startup and raises
ConfigError if any required settings are missing or invalid.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol
from enum import Enum, auto
import re


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = auto()      # Must be fixed, raises ConfigError
    WARNING = auto()    # Should be fixed, logged as warning
    INFO = auto()       # FYI, logged as info


class ConfigError(Exception):
    """
    Exception raised for configuration errors.
    
    This exception is raised when the configuration is invalid
    and the application cannot safely start.
    """
    
    def __init__(self, message: str, field: str | None = None, suggestions: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.field = field
        self.suggestions = suggestions or []
    
    def __str__(self) -> str:
        result = f"Configuration Error"
        if self.field:
            result += f" [{self.field}]"
        result += f": {self.message}"
        if self.suggestions:
            result += f"\n  Suggestions: {', '.join(self.suggestions)}"
        return result


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""
    
    field: str
    message: str
    severity: ValidationSeverity
    suggestions: list[str] = field(default_factory=list)


class Validatable(Protocol):
    """Protocol for objects that can be validated."""
    
    def validate(self) -> list[ValidationIssue]:
        """Validate and return list of issues."""
        ...


class ConfigValidator:
    """
    Validates complete application configuration.
    
    Performs comprehensive validation of all configuration components
    and raises ConfigError if critical issues are found.
    """
    
    def __init__(
        self,
        settings: Any,
        thresholds: Any | None = None,
        fee_config: Any | None = None,
        slippage_config: Any | None = None,
        telegram_config: Any | None = None,
        api_keys: Any | None = None,
        feature_flags: Any | None = None,
        runtime_config: Any | None = None,
    ):
        """
        Initialize validator with all configuration components.
        
        Args:
            settings: Main Settings instance
            thresholds: ArbThresholds instance
            fee_config: FeeConfig instance
            slippage_config: SlippageConfig instance
            telegram_config: TelegramConfig instance
            api_keys: ApiKeys instance
            feature_flags: FeatureFlags instance
            runtime_config: RuntimeConfig instance
        """
        self.settings = settings
        self.thresholds = thresholds
        self.fee_config = fee_config
        self.slippage_config = slippage_config
        self.telegram_config = telegram_config
        self.api_keys = api_keys
        self.feature_flags = feature_flags
        self.runtime_config = runtime_config
        
        self._issues: list[ValidationIssue] = []
    
    def validate_all(self, raise_on_error: bool = True) -> list[ValidationIssue]:
        """
        Run all validation checks.
        
        Args:
            raise_on_error: If True, raise ConfigError on validation errors
            
        Returns:
            List of all validation issues
            
        Raises:
            ConfigError: If raise_on_error is True and errors exist
        """
        self._issues = []
        
        # Run all validation checks
        self._validate_settings()
        self._validate_thresholds()
        self._validate_fee_config()
        self._validate_slippage_config()
        self._validate_telegram_config()
        self._validate_api_keys()
        self._validate_feature_flags()
        self._validate_runtime_config()
        self._validate_cross_component()
        
        # Check for errors
        errors = [i for i in self._issues if i.severity == ValidationSeverity.ERROR]
        
        if errors and raise_on_error:
            first_error = errors[0]
            raise ConfigError(
                message=first_error.message,
                field=first_error.field,
                suggestions=first_error.suggestions,
            )
        
        return self._issues
    
    def _add_issue(
        self,
        field: str,
        message: str,
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        suggestions: list[str] | None = None,
    ) -> None:
        """Add a validation issue."""
        self._issues.append(ValidationIssue(
            field=field,
            message=message,
            severity=severity,
            suggestions=suggestions or [],
        ))
    
    def _validate_settings(self) -> None:
        """Validate main settings."""
        if not self.settings:
            self._add_issue("settings", "Settings not provided")
            return
        
        # Check database configuration
        if not self.settings.database_url:
            self._add_issue(
                "settings.database_url",
                "Database URL not configured",
                suggestions=["Set DATABASE_URL or individual DB_* variables"],
            )
        
        # Check position size consistency
        if hasattr(self.settings, 'min_position_size_usd') and hasattr(self.settings, 'max_position_size_usd'):
            if self.settings.min_position_size_usd >= self.settings.max_position_size_usd:
                self._add_issue(
                    "settings.position_size",
                    f"MIN_POSITION_SIZE_USD ({self.settings.min_position_size_usd}) "
                    f"must be less than MAX_POSITION_SIZE_USD ({self.settings.max_position_size_usd})",
                )
        
        # Warn about development settings in production
        if hasattr(self.settings, 'is_production'):
            if self.settings.is_production:
                if hasattr(self.settings, 'log_level') and self.settings.log_level == "DEBUG":
                    self._add_issue(
                        "settings.log_level",
                        "DEBUG log level in production may impact performance",
                        ValidationSeverity.WARNING,
                    )
    
    def _validate_thresholds(self) -> None:
        """Validate arbitrage thresholds."""
        if not self.thresholds:
            return
        
        # Thresholds are validated in their dataclass __post_init__
        # This is for additional cross-component validation
        pass
    
    def _validate_fee_config(self) -> None:
        """Validate fee configuration."""
        if not self.fee_config:
            return
        
        # Check for obviously wrong fee values
        if hasattr(self.fee_config, 'polymarket'):
            if hasattr(self.fee_config.polymarket, 'taker_fee_pct'):
                if self.fee_config.polymarket.taker_fee_pct > 10:
                    self._add_issue(
                        "fee_config.polymarket",
                        f"Polymarket taker fee ({self.fee_config.polymarket.taker_fee_pct}%) seems high",
                        ValidationSeverity.WARNING,
                        suggestions=["Current fee is 2%"],
                    )
    
    def _validate_slippage_config(self) -> None:
        """Validate slippage configuration."""
        if not self.slippage_config:
            return
        
        if hasattr(self.slippage_config, 'max_slippage_bps'):
            if self.slippage_config.max_slippage_bps > 500:  # 5%
                self._add_issue(
                    "slippage_config.max_slippage_bps",
                    f"Maximum slippage ({self.slippage_config.max_slippage_bps} bps) is very high",
                    ValidationSeverity.WARNING,
                )
    
    def _validate_telegram_config(self) -> None:
        """Validate Telegram configuration."""
        if not self.telegram_config:
            return
        
        if hasattr(self.telegram_config, 'enabled'):
            if self.telegram_config.enabled:
                if not hasattr(self.telegram_config, 'bot_token') or not self.telegram_config.bot_token:
                    self._add_issue(
                        "telegram_config.bot_token",
                        "Telegram enabled but bot_token not set",
                        suggestions=["Set TELEGRAM_BOT_TOKEN or disable Telegram"],
                    )
                if not hasattr(self.telegram_config, 'chat_id') or not self.telegram_config.chat_id:
                    self._add_issue(
                        "telegram_config.chat_id",
                        "Telegram enabled but chat_id not set",
                        suggestions=["Set TELEGRAM_CHAT_ID or disable Telegram"],
                    )
    
    def _validate_api_keys(self) -> None:
        """Validate API keys."""
        if not self.api_keys:
            self._add_issue(
                "api_keys",
                "API keys not configured - no venues will work",
                ValidationSeverity.WARNING,
            )
            return
        
        # Check if any APIs are configured
        has_any_key = (
            getattr(self.api_keys, 'has_odds_api', False) or
            getattr(self.api_keys, 'has_kalshi', False) or
            getattr(self.api_keys, 'has_polymarket', False) or
            getattr(self.api_keys, 'has_predictit', False)
        )
        
        if not has_any_key:
            # Check if mock mode is enabled
            mock_enabled = (
                self.feature_flags and
                hasattr(self.feature_flags, 'trading') and
                hasattr(self.feature_flags.trading, 'mock_data') and
                self.feature_flags.trading.mock_data
            )
            
            if not mock_enabled:
                self._add_issue(
                    "api_keys",
                    "No API keys configured and mock_data not enabled",
                    ValidationSeverity.ERROR,
                    suggestions=[
                        "Set at least one API key (ODDS_API_KEY, KALSHI_KEY_ID, etc.)",
                        "Or enable ENABLE_MOCK_DATA for testing",
                    ],
                )
    
    def _validate_feature_flags(self) -> None:
        """Validate feature flags."""
        if not self.feature_flags:
            return
        
        # Check if at least one venue is enabled
        if hasattr(self.feature_flags, 'venues'):
            venues = getattr(self.feature_flags.venues, 'get_enabled_venues', lambda: [])()
            if not venues:
                self._add_issue(
                    "feature_flags.venues",
                    "No venues enabled - nothing to do",
                    suggestions=["Enable at least one venue: ENABLE_POLYMARKET=true"],
                )
        
        # Warn about experimental features in production
        if hasattr(self.feature_flags, 'enable_experimental_features'):
            if self.feature_flags.enable_experimental_features:
                if self.settings and hasattr(self.settings, 'is_production'):
                    if self.settings.is_production:
                        self._add_issue(
                            "feature_flags.enable_experimental_features",
                            "Experimental features enabled in production",
                            ValidationSeverity.WARNING,
                        )
    
    def _validate_runtime_config(self) -> None:
        """Validate runtime configuration."""
        if not self.runtime_config:
            return
        
        # Runtime config is generally safe, just check for odd values
        pass
    
    def _validate_cross_component(self) -> None:
        """Validate cross-component consistency."""
        # Check venue flags match API keys
        if self.feature_flags and self.api_keys:
            if hasattr(self.feature_flags, 'is_venue_enabled'):
                # Kalshi
                if self.feature_flags.is_venue_enabled('kalshi'):
                    if not getattr(self.api_keys, 'has_kalshi', False):
                        self._add_issue(
                            "cross_component.kalshi",
                            "Kalshi enabled but no API credentials configured",
                            suggestions=["Set KALSHI_KEY_ID and KALSHI_KEY_SECRET"],
                        )
                
                # Polymarket (can work with wallet instead of API key)
                if self.feature_flags.is_venue_enabled('polymarket'):
                    if not getattr(self.api_keys, 'has_polymarket', False):
                        self._add_issue(
                            "cross_component.polymarket",
                            "Polymarket enabled but no API key (wallet auth may be used)",
                            ValidationSeverity.INFO,
                        )
                
                # Sportsbooks
                if self.feature_flags.is_venue_enabled('sportsbook'):
                    if not getattr(self.api_keys, 'has_odds_api', False):
                        self._add_issue(
                            "cross_component.sportsbook",
                            "Sportsbooks enabled but no Odds API key",
                            suggestions=["Set ODDS_API_KEY"],
                        )
        
        # Check dry_run safety in production
        if self.settings and hasattr(self.settings, 'is_production'):
            if self.settings.is_production:
                if self.feature_flags and hasattr(self.feature_flags, 'trading'):
                    if hasattr(self.feature_flags.trading, 'dry_run'):
                        if not self.feature_flags.trading.dry_run:
                            # Check for runtime force dry run
                            if self.runtime_config and hasattr(self.runtime_config, 'force_dry_run'):
                                if self.runtime_config.force_dry_run:
                                    self._add_issue(
                                        "cross_component.safety",
                                        "Runtime force_dry_run is active (safety override)",
                                        ValidationSeverity.INFO,
                                    )
    
    def get_errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self._issues if i.severity == ValidationSeverity.ERROR]
    
    def get_warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self._issues if i.severity == ValidationSeverity.WARNING]
    
    def get_info(self) -> list[ValidationIssue]:
        """Get only info-level issues."""
        return [i for i in self._issues if i.severity == ValidationSeverity.INFO]
    
    def print_report(self) -> None:
        """Print a formatted validation report."""
        print("=" * 60)
        print("CONFIGURATION VALIDATION REPORT")
        print("=" * 60)
        
        if not self._issues:
            print("✅ All checks passed!")
            return
        
        # Group by severity
        errors = self.get_errors()
        warnings = self.get_warnings()
        infos = self.get_info()
        
        if errors:
            print(f"\n❌ ERRORS ({len(errors)}):")
            for issue in errors:
                print(f"  [{issue.field}] {issue.message}")
                if issue.suggestions:
                    for suggestion in issue.suggestions:
                        print(f"    → {suggestion}")
        
        if warnings:
            print(f"\n⚠️  WARNINGS ({len(warnings)}):")
            for issue in warnings:
                print(f"  [{issue.field}] {issue.message}")
        
        if infos:
            print(f"\nℹ️  INFO ({len(infos)}):")
            for issue in infos:
                print(f"  [{issue.field}] {issue.message}")
        
        print("\n" + "=" * 60)


def validate_config(
    settings: Any,
    thresholds: Any | None = None,
    fee_config: Any | None = None,
    slippage_config: Any | None = None,
    telegram_config: Any | None = None,
    api_keys: Any | None = None,
    feature_flags: Any | None = None,
    runtime_config: Any | None = None,
    raise_on_error: bool = True,
) -> list[ValidationIssue]:
    """
    Convenience function to validate all configuration.
    
    Args:
        settings: Main Settings instance
        thresholds: ArbThresholds instance
        fee_config: FeeConfig instance
        slippage_config: SlippageConfig instance
        telegram_config: TelegramConfig instance
        api_keys: ApiKeys instance
        feature_flags: FeatureFlags instance
        runtime_config: RuntimeConfig instance
        raise_on_error: If True, raise ConfigError on validation errors
        
    Returns:
        List of validation issues
        
    Raises:
        ConfigError: If raise_on_error is True and errors exist
    """
    validator = ConfigValidator(
        settings=settings,
        thresholds=thresholds,
        fee_config=fee_config,
        slippage_config=slippage_config,
        telegram_config=telegram_config,
        api_keys=api_keys,
        feature_flags=feature_flags,
        runtime_config=runtime_config,
    )
    
    return validator.validate_all(raise_on_error=raise_on_error)
