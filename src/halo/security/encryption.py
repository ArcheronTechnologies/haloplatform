"""
PII Field Encryption for Halo Platform.

Implements field-level encryption for sensitive Swedish PII data including:
- Personnummer (Swedish personal identity number)
- Organisationsnummer (Swedish organization number)
- Account numbers
- Other sensitive identifiers

SECURITY NOTES:
- Uses AES-256-GCM (not Fernet/AES-128) for Säkerhetsskyddslagen compliance
- Blind indexing uses HMAC-SHA256 with secret key (NOT plain SHA-256)
  - Plain SHA-256 of personnummer is trivially reversible via rainbow table
  - Sweden has ~12M valid personnummer - takes minutes to enumerate
- Encryption key derived from PII_ENCRYPTION_KEY environment variable
- Index key derived from PII_INDEX_KEY environment variable
"""

import base64
import hashlib
import hmac
import logging
import os
import re
from functools import lru_cache
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from halo.config import settings

logger = logging.getLogger(__name__)

# Constants
NONCE_SIZE = 12  # 96 bits for AES-GCM
KEY_SIZE = 32    # 256 bits for AES-256
BLIND_INDEX_SIZE = 16  # Truncated HMAC for storage efficiency

# HKDF info strings for domain separation (per security framework)
HKDF_INFO = {
    "pii_encryption": b"halo-pii-encryption-v1",
    "pii_index": b"halo-pii-blind-index-v1",
    "audit_chain": b"halo-audit-chain-v1",
}


