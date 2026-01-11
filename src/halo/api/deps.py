"""
FastAPI dependencies for the API.

Provides:
- Database session management
- JWT-based authentication
- Session-based authentication
- Role-based authorization
- Audit logging
"""

import logging
from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from halo.config import settings
from halo.db.repositories import (
    AlertRepository,
    AuditLogRepository,
    CaseRepository,
    EntityRepository,
    RelationshipRepository,
    UserRepository,
)
from halo.security.auth import (
    AuthenticationError,
    AuthorizationError,
    User as AuthUser,
    UserRole,
    verify_access_token,
    require_role,
    require_permission,
)
from halo.security.sessions import SessionManager, get_session_manager

logger = logging.getLogger(__name__)


# HTTP Bearer token extractor
security = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session from request state.

    Uses the session factory stored during app startup.
    """
    async with request.app.state.db_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    request: Request,
    # Development fallback headers (only work when not in production)
    x_user_id: Annotated[Optional[str], Header()] = None,
    x_user_name: Annotated[Optional[str], Header()] = None,
    x_user_role: Annotated[Optional[str], Header()] = None,
) -> AuthUser:
    """
    Get current authenticated user from JWT token.

    In development mode, also accepts X-User-* headers for testing.
    In production, ONLY JWT tokens are accepted.

    Raises:
        HTTPException: 401 if not authenticated
    """
    # Try JWT authentication first
    if credentials:
        try:
            token_payload = verify_access_token(credentials.credentials)

            # In production, fetch full user from database
            # For now, construct from token payload
            return AuthUser(
                id=token_payload.sub,
                username=token_payload.sub,  # Would be fetched from DB
                role=token_payload.role,
                is_active=True,
            )
        except AuthenticationError as e:
            logger.warning(f"JWT authentication failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from e

    # Development fallback: accept headers (NOT in production)
    if not settings.is_production and x_user_id:
        logger.warning(
            f"Using development header auth for user: {x_user_id}. "
            "This is disabled in production!"
        )
        role = UserRole.VIEWER
        if x_user_role:
            try:
                role = UserRole(x_user_role)
            except ValueError:
                role = UserRole.VIEWER

        return AuthUser(
            id=x_user_id,
            username=x_user_id,
            full_name=x_user_name,
            role=role,
            is_active=True,
        )

    # No authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user_optional(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    request: Request,
    x_user_id: Annotated[Optional[str], Header()] = None,
    x_user_name: Annotated[Optional[str], Header()] = None,
    x_user_role: Annotated[Optional[str], Header()] = None,
) -> Optional[AuthUser]:
    """
    Get current user if authenticated, or None.

    Use this for endpoints that can work with or without authentication.
    """
    try:
        return await get_current_user(
            credentials, request, x_user_id, x_user_name, x_user_role
        )
    except HTTPException:
        return None


# Type aliases for dependency injection
User = Annotated[AuthUser, Depends(get_current_user)]
OptionalUser = Annotated[Optional[AuthUser], Depends(get_current_user_optional)]


async def get_current_user_from_session(
    request: Request,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> AuthUser:
    """
    Get current user from session token.

    Checks Authorization header (Bearer token) or session_token cookie.

    Raises:
        HTTPException: 401 if not authenticated
    """
    # Extract token from header or cookie
    token = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    else:
        token = request.cookies.get("session_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autentisering krävs",  # "Authentication required"
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate session
    session_data = await session_manager.validate_session(token)

    if not session_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ogiltig eller utgången session",  # "Invalid or expired session"
            headers={"WWW-Authenticate": "Bearer"},
        )

    # In production, fetch full user from database using user_id
    # For now, construct minimal user from session data
    return AuthUser(
        id=session_data["user_id"],
        username=session_data["user_id"],  # Would be fetched from DB
        role=UserRole.VIEWER,  # Would be fetched from DB
        is_active=True,
    )


async def get_current_user_from_session_optional(
    request: Request,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> Optional[AuthUser]:
    """Get current user from session if present, or None."""
    try:
        return await get_current_user_from_session(request, session_manager)
    except HTTPException:
        return None


# Session-based user types
SessionUser = Annotated[AuthUser, Depends(get_current_user_from_session)]
OptionalSessionUser = Annotated[Optional[AuthUser], Depends(get_current_user_from_session_optional)]


# Role-based dependencies
async def require_analyst(user: User) -> AuthUser:
    """Require at least analyst role."""
    try:
        require_role(user, UserRole.ANALYST)
        return user
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def require_senior_analyst(user: User) -> AuthUser:
    """Require at least senior analyst role (for Tier 3 approvals)."""
    try:
        require_role(user, UserRole.SENIOR_ANALYST)
        return user
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def require_admin(user: User) -> AuthUser:
    """Require admin role."""
    try:
        require_role(user, UserRole.ADMIN)
        return user
    except AuthorizationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


# Role-checked user types
AnalystUser = Annotated[AuthUser, Depends(require_analyst)]
SeniorAnalystUser = Annotated[AuthUser, Depends(require_senior_analyst)]
AdminUser = Annotated[AuthUser, Depends(require_admin)]


def get_entity_repo(session: DbSession) -> EntityRepository:
    """Get entity repository."""
    return EntityRepository(session)


def get_relationship_repo(session: DbSession) -> RelationshipRepository:
    """Get relationship repository."""
    return RelationshipRepository(session)


def get_alert_repo(session: DbSession) -> AlertRepository:
    """Get alert repository."""
    return AlertRepository(session)


def get_audit_repo(session: DbSession) -> AuditLogRepository:
    """Get audit log repository."""
    return AuditLogRepository(session)


def get_case_repo(session: DbSession) -> CaseRepository:
    """Get case repository."""
    return CaseRepository(session)


def get_user_repo(session: DbSession) -> UserRepository:
    """Get user repository."""
    return UserRepository(session)


# Type aliases for repositories
EntityRepo = Annotated[EntityRepository, Depends(get_entity_repo)]
RelationshipRepo = Annotated[RelationshipRepository, Depends(get_relationship_repo)]
AlertRepo = Annotated[AlertRepository, Depends(get_alert_repo)]
AuditRepo = Annotated[AuditLogRepository, Depends(get_audit_repo)]
CaseRepo = Annotated[CaseRepository, Depends(get_case_repo)]
UserRepo = Annotated[UserRepository, Depends(get_user_repo)]
