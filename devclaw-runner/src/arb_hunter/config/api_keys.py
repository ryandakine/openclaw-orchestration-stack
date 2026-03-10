"""
API Key Management.

Manages API credentials for external services including
prediction markets, sportsbooks, and data providers.
"""

from dataclasses import dataclass, field
from typing import Self
import re


@dataclass(frozen=True, slots=True)
class ApiKeys:
    """
    Container for all API credentials.
    
    Uses frozen dataclass to prevent accidental modification of keys.
    All keys are optional - the system will only use configured APIs.
    
    Attributes:
        odds_api_key: The Odds API key for sportsbook data
        kalshi_key_id: Kalshi API key ID
        kalshi_key_secret: Kalshi API key secret
        polymarket_api_key: Polymarket API key (optional, can use wallet)
        predictit_username: PredictIt login username
        predictit_password: PredictIt login password
        cmc_api_key: CoinMarketCap API key (for token prices)
        coingecko_api_key: CoinGecko API key (optional, pro features)
    """
    
    # The Odds API - Sportsbook odds data
    odds_api_key: str | None = field(default=None)
    """API key from https://the-odds-api.com/ for sportsbook odds."""
    
    # Kalshi - Prediction market
    kalshi_key_id: str | None = field(default=None)
    """Kalshi API Key ID."""
    
    kalshi_key_secret: str | None = field(default=None)
    """Kalshi API Key Secret."""
    
    # Polymarket - Prediction market
    polymarket_api_key: str | None = field(default=None)
    """Polymarket API key (optional, wallet auth preferred)."""
    
    # PredictIt - Prediction market
    predictit_username: str | None = field(default=None)
    """PredictIt account username."""
    
    predictit_password: str | None = field(default=None)
    """PredictIt account password."""
    
    # Price/Token APIs
    cmc_api_key: str | None = field(default=None)
    """CoinMarketCap API key for token pricing."""
    
    coingecko_api_key: str | None = field(default=None)
    """CoinGecko API key for pro features (optional)."""
    
    # Custom headers for specific APIs
    custom_headers: dict[str, dict[str, str]] = field(default_factory=dict)
    """Custom headers for specific API calls (e.g., {'odds_api': {'X-Custom': 'value'}})."""
    
    def __post_init__(self) -> None:
        """Validate API key formats."""
        self._validate_odds_api_key()
        self._validate_kalshi_keys()
        self._validate_predictit_credentials()
    
    def _validate_odds_api_key(self) -> None:
        """Validate Odds API key format if provided."""
        if self.odds_api_key:
            # Odds API keys are typically alphanumeric strings
            if len(self.odds_api_key) < 10:
                raise ValueError("odds_api_key appears too short")
    
    def _validate_kalshi_keys(self) -> None:
        """Validate Kalshi key format if provided."""
        if self.kalshi_key_id and not self.kalshi_key_secret:
            raise ValueError("kalshi_key_secret required when kalshi_key_id is provided")
        if self.kalshi_key_secret and not self.kalshi_key_id:
            raise ValueError("kalshi_key_id required when kalshi_key_secret is provided")
        
        if self.kalshi_key_id:
            # Kalshi key IDs are UUID-like
            uuid_pattern = re.compile(
                r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
                re.IGNORECASE
            )
            if not uuid_pattern.match(self.kalshi_key_id):
                raise ValueError("kalshi_key_id does not match expected UUID format")
    
    def _validate_predictit_credentials(self) -> None:
        """Validate PredictIt credentials if provided."""
        has_username = bool(self.predictit_username)
        has_password = bool(self.predictit_password)
        
        if has_username != has_password:
            raise ValueError(
                "Both predictit_username and predictit_password must be provided together"
            )
    
    # =========================================================================
    # Convenience Properties
    # =========================================================================
    
    @property
    def has_odds_api(self) -> bool:
        """Check if Odds API key is configured."""
        return bool(self.odds_api_key)
    
    @property
    def has_kalshi(self) -> bool:
        """Check if Kalshi credentials are configured."""
        return bool(self.kalshi_key_id and self.kalshi_key_secret)
    
    @property
    def has_polymarket(self) -> bool:
        """Check if Polymarket API key is configured."""
        return bool(self.polymarket_api_key)
    
    @property
    def has_predictit(self) -> bool:
        """Check if PredictIt credentials are configured."""
        return bool(self.predictit_username and self.predictit_password)
    
    @property
    def has_cmc(self) -> bool:
        """Check if CoinMarketCap API is configured."""
        return bool(self.cmc_api_key)
    
    @property
    def has_coingecko_pro(self) -> bool:
        """Check if CoinGecko Pro API is configured."""
        return bool(self.coingecko_api_key)
    
    # =========================================================================
    # Key Access Methods
    # =========================================================================
    
    def get_odds_api_key(self) -> str:
        """
        Get Odds API key.
        
        Raises:
            ValueError: If key is not configured
        """
        if not self.odds_api_key:
            raise ValueError("Odds API key not configured")
        return self.odds_api_key
    
    def get_kalshi_credentials(self) -> tuple[str, str]:
        """
        Get Kalshi key ID and secret.
        
        Returns:
            Tuple of (key_id, key_secret)
            
        Raises:
            ValueError: If credentials are not configured
        """
        if not self.has_kalshi:
            raise ValueError("Kalshi credentials not configured")
        return self.kalshi_key_id, self.kalshi_key_secret  # type: ignore
    
    def get_predictit_credentials(self) -> tuple[str, str]:
        """
        Get PredictIt username and password.
        
        Returns:
            Tuple of (username, password)
            
        Raises:
            ValueError: If credentials are not configured
        """
        if not self.has_predictit:
            raise ValueError("PredictIt credentials not configured")
        return self.predictit_username, self.predictit_password  # type: ignore
    
    def get_headers_for_api(self, api_name: str) -> dict[str, str]:
        """
        Get custom headers for a specific API.
        
        Args:
            api_name: Name of the API (e.g., 'odds_api', 'kalshi')
            
        Returns:
            Dictionary of headers (empty if none configured)
        """
        return self.custom_headers.get(api_name, {})
    
    # =========================================================================
    # Masked Display
    # =========================================================================
    
    def get_masked_summary(self) -> dict[str, str]:
        """
        Get a masked summary of configured APIs (safe for logging).
        
        Returns:
            Dictionary with API names and masked key indicators
        """
        def mask_key(key: str | None) -> str:
            if not key:
                return "not configured"
            if len(key) <= 8:
                return "****"
            return f"{key[:4]}...{key[-4:]}"
        
        return {
            "odds_api": mask_key(self.odds_api_key),
            "kalshi": "configured" if self.has_kalshi else "not configured",
            "polymarket": mask_key(self.polymarket_api_key),
            "predictit": "configured" if self.has_predictit else "not configured",
            "cmc": mask_key(self.cmc_api_key),
            "coingecko": "pro" if self.has_coingecko_pro else "free",
        }
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self, include_secrets: bool = False) -> dict:
        """
        Convert to dictionary.
        
        Args:
            include_secrets: If False, sensitive values are redacted
            
        Returns:
            Dictionary representation
        """
        if include_secrets:
            return {
                "odds_api_key": self.odds_api_key,
                "kalshi_key_id": self.kalshi_key_id,
                "kalshi_key_secret": self.kalshi_key_secret,
                "polymarket_api_key": self.polymarket_api_key,
                "predictit_username": self.predictit_username,
                "predictit_password": self.predictit_password,
                "cmc_api_key": self.cmc_api_key,
                "coingecko_api_key": self.coingecko_api_key,
                "custom_headers": self.custom_headers,
            }
        else:
            return {
                "odds_api_key": "***" if self.odds_api_key else None,
                "kalshi_key_id": "***" if self.kalshi_key_id else None,
                "kalshi_key_secret": "***" if self.kalshi_key_secret else None,
                "polymarket_api_key": "***" if self.polymarket_api_key else None,
                "predictit_username": self.predictit_username,
                "predictit_password": "***" if self.predictit_password else None,
                "cmc_api_key": "***" if self.cmc_api_key else None,
                "coingecko_api_key": "***" if self.coingecko_api_key else None,
                "custom_headers": self.custom_headers,
            }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary."""
        return cls(
            odds_api_key=data.get("odds_api_key"),
            kalshi_key_id=data.get("kalshi_key_id"),
            kalshi_key_secret=data.get("kalshi_key_secret"),
            polymarket_api_key=data.get("polymarket_api_key"),
            predictit_username=data.get("predictit_username"),
            predictit_password=data.get("predictit_password"),
            cmc_api_key=data.get("cmc_api_key"),
            coingecko_api_key=data.get("coingecko_api_key"),
            custom_headers=data.get("custom_headers", {}),
        )
    
    @classmethod
    def from_env(cls) -> Self:
        """
        Create from environment variables.
        
        Environment variables:
        - ODDS_API_KEY
        - KALSHI_KEY_ID
        - KALSHI_KEY_SECRET
        - POLYMARKET_API_KEY
        - PREDICTIT_USERNAME
        - PREDICTIT_PASSWORD
        - CMC_API_KEY
        - COINGECKO_API_KEY
        
        Returns:
            ApiKeys instance
        """
        import os
        
        return cls(
            odds_api_key=os.getenv("ODDS_API_KEY"),
            kalshi_key_id=os.getenv("KALSHI_KEY_ID"),
            kalshi_key_secret=os.getenv("KALSHI_KEY_SECRET"),
            polymarket_api_key=os.getenv("POLYMARKET_API_KEY"),
            predictit_username=os.getenv("PREDICTIT_USERNAME"),
            predictit_password=os.getenv("PREDICTIT_PASSWORD"),
            cmc_api_key=os.getenv("CMC_API_KEY"),
            coingecko_api_key=os.getenv("COINGECKO_API_KEY"),
        )


def get_required_apis() -> list[str]:
    """
    Get list of required API keys for full functionality.
    
    Returns:
        List of API names that should be configured
    """
    return [
        "odds_api_key",
        "kalshi_key_id",
        "kalshi_key_secret",
    ]


def get_optional_apis() -> list[str]:
    """
    Get list of optional API keys.
    
    Returns:
        List of optional API names
    """
    return [
        "polymarket_api_key",
        "predictit_username",
        "cmc_api_key",
        "coingecko_api_key",
    ]
