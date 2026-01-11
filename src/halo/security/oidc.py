"""
OIDC (OpenID Connect) Integration for Halo Platform.

Supports authentication via external identity providers including:
- Identity brokers (Signicat, CGI, Freja eID)
- Enterprise IdPs (Azure AD, Okta)
- Government IdPs (SITHS via Inera)

This module provides a generic OIDC client that can be configured
for different providers.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt
from jose.constants import ALGORITHMS

from halo.config import settings

logger = logging.getLogger(__name__)


class OIDCError(Exception):
    """Base exception for OIDC errors."""

    pass


class OIDCTokenError(OIDCError):
    """Token validation or exchange failed."""

    pass


class OIDCConfigurationError(OIDCError):
    """Provider configuration error."""

    pass


class OIDCProvider(str, Enum):
    """Pre-configured OIDC providers."""

    # Swedish identity brokers
    SIGNICAT = "signicat"
    FREJA = "freja"
    CGI = "cgi"

    # Enterprise IdPs
    AZURE_AD = "azure_ad"
    OKTA = "okta"

    # Government
    SITHS = "siths"

    # Generic
    CUSTOM = "custom"


@dataclass
class OIDCConfiguration:
    """OIDC provider configuration."""

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str]
    jwks_uri: str
    end_session_endpoint: Optional[str] = None
    scopes_supported: list[str] = None
    response_types_supported: list[str] = None
    claims_supported: list[str] = None

    @classmethod
    async def discover(cls, issuer: str) -> "OIDCConfiguration":
        """
        Discover OIDC configuration from well-known endpoint.

        Args:
            issuer: OIDC issuer URL

        Returns:
            OIDCConfiguration populated from discovery
        """
        discovery_url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"

        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url)
            if response.status_code != 200:
                raise OIDCConfigurationError(
                    f"Failed to discover OIDC config: {response.status_code}"
                )

            data = response.json()

        return cls(
            issuer=data["issuer"],
            authorization_endpoint=data["authorization_endpoint"],
            token_endpoint=data["token_endpoint"],
            userinfo_endpoint=data.get("userinfo_endpoint"),
            jwks_uri=data["jwks_uri"],
            end_session_endpoint=data.get("end_session_endpoint"),
            scopes_supported=data.get("scopes_supported", []),
            response_types_supported=data.get("response_types_supported", []),
            claims_supported=data.get("claims_supported", []),
        )


@dataclass
class OIDCUser:
    """User information from OIDC claims."""

    subject: str  # Unique identifier from IdP
    email: Optional[str] = None
    email_verified: bool = False
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    personnummer: Optional[str] = None  # Swedish personal ID (from BankID/SITHS)
    organization: Optional[str] = None
    raw_claims: dict = None  # All claims from IdP


@dataclass
class OIDCTokens:
    """OIDC token response."""

    access_token: str
    token_type: str
    expires_in: int
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class OIDCClient:
    """
    OIDC Relying Party client.

    Implements the Authorization Code flow with PKCE.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str],
        redirect_uri: str,
        config: OIDCConfiguration,
        scopes: list[str] = None,
    ):
        """
        Initialize OIDC client.

        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret (optional for public clients)
            redirect_uri: Callback URL after authentication
            config: OIDC provider configuration
            scopes: Scopes to request (default: openid profile email)
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.config = config
        self.scopes = scopes or ["openid", "profile", "email"]

        # JWKS cache
        self._jwks: Optional[dict] = None
        self._jwks_fetched_at: Optional[datetime] = None
        self._jwks_cache_duration = timedelta(hours=24)

    def generate_auth_url(
        self,
        state: Optional[str] = None,
        nonce: Optional[str] = None,
        code_verifier: Optional[str] = None,
        extra_params: Optional[dict] = None,
    ) -> tuple[str, str, str, str]:
        """
        Generate authorization URL for redirect.

        Args:
            state: Optional state parameter (generated if not provided)
            nonce: Optional nonce parameter (generated if not provided)
            code_verifier: Optional PKCE code verifier (generated if not provided)
            extra_params: Additional parameters to include

        Returns:
            Tuple of (auth_url, state, nonce, code_verifier)
        """
        # Generate security parameters if not provided
        state = state or secrets.token_urlsafe(32)
        nonce = nonce or secrets.token_urlsafe(32)
        code_verifier = code_verifier or secrets.token_urlsafe(64)

        # Generate code challenge (PKCE)
        code_challenge = (
            hashlib.sha256(code_verifier.encode())
            .digest()
        )
        code_challenge_b64 = (
            secrets.token_urlsafe(0)  # Base64url encoding
            .join(
                __import__("base64")
                .urlsafe_b64encode(code_challenge)
                .decode()
                .rstrip("=")
            )
        )
        # Correct implementation:
        import base64
        code_challenge_b64 = (
            base64.urlsafe_b64encode(code_challenge).decode().rstrip("=")
        )

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge_b64,
            "code_challenge_method": "S256",
        }

        if extra_params:
            params.update(extra_params)

        auth_url = f"{self.config.authorization_endpoint}?{urlencode(params)}"

        return auth_url, state, nonce, code_verifier

    async def exchange_code(
        self,
        code: str,
        code_verifier: str,
    ) -> OIDCTokens:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            code_verifier: PKCE code verifier used in auth request

        Returns:
            OIDCTokens with access token and optionally ID token
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": code_verifier,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise OIDCTokenError(f"Token exchange failed: {response.status_code}")

            token_data = response.json()

        return OIDCTokens(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            id_token=token_data.get("id_token"),
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
        )

    async def refresh_tokens(self, refresh_token: str) -> OIDCTokens:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token from previous exchange

        Returns:
            New OIDCTokens
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": refresh_token,
        }

        if self.client_secret:
            data["client_secret"] = self.client_secret

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                raise OIDCTokenError(f"Token refresh failed: {response.status_code}")

            token_data = response.json()

        return OIDCTokens(
            access_token=token_data["access_token"],
            token_type=token_data.get("token_type", "Bearer"),
            expires_in=token_data.get("expires_in", 3600),
            id_token=token_data.get("id_token"),
            refresh_token=token_data.get("refresh_token", refresh_token),
            scope=token_data.get("scope"),
        )

    async def _get_jwks(self) -> dict:
        """Fetch and cache JWKS from provider."""
        now = datetime.utcnow()

        if (
            self._jwks is not None
            and self._jwks_fetched_at is not None
            and now - self._jwks_fetched_at < self._jwks_cache_duration
        ):
            return self._jwks

        async with httpx.AsyncClient() as client:
            response = await client.get(self.config.jwks_uri)
            if response.status_code != 200:
                raise OIDCTokenError("Failed to fetch JWKS")

            self._jwks = response.json()
            self._jwks_fetched_at = now

        return self._jwks

    async def validate_id_token(
        self,
        id_token: str,
        nonce: Optional[str] = None,
    ) -> dict:
        """
        Validate an ID token.

        Args:
            id_token: JWT ID token to validate
            nonce: Expected nonce value (if used in auth request)

        Returns:
            Validated claims from the ID token
        """
        # Get JWKS for signature verification
        jwks = await self._get_jwks()

        try:
            # Decode and verify the token
            claims = jwt.decode(
                id_token,
                jwks,
                algorithms=["RS256", "ES256"],
                audience=self.client_id,
                issuer=self.config.issuer,
            )

            # Verify nonce if provided
            if nonce and claims.get("nonce") != nonce:
                raise OIDCTokenError("Nonce mismatch")

            return claims

        except JWTError as e:
            logger.error(f"ID token validation failed: {e}")
            raise OIDCTokenError(f"ID token validation failed: {e}")

    async def get_userinfo(self, access_token: str) -> dict:
        """
        Fetch user information from userinfo endpoint.

        Args:
            access_token: Valid access token

        Returns:
            User claims from userinfo endpoint
        """
        if not self.config.userinfo_endpoint:
            raise OIDCConfigurationError("Userinfo endpoint not available")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.config.userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise OIDCTokenError(f"Userinfo request failed: {response.status_code}")

            return response.json()

    async def authenticate(
        self,
        code: str,
        code_verifier: str,
        nonce: Optional[str] = None,
    ) -> OIDCUser:
        """
        Complete authentication flow after callback.

        Args:
            code: Authorization code from callback
            code_verifier: PKCE code verifier
            nonce: Expected nonce (if used)

        Returns:
            OIDCUser with user information
        """
        # Exchange code for tokens
        tokens = await self.exchange_code(code, code_verifier)

        # Validate ID token if present
        claims = {}
        if tokens.id_token:
            claims = await self.validate_id_token(tokens.id_token, nonce)

        # Optionally fetch additional claims from userinfo
        if self.config.userinfo_endpoint:
            try:
                userinfo = await self.get_userinfo(tokens.access_token)
                claims.update(userinfo)
            except OIDCError:
                pass  # Continue with ID token claims only

        return OIDCUser(
            subject=claims.get("sub", ""),
            email=claims.get("email"),
            email_verified=claims.get("email_verified", False),
            name=claims.get("name"),
            given_name=claims.get("given_name"),
            family_name=claims.get("family_name"),
            personnummer=claims.get("personnummer") or claims.get("personal_number"),
            organization=claims.get("organization") or claims.get("org"),
            raw_claims=claims,
        )

    def generate_logout_url(
        self,
        id_token_hint: Optional[str] = None,
        post_logout_redirect_uri: Optional[str] = None,
        state: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate logout URL for single sign-out.

        Args:
            id_token_hint: ID token for logout hint
            post_logout_redirect_uri: Where to redirect after logout
            state: Optional state parameter

        Returns:
            Logout URL or None if not supported
        """
        if not self.config.end_session_endpoint:
            return None

        params = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        if state:
            params["state"] = state

        if params:
            return f"{self.config.end_session_endpoint}?{urlencode(params)}"
        return self.config.end_session_endpoint


