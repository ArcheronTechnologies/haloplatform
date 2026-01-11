# Halo Platform Security Assessment Report

**Platform:** Halo - Swedish-Sovereign Intelligence Platform
**Assessment Date:** 2025-12-21
**Version:** 0.1.0
**Revision:** 4 (Security Framework Implementation)
**Classification:** INTERNAL - SECURITY SENSITIVE

---

## Executive Summary

This report documents the security posture of the Halo platform following a comprehensive security audit, initial hardening, and expert security review. The platform is designed for Swedish law enforcement and financial compliance use cases, handling sensitive PII including personnummer (Swedish personal identity numbers), financial transaction data, and intelligence information.

### Risk Rating Summary

| Category | Initial | Post-Hardening | After Expert Review | Status |
|----------|---------|----------------|---------------------|--------|
| Authentication | CRITICAL | HIGH | LOW | Mitigated |
| Authorization (RBAC) | CRITICAL | MEDIUM | LOW | Mitigated |
| Authorization (Need-to-Know) | CRITICAL | CRITICAL | LOW | Mitigated |
| PII Encryption | CRITICAL | MEDIUM | LOW | Mitigated |
| Blind Indexing | CRITICAL | CRITICAL | LOW | **Fixed** |
| Dependencies | CRITICAL | LOW | LOW | Mitigated |
| Configuration | HIGH | LOW | LOW | Mitigated |
| API Security | HIGH | MEDIUM | LOW | Mitigated |
| Rate Limiting | HIGH | MEDIUM | LOW | Mitigated |
| ML Model Security | HIGH | HIGH | LOW | Mitigated |
| Audit Integrity | HIGH | HIGH | LOW | Mitigated |
| Session Management | HIGH | HIGH | LOW | Mitigated |
| Credential Stuffing | HIGH | HIGH | LOW | Mitigated |

### Critical Issues Fixed in Revision 2

1. **Personnummer Hash Vulnerability** - Plain SHA-256 was trivially reversible via rainbow table
2. **AES-128 vs AES-256** - Upgraded to AES-256-GCM for Säkerhetsskyddslagen compliance
3. **No User Model** - Added complete User model with session management
4. **No Need-to-Know** - Added CaseAssignment for case-level access control
5. **Audit Log Tampering** - Added HMAC hash chain for integrity verification
6. **No Account Lockout** - Added credential stuffing protection

### Additional Fixes in Revision 3

1. **Missing Dependency** - Added `argon2-cffi` for Argon2id password hashing
2. **Personnummer Plus Sign Bug** - Fixed century calculation for persons over 100 years old (using `+` separator)
3. **Test Data Validation** - Corrected test personnummer checksums for coordination numbers

### Security Framework Implementation (Revision 4)

1. **Proper HKDF Key Derivation** - Replaced custom "HKDF-like" with cryptography library's HKDF
2. **Redis Session Management** - SessionManager with concurrent session limits and device tracking
3. **Combined IP + User Lockout** - LockoutManager with CAPTCHA before hard lockout (prevents DoS)
4. **Case Access Manager** - Need-to-know enforcement with audit trail
5. **CSRF Protection** - Double-submit cookie pattern with signed tokens
6. **Per-User Rate Limiting** - Endpoint-specific limits with Redis backend
7. **Secure Model Loader** - Prevents pickle deserialization attacks in ML pipeline

---

## 1. Authentication & Authorization

### 1.1 Current Implementation

**Location:** `halo/security/auth.py`, `halo/api/deps.py`, `halo/db/models.py`

#### Authentication Mechanism
- JWT (JSON Web Token) based authentication using `python-jose`
- Access tokens: 30-minute expiration (configurable)
- Refresh tokens: 7-day expiration (configurable)
- Algorithm: HS256 (HMAC-SHA256)

**Known Limitation:** HS256 is symmetric. Consider RS256/ES256 for multi-service deployments where key distribution is a concern.

#### Password Security
- Argon2id hashing (memory-hard, GPU-resistant)
- Parameters: time_cost=3, memory_cost=64MB, parallelism=4
- Salt: 16 bytes, Hash: 32 bytes

#### User Database Model
**Location:** `halo/db/models.py` (User, UserSession)

```python
class User(Base):
    # Credentials
    username, email, password_hash

    # Security - Lockout
    failed_login_attempts      # Tracks failed attempts
    locked_until               # Account lockout timestamp

    # Security - MFA (ready for BankID/TOTP)
    totp_secret, totp_enabled

    # Session tracking
    last_login, last_login_ip
```

#### Account Lockout (UPGRADED in Revision 4)

