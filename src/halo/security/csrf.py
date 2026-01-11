"""
CSRF protection for Halo platform.

Implements double-submit cookie pattern for CSRF protection.
Required for state-changing operations on the API.

Per security framework section 6.2.
"""

import hmac
import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, Request, Response

from halo.config import settings

logger = logging.getLogger(__name__)


class CSRFProtection:
    """
    Double-submit cookie CSRF protection.

    Token format: {timestamp}.{random}.{signature}
    - Timestamp allows expiration
    - Random provides uniqueness
    - Signature prevents forgery
    """

    TOKEN_LIFETIME = 3600  # 1 hour
    COOKIE_NAME = "csrf_token"
    HEADER_NAME = "X-CSRF-Token"

    def __init__(self, secret_key: Optional[bytes] = None):
        """
        Initialize CSRF protection.

        Args:
            secret_key: Key for signing tokens. If None, uses settings.secret_key
        """
        if secret_key is None:
            key = settings.secret_key
            if isinstance(key, str):
                key = key.encode()
            self._key = key
        else:
            self._key = secret_key

    def generate_token(self) -> str:
        """
        Generate a new CSRF token.

        Returns:
            Signed token string
        """
        timestamp = int(datetime.utcnow().timestamp())
        random_part = secrets.token_urlsafe(32)
        message = f"{timestamp}.{random_part}"
        signature = hmac.new(self._key, message.encode(), "sha256").hexdigest()[:16]
        return f"{message}.{signature}"

    def validate_token(self, token: str) -> bool:
        """
        Validate a CSRF token.

        Args:
            token: The token to validate

        Returns:
            True if valid, False otherwise
        """
        if not token:
            return False

        parts = token.split(".")
        if len(parts) != 3:
            return False

        timestamp_str, random_part, signature = parts

        # Check signature
        message = f"{timestamp_str}.{random_part}"
        expected_sig = hmac.new(self._key, message.encode(), "sha256").hexdigest()[:16]
        if not hmac.compare_digest(signature, expected_sig):
            return False

        # Check expiration
        try:
            timestamp = int(timestamp_str)
        except ValueError:
            return False

        now = int(datetime.utcnow().timestamp())
        if now - timestamp > self.TOKEN_LIFETIME:
            return False

        return True

    def set_token_cookie(self, response: Response, token: str) -> None:
        """
        Set CSRF token cookie on response.

        Args:
            response: FastAPI Response object
            token: The CSRF token
        """
        response.set_cookie(
            key=self.COOKIE_NAME,
            value=token,
            max_age=self.TOKEN_LIFETIME,
            httponly=False,  # Must be readable by JS
            samesite="strict",
            secure=settings.is_production,
        )

    async def verify(self, request: Request) -> None:
        """
        Verify CSRF token on request.

        Safe methods (GET, HEAD, OPTIONS) are skipped.
        For other methods, cookie and header must match.

        Args:
            request: FastAPI Request object

        Raises:
            HTTPException: 403 if CSRF validation fails
        """
        # Skip safe methods
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return

        # Get tokens
        cookie_token = request.cookies.get(self.COOKIE_NAME)
        header_token = request.headers.get(self.HEADER_NAME)

        # Both must be present
        if not cookie_token:
            logger.warning(f"CSRF cookie missing for {request.method} {request.url.path}")
            raise HTTPException(
                status_code=403,
                detail="CSRF-token saknas (cookie)",
            )

        if not header_token:
            logger.warning(f"CSRF header missing for {request.method} {request.url.path}")
            raise HTTPException(
                status_code=403,
                detail="CSRF-token saknas (header)",
            )

        # Tokens must match
        if not hmac.compare_digest(cookie_token, header_token):
            logger.warning(
                f"CSRF token mismatch for {request.method} {request.url.path}"
            )
            raise HTTPException(
                status_code=403,
                detail="CSRF-token matchar inte",
            )

        # Token must be valid (not expired, valid signature)
        if not self.validate_token(cookie_token):
            logger.warning(
                f"Invalid CSRF token for {request.method} {request.url.path}"
            )
            raise HTTPException(
                status_code=403,
                detail="CSRF-token är ogiltigt eller har utgått",
            )


# Middleware for automatic CSRF protection
class CSRFMiddleware:
    """
    CSRF protection middleware.

    Automatically verifies CSRF tokens on state-changing requests.
    Generates and sets tokens for GET requests.
    """

    # Paths exempt from CSRF (e.g., API endpoints with their own auth)
    EXEMPT_PATHS = {
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/health",
        "/docs",
        "/openapi.json",
    }

    def __init__(self, app, csrf: Optional[CSRFProtection] = None):
        """
        Initialize middleware.

        Args:
            app: The FastAPI/Starlette app
            csrf: CSRFProtection instance (creates new one if None)
        """
        self.app = app
        self.csrf = csrf or CSRFProtection()

    async def __call__(self, scope, receive, send):
        """ASGI middleware entry point."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive, send)

        # Skip exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        # Skip if path starts with exempt prefix
        for exempt in self.EXEMPT_PATHS:
            if request.url.path.startswith(exempt):
                await self.app(scope, receive, send)
                return

        # For GET requests, ensure token is set
        if request.method == "GET":
            # Wrap send to add cookie if needed
            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    # Check if cookie already set
                    if self.csrf.COOKIE_NAME not in request.cookies:
                        token = self.csrf.generate_token()
                        # Add Set-Cookie header
                        headers = list(message.get("headers", []))
                        cookie = (
                            f"{self.csrf.COOKIE_NAME}={token}; "
                            f"Max-Age={self.csrf.TOKEN_LIFETIME}; "
                            f"SameSite=Strict; Path=/"
                        )
                        if settings.is_production:
                            cookie += "; Secure"
                        headers.append((b"set-cookie", cookie.encode()))
                        message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_wrapper)
            return

        # For state-changing requests, verify token
        try:
            await self.csrf.verify(request)
        except HTTPException as e:
            # Send error response
            response = Response(
                content=e.detail,
                status_code=e.status_code,
                media_type="text/plain",
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