# Pre-configured provider factories
class OIDCProviderFactory:
    """Factory for creating pre-configured OIDC clients."""

    # Known provider discovery URLs
    PROVIDER_ISSUERS = {
        OIDCProvider.SIGNICAT: "https://id.signicat.com",
        OIDCProvider.AZURE_AD: "https://login.microsoftonline.com/{tenant}/v2.0",
        OIDCProvider.OKTA: "https://{domain}.okta.com",
    }

    @classmethod
    async def create(
        cls,
        provider: OIDCProvider,
        client_id: str,
        client_secret: Optional[str],
        redirect_uri: str,
        issuer: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        **kwargs,
    ) -> OIDCClient:
        """
        Create an OIDC client for a specific provider.

        Args:
            provider: Provider type
            client_id: OAuth client ID
            client_secret: OAuth client secret
            redirect_uri: Callback URL
            issuer: Custom issuer URL (required for CUSTOM provider)
            scopes: Scopes to request
            **kwargs: Additional provider-specific parameters

        Returns:
            Configured OIDCClient
        """
        if provider == OIDCProvider.CUSTOM:
            if not issuer:
                raise OIDCConfigurationError("Issuer required for custom provider")
            config = await OIDCConfiguration.discover(issuer)

        elif provider == OIDCProvider.AZURE_AD:
            tenant = kwargs.get("tenant", "common")
            issuer_url = cls.PROVIDER_ISSUERS[provider].format(tenant=tenant)
            config = await OIDCConfiguration.discover(issuer_url)

        elif provider == OIDCProvider.OKTA:
            domain = kwargs.get("domain")
            if not domain:
                raise OIDCConfigurationError("Okta domain required")
            issuer_url = cls.PROVIDER_ISSUERS[provider].format(domain=domain)
            config = await OIDCConfiguration.discover(issuer_url)

        elif provider in cls.PROVIDER_ISSUERS:
            config = await OIDCConfiguration.discover(cls.PROVIDER_ISSUERS[provider])

        else:
            if not issuer:
                raise OIDCConfigurationError(f"Issuer required for provider: {provider}")
            config = await OIDCConfiguration.discover(issuer)

        # Add Swedish-specific scopes for identity providers
        if provider in [OIDCProvider.SIGNICAT, OIDCProvider.FREJA, OIDCProvider.SITHS]:
            if scopes is None:
                scopes = ["openid", "profile", "email", "ssn"]  # ssn = personnummer

        return OIDCClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            config=config,
            scopes=scopes,
        )