**Location:** `halo/security/lockout.py`

Combined IP + User lockout strategy prevents both brute force and DoS attacks:

```python
class LockoutManager:
    # Per-IP thresholds (protects against distributed attacks)
    IP_CAPTCHA_THRESHOLD = 10    # Show CAPTCHA after 10 failures
    IP_BLOCK_THRESHOLD = 50      # Hard block after 50 failures

    # Per-user thresholds (protects individual accounts)
    USER_CAPTCHA_THRESHOLD = 3   # Show CAPTCHA after 3 failures
    USER_NOTIFY_THRESHOLD = 5    # Notify user after 5 failures
    USER_BLOCK_THRESHOLD = 10    # Hard block after 10 failures
```

**Key Design Decision:** Uses CAPTCHA before hard lockout to prevent DoS via lockout attacks.

#### Session Management (UPGRADED in Revision 4)

**Location:** `halo/security/sessions.py`

Redis-backed session management with concurrent session limits:

```python
class SessionManager:
    MAX_SESSIONS_PER_USER = 3    # Concurrent session limit
    ACCESS_TOKEN_TTL = 1800      # 30 minutes
    REFRESH_TOKEN_TTL = 604800   # 7 days
```

**Features:**

- Session tokens hashed before storage (SHA-256)
- Device fingerprinting support
- Concurrent session enforcement (oldest evicted)
- Emergency revocation (all sessions)

#### Role-Based Access Control (RBAC)
```
VIEWER (0)        → Read-only access
ANALYST (1)       → Create cases, acknowledge Tier 2 alerts
SENIOR_ANALYST (2)→ Approve Tier 3 alerts, export data
ADMIN (3)         → Full system access
SYSTEM (4)        → Service accounts
```

### 1.2 Case-Level Access Control (Need-to-Know) (UPGRADED in Revision 4)

**Location:** `halo/db/models.py` (CaseAssignment), `halo/security/access.py` (CaseAccessManager)

RBAC alone is insufficient - an ANALYST shouldn't access every case. The CaseAssignment model implements need-to-know:

```python
class CaseAssignment(Base):
    case_id: UUID           # Which case
    user_id: UUID           # Which user
    access_level: Enum      # READ, WRITE, OWNER
    granted_by: UUID        # Who granted access
    justification: str      # Why (audit trail)
    expires_at: datetime    # Time-limited access
    revoked_at: datetime    # Revocation tracking
```

**Access Levels:**

- `READ` - View case details
- `WRITE` - Modify case, add notes
- `OWNER` - Full control, can grant access to others

**CaseAccessManager (NEW in Revision 4):**

```python
class CaseAccessManager:
    async def check_access(self, user_id, case_id, required_level) -> bool
    async def require_access(self, user_id, case_id, required_level) -> None  # Raises 403
    async def grant_access(self, case_id, user_id, level, granted_by, justification)
    async def revoke_access(self, case_id, user_id, revoked_by)
```

Swedish error messages for user-facing errors (e.g., "Åtkomst nekad").

### 1.3 Remaining Concerns

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| HS256 vs RS256 | MEDIUM | Open | Consider asymmetric for multi-service |
| BankID/SITHS Integration | MEDIUM | **Partial** | Modules ready, requires Inera agreement |
| Token Revocation | MEDIUM | Partial | Session model supports it, needs API |
| Breached Password Check | LOW | Open | HaveIBeenPwned API integration |

---

## 2. Data Protection

### 2.1 PII Encryption at Rest

**Location:** `halo/security/encryption.py`, `halo/db/types.py`

#### Encryption Algorithm (UPGRADED)

| Aspect | Old (Insecure) | New (Secure) |
|--------|----------------|--------------|
| Algorithm | Fernet (AES-128-CBC) | AES-256-GCM |
| Key Size | 128 bits | 256 bits |
| Mode | CBC + separate HMAC | GCM (authenticated) |
| Prefix | `enc:` | `enc2:` |

**Säkerhetsskyddslagen Compliance:** AES-256 is recommended for classified data. AES-128 may not meet requirements for "hemlig" (secret) classification.

#### Encrypted Fields
| Model | Field | Encryption |
|-------|-------|------------|
| Entity | personnummer | AES-256-GCM |
| Entity | organisationsnummer | AES-256-GCM |
| Transaction | from_account | AES-256-GCM |
| Transaction | to_account | AES-256-GCM |

#### Key Derivation (UPGRADED in Revision 4)

Keys are derived from `PII_ENCRYPTION_KEY` using proper HKDF from the `cryptography` library:

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

