"""
Authentication and Authorization for Halo Platform.

Implements:
- JWT token-based authentication
- Password hashing with Argon2
- Role-based access control (RBAC)
- User session management

Note: For production Swedish law enforcement use, this should be
integrated with BankID or SITHS card authentication.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from halo.config import settings

logger = logging.getLogger(__name__)


# Password hasher (Argon2id - recommended for high security)
ph = PasswordHasher(
    time_cost=3,        # Number of iterations
    memory_cost=65536,  # 64 MB
    parallelism=4,      # Number of parallel threads
    hash_len=32,        # Hash output length
    salt_len=16,        # Salt length
)


class UserRole(str, Enum):
    """User roles for RBAC."""
    VIEWER = "viewer"           # Read-only access
    ANALYST = "analyst"         # Can create cases, acknowledge alerts
    SENIOR_ANALYST = "senior_analyst"  # Can approve Tier 3 alerts
    ADMIN = "admin"             # Full system access
    SYSTEM = "system"           # System/service accounts


class TokenType(str, Enum):
    """Types of JWT tokens."""
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str                          # User ID
    type: TokenType                   # Token type
    role: UserRole                    # User role
    exp: datetime                     # Expiration time
    iat: datetime = Field(default_factory=datetime.utcnow)  # Issued at
    jti: Optional[str] = None         # JWT ID (for token revocation)


class User(BaseModel):
    """User model for authentication context."""
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    last_login: Optional[datetime] = None

    # Permissions (derived from role)
    @property
    def can_view_entities(self) -> bool:
        return self.role in [UserRole.VIEWER, UserRole.ANALYST, UserRole.SENIOR_ANALYST, UserRole.ADMIN]

    @property
    def can_create_cases(self) -> bool:
        return self.role in [UserRole.ANALYST, UserRole.SENIOR_ANALYST, UserRole.ADMIN]

    @property
    def can_acknowledge_alerts(self) -> bool:
        return self.role in [UserRole.ANALYST, UserRole.SENIOR_ANALYST, UserRole.ADMIN]

    @property
    def can_approve_tier3(self) -> bool:
        """Tier 3 approval requires senior analyst or admin role."""
        return self.role in [UserRole.SENIOR_ANALYST, UserRole.ADMIN]

    @property
    def can_export_data(self) -> bool:
        return self.role in [UserRole.SENIOR_ANALYST, UserRole.ADMIN]

    @property
    def can_manage_users(self) -> bool:
        return self.role == UserRole.ADMIN


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class AuthorizationError(Exception):
    """Raised when authorization fails."""
    pass


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
    return ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        password: Plain text password to verify
        hashed: Hashed password to check against

    Returns:
        True if password matches, False otherwise
    """
    try:
        ph.verify(hashed, password)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(
    user: User,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        user: User to create token for
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)

    expire = datetime.utcnow() + expires_delta

    payload = TokenPayload(
        sub=user.id,
        type=TokenType.ACCESS,
        role=user.role,
        exp=expire,
    )

    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(
    user: User,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT refresh token.

    Args:
        user: User to create token for
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token string
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.refresh_token_expire_days)

    expire = datetime.utcnow() + expires_delta

    payload = TokenPayload(
        sub=user.id,
        type=TokenType.REFRESH,
        role=user.role,
        exp=expire,
    )

    return jwt.encode(
        payload.model_dump(mode="json"),
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**payload)
    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        raise AuthenticationError("Invalid or expired token") from e


def verify_access_token(token: str) -> TokenPayload:
    """
    Verify an access token.

    Args:
        token: JWT access token

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid, expired, or wrong type
    """
    payload = decode_token(token)

    if payload.type != TokenType.ACCESS:
        raise AuthenticationError("Invalid token type")

    return payload


def verify_refresh_token(token: str) -> TokenPayload:
    """
    Verify a refresh token.

    Args:
        token: JWT refresh token

    Returns:
        Decoded token payload

    Raises:
        AuthenticationError: If token is invalid, expired, or wrong type
    """
    payload = decode_token(token)

    if payload.type != TokenType.REFRESH:
        raise AuthenticationError("Invalid token type")

    return payload


def require_role(user: User, required_role: UserRole) -> None:
    """
    Check if user has the required role or higher.

    Args:
        user: User to check
        required_role: Minimum required role

    Raises:
        AuthorizationError: If user doesn't have required role
    """
    role_hierarchy = {
        UserRole.VIEWER: 0,
        UserRole.ANALYST: 1,
        UserRole.SENIOR_ANALYST: 2,
        UserRole.ADMIN: 3,
        UserRole.SYSTEM: 4,
    }

    if role_hierarchy.get(user.role, -1) < role_hierarchy.get(required_role, 99):
        raise AuthorizationError(
            f"Insufficient permissions. Required: {required_role.value}, "
            f"Current: {user.role.value}"
        )


def require_permission(user: User, permission: str) -> None:
    """
    Check if user has a specific permission.

    Args:
        user: User to check
        permission: Permission name (e.g., 'can_approve_tier3')

    Raises:
        AuthorizationError: If user doesn't have the permission
    """
    if not hasattr(user, permission):
        raise AuthorizationError(f"Unknown permission: {permission}")

    if not getattr(user, permission):
        raise AuthorizationError(f"Permission denied: {permission}")
