"""Custom error types for API integrations."""

from __future__ import annotations

from typing import Any


class APIError(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: Any = None,
        api_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        self.api_name = api_name
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.api_name:
            parts.append(f"API: {self.api_name}")
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        return " | ".join(parts)


class RateLimitError(APIError):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
        status_code: int = 429,
        response_body: Any = None,
        api_name: str | None = None,
    ) -> None:
        super().__init__(message, status_code, response_body, api_name)
        self.retry_after = retry_after


class TimeoutError(APIError):
    """Raised when request times out."""
    
    def __init__(
        self,
        message: str = "Request timed out",
        timeout_seconds: float | None = None,
        api_name: str | None = None,
    ) -> None:
        super().__init__(message, None, None, api_name)
        self.timeout_seconds = timeout_seconds


class CircuitBreakerError(APIError):
    """Raised when circuit breaker is open."""
    
    def __init__(
        self,
        message: str = "Circuit breaker is open",
        api_name: str | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        super().__init__(message, None, None, api_name)
        self.cooldown_seconds = cooldown_seconds


class AuthenticationError(APIError):
    """Raised when authentication fails."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        status_code: int = 401,
        response_body: Any = None,
        api_name: str | None = None,
    ) -> None:
        super().__init__(message, status_code, response_body, api_name)


class ValidationError(APIError):
    """Raised when request validation fails."""
    
    def __init__(
        self,
        message: str = "Request validation failed",
        status_code: int = 400,
        response_body: Any = None,
        api_name: str | None = None,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, status_code, response_body, api_name)
        self.field_errors = field_errors or {}


class ServerError(APIError):
    """Raised when server returns 5xx error."""
    
    def __init__(
        self,
        message: str = "Server error",
        status_code: int = 500,
        response_body: Any = None,
        api_name: str | None = None,
    ) -> None:
        super().__init__(message, status_code, response_body, api_name)


class NotFoundError(APIError):
    """Raised when resource is not found."""
    
    def __init__(
        self,
        message: str = "Resource not found",
        status_code: int = 404,
        response_body: Any = None,
        api_name: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        super().__init__(message, status_code, response_body, api_name)
        self.resource_id = resource_id
