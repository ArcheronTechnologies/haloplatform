"""
SITHS (Säker IT inom Hälso- och Sjukvård) Integration for Halo Platform.

SITHS is the Swedish smart card PKI infrastructure used by:
- Healthcare organizations
- Social services
- Law enforcement (via extension)
- Government agencies

This module provides integration guidance and placeholder implementation
for SITHS authentication via Inera's infrastructure.

IMPORTANT: Full SITHS integration requires:
1. Agreement with Inera AB (https://www.inera.se)
2. Connection to SITHS-miljön (SITHS environment)
3. Certificate enrollment for your organization
4. Smart card readers deployed to workstations
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SITHSCardType(str, Enum):
    """Types of SITHS smart cards."""

    # Standard SITHS cards
    SITHS_E_ID = "siths_e_id"  # Electronic ID for authentication
    SITHS_FUNCTION = "siths_function"  # Function certificate (for systems)

    # Extended cards
    SITHS_HCC = "siths_hcc"  # Healthcare professional card
    SITHS_RESERVE = "siths_reserve"  # Reserve/backup card


class SITHSError(Exception):
    """Base exception for SITHS errors."""

    pass


class SITHSCardNotPresentError(SITHSError):
    """Smart card not inserted or not readable."""

    pass


class SITHSPINError(SITHSError):
    """PIN verification failed."""

    pass


class SITHSCertificateError(SITHSError):
    """Certificate validation failed."""

    pass


@dataclass
class SITHSCertificate:
    """Certificate information from SITHS card."""

    # Subject information
    serial_number: str  # HSA-ID or other identifier
    common_name: str  # Full name
    given_name: str
    surname: str
    organization: str
    organizational_unit: Optional[str] = None

    # Swedish identifiers
    personnummer: Optional[str] = None  # Personal identity number
    hsa_id: Optional[str] = None  # HSA (Hälso- och Sjukvårdens Adressregister) ID

    # Certificate metadata
    issuer: str = ""
    not_before: Optional[datetime] = None
    not_after: Optional[datetime] = None
    card_type: SITHSCardType = SITHSCardType.SITHS_E_ID

    # Raw certificate
    certificate_pem: Optional[str] = None


@dataclass
class SITHSAuthResult:
    """Result of SITHS authentication."""

    success: bool
    certificate: Optional[SITHSCertificate] = None
    error_message: Optional[str] = None
    authenticated_at: Optional[datetime] = None


# ============================================================================
# SITHS Integration Architecture
# ============================================================================
#
# There are several approaches to SITHS integration:
#
# 1. CLIENT-SIDE TLS (mTLS)
#    - User's browser uses smart card for TLS client authentication
#    - Requires SITHS root CA in server's trust store
#    - Works with standard web servers (nginx, Apache)
#
# 2. INERA AUTHENTICERING
#    - Inera's authentication service acts as identity broker
#    - Provides SAML or OIDC interface
#    - Handles smart card interaction on their side
#    - Recommended for most integrations
#
# 3. DIRECT PKCS#11
#    - Direct interaction with smart card via PKCS#11 API
#    - Requires middleware on client workstations
#    - Most complex but most control
#
# ============================================================================


class SITHSIntegrationGuide:
    """
    SITHS Integration Requirements and Guidance.

    This class documents the requirements and provides
    placeholder implementations for SITHS integration.
    """

    # Inera endpoints
    INERA_TEST_URL = "https://auth.test.siths.se"
    INERA_PROD_URL = "https://auth.siths.se"

    # SITHS root CA
    SITHS_ROOT_CA_SUBJECT = "CN=SITHS Root CA v1,O=Inera AB,C=SE"

    @staticmethod
    def get_requirements() -> dict:
        """
        Get SITHS integration requirements.

        Returns:
            Dictionary of requirements and status
        """
        return {
            "organizational": {
                "inera_agreement": {
                    "description": "Signed agreement with Inera AB",
                    "required": True,
                    "how_to": "Contact Inera at https://www.inera.se/kontakta-oss/",
                },
                "hsa_registration": {
                    "description": "Organization registered in HSA katalog",
                    "required": True,
                    "how_to": "Apply via your regional healthcare organization",
                },
                "security_classification": {
                    "description": "Security classification for handled data",
                    "required": True,
                    "how_to": "Document classification per Säkerhetsskyddslagen",
                },
            },
            "technical": {
                "siths_certificates": {
                    "description": "SITHS server certificates for TLS",
                    "required": True,
                    "how_to": "Request via Inera's certificate portal",
                },
                "smart_card_readers": {
                    "description": "SITHS-compatible smart card readers",
                    "required": True,
                    "how_to": "Procure readers compatible with SITHS e-ID",
                },
                "middleware": {
                    "description": "SITHS middleware on client workstations",
                    "required": True,
                    "how_to": "Install Net iD Enterprise or similar",
                },
                "hsa_integration": {
                    "description": "Integration with HSA catalog for user info",
                    "required": False,
                    "how_to": "Use HSA WS API via Inera",
                },
            },
            "network": {
                "inera_network": {
                    "description": "Connection to Inera's SITHS network",
                    "required": True,
                    "how_to": "Via Sjunet or approved network path",
                },
                "ocsp_access": {
                    "description": "Access to SITHS OCSP responders",
                    "required": True,
                    "how_to": "Whitelist Inera OCSP endpoints",
                },
            },
        }

    @staticmethod
    def get_implementation_options() -> dict:
        """
        Get available implementation options.

        Returns:
            Dictionary of implementation approaches
        """
        return {
            "option_1_inera_authenticering": {
                "name": "Inera Autentisering (Recommended)",
                "description": (
                    "Use Inera's authentication service as identity broker. "
                    "This is the recommended approach for most organizations."
                ),
                "pros": [
                    "Simplest integration",
                    "Inera handles smart card interaction",
                    "Supports SAML 2.0 and OIDC",
                    "Automatic certificate validation",
                ],
                "cons": [
                    "Dependency on Inera service",
                    "May have latency",
                ],
                "integration_method": "OIDC (use halo/security/oidc.py)",
                "issuer_url": "https://auth.siths.se",
            },
            "option_2_mtls": {
                "name": "Mutual TLS (mTLS)",
                "description": (
                    "Configure web server for client certificate authentication. "
                    "The browser prompts for SITHS card when connecting."
                ),
                "pros": [
                    "Direct integration",
                    "No external service dependency",
                    "Works with standard browsers",
                ],
                "cons": [
                    "Complex certificate validation",
                    "Must handle OCSP/CRL checking",
                    "Browser configuration may be needed",
                ],
                "integration_method": "nginx/Apache configuration + custom handler",
            },
            "option_3_pkcs11": {
                "name": "Direct PKCS#11",
                "description": (
                    "Direct interaction with smart card via PKCS#11 API. "
                    "Requires custom client application."
                ),
                "pros": [
                    "Full control",
                    "Works offline",
                    "Custom UX possible",
                ],
                "cons": [
                    "Most complex",
                    "Requires client software",
                    "Platform-specific code",
                ],
                "integration_method": "python-pkcs11 library",
            },
        }


class SITHSViaOIDC:
    """
    SITHS integration via Inera Autentisering (OIDC).

    This is the recommended approach using Inera's identity broker.
    """

    # Inera OIDC configuration
    TEST_ISSUER = "https://auth.test.siths.se"
    PROD_ISSUER = "https://auth.siths.se"

    # Scopes for SITHS
    SITHS_SCOPES = [
        "openid",
        "profile",
        "hsa",  # HSA-ID
        "personnummer",  # Swedish personal ID
    ]

    @classmethod
    async def create_client(
        cls,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        production: bool = False,
    ):
        """
        Create OIDC client configured for SITHS via Inera.

        Args:
            client_id: OAuth client ID from Inera
            client_secret: OAuth client secret from Inera
            redirect_uri: Your callback URL
            production: Use production environment

        Returns:
            Configured OIDCClient for SITHS
        """
        from halo.security.oidc import OIDCConfiguration, OIDCClient

        issuer = cls.PROD_ISSUER if production else cls.TEST_ISSUER

        try:
            config = await OIDCConfiguration.discover(issuer)
        except Exception as e:
            logger.error(f"Failed to discover SITHS OIDC config: {e}")
            raise SITHSError(f"Cannot connect to Inera: {e}")

        return OIDCClient(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            config=config,
            scopes=cls.SITHS_SCOPES,
        )

    @classmethod
    def extract_siths_claims(cls, oidc_user) -> SITHSCertificate:
        """
        Extract SITHS-specific claims from OIDC user.

        Args:
            oidc_user: OIDCUser from authentication

        Returns:
            SITHSCertificate with extracted information
        """
        claims = oidc_user.raw_claims or {}

        return SITHSCertificate(
            serial_number=claims.get("hsa_id", oidc_user.subject),
            common_name=oidc_user.name or "",
            given_name=oidc_user.given_name or "",
            surname=oidc_user.family_name or "",
            organization=claims.get("organization", ""),
            organizational_unit=claims.get("organizational_unit"),
            personnummer=claims.get("personnummer"),
            hsa_id=claims.get("hsa_id"),
        )


class SITHSViaMTLS:
    """
    SITHS integration via mutual TLS.

    Requires nginx/Apache configuration for client certificates.
    """

    # nginx configuration example
    NGINX_CONFIG_EXAMPLE = """
