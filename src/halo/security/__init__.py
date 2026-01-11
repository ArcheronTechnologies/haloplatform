"""
Halo Security Module

Provides encryption, authentication, and authorization utilities.

Includes:
- PII encryption with AES-256-GCM
- Password hashing with Argon2id
- JWT authentication
- RBAC and case-level access control
- BankID integration (Swedish e-ID)
- OIDC/SAML for identity federation
- SITHS smart card integration (Swedish healthcare/government)
"""

from halo.security.encryption import (
    PIIEncryption,
    encrypt_pii,
    decrypt_pii,
    create_blind_index,
    derive_key,
    mask_personnummer,
    mask_organisationsnummer,
    validate_personnummer,
    validate_organisationsnummer,
)
from halo.security.auth import (
    AuthenticationError,
    AuthorizationError,
    User,
    UserRole,
    TokenPayload,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_access_token,
    verify_refresh_token,
    require_role,
    require_permission,
)

# BankID integration
from halo.security.bankid import (
    BankIDClient,
    BankIDAuthenticator,
    BankIDUser,
    BankIDOrder,
    BankIDError,
    BankIDEnvironment,
    get_bankid_client,
)

# OIDC integration
from halo.security.oidc import (
    OIDCClient,
    OIDCConfiguration,
    OIDCUser,
    OIDCTokens,
    OIDCError,
    OIDCProvider,
    OIDCProviderFactory,
    get_oidc_state_store,
)

# SITHS integration
from halo.security.siths import (
    SITHSCertificate,
    SITHSError,
    SITHSViaOIDC,
    SITHSViaMTLS,
    SITHSIntegrationGuide,
    check_siths_readiness,
)

__all__ = [
    # Encryption
    "PIIEncryption",
    "encrypt_pii",
    "decrypt_pii",
    "create_blind_index",
    "derive_key",
    "mask_personnummer",
    "mask_organisationsnummer",
    "validate_personnummer",
    "validate_organisationsnummer",
    # Authentication
    "AuthenticationError",
    "AuthorizationError",
    "User",
    "UserRole",
    "TokenPayload",
    "hash_password",
    "verify_password",
    "create_access_token",
    "create_refresh_token",
    "verify_access_token",
    "verify_refresh_token",
    "require_role",
    "require_permission",
    # BankID
    "BankIDClient",
    "BankIDAuthenticator",
    "BankIDUser",
    "BankIDOrder",
    "BankIDError",
    "BankIDEnvironment",
    "get_bankid_client",
    # OIDC
    "OIDCClient",
    "OIDCConfiguration",
    "OIDCUser",
    "OIDCTokens",
    "OIDCError",
    "OIDCProvider",
    "OIDCProviderFactory",
    "get_oidc_state_store",
    # SITHS
    "SITHSCertificate",
    "SITHSError",
    "SITHSViaOIDC",
    "SITHSViaMTLS",
    "SITHSIntegrationGuide",
    "check_siths_readiness",
]
