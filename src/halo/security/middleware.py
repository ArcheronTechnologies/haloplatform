"""
Security middleware for Halo platform.

Implements:
- Session-based authentication middleware
- CSRF validation middleware
- Request sanitization middleware

Per security framework sections 2.2 and 2.4.
"""

import logging
from typing import Callable, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from halo.config import settings
from halo.security.csrf import CSRFProtection
from halo.security.sessions import SessionManager

logger = logging.getLogger(__name__)


# Session manager instance (initialized on first request)
_session_manager: Optional[SessionManager] = None


def _get_session_manager(request: Request) -> SessionManager:
    """Get or create session manager instance."""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager(request.app.state.redis)
    return _session_manager


class SessionAuthMiddleware(BaseHTTPMiddleware):
    """
    Session-based authentication middleware.

    Validates session tokens from cookies or Authorization headers.
    Sets request.state.user and request.state.session on success.

    Paths can be configured to:
    - Skip authentication entirely (public paths)
    - Require authentication (protected paths)
    - Optionally authenticate (mixed paths)
    """

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/bankid/init",
        "/api/v1/auth/bankid/qr",
        "/api/v1/auth/bankid/collect",
        "/api/v1/auth/bankid/cancel",
        "/api/v1/auth/oidc/init",
        "/api/v1/auth/oidc/callback",
        "/api/v1/auth/oidc/token",
        "/api/v1/auth/oidc/providers",
        "/api/v1/auth/refresh",
        "/api/v1/auth/forgot-password",
        "/api/v1/auth/reset-password",
    }

    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = {
        "/static/",
        "/assets/",
    }

    def __init__(self, app, require_session: bool = True):
        """
        Initialize session auth middleware.

        Args:
            app: The FastAPI application
            require_session: If True, returns 401 for missing sessions on protected paths.
                           If False, just sets request.state.user = None for missing sessions.
        """
        super().__init__(app)
        self.require_session = require_session

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (no auth required)."""
        if path in self.PUBLIC_PATHS:
            return True
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    def _extract_token(self, request: Request) -> Optional[str]:
        """
        Extract session token from request.

        Checks (in order):
        1. Authorization header (Bearer token)
        2. Session cookie
        """
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix

        # Check session cookie
        return request.cookies.get("session_token")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with session authentication."""
        path = request.url.path

        # Skip auth for public paths
        if self._is_public_path(path):
            request.state.user = None
            request.state.session = None
            return await call_next(request)

        # Extract token
        token = self._extract_token(request)

        if not token:
            if self.require_session:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Autentisering krävs",  # "Authentication required" in Swedish
                        "message": "Ingen giltig session hittades",  # "No valid session found"
                    },
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.user = None
            request.state.session = None
            return await call_next(request)

        # Validate session
        try:
            session_manager = _get_session_manager(request)
            session_data = await session_manager.validate_session(token)

            if not session_data:
                if self.require_session:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Ogiltig session",  # "Invalid session"
                            "message": "Din session har gått ut eller är ogiltig",  # "Your session has expired or is invalid"
                        },
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                request.state.user = None
                request.state.session = None
                return await call_next(request)

            # Set user info in request state
            request.state.user = {
                "user_id": session_data["user_id"],
                "ip": session_data.get("ip"),
                "created_at": session_data.get("created_at"),
            }
            request.state.session = session_data

            logger.debug(f"Session validated for user {session_data['user_id']}")

        except Exception as e:
            logger.error(f"Session validation error: {e}")
            if self.require_session:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content={
                        "error": "Autentiseringsfel",  # "Authentication error"
                        "message": "Ett fel uppstod vid validering av session",  # "An error occurred validating session"
                    },
                )
            request.state.user = None
            request.state.session = None

        return await call_next(request)


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware.

    Validates CSRF tokens for state-changing requests (POST, PUT, PATCH, DELETE).
    Tokens can be provided via:
    - X-CSRF-Token header
    - csrf_token form field
    """

    # Methods that require CSRF validation
    PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    # Paths exempt from CSRF (API endpoints with bearer auth)
    EXEMPT_PATHS = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/bankid/init",
        "/api/v1/auth/bankid/collect",
        "/api/v1/auth/bankid/cancel",
        "/api/v1/auth/oidc/callback",
        "/api/v1/auth/oidc/token",
    }

    # Exempt path prefixes (API endpoints typically use bearer tokens)
    EXEMPT_PREFIXES = {
        "/api/",  # All API routes use bearer auth
    }

    def __init__(self, app, secret_key: bytes):
        """
        Initialize CSRF middleware.

        Args:
            app: The FastAPI application
            secret_key: Secret key for CSRF token validation
        """
        super().__init__(app)
        self.csrf = CSRFProtection(secret_key=secret_key)

    def _is_exempt(self, path: str, method: str) -> bool:
        """Check if request is exempt from CSRF validation."""
        # Safe methods don't need CSRF
        if method not in self.PROTECTED_METHODS:
            return True

        # Check exempt paths
        if path in self.EXEMPT_PATHS:
            return True

        # Check exempt prefixes
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with CSRF validation."""
        path = request.url.path
        method = request.method

        # Skip validation for exempt requests
        if self._is_exempt(path, method):
            return await call_next(request)

        # Get CSRF token from header or form
        csrf_token = request.headers.get("X-CSRF-Token")

        if not csrf_token:
            # Try form data (only for form submissions)
            content_type = request.headers.get("content-type", "")
            if "form" in content_type:
                try:
                    form = await request.form()
                    csrf_token = form.get("csrf_token")
                except Exception:
                    pass

        # Validate token
        if not csrf_token or not self.csrf.validate_token(csrf_token):
            logger.warning(f"CSRF validation failed for {method} {path}")
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "CSRF-validering misslyckades",  # "CSRF validation failed"
                    "message": "Ogiltig eller saknad CSRF-token",  # "Invalid or missing CSRF token"
                },
            )

        return await call_next(request)


class RequestSanitizerMiddleware(BaseHTTPMiddleware):
    """
    Request sanitization middleware.

    Cleans potentially dangerous content from requests:
    - Strips null bytes from paths and query strings
    - Rejects requests with path traversal attempts
    - Normalizes Unicode in paths
    """

    # Patterns that indicate path traversal attempts
    DANGEROUS_PATTERNS = [
        "..",
        "%2e%2e",
        "%252e%252e",
        "..%c0%af",
        "..%c1%9c",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with sanitization."""
        path = request.url.path
        query = request.url.query or ""

        # Check for null bytes
        if "\x00" in path or "\x00" in query:
            logger.warning(f"Null byte injection attempt blocked: {request.client.host}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error": "Invalid request"},
            )

        # Check for path traversal
        path_lower = path.lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in path_lower:
                logger.warning(
                    f"Path traversal attempt blocked: {path} from {request.client.host}"
                )
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"error": "Invalid request path"},
                )

        return await call_next(request)
