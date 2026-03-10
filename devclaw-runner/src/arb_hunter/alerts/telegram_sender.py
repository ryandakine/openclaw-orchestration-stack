"""Telegram API sender with rate limiting and retry logic.

Uses httpx for async HTTP requests with automatic retries.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


# Telegram API base URL
TELEGRAM_API_BASE = "https://api.telegram.org"

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds
DEFAULT_TIMEOUT = 30.0  # seconds

# Rate limiting
DEFAULT_RATE_LIMIT_PER_MINUTE = 20


@dataclass
class TelegramConfig:
    """Configuration for Telegram API."""
    
    bot_token: str
    chat_id: str
    max_retries: int = DEFAULT_MAX_RETRIES
    retry_delay: float = DEFAULT_RETRY_DELAY
    timeout: float = DEFAULT_TIMEOUT
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    parse_mode: str = "MarkdownV2"


class TelegramRateLimiter:
    """Simple rate limiter for Telegram API."""
    
    def __init__(self, max_requests_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE):
        """Initialize rate limiter.
        
        Args:
            max_requests_per_minute: Maximum requests allowed per minute
        """
        self.max_requests = max_requests_per_minute
        self._requests: list[float] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        """Acquire a rate limit slot, waiting if necessary."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            
            # Remove requests older than 1 minute
            cutoff = now - 60.0
            self._requests = [t for t in self._requests if t > cutoff]
            
            # Check if we need to wait
            if len(self._requests) >= self.max_requests:
                # Wait until oldest request expires
                wait_time = self._requests[0] - cutoff
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Recalculate after wait
                    now = asyncio.get_event_loop().time()
                    cutoff = now - 60.0
                    self._requests = [t for t in self._requests if t > cutoff]
            
            # Record this request
            self._requests.append(now)
    
    def get_remaining(self) -> int:
        """Get remaining requests in current window."""
        now = asyncio.get_event_loop().time()
        cutoff = now - 60.0
        recent = len([t for t in self._requests if t > cutoff])
        return max(0, self.max_requests - recent)


class TelegramSender:
    """Sends messages to Telegram with retry and rate limiting."""
    
    def __init__(self, config: TelegramConfig | None = None) -> None:
        """Initialize the Telegram sender.
        
        Args:
            config: Telegram configuration
        """
        self.config = config
        self._rate_limiter = TelegramRateLimiter(
            config.rate_limit_per_minute if config else DEFAULT_RATE_LIMIT_PER_MINUTE
        )
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            timeout = httpx.Timeout(
                self.config.timeout if self.config else DEFAULT_TIMEOUT
            )
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client
    
    async def send_message(
        self,
        message: str,
        disable_notification: bool = False,
    ) -> dict[str, Any]:
        """Send a message to Telegram.
        
        Args:
            message: Message text to send
            disable_notification: Send without notification sound
            
        Returns:
            Telegram API response
            
        Raises:
            ValueError: If no config is set
            TelegramAPIError: If API request fails after retries
        """
        if self.config is None:
            raise ValueError("TelegramConfig not set")
        
        # Wait for rate limit
        await self._rate_limiter.acquire()
        
        url = f"{TELEGRAM_API_BASE}/bot{self.config.bot_token}/sendMessage"
        
        payload = {
            "chat_id": self.config.chat_id,
            "text": message,
            "parse_mode": self.config.parse_mode,
            "disable_notification": disable_notification,
        }
        
        max_retries = self.config.max_retries
        retry_delay = self.config.retry_delay
        
        for attempt in range(max_retries + 1):
            try:
                client = await self._get_client()
                response = await client.post(url, json=payload)
                
                # Handle rate limiting from Telegram
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", retry_delay))
                    if attempt < max_retries:
                        await asyncio.sleep(retry_after)
                        continue
                
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                raise TelegramAPIError(
                    f"HTTP error after {max_retries} retries: {e.response.status_code}"
                ) from e
                
            except httpx.RequestError as e:
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                raise TelegramAPIError(
                    f"Request error after {max_retries} retries: {e}"
                ) from e
        
        raise TelegramAPIError("Max retries exceeded")
    
    async def send_messages_batch(
        self,
        messages: list[str],
        delay_between: float = 1.0,
    ) -> list[dict[str, Any]]:
        """Send multiple messages with delay between each.
        
        Args:
            messages: List of messages to send
            delay_between: Delay in seconds between messages
            
        Returns:
            List of API responses
        """
        results = []
        for i, message in enumerate(messages):
            try:
                result = await self.send_message(message)
                results.append(result)
            except TelegramAPIError as e:
                results.append({"error": str(e)})
            
            # Delay between messages (but not after the last one)
            if i < len(messages) - 1:
                await asyncio.sleep(delay_between)
        
        return results
    
    async def test_connection(self) -> bool:
        """Test the Telegram connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        if self.config is None:
            return False
        
        try:
            url = f"{TELEGRAM_API_BASE}/bot{self.config.bot_token}/getMe"
            client = await self._get_client()
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("ok", False)
        except Exception:
            return False
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def get_rate_limit_status(self) -> dict[str, int]:
        """Get current rate limit status.
        
        Returns:
            Dictionary with remaining requests
        """
        return {
            "remaining": self._rate_limiter.get_remaining(),
            "limit": self._rate_limiter.max_requests,
        }


class TelegramAPIError(Exception):
    """Error from Telegram API."""
    pass


# Convenience factory functions

def create_sender_from_env() -> TelegramSender:
    """Create sender from environment variables.
    
    Expects:
        TELEGRAM_BOT_TOKEN: Bot token from @BotFather
        TELEGRAM_CHAT_ID: Target chat ID
        
    Returns:
        Configured TelegramSender
        
    Raises:
        ValueError: If required env vars are missing
    """
    import os
    
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set"
        )
    
    config = TelegramConfig(
        bot_token=bot_token,
        chat_id=chat_id,
    )
    
    return TelegramSender(config)
