"""Shared HTTP client with connection pooling and timeouts."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx

from .errors import APIError, TimeoutError


# Default timeout configuration (30 seconds total)
DEFAULT_TIMEOUT = httpx.Timeout(
    connect=10.0,      # Time to establish connection
    read=30.0,         # Time to read response
    write=10.0,        # Time to send request
    pool=5.0,          # Time to acquire connection from pool
)

# Connection pool limits
DEFAULT_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=30.0,
)


class HTTPClient:
    """Shared async HTTP client with connection pooling."""
    
    _instance: HTTPClient | None = None
    _lock = asyncio.Lock()
    
    def __init__(
        self,
        timeout: httpx.Timeout | None = None,
        limits: httpx.Limits | None = None,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize HTTP client.
        
        Args:
            timeout: Request timeout configuration
            limits: Connection pool limits
            base_url: Optional base URL for all requests
            headers: Default headers for all requests
        """
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.limits = limits or DEFAULT_LIMITS
        self.base_url = base_url
        self.default_headers = headers or {}
        
        self._client: httpx.AsyncClient | None = None
        self._client_ref_count: int = 0
    
    @classmethod
    async def get_instance(
        cls,
        timeout: httpx.Timeout | None = None,
        limits: httpx.Limits | None = None,
    ) -> HTTPClient:
        """Get singleton HTTP client instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(timeout=timeout, limits=limits)
        return cls._instance
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the underlying httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=self.limits,
                base_url=self.base_url or "",
                headers=self.default_headers,
            )
        self._client_ref_count += 1
        return self._client
    
    async def _release_client(self) -> None:
        """Release reference to client."""
        self._client_ref_count -= 1
    
    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None
    
    @asynccontextmanager
    async def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> AsyncGenerator[httpx.Response, None]:
        """Make an HTTP request with proper resource management.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            **kwargs: Additional arguments passed to httpx
            
        Yields:
            httpx.Response object
            
        Raises:
            TimeoutError: If request times out
            APIError: For other request errors
        """
        client = await self._get_client()
        try:
            response = await client.request(method, url, **kwargs)
            yield response
        except httpx.TimeoutException as e:
            raise TimeoutError(
                message=f"Request timeout: {e}",
                timeout_seconds=self.timeout.read,
            ) from e
        except httpx.HTTPStatusError as e:
            raise APIError(
                message=f"HTTP error: {e}",
                status_code=e.response.status_code,
                response_body=e.response.text,
            ) from e
        except httpx.RequestError as e:
            raise APIError(message=f"Request failed: {e}") from e
        finally:
            await self._release_client()
    
    async def get(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a GET request."""
        async with self.request("GET", url, **kwargs) as response:
            return response
    
    async def post(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a POST request."""
        async with self.request("POST", url, **kwargs) as response:
            return response
    
    async def put(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a PUT request."""
        async with self.request("PUT", url, **kwargs) as response:
            return response
    
    async def patch(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a PATCH request."""
        async with self.request("PATCH", url, **kwargs) as response:
            return response
    
    async def delete(
        self,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make a DELETE request."""
        async with self.request("DELETE", url, **kwargs) as response:
            return response


# Global client instance
_global_client: HTTPClient | None = None


async def get_http_client(
    timeout: float = 30.0,
    max_connections: int = 100,
    max_keepalive: int = 20,
) -> HTTPClient:
    """Get the global HTTP client instance.
    
    Args:
        timeout: Request timeout in seconds
        max_connections: Maximum number of connections
        max_keepalive: Maximum keepalive connections
        
    Returns:
        Configured HTTPClient instance
    """
    global _global_client
    
    if _global_client is None:
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=timeout,
            write=10.0,
            pool=5.0,
        )
        limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive,
            keepalive_expiry=30.0,
        )
        _global_client = HTTPClient(
            timeout=timeout_config,
            limits=limits,
        )
    
    return _global_client


async def close_http_client() -> None:
    """Close the global HTTP client."""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None
