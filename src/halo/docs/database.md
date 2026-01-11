# Halo Database Schema Documentation

## Overview

Halo uses PostgreSQL with SQLAlchemy ORM. The schema supports:
- Entity resolution across fragmented data sources
- Financial transaction analysis for AML
- Tiered alert review system (Brottsdatalagen compliance)
- Immutable audit logging with hash chain integrity
- Case management with need-to-know access control

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USERS & AUTH                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐         ┌──────────────────┐                             │
│   │    users     │────────►│  user_sessions   │                             │
│   └──────────────┘         └──────────────────┘                             │
│          │                                                                   │
│          └─────────────────────────────────┐                                │
│                                            ▼                                │
│                                   ┌────────────────┐                        │
│                                   │case_assignments│                        │
│                                   └────────────────┘                        │
│                                            │                                │
└────────────────────────────────────────────┼────────────────────────────────┘
                                             │
┌────────────────────────────────────────────┼────────────────────────────────┐
│                           ENTITY GRAPH     │                                │
├────────────────────────────────────────────┼────────────────────────────────┤
│                                            ▼                                │
│   ┌──────────────┐         ┌──────────────────────────┐                     │
│   │   entities   │◄───────►│  entity_relationships    │                     │
│   └──────────────┘         └──────────────────────────┘                     │
│          │                                                                   │
│          ├───────────────────────────────────────────┐                      │
│          │                                           │                      │
│          ▼                                           ▼                      │
│   ┌────────────────────┐                    ┌──────────────┐                │
│   │document_entity_    │                    │ transactions │                │
│   │    mentions        │                    └──────────────┘                │
│   └────────────────────┘                             │                      │
│          │                                           │                      │
│          ▼                                           │                      │
│   ┌──────────────┐                                   │                      │
│   │  documents   │                                   │                      │
│   └──────────────┘                                   │                      │
│                                                      │                      │
└──────────────────────────────────────────────────────┼──────────────────────┘
                                                       │
┌──────────────────────────────────────────────────────┼──────────────────────┐
│                        ALERTS & CASES                │                      │
├──────────────────────────────────────────────────────┼──────────────────────┤
│                                                      ▼                      │
│   ┌──────────────┐         ┌──────────────────────────┐                     │
│   │    alerts    │◄───────►│    alert_decisions       │                     │
│   └──────────────┘         └──────────────────────────┘                     │
│          │                                                                   │
│          ▼                                                                   │
│   ┌──────────────┐         ┌──────────────────────────┐                     │
│   │    cases     │◄───────►│    case_assignments      │                     │
│   └──────────────┘         └──────────────────────────┘                     │
│          │                                                                   │
│          ▼                                                                   │
│   ┌──────────────┐                                                          │
│   │ case_notes   │                                                          │
│   └──────────────┘                                                          │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                              AUDIT LOG                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ┌──────────────────────────────────────────────────────────────────┐       │
│   │                        audit_log                                  │       │
│   │  (Immutable, hash-chained for tamper detection)                  │       │
│   └──────────────────────────────────────────────────────────────────┘       │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Tables

### users

User authentication and profile information.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `username` | VARCHAR(100) | Unique username |
| `email` | VARCHAR(255) | Unique email |
| `password_hash` | VARCHAR(255) | Argon2id hash |
| `full_name` | VARCHAR(255) | Display name |
| `role` | ENUM | User role (viewer, analyst, senior_analyst, admin, system) |
| `is_active` | BOOLEAN | Account active status |
| `is_verified` | BOOLEAN | Email verified |
| `failed_login_attempts` | INTEGER | Failed login counter |
| `locked_until` | TIMESTAMP | Account lockout expiry |
| `totp_secret` | VARCHAR(32) | MFA secret (optional) |
| `totp_enabled` | BOOLEAN | MFA enabled flag |
| `password_changed_at` | TIMESTAMP | Last password change |
| `must_change_password` | BOOLEAN | Force password change |
| `last_login` | TIMESTAMP | Last successful login |
| `last_login_ip` | VARCHAR(45) | IP of last login |
| `created_at` | TIMESTAMP | Account creation |
| `updated_at` | TIMESTAMP | Last update |

**Indexes:**
- `idx_users_username` (username)
- `idx_users_email` (email)
- `idx_users_role` (role)

**Security Notes:**
- Passwords hashed with Argon2id
- Account locks after 5 failed attempts (30 minutes)
- Supports TOTP-based MFA

---

### user_sessions

Active user sessions for concurrent session control.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK → users.id |
| `token_hash` | VARCHAR(64) | SHA-256 of session token |
| `ip_address` | VARCHAR(45) | Client IP |
| `user_agent` | VARCHAR(500) | Browser/client info |
| `device_fingerprint` | VARCHAR(64) | Device hash |
| `created_at` | TIMESTAMP | Session start |
| `expires_at` | TIMESTAMP | Session expiry |
| `revoked_at` | TIMESTAMP | Manual revocation |