# SITHS mTLS configuration for nginx

# Add SITHS root CA to trusted CAs
ssl_client_certificate /etc/nginx/siths/siths-root-ca.pem;

# Request client certificate
ssl_verify_client optional;  # or 'on' for required

# Pass certificate info to backend
location /api/ {
    proxy_set_header X-SSL-Client-Cert $ssl_client_cert;
    proxy_set_header X-SSL-Client-S-DN $ssl_client_s_dn;
    proxy_set_header X-SSL-Client-Verify $ssl_client_verify;
    proxy_pass http://backend;
}
"""

    @staticmethod
    def parse_certificate_header(
        cert_dn: str,
        verify_status: str,
    ) -> Optional[SITHSCertificate]:
        """
        Parse SITHS certificate from nginx headers.

        Args:
            cert_dn: Subject DN from X-SSL-Client-S-DN
            verify_status: Verification status from X-SSL-Client-Verify

        Returns:
            SITHSCertificate or None if invalid
        """
        if verify_status != "SUCCESS":
            logger.warning(f"Client cert verification failed: {verify_status}")
            return None

        # Parse DN components
        # Format: /CN=Name/serialNumber=HSA-ID/O=Org/C=SE
        parts = {}
        for component in cert_dn.split("/"):
            if "=" in component:
                key, value = component.split("=", 1)
                parts[key.strip()] = value.strip()

        if not parts.get("CN"):
            logger.warning("Certificate missing CN")
            return None

        return SITHSCertificate(
            serial_number=parts.get("serialNumber", ""),
            common_name=parts.get("CN", ""),
            given_name=parts.get("GN", ""),
            surname=parts.get("SN", ""),
            organization=parts.get("O", ""),
            organizational_unit=parts.get("OU"),
            hsa_id=parts.get("serialNumber"),
        )


# Placeholder for future PKCS#11 implementation
class SITHSViaPKCS11:
    """
    SITHS integration via PKCS#11.

    This is a placeholder for direct smart card integration.
    Requires python-pkcs11 library and SITHS middleware.
    """

    @staticmethod
    def get_requirements() -> list[str]:
        """Get requirements for PKCS#11 integration."""
        return [
            "python-pkcs11 library",
            "SITHS middleware (Net iD Enterprise or similar)",
            "PKCS#11 module path for SITHS middleware",
            "Smart card reader drivers",
        ]

    @staticmethod
    async def authenticate_with_pin(pin: str) -> SITHSAuthResult:
        """
        Authenticate using SITHS card and PIN.

        This is a placeholder - actual implementation requires
        python-pkcs11 library and proper middleware configuration.
        """
        raise NotImplementedError(
            "PKCS#11 authentication not yet implemented. "
            "Use SITHSViaOIDC for Inera-brokered authentication."
        )


# Helper function to check SITHS readiness
def check_siths_readiness() -> dict:
    """
    Check if the system is ready for SITHS integration.

    Returns:
        Dictionary with readiness status for each component
    """
    import importlib.util

    results = {
        "oidc_module": {
            "ready": True,
            "details": "halo.security.oidc module available",
        },
        "httpx": {
            "ready": importlib.util.find_spec("httpx") is not None,
            "details": "httpx library for HTTP requests",
        },
        "cryptography": {
            "ready": importlib.util.find_spec("cryptography") is not None,
            "details": "cryptography library for certificate handling",
        },
        "pkcs11": {
            "ready": importlib.util.find_spec("pkcs11") is not None,
            "details": "python-pkcs11 for direct smart card access (optional)",
        },
    }

    # Check for Inera connectivity (would need to actually test in real scenario)
    results["inera_connectivity"] = {
        "ready": None,  # Unknown until tested
        "details": "Connection to Inera authentication service",
    }

    return results
