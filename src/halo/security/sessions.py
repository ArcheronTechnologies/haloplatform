"""
Session management for Halo platform.

Implements Redis-backed session management with:
- Concurrent session limits per user
- Session revocation (for incident response)
- Device fingerprinting
- Token hashing for secure storage

Per security framework section 2.2.
"""

import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as redis

from halo.config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Redis-backed session management.

    Security features:
    - Max sessions per user (default: 3)
    - Tokens hashed before storage
    - Session metadata for audit
    - Emergency revocation support
    """

    MAX_SESSIONS_PER_USER = 3
    ACCESS_TOKEN_TTL = 1800  # 30 minutes
    REFRESH_TOKEN_TTL = 604800  # 7 days

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize session manager.

        Args:
            redis_client: Async Redis client
        """
        self._redis = redis_client

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token for secure storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def create_session(
        self,
        user_id: str,
        ip_address: str,
        user_agent: str,
        device_fingerprint: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Create a new session for a user.

        Enforces concurrent session limit by removing oldest sessions.

        Args:
            user_id: User's unique identifier
            ip_address: Client IP address
            user_agent: Client user agent string
            device_fingerprint: Optional device fingerprint

        Returns:
            Tuple of (access_token, refresh_token)
        """
        # Enforce session limit
        await self._enforce_session_limit(user_id)

        # Generate tokens
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(64)

        # Hash tokens for storage
        access_hash = self._hash_token(access_token)
        refresh_hash = self._hash_token(refresh_token)

        # Session metadata
        session_data = {
            "user_id": user_id,
            "ip": ip_address,
            "ua": user_agent,
            "fp": device_fingerprint,
            "created_at": datetime.utcnow().isoformat(),
            "refresh_hash": refresh_hash,
        }

        # Store access token session
        await self._redis.setex(
            f"session:{access_hash}",
            self.ACCESS_TOKEN_TTL,
            json.dumps(session_data),
        )

        # Store refresh token (longer TTL)
        refresh_data = {
            "user_id": user_id,
            "access_hash": access_hash,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self._redis.setex(
            f"refresh:{refresh_hash}",
            self.REFRESH_TOKEN_TTL,
            json.dumps(refresh_data),
        )

        # Track user's active sessions
        await self._redis.sadd(f"user:sessions:{user_id}", access_hash)
        await self._redis.expire(f"user:sessions:{user_id}", self.REFRESH_TOKEN_TTL)

        logger.info(f"Created session for user {user_id} from {ip_address}")

        return access_token, refresh_token

    async def validate_session(self, access_token: str) -> Optional[dict]:
        """
        Validate an access token and return session data.

        Args:
            access_token: The access token to validate

        Returns:
            Session data dict if valid, None otherwise
        """
        access_hash = self._hash_token(access_token)
        session_json = await self._redis.get(f"session:{access_hash}")

        if not session_json:
            return None

        return json.loads(session_json)

    async def refresh_session(
        self, refresh_token: str, ip_address: str, user_agent: str
    ) -> Optional[tuple[str, str]]:
        """
        Refresh a session using a refresh token.

        Args:
            refresh_token: The refresh token
            ip_address: Current client IP
            user_agent: Current user agent

        Returns:
            New (access_token, refresh_token) tuple if valid, None otherwise
        """
        refresh_hash = self._hash_token(refresh_token)
        refresh_json = await self._redis.get(f"refresh:{refresh_hash}")

        if not refresh_json:
            return None

        refresh_data = json.loads(refresh_json)
        user_id = refresh_data["user_id"]

        # Revoke old tokens
        old_access_hash = refresh_data.get("access_hash")
        if old_access_hash:
            await self._redis.delete(f"session:{old_access_hash}")
            await self._redis.srem(f"user:sessions:{user_id}", old_access_hash)

        await self._redis.delete(f"refresh:{refresh_hash}")

        # Create new session
        return await self.create_session(user_id, ip_address, user_agent)

    async def revoke_session(self, access_token: str) -> bool:
        """
        Revoke a single session.

        Args:
            access_token: The access token to revoke

        Returns:
            True if session was revoked, False if not found
        """
        access_hash = self._hash_token(access_token)
        session_json = await self._redis.get(f"session:{access_hash}")

        if not session_json:
            return False

        session_data = json.loads(session_json)
        user_id = session_data["user_id"]
        refresh_hash = session_data.get("refresh_hash")

        # Delete session and refresh token
        await self._redis.delete(f"session:{access_hash}")
        if refresh_hash:
            await self._redis.delete(f"refresh:{refresh_hash}")
        await self._redis.srem(f"user:sessions:{user_id}", access_hash)

        logger.info(f"Revoked session for user {user_id}")
        return True

    async def revoke_all_sessions(self, user_id: str) -> int:
        """
        Revoke all sessions for a user (emergency revocation).

        Use this for incident response when credentials may be compromised.

        Args:
            user_id: The user whose sessions to revoke

        Returns:
            Number of sessions revoked
        """
        sessions = await self._redis.smembers(f"user:sessions:{user_id}")
        count = 0

        for access_hash in sessions:
            # Get session to find refresh token
            if isinstance(access_hash, bytes):
                access_hash = access_hash.decode()

            session_json = await self._redis.get(f"session:{access_hash}")
            if session_json:
                session_data = json.loads(session_json)
                refresh_hash = session_data.get("refresh_hash")
                if refresh_hash:
                    await self._redis.delete(f"refresh:{refresh_hash}")

            await self._redis.delete(f"session:{access_hash}")
            count += 1

        await self._redis.delete(f"user:sessions:{user_id}")

        logger.warning(f"Emergency revocation: revoked {count} sessions for user {user_id}")
        return count

    async def get_active_sessions(self, user_id: str) -> list[dict]:
        """
        Get all active sessions for a user.

        Args:
            user_id: The user ID

        Returns:
            List of session metadata dicts
        """
        sessions = await self._redis.smembers(f"user:sessions:{user_id}")
        result = []

        for access_hash in sessions:
            if isinstance(access_hash, bytes):
                access_hash = access_hash.decode()

            session_json = await self._redis.get(f"session:{access_hash}")
            if session_json:
                session_data = json.loads(session_json)
                # Don't expose refresh hash
                session_data.pop("refresh_hash", None)
                session_data["session_id"] = access_hash[:8]  # Truncated for display
                result.append(session_data)

        return result

    async def _enforce_session_limit(self, user_id: str) -> None:
        """
        Enforce max sessions per user by removing oldest sessions.

        Args:
            user_id: The user ID
        """
        sessions = await self._redis.smembers(f"user:sessions:{user_id}")

        if len(sessions) >= self.MAX_SESSIONS_PER_USER:
            # Get session creation times
            session_times = []
            for access_hash in sessions:
                if isinstance(access_hash, bytes):
                    access_hash = access_hash.decode()

                session_json = await self._redis.get(f"session:{access_hash}")
                if session_json:
                    session_data = json.loads(session_json)
                    created_at = session_data.get("created_at", "")
                    session_times.append((access_hash, created_at))

            # Sort by creation time (oldest first)
            session_times.sort(key=lambda x: x[1])

            # Remove oldest sessions to make room
            to_remove = len(sessions) - self.MAX_SESSIONS_PER_USER + 1
            for i in range(to_remove):
                access_hash = session_times[i][0]
                session_json = await self._redis.get(f"session:{access_hash}")
                if session_json:
                    session_data = json.loads(session_json)
                    refresh_hash = session_data.get("refresh_hash")
                    if refresh_hash:
                        await self._redis.delete(f"refresh:{refresh_hash}")

                await self._redis.delete(f"session:{access_hash}")
                await self._redis.srem(f"user:sessions:{user_id}", access_hash)

            logger.info(f"Removed {to_remove} old session(s) for user {user_id}")


# Global session manager instance
_session_manager: Optional[SessionManager] = None


async def get_session_manager(request) -> SessionManager:
    """
    FastAPI dependency to get session manager.

    Gets Redis client from request state and creates/caches SessionManager.
    """
    global _session_manager
    if _session_manager is None:
        redis_client = request.app.state.redis
        _session_manager = SessionManager(redis_client)
    return _session_manager