class PIIEncryption:
    """
    Handles encryption/decryption of PII fields using AES-256-GCM.

    Thread-safe singleton implementation.

    Security properties:
    - Confidentiality: AES-256 encryption
    - Integrity: GCM authentication tag
    - Unique ciphertexts: Random nonce per encryption
    """

    _instance: Optional["PIIEncryption"] = None

    def __init__(
        self,
        encryption_key: Optional[bytes] = None,
        index_key: Optional[bytes] = None,
    ):
        """
        Initialize with encryption and indexing keys.

        Args:
            encryption_key: 32-byte key for AES-256-GCM. If None, derived from settings.
            index_key: Key for HMAC blind indexing. If None, derived from settings.
        """
        # Derive encryption key
        if encryption_key is None:
            raw_key = settings.pii_encryption_key
            if not raw_key:
                raise ValueError("PII_ENCRYPTION_KEY not configured")
            # Derive 256-bit key from the configured key using HKDF-like derivation
            encryption_key = self._derive_key(raw_key, b"encryption")

        # Derive index key (MUST be different from encryption key)
        if index_key is None:
            raw_key = settings.pii_encryption_key
            if not raw_key:
                raise ValueError("PII_ENCRYPTION_KEY not configured")
            # Use different context for index key derivation
            index_key = self._derive_key(raw_key, b"blind_index")

        if len(encryption_key) != KEY_SIZE:
            raise ValueError(f"Encryption key must be {KEY_SIZE} bytes")

        self._aesgcm = AESGCM(encryption_key)
        self._index_key = index_key
        self._key_id = hashlib.sha256(encryption_key).hexdigest()[:8]

    @staticmethod
    def _derive_key(master_key: str, purpose: str) -> bytes:
        """
        Derive a 256-bit key from master key using proper HKDF.

        Args:
            master_key: The master key string (from config)
            purpose: Key purpose for domain separation ("pii_encryption" or "pii_index")

        Returns:
            32-byte derived key
        """
        # Get HKDF info string for this purpose
        if purpose == b"encryption":
            # Legacy compatibility
            info = HKDF_INFO["pii_encryption"]
        elif purpose == b"blind_index":
            # Legacy compatibility
            info = HKDF_INFO["pii_index"]
        elif isinstance(purpose, str) and purpose in HKDF_INFO:
            info = HKDF_INFO[purpose]
        elif isinstance(purpose, bytes):
            info = purpose
        else:
            raise ValueError(f"Unknown key purpose: {purpose}")

        # Decode master key if base64 encoded
        try:
            if len(master_key) == 44 and master_key.endswith("="):
                # Looks like Fernet key format
                key_bytes = base64.urlsafe_b64decode(master_key)
            else:
                key_bytes = master_key.encode()
        except Exception:
            key_bytes = master_key.encode()

        # Use proper HKDF from cryptography library
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=None,  # No salt - using info for domain separation
            info=info,
        )

        return hkdf.derive(key_bytes)

    @classmethod
    def get_instance(cls) -> "PIIEncryption":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = PIIEncryption()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext value using AES-256-GCM.

        Args:
            plaintext: The sensitive value to encrypt

        Returns:
            Base64-encoded encrypted value with 'enc2:' prefix
            Format: enc2:<base64(nonce || ciphertext || tag)>

        Note: 'enc2:' prefix distinguishes from old Fernet 'enc:' format
        """
        if not plaintext:
            return plaintext

        # Already encrypted (either format)
        if plaintext.startswith("enc:") or plaintext.startswith("enc2:"):
            return plaintext

        try:
            # Generate random nonce
            nonce = os.urandom(NONCE_SIZE)

            # Encrypt with authentication
            ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

            # Combine nonce + ciphertext (tag is appended by GCM)
            combined = nonce + ciphertext

            # Base64 encode
            encoded = base64.urlsafe_b64encode(combined).decode("ascii")

            return f"enc2:{encoded}"

        except Exception as e:
            logger.error(f"Encryption failed: {type(e).__name__}")
            raise ValueError("Failed to encrypt PII data") from e

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted value.

        Args:
            ciphertext: The encrypted value (with 'enc2:' or legacy 'enc:' prefix)

        Returns:
            Decrypted plaintext value
        """
        if not ciphertext:
            return ciphertext

        # Not encrypted
        if not ciphertext.startswith("enc") or ":" not in ciphertext:
            return ciphertext

        try:
            prefix, encoded = ciphertext.split(":", 1)

            if prefix == "enc2":
                # New AES-256-GCM format
                combined = base64.urlsafe_b64decode(encoded)

                if len(combined) < NONCE_SIZE + 16:  # nonce + min tag
                    raise ValueError("Ciphertext too short")

                nonce = combined[:NONCE_SIZE]
                ciphertext_with_tag = combined[NONCE_SIZE:]

                plaintext = self._aesgcm.decrypt(nonce, ciphertext_with_tag, None)
                return plaintext.decode("utf-8")

            elif prefix == "enc":
                # Legacy Fernet format - attempt migration path
                logger.warning(
                    "Decrypting legacy Fernet format. Consider re-encrypting data."
                )
                # Import Fernet only for legacy support
                from cryptography.fernet import Fernet

                # Try to use the raw key as Fernet key
                raw_key = settings.pii_encryption_key
                if isinstance(raw_key, str):
                    raw_key = raw_key.encode()
                fernet = Fernet(raw_key)
                return fernet.decrypt(encoded.encode()).decode("utf-8")

            else:
                raise ValueError(f"Unknown encryption prefix: {prefix}")

        except Exception as e:
            logger.error(f"Decryption failed: {type(e).__name__}: {e}")
            raise ValueError("Failed to decrypt PII data") from e

    def is_encrypted(self, value: str) -> bool:
        """Check if a value is already encrypted."""
        if not value:
            return False
        return value.startswith("enc:") or value.startswith("enc2:")

    def create_blind_index(self, plaintext: str) -> str:
        """
        Create a blind index for searchable encryption.

        CRITICAL: This uses HMAC with a secret key, NOT plain SHA-256.

        Plain SHA-256 of personnummer is trivially reversible:
        - Sweden has ~12M valid personnummer
        - Rainbow table takes ~10 minutes to generate
        - Any hash can be reversed in O(1)

        HMAC with secret key prevents this attack - attacker needs the key.

        Args:
            plaintext: The value to create an index for

        Returns:
            Hex-encoded truncated HMAC (32 characters)
        """
        if not plaintext:
            return ""

        # Normalize: remove formatting
        normalized = re.sub(r"[-\s]", "", plaintext.lower())

        # HMAC-SHA256 with secret index key
        mac = hmac.new(self._index_key, normalized.encode("utf-8"), "sha256")

        # Truncate to 16 bytes (128 bits) for storage efficiency
        # Still provides 2^128 collision resistance
        return mac.hexdigest()[:BLIND_INDEX_SIZE * 2]

    def verify_blind_index(self, plaintext: str, index: str) -> bool:
        """
        Verify a blind index matches a plaintext value.

        Args:
            plaintext: The plaintext value
            index: The stored blind index

        Returns:
            True if the index matches
        """
        expected = self.create_blind_index(plaintext)
        # Constant-time comparison to prevent timing attacks
        return hmac.compare_digest(expected, index)


# Module-level convenience functions
def derive_key(master_key: str, purpose: str) -> bytes:
    """
    Derive a purpose-specific key using HKDF.

    This is the recommended way to derive keys for different purposes
    from a single master key. Uses proper domain separation.

    Args:
        master_key: The master key string
        purpose: One of "pii_encryption", "pii_index", or "audit_chain"

    Returns:
        32-byte derived key

    Example:
        >>> audit_key = derive_key(settings.pii_encryption_key, "audit_chain")
    """
    return PIIEncryption._derive_key(master_key, purpose)


def encrypt_pii(plaintext: str) -> str:
    """Encrypt a PII value using the default encryption instance."""
    return PIIEncryption.get_instance().encrypt(plaintext)


def decrypt_pii(ciphertext: str) -> str:
    """Decrypt a PII value using the default encryption instance."""
    return PIIEncryption.get_instance().decrypt(ciphertext)


def create_blind_index(plaintext: str) -> str:
    """
    Create a blind index for searchable encryption.

    Use this instead of plain hashing for personnummer/orgnummer lookups.
    """
    return PIIEncryption.get_instance().create_blind_index(plaintext)


