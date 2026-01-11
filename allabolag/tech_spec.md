# Halo Technical Specification

## Implementation Handoff Document

Version: 1.0
Date: January 2026
Status: Ready for Implementation

---

## 1. Project Overview

**Product**: Halo (formerly Zion) - Swedish Organized Crime Intelligence Platform
**Scope**: MVP with entity resolution across Bolagsverket and Allabolag data sources
**Timeline**: 16 weeks to production-ready MVP

### 1.1 MVP Deliverables

1. Ingest all Swedish companies (including dissolved/liquidated) from Bolagsverket HVD
2. Ingest director and ownership data from Allabolag scraper
3. Resolve persons and companies across sources
4. Detect shell company network patterns
5. Generate alerts on high-risk new registrations
6. Provide API for entity lookup, graph traversal, and pattern matching
7. Basic analyst dashboard for review queue and pattern exploration

### 1.2 Out of Scope for MVP

- Aegis (housing security) integration
- Atlas (battlefield awareness) integration
- Kronofogden debt records
- Court records integration
- ML-based entity resolution (rule-based only for MVP)
- Mobile interface

---

## 2. Technology Stack

### 2.1 Infrastructure

| Component | Technology | Version | Hosting |
|-----------|------------|---------|---------|
| Primary Database | PostgreSQL | 16 | Scaleway |
| Graph Extension | Apache AGE | 1.5+ | Same instance |
| Spatial Extension | PostGIS | 3.4 | Same instance |
| Time Series | TimescaleDB | 2.13 | Same instance |
| Cache | Redis | 7.2 | Scaleway |
| Message Queue | Redis Streams | 7.2 | Same instance |
| Object Storage | Scaleway S3 | - | Scaleway |
| Secrets | Scaleway Secret Manager | - | Scaleway |

### 2.2 Application Stack

| Component | Technology | Version |
|-----------|------------|---------|
| API Framework | FastAPI | 0.109+ |
| Task Queue | Celery | 5.3+ |
| ORM | SQLAlchemy | 2.0+ |
| Migrations | Alembic | 1.13+ |
| Validation | Pydantic | 2.5+ |
| HTTP Client | httpx | 0.26+ |
| Testing | pytest | 8.0+ |

### 2.3 Development Environment

| Tool | Purpose |
|------|---------|
| Docker Compose | Local development |
| pre-commit | Code quality hooks |
| ruff | Linting + formatting |
| mypy | Type checking |
| pytest-cov | Coverage reporting |

---

## 3. Repository Structure

```
halo/
├── alembic/
│   ├── versions/
│   └── env.py
├── src/
│   └── halo/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app entry
│       ├── config.py                  # Settings from env
│       ├── database.py                # DB connection
│       │
│       ├── models/                    # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── entity.py
│       │   ├── fact.py
│       │   ├── mention.py
│       │   ├── provenance.py
│       │   └── audit.py
│       │
│       ├── schemas/                   # Pydantic schemas
│       │   ├── __init__.py
│       │   ├── entity.py
│       │   ├── fact.py
│       │   ├── resolution.py
│       │   └── pattern.py
│       │
│       ├── api/                       # API routes
│       │   ├── __init__.py
│       │   ├── entities.py
│       │   ├── relationships.py
│       │   ├── patterns.py
│       │   ├── resolution.py
│       │   └── health.py
│       │
│       ├── ingestion/                 # Data ingestion
│       │   ├── __init__.py
│       │   ├── bolagsverket.py
│       │   ├── allabolag.py
│       │   └── base.py
│       │
│       ├── resolution/                # Entity resolution
│       │   ├── __init__.py
│       │   ├── blocking.py
│       │   ├── comparison.py
│       │   ├── clustering.py
│       │   └── resolver.py
│       │
│       ├── patterns/                  # Pattern detection
│       │   ├── __init__.py
│       │   ├── shell_network.py
│       │   └── base.py
│       │
│       ├── derivation/                # Derived fact computation
│       │   ├── __init__.py
│       │   ├── risk_score.py
│       │   ├── velocity.py
│       │   └── scheduler.py
│       │
│       ├── swedish/                   # Swedish-specific utilities
│       │   ├── __init__.py
│       │   ├── personnummer.py
│       │   ├── company_name.py
│       │   └── address.py
│       │
│       └── utils/
│           ├── __init__.py
│           ├── audit.py
│           └── provenance.py
│
├── tests/
│   ├── conftest.py
│   ├── test_api/
│   ├── test_ingestion/
│   ├── test_resolution/
│   ├── test_patterns/
│   └── fixtures/
│
├── scripts/
│   ├── initial_load.py               # Full company load
│   ├── generate_synthetic.py         # Test data generation
│   └── measure_accuracy.py           # Validation metrics
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.dev.yml
│
├── .env.example
├── pyproject.toml
├── alembic.ini
└── README.md
```

---

## 4. Database Schema

### 4.1 Core Tables

Execute via Alembic migrations in order:

```sql
-- Migration 001: Core entity structure
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

CREATE TYPE entity_type AS ENUM ('PERSON', 'COMPANY', 'ADDRESS');
CREATE TYPE entity_status AS ENUM ('ACTIVE', 'MERGED', 'SPLIT', 'ANONYMIZED');
CREATE TYPE fact_type AS ENUM ('ATTRIBUTE', 'RELATIONSHIP');
CREATE TYPE source_type AS ENUM (
    'BOLAGSVERKET_HVD',
    'BOLAGSVERKET_ANNUAL_REPORT', 
    'ALLABOLAG_SCRAPE',
    'MANUAL_ENTRY',
    'DERIVED_COMPUTATION'
);
CREATE TYPE resolution_status AS ENUM (
    'PENDING', 'AUTO_MATCHED', 'HUMAN_MATCHED', 'AUTO_REJECTED', 'HUMAN_REJECTED'
);

-- Provenances (created first - referenced by others)
CREATE TABLE provenances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type source_type NOT NULL,
    source_id TEXT NOT NULL,
    source_url TEXT,
    source_document_hash TEXT,
    extraction_method TEXT NOT NULL,
    extraction_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extraction_system_version TEXT NOT NULL,
    derived_from UUID[],
    derivation_rule TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_prov_source ON provenances(source_type, source_id);
CREATE INDEX idx_prov_timestamp ON provenances(extraction_timestamp);

-- Entities
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type entity_type NOT NULL,
    canonical_name TEXT NOT NULL,
    resolution_confidence FLOAT NOT NULL DEFAULT 1.0 
        CHECK (resolution_confidence BETWEEN 0 AND 1),
    status entity_status NOT NULL DEFAULT 'ACTIVE',
    merged_into UUID REFERENCES entities(id),
    split_from UUID REFERENCES entities(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    anonymized_at TIMESTAMPTZ
);

CREATE INDEX idx_entity_type ON entities(entity_type) WHERE status = 'ACTIVE';
CREATE INDEX idx_entity_status ON entities(status);
CREATE INDEX idx_entity_merged ON entities(merged_into) WHERE merged_into IS NOT NULL;
CREATE INDEX idx_entity_name_trgm ON entities USING gin(canonical_name gin_trgm_ops);

-- Entity Identifiers
CREATE TABLE entity_identifiers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL CHECK (identifier_type IN (
        'PERSONNUMMER', 'SAMORDNINGSNUMMER', 'ORGANISATIONSNUMMER',
        'POSTAL_CODE', 'PROPERTY_ID'
    )),
    identifier_value TEXT NOT NULL,
    confidence FLOAT NOT NULL DEFAULT 1.0,
    provenance_id UUID NOT NULL REFERENCES provenances(id),
    valid_from DATE,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_id, identifier_type, identifier_value)
);

CREATE INDEX idx_ident_lookup ON entity_identifiers(identifier_type, identifier_value);
CREATE INDEX idx_ident_entity ON entity_identifiers(entity_id);

-- Facts
CREATE TABLE facts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fact_type fact_type NOT NULL,
    subject_id UUID NOT NULL REFERENCES entities(id),
    predicate TEXT NOT NULL CHECK (predicate IN (
        'DIRECTOR_OF', 'SHAREHOLDER_OF', 'REGISTERED_AT', 'SAME_AS',
        'RISK_SCORE', 'SHELL_INDICATOR', 'DIRECTOR_VELOCITY', 'NETWORK_CLUSTER'
    )),
    -- Value columns (use appropriate one based on predicate)
    value_text TEXT,
    value_int BIGINT,
    value_float FLOAT,
    value_date DATE,
    value_bool BOOLEAN,
    value_json JSONB,
    -- Relationship target
    object_id UUID REFERENCES entities(id),
    relationship_attributes JSONB,
    -- Temporality
    valid_from DATE NOT NULL,
    valid_to DATE,
    -- Confidence and provenance
    confidence FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    provenance_id UUID NOT NULL REFERENCES provenances(id),
    -- Lifecycle
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_by UUID REFERENCES facts(id),
    superseded_at TIMESTAMPTZ,
    -- Derivation
    is_derived BOOLEAN NOT NULL DEFAULT FALSE,
    derivation_rule TEXT,
    derived_from UUID[]
);

CREATE INDEX idx_fact_subject ON facts(subject_id, predicate) 
    WHERE superseded_by IS NULL;
CREATE INDEX idx_fact_object ON facts(object_id, predicate) 
    WHERE superseded_by IS NULL AND object_id IS NOT NULL;
CREATE INDEX idx_fact_temporal ON facts(valid_from, valid_to) 
    WHERE superseded_by IS NULL;
CREATE INDEX idx_fact_current ON facts(subject_id) 
    WHERE superseded_by IS NULL AND valid_to IS NULL;

-- Mentions
CREATE TABLE mentions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mention_type entity_type NOT NULL,
    surface_form TEXT NOT NULL,
    normalized_form TEXT NOT NULL,
    extracted_personnummer TEXT,
    extracted_orgnummer TEXT,
    extracted_attributes JSONB NOT NULL DEFAULT '{}',
    provenance_id UUID NOT NULL REFERENCES provenances(id),
    document_location TEXT,
    resolution_status resolution_status NOT NULL DEFAULT 'PENDING',
    resolved_to UUID REFERENCES entities(id),
    resolution_confidence FLOAT,
    resolution_method TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mention_pending ON mentions(mention_type) 
    WHERE resolution_status = 'PENDING';
CREATE INDEX idx_mention_resolved ON mentions(resolved_to) 
    WHERE resolved_to IS NOT NULL;
CREATE INDEX idx_mention_pnr ON mentions(extracted_personnummer) 
    WHERE extracted_personnummer IS NOT NULL;
CREATE INDEX idx_mention_org ON mentions(extracted_orgnummer) 
    WHERE extracted_orgnummer IS NOT NULL;

-- Resolution Decisions (for audit and accuracy measurement)
CREATE TABLE resolution_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    mention_id UUID NOT NULL REFERENCES mentions(id),
    candidate_entity_id UUID NOT NULL REFERENCES entities(id),
    overall_score FLOAT NOT NULL,
    feature_scores JSONB NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN (
        'AUTO_MATCH', 'AUTO_REJECT', 'HUMAN_MATCH', 'HUMAN_REJECT', 'PENDING_REVIEW'
    )),
    decision_reason TEXT,
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resdec_pending ON resolution_decisions(decision) 
    WHERE decision = 'PENDING_REVIEW';
CREATE INDEX idx_resdec_mention ON resolution_decisions(mention_id);
```

