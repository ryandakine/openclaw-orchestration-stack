"""Custom exception for market normalization errors."""


class MarketNormalizationError(Exception):
    """Raised when market normalization fails."""

    def __init__(self, message: str, source: str | None = None, raw_data: dict | None = None) -> None:
        """Initialize the error.

        Args:
            message: Error description
            source: Data source that caused the error
            raw_data: Raw data that caused the error
        """
        super().__init__(message)
        self.source = source
        self.raw_data = raw_data
        self.message = message

    def __str__(self) -> str:
        if self.source:
            return f"[{self.source}] {self.message}"
        return self.message
