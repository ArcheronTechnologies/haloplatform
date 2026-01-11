"""
Account lockout management for Halo platform.

Implements combined IP + user lockout to prevent both:
- Brute force attacks (per-IP limiting)
- Targeted attacks (per-user limiting)
- DoS via lockout (using CAPTCHA instead of hard lockout for early attempts)

Per security framework section 2.3.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class LockoutAction(str, Enum):
    """Actions to take based on lockout state."""

    ALLOW = "allow"
    CAPTCHA = "captcha"
    BLOCK = "block"


@dataclass
class LockoutResult:
    """Result of a lockout check."""

    action: LockoutAction
    reason: Optional[str] = None
    notify_user: bool = False
    remaining_attempts: Optional[int] = None
    block_expires_in: Optional[int] = None  # seconds


class LockoutManager:
    """
    Combined IP + user lockout to prevent brute force and DoS.

    Strategy:
    - Per-IP: Stops distributed brute force
    - Per-user: Stops targeted attacks, but uses CAPTCHA not lockout early
      to prevent DoS via intentional lockout
    """

    # Per-IP thresholds
    IP_CAPTCHA_THRESHOLD = 10
    IP_BLOCK_THRESHOLD = 50
    IP_BLOCK_DURATION = 3600  # 1 hour
    IP_WINDOW = 3600  # 1 hour window

    # Per-user thresholds
    USER_CAPTCHA_THRESHOLD = 3
    USER_NOTIFY_THRESHOLD = 5  # Alert legitimate user
    USER_BLOCK_THRESHOLD = 10  # Only after many failures
    USER_BLOCK_DURATION = 1800  # 30 minutes
    USER_WINDOW = 3600  # 1 hour window

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize lockout manager.

        Args:
            redis_client: Async Redis client
        """
        self._redis = redis_client

    async def check_and_record(
        self, username: str, ip_address: str, success: bool
    ) -> LockoutResult:
        """
        Check lockout status and record attempt.

        Call this after every authentication attempt (success or failure).

        Args:
            username: The username attempting login
            ip_address: The client IP address
            success: Whether the attempt succeeded

        Returns:
            LockoutResult indicating what action to take
        """
        if success:
            # Clear user failures on success (keep IP failures as they may be probing)
            await self._redis.delete(f"lockout:failures:user:{username}")
            logger.info(f"Successful login for {username} from {ip_address}")
            return LockoutResult(action=LockoutAction.ALLOW)

        # Check if already blocked
        ip_blocked = await self._redis.get(f"lockout:blocked:ip:{ip_address}")
        if ip_blocked:
            ttl = await self._redis.ttl(f"lockout:blocked:ip:{ip_address}")
            logger.warning(f"Blocked IP {ip_address} attempted login for {username}")
            return LockoutResult(
                action=LockoutAction.BLOCK,
                reason="ip_blocked",
                block_expires_in=ttl,
            )

        user_blocked = await self._redis.get(f"lockout:blocked:user:{username}")
        if user_blocked:
            ttl = await self._redis.ttl(f"lockout:blocked:user:{username}")
            logger.warning(f"Blocked user {username} attempted login from {ip_address}")
            return LockoutResult(
                action=LockoutAction.BLOCK,
                reason="user_blocked",
                block_expires_in=ttl,
            )

        # Record failure
        ip_key = f"lockout:failures:ip:{ip_address}"
        user_key = f"lockout:failures:user:{username}"

        ip_failures = await self._redis.incr(ip_key)
        await self._redis.expire(ip_key, self.IP_WINDOW)

        user_failures = await self._redis.incr(user_key)
        await self._redis.expire(user_key, self.USER_WINDOW)

        logger.info(
            f"Failed login for {username} from {ip_address} "
            f"(IP: {ip_failures}, User: {user_failures})"
        )

        # Check if should block
        if ip_failures >= self.IP_BLOCK_THRESHOLD:
            await self._redis.setex(
                f"lockout:blocked:ip:{ip_address}",
                self.IP_BLOCK_DURATION,
                "1",
            )
            logger.warning(f"Blocking IP {ip_address} after {ip_failures} failures")
            return LockoutResult(
                action=LockoutAction.BLOCK,
                reason="ip_blocked",
                block_expires_in=self.IP_BLOCK_DURATION,
            )

        if user_failures >= self.USER_BLOCK_THRESHOLD:
            await self._redis.setex(
                f"lockout:blocked:user:{username}",
                self.USER_BLOCK_DURATION,
                "1",
            )
            logger.warning(f"Blocking user {username} after {user_failures} failures")
            return LockoutResult(
                action=LockoutAction.BLOCK,
                reason="user_blocked",
                notify_user=True,
                block_expires_in=self.USER_BLOCK_DURATION,
            )

        # Check if should require CAPTCHA
        if (
            ip_failures >= self.IP_CAPTCHA_THRESHOLD
            or user_failures >= self.USER_CAPTCHA_THRESHOLD
        ):
            remaining = min(
                self.IP_BLOCK_THRESHOLD - ip_failures,
                self.USER_BLOCK_THRESHOLD - user_failures,
            )
            notify = user_failures >= self.USER_NOTIFY_THRESHOLD
            return LockoutResult(
                action=LockoutAction.CAPTCHA,
                reason="too_many_failures",
                notify_user=notify,
                remaining_attempts=remaining,
            )

        # Allow but track remaining attempts
        remaining = min(
            self.IP_CAPTCHA_THRESHOLD - ip_failures,
            self.USER_CAPTCHA_THRESHOLD - user_failures,
        )
        return LockoutResult(
            action=LockoutAction.ALLOW,
            remaining_attempts=remaining,
        )

    async def get_lockout_status(
        self, username: str, ip_address: str
    ) -> dict:
        """
        Get current lockout status without recording an attempt.

        Args:
            username: The username
            ip_address: The client IP

        Returns:
            Dict with lockout status information
        """
        ip_failures = await self._redis.get(f"lockout:failures:ip:{ip_address}")
        user_failures = await self._redis.get(f"lockout:failures:user:{username}")
        ip_blocked = await self._redis.get(f"lockout:blocked:ip:{ip_address}")
        user_blocked = await self._redis.get(f"lockout:blocked:user:{username}")

        return {
            "ip_failures": int(ip_failures) if ip_failures else 0,
            "user_failures": int(user_failures) if user_failures else 0,
            "ip_blocked": bool(ip_blocked),
            "user_blocked": bool(user_blocked),
            "ip_blocked_ttl": await self._redis.ttl(f"lockout:blocked:ip:{ip_address}")
            if ip_blocked
            else None,
            "user_blocked_ttl": await self._redis.ttl(f"lockout:blocked:user:{username}")
            if user_blocked
            else None,
        }

    async def unblock_user(self, username: str) -> bool:
        """
        Manually unblock a user (admin action).

        Args:
            username: The username to unblock

        Returns:
            True if user was blocked and is now unblocked
        """
        result = await self._redis.delete(
            f"lockout:blocked:user:{username}",
            f"lockout:failures:user:{username}",
        )
        if result:
            logger.info(f"Admin unblocked user {username}")
        return result > 0

    async def unblock_ip(self, ip_address: str) -> bool:
        """
        Manually unblock an IP (admin action).

        Args:
            ip_address: The IP to unblock

        Returns:
            True if IP was blocked and is now unblocked
        """
        result = await self._redis.delete(
            f"lockout:blocked:ip:{ip_address}",
            f"lockout:failures:ip:{ip_address}",
        )
        if result:
            logger.info(f"Admin unblocked IP {ip_address}")
        return result > 0

    async def get_blocked_ips(self, limit: int = 100) -> list[str]:
        """
        Get list of currently blocked IPs.

        Args:
            limit: Max number of IPs to return

        Returns:
            List of blocked IP addresses
        """
        cursor = 0
        blocked = []
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match="lockout:blocked:ip:*", count=100
            )
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                ip = key.replace("lockout:blocked:ip:", "")
                blocked.append(ip)
                if len(blocked) >= limit:
                    return blocked
            if cursor == 0:
                break
        return blocked

    async def get_blocked_users(self, limit: int = 100) -> list[str]:
        """
        Get list of currently blocked users.

        Args:
            limit: Max number of users to return

        Returns:
            List of blocked usernames
        """
        cursor = 0
        blocked = []
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match="lockout:blocked:user:*", count=100
            )
            for key in keys:
                if isinstance(key, bytes):
                    key = key.decode()
                username = key.replace("lockout:blocked:user:", "")
                blocked.append(username)
                if len(blocked) >= limit:
                    return blocked
            if cursor == 0:
                break
        return blocked


# Global lockout manager instance
_lockout_manager: Optional[LockoutManager] = None


async def get_lockout_manager(request) -> LockoutManager:
    """
    FastAPI dependency to get lockout manager.

    Gets Redis client from request state and creates/caches LockoutManager.
    """
    global _lockout_manager
    if _lockout_manager is None:
        redis_client = request.app.state.redis
        _lockout_manager = LockoutManager(redis_client)
    return _lockout_manager


# Alias for compatibility
LockoutStatus = LockoutAction