### 4.2 Attribute Tables

```sql
-- Migration 002: Entity attribute tables

-- Person attributes
CREATE TABLE person_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    birth_year INT,
    birth_date DATE,
    gender TEXT CHECK (gender IN ('M', 'F', NULL)),
    company_count INT NOT NULL DEFAULT 0,
    active_directorship_count INT NOT NULL DEFAULT 0,
    network_cluster_id UUID,
    risk_score FLOAT NOT NULL DEFAULT 0.0 CHECK (risk_score BETWEEN 0 AND 1),
    risk_factors TEXT[],
    first_seen DATE NOT NULL DEFAULT CURRENT_DATE,
    last_activity DATE NOT NULL DEFAULT CURRENT_DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_person_risk ON person_attributes(risk_score) WHERE risk_score > 0.5;
CREATE INDEX idx_person_cluster ON person_attributes(network_cluster_id) 
    WHERE network_cluster_id IS NOT NULL;

-- Company attributes
CREATE TABLE company_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    legal_form TEXT,
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    registration_date DATE,
    dissolution_date DATE,
    sni_codes TEXT[],
    sni_primary TEXT,
    latest_revenue BIGINT,
    latest_employees INT,
    latest_assets BIGINT,
    financial_year_end DATE,
    director_count INT NOT NULL DEFAULT 0,
    director_change_velocity FLOAT NOT NULL DEFAULT 0.0,
    network_cluster_id UUID,
    risk_score FLOAT NOT NULL DEFAULT 0.0 CHECK (risk_score BETWEEN 0 AND 1),
    risk_factors TEXT[],
    shell_indicators TEXT[],
    ownership_opacity_score FLOAT NOT NULL DEFAULT 0.0,
    last_filing_date DATE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_company_status ON company_attributes(status);
CREATE INDEX idx_company_sni ON company_attributes(sni_primary);
CREATE INDEX idx_company_risk ON company_attributes(risk_score) WHERE risk_score > 0.5;
CREATE INDEX idx_company_shell ON company_attributes(entity_id) 
    WHERE array_length(shell_indicators, 1) > 0;

-- Address attributes
CREATE TABLE address_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    street TEXT NOT NULL,
    street_number TEXT,
    postal_code TEXT NOT NULL,
    city TEXT NOT NULL,
    municipality TEXT,
    coordinates GEOGRAPHY(POINT, 4326),
    geocode_confidence FLOAT,
    vulnerable_area BOOLEAN NOT NULL DEFAULT FALSE,
    vulnerability_level TEXT,
    company_count INT NOT NULL DEFAULT 0,
    person_count INT NOT NULL DEFAULT 0,
    is_registration_hub BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_address_postal ON address_attributes(postal_code);
CREATE INDEX idx_address_geo ON address_attributes USING GIST(coordinates);
CREATE INDEX idx_address_vulnerable ON address_attributes(vulnerable_area) 
    WHERE vulnerable_area = TRUE;
CREATE INDEX idx_address_hub ON address_attributes(is_registration_hub) 
    WHERE is_registration_hub = TRUE;
```

### 4.3 Audit Tables

```sql
-- Migration 003: Audit logging (separate schema for isolation)

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE audit.log (
    id BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('SYSTEM', 'USER', 'API')),
    actor_id TEXT,
    target_type TEXT,
    target_id UUID,
    event_data JSONB NOT NULL,
    request_id UUID,
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX idx_audit_timestamp ON audit.log(event_timestamp);
CREATE INDEX idx_audit_target ON audit.log(target_type, target_id);
CREATE INDEX idx_audit_actor ON audit.log(actor_type, actor_id);
CREATE INDEX idx_audit_type ON audit.log(event_type);

-- Erasure request log (longer retention)
CREATE TABLE audit.erasure_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL,
    request_reference TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processor_id TEXT NOT NULL
);

-- Validation ground truth
CREATE TABLE audit.validation_ground_truth (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ground_truth_type TEXT NOT NULL CHECK (ground_truth_type IN (
        'PERSONNUMMER_MATCH', 'ORGNUMMER_MATCH', 'SYNTHETIC', 'EKOBROTTSMYNDIGHETEN'
    )),
    entity_a_id UUID,
    entity_b_id UUID,
    mention_a_id UUID,
    mention_b_id UUID,
    is_same_entity BOOLEAN NOT NULL,
    source_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 4.4 Configuration Tables

```sql
-- Migration 004: Configuration

CREATE TABLE resolution_config (
    mention_type entity_type PRIMARY KEY,
    auto_match_threshold FLOAT NOT NULL,
    human_review_min FLOAT NOT NULL,
    auto_reject_threshold FLOAT NOT NULL
);

INSERT INTO resolution_config VALUES
    ('PERSON', 0.95, 0.60, 0.60),
    ('COMPANY', 0.95, 0.60, 0.60),
    ('ADDRESS', 0.90, 0.50, 0.50);

CREATE TABLE source_authority (
    source_type source_type NOT NULL,
    predicate TEXT NOT NULL,
    authority_level INT NOT NULL,
    PRIMARY KEY (source_type, predicate)
);

INSERT INTO source_authority VALUES
    ('BOLAGSVERKET_HVD', 'DIRECTOR_OF', 1),
    ('BOLAGSVERKET_HVD', 'REGISTERED_AT', 1),
    ('BOLAGSVERKET_HVD', 'SHAREHOLDER_OF', 2),
    ('BOLAGSVERKET_ANNUAL_REPORT', 'SHAREHOLDER_OF', 1),
    ('ALLABOLAG_SCRAPE', 'DIRECTOR_OF', 2),
    ('ALLABOLAG_SCRAPE', 'SHAREHOLDER_OF', 3);

CREATE TABLE derivation_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_name TEXT NOT NULL UNIQUE,
    rule_type TEXT NOT NULL,
    rule_definition JSONB NOT NULL,
    version INT NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Alerts
CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_type TEXT NOT NULL,
    entity_id UUID REFERENCES entities(id),
    risk_score FLOAT,
    alert_data JSONB,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_unack ON alerts(alert_type, created_at) 
    WHERE acknowledged = FALSE;
```

---

## 5. API Specification

### 5.1 Entity Endpoints

```python
# src/halo/api/entities.py

from fastapi import APIRouter, HTTPException, Depends
from uuid import UUID
from typing import Optional

router = APIRouter(prefix="/entities", tags=["entities"])

@router.get("/{entity_id}", response_model=EntityResponse)
async def get_entity(
    entity_id: UUID,
    include_facts: bool = False,
    include_same_as: bool = True,
    db: Session = Depends(get_db)
) -> EntityResponse:
    """
    Get entity by ID.
    Performance target: <100ms
    """
    pass

@router.get("/{entity_id}/relationships", response_model=GraphResponse)
async def get_relationships(
    entity_id: UUID,
    depth: int = 2,
    predicates: Optional[list[str]] = None,
    max_nodes: int = 100,
    db: Session = Depends(get_db)
) -> GraphResponse:
    """
    Get relationship graph from entity.
    Performance target: <1s for depth=2
    """
    pass