---

### entities

Core entity table for people, companies, properties, and vehicles.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `entity_type` | ENUM | person, company, property, vehicle |
| `personnummer` | ENCRYPTED | Swedish personal ID (encrypted) |
| `organisationsnummer` | ENCRYPTED | Swedish org number (encrypted) |
| `personnummer_hash` | VARCHAR(64) | HMAC hash for lookup |
| `organisationsnummer_hash` | VARCHAR(64) | HMAC hash for lookup |
| `display_name` | VARCHAR(255) | Display name |
| `attributes` | JSONB | Flexible attributes |
| `sources` | TEXT[] | Data sources |
| `risk_level` | VARCHAR(20) | low, medium, high, very_high |
| `status` | VARCHAR(20) | active, inactive, etc. |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update |

**Indexes:**
- `idx_entities_personnummer_hash` (personnummer_hash, UNIQUE)
- `idx_entities_organisationsnummer_hash` (organisationsnummer_hash, UNIQUE)
- `idx_entities_type` (entity_type)
- `idx_entities_display_name` (display_name)

**Security Notes:**
- PII fields encrypted with AES-256-GCM
- Hash indexes use HMAC (not plain SHA-256) to prevent rainbow table attacks

---

### entity_relationships

Relationships between entities (graph edges).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `from_entity_id` | UUID | FK → entities.id |
| `to_entity_id` | UUID | FK → entities.id |
| `relationship_type` | ENUM | Relationship type (see below) |
| `attributes` | JSONB | Relationship metadata |
| `confidence` | FLOAT | Confidence score (0-1) |
| `valid_from` | TIMESTAMP | Start of validity |
| `valid_to` | TIMESTAMP | End of validity |
| `source` | VARCHAR(100) | Data source |
| `created_at` | TIMESTAMP | Creation time |

**Relationship Types:**
- Person-Company: `owner`, `board_member`, `board_chair`, `ceo`, `employee`, `beneficial_owner`, `signatory`, `auditor`
- Person-Person: `family`, `spouse`, `business_partner`, `associated`
- Company-Company: `subsidiary`, `parent`, `supplier`, `customer`
- Person/Company-Property: `owns_property`, `registered_at`, `colocated`
- Person-Vehicle: `owns_vehicle`
- Financial: `transacted_with`

---

### documents

Ingested documents for NLP analysis.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `title` | VARCHAR(500) | Document title |
| `source` | VARCHAR(100) | upload, scrape, api |
| `source_url` | TEXT | Original URL |
| `document_type` | VARCHAR(50) | forum_post, news, report, etc. |
| `raw_text` | TEXT | Extracted text content |
| `language` | VARCHAR(10) | Language code (default: sv) |
| `entities_extracted` | JSONB | NER results |
| `sentiment_scores` | JSONB | Sentiment analysis results |
| `threat_indicators` | TEXT[] | Detected threat terms |
| `summary` | TEXT | AI-generated summary |
| `processed` | BOOLEAN | Processing complete |
| `processed_at` | TIMESTAMP | Processing time |
| `created_at` | TIMESTAMP | Upload time |

---

### document_entity_mentions

Links documents to mentioned entities.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `document_id` | UUID | FK → documents.id |
| `entity_id` | UUID | FK → entities.id |
| `start_char` | INTEGER | Start position in text |
| `end_char` | INTEGER | End position in text |
| `mention_text` | VARCHAR(500) | The mentioned text |
| `confidence` | FLOAT | NER confidence score |

---

### transactions

Financial transactions for AML analysis.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `transaction_id` | VARCHAR(100) | External transaction ID |
| `timestamp` | TIMESTAMP | Transaction time |
| `from_entity_id` | UUID | FK → entities.id (optional) |
| `to_entity_id` | UUID | FK → entities.id (optional) |
| `from_account` | ENCRYPTED | Source account (encrypted) |
| `to_account` | ENCRYPTED | Destination account (encrypted) |
| `amount` | FLOAT | Transaction amount |
| `currency` | VARCHAR(3) | Currency code (default: SEK) |
| `transaction_type` | VARCHAR(50) | Transaction type |
| `description` | TEXT | Transaction description |
| `risk_score` | FLOAT | Calculated risk score |
| `risk_factors` | TEXT[] | Identified risk factors |
| `created_at` | TIMESTAMP | Import time |

**Indexes:**
- `idx_transactions_timestamp` (timestamp)
- `idx_transactions_from` (from_entity_id)
- `idx_transactions_to` (to_entity_id)

---

### alerts

