# Halo Platform Security Framework

**Version:** 1.0 | **Date:** 2025-12-21 | **Classification:** INTERNAL - SECURITY SENSITIVE

---

## Executive Summary

This framework defines security requirements for Halo, a Swedish law enforcement intelligence platform handling personnummer, financial transactions, and case intelligence. It addresses the gaps identified in the security assessment and provides implementation guidance.

---

## 1. Threat Model

### 1.1 Threat Actors

| Actor | Motivation | Capability | Priority |
|-------|------------|------------|----------|
| **Organized Crime** | Identify informants, compromise investigations | High | **P0** |
| **Foreign Intelligence** | Strategic intelligence gathering | Very High | **P0** |
| **Corrupt Insider** | Personal gain, coercion | High (legitimate access) | **P0** |
| **Opportunistic Attacker** | Financial gain | Medium | **P2** |

### 1.2 Critical Assets

| Asset | Impact if Compromised |
|-------|----------------------|
| Personnummer database | Identity theft, informant exposure |
| Case intelligence | Criminal investigations compromised |
| Audit logs | Evidence tampering, cover-up |
| User credentials | Unauthorized access to all above |

---

## 2. Authentication

### 2.1 BankID Integration (Required for Production)

```python
# halo/security/bankid.py
class BankIDClient:
    """Swedish e-identification for law enforcement systems."""
    
    async def authenticate(self, end_user_ip: str, personnummer: str = None) -> dict:
        """Initiate BankID authentication."""
        payload = {"endUserIp": end_user_ip}
        if personnummer:
            payload["personalNumber"] = personnummer.replace("-", "")
        
        response = await self._client.post("/auth", json=payload)
        return response.json()  # {orderRef, autoStartToken, qrStartToken}
    
    async def collect(self, order_ref: str) -> dict:
        """Poll for authentication result."""
        response = await self._client.post("/collect", json={"orderRef": order_ref})
        return response.json()  # {status, completionData}
```

### 2.2 Session Management

```python
# halo/security/sessions.py
class SessionManager:
    """Redis-backed session management."""
    
    MAX_SESSIONS_PER_USER = 3
    ACCESS_TOKEN_TTL = 1800      # 30 minutes
    REFRESH_TOKEN_TTL = 604800   # 7 days
    
    async def create_session(self, user_id: str, ip: str, user_agent: str) -> tuple:
        """Create session, enforce concurrent session limit."""
        await self._enforce_session_limit(user_id)
        
        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(64)
        
        # Store hashed tokens
        await self.redis.setex(
            f"session:{self._hash(access_token)}",
            self.ACCESS_TOKEN_TTL,
            json.dumps({"user_id": user_id, "ip": ip, "ua": user_agent})
        )
        return access_token, refresh_token
    
    async def revoke_all_sessions(self, user_id: str) -> int:
        """Emergency session revocation."""
        # Required for incident response
        sessions = await self.redis.smembers(f"user:sessions:{user_id}")
        await self.redis.delete(f"user:sessions:{user_id}")
        return len(sessions)
```

### 2.3 Account Lockout (Fixed Logic)

The assessment had inverted lockout logic. Per-user lockout enables DoS attacks.

```python
# halo/security/lockout.py
class LockoutManager:
    """Combined IP + user lockout to prevent both brute force and DoS."""
    
    # Per-IP: Stop distributed brute force
    IP_CAPTCHA_THRESHOLD = 10
    IP_BLOCK_THRESHOLD = 50
    IP_BLOCK_DURATION = 3600  # 1 hour
    
    # Per-user: Stop targeted attacks, but use CAPTCHA not lockout
    USER_CAPTCHA_THRESHOLD = 3
    USER_NOTIFY_THRESHOLD = 5    # Alert legitimate user
    USER_BLOCK_THRESHOLD = 10    # Only after many failures
    USER_BLOCK_DURATION = 1800   # 30 minutes
    
    async def check_and_record(self, username: str, ip: str, success: bool):
        if success:
            await self.redis.delete(f"failures:user:{username}")
            return {"action": "allow"}
        
        # Record failure
        ip_failures = await self.redis.incr(f"failures:ip:{ip}")
        user_failures = await self.redis.incr(f"failures:user:{username}")
        
        # Decide response
        if ip_failures >= self.IP_BLOCK_THRESHOLD:
            return {"action": "block", "reason": "ip_blocked"}
        if user_failures >= self.USER_BLOCK_THRESHOLD:
            return {"action": "block", "reason": "user_blocked", "notify": True}
        if ip_failures >= self.IP_CAPTCHA_THRESHOLD or user_failures >= self.USER_CAPTCHA_THRESHOLD:
            return {"action": "captcha"}
        
        return {"action": "allow"}
```