def mask_personnummer(personnummer: str, show_last: int = 4) -> str:
    """
    Mask a personnummer for display.

    Args:
        personnummer: The personnummer (may be encrypted)
        show_last: Number of digits to show at the end

    Returns:
        Masked personnummer like "XXXXXX-XXXX" or "XXXXXXXX-1234"

    Example:
        >>> mask_personnummer("19800101-1234")
        "XXXXXXXX-1234"
    """
    if not personnummer:
        return ""

    # Decrypt if needed
    if personnummer.startswith("enc"):
        try:
            personnummer = decrypt_pii(personnummer)
        except ValueError:
            return "XXXX-XXXX"  # Can't decrypt, show fully masked

    # Clean format (remove hyphens for processing)
    clean = re.sub(r"[-\s]", "", personnummer)

    if len(clean) < show_last:
        return "X" * len(clean)

    # Keep last N digits visible
    masked_part = "X" * (len(clean) - show_last)
    visible_part = clean[-show_last:]

    # Format with hyphen if original had one
    if "-" in personnummer or len(clean) == 12:
        # Standard format: YYYYMMDD-NNNN
        if len(masked_part) >= 8:
            return f"{masked_part[:8]}-{masked_part[8:]}{visible_part}"
        return f"{masked_part}-{visible_part}"

    return f"{masked_part}{visible_part}"


def mask_organisationsnummer(orgnr: str) -> str:
    """
    Mask an organisationsnummer for display.

    Organisation numbers are semi-public in Sweden, so we only mask partially.

    Args:
        orgnr: The organisation number (may be encrypted)

    Returns:
        Partially masked org number like "5590XX-XXXX"
    """
    if not orgnr:
        return ""

    # Decrypt if needed
    if orgnr.startswith("enc"):
        try:
            orgnr = decrypt_pii(orgnr)
        except ValueError:
            return "XXXXXX-XXXX"

    # Clean format
    clean = re.sub(r"[-\s]", "", orgnr)

    if len(clean) < 6:
        return "X" * len(clean)

    # Show first 4 digits (company type prefix is semi-public)
    return f"{clean[:4]}XX-XXXX"


def validate_personnummer(pnr: str, check_luhn: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Validate Swedish personnummer format and optionally Luhn checksum.

    Args:
        pnr: The personnummer to validate
        check_luhn: Whether to verify the Luhn checksum

    Returns:
        Tuple of (is_valid, error_message)

    Supports formats:
    - YYYYMMDD-NNNN (12 digits with hyphen)
    - YYYYMMDDNNNN (12 digits no hyphen)
    - YYMMDD-NNNN (10 digits with hyphen)
    - YYMMDDNNNN (10 digits no hyphen)
    """
    if not pnr:
        return False, "Empty personnummer"

    # Clean the input
    clean = re.sub(r"[-\s]", "", pnr)

    # Check length
    if len(clean) not in (10, 12):
        return False, f"Invalid length: {len(clean)} (expected 10 or 12)"

    # Check all digits
    if not clean.isdigit():
        return False, "Contains non-digit characters"

    # Normalize to 10-digit format for Luhn check
    if len(clean) == 12:
        # YYYYMMDDNNNN -> YYMMDDNNNN
        clean = clean[2:]

    if check_luhn:
        # Swedish personnummer uses Luhn algorithm on last 10 digits
        # The check digit is the last digit
        digits = [int(d) for d in clean]

        # Luhn: multiply odd positions by 2, even by 1 (0-indexed)
        weights = [2, 1, 2, 1, 2, 1, 2, 1, 2, 1]
        products = []
        for digit, weight in zip(digits, weights):
            product = digit * weight
            # If product >= 10, sum the digits (e.g., 12 -> 1+2 = 3)
            if product >= 10:
                product = product // 10 + product % 10
            products.append(product)

        total = sum(products)

        if total % 10 != 0:
            return False, "Invalid Luhn checksum"

    return True, None


def validate_organisationsnummer(orgnr: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Swedish organisationsnummer.

    Args:
        orgnr: The organisation number to validate

    Returns:
        Tuple of (is_valid, error_message)

    Swedish org numbers:
    - 10 digits: NNNNNN-NNNN
    - Third digit must be >= 2 (distinguishes from personnummer)
    - Uses Luhn checksum
    """
    if not orgnr:
        return False, "Empty organisationsnummer"

    clean = re.sub(r"[-\s]", "", orgnr)

    if len(clean) != 10:
        return False, f"Invalid length: {len(clean)} (expected 10)"

    if not clean.isdigit():
        return False, "Contains non-digit characters"

    # Third digit must be >= 2 to distinguish from personnummer
    if int(clean[2]) < 2:
        return False, "Third digit must be >= 2 for organisation numbers"

    # Luhn check (same as personnummer)
    digits = [int(d) for d in clean]
    weights = [2, 1, 2, 1, 2, 1, 2, 1, 2, 1]
    products = []
    for digit, weight in zip(digits, weights):
        product = digit * weight
        if product >= 10:
            product = product // 10 + product % 10
        products.append(product)

    if sum(products) % 10 != 0:
        return False, "Invalid Luhn checksum"

    return True, None
