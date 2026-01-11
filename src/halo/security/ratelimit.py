"""
Rate limiting for Halo platform.

Implements per-user + per-endpoint rate limiting.
Per-IP alone fails behind NAT/corporate proxies.

Per security framework section 6.1.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as redis
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an endpoint."""

    max_requests: int
    window_seconds: int


# Default rate limits per endpoint
RATE_LIMITS = {
    "/api/v1/auth/login": RateLimitConfig(5, 60),  # 5/minute - auth is sensitive
    "/api/v1/auth/register": RateLimitConfig(3, 60),  # 3/minute
    "/api/v1/search": RateLimitConfig(30, 60),  # 30/minute - expensive
    "/api/v1/entities/search": RateLimitConfig(30, 60),
    "/api/v1/export": RateLimitConfig(5, 3600),  # 5/hour - data exfil risk
    "/api/v1/cases/export": RateLimitConfig(5, 3600),
    "default": RateLimitConfig(100, 60),  # 100/minute default
}


class RateLimiter:
    """
    Per-user + per-endpoint rate limiter with Redis backend.

    Features:
    - Per-user limiting for authenticated requests
    - Per-IP fallback for unauthenticated requests
    - Per-endpoint customization
    - Sliding window using Redis INCR + EXPIRE
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        limits: Optional[dict[str, RateLimitConfig]] = None,
    ):
        """
        Initialize rate limiter.

        Args:
            redis_client: Async Redis client
            limits: Optional custom rate limits (uses RATE_LIMITS if None)
        """
        self._redis = redis_client
        self._limits = limits or RATE_LIMITS

    def _get_limit(self, path: str) -> RateLimitConfig:
        """
        Get rate limit config for a path.

        Checks for exact match first, then prefix match, then default.

        Args:
            path: The request path

        Returns:
            RateLimitConfig for this path
        """
        # Exact match
        if path in self._limits:
            return self._limits[path]

        # Prefix match
        for pattern, config in self._limits.items():
            if pattern != "default" and path.startswith(pattern):
                return config

        # Default
        return self._limits.get("default", RateLimitConfig(100, 60))

    async def check(
        self,
        request: Request,
        user_id: Optional[str] = None,
    ) -> dict:
        """
        Check rate limit and increment counter.

        Args:
            request: FastAPI Request object
            user_id: Authenticated user ID (uses IP if None)

        Returns:
            Dict with rate limit info

        Raises:
            HTTPException: 429 if rate limit exceeded
        """
        path = request.url.path
        config = self._get_limit(path)

        # Build key based on user or IP
        if user_id:
            key = f"ratelimit:user:{user_id}:{path}"
        else:
            client_ip = self._get_client_ip(request)
            key = f"ratelimit:ip:{client_ip}:{path}"

        # Increment counter
        current = await self._redis.incr(key)

        # Set expiry on first request in window
        if current == 1:
            await self._redis.expire(key, config.window_seconds)

        # Get TTL for headers
        ttl = await self._redis.ttl(key)

        # Check if over limit
        remaining = max(0, config.max_requests - current)

        if current > config.max_requests:
            logger.warning(
                f"Rate limit exceeded: {key} ({current}/{config.max_requests})"
            )
            raise HTTPException(
                status_code=429,
                detail="För många förfrågningar. Försök igen senare.",
                headers={
                    "Retry-After": str(ttl),
                    "X-RateLimit-Limit": str(config.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(ttl),
                },
            )

        return {
            "limit": config.max_requests,
            "remaining": remaining,
            "reset_in": ttl,
            "window": config.window_seconds,
        }

    async def add_headers(
        self,
        response,
        limit_info: dict,
    ) -> None:
        """
        Add rate limit headers to response.

        Args:
            response: FastAPI Response object
            limit_info: Dict from check() method
        """
        response.headers["X-RateLimit-Limit"] = str(limit_info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(limit_info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(limit_info["reset_in"])

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP from request, handling proxies.

        Args:
            request: FastAPI Request object

        Returns:
            Client IP address
        """
        # Check X-Forwarded-For header (from reverse proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in the list is the original client
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct connection
        if request.client:
            return request.client.host

        return "unknown"

    async def reset_user(self, user_id: str) -> int:
        """
        Reset all rate limits for a user.

        Args:
            user_id: The user ID

        Returns:
            Number of keys deleted
        """
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"ratelimit:user:{user_id}:*", count=100
            )
            if keys:
                deleted += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return deleted

    async def reset_ip(self, ip_address: str) -> int:
        """
        Reset all rate limits for an IP.

        Args:
            ip_address: The IP address

        Returns:
            Number of keys deleted
        """
        cursor = 0
        deleted = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"ratelimit:ip:{ip_address}:*", count=100
            )
            if keys:
                deleted += await self._redis.delete(*keys)
            if cursor == 0:
                break
        return deleted

    async def get_stats(self, user_id: Optional[str] = None) -> dict:
        """
        Get rate limit stats for a user or globally.

        Args:
            user_id: Optional user ID (global stats if None)

        Returns:
            Dict with rate limit statistics
        """
        if user_id:
            pattern = f"ratelimit:user:{user_id}:*"
        else:
            pattern = "ratelimit:*"

        stats = {"endpoints": {}, "total_requests": 0}

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                count = await self._redis.get(key)
                if count:
                    # Extract endpoint from key
                    parts = key.split(":")
                    endpoint = parts[-1] if parts else "unknown"
                    stats["endpoints"][endpoint] = int(count)
                    stats["total_requests"] += int(count)
            if cursor == 0:
                break

        return stats


# FastAPI dependency for rate limiting
class RateLimitDependency:
    """
    FastAPI dependency for rate limiting.

    Usage:
        @app.get("/endpoint")
        async def endpoint(
            rate_limit: dict = Depends(RateLimitDependency(redis_client))
        ):
            ...
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        limits: Optional[dict[str, RateLimitConfig]] = None,
    ):
        """
        Initialize dependency.

        Args:
            redis_client: Async Redis client
            limits: Optional custom rate limits
        """
        self._limiter = RateLimiter(redis_client, limits)

    async def __call__(
        self,
        request: Request,
        user_id: Optional[str] = None,
    ) -> dict:
        """
        Check rate limit.

        Args:
            request: FastAPI Request object
            user_id: Optional user ID

        Returns:
            Rate limit info dict
        """
        return await self._limiter.check(request, user_id)
