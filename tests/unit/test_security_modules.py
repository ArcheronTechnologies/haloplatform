"""
Unit tests for Halo security modules.

Tests:
- BankID integration
- OIDC client
- SITHS integration
- CSRF protection
- Rate limiting
- Session management
- Lockout management
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# BankID tests
from halo.security.bankid import (
    BankIDClient,
    BankIDAuthenticator,
    BankIDOrder,
    BankIDUser,
    BankIDEnvironment,
    BankIDStatus,
    BankIDError,
)

# OIDC tests
from halo.security.oidc import (
    OIDCClient,
    OIDCConfiguration,
    OIDCUser,
    OIDCStateStore,
    OIDCProvider,
)

# SITHS tests
from halo.security.siths import (
    SITHSIntegrationGuide,
    SITHSViaMTLS,
    SITHSCertificate,
    check_siths_readiness,
)

# CSRF tests
from halo.security.csrf import CSRFProtection

# Rate limiting tests
from halo.security.ratelimit import RateLimiter


class TestBankIDClient:
    """Tests for BankID client."""

    def test_environment_urls(self):
        """Test environment URL selection."""
        test_client = BankIDClient(environment=BankIDEnvironment.TEST)
        assert "test.bankid.com" in test_client.base_url

        prod_client = BankIDClient(environment=BankIDEnvironment.PRODUCTION)
        assert "appapi2.bankid.com" in prod_client.base_url
        assert "test" not in prod_client.base_url

    def test_qr_code_generation(self):
        """Test QR code data generation."""
        client = BankIDClient()
        order = BankIDOrder(
            order_ref="test-order-ref",
            auto_start_token="test-auto-start",
            qr_start_token="test-qr-token",
            qr_start_secret="test-secret",
            created_at=datetime.utcnow(),
        )

        qr_data = client.generate_qr_code_data(order)

        assert qr_data.startswith("bankid.")
        assert "test-qr-token" in qr_data
        # Format: bankid.{qr_start_token}.{elapsed}.{qr_auth_code}
        parts = qr_data.split(".")
        assert len(parts) == 4
        assert parts[0] == "bankid"
        assert parts[1] == "test-qr-token"

    def test_auto_start_url(self):
        """Test auto-start URL generation."""
        client = BankIDClient()
        order = BankIDOrder(
            order_ref="test-order-ref",
            auto_start_token="test-auto-start",
            qr_start_token="test-qr-token",
            qr_start_secret="test-secret",
            created_at=datetime.utcnow(),
        )

        url = client.generate_auto_start_url(order)
        assert url.startswith("bankid://")
        assert "autostarttoken=test-auto-start" in url

        url_with_redirect = client.generate_auto_start_url(
            order, redirect_url="https://example.com/callback"
        )
        assert "redirect=https://example.com/callback" in url_with_redirect


class TestBankIDUser:
    """Tests for BankID user model."""

    def test_user_creation(self):
        """Test BankID user data structure."""
        user = BankIDUser(
            personnummer="198001011234",
            name="Test Testsson",
            given_name="Test",
            surname="Testsson",
        )

        assert user.personnummer == "198001011234"
        assert user.name == "Test Testsson"
        assert user.given_name == "Test"
        assert user.surname == "Testsson"


class TestOIDCStateStore:
    """Tests for OIDC state management."""

    def test_save_and_retrieve(self):
        """Test saving and retrieving state."""
        store = OIDCStateStore(ttl_seconds=60)

        state = "test-state-123"
        nonce = "test-nonce-456"
        verifier = "test-verifier-789"

        store.save(state, nonce, verifier)
        retrieved = store.get(state)

        assert retrieved is not None
        assert retrieved["nonce"] == nonce
        assert retrieved["code_verifier"] == verifier

    def test_state_consumed_on_get(self):
        """Test that state is consumed after retrieval."""
        store = OIDCStateStore()

        state = "consumable-state"
        store.save(state, "nonce", "verifier")

        # First get should succeed
        assert store.get(state) is not None

        # Second get should return None (consumed)
        assert store.get(state) is None

    def test_expired_state_rejected(self):
        """Test that expired state is rejected."""
        store = OIDCStateStore(ttl_seconds=0)  # Immediate expiry

        state = "expired-state"
        store.save(state, "nonce", "verifier")

        # Should be expired immediately
        import time
        time.sleep(0.1)
        assert store.get(state) is None

    def test_extra_data_preserved(self):
        """Test that extra data is preserved."""
        store = OIDCStateStore()

        state = "state-with-extra"
        extra = {"redirect_uri": "/dashboard", "user_hint": "test@example.com"}

        store.save(state, "nonce", "verifier", extra_data=extra)
        retrieved = store.get(state)

        assert retrieved["extra_data"]["redirect_uri"] == "/dashboard"
        assert retrieved["extra_data"]["user_hint"] == "test@example.com"


class TestOIDCClient:
    """Tests for OIDC client."""

    def test_auth_url_generation(self):
        """Test authorization URL generation."""
        config = OIDCConfiguration(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
            userinfo_endpoint="https://example.com/userinfo",
            jwks_uri="https://example.com/.well-known/jwks.json",
        )

        client = OIDCClient(
            client_id="test-client-id",
            client_secret="test-secret",
            redirect_uri="https://myapp.com/callback",
            config=config,
        )

        auth_url, state, nonce, verifier = client.generate_auth_url()

        assert "https://example.com/authorize" in auth_url
        assert "client_id=test-client-id" in auth_url
        assert "redirect_uri=" in auth_url
        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url
        assert len(state) > 20  # Should be cryptographically random
        assert len(nonce) > 20
        assert len(verifier) > 50

    def test_logout_url_generation(self):
        """Test logout URL generation."""
        config = OIDCConfiguration(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://example.com/.well-known/jwks.json",
            end_session_endpoint="https://example.com/logout",
        )

        client = OIDCClient(
            client_id="test-client-id",
            client_secret=None,
            redirect_uri="https://myapp.com/callback",
            config=config,
        )

        logout_url = client.generate_logout_url(
            id_token_hint="test-id-token",
            post_logout_redirect_uri="https://myapp.com/logged-out",
        )

        assert logout_url is not None
        assert "https://example.com/logout" in logout_url
        assert "id_token_hint=test-id-token" in logout_url
        assert "post_logout_redirect_uri=" in logout_url

    def test_logout_url_none_when_not_supported(self):
        """Test that logout URL is None when not supported."""
        config = OIDCConfiguration(
            issuer="https://example.com",
            authorization_endpoint="https://example.com/authorize",
            token_endpoint="https://example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://example.com/.well-known/jwks.json",
            end_session_endpoint=None,  # Not supported
        )

        client = OIDCClient(
            client_id="test-client-id",
            client_secret=None,
            redirect_uri="https://myapp.com/callback",
            config=config,
        )

        assert client.generate_logout_url() is None


class TestSITHSIntegration:
    """Tests for SITHS integration helpers."""

    def test_requirements_structure(self):
        """Test that requirements are properly structured."""
        requirements = SITHSIntegrationGuide.get_requirements()

        assert "organizational" in requirements
        assert "technical" in requirements
        assert "network" in requirements

        # Check required organizational items
        assert "inera_agreement" in requirements["organizational"]
        assert requirements["organizational"]["inera_agreement"]["required"] is True

    def test_implementation_options(self):
        """Test implementation options documentation."""
        options = SITHSIntegrationGuide.get_implementation_options()

        assert "option_1_inera_authenticering" in options
        assert "option_2_mtls" in options
        assert "option_3_pkcs11" in options

        # Recommended option should mention OIDC
        assert "OIDC" in options["option_1_inera_authenticering"]["integration_method"]

    def test_mtls_certificate_parsing(self):
        """Test mTLS certificate DN parsing."""
        cert_dn = "/CN=Test User/serialNumber=SE123456789/O=Test Org/C=SE"
        verify_status = "SUCCESS"

        cert = SITHSViaMTLS.parse_certificate_header(cert_dn, verify_status)

        assert cert is not None
        assert cert.common_name == "Test User"
        assert cert.hsa_id == "SE123456789"
        assert cert.organization == "Test Org"

    def test_mtls_invalid_verification_rejected(self):
        """Test that invalid verification is rejected."""
        cert_dn = "/CN=Test User/O=Test Org/C=SE"
        verify_status = "FAILED:certificate_expired"

        cert = SITHSViaMTLS.parse_certificate_header(cert_dn, verify_status)
        assert cert is None

    def test_siths_readiness_check(self):
        """Test SITHS readiness checker."""
        readiness = check_siths_readiness()

        assert "oidc_module" in readiness
        assert "httpx" in readiness
        assert "cryptography" in readiness

        # OIDC module should be ready (we created it)
        assert readiness["oidc_module"]["ready"] is True


class TestCSRFProtection:
    """Tests for CSRF protection."""

    def test_token_generation(self):
        """Test CSRF token generation."""
        csrf = CSRFProtection(secret_key=b"test-secret-key-32-bytes-long!!")

        token = csrf.generate_token()

        # Token format: {timestamp}.{random}.{signature}
        parts = token.split(".")
        assert len(parts) == 3

        # Timestamp should be numeric
        assert parts[0].isdigit()

        # Random part should be URL-safe base64
        assert len(parts[1]) > 20

        # Signature should be hex
        assert len(parts[2]) == 16

    def test_token_validation_success(self):
        """Test successful CSRF token validation."""
        csrf = CSRFProtection(secret_key=b"test-secret-key-32-bytes-long!!")

        token = csrf.generate_token()
        assert csrf.validate_token(token) is True

    def test_token_validation_failure_tampered(self):
        """Test that tampered tokens are rejected."""
        csrf = CSRFProtection(secret_key=b"test-secret-key-32-bytes-long!!")

        token = csrf.generate_token()

        # Tamper with the signature
        parts = token.split(".")
        parts[2] = "0000000000000000"
        tampered = ".".join(parts)

        assert csrf.validate_token(tampered) is False

    def test_token_validation_failure_expired(self):
        """Test that expired tokens are rejected."""
        csrf = CSRFProtection(secret_key=b"test-secret-key-32-bytes-long!!")

        # Generate token, then modify timestamp to be expired
        token = csrf.generate_token()
        parts = token.split(".")

        # Set timestamp to 2 hours ago (past TOKEN_LIFETIME of 1 hour)
        old_timestamp = str(int(parts[0]) - 7200)
        old_message = f"{old_timestamp}.{parts[1]}"
        # Re-sign with correct signature for old timestamp
        import hmac
        signature = hmac.new(csrf._key, old_message.encode(), "sha256").hexdigest()[:16]
        expired_token = f"{old_message}.{signature}"

        assert csrf.validate_token(expired_token) is False

    def test_token_validation_failure_malformed(self):
        """Test that malformed tokens are rejected."""
        csrf = CSRFProtection(secret_key=b"test-secret-key-32-bytes-long!!")

        assert csrf.validate_token("") is False
        assert csrf.validate_token("invalid") is False
        assert csrf.validate_token("a.b") is False
        assert csrf.validate_token("a.b.c.d") is False


class TestRateLimiter:
    """Tests for rate limiting."""

    def test_default_limits_exist(self):
        """Test that default limits are configured."""
        from halo.security.ratelimit import RATE_LIMITS, RateLimitConfig

        # Check default rate limits are defined
        assert RATE_LIMITS is not None
        assert "default" in RATE_LIMITS
        assert "/api/v1/auth/login" in RATE_LIMITS

        # Verify structure
        assert isinstance(RATE_LIMITS["default"], RateLimitConfig)
        assert RATE_LIMITS["default"].max_requests > 0
        assert RATE_LIMITS["default"].window_seconds > 0

    def test_get_limit_for_path(self):
        """Test getting limits for specific paths."""
        from halo.security.ratelimit import RATE_LIMITS

        # Login should have stricter limits than default
        login_limit = RATE_LIMITS["/api/v1/auth/login"]
        default_limit = RATE_LIMITS["default"]

        assert login_limit.max_requests < default_limit.max_requests  # Fewer requests allowed

    def test_custom_limits(self):
        """Test custom limit configuration with mocked Redis."""
        from halo.security.ratelimit import RateLimitConfig

        mock_redis = MagicMock()
        custom_limits = {
            "/api/v1/custom": RateLimitConfig(10, 30),  # 10 requests per 30 seconds
            "default": RateLimitConfig(50, 60),
        }

        limiter = RateLimiter(redis_client=mock_redis, limits=custom_limits)

        # Test internal _get_limit method
        custom_config = limiter._get_limit("/api/v1/custom")
        default_config = limiter._get_limit("/api/v1/other")

        assert custom_config.max_requests == 10
        assert custom_config.window_seconds == 30
        assert default_config.max_requests == 50
        assert default_config.window_seconds == 60


class TestOIDCUser:
    """Tests for OIDC user model."""

    def test_user_from_claims(self):
        """Test creating OIDCUser from claims."""
        user = OIDCUser(
            subject="user-123",
            email="test@example.com",
            email_verified=True,
            name="Test User",
            given_name="Test",
            family_name="User",
            personnummer="198001011234",
            organization="Test Org",
            raw_claims={"custom_claim": "value"},
        )

        assert user.subject == "user-123"
        assert user.email == "test@example.com"
        assert user.email_verified is True
        assert user.personnummer == "198001011234"
        assert user.raw_claims["custom_claim"] == "value"

    def test_user_optional_fields(self):
        """Test that optional fields default correctly."""
        user = OIDCUser(subject="minimal-user")

        assert user.subject == "minimal-user"
        assert user.email is None
        assert user.email_verified is False
        assert user.personnummer is None


class TestBankIDOrder:
    """Tests for BankID order model."""

    def test_order_creation(self):
        """Test BankID order data structure."""
        now = datetime.utcnow()
        order = BankIDOrder(
            order_ref="order-123",
            auto_start_token="auto-456",
            qr_start_token="qr-789",
            qr_start_secret="secret-abc",
            created_at=now,
        )

        assert order.order_ref == "order-123"
        assert order.auto_start_token == "auto-456"
        assert order.qr_start_token == "qr-789"
        assert order.qr_start_secret == "secret-abc"
        assert order.created_at == now
