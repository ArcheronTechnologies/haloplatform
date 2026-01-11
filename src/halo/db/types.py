"""
Custom SQLAlchemy column types for Halo platform.

Includes encrypted types for PII data.
"""

from typing import Optional

from sqlalchemy import String, TypeDecorator

from halo.security.encryption import encrypt_pii, decrypt_pii


class EncryptedString(TypeDecorator):
    """
    A SQLAlchemy type that transparently encrypts/decrypts string values.

    Usage:
        personnummer: Mapped[Optional[str]] = mapped_column(EncryptedString(12))

    The value is automatically encrypted when written to the database
    and decrypted when read from the database.

    Storage format: "enc:<base64-encoded-encrypted-data>"
    """

    impl = String
    cache_ok = True

    def __init__(self, length: Optional[int] = None, *args, **kwargs):
        """
        Initialize encrypted string type.

        Args:
            length: Maximum length of the *encrypted* value (typically 2-3x plaintext length)
        """
        # Encrypted values are longer than plaintext due to:
        # - Base64 encoding (~33% overhead)
        # - Encryption overhead (IV, HMAC, etc.)
        # - 'enc:' prefix (4 chars)
        # Typical overhead is 2-3x, so we multiply the intended length
        if length:
            length = length * 3 + 50  # Extra buffer for encryption overhead
        super().__init__(length, *args, **kwargs)

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        """Encrypt value before storing in database."""
        if value is None:
            return None
        if value.startswith("enc:"):
            # Already encrypted
            return value
        return encrypt_pii(value)

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        """Decrypt value when reading from database."""
        if value is None:
            return None
        if not value.startswith("enc:"):
            # Not encrypted (legacy data or error)
            return value
        return decrypt_pii(value)


class EncryptedPersonnummer(EncryptedString):
    """
    Specialized encrypted type for Swedish personnummer.

    Personnummer format: YYYYMMDD-NNNN (12 digits + hyphen = 13 chars)
    Encrypted storage: ~150 chars (with encryption overhead)
    """

    def __init__(self, *args, **kwargs):
        # Personnummer is max 13 chars (12 digits + hyphen)
        super().__init__(length=13, *args, **kwargs)


class EncryptedOrganisationsnummer(EncryptedString):
    """
    Specialized encrypted type for Swedish organisationsnummer.

    Format: NNNNNN-NNNN (10 digits + hyphen = 11 chars)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(length=11, *args, **kwargs)


class EncryptedAccountNumber(EncryptedString):
    """
    Encrypted type for bank account numbers.

    Swedish account numbers vary in length (typically 10-16 digits).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(length=20, *args, **kwargs)