@router.get("/search", response_model=SearchResponse)
async def search_entities(
    q: str,
    entity_type: Optional[EntityType] = None,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> SearchResponse:
    """
    Search entities by name or identifier.
    """
    pass

@router.get("/by-identifier", response_model=EntityResponse)
async def get_by_identifier(
    identifier_type: str,
    identifier_value: str,
    db: Session = Depends(get_db)
) -> EntityResponse:
    """
    Lookup entity by identifier (personnummer, orgnummer).
    Performance target: <100ms
    """
    pass
```

### 5.2 Pattern Endpoints

```python
# src/halo/api/patterns.py

router = APIRouter(prefix="/patterns", tags=["patterns"])

@router.post("/shell-network", response_model=PatternMatchResponse)
async def detect_shell_networks(
    params: ShellNetworkParams,
    db: Session = Depends(get_db)
) -> PatternMatchResponse:
    """
    Detect shell company network patterns.
    Performance target: <10s
    
    Parameters:
    - min_companies: Minimum companies per person (default: 3)
    - max_employees: Maximum employees per company (default: 2)
    - max_revenue: Maximum revenue per company (default: 500000)
    """
    pass

@router.get("/alerts", response_model=AlertListResponse)
async def get_alerts(
    alert_type: Optional[str] = None,
    acknowledged: Optional[bool] = False,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> AlertListResponse:
    """
    Get pending alerts.
    """
    pass

@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: UUID,
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    Acknowledge an alert.
    """
    pass
```

### 5.3 Resolution Endpoints

```python
# src/halo/api/resolution.py

router = APIRouter(prefix="/resolution", tags=["resolution"])

@router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    mention_type: Optional[EntityType] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
) -> ReviewQueueResponse:
    """
    Get mentions pending human review.
    """
    pass

@router.post("/decide", response_model=ResolutionDecisionResponse)
async def submit_decision(
    decision: ResolutionDecisionRequest,
    reviewer_id: str,
    db: Session = Depends(get_db)
) -> ResolutionDecisionResponse:
    """
    Submit human review decision.
    """
    pass

@router.get("/accuracy", response_model=AccuracyMetrics)
async def get_accuracy_metrics(
    db: Session = Depends(get_db)
) -> AccuracyMetrics:
    """
    Get current resolution accuracy metrics against ground truth.
    """
    pass
```

### 5.4 Response Schemas

```python
# src/halo/schemas/entity.py

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime, date
from typing import Optional

class EntityIdentifier(BaseModel):
    identifier_type: str
    identifier_value: str
    confidence: float

class EntityResponse(BaseModel):
    id: UUID
    entity_type: str
    canonical_name: str
    status: str
    resolution_confidence: float
    identifiers: list[EntityIdentifier]
    attributes: dict
    same_as: list[UUID]
    created_at: datetime
    updated_at: datetime

class GraphNode(BaseModel):
    id: UUID
    entity_type: str
    canonical_name: str
    risk_score: Optional[float]

class GraphEdge(BaseModel):
    source: UUID
    target: UUID
    predicate: str
    valid_from: date
    valid_to: Optional[date]

class GraphResponse(BaseModel):
    root: UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    total_nodes: int

class PatternMatch(BaseModel):
    person_id: UUID
    person_name: str
    companies: list[UUID]
    company_names: list[str]
    risk_score: float
    indicators: list[str]

class PatternMatchResponse(BaseModel):
    matches: list[PatternMatch]
    execution_time_ms: int
    total_matches: int
```

---

## 6. Ingestion Pipeline

### 6.1 Bolagsverket HVD

```python
# src/halo/ingestion/bolagsverket.py

from dataclasses import dataclass
from typing import Iterator
import httpx

@dataclass
class BolagsverketConfig:
    base_url: str = "https://data.bolagsverket.se/v3"
    api_key: str = ""
    batch_size: int = 1000
    
class BolagsverketIngester:
    """
    Ingest companies from Bolagsverket HVD API.
    
    Data flow:
    1. Fetch company list from SCB (enumeration)
    2. For each company, fetch details from Bolagsverket HVD
    3. Extract directors from iXBRL annual reports
    4. Create mentions for companies and persons
    5. Queue for resolution
    """
    
    async def ingest_all_companies(self, include_dissolved: bool = True):
        """
        Full load of all Swedish companies.
        Expected: ~1.2M companies (including dissolved)
        """
        pass
    
    async def ingest_company(self, orgnummer: str) -> CompanyMention:
        """
        Ingest single company and its directors.
        """
        pass
    
    async def extract_directors_from_ixbrl(
        self, 
        document_bytes: bytes
    ) -> list[PersonMention]:
        """
        Extract director information from iXBRL annual report.
        Uses existing pipeline achieving 68% document coverage.
        """
        pass
    
    def create_provenance(self, source_id: str, method: str) -> Provenance:
        """
        Create provenance record for Bolagsverket data.
        """
        return Provenance(
            source_type=SourceType.BOLAGSVERKET_HVD,
            source_id=source_id,
            extraction_method=method,
            extraction_timestamp=datetime.utcnow(),
            extraction_system_version=settings.VERSION
        )
```

### 6.2 Allabolag Scraper

```python
# src/halo/ingestion/allabolag.py

@dataclass
class AllabolagConfig:
    base_url: str = "https://www.allabolag.se"
    requests_per_day: int = 150
    business_hours_only: bool = True
    residential_proxy: str = ""

class AllabolagIngester:
    """
    Scrape director and ownership data from Allabolag.
    
    Rate limiting:
    - 150 requests/day maximum
    - Business hours only (08:00-18:00 CET)
    - Human-like delays (30-120 seconds between requests)
    - Residential IP addresses
    
    Expected timeline: ~10 months for full coverage
    """
    
    async def scrape_company_page(self, orgnummer: str) -> CompanyData:
        """
        Phase 1: Scrape company page for basic info.
        """
        pass
    
    async def scrape_person_page(self, person_url: str) -> PersonData:
        """
        Phase 2: Scrape person page for full birth date and relationships.
        """
        pass
    
    def create_provenance(self, url: str) -> Provenance:
        return Provenance(
            source_type=SourceType.ALLABOLAG_SCRAPE,
            source_id=url,
            source_url=url,
            extraction_method="allabolag_scraper_v1",
            extraction_timestamp=datetime.utcnow(),
            extraction_system_version=settings.VERSION
        )
```

### 6.3 Ingestion Orchestration

```python
# src/halo/ingestion/orchestrator.py

class IngestionOrchestrator:
    """
    Coordinate ingestion from multiple sources.
    """
    
    async def run_initial_load(self):
        """
        Full initial load sequence:
        1. Load all companies from Bolagsverket
        2. Create company entities
        3. Extract and queue person mentions
        4. Run entity resolution
        5. Build initial relationship graph
        """
        
        # Step 1: Companies
        logger.info("Starting company ingestion")
        async for batch in self.bolagsverket.ingest_all_companies():
            await self.process_company_batch(batch)
            
        # Step 2: Resolution
        logger.info("Running entity resolution")
        await self.resolver.resolve_all_pending()
        
        # Step 3: Derived facts
        logger.info("Computing derived facts")
        await self.derivation.compute_all()
        
        logger.info("Initial load complete")
    
    async def run_incremental_update(self):
        """
        Daily incremental update:
        1. Fetch changed companies (last 24h)
        2. Update entities and facts
        3. Resolve new mentions
        4. Recompute affected derived facts
        5. Generate alerts for high-risk changes
        """
        pass
```

---

## 7. Entity Resolution

### 7.1 Resolution Pipeline

```python
# src/halo/resolution/resolver.py

class EntityResolver:
    """
    Main resolution pipeline.
    
    Flow:
    1. Blocking: Group mentions by blocking keys
    2. Comparison: Score candidate pairs
    3. Decision: Auto-match, auto-reject, or queue for review
    4. Clustering: Group matched mentions
    5. Merge: Create/update entities
    """
    
    def __init__(self, config: ResolutionConfig):
        self.blocker = BlockingIndex(config)
        self.comparator = FeatureComparator(config)
        self.config = config
    
    async def resolve_mention(self, mention: Mention) -> ResolutionResult:
        """
        Resolve single mention.
        """
        # 1. Get candidates via blocking
        candidates = await self.blocker.get_candidates(mention)
        
        if not candidates:
            # No candidates - create new entity
            return await self.create_new_entity(mention)
        
        # 2. Score each candidate
        scored = []
        for candidate in candidates:
            features = self.comparator.compute_features(mention, candidate)
            score = self.score_features(features)
            scored.append((candidate, score, features))
        
        # 3. Get best match
        best_candidate, best_score, best_features = max(scored, key=lambda x: x[1])
        
        # 4. Decide
        threshold = self.config.get_threshold(mention.mention_type)
        
        if best_score >= threshold.auto_match:
            return await self.auto_match(mention, best_candidate, best_score, best_features)
        elif best_score >= threshold.human_review_min:
            return await self.queue_for_review(mention, scored)
        else:
            return await self.create_new_entity(mention)
    
    async def resolve_all_pending(self, batch_size: int = 1000):
        """
        Process all pending mentions.
        """
        while True:
            mentions = await self.get_pending_mentions(batch_size)
            if not mentions:
                break
            
            for mention in mentions:
                try:
                    result = await self.resolve_mention(mention)
                    await self.log_resolution(mention, result)
                except Exception as e:
                    logger.error(f"Resolution failed for {mention.id}: {e}")
                    await self.mark_failed(mention, str(e))
```

### 7.2 Blocking

```python
# src/halo/resolution/blocking.py

class BlockingIndex:
    """
    Blocking index for candidate generation.
    """
    
    def __init__(self, config: ResolutionConfig):
        self.config = config
    
    async def get_candidates(self, mention: Mention) -> list[Entity]:
        """
        Get candidate entities for a mention.
        Uses multiple blocking strategies.
        """
        candidates = set()
        
        # Strategy 1: Exact identifier match
        if mention.extracted_personnummer:
            exact = await self.lookup_by_identifier(
                'PERSONNUMMER', 
                mention.extracted_personnummer
            )
            if exact:
                candidates.add(exact)
                return list(candidates)  # Exact match - no need for more
        
        if mention.extracted_orgnummer:
            exact = await self.lookup_by_identifier(
                'ORGANISATIONSNUMMER',
                mention.extracted_orgnummer
            )
            if exact:
                candidates.add(exact)
                return list(candidates)
        
        # Strategy 2: Phonetic name blocking
        phonetic = self.get_phonetic_key(mention.normalized_form)
        phonetic_matches = await self.lookup_by_phonetic(
            mention.mention_type,
            phonetic
        )
        candidates.update(phonetic_matches)
        
        # Strategy 3: Name prefix + birth year (persons only)
        if mention.mention_type == EntityType.PERSON:
            birth_year = mention.extracted_attributes.get('birth_year')
            if birth_year:
                prefix_key = f"{mention.normalized_form[:4]}_{birth_year}"
                prefix_matches = await self.lookup_by_prefix_year(prefix_key)
                candidates.update(prefix_matches)
        
        # Strategy 4: Address cluster (for addresses)
        if mention.mention_type == EntityType.ADDRESS:
            postal_prefix = mention.extracted_attributes.get('postal_code', '')[:3]
            address_matches = await self.lookup_by_postal_prefix(postal_prefix)
            candidates.update(address_matches)
        
        return list(candidates)
    
    def get_phonetic_key(self, name: str) -> str:
        """
        Generate phonetic key using Double Metaphone.
        """
        import metaphone
        primary, secondary = metaphone.doublemetaphone(name)
        return primary or secondary or name[:4].upper()
```

### 7.3 Feature Comparison

```python
# src/halo/resolution/comparison.py

from dataclasses import dataclass
import jellyfish

@dataclass
class FeatureScores:
    identifier_match: float = 0.0
    name_jaro_winkler: float = 0.0
    name_token_jaccard: float = 0.0
    birth_year_match: float = 0.0
    address_similarity: float = 0.0
    network_overlap: float = 0.0

class FeatureComparator:
    """
    Compute pairwise features for resolution.
    """
    
    # Weights for MVP (rule-based, no ML)
    PERSON_WEIGHTS = {
        'identifier_match': 10.0,      # Definitive
        'name_jaro_winkler': 2.0,
        'name_token_jaccard': 1.5,
        'birth_year_match': 1.5,
        'address_similarity': 1.0,
        'network_overlap': 2.5,        # Strong signal
    }
    
    COMPANY_WEIGHTS = {
        'identifier_match': 10.0,
        'name_jaro_winkler': 3.0,
        'address_similarity': 1.5,
        'director_overlap': 2.0,
    }
    
    def compute_features(
        self, 
        mention: Mention, 
        entity: Entity
    ) -> FeatureScores:
        """
        Compute all comparison features.
        """
        if mention.mention_type == EntityType.PERSON:
            return self.compute_person_features(mention, entity)
        elif mention.mention_type == EntityType.COMPANY:
            return self.compute_company_features(mention, entity)
        else:
            return self.compute_address_features(mention, entity)
    
    def compute_person_features(
        self, 
        mention: Mention, 
        entity: Entity
    ) -> FeatureScores:
        scores = FeatureScores()
        
        # Identifier match
        if mention.extracted_personnummer:
            entity_pnr = self.get_entity_identifier(entity, 'PERSONNUMMER')
            if entity_pnr == mention.extracted_personnummer:
                scores.identifier_match = 1.0
        
        # Name similarity
        scores.name_jaro_winkler = jellyfish.jaro_winkler_similarity(
            mention.normalized_form,
            entity.canonical_name
        )
        
        # Token overlap
        mention_tokens = set(mention.normalized_form.lower().split())
        entity_tokens = set(entity.canonical_name.lower().split())
        if mention_tokens and entity_tokens:
            scores.name_token_jaccard = len(mention_tokens & entity_tokens) / len(mention_tokens | entity_tokens)
        
        # Birth year
        mention_year = mention.extracted_attributes.get('birth_year')
        entity_year = self.get_person_birth_year(entity)
        if mention_year and entity_year:
            scores.birth_year_match = 1.0 if mention_year == entity_year else 0.0
        
        # Network overlap (shared companies)
        scores.network_overlap = self.compute_network_overlap(mention, entity)
        
        return scores
    
    def score_features(self, features: FeatureScores, entity_type: EntityType) -> float:
        """
        Compute weighted score from features.
        """
        weights = self.PERSON_WEIGHTS if entity_type == EntityType.PERSON else self.COMPANY_WEIGHTS
        
        # Definitive identifier match
        if features.identifier_match == 1.0:
            return 0.99
        
        total = 0.0
        max_possible = 0.0
        
        for feature_name, weight in weights.items():
            value = getattr(features, feature_name, 0.0)
            total += value * weight
            max_possible += weight
        
        return total / max_possible if max_possible > 0 else 0.0
```

---

## 8. Pattern Detection

### 8.1 Shell Network Detection

```python
# src/halo/patterns/shell_network.py

@dataclass
class ShellNetworkParams:
    min_companies: int = 3
    max_employees: int = 2
    max_revenue: int = 500000
    include_dissolved: bool = False

@dataclass  
class ShellNetworkMatch:
    person_id: UUID
    person_name: str
    companies: list[UUID]
    company_names: list[str]
    risk_score: float
    indicators: list[str]

class ShellNetworkDetector:
    """
    Detect shell company network patterns.
    """
    
    async def detect(
        self, 
        params: ShellNetworkParams,
        db: Session
    ) -> list[ShellNetworkMatch]:
        """
        Find persons directing multiple shell-like companies.
        
        SQL query with Apache AGE for graph traversal.
        """
        query = """
        WITH director_companies AS (
            SELECT 
                f.subject_id as person_id,
                e_person.canonical_name as person_name,
                f.object_id as company_id,
                e_company.canonical_name as company_name,
                ca.status,
                ca.latest_employees,
                ca.latest_revenue,
                ca.shell_indicators
            FROM facts f
            JOIN entities e_person ON e_person.id = f.subject_id
            JOIN entities e_company ON e_company.id = f.object_id
            JOIN company_attributes ca ON ca.entity_id = f.object_id
            WHERE f.predicate = 'DIRECTOR_OF'
            AND f.valid_to IS NULL
            AND f.superseded_by IS NULL
            AND e_person.status = 'ACTIVE'
            AND e_company.status = 'ACTIVE'
            AND (:include_dissolved OR ca.status = 'ACTIVE')
            AND (ca.latest_employees IS NULL OR ca.latest_employees <= :max_employees)
            AND (ca.latest_revenue IS NULL OR ca.latest_revenue <= :max_revenue)
        ),
        person_shells AS (
            SELECT 
                person_id,
                person_name,
                array_agg(company_id) as company_ids,
                array_agg(company_name) as company_names,
                array_agg(DISTINCT unnest(shell_indicators)) as all_indicators
            FROM director_companies
            GROUP BY person_id, person_name
            HAVING count(*) >= :min_companies
        )
        SELECT 
            ps.*,
            pa.risk_score
        FROM person_shells ps
        LEFT JOIN person_attributes pa ON pa.entity_id = ps.person_id
        ORDER BY array_length(ps.company_ids, 1) DESC, pa.risk_score DESC
        """
        
        results = await db.execute(
            text(query),
            {
                'min_companies': params.min_companies,
                'max_employees': params.max_employees,
                'max_revenue': params.max_revenue,
                'include_dissolved': params.include_dissolved
            }
        )
        
        return [
            ShellNetworkMatch(
                person_id=row.person_id,
                person_name=row.person_name,
                companies=row.company_ids,
                company_names=row.company_names,
                risk_score=row.risk_score or 0.0,
                indicators=row.all_indicators or []
            )
            for row in results
        ]
```

### 8.2 Real-Time Alerting

```python
# src/halo/patterns/alerting.py

class AlertGenerator:
    """
    Generate alerts on high-risk patterns.
    """
    
    async def check_new_company(self, company_id: UUID, db: Session):
        """
        Check newly ingested company for risk indicators.
        Called from ingestion pipeline.
        """
        # Get company and its directors
        company = await self.get_company_with_directors(company_id, db)
        
        risk_signals = []
        
        # Check 1: Director with high risk score
        high_risk_directors = [
            d for d in company.directors 
            if d.risk_score and d.risk_score > 0.7
        ]
        if high_risk_directors:
            risk_signals.append(f"director_risk:{max(d.risk_score for d in high_risk_directors):.2f}")
        
        # Check 2: Registered in vulnerable area
        if company.address and company.address.vulnerable_area:
            risk_signals.append(f"vulnerable_area:{company.address.vulnerability_level}")
        
        # Check 3: Registration hub address
        if company.address and company.address.is_registration_hub:
            risk_signals.append("registration_hub")
        
        # Check 4: Healthcare SNI in vulnerable area
        if company.sni_primary and company.sni_primary[:2] in ('86', '87', '88'):
            if company.address and company.address.vulnerable_area:
                risk_signals.append("healthcare_vulnerable_area")
        
        # Generate alert if sufficient risk
        if len(risk_signals) >= 2 or 'healthcare_vulnerable_area' in risk_signals:
            await self.create_alert(
                alert_type='HIGH_RISK_REGISTRATION',
                entity_id=company_id,
                risk_score=self.compute_alert_risk(risk_signals),
                alert_data={'signals': risk_signals}
            )
```

---

## 9. Derived Fact Computation

### 9.1 Nightly Job

```python
# src/halo/derivation/scheduler.py

from celery import Celery
from celery.schedules import crontab

app = Celery('halo')

@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Run derivation at 02:00 UTC daily
    sender.add_periodic_task(
        crontab(hour=2, minute=0),
        run_nightly_derivation.s(),
        name='nightly-derivation'
    )

@app.task(bind=True, max_retries=3)
def run_nightly_derivation(self):
    """
    Nightly derivation job.
    Target: <4 hours for full graph.
    """
    try:
        asyncio.run(_run_derivation())
    except Exception as e:
        logger.error(f"Derivation failed: {e}")
        self.retry(countdown=600)  # Retry in 10 minutes

async def _run_derivation():
    job_start = datetime.utcnow()
    
    async with get_db_session() as db:
        # 1. Risk scores
        await compute_person_risk_scores(db)
        await compute_company_risk_scores(db)
        
        # 2. Director velocity
        await compute_director_velocity(db)
        
        # 3. Address statistics
        await compute_address_statistics(db)
        
        # 4. Shell indicators
        await compute_shell_indicators(db)
        
        # 5. Network clusters (most expensive)
        await compute_network_clusters(db)
    
    job_duration = datetime.utcnow() - job_start
    
    await log_audit_event('DERIVATION_JOB_COMPLETE', {
        'duration_seconds': job_duration.total_seconds(),
        'status': 'success'
    })
```

### 9.2 Risk Score Computation

```python
# src/halo/derivation/risk_score.py

class RiskScoreComputer:
    """
    Compute risk scores for persons and companies.
    """
    
    PERSON_RISK_FACTORS = {
        'many_directorships': (0.2, lambda p: p.active_directorship_count > 5),
        'shell_company_director': (0.3, lambda p: p.shell_company_count > 0),
        'high_velocity_network': (0.2, lambda p: p.avg_company_velocity > 2.0),
        'vulnerable_area_companies': (0.15, lambda p: p.vulnerable_area_company_count > 0),
        'dissolved_company_history': (0.1, lambda p: p.dissolved_company_count > 3),
        'young_director': (0.05, lambda p: p.birth_year and (2026 - p.birth_year) < 25),
    }
    
    async def compute_person_risk_scores(self, db: Session):
        """
        Batch compute risk scores for all active persons.
        """
        query = """
        WITH person_stats AS (
            SELECT 
                pa.entity_id,
                pa.active_directorship_count,
                pa.birth_year,
                -- Count shell companies
                (
                    SELECT count(*) 
                    FROM facts f
                    JOIN company_attributes ca ON ca.entity_id = f.object_id
                    WHERE f.subject_id = pa.entity_id
                    AND f.predicate = 'DIRECTOR_OF'
                    AND f.superseded_by IS NULL
                    AND array_length(ca.shell_indicators, 1) > 0
                ) as shell_company_count,
                -- Count companies in vulnerable areas
                (
                    SELECT count(*)
                    FROM facts f
                    JOIN facts f2 ON f2.subject_id = f.object_id
                    JOIN address_attributes aa ON aa.entity_id = f2.object_id
                    WHERE f.subject_id = pa.entity_id
                    AND f.predicate = 'DIRECTOR_OF'
                    AND f2.predicate = 'REGISTERED_AT'
                    AND f.superseded_by IS NULL
                    AND f2.superseded_by IS NULL
                    AND aa.vulnerable_area = true
                ) as vulnerable_area_company_count,
                -- Count dissolved companies
                (
                    SELECT count(*)
                    FROM facts f
                    JOIN company_attributes ca ON ca.entity_id = f.object_id
                    WHERE f.subject_id = pa.entity_id
                    AND f.predicate = 'DIRECTOR_OF'
                    AND ca.status = 'DISSOLVED'
                ) as dissolved_company_count,
                -- Avg director velocity of their companies
                (
                    SELECT avg(ca.director_change_velocity)
                    FROM facts f
                    JOIN company_attributes ca ON ca.entity_id = f.object_id
                    WHERE f.subject_id = pa.entity_id
                    AND f.predicate = 'DIRECTOR_OF'
                    AND f.superseded_by IS NULL
                ) as avg_company_velocity
            FROM person_attributes pa
            JOIN entities e ON e.id = pa.entity_id
            WHERE e.status = 'ACTIVE'
        )
        SELECT 
            entity_id,
            active_directorship_count,
            shell_company_count,
            vulnerable_area_company_count,
            dissolved_company_count,
            avg_company_velocity,
            birth_year
        FROM person_stats
        """
        
        results = await db.execute(text(query))
        
        for row in results:
            risk_score, risk_factors = self.compute_person_risk(row)
            
            await db.execute(
                text("""
                    UPDATE person_attributes 
                    SET risk_score = :score, risk_factors = :factors, updated_at = NOW()
                    WHERE entity_id = :entity_id
                """),
                {'entity_id': row.entity_id, 'score': risk_score, 'factors': risk_factors}
            )
            
            # Store as derived fact
            await self.store_derived_fact(
                db,
                entity_id=row.entity_id,
                predicate='RISK_SCORE',
                value=risk_score,
                rule_name='person_risk_v1',
                metadata={'factors': risk_factors}
            )
        
        await db.commit()
```

---

## 10. Swedish Data Utilities

### 10.1 Personnummer

```python
# src/halo/swedish/personnummer.py

import re
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import date

@dataclass
class PersonnummerResult:
    valid: bool
    normalized: Optional[str]  # 12-digit format
    birth_date: Optional[date]
    gender: Optional[str]
    is_samordningsnummer: bool
    error: Optional[str]

def validate_personnummer(pnr: str) -> PersonnummerResult:
    """
    Validate and parse Swedish personnummer.
    
    Accepts formats:
    - YYYYMMDD-XXXX (12 digits with dash)
    - YYYYMMDDXXXX (12 digits)
    - YYMMDD-XXXX (10 digits with dash)
    - YYMMDDXXXX (10 digits)
    
    Also handles samordningsnummer (day + 60).
    """
    # Normalize
    clean = re.sub(r'[-\s]', '', pnr)
    
    # Handle 10-digit format
    if len(clean) == 10:
        # Determine century
        year = int(clean[0:2])
        current_year = date.today().year % 100
        
        if year > current_year:
            century = '19'
        else:
            century = '20'
        
        clean = century + clean
    
    if len(clean) != 12:
        return PersonnummerResult(
            valid=False, normalized=None, birth_date=None,
            gender=None, is_samordningsnummer=False,
            error="Invalid length"
        )
    
    # Parse components
    try:
        year = int(clean[0:4])
        month = int(clean[4:6])
        day = int(clean[6:8])
        serial = clean[8:11]
        checksum = int(clean[11])
    except ValueError:
        return PersonnummerResult(
            valid=False, normalized=None, birth_date=None,
            gender=None, is_samordningsnummer=False,
            error="Non-numeric characters"
        )
    
    # Check for samordningsnummer
    is_samordning = day > 60
    actual_day = day - 60 if is_samordning else day
    
    # Validate date
    try:
        birth_date = date(year, month, actual_day)
    except ValueError:
        return PersonnummerResult(
            valid=False, normalized=None, birth_date=None,
            gender=None, is_samordningsnummer=is_samordning,
            error="Invalid date"
        )
    
    # Luhn checksum (on 10-digit portion)
    check_digits = clean[2:11]
    weights = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    
    total = 0
    for digit, weight in zip(check_digits, weights):
        product = int(digit) * weight
        total += product // 10 + product % 10
    
    expected_checksum = (10 - (total % 10)) % 10
    
    if checksum != expected_checksum:
        return PersonnummerResult(
            valid=False, normalized=clean, birth_date=birth_date,
            gender=None, is_samordningsnummer=is_samordning,
            error="Invalid checksum"
        )
    
    # Determine gender (odd = male, even = female)
    gender = 'M' if int(serial[2]) % 2 == 1 else 'F'
    
    return PersonnummerResult(
        valid=True,
        normalized=clean,
        birth_date=birth_date,
        gender=gender,
        is_samordningsnummer=is_samordning,
        error=None
    )

def extract_birth_year(pnr: str) -> Optional[int]:
    """
    Extract birth year from personnummer.
    Returns None if invalid.
    """
    result = validate_personnummer(pnr)
    return result.birth_date.year if result.valid and result.birth_date else None
```

### 10.2 Company Name Normalization

```python
# src/halo/swedish/company_name.py

import re
from typing import Tuple

# Legal form patterns
LEGAL_FORMS = {
    r'\bAKTIEBOLAG\b': 'AB',
    r'\bAKTIEBOLAGET\b': 'AB',
    r'\bHANDELSBOLAG\b': 'HB',
    r'\bHANDELSBOLAGET\b': 'HB',
    r'\bKOMMANDITBOLAG\b': 'KB',
    r'\bKOMMANDITBOLAGET\b': 'KB',
    r'\bENSKILD\s*FIRMA\b': 'EF',
    r'\bEKONOMISK\s*FÖRENING\b': 'EK FÖR',
    r'\bIDEELL\s*FÖRENING\b': 'IDEELL FÖR',
    r'\bSTIFTELSE\b': 'STIFTELSE',
}

# Status indicators to remove for matching
STATUS_INDICATORS = [
    r'\bI\s*LIKVIDATION\b',
    r'\bI\s*KONKURS\b',
    r'\bUNDER\s*REKONSTRUKTION\b',
    r'\bUNDER\s*AVVECKLING\b',
    r'\(PUBL\)',
    r'\bPUBL\b',
]

def normalize_company_name(name: str) -> Tuple[str, str]:
    """
    Normalize Swedish company name for matching.
    
    Returns: (normalized_name, detected_legal_form)
    """
    normalized = name.upper().strip()
    legal_form = None
    
    # Detect and normalize legal form
    for pattern, form in LEGAL_FORMS.items():
        if re.search(pattern, normalized):
            legal_form = form
            normalized = re.sub(pattern, '', normalized)
            break
    
    # Remove trailing "AB" etc if at end
    normalized = re.sub(r'\s+(AB|HB|KB|EF)\s*$', '', normalized)
    
    # Remove status indicators
    for pattern in STATUS_INDICATORS:
        normalized = re.sub(pattern, '', normalized)
    
    # Remove punctuation except &
    normalized = re.sub(r'[^\w\s&]', ' ', normalized)
    
    # Normalize whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized, legal_form

def company_name_similarity(name1: str, name2: str) -> float:
    """
    Compute similarity between two company names.
    Handles common variations.
    """
    norm1, form1 = normalize_company_name(name1)
    norm2, form2 = normalize_company_name(name2)
    
    # Exact normalized match
    if norm1 == norm2:
        return 1.0
    
    # Jaro-Winkler on normalized names
    import jellyfish
    jw_score = jellyfish.jaro_winkler_similarity(norm1, norm2)
    
    # Token overlap
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())
    
    if tokens1 and tokens2:
        jaccard = len(tokens1 & tokens2) / len(tokens1 | tokens2)
    else:
        jaccard = 0.0
    
    # Combined score
    return 0.6 * jw_score + 0.4 * jaccard
```

### 10.3 Address Normalization

```python
# src/halo/swedish/address.py

import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedAddress:
    street: str
    street_number: Optional[str]
    entrance: Optional[str]  # A, B, C etc
    floor: Optional[str]
    apartment: Optional[str]
    postal_code: str
    city: str
    normalized: str

# Street type normalization
STREET_TYPES = {
    'GATAN': 'G',
    'VÄGEN': 'V', 
    'ALLÉN': 'A',
    'STIGEN': 'ST',
    'GRÄND': 'GR',
    'PLAN': 'PL',
    'TORG': 'T',
    'BACKE': 'B',
    'PLATS': 'PL',
}

def parse_swedish_address(address: str) -> ParsedAddress:
    """
    Parse Swedish address into components.
    """
    # Normalize
    addr = address.upper().strip()
    
    # Extract postal code (5 digits, optional space)
    postal_match = re.search(r'(\d{3})\s?(\d{2})', addr)
    postal_code = None
    city = None
    
    if postal_match:
        postal_code = f"{postal_match.group(1)} {postal_match.group(2)}"
        # City is usually after postal code
        after_postal = addr[postal_match.end():].strip()
        city_match = re.match(r'^([A-ZÅÄÖ\s]+)', after_postal)
        if city_match:
            city = city_match.group(1).strip()
        addr = addr[:postal_match.start()].strip()
    
    # Extract street number with optional entrance
    number_match = re.search(r'(\d+)\s*([A-Z])?(?:\s|,|$)', addr)
    street_number = None
    entrance = None
    
    if number_match:
        street_number = number_match.group(1)
        entrance = number_match.group(2)
        addr = addr[:number_match.start()].strip()
    
    # Remaining is street name
    street = addr.rstrip(',').strip()
    
    # Normalize street name
    for full, abbrev in STREET_TYPES.items():
        street = re.sub(rf'\b{full}\b', abbrev, street)
    
    # Build normalized form
    parts = [street]
    if street_number:
        parts.append(street_number)
        if entrance:
            parts.append(entrance)
    if postal_code:
        parts.append(postal_code)
    if city:
        parts.append(city)
    
    normalized = ' '.join(parts)
    
    return ParsedAddress(
        street=street,
        street_number=street_number,
        entrance=entrance,
        floor=None,  # TODO: extract floor
        apartment=None,  # TODO: extract apartment
        postal_code=postal_code or '',
        city=city or '',
        normalized=normalized
    )

def address_similarity(addr1: str, addr2: str) -> float:
    """
    Compute similarity between two addresses.
    """
    p1 = parse_swedish_address(addr1)
    p2 = parse_swedish_address(addr2)
    
    # Exact postal code match is strong signal
    postal_match = 1.0 if p1.postal_code == p2.postal_code else 0.0
    
    # Street match
    import jellyfish
    street_sim = jellyfish.jaro_winkler_similarity(p1.street, p2.street)
    
    # Number match
    number_match = 1.0 if p1.street_number == p2.street_number else 0.0
    
    # Combined score
    return 0.3 * postal_match + 0.5 * street_sim + 0.2 * number_match
```

---

## 11. Testing Strategy

### 11.1 Test Structure

```
tests/
├── conftest.py                    # Fixtures
├── test_api/
│   ├── test_entities.py
│   ├── test_patterns.py
│   └── test_resolution.py
├── test_ingestion/
│   ├── test_bolagsverket.py
│   └── test_allabolag.py
├── test_resolution/
│   ├── test_blocking.py
│   ├── test_comparison.py
│   └── test_resolver.py
├── test_swedish/
│   ├── test_personnummer.py
│   ├── test_company_name.py
│   └── test_address.py
├── test_patterns/
│   └── test_shell_network.py
└── fixtures/
    ├── companies.json
    ├── persons.json
    └── ground_truth.json
```

### 11.2 Key Test Cases

```python
# tests/test_swedish/test_personnummer.py

import pytest
from halo.swedish.personnummer import validate_personnummer

class TestPersonnummer:
    
    def test_valid_12_digit(self):
        result = validate_personnummer("19850101-1234")
        # Note: checksum may not be valid in example
        
    def test_valid_10_digit(self):
        result = validate_personnummer("8501011234")
        
    def test_samordningsnummer(self):
        # Day > 60 indicates samordningsnummer
        result = validate_personnummer("19850161-1234")
        assert result.is_samordningsnummer
        
    def test_invalid_checksum(self):
        result = validate_personnummer("19850101-1235")
        assert not result.valid
        assert "checksum" in result.error.lower()
        
    def test_invalid_date(self):
        result = validate_personnummer("19851301-1234")
        assert not result.valid
        assert "date" in result.error.lower()
```

### 11.3 Ground Truth Validation

```python
# tests/test_resolution/test_accuracy.py

import pytest
from halo.resolution.resolver import EntityResolver

class TestResolutionAccuracy:
    """
    Test resolution accuracy against ground truth.
    Target: >99.5% specificity, >90% sensitivity
    """
    
    @pytest.fixture
    def ground_truth(self, db):
        """Load ground truth from validation table."""
        return db.query(ValidationGroundTruth).all()
    
    def test_specificity_target(self, resolver, ground_truth):
        """
        Specificity = TN / (TN + FP) > 99.5%
        """
        negatives = [gt for gt in ground_truth if not gt.is_same_entity]
        
        true_negatives = 0
        false_positives = 0
        
        for gt in negatives:
            predicted_same = resolver.are_same_entity(gt.entity_a_id, gt.entity_b_id)
            if not predicted_same:
                true_negatives += 1
            else:
                false_positives += 1
        
        specificity = true_negatives / (true_negatives + false_positives)
        assert specificity >= 0.995, f"Specificity {specificity:.4f} below target 0.995"
    
    def test_sensitivity_target(self, resolver, ground_truth):
        """
        Sensitivity = TP / (TP + FN) > 90%
        """
        positives = [gt for gt in ground_truth if gt.is_same_entity]
        
        true_positives = 0
        false_negatives = 0
        
        for gt in positives:
            predicted_same = resolver.are_same_entity(gt.entity_a_id, gt.entity_b_id)
            if predicted_same:
                true_positives += 1
            else:
                false_negatives += 1
        
        sensitivity = true_positives / (true_positives + false_negatives)
        assert sensitivity >= 0.90, f"Sensitivity {sensitivity:.4f} below target 0.90"
```

---

## 12. Deployment

### 12.1 Docker Configuration

```yaml
# docker/docker-compose.yml
version: '3.8'

services:
  db:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: halo
      POSTGRES_USER: halo
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-extensions.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U halo"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7.2-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    environment:
      DATABASE_URL: postgresql://halo:${DB_PASSWORD}@db:5432/halo
      REDIS_URL: redis://redis:6379
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started

  worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    command: celery -A halo.derivation.scheduler worker -l info
    environment:
      DATABASE_URL: postgresql://halo:${DB_PASSWORD}@db:5432/halo
      REDIS_URL: redis://redis:6379
    depends_on:
      - db
      - redis

  beat:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    command: celery -A halo.derivation.scheduler beat -l info
    environment:
      DATABASE_URL: postgresql://halo:${DB_PASSWORD}@db:5432/halo
      REDIS_URL: redis://redis:6379
    depends_on:
      - db
      - redis

volumes:
  postgres_data:
  redis_data:
```

### 12.2 Initial Load Script

```python
# scripts/initial_load.py

import asyncio
import click
from halo.ingestion.orchestrator import IngestionOrchestrator
from halo.database import get_db_session

@click.command()
@click.option('--batch-size', default=1000, help='Batch size for processing')
@click.option('--skip-resolution', is_flag=True, help='Skip entity resolution')
def main(batch_size: int, skip_resolution: bool):
    """
    Run initial data load.
    """
    asyncio.run(_main(batch_size, skip_resolution))

async def _main(batch_size: int, skip_resolution: bool):
    async with get_db_session() as db:
        orchestrator = IngestionOrchestrator(db)
        
        click.echo("Starting initial load...")
        
        # Load companies
        click.echo("Loading companies from Bolagsverket...")
        await orchestrator.load_all_companies(batch_size=batch_size)
        
        if not skip_resolution:
            # Run resolution
            click.echo("Running entity resolution...")
            await orchestrator.resolve_all()
            
            # Compute derived facts
            click.echo("Computing derived facts...")
            await orchestrator.compute_derived_facts()
        
        click.echo("Initial load complete!")

if __name__ == '__main__':
    main()
```

---

## 13. Implementation Checklist

### Week 1-2: Infrastructure
- [ ] Repository setup with structure above
- [ ] Docker Compose for local development
- [ ] PostgreSQL with extensions (PostGIS, AGE)
- [ ] Alembic migrations for all tables
- [ ] Basic FastAPI app with health endpoint
- [ ] CI/CD pipeline

### Week 3-4: Ingestion
- [ ] Bolagsverket HVD client
- [ ] Company ingestion pipeline
- [ ] Director extraction from iXBRL
- [ ] Allabolag scraper integration
- [ ] Mention creation from both sources
- [ ] Provenance tracking

### Week 5-6: Swedish Utilities
- [ ] Personnummer validation
- [ ] Company name normalization
- [ ] Address parsing and normalization
- [ ] Unit tests for all utilities

### Week 7-8: Entity Resolution
- [ ] Blocking index implementation
- [ ] Feature comparison (name, identifiers)
- [ ] Confidence scoring
- [ ] Auto-match/reject logic
- [ ] Human review queue

### Week 9-10: Graph & Patterns
- [ ] Apache AGE integration
- [ ] Entity lookup API
- [ ] Relationship traversal API
- [ ] Shell network detection query
- [ ] Real-time alert generation

### Week 11-12: Derived Facts
- [ ] Risk score computation
- [ ] Director velocity calculation
- [ ] Address statistics
- [ ] Shell indicators
- [ ] Nightly job scheduling

### Week 13-14: Audit & Validation
- [ ] Audit logging implementation
- [ ] Ground truth data generation
- [ ] Accuracy measurement
- [ ] GDPR anonymization

### Week 15-16: Integration & Polish
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] API documentation
- [ ] Deployment to Scaleway
- [ ] Monitoring setup

---

## 14. Success Criteria

### MVP Complete When:

1. **Data Loaded**: All Swedish companies (including dissolved) with directors ingested
2. **Resolution Working**: >99.5% specificity, >90% sensitivity measured against ground truth
3. **Patterns Detected**: Shell network query returns results in <10s
4. **Alerts Generating**: New high-risk registrations trigger alerts
5. **API Functional**: All endpoints returning within performance targets
6. **Audit Complete**: All operations logged with provenance

### Performance Targets Met:

| Metric | Target | Measured |
|--------|--------|----------|
| Entity lookup | <100ms | ___ |
| 2-hop traversal | <1s | ___ |
| Pattern query | <10s | ___ |
| Nightly derivation | <4hr | ___ |
| Specificity | >99.5% | ___ |
| Sensitivity | >90% | ___ |

---

## 15. Frontend Architecture

### 15.1 Overview

The frontend provides two integrated modes for exploring the full Swedish corporate graph:

1. **Discovery Mode** — Geographic semantic zoom showing all entities on a map of Sweden
2. **Investigation Mode** — Network-centric workspace for deep analysis of bounded entity sets

Users flow naturally between modes: discover patterns geographically, then open investigation workspaces for detailed analysis.

### 15.2 Tech Stack

| Component | Library | Version | Rationale |
|-----------|---------|---------|-----------|
| Framework | React | 18+ | Standard, large ecosystem |
| Language | TypeScript | 5+ | Type safety for complex state |
| Build | Vite | 5+ | Fast dev server, good production builds |
| Routing | React Router | 6+ | Standard |
| State | Zustand | 4+ | Simpler than Redux, good for graph state |
| Server State | TanStack Query | 5+ | Caching, background refresh, pagination |
| Map | Mapbox GL JS | 3+ | Best performance, semantic zoom support |
| Spatial Index | H3-js | 4+ | Uber's hierarchical hex grid |
| Clustering | Supercluster | 8+ | Fast viewport clustering |
| Graph | Cytoscape.js | 3.28+ | Mature, good interaction model |
| Graph Layout | Cola.js | 3+ | Constraint-based, better than pure force |
| Styling | Tailwind CSS | 3+ | Rapid iteration |
| Components | Radix UI | Latest | Accessible primitives |
| Icons | Lucide React | Latest | Clean, consistent |
| Charts | Recharts | 2+ | Simple, React-native |

### 15.3 Project Structure

```
frontend/
├── public/
│   └── favicon.ico
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css
│   │
│   ├── api/                      # API client
│   │   ├── client.ts             # Axios/fetch setup
│   │   ├── entities.ts           # Entity endpoints
│   │   ├── spatial.ts            # Spatial/cluster endpoints
│   │   ├── patterns.ts           # Pattern detection endpoints
│   │   └── investigations.ts     # Investigation CRUD
│   │
│   ├── components/
│   │   ├── common/               # Shared components
│   │   │   ├── Button.tsx
│   │   │   ├── Panel.tsx
│   │   │   ├── SearchInput.tsx
│   │   │   └── RiskBadge.tsx
│   │   │
│   │   ├── discovery/            # Discovery mode
│   │   │   ├── DiscoveryMap.tsx
│   │   │   ├── ClusterLayer.tsx
│   │   │   ├── EntityLayer.tsx
│   │   │   ├── EdgeLayer.tsx
│   │   │   ├── ClusterPopup.tsx
│   │   │   └── MapControls.tsx
│   │   │
│   │   ├── investigation/        # Investigation mode
│   │   │   ├── InvestigationWorkspace.tsx
│   │   │   ├── GraphCanvas.tsx
│   │   │   ├── NodeRenderer.tsx
│   │   │   ├── EdgeRenderer.tsx
│   │   │   ├── LayoutControls.tsx
│   │   │   └── EvidencePanel.tsx
│   │   │
│   │   ├── detail/               # Entity detail
│   │   │   ├── DetailPanel.tsx
│   │   │   ├── PersonDetail.tsx
│   │   │   ├── CompanyDetail.tsx
│   │   │   ├── AddressDetail.tsx
│   │   │   ├── RelationshipList.tsx
│   │   │   └── TimelineView.tsx
│   │   │
│   │   ├── patterns/             # Pattern views
│   │   │   ├── PatternList.tsx
│   │   │   ├── ShellNetworkCard.tsx
│   │   │   └── AlertsList.tsx
│   │   │
│   │   └── layout/               # App layout
│   │       ├── AppShell.tsx
│   │       ├── Sidebar.tsx
│   │       ├── Header.tsx
│   │       └── ModeSwitcher.tsx
│   │
│   ├── stores/                   # Zustand stores
│   │   ├── mapStore.ts           # Viewport, zoom level
│   │   ├── selectionStore.ts     # Selected entities
│   │   ├── investigationStore.ts # Current investigation state
│   │   ├── filterStore.ts        # Active filters
│   │   └── uiStore.ts            # Panel states, mode
│   │
│   ├── hooks/                    # Custom hooks
│   │   ├── useMapClusters.ts
│   │   ├── useEntityDetail.ts
│   │   ├── useGraphLayout.ts
│   │   ├── useInvestigation.ts
│   │   └── useKeyboardShortcuts.ts
│   │
│   ├── lib/                      # Utilities
│   │   ├── spatial.ts            # H3, geo calculations
│   │   ├── graph.ts              # Graph utilities
│   │   ├── colors.ts             # Risk color scales
│   │   └── format.ts             # Swedish formatters
│   │
│   └── types/                    # TypeScript types
│       ├── entity.ts
│       ├── spatial.ts
│       ├── graph.ts
│       └── investigation.ts
│
├── package.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.ts
└── .env.example
```

### 15.4 Discovery Mode — Geographic Semantic Zoom

#### 15.4.1 Zoom Levels

| Level | Scale | Display | Data Source |
|-------|-------|---------|-------------|
| 1-4 | National | H3 res 3 hexagons (~12K km²) | Pre-aggregated |
| 5-7 | Regional | H3 res 5 hexagons (~250 km²) | Pre-aggregated |
| 8-10 | Municipal | H3 res 7 hexagons (~5 km²) | Pre-aggregated |
| 11-13 | District | H3 res 9 hexagons (~0.1 km²) | Dynamic query |
| 14-16 | Street | Individual entities | Dynamic query |
| 17+ | Building | Full graph with edges | Dynamic query |

#### 15.4.2 Cluster Data Structure

```typescript
interface SpatialCluster {
  h3Index: string;           // H3 cell ID
  resolution: number;        // H3 resolution (3, 5, 7, 9)
  center: [number, number];  // [lng, lat]
  
  // Counts
  entityCount: number;
  companyCount: number;
  personCount: number;
  addressCount: number;
  
  // Risk aggregates
  avgRiskScore: number;
  maxRiskScore: number;
  highRiskCount: number;     // Entities with risk > 0.7
  
  // Pattern indicators
  shellNetworkCount: number;
  alertCount: number;
  
  // For rendering
  bounds: GeoJSON.Polygon;
}
```

#### 15.4.3 Server Endpoints for Spatial

```python
# New endpoints in src/halo/api/spatial.py

@router.get("/clusters/{resolution}")
async def get_clusters(
    resolution: int,  # H3 resolution: 3, 5, 7, or 9
    bounds: str,      # "minLng,minLat,maxLng,maxLat"
    min_risk: float = 0.0,
    db: Session = Depends(get_db),
) -> list[SpatialCluster]:
    """
    Get pre-aggregated clusters for viewport.
    Performance target: <200ms
    """
    pass

@router.get("/entities/viewport")
async def get_entities_in_viewport(
    bounds: str,
    zoom: int,
    limit: int = 5000,
    min_risk: float = 0.0,
    entity_types: str = None,  # Comma-separated
    db: Session = Depends(get_db),
) -> EntityViewportResponse:
    """
    Get individual entities for high zoom levels.
    Performance target: <500ms
    """
    pass

@router.get("/edges/viewport")
async def get_edges_in_viewport(
    bounds: str,
    entity_ids: str,  # Comma-separated, from entities query
    predicates: str = None,
    db: Session = Depends(get_db),
) -> list[EdgeResponse]:
    """
    Get edges between entities in viewport.
    Performance target: <300ms
    """
    pass
```

#### 15.4.4 Pre-aggregation Schema

```sql
-- Migration: Add spatial aggregation tables

-- H3 aggregates at multiple resolutions
CREATE TABLE spatial_clusters (
    h3_index TEXT NOT NULL,
    resolution INT NOT NULL,
    
    -- Counts
    entity_count INT NOT NULL DEFAULT 0,
    company_count INT NOT NULL DEFAULT 0,
    person_count INT NOT NULL DEFAULT 0,
    address_count INT NOT NULL DEFAULT 0,
    
    -- Risk
    avg_risk_score FLOAT NOT NULL DEFAULT 0.0,
    max_risk_score FLOAT NOT NULL DEFAULT 0.0,
    high_risk_count INT NOT NULL DEFAULT 0,
    
    -- Patterns
    shell_network_count INT NOT NULL DEFAULT 0,
    alert_count INT NOT NULL DEFAULT 0,
    
    -- Geometry for fast queries
    center GEOGRAPHY(POINT, 4326) NOT NULL,
    bounds GEOGRAPHY(POLYGON, 4326) NOT NULL,
    
    -- Timestamps
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    PRIMARY KEY (h3_index, resolution)
);

CREATE INDEX idx_cluster_resolution ON spatial_clusters(resolution);
CREATE INDEX idx_cluster_bounds ON spatial_clusters USING GIST(bounds);
CREATE INDEX idx_cluster_risk ON spatial_clusters(resolution, avg_risk_score);

-- Entity to H3 mapping (for fast aggregation updates)
CREATE TABLE entity_h3_mapping (
    entity_id UUID PRIMARY KEY REFERENCES entities(id),
    h3_res3 TEXT NOT NULL,
    h3_res5 TEXT NOT NULL,
    h3_res7 TEXT NOT NULL,
    h3_res9 TEXT NOT NULL,
    coordinates GEOGRAPHY(POINT, 4326)
);

CREATE INDEX idx_entity_h3_res3 ON entity_h3_mapping(h3_res3);
CREATE INDEX idx_entity_h3_res5 ON entity_h3_mapping(h3_res5);
CREATE INDEX idx_entity_h3_res7 ON entity_h3_mapping(h3_res7);
CREATE INDEX idx_entity_h3_res9 ON entity_h3_mapping(h3_res9);
```

#### 15.4.5 DiscoveryMap Component

```typescript
// src/components/discovery/DiscoveryMap.tsx

import { useEffect, useRef, useCallback } from 'react';
import mapboxgl from 'mapbox-gl';
import { useMapStore } from '@/stores/mapStore';
import { useFilterStore } from '@/stores/filterStore';
import { useSpatialClusters, useViewportEntities } from '@/hooks/useMapData';
import { ClusterLayer } from './ClusterLayer';
import { EntityLayer } from './EntityLayer';
import { EdgeLayer } from './EdgeLayer';

const CLUSTER_ZOOM_THRESHOLD = 14;
const EDGE_ZOOM_THRESHOLD = 17;

export function DiscoveryMap() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  
  const { viewport, setViewport } = useMapStore();
  const { filters } = useFilterStore();
  
  const zoom = viewport.zoom;
  const showClusters = zoom < CLUSTER_ZOOM_THRESHOLD;
  const showEntities = zoom >= CLUSTER_ZOOM_THRESHOLD;
  const showEdges = zoom >= EDGE_ZOOM_THRESHOLD;
  
  // Determine H3 resolution from zoom
  const h3Resolution = zoom < 5 ? 3 : zoom < 8 ? 5 : zoom < 11 ? 7 : 9;
  
  // Fetch appropriate data
  const { data: clusters } = useSpatialClusters({
    resolution: h3Resolution,
    bounds: viewport.bounds,
    enabled: showClusters,
  });
  
  const { data: entities } = useViewportEntities({
    bounds: viewport.bounds,
    zoom,
    filters,
    enabled: showEntities,
  });
  
  // Initialize map
  useEffect(() => {
    if (!mapContainer.current || map.current) return;
    
    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [18.0686, 59.3293], // Stockholm
      zoom: 5,
    });
    
    map.current.on('moveend', () => {
      const m = map.current!;
      setViewport({
        center: m.getCenter().toArray(),
        zoom: m.getZoom(),
        bounds: m.getBounds().toArray().flat(),
      });
    });
    
    return () => map.current?.remove();
  }, []);
  
  return (
    <div ref={mapContainer} className="w-full h-full">
      {map.current && (
        <>
          {showClusters && clusters && (
            <ClusterLayer map={map.current} clusters={clusters} />
          )}
          {showEntities && entities && (
            <EntityLayer map={map.current} entities={entities} />
          )}
          {showEdges && entities && (
            <EdgeLayer map={map.current} entityIds={entities.map(e => e.id)} />
          )}
        </>
      )}
    </div>
  );
}
```

### 15.5 Investigation Mode — Network Workspace

#### 15.5.1 Investigation Data Model

```typescript
interface Investigation {
  id: string;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
  
  // Working set
  entities: InvestigationEntity[];
  
  // Layout positions (persisted)
  positions: Record<string, { x: number; y: number }>;
  
  // Filters and view state
  visiblePredicates: string[];
  timeRange?: [string, string];
  
  // Evidence collection
  evidence: EvidenceItem[];
  
  // Annotations
  notes: InvestigationNote[];
}

interface InvestigationEntity {
  entityId: string;
  addedAt: string;
  addedBy: string;
  addedReason: string;  // "search", "expansion", "pattern_match", "manual"
  pinned: boolean;      // Pinned entities stay visible
}

interface EvidenceItem {
  id: string;
  entityId: string;
  factIds: string[];
  note?: string;
  addedAt: string;
}
```

#### 15.5.2 Graph Canvas Component

```typescript
// src/components/investigation/GraphCanvas.tsx

import { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import cola from 'cytoscape-cola';
import { useInvestigationStore } from '@/stores/investigationStore';
import { useSelectionStore } from '@/stores/selectionStore';

cytoscape.use(cola);

export function GraphCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  
  const { entities, edges, positions, setPositions } = useInvestigationStore();
  const { selectedIds, setSelected } = useSelectionStore();
  
  // Initialize Cytoscape
  useEffect(() => {
    if (!containerRef.current) return;
    
    cyRef.current = cytoscape({
      container: containerRef.current,
      style: graphStyles,
      layout: { name: 'preset' },
      minZoom: 0.1,
      maxZoom: 3,
    });
    
    // Selection handling
    cyRef.current.on('tap', 'node', (e) => {
      setSelected([e.target.id()]);
    });
    
    // Position persistence
    cyRef.current.on('dragfree', 'node', (e) => {
      const node = e.target;
      setPositions({
        ...positions,
        [node.id()]: node.position(),
      });
    });
    
    return () => cyRef.current?.destroy();
  }, []);
  
  // Update graph data
  useEffect(() => {
    if (!cyRef.current) return;
    
    const cy = cyRef.current;
    
    // Build elements
    const nodes = entities.map(e => ({
      data: {
        id: e.id,
        label: e.canonical_name,
        type: e.entity_type,
        riskScore: e.attributes?.risk_score ?? 0,
      },
      position: positions[e.id] ?? undefined,
    }));
    
    const edgeElements = edges.map(e => ({
      data: {
        id: `${e.source}-${e.predicate}-${e.target}`,
        source: e.source,
        target: e.target,
        predicate: e.predicate,
      },
    }));
    
    // Update
    cy.json({ elements: { nodes, edges: edgeElements } });
    
    // Run layout for nodes without positions
    const noPosition = nodes.filter(n => !n.position);
    if (noPosition.length > 0) {
      cy.layout({
        name: 'cola',
        animate: true,
        randomize: false,
        fit: false,
        nodeSpacing: 50,
      }).run();
    }
  }, [entities, edges, positions]);
  
  // Highlight selection
  useEffect(() => {
    if (!cyRef.current) return;
    
    cyRef.current.nodes().removeClass('selected');
    selectedIds.forEach(id => {
      cyRef.current!.$id(id).addClass('selected');
    });
  }, [selectedIds]);
  
  return <div ref={containerRef} className="w-full h-full" />;
}

const graphStyles: cytoscape.Stylesheet[] = [
  {
    selector: 'node',
    style: {
      'label': 'data(label)',
      'background-color': (ele) => riskColor(ele.data('riskScore')),
      'width': 40,
      'height': 40,
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 5,
    },
  },
  {
    selector: 'node[type="COMPANY"]',
    style: { 'shape': 'rectangle' },
  },
  {
    selector: 'node[type="PERSON"]',
    style: { 'shape': 'ellipse' },
  },
  {
    selector: 'node[type="ADDRESS"]',
    style: { 'shape': 'diamond' },
  },
  {
    selector: 'node.selected',
    style: {
      'border-width': 3,
      'border-color': '#3b82f6',
    },
  },
  {
    selector: 'edge',
    style: {
      'width': 1,
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      'label': 'data(predicate)',
      'font-size': 8,
      'text-rotation': 'autorotate',
    },
  },
];
```

#### 15.5.3 Progressive Expansion

```typescript
// src/hooks/useGraphExpansion.ts

import { useMutation } from '@tanstack/react-query';
import { useInvestigationStore } from '@/stores/investigationStore';
import { api } from '@/api/client';

interface ExpandOptions {
  entityId: string;
  predicates?: string[];
  direction?: 'outgoing' | 'incoming' | 'both';
  limit?: number;
  minRisk?: number;
}

export function useGraphExpansion() {
  const { addEntities, addEdges, investigation } = useInvestigationStore();
  
  return useMutation({
    mutationFn: async (options: ExpandOptions) => {
      const response = await api.get(`/entities/${options.entityId}/connections`, {
        params: {
          predicates: options.predicates?.join(','),
          direction: options.direction ?? 'both',
          limit: options.limit ?? 10,
          min_risk: options.minRisk ?? 0,
          exclude: investigation.entities.map(e => e.entityId).join(','),
        },
      });
      return response.data;
    },
    onSuccess: (data, options) => {
      // Add new entities
      addEntities(data.entities.map(e => ({
        entityId: e.id,
        addedAt: new Date().toISOString(),
        addedBy: 'user',
        addedReason: 'expansion',
        pinned: false,
      })));
      
      // Add edges
      addEdges(data.edges);
    },
  });
}
```

#### 15.5.4 Server Endpoint for Expansion

```python
# Add to src/halo/api/entities.py

@router.get("/{entity_id}/connections")
async def get_connections(
    entity_id: UUID,
    predicates: Optional[str] = None,
    direction: str = "both",
    limit: int = 10,
    min_risk: float = 0.0,
    exclude: Optional[str] = None,  # Comma-separated UUIDs to exclude
    db: AsyncSession = Depends(get_db),
) -> ConnectionsResponse:
    """
    Get connections for progressive graph expansion.
    Returns entities and edges, sorted by risk score.
    """
    excluded_ids = set(exclude.split(",")) if exclude else set()
    predicate_list = predicates.split(",") if predicates else None
    
    # Build query based on direction
    if direction == "outgoing":
        query = """
            SELECT DISTINCT ON (f.object_id)
                f.object_id as entity_id,
                f.predicate,
                e.canonical_name,
                e.entity_type,
                COALESCE(pa.risk_score, ca.risk_score, 0) as risk_score
            FROM facts f
            JOIN entities e ON e.id = f.object_id
            LEFT JOIN person_attributes pa ON pa.entity_id = e.id
            LEFT JOIN company_attributes ca ON ca.entity_id = e.id
            WHERE f.subject_id = :entity_id
            AND f.fact_type = 'RELATIONSHIP'
            AND f.superseded_by IS NULL
            AND e.status = 'ACTIVE'
            AND (:predicates IS NULL OR f.predicate = ANY(:predicates))
            AND e.id != ALL(:excluded)
            ORDER BY f.object_id, risk_score DESC
        """
    elif direction == "incoming":
        # Similar but swapped subject/object
        pass
    else:  # both
        # UNION of both directions
        pass
    
    # Execute and filter by risk
    # Return top N by risk score
    pass
```

### 15.6 Shared Components

#### 15.6.1 Detail Panel

```typescript
// src/components/detail/DetailPanel.tsx

import { useQuery } from '@tanstack/react-query';
import { useSelectionStore } from '@/stores/selectionStore';
import { api } from '@/api/client';
import { PersonDetail } from './PersonDetail';
import { CompanyDetail } from './CompanyDetail';
import { AddressDetail } from './AddressDetail';
import { RelationshipList } from './RelationshipList';
import { TimelineView } from './TimelineView';

export function DetailPanel() {
  const { selectedIds } = useSelectionStore();
  const entityId = selectedIds[0];
  
  const { data: entity, isLoading } = useQuery({
    queryKey: ['entity', entityId],
    queryFn: () => api.get(`/entities/${entityId}`).then(r => r.data),
    enabled: !!entityId,
  });
  
  if (!entityId) {
    return (
      <div className="p-4 text-gray-400">
        Select an entity to view details
      </div>
    );
  }
  
  if (isLoading) {
    return <div className="p-4">Loading...</div>;
  }
  
  return (
    <div className="h-full overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <h2 className="text-lg font-semibold">{entity.canonical_name}</h2>
        <div className="flex items-center gap-2 mt-1">
          <EntityTypeBadge type={entity.entity_type} />
          <RiskBadge score={entity.attributes?.risk_score} />
        </div>
      </div>
      
      {/* Type-specific content */}
      <div className="p-4">
        {entity.entity_type === 'PERSON' && <PersonDetail entity={entity} />}
        {entity.entity_type === 'COMPANY' && <CompanyDetail entity={entity} />}
        {entity.entity_type === 'ADDRESS' && <AddressDetail entity={entity} />}
      </div>
      
      {/* Relationships */}
      <div className="border-t border-gray-700 p-4">
        <h3 className="font-medium mb-2">Relationships</h3>
        <RelationshipList entityId={entityId} />
      </div>
      
      {/* Timeline */}
      <div className="border-t border-gray-700 p-4">
        <h3 className="font-medium mb-2">Timeline</h3>
        <TimelineView entityId={entityId} />
      </div>
      
      {/* Actions */}
      <div className="border-t border-gray-700 p-4 flex gap-2">
        <Button onClick={() => openInInvestigation(entityId)}>
          Open Investigation
        </Button>
        <Button variant="secondary" onClick={() => addToEvidence(entityId)}>
          Add to Evidence
        </Button>
      </div>
    </div>
  );
}
```

#### 15.6.2 Filter Panel

```typescript
// src/components/common/FilterPanel.tsx

import { useFilterStore } from '@/stores/filterStore';

export function FilterPanel() {
  const {
    entityTypes,
    setEntityTypes,
    predicates,
    setPredicates,
    riskRange,
    setRiskRange,
    timeRange,
    setTimeRange,
  } = useFilterStore();
  
  return (
    <div className="p-4 space-y-4">
      {/* Entity Types */}
      <div>
        <h4 className="text-sm font-medium mb-2">Entity Types</h4>
        <div className="space-y-1">
          <Checkbox
            checked={entityTypes.includes('COMPANY')}
            onChange={(v) => toggleArrayItem(entityTypes, 'COMPANY', setEntityTypes)}
            label="Companies"
          />
          <Checkbox
            checked={entityTypes.includes('PERSON')}
            onChange={(v) => toggleArrayItem(entityTypes, 'PERSON', setEntityTypes)}
            label="Persons"
          />
          <Checkbox
            checked={entityTypes.includes('ADDRESS')}
            onChange={(v) => toggleArrayItem(entityTypes, 'ADDRESS', setEntityTypes)}
            label="Addresses"
          />
        </div>
      </div>
      
      {/* Relationship Types */}
      <div>
        <h4 className="text-sm font-medium mb-2">Relationships</h4>
        <div className="space-y-1">
          <Checkbox
            checked={predicates.includes('DIRECTOR_OF')}
            onChange={(v) => toggleArrayItem(predicates, 'DIRECTOR_OF', setPredicates)}
            label="Directors"
          />
          <Checkbox
            checked={predicates.includes('SHAREHOLDER_OF')}
            onChange={(v) => toggleArrayItem(predicates, 'SHAREHOLDER_OF', setPredicates)}
            label="Shareholders"
          />
          <Checkbox
            checked={predicates.includes('REGISTERED_AT')}
            onChange={(v) => toggleArrayItem(predicates, 'REGISTERED_AT', setPredicates)}
            label="Addresses"
          />
        </div>
      </div>
      
      {/* Risk Range */}
      <div>
        <h4 className="text-sm font-medium mb-2">Risk Score</h4>
        <RangeSlider
          min={0}
          max={1}
          step={0.1}
          value={riskRange}
          onChange={setRiskRange}
        />
      </div>
      
      {/* Time Range */}
      <div>
        <h4 className="text-sm font-medium mb-2">Time Period</h4>
        <DateRangePicker
          value={timeRange}
          onChange={setTimeRange}
        />
      </div>
    </div>
  );
}
```

### 15.7 Application Shell

```typescript
// src/components/layout/AppShell.tsx

import { useState } from 'react';
import { useUIStore } from '@/stores/uiStore';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { DiscoveryMap } from '../discovery/DiscoveryMap';
import { InvestigationWorkspace } from '../investigation/InvestigationWorkspace';
import { DetailPanel } from '../detail/DetailPanel';
import { FilterPanel } from '../common/FilterPanel';

export function AppShell() {
  const { mode, sidebarOpen, detailOpen } = useUIStore();
  
  return (
    <div className="h-screen flex flex-col bg-gray-900 text-white">
      {/* Header */}
      <Header />
      
      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar */}
        {sidebarOpen && (
          <aside className="w-64 border-r border-gray-700 flex flex-col">
            <Sidebar />
          </aside>
        )}
        
        {/* Center: Map or Graph */}
        <main className="flex-1 relative">
          {mode === 'discovery' ? (
            <DiscoveryMap />
          ) : (
            <InvestigationWorkspace />
          )}
          
          {/* Floating controls */}
          <div className="absolute top-4 left-4 z-10">
            <ModeSwitcher />
          </div>
          
          <div className="absolute top-4 right-4 z-10">
            <SearchInput />
          </div>
        </main>
        
        {/* Right panel: Filters + Detail */}
        <aside className="w-80 border-l border-gray-700 flex flex-col">
          <FilterPanel />
          {detailOpen && <DetailPanel />}
        </aside>
      </div>
    </div>
  );
}
```

### 15.8 API Additions Summary

New endpoints required for frontend:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/spatial/clusters/{resolution}` | GET | Pre-aggregated H3 clusters |
| `/spatial/entities/viewport` | GET | Entities in map viewport |
| `/spatial/edges/viewport` | GET | Edges between viewport entities |
| `/entities/{id}/connections` | GET | Progressive expansion |
| `/investigations` | GET, POST | List/create investigations |
| `/investigations/{id}` | GET, PUT, DELETE | Investigation CRUD |
| `/investigations/{id}/entities` | POST, DELETE | Add/remove entities |
| `/investigations/{id}/evidence` | POST, DELETE | Evidence collection |
| `/search` | GET | Global search across entities |

### 15.9 Performance Budgets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Initial map load | <2s | Time to interactive |
| Cluster fetch | <200ms | API response |
| Viewport entities | <500ms | API response |
| Graph layout (100 nodes) | <500ms | Client-side |
| Graph layout (500 nodes) | <2s | Client-side |
| Entity detail load | <100ms | API response |
| Search results | <300ms | API response |

---

## 16. Frontend Implementation Phases

### Phase 1: Foundation (Weeks 17-18)
- [ ] Vite + React + TypeScript setup
- [ ] Tailwind configuration
- [ ] API client with TanStack Query
- [ ] Zustand stores skeleton
- [ ] App shell with routing
- [ ] Basic header and sidebar

### Phase 2: Discovery Map (Weeks 19-20)
- [ ] Mapbox GL integration
- [ ] H3 cluster layer
- [ ] Cluster aggregation backend
- [ ] Viewport entity loading
- [ ] Zoom-level transitions
- [ ] Map controls

### Phase 3: Investigation Workspace (Weeks 21-22)
- [ ] Cytoscape.js integration
- [ ] Cola.js layout
- [ ] Progressive expansion
- [ ] Node/edge rendering
- [ ] Selection handling
- [ ] Position persistence

### Phase 4: Detail & Interaction (Weeks 23-24)
- [ ] Detail panel (all entity types)
- [ ] Relationship list
- [ ] Timeline view
- [ ] Filter panel
- [ ] Mode switching
- [ ] Evidence collection

---

*This specification is ready for implementation. All decisions are final. Build it.*