HKDF_INFO = {
    "pii_encryption": b"halo-pii-encryption-v1",
    "pii_index": b"halo-pii-blind-index-v1",
    "audit_chain": b"halo-audit-chain-v1",
}

def _derive_key(master_key: str, purpose: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bits
        salt=None,  # Not needed when master key has sufficient entropy
        info=HKDF_INFO[purpose],
    )
    return hkdf.derive(master_key.encode())
```

**Security Improvement:** Replaced custom "HKDF-like" implementation with industry-standard HKDF. This ensures proper domain separation between encryption keys, blind index keys, and audit chain keys.

### 2.2 Blind Indexing (CRITICAL FIX)

**The Problem:**
Plain SHA-256 of personnummer is trivially reversible:
- Sweden has ~12M valid personnummer
- Rainbow table generation: ~10 minutes
- Hash reversal: O(1) lookup

**The Fix:** HMAC blind indexing with secret key

```python
def create_blind_index(plaintext: str) -> str:
    """
    HMAC-SHA256 with secret key - NOT plain SHA-256.
    Attacker needs the index_key to reverse.
    """
    normalized = re.sub(r"[-\s]", "", plaintext.lower())
    mac = hmac.new(self._index_key, normalized.encode(), "sha256")
    return mac.hexdigest()[:32]  # 128-bit truncation
```

**Database Schema:**
```sql
-- Entity table
personnummer         -- Encrypted (AES-256-GCM)
personnummer_hash    -- HMAC blind index (for lookups)
```

### 2.3 Input Validation

**Location:** `halo/security/encryption.py`

Added Swedish identifier validation with Luhn checksum:

```python
validate_personnummer("19800101-1234", check_luhn=True)
# Returns: (True, None) or (False, "Invalid Luhn checksum")

validate_organisationsnummer("5591234567")
# Also checks third digit >= 2 (distinguishes from personnummer)
```

### 2.4 Key Management Concerns

| Issue | Severity | Status | Notes |
|-------|----------|--------|-------|
| Keys in env vars | MEDIUM | Open | Consider Vault/KMS for production |
| Key rotation | MEDIUM | Open | Need re-encryption tooling |
| Per-field keys | LOW | Mitigated | Using HKDF domain separation |

---

## 3. Audit Log Integrity

### 3.1 Hash Chain Implementation (NEW)

**Location:** `halo/db/models.py` (AuditLog)

**The Problem:** If an attacker (or insider) can modify audit logs, they can cover their tracks. For law enforcement, this is catastrophic.

**The Solution:** HMAC hash chain

```python
class AuditLog(Base):
    sequence_id: int          # Sequential for ordering
    previous_hash: str        # Hash of previous entry ("GENESIS" for first)
    entry_hash: str           # HMAC of this entry + previous_hash

    @staticmethod
    def compute_entry_hash(previous_hash, user_id, action, ..., audit_key):
        data = json.dumps({
            "previous_hash": previous_hash,
            "user_id": user_id,
            "action": action,
            ...
        }, sort_keys=True)
        return hmac.new(audit_key, data.encode(), "sha256").hexdigest()
```

**Integrity Verification:**
```python
is_valid, first_invalid_id = AuditLog.verify_chain(entries, audit_key)
# If any entry modified/deleted, chain verification fails
```

**Security Properties:**
- Append-only: Can't modify past entries without breaking chain
- Tamper-evident: Any modification is detectable
- Key-dependent: Can't forge entries without HMAC key

### 3.2 Audit Fields

- WHO: user_id, user_name
- WHAT: action, resource_type, resource_id
- WHEN: timestamp
- WHY: case_id, justification
- CONTEXT: ip_address, user_agent
- INTEGRITY: previous_hash, entry_hash

---

## 4. API Security

### 4.1 Security Headers

**Location:** `halo/main.py` (SecurityHeadersMiddleware)

| Header | Value | Purpose |
|--------|-------|---------|
| X-Frame-Options | DENY | Clickjacking prevention |
| X-Content-Type-Options | nosniff | MIME sniffing prevention |
| Content-Security-Policy | Strict | XSS/injection prevention |
| Permissions-Policy | Restrictive | Disable unnecessary APIs |
| Strict-Transport-Security | max-age=31536000 | HSTS (production only) |

### 4.2 Rate Limiting (UPGRADED in Revision 4)

**Location:** `halo/security/ratelimit.py`

**Implementation:** Redis-backed per-user rate limiting with endpoint-specific limits.

```python
DEFAULT_LIMITS = {
    "/api/v1/auth/login": (5, 60),      # 5 per minute (brute force protection)
    "/api/v1/search": (30, 60),          # 30 per minute (expensive operation)
    "/api/v1/export": (5, 3600),         # 5 per hour (very expensive)
    "default": (100, 60),                 # 100 per minute (general)
}
```

**Features:**

- Authenticated requests: Rate limit by user ID
- Unauthenticated requests: Fall back to IP-based limiting
- Sliding window algorithm for smooth rate limiting
- Redis backend for distributed deployments

### 4.3 CSRF Protection (NEW in Revision 4)

**Location:** `halo/security/csrf.py`

**Implementation:** Double-submit cookie pattern with signed tokens.

```python
class CSRFProtection:
    TOKEN_LIFETIME = 3600  # 1 hour
    COOKIE_NAME = "csrf_token"
    HEADER_NAME = "X-CSRF-Token"

    # Token format: {timestamp}.{random}.{signature}
    def generate_token(self) -> str:
        timestamp = int(datetime.utcnow().timestamp())
        random_part = secrets.token_urlsafe(32)
        message = f"{timestamp}.{random_part}"
        signature = hmac.new(self._key, message.encode(), "sha256").hexdigest()[:16]
        return f"{message}.{signature}"
