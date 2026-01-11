# Halo API Documentation

## Overview

The Halo API is a RESTful API built with FastAPI. All endpoints require authentication unless otherwise noted.

**Base URL:** `http://localhost:8000/api/v1`

## Authentication

### Methods

Halo supports three authentication methods:

1. **Username/Password** - Traditional login with JWT tokens
2. **BankID** - Swedish electronic identification
3. **OIDC/SAML** - Federation with identity providers

### Tokens

All authenticated requests require a Bearer token in the Authorization header:

```
Authorization: Bearer <access_token>
```

Access tokens expire after 30 minutes. Use the refresh token to obtain new access tokens.

---

## Authentication Endpoints

### POST /api/v1/auth/login

Login with username and password.

**Request:**
```json
{
  "username": "string",
  "password": "string",
  "captcha_token": "string (optional)"
}
```

**Response:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Errors:**
- `401` - Invalid credentials
- `423` - Account locked (too many failed attempts)

---

### POST /api/v1/auth/refresh

Refresh an access token.

**Request:**
```json
{
  "refresh_token": "string"
}
```

**Response:**
```json
{
  "access_token": "string",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### POST /api/v1/auth/logout

Revoke the current session.

**Response:**
```json
{
  "message": "Logged out successfully"
}
```

---

### GET /api/v1/auth/me

Get current user information.

**Response:**
```json
{
  "user_id": "uuid",
  "username": "string",
  "email": "string",
  "role": "analyst|investigator|admin",
  "personnummer_last4": "1234"
}
```

---

### POST /api/v1/auth/bankid/init

Initiate BankID authentication.

**Request:**
```json
{
  "personnummer": "string (optional, 12 digits)"
}
```

**Response:**
```json
{
  "order_ref": "string",
  "auto_start_token": "string",
  "qr_start_token": "string",
  "qr_start_secret": "string",
  "auto_start_url": "bankid:///?autostarttoken=..."
}
```

---

### POST /api/v1/auth/bankid/qr

Get current QR code data for BankID.

**Request:**
```json
{
  "order_ref": "string"
}
```

**Response:**
```json
{
  "qr_data": "string"
}
```

---

### POST /api/v1/auth/bankid/collect

Poll for BankID authentication status.

**Request:**
```json
{
  "order_ref": "string"
}
```

**Response (pending):**
```json
{
  "status": "pending",
  "hint_code": "outstandingTransaction"
}
```

**Response (complete):**
```json
{
  "status": "complete",
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 1800
}
```

---

### POST /api/v1/auth/bankid/cancel

Cancel a pending BankID authentication.

**Request:**
```json
{
  "order_ref": "string"
}
```

---

## Entity Endpoints

### GET /api/v1/entities/{entity_id}

Get entity by ID.

**Response:**
```json
{
  "id": "uuid",
  "entity_type": "person|company|property|vehicle",
  "display_name": "string",
  "personnummer": "string (masked)",
  "organisationsnummer": "string",
  "attributes": {},
  "sources": ["scb", "bolagsverket"]
}
```

---

### POST /api/v1/entities

Create a new entity.

**Request:**
```json
{
  "entity_type": "person|company|property|vehicle",
  "display_name": "string",
  "personnummer": "string (optional)",
  "organisationsnummer": "string (optional)",
  "attributes": {}
}
```

**Response:** Same as GET entity

---

### PATCH /api/v1/entities/{entity_id}

Update an entity.

**Request:**
```json
{
  "display_name": "string (optional)",
  "attributes": {}
}
```

---

### GET /api/v1/entities/{entity_id}/relationships

Get relationships for an entity.

**Query Parameters:**
- `relationship_type` - Filter by relationship type
- `direction` - `incoming`, `outgoing`, or `both` (default)

**Response:**
```json
{
  "relationships": [
    {
      "id": "uuid",
      "from_entity_id": "uuid",
      "to_entity_id": "uuid",
      "relationship_type": "styrelseledamot|agare|anstallning|...",
      "source": "bolagsverket",
      "attributes": {},
      "confidence": 0.95
    }
  ]
}
```

---

### POST /api/v1/entities/{entity_id}/relationships

Create a relationship from this entity.

**Request:**
```json
{
  "to_entity_id": "uuid",
  "relationship_type": "string",
  "source": "string",
  "attributes": {},
  "confidence": 1.0
}
```

---

## Search Endpoints

### GET /api/v1/search

Search entities by name.

**Query Parameters:**
- `q` (required) - Search query
- `entity_type` - Filter by type (person, company, property, vehicle)
- `limit` - Max results (1-100, default 10)
- `offset` - Pagination offset

**Response:**
```json
{
  "query": "string",
  "total": 42,
  "results": [
    {
      "id": "uuid",
      "entity_type": "company",
      "display_name": "IKEA AB",
      "organisationsnummer": "5560747569",
      "attributes": {},
      "score": 0.95
    }
  ]
}
```

---

## Alert Endpoints

### GET /api/v1/alerts

List alerts requiring review.

**Query Parameters:**
- `tier` - Filter by tier (1, 2, 3)
- `status` - Filter by status (pending, acknowledged, approved, rejected)
- `limit` - Max results (default 50)

**Response:**
```json
{
  "alerts": [
    {
      "id": "uuid",
      "alert_type": "aml_suspicious_pattern",
      "severity": "high",
      "title": "Unusual transaction pattern",
      "description": "...",
      "confidence": 0.87,
      "tier": 3,
      "affects_person": true,
      "status": "pending",
      "review_status": "pending",
      "can_export": false,
      "is_rubber_stamp": false,
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 15
}
```

---

### GET /api/v1/alerts/{alert_id}

Get alert details.

---

### POST /api/v1/alerts/{alert_id}/acknowledge

Acknowledge a Tier 2 alert.

**Request:**
```json
{
  "displayed_at": "2025-01-15T10:30:00Z"
}
```

**Notes:**
- Tier 2 alerts require human acknowledgment before export
- System tracks review time to detect rubber-stamping

---

### POST /api/v1/alerts/{alert_id}/approve

Approve or reject a Tier 3 alert.

**Request:**
```json
{
  "decision": "approved|rejected|escalated",
  "justification": "Detailed justification (min 10 chars)",
  "displayed_at": "2025-01-15T10:30:00Z"
}
```

**Notes:**
- Tier 3 alerts affect individuals and require explicit approval per Brottsdatalagen 2 kap. 19 §
- Garbage justifications are rejected ("ok", "yes", "approved", etc.)
- Review time under 2 seconds triggers rubber-stamp warning

---

### POST /api/v1/alerts/batch/acknowledge

Batch acknowledge Tier 2 alerts.

**Request:**
```json
{
  "alert_ids": ["uuid", "uuid"],
  "displayed_at": "2025-01-15T10:30:00Z"
}
```

---

### GET /api/v1/alerts/review-stats

Get review statistics for rubber-stamp detection.

**Response:**
```json
{
  "user_id": "string",
  "total_reviews": 150,
  "approval_rate": 0.98,
  "avg_review_seconds": 3.5,
  "is_suspicious": true
}
```

---

## Case Endpoints

### GET /api/v1/cases

List cases.

**Query Parameters:**
- `status` - Filter by status (open, closed)
- `limit` - Max results (default 50)

**Response:**
```json
{
  "cases": [
    {
      "id": "uuid",
      "case_number": "2025-001",
      "title": "Investigation Title",
      "description": "...",
      "status": "open",
      "assigned_to": "analyst@example.com",
      "entity_ids": ["uuid"],
      "alert_ids": ["uuid"],
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T12:00:00Z",
      "closed_at": null
    }
  ]
}
```

---

### POST /api/v1/cases

Create a new case.

**Request:**
```json
{
  "case_number": "2025-001",
  "title": "Investigation Title",
  "description": "Case description",
  "assigned_to": "analyst@example.com",
  "entity_ids": ["uuid"],
  "alert_ids": ["uuid"]
}
```

---

### GET /api/v1/cases/{case_id}

Get case details.

---

### PATCH /api/v1/cases/{case_id}

Update a case.

---

### POST /api/v1/cases/{case_id}/close

Close a case.

**Request:**
```json
{
  "resolution": "Concluded - no action required",
  "notes": "Optional closing notes"
}
```

---

## Audit Endpoints

### GET /api/v1/audit

Get audit log entries.

**Query Parameters:**
- `entity_id` - Filter by entity
- `user_id` - Filter by user
- `action` - Filter by action (view, create, update, delete, export)
- `start_date` - Start of date range
- `end_date` - End of date range
- `limit` - Max results (default 100)
- `offset` - Pagination offset

**Response:**
```json
{
  "entries": [
    {
      "id": "uuid",
      "timestamp": "2025-01-15T10:30:00Z",
      "user_id": "string",
      "user_name": "string",
      "action": "view",
      "resource_type": "entity",
      "resource_id": "uuid",
      "details": {},
      "ip_address": "192.168.1.1",
      "chain_hash": "sha256..."
    }
  ],
  "total": 1500,
  "chain_valid": true
}
```

---

## Document Endpoints

### POST /api/v1/documents

Upload a document.

**Request:** `multipart/form-data`
- `file` - The document file (PDF, DOCX, etc.)
- `entity_id` - Optional entity to associate
- `case_id` - Optional case to associate

**Response:**
```json
{
  "id": "uuid",
  "filename": "document.pdf",
  "content_type": "application/pdf",
  "size_bytes": 102400,
  "extracted_text": "...",
  "entities_found": ["uuid"],
  "created_at": "2025-01-15T10:30:00Z"
}
```

---

### GET /api/v1/documents/{document_id}

Get document metadata.

---

### GET /api/v1/documents/{document_id}/download

Download the original document.

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "field_errors": {
    "field_name": ["validation error"]
  }
}
```

### Common Error Codes

| Code | Status | Description |
|------|--------|-------------|
| `UNAUTHORIZED` | 401 | Invalid or missing authentication |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 422 | Request validation failed |
| `RATE_LIMITED` | 429 | Too many requests |
| `ACCOUNT_LOCKED` | 423 | Account temporarily locked |
| `RUBBER_STAMP_WARNING` | 400 | Review completed too quickly |

---

## Rate Limits

| Endpoint Category | Limit |
|-------------------|-------|
| Authentication | 10 requests/minute |
| Search | 100 requests/minute |
| Entity CRUD | 200 requests/minute |
| Document Upload | 20 requests/minute |

---

## Compliance Notes

### Audit Trail
All API requests are logged with:
- User identity
- Timestamp
- Action performed
- Resources accessed
- IP address
- Hash chain for tamper detection

### Human-in-Loop (Brottsdatalagen)
Tier 3 alerts affecting individuals require:
- Explicit human approval
- Documented justification
- Minimum review time (2 seconds)
- Cannot be batch-approved

### Data Minimization (GDPR)
- Personnummer is masked in responses (shows last 4 digits only)
- Full personnummer only shown when specifically requested
- Access to PII is logged and auditable
