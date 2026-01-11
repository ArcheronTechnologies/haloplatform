"""
Rate limiting utilities for API adapters.

Implements token bucket algorithm to respect API rate limits.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_window: int = 10
    window_seconds: float = 10.0
    max_retry_attempts: int = 3
    retry_backoff_base: float = 1.0


class RateLimiter:
    """
    Token bucket rate limiter for API requests.

    Thread-safe and async-compatible.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize the rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        self._timestamps: deque = deque()
        self._lock = asyncio.Lock()
        self._sync_lock = None  # Lazy init for threading.Lock

    def acquire(self) -> bool:
        """
        Synchronously acquire permission to make a request.

        Blocks if rate limit would be exceeded.

        Returns:
            True if request is allowed
        """
        import threading

        if self._sync_lock is None:
            self._sync_lock = threading.Lock()

        with self._sync_lock:
            now = time.time()

            # Remove timestamps outside the window
            window_start = now - self.config.window_seconds
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            # Check if we're at the limit
            if len(self._timestamps) >= self.config.requests_per_window:
                # Calculate wait time
                oldest = self._timestamps[0]
                wait_time = oldest + self.config.window_seconds - now

                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    time.sleep(wait_time)

                    # Clean up again after waiting
                    now = time.time()
                    window_start = now - self.config.window_seconds
                    while self._timestamps and self._timestamps[0] < window_start:
                        self._timestamps.popleft()

            # Record this request
            self._timestamps.append(now)
            return True

    def try_acquire(self) -> bool:
        """
        Try to acquire permission without blocking.

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        import threading

        if self._sync_lock is None:
            self._sync_lock = threading.Lock()

        with self._sync_lock:
            now = time.time()

            # Remove timestamps outside the window
            window_start = now - self.config.window_seconds
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            # Check if we're at the limit
            if len(self._timestamps) >= self.config.requests_per_window:
                return False

            # Record this request
            self._timestamps.append(now)
            return True

    def available_tokens(self) -> int:
        """Get number of requests available in current window."""
        now = time.time()
        window_start = now - self.config.window_seconds

        # Count timestamps in current window
        count = sum(1 for ts in self._timestamps if ts >= window_start)
        return max(0, self.config.requests_per_window - count)

    async def acquire_async(self) -> bool:
        """
        Asynchronously acquire permission to make a request.

        Blocks if rate limit would be exceeded.

        Returns:
            True if request is allowed
        """
        async with self._lock:
            now = time.time()

            # Remove timestamps outside the window
            window_start = now - self.config.window_seconds
            while self._timestamps and self._timestamps[0] < window_start:
                self._timestamps.popleft()

            # Check if we're at the limit
            if len(self._timestamps) >= self.config.requests_per_window:
                # Calculate wait time
                oldest = self._timestamps[0]
                wait_time = oldest + self.config.window_seconds - now

                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)

                    # Clean up again after waiting
                    now = time.time()
                    window_start = now - self.config.window_seconds
                    while self._timestamps and self._timestamps[0] < window_start:
                        self._timestamps.popleft()

            # Record this request
            self._timestamps.append(now)
            return True

    async def acquire_with_retry(
        self,
        func,
        *args,
        **kwargs,
    ):
        """
        Acquire permission and execute function with retry.

        Handles HTTP 429 (Too Many Requests) responses.

        Args:
            func: Async function to execute
            *args: Arguments to pass to function
            **kwargs: Keyword arguments to pass to function

        Returns:
            Result of function execution
        """
        import httpx

        for attempt in range(self.config.max_retry_attempts):
            await self.acquire_async()

            try:
                return await func(*args, **kwargs)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited by server
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        wait_time = float(retry_after)
                    else:
                        wait_time = self.config.retry_backoff_base * (2 ** attempt)

                    logger.warning(
                        f"Rate limited by server, waiting {wait_time}s "
                        f"(attempt {attempt + 1}/{self.config.max_retry_attempts})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

        # All retries exhausted
        raise Exception(
            f"Rate limit exceeded after {self.config.max_retry_attempts} attempts"
        )

    @property
    def current_usage(self) -> int:
        """Get current number of requests in the window."""
        now = time.time()
        window_start = now - self.config.window_seconds

        return sum(1 for ts in self._timestamps if ts >= window_start)

    @property
    def available(self) -> int:
        """Get number of requests available in current window."""
        return max(0, self.config.requests_per_window - self.current_usage)


# Pre-configured rate limiters for known APIs
SCB_RATE_LIMITER = RateLimiter(
    RateLimitConfig(
        requests_per_window=10,
        window_seconds=10.0,
    )
)

BOLAGSVERKET_RATE_LIMITER = RateLimiter(
    RateLimitConfig(
        requests_per_window=50,  # Conservative estimate
        window_seconds=60.0,
    )
)

LANTMATERIET_RATE_LIMITER = RateLimiter(
    RateLimitConfig(
        requests_per_window=100,  # Conservative estimate
        window_seconds=60.0,
    )
)


class RateLimitedClient:
    """
    HTTP client wrapper with built-in rate limiting.

    Wraps httpx.AsyncClient to apply rate limiting to all requests.
    """

    def __init__(
        self,
        client,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """
        Initialize rate-limited client.

        Args:
            client: httpx.AsyncClient instance
            rate_limiter: RateLimiter instance
        """
        self._client = client
        self._limiter = rate_limiter or RateLimiter()

    async def get(self, url: str, **kwargs):
        """Rate-limited GET request."""
        return await self._limiter.acquire_with_retry(
            self._client.get, url, **kwargs
        )

    async def post(self, url: str, **kwargs):
        """Rate-limited POST request."""
        return await self._limiter.acquire_with_retry(
            self._client.post, url, **kwargs
        )

    async def put(self, url: str, **kwargs):
        """Rate-limited PUT request."""
        return await self._limiter.acquire_with_retry(
            self._client.put, url, **kwargs
        )

    async def delete(self, url: str, **kwargs):
        """Rate-limited DELETE request."""
        return await self._limiter.acquire_with_retry(
            self._client.delete, url, **kwargs
        )

    async def aclose(self):
        """Close the underlying client."""
        await self._client.aclose()