```

**Exempt Paths:** Login, refresh, health check, docs (API-authenticated endpoints)

### 4.4 Remaining API Concerns

| Issue | Severity | Status |
|-------|----------|--------|
| CSRF protection | MEDIUM | **Fixed** |
| Per-user rate limiting | MEDIUM | **Fixed** |
| Per-endpoint rate limits | LOW | **Fixed** |
| Request body size limits | MEDIUM | Open |

---

## 5. ML Model Security (NEW in Revision 4)

**Location:** `halo/security/model_loader.py`

### 5.1 The Problem

Pickle deserialization attacks are a critical risk in ML pipelines. A malicious `.pkl` or `.pt` file can execute arbitrary code when loaded with `torch.load()` or `pickle.load()`.

### 5.2 SecureModelLoader

```python
class SecureModelLoader:
    # Only allow trusted sources
    ALLOWED_SOURCES = {
        "KB/",           # Royal Library of Sweden models
        "AI-Nordics/",   # Nordic AI models
        "halo-internal/", # Internal models
    }

    # Reject pickle formats
    def load(self, path: Path):
        if path.suffix in (".pkl", ".pickle"):
            raise ModelSecurityError(
                "Pickle format not allowed for security reasons"
            )
```

### 5.3 Security Features

- **Hash verification** - Verify model integrity before loading
- **Source allowlist** - Only load from trusted HuggingFace repos
- **No remote code execution** - `trust_remote_code=False` always
- **Safetensors preferred** - Non-executable tensor format
- **Local-first loading** - `local_files_only=True` by default

### 5.4 Usage

```python
from halo.security.model_loader import get_model_loader

loader = get_model_loader()
loader.register_hash("KB/bert-base-swedish-cased", "abc123...")
model = loader.load_huggingface("KB/bert-base-swedish-cased")
```

---

## 6. Dependency Security

### 6.1 Updated Dependencies

**Frontend:**
| Package | Version | CVE Fixed |
|---------|---------|-----------|
| axios | 1.7.9 | CVE-2025-27152, CVE-2025-58754 |
| vite | 5.4.11 | Path traversal |

**Backend:**
| Package | Version | Notes |
|---------|---------|-------|
| fastapi | 0.115.0 | Security patches |
| cryptography | 43.0.0 | AES-256-GCM support |
| argon2-cffi | 23.1.0 | Password hashing |

### 6.2 Recommendations

- Add `pip-audit` and `npm audit` to CI pipeline
- Generate lockfiles for reproducible builds
- Monitor torch/transformers for CVEs (large attack surface)

---

## 7. Compliance Status

### 7.1 GDPR (via Swedish implementation)
- [x] Data minimization
- [x] Encryption at rest (AES-256)
- [x] Audit logging with integrity
- [ ] Data subject access request workflow
- [ ] Right to erasure workflow

### 7.2 Brottsdatalagen
- [x] Tiered human-in-loop review
- [x] Rubber-stamp detection
- [x] Immutable audit trail (hash chain)
- [ ] 25-year retention enforcement

### 7.3 Säkerhetsskyddslagen
- [x] Access control (RBAC + case-level)
- [x] Audit logging with integrity
- [x] AES-256 encryption
- [x] Need-to-know via CaseAssignment
- [ ] Classification marking
- [ ] Security clearance verification

---

## 8. Remediation Status

### Completed in Revision 2
- [x] HMAC blind indexing (fixes rainbow table attack)
- [x] AES-256-GCM encryption (Säkerhetsskyddslagen compliance)
- [x] User database model with password storage
- [x] Session management with device tracking
- [x] Account lockout (credential stuffing protection)
- [x] Case-level access control (need-to-know)
- [x] Audit log hash chain (tamper detection)
- [x] Luhn validation for Swedish identifiers

### Completed in Revision 4

- [x] Proper HKDF key derivation (cryptography library)
- [x] Redis session management with concurrent limits
- [x] Combined IP + User lockout (prevents DoS via lockout)
- [x] CaseAccessManager for need-to-know enforcement
- [x] CSRF protection (double-submit cookie)
- [x] Per-user rate limiting with endpoint-specific limits
- [x] Secure ML model loader (prevents pickle attacks)

### Remaining High Priority

- [ ] BankID/SITHS integration
- [ ] Token revocation API (session model supports it)

### Medium Priority

- [ ] Key rotation mechanism
- [ ] Breached password detection (HIBP)
- [ ] Request body size limits

---

## 9. Testing Recommendations

### Security Testing Checklist
```bash
# Dependency scans
pip-audit
npm audit