---

## 3. Authorization

### 3.1 RBAC + Need-to-Know

RBAC alone is insufficient. An ANALYST shouldn't access every case.

```python
# halo/security/access.py
class CaseAccessManager:
    """Case-level access control (need-to-know)."""
    
    async def check_access(self, user: User, case_id: UUID, level: str = "read") -> bool:
        # Admins bypass
        if user.role >= Role.ADMIN:
            return True
        
        # Check case assignment
        assignment = await self.db.get(
            CaseAssignment,
            case_id=case_id,
            user_id=user.id,
            revoked_at=None
        )
        
        if not assignment:
            return False
        if assignment.expires_at and assignment.expires_at < datetime.utcnow():
            return False
        
        return self._level_sufficient(assignment.access_level, level)
    
    async def grant_access(self, granter: User, case_id: UUID, user_id: UUID,
                           level: str, justification: str, expires_in_days: int = None):
        """Grant requires owner/admin + justification."""
        if not await self.check_access(granter, case_id, "owner"):
            raise HTTPException(403, "Endast ärendeägare kan tilldela behörigheter")
        
        return CaseAssignment(
            case_id=case_id,
            user_id=user_id,
            access_level=level,
            granted_by=granter.id,
            justification=justification,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days) if expires_in_days else None
        )
```

### 3.2 Break-Glass Procedure

For emergencies when case owner is unavailable:

```python
class BreakGlassManager:
    """Emergency access with dual-admin approval and mandatory review."""
    
    MAX_DURATION = {"critical": 4, "high": 2, "medium": 1}  # hours
    REVIEW_DEADLINE = 24  # hours after expiration
    
    async def request_emergency_access(
        self, requestor: User, approver: User, case_id: UUID,
        justification: str, urgency: str = "high"
    ):
        # Requestor: SENIOR_ANALYST+, Approver: ADMIN, must be different people
        if requestor.id == approver.id:
            raise HTTPException(400, "Begärare och godkännare måste vara olika")
        
        duration = timedelta(hours=self.MAX_DURATION[urgency])
        
        # Create temporary access
        access = EmergencyAccess(
            case_id=case_id,
            requestor_id=requestor.id,
            approver_id=approver.id,
            justification=f"NÖDÅTKOMST: {justification}",
            expires_at=datetime.utcnow() + duration
        )
        
        # Notify stakeholders, create audit entry
        await self._notify_case_owner(case_id)
        await self._notify_security_team(access)
        
        return access
```

---

## 4. Cryptography

### 4.1 HMAC Blind Indexing (Critical Fix)

The assessment used plain SHA-256 which is trivially reversible:

```python
# WRONG: Rainbow table attack in ~10 minutes
hash = hashlib.sha256(personnummer.encode()).hexdigest()

# RIGHT: Requires secret key to reverse
def create_blind_index(plaintext: str, secret_key: bytes) -> str:
    """HMAC-SHA256 blind index - can't reverse without key."""
    normalized = re.sub(r"[-\s]", "", plaintext.lower())
    return hmac.new(secret_key, normalized.encode(), "sha256").hexdigest()[:32]
```

### 4.2 AES-256-GCM Encryption

Upgraded from Fernet (AES-128) for Säkerhetsskyddslagen compliance:

```python
# halo/security/encryption.py
class PIIEncryption:
    """AES-256-GCM for PII fields."""
    
    PREFIX = "enc2:"  # Distinguishes from old enc: format
    
    def __init__(self, encryption_key: bytes, index_key: bytes):
        assert len(encryption_key) == 32, "AES-256 requires 32-byte key"
        self._aesgcm = AESGCM(encryption_key)
        self._index_key = index_key
    
    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return f"{self.PREFIX}{b64encode(nonce).decode()}:{b64encode(ciphertext).decode()}"
    
    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext.startswith(self.PREFIX):
            raise ValueError("Unknown encryption format")
        nonce_b64, ct_b64 = ciphertext[len(self.PREFIX):].split(":")
        plaintext = self._aesgcm.decrypt(b64decode(nonce_b64), b64decode(ct_b64), None)
        return plaintext.decode()
```

### 4.3 Key Derivation (Use Real HKDF)

The assessment mentioned "HKDF-like" which is concerning. Use actual HKDF:

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

PURPOSES = {
    "pii_encryption": b"halo-pii-encryption-v1",
    "pii_index": b"halo-pii-blind-index-v1",
    "audit_chain": b"halo-audit-chain-v1",
}