Alerts generated by anomaly detection with tiered review.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `alert_type` | VARCHAR(50) | Alert category |
| `severity` | VARCHAR(20) | critical, high, medium, low |
| `title` | VARCHAR(255) | Alert title |
| `description` | TEXT | Alert details |
| `entity_ids` | UUID[] | Related entities |
| `transaction_ids` | UUID[] | Related transactions |
| `confidence` | FLOAT | Detection confidence |
| `tier` | INTEGER | Review tier (1, 2, 3) |
| `affects_person` | BOOLEAN | Impacts identifiable person |
| `acknowledged_by` | VARCHAR(100) | Tier 2: Who acknowledged |
| `acknowledged_at` | TIMESTAMP | Tier 2: When acknowledged |
| `approved_by` | VARCHAR(100) | Tier 3: Who approved |
| `approved_at` | TIMESTAMP | Tier 3: When approved |
| `approval_decision` | VARCHAR(20) | approved, rejected, escalated |
| `approval_justification` | TEXT | Tier 3: Decision reasoning |
| `can_export` | BOOLEAN | Export permitted |
| `displayed_at` | TIMESTAMP | When shown to reviewer |
| `review_duration_seconds` | FLOAT | Time spent reviewing |
| `is_rubber_stamp` | BOOLEAN | Suspiciously fast review |
| `status` | VARCHAR(20) | Alert status |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update |

**Tier System (Brottsdatalagen Compliance):**
- **Tier 1**: Informational only, no review required
- **Tier 2**: Requires acknowledgment before export
- **Tier 3**: Requires explicit approval with justification (affects individuals)

---

### cases

Investigation case management.

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `case_number` | VARCHAR(50) | Case reference number |
| `title` | VARCHAR(255) | Case title |
| `description` | TEXT | Case description |
| `status` | VARCHAR(20) | open, closed, escalated |
| `priority` | VARCHAR(20) | low, medium, high, critical |
| `assigned_to` | VARCHAR(100) | Primary assignee |
| `entity_ids` | UUID[] | Related entities |
| `alert_ids` | UUID[] | Related alerts |
| `created_by` | UUID | FK → users.id |
| `created_at` | TIMESTAMP | Creation time |
| `updated_at` | TIMESTAMP | Last update |
| `closed_at` | TIMESTAMP | Closure time |
| `closed_by` | UUID | Who closed |
| `resolution` | TEXT | Closure resolution |

---

### case_assignments

Case-level access control (need-to-know).

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `case_id` | UUID | FK → cases.id |
| `user_id` | UUID | FK → users.id |
| `role` | VARCHAR(50) | lead, analyst, reviewer |
| `granted_by` | UUID | Who granted access |
| `granted_at` | TIMESTAMP | When granted |
| `revoked_at` | TIMESTAMP | When revoked |

---

### audit_log

Immutable audit trail with hash chain integrity.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGINT | Auto-increment primary key |
| `timestamp` | TIMESTAMP | Event time |
| `user_id` | VARCHAR(100) | Acting user |
| `user_name` | VARCHAR(255) | User display name |
| `action` | VARCHAR(50) | view, create, update, delete, export, etc. |
| `resource_type` | VARCHAR(50) | entity, case, alert, etc. |
| `resource_id` | UUID | Affected resource |
| `details` | JSONB | Action details |
| `ip_address` | VARCHAR(45) | Client IP |
| `user_agent` | VARCHAR(500) | Client info |
| `previous_hash` | VARCHAR(64) | Hash of previous entry |
| `entry_hash` | VARCHAR(64) | Hash of this entry |

**Security Notes:**
- Table is INSERT-only (no UPDATE/DELETE permissions)
- Hash chain enables tamper detection
- `entry_hash = SHA-256(timestamp + user_id + action + resource_id + previous_hash)`

---

## Custom Types

### Encrypted Types

Custom SQLAlchemy types that encrypt data at rest:

- `EncryptedPersonnummer` - Encrypts Swedish personal ID numbers
- `EncryptedOrganisationsnummer` - Encrypts Swedish org numbers
- `EncryptedAccountNumber` - Encrypts bank account numbers

**Encryption Details:**
- Algorithm: AES-256-GCM
- Key: Derived from `PII_ENCRYPTION_KEY` environment variable
- Each value has unique IV/nonce

### Blind Index

For encrypted fields that need searching:
- HMAC-SHA256 with secret key
- Stored in `*_hash` columns
- Enables exact-match lookups without decryption

---

## Migrations

Migrations are managed with Alembic.

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Run pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Show migration history
alembic history
```

Migration files: `halo/db/migrations/versions/`

---

## Performance Considerations

### Indexes
All foreign keys and frequently-queried columns have indexes.

### Partitioning (Future)
Consider partitioning for:
- `transactions` - By timestamp (monthly)
- `audit_log` - By timestamp (monthly)

### Connection Pooling
Use PgBouncer or SQLAlchemy's built-in pooling for production:

```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
)
```