# Static analysis
bandit -r halo/
semgrep --config=p/security-audit halo/

# Secrets scanning
trufflehog filesystem .
gitleaks detect

# Audit log integrity
python -c "from halo.db.models import AuditLog; ..."
```

### Penetration Testing Scope
1. Blind index reversal attempts (should fail without key)
2. Audit log tampering detection
3. Session hijacking/fixation
4. Case access without assignment
5. Account lockout bypass
6. JWT manipulation (algorithm confusion)

---

## 10. Files Modified

| File | Changes (Revision 2) |
|------|----------------------|
| `halo/security/encryption.py` | AES-256-GCM, HMAC blind indexing, Luhn validation |
| `halo/db/models.py` | User, UserSession, CaseAssignment, AuditLog hash chain |
| `halo/db/types.py` | Updated for AES-256-GCM |
| `halo/security/__init__.py` | Export new functions |

| File                                     | Changes (Revision 3)                         |
|------------------------------------------|----------------------------------------------|
| `halo/entities/swedish_personnummer.py`  | Fixed century calculation for `+` separator  |
| `tests/unit/test_personnummer.py`        | Corrected test data checksums                |

| File                              | Changes (Revision 4)                                |
|-----------------------------------|-----------------------------------------------------|
| `halo/security/encryption.py`     | Proper HKDF key derivation, `derive_key()` export   |
| `halo/security/sessions.py`       | NEW: Redis-backed SessionManager                    |
| `halo/security/lockout.py`        | NEW: Combined IP + User LockoutManager              |
| `halo/security/access.py`         | NEW: CaseAccessManager for need-to-know             |
| `halo/security/csrf.py`           | NEW: CSRF protection with double-submit cookie      |
| `halo/security/ratelimit.py`      | NEW: Per-user rate limiting with Redis              |
| `halo/security/model_loader.py`   | NEW: Secure ML model loader                         |
| `halo/security/__init__.py`       | Added `derive_key` export                           |

---

## 11. Conclusion

**Current Security Posture: HIGH**

The platform has addressed critical security vulnerabilities identified in expert review and implemented comprehensive security framework controls:

1. **Personnummer indexing** - HMAC blind indexing prevents rainbow table attacks
2. **Encryption** - AES-256-GCM with proper HKDF key derivation
3. **Authentication** - Full User model with combined IP + User lockout
4. **Authorization** - RBAC + CaseAccessManager for need-to-know enforcement
5. **Audit integrity** - HMAC hash chain prevents tampering
6. **Session management** - Redis-backed with concurrent session limits
7. **API security** - CSRF protection, per-user rate limiting
8. **ML pipeline** - Secure model loading prevents pickle attacks

### Production Readiness Blockers

1. BankID/SITHS integration for Swedish law enforcement
2. External penetration testing
3. Key management solution (Vault/KMS)

### Threat Model Considerations

For Swedish law enforcement, realistic threats include:
- Organized crime seeking to identify informants
- Foreign intelligence seeking operational data
- Corrupt insiders with legitimate access
- Hacktivists seeking to embarrass

The current security controls address insider threats through:

- Audit log integrity (can't cover tracks)
- Need-to-know access via CaseAccessManager (limited blast radius)
- Session management with device tracking (can't share credentials undetected)
- Combined lockout prevents credential abuse
- Per-user rate limiting detects anomalous access patterns

---

**Report Prepared By:** Claude Code Security Analysis
**Expert Review By:** Security Consultant
**Revision:** 4 (Security framework implementation)
**Next Review Date:** Before production deployment