def derive_key(master_key: bytes, purpose: str) -> bytes:
    """Derive purpose-specific key using HKDF."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=PURPOSES[purpose],
    ).derive(master_key)
```

---

## 5. Audit Log Integrity

### 5.1 HMAC Hash Chain

Prevents tampering and detects deletions:

```python
# halo/db/models.py
class AuditLog(Base):
    sequence_id = Column(Integer, primary_key=True, autoincrement=True)
    previous_hash = Column(String(64), nullable=False)  # "GENESIS" for first
    entry_hash = Column(String(64), nullable=False, unique=True)
    
    # ... other fields ...
    
    @classmethod
    def compute_hash(cls, previous_hash: str, data: dict, audit_key: bytes) -> str:
        """HMAC hash including previous entry."""
        content = json.dumps({"previous_hash": previous_hash, **data}, sort_keys=True)
        return hmac.new(audit_key, content.encode(), "sha256").hexdigest()
    
    @classmethod
    def verify_chain(cls, entries: list, audit_key: bytes) -> tuple[bool, int]:
        """Verify chain integrity. Returns (valid, first_invalid_seq)."""
        for i, entry in enumerate(entries):
            expected_prev = "GENESIS" if i == 0 else entries[i-1].entry_hash
            
            # Check chain linkage
            if entry.previous_hash != expected_prev:
                return False, entry.sequence_id
            
            # Check sequence gaps (detects deletions)
            if i > 0 and entry.sequence_id != entries[i-1].sequence_id + 1:
                return False, entry.sequence_id
            
            # Verify hash
            computed = cls.compute_hash(entry.previous_hash, entry.to_dict(), audit_key)
            if not hmac.compare_digest(entry.entry_hash, computed):
                return False, entry.sequence_id
        
        return True, None
```

### 5.2 External Replication

Hash chain detects modification but not deletion of recent entries. Mitigate with:

```python
# Replicate to append-only external store
async def replicate_audit_entry(entry: AuditLog):
    # Option 1: S3 with Object Lock
    await s3.put_object(
        Bucket="halo-audit-immutable",
        Key=f"audit/{entry.sequence_id}.json",
        Body=json.dumps(entry.to_dict()),
        ObjectLockMode="GOVERNANCE",
        ObjectLockRetainUntilDate=datetime.utcnow() + timedelta(days=365*25)
    )
    
    # Option 2: SIEM ingestion
    await siem.send(entry.to_dict())
```

---

## 6. API Security

### 6.1 Rate Limiting (Per-User + Per-Endpoint)

Per-IP fails behind NAT. Use authenticated user + endpoint-specific limits:

```python
RATE_LIMITS = {
    "/api/v1/auth/login": (5, 60),        # 5/minute - auth is sensitive
    "/api/v1/search": (30, 60),           # 30/minute - expensive
    "/api/v1/export": (5, 3600),          # 5/hour - data exfil risk
    "default": (100, 60),                  # 100/minute
}

async def rate_limit(request: Request, user_id: str = None):
    key = f"ratelimit:user:{user_id}" if user_id else f"ratelimit:ip:{request.client.host}"
    key += f":{request.url.path}"
    
    max_requests, window = RATE_LIMITS.get(request.url.path, RATE_LIMITS["default"])
    
    current = await redis.incr(key)
    await redis.expire(key, window)
    
    if current > max_requests:
        raise HTTPException(429, headers={"Retry-After": str(window)})
```

### 6.2 CSRF Protection

```python
class CSRFProtection:
    """Double-submit cookie pattern."""
    
    def generate_token(self) -> str:
        timestamp = int(datetime.utcnow().timestamp())
        random = secrets.token_urlsafe(32)
        message = f"{timestamp}.{random}"
        sig = hmac.new(self._key, message.encode(), "sha256").hexdigest()[:16]
        return f"{message}.{sig}"
    
    async def verify(self, request: Request):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return
        
        cookie = request.cookies.get("csrf_token")
        header = request.headers.get("X-CSRF-Token")
        
        if not cookie or not header:
            raise HTTPException(403, "CSRF-token saknas")
        if not hmac.compare_digest(cookie, header):
            raise HTTPException(403, "CSRF-token matchar inte")
```

### 6.3 Security Headers

```python
class SecurityHeadersMiddleware:
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        
        if is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        return response
```

---

## 7. Infrastructure

### 7.1 Network Zones

```
INTERNET → WAF/DDoS → Load Balancer (TLS 1.3 termination)
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
    DMZ Zone          App Zone           Data Zone
    (Nginx)           (API, Workers)     (PostgreSQL, Redis)
                           │                  │
                      ML Zone ────────────────┘
                      (Inference)
```

### 7.2 Container Security

```yaml
# kubernetes/deployment.yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]

resources:
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

### 7.3 Database Security

```sql
-- Application role: No DELETE on audit_logs
REVOKE DELETE ON audit_logs FROM halo_app;

-- Row-level security for cases
ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

CREATE POLICY case_access ON cases
    USING (
        current_setting('app.user_role')::int >= 3  -- Admin bypass
        OR id IN (
            SELECT case_id FROM case_assignments 
            WHERE user_id = current_setting('app.user_id')::uuid
            AND revoked_at IS NULL
        )
    );

-- Require SSL
ALTER SYSTEM SET ssl = on;
```

---

## 8. Swedish Compliance

### 8.1 Compliance Matrix

| Requirement | Regulation | Implementation | Status |
|-------------|------------|----------------|--------|
| Encryption at rest | GDPR Art. 32 | AES-256-GCM | ✅ |
| Access control | GDPR Art. 25 | RBAC + case-level | ✅ |
| Audit logging | GDPR Art. 30 | Hash chain | ✅ |
| Human oversight | Brottsdatalagen 2:19 | Tiered review | ✅ |
| Breach notification | GDPR Art. 33 | Procedures defined | ✅ |
| Data subject rights | GDPR Art. 15-22 | Not implemented | ❌ |
| Retention limits | Brottsdatalagen | Not implemented | ❌ |

### 8.2 Breach Notification

| Authority | Deadline | Condition |
|-----------|----------|-----------|
| Datainspektionen | 72 hours | Personal data breach |
| Affected individuals | Without undue delay | High risk to rights |
| Säkerhetspolisen | Immediate | Classified data involved |

---

## 9. Incident Response

### 9.1 Severity Levels

| Level | Response Time | Examples |
|-------|---------------|----------|
| P1 Critical | Immediate | Active breach, data exfiltration |
| P2 High | < 4 hours | Auth bypass, encryption failure |
| P3 Medium | < 24 hours | Anomalous access patterns |
| P4 Low | < 72 hours | Policy violations |

### 9.2 Credential Compromise Runbook

1. **Immediate:** `await session_manager.revoke_all_sessions(user_id)`
2. **Investigate:** Review audit logs for user activity
3. **Contain:** If data accessed, identify scope
4. **Recover:** Reset password, require MFA, monitor 30 days
5. **Post-incident:** Root cause analysis, update detection

---

## 10. ML Pipeline Security

### 10.1 Model Loading

```python
class SecureModelLoader:
    """Prevent pickle deserialization attacks."""
    
    ALLOWED_SOURCES = {"huggingface.co/KB", "internal/halo-models"}
    
    def load(self, path: Path, expected_hash: str = None):
        # Verify hash
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_hash and actual_hash != expected_hash:
            raise SecurityError("Model integrity check failed")
        
        # Safe loading
        if path.suffix == ".safetensors":
            from safetensors.torch import load_file
            return load_file(path)
        
        if path.is_dir():  # HuggingFace
            return AutoModel.from_pretrained(
                path,
                trust_remote_code=False,  # Never run arbitrary code
                local_files_only=True
            )
        
        raise SecurityError(f"Unsupported format: {path.suffix}")
```

---

## 11. Implementation Roadmap

### Phase 1: Critical (Weeks 1-2) ✅
- [x] HMAC blind indexing
- [x] AES-256-GCM encryption  
- [x] Audit log hash chain
- [ ] Token revocation API

### Phase 2: High (Weeks 3-4)
- [ ] BankID integration
- [ ] Case-level access enforcement
- [ ] Break-glass procedure
- [ ] CSRF protection
- [ ] Per-user rate limiting

### Phase 3: Medium (Weeks 5-6)
- [ ] Vault/KMS integration
- [ ] Key rotation tooling
- [ ] SIEM integration
- [ ] Penetration test

### Phase 4: Compliance (Weeks 7-8)
- [ ] GDPR data subject workflows
- [ ] Retention policy
- [ ] Security training
- [ ] Documentation

---

## Appendix: Pre-Deployment Checklist

- [ ] Secrets in Vault/KMS (not env vars)
- [ ] BankID integration tested
- [ ] TLS 1.3 on load balancer
- [ ] Penetration test completed
- [ ] Incident response documented
- [ ] Audit log integrity verified
- [ ] Monitoring alerts configured
- [ ] On-call rotation established

---

**Document Control:** v1.0 | Security Team | Review before production deployment