# State management for OIDC flows
class OIDCStateStore:
    """
    Simple in-memory state store for OIDC flows.

    In production, use Redis or database storage.
    """

    def __init__(self, ttl_seconds: int = 600):
        """
        Initialize state store.

        Args:
            ttl_seconds: Time-to-live for state entries
        """
        self._store: dict[str, dict] = {}
        self._ttl = timedelta(seconds=ttl_seconds)

    def save(
        self,
        state: str,
        nonce: str,
        code_verifier: str,
        extra_data: Optional[dict] = None,
    ) -> None:
        """Save state for an authentication flow."""
        self._store[state] = {
            "nonce": nonce,
            "code_verifier": code_verifier,
            "created_at": datetime.utcnow(),
            "extra_data": extra_data or {},
        }

    def get(self, state: str) -> Optional[dict]:
        """Retrieve and delete state."""
        entry = self._store.pop(state, None)
        if entry is None:
            return None

        # Check expiration
        if datetime.utcnow() - entry["created_at"] > self._ttl:
            return None

        return entry

    def cleanup(self) -> None:
        """Remove expired entries."""
        now = datetime.utcnow()
        expired = [
            state
            for state, entry in self._store.items()
            if now - entry["created_at"] > self._ttl
        ]
        for state in expired:
            del self._store[state]


# Global state store (use Redis in production)
_state_store = OIDCStateStore()


def get_oidc_state_store() -> OIDCStateStore:
    """Get the global OIDC state store."""
    return _state_store
