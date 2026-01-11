# Halo Intelligence Platform - System Rundown

**Version**: 1.0
**Last Updated**: December 2024

A comprehensive Swedish-sovereign intelligence platform for financial crime detection, entity resolution, and investigation case management.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Core Systems](#2-core-systems)
3. [Data Ingestion](#3-data-ingestion)
4. [Intelligence Engine](#4-intelligence-engine)
5. [Graph Database](#5-graph-database)
6. [API Layer](#6-api-layer)
7. [User Interface](#7-user-interface)
8. [Security & Compliance](#8-security--compliance)
9. [Database Schema](#9-database-schema)
10. [Component Interactions](#10-component-interactions)

---

## 1. Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           PRESENTATION LAYER                             │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    React Frontend (TypeScript)                   │    │
│  │  Dashboard │ Entities │ Alerts │ Cases │ Search │ Graph View    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              API LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI REST Endpoints                        │    │
│  │  Auth │ Entities │ Alerts │ Cases │ Search │ Graph │ Intelligence│    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         BUSINESS LOGIC LAYER                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ Intelligence │ │   Entity     │ │Investigation │ │     NLP      │   │
│  │   Engine     │ │ Resolution   │ │   Workflow   │ │   Pipeline   │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATA ACCESS LAYER                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ Repositories │ │Graph Client  │ │   Adapters   │ │    Cache     │   │
│  │ (SQLAlchemy) │ │   (Neo4j)    │ │ (Ingestion)  │ │   (Redis)    │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           STORAGE LAYER                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │  PostgreSQL  │ │    Neo4j     │ │Elasticsearch │ │    Redis     │   │
│  │ (Primary DB) │ │   (Graph)    │ │  (Search)    │ │  (Sessions)  │   │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 18, TypeScript, Vite | User interface |
| Styling | Tailwind CSS, Lucide Icons | UI components |
| API | FastAPI, Pydantic | REST endpoints |
| ORM | SQLAlchemy (async) | Database access |
| Primary DB | PostgreSQL | Relational data |
| Graph DB | Neo4j | Entity relationships |
| Search | Elasticsearch | Full-text search |
| Cache | Redis | Sessions, caching |
| NLP | KB-BERT, GPT-SW3 | Swedish text analysis |

---

## 2. Core Systems

### 2.1 Entity Management

**Location**: `halo/entities/`

The entity system manages people, companies, properties, and vehicles with Swedish-specific validation.

#### Components

| File | Purpose |
|------|---------|
| `models.py` | Pydantic models for entity attributes |
| `graph.py` | Entity relationship graph operations |
| `relationships.py` | Relationship type definitions |
| `resolution.py` | Entity matching and deduplication |
| `swedish_personnummer.py` | Swedish personal ID (personnummer) validation |
| `organisationsnummer.py` | Swedish company ID validation |

#### Entity Types

```python
class EntityType(str, Enum):
    PERSON = "person"
    COMPANY = "company"
    PROPERTY = "property"
    VEHICLE = "vehicle"
```

#### Relationship Types

```python
class RelationshipType(str, Enum):
    OWNER = "owner"              # Ownership
    BOARD_MEMBER = "board_member" # Company board
    FAMILY = "family"            # Family relationship
    BUSINESS = "business"        # Business connection
    TRANSACTION = "transaction"  # Financial link
    CO_LOCATED = "co_located"    # Same address
    CO_DIRECTOR = "co_director"  # Shared directorship
```

### 2.2 Investigation Workflow

**Location**: `halo/investigation/`

Manages investigation cases from creation to closure with workflow automation.

#### Components

| File | Purpose |
|------|---------|
| `case_manager.py` | Case lifecycle management |
| `evidence.py` | Evidence collection and chain of custody |
| `timeline.py` | Event timeline construction |
| `workflow.py` | State machine for case progression |

#### Case States

```
DRAFT → OPEN → INVESTIGATION → REVIEW → CLOSED
                    ↓
                ESCALATED
```

#### Case Types

- `FRAUD` - Financial fraud investigation
- `AML` - Anti-money laundering
- `SANCTIONS` - Sanctions violation
- `PEP` - Politically exposed person review
- `INTERNAL` - Internal investigation

### 2.3 Alert System

**Location**: `halo/api/routes/alerts.py`, `halo/anomaly/`

Manages alerts with a three-tier human-in-the-loop system for Brottsdatalagen compliance.

#### Alert Tiers

| Tier | Description | Action Required |
|------|-------------|-----------------|
| **Tier 1** | Automated alerts | Auto-processed, logged |
| **Tier 2** | Human acknowledgment | Analyst must acknowledge |
| **Tier 3** | Human approval | Senior analyst must approve/reject |

#### Alert Workflow

```
Detection → Alert Created → Tier Assignment
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           Tier 1          Tier 2          Tier 3
        (Automatic)    (Acknowledge)    (Approve/Reject)
              │               │               │
              └───────────────┼───────────────┘
                              ▼
                    Alert Resolution
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          Dismissed     Escalated to      Closed
                          Case
```

### 2.4 Audit System

**Location**: `halo/db/models.py`, `halo/api/routes/audit.py`

Immutable audit logging with cryptographic integrity verification.

#### Features

- **Hash Chain**: Each entry contains HMAC of previous entry
- **Tamper Detection**: Broken chain indicates manipulation
- **User Attribution**: All actions tied to authenticated user
- **Resource Tracking**: Tracks access to sensitive entities

#### Audit Entry Structure

```python
class AuditLog:
    id: UUID
    user_id: UUID
    user_name: str
    action: str           # view, create, update, delete, export
    resource_type: str    # entity, alert, case, document
    resource_id: UUID
    details: dict         # Additional context
    entry_hash: str       # HMAC-SHA256 of entry
    previous_hash: str    # Link to previous entry
    created_at: datetime
```

---

## 3. Data Ingestion

**Location**: `halo/ingestion/`

Adapters for Swedish government data sources and external systems.

### 3.1 Data Source Adapters

| Adapter | Source | Data Type |
|---------|--------|-----------|
| `bolagsverket_hvd.py` | Swedish Companies House | Company registration, directors, ownership |
| `scb_foretag.py` | Statistics Sweden | Business statistics |
| `scb_pxweb.py` | SCB PxWeb API | Statistical tables |
| `lantmateriet.py` | Land Survey Authority | Property ownership |
| `lantmateriet_geotorget.py` | Lantmäteriet Geotorget | Geographic data |
| `polisen_incidents.py` | Swedish Police | Incident reports |
| `bank_transactions.py` | Banks | CAMT.053, CSV, Bankgirot |
| `document_upload.py` | Internal | PDF, DOCX documents |

### 3.2 Adapter Architecture

```python
class BaseAdapter(ABC):
    """Abstract base for all data adapters."""

    @abstractmethod
    async def fetch(self, params: dict) -> list[dict]:
        """Fetch raw data from source."""
        pass

    @abstractmethod
    def transform(self, raw_data: dict) -> Entity:
        """Transform raw data to entity model."""
        pass

    @abstractmethod
    async def load(self, entities: list[Entity]) -> int:
        """Load entities into database."""
        pass
```

### 3.3 Bolagsverket HVD Integration

**File**: `halo/ingestion/bolagsverket_hvd.py`

Integrates with Swedish Companies House High Value Dataset.

#### Capabilities

- Company basic information (name, legal form, status)
- Registration dates and changes
- SNI codes (industry classification)
- Director and board member information
- Ownership structures
- Address history
- F-skatt and VAT registration status

#### Example Usage

```python
adapter = BolagsverketHVDAdapter()

# Fetch company by organisationsnummer
company_data = await adapter.fetch_company("5566778899")

# Transform to graph node
company = adapter.transform_company(company_data)

# Load into graph
await graph_loader.load_company(company)
```

### 3.4 Graph Loader

**File**: `halo/ingestion/graph_loader.py`

Loads ingested data into the intelligence graph.

#### Operations

```python
class GraphLoader:
    async def load_company_from_bolagsverket(
        self,
        orgnr: str,
        include_directors: bool = True,
        include_address: bool = True
    ) -> str:
        """Load company with relationships."""

    async def load_companies_batch(
        self,
        orgnrs: list[str]
    ) -> list[str]:
        """Batch load multiple companies."""
```

### 3.5 Rate Limiting

**File**: `halo/ingestion/rate_limiter.py`

Implements rate limiting for external API calls.

```python
class RateLimiter:
    def __init__(
        self,
        calls_per_second: float = 10,
        calls_per_minute: float = 300,
        backoff_factor: float = 2.0
    ):
        ...
```

---

## 4. Intelligence Engine

**Location**: `halo/intelligence/`

Three-layer detection system for fraud and financial crime.

### 4.1 Detection Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 3: PREDICTIVE                       │
│         ML-based risk prediction and scoring                 │
│    ┌─────────────────────────────────────────────────┐      │
│    │ Risk Predictor │ Konkurs Predictor │ Network Risk│      │
│    └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 2: PATTERN                          │
│          Cypher-based fraud pattern matching                 │
│    ┌─────────────────────────────────────────────────┐      │
│    │ Registration Mills │ Shell Networks │ Phoenix    │      │
│    └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    LAYER 1: ANOMALY                          │
│       Statistical deviation from baseline behavior           │
│    ┌─────────────────────────────────────────────────┐      │
│    │ Address Scorer │ Company Scorer │ Person Scorer │      │
│    └─────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Anomaly Detection

**File**: `halo/intelligence/anomaly.py`

Statistical anomaly detection based on Swedish business baselines.

#### Baseline Statistics

```python
class BaselineStats:
    # Address registration density
    addr_density_mean: float = 1.3
    addr_density_std: float = 0.8

    # Director portfolio size
    director_roles_mean: float = 1.2
    director_roles_std: float = 1.5
    director_roles_p99: float = 4.0

    # Formation velocity
    formations_per_agent_month_mean: float = 12.0
    formations_per_agent_month_p99: float = 50.0

    # Company lifespan
    company_lifespan_months_median: float = 84.0  # 7 years
```

#### Anomaly Types

| Entity Type | Anomaly Indicators |
|-------------|-------------------|
| **Address** | High registration density, high formation velocity, short company lifespans |
| **Company** | No employees, virtual address, F-skatt without VAT, generic SNI code |
| **Person** | High directorship count, similar company portfolio, age outliers |

#### Usage

```python
detector = AnomalyDetector(graph_client=client)

# Score an address
address_score = await detector.score_address("addr_001")
# Returns: AnomalyScore(composite_score=5.88, flags=["high_registration_density"])

# Score a company
company_score = await detector.score_company("company_001")
# Returns: AnomalyScore with shell company indicators
```

### 4.3 Pattern Detection

**File**: `halo/intelligence/patterns.py`

Cypher-based fraud pattern matching.

#### Built-in Patterns

| Pattern | Description | Severity |
|---------|-------------|----------|
| `registration_mill` | Many companies at same address | High |
| `shell_company_network` | Connected shell companies | High |
| `phoenix_company` | Company reformed after bankruptcy | Critical |
| `nominee_director` | Professional director across many companies | Medium |
| `circular_ownership` | Ownership loops | Critical |
| `rapid_formation` | Many companies formed quickly | Medium |
| `layered_ownership` | Deep ownership structures | High |

#### Pattern Definition

```python
@dataclass
class FraudPattern:
    id: str
    name: str
    description: str
    cypher_query: str
    severity: str  # low, medium, high, critical
    typology: str  # registration_mill, shell_network, etc.
    enabled: bool = True
```

#### Example Pattern Query

```cypher
// Registration Mill Detection
MATCH (a:Address)<-[:REGISTERED_AT]-(c:Company)
WITH a, collect(c) as companies, count(c) as company_count
WHERE company_count > 5
RETURN a.id as address_id,
       [c in companies | c.id] as company_ids,
       company_count
```

### 4.4 Predictive Risk

**File**: `halo/intelligence/predictive.py`

ML-based risk prediction and scoring.

#### Risk Predictor

```python
class RiskPredictor:
    async def predict(self, entity_id: str) -> FraudPrediction:
        """Predict fraud risk for an entity."""

    async def predict_batch(self, entity_ids: list[str]) -> list[FraudPrediction]:
        """Batch prediction for multiple entities."""

    async def explain(self, entity_id: str) -> dict:
        """Explain prediction with contributing factors."""
```

#### Construction Signals

Indicators of potential shell company construction:

- Minimum share capital (25,000 SEK for AB)
- Generic SNI codes (70100 holding, 74909 consulting)
- No employees with revenue
- F-skatt without VAT registration
- Virtual or shared address
- Recent formation with multiple director changes

### 4.5 Konkurs (Bankruptcy) Prediction

**File**: `halo/intelligence/konkurs.py`

Predicts bankruptcy risk with network contagion analysis.

```python
class KonkursPredictor:
    async def predict(
        self,
        company_id: str,
        horizon_months: int = 12
    ) -> KonkursPrediction:
        """Predict bankruptcy probability."""

    async def analyze_contagion(
        self,
        company_id: str
    ) -> ContagionAnalysis:
        """Analyze network contagion if company fails."""
```

#### Risk Factors

- Financial distress indicators
- Director history (previous bankruptcies)
- Network exposure (connected failing companies)
- Industry risk (SNI-based)
- Age and stability metrics

### 4.6 Sequence Detection

**File**: `halo/intelligence/sequence_detector.py`

Detects multi-event fraud sequences over time.

#### Playbook Patterns

```python
FRAUD_PLAYBOOKS = [
    {
        "id": "classic_phoenix",
        "name": "Classic Phoenix Scheme",
        "stages": [
            {"event": "company_registered", "within_days": 0},
            {"event": "director_appointed", "within_days": 30},
            {"event": "invoice_activity", "within_days": 90},
            {"event": "tax_debt_accumulated", "within_days": 180},
            {"event": "company_bankruptcy", "within_days": 365},
            {"event": "new_company_same_director", "within_days": 30}
        ]
    }
]
```

### 4.7 SAR Generation

**File**: `halo/intelligence/sar_generator.py`

Automated Suspicious Activity Report generation.

```python
class SARGenerator:
    async def generate(
        self,
        entity_id: str,
        trigger_reason: str,
        alert_ids: list[str] = None,
        notes: str = None
    ) -> SAR:
        """Generate SAR from entity and alerts."""
```

#### SAR Structure

- Subject identification
- Activity description
- Timeline of suspicious activities
- Supporting evidence
- Risk assessment
- Recommended actions

---

## 5. Graph Database

**Location**: `halo/graph/`

Intelligence graph for entity relationships and network analysis.

### 5.1 Graph Schema

**File**: `halo/graph/schema.py`

#### Node Types

```python
@dataclass
class Person:
    id: str
    personnummer: Optional[str]  # Encrypted
    names: list[dict]            # [{name, source, observed_at}]
    addresses: list[dict]
    dob: Optional[date]
    nationality: Optional[str]
    pep_status: Optional[dict]
    sanctions_matches: list[dict]
    risk_score: float
    flags: list[dict]
    network_metrics: dict

@dataclass
class Company:
    id: str
    orgnr: str                   # Organisationsnummer
    names: list[dict]            # Including särskilda firmor
    legal_form: str              # AB, HB, EF, etc.
    status: dict
    formation: dict
    addresses: list[dict]
    sni_codes: list[dict]
    f_skatt: Optional[dict]
    vat: Optional[dict]
    employees: Optional[dict]
    revenue: Optional[dict]

@dataclass
class Address:
    id: str
    normalized: dict             # {street, city, postal_code}
    type: str                    # residential, commercial, virtual
    registration_count: int
    registration_velocity: float
```

### 5.2 Edge Types

**File**: `halo/graph/edges.py`

| Edge Type | From | To | Attributes |
|-----------|------|-----|------------|
| `DirectsEdge` | Person | Company | role, signing_rights, from_date, to_date |
| `OwnsEdge` | Person/Company | Company | ownership_pct, from_date, to_date |
| `BeneficialOwnerEdge` | Person | Company | ownership_pct, control_type |
| `RegisteredAtEdge` | Company | Address | type, from_date, to_date |
| `LivesAtEdge` | Person | Address | type, from_date, to_date |
| `CoDirectorEdge` | Person | Person | shared_companies, overlap_period |
| `CoRegisteredEdge` | Company | Company | shared_address, overlap_period |
| `TransactsEdge` | Entity | Entity | amount, count, first_date, last_date |

### 5.3 Graph Client

**File**: `halo/graph/client.py`

Dual-backend graph client supporting NetworkX (dev) and Neo4j (production).

#### Backend Architecture

```python
class GraphBackend(Protocol):
    """Abstract graph backend interface."""

    async def create_node(self, node: NodeType) -> str: ...
    async def create_edge(self, edge: EdgeType) -> str: ...
    async def get_node(self, node_id: str, node_type: str) -> Optional[dict]: ...
    async def get_neighbors(self, node_id: str, ...) -> list[dict]: ...
    async def execute(self, query: str, params: dict) -> list[dict]: ...
```

#### Neo4j Backend Features

- Connection pooling (configurable pool size)
- Automatic schema setup (constraints + indexes)
- Transaction support
- Batch operations
- Cypher query execution

#### Schema Setup

```cypher
-- Constraints (unique IDs)
CREATE CONSTRAINT person_id FOR (n:Person) REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT company_id FOR (n:Company) REQUIRE n.id IS UNIQUE
CREATE CONSTRAINT address_id FOR (n:Address) REQUIRE n.id IS UNIQUE

-- Indexes for common lookups
CREATE INDEX company_orgnr FOR (n:Company) ON (n.orgnr)
CREATE INDEX person_personnummer FOR (n:Person) ON (n.personnummer)
CREATE INDEX company_risk_score FOR (n:Company) ON (n.risk_score)
```

#### Client Usage

```python
# Create client with NetworkX (development)
client = create_graph_client("networkx")

# Create client with Neo4j (production)
client = create_graph_client(
    "neo4j",
    uri="bolt://localhost:7687",
    user="neo4j",
    password="secret",
    database="halo"
)

# Add entities
await client.add_company(company)
await client.add_person(person)
await client.add_directorship(edge)

# Query relationships
neighbors = await client.get_neighbors(entity_id, hops=2)
ownership_chain = await client.get_ownership_chain(company_id)

# Graph algorithms (NetworkX only)
centrality = client.compute_centrality()
components = client.find_connected_components()
```

---

## 6. API Layer

**Location**: `halo/api/`

FastAPI REST API with OpenAPI documentation.

### 6.1 Route Modules

| Module | Prefix | Purpose |
|--------|--------|---------|
| `auth.py` | `/v1/auth` | Authentication and sessions |
| `entities.py` | `/entities` | Entity CRUD |
| `alerts.py` | `/alerts` | Alert management |
| `cases.py` | `/cases` | Case management |
| `search.py` | `/search` | Full-text search |
| `documents.py` | `/documents` | Document upload |
| `audit.py` | `/audit` | Audit logs |
| `graph.py` | `/graph` | Graph queries |
| `intelligence.py` | `/intelligence` | Detection endpoints |

### 6.2 Authentication Endpoints

```
POST /v1/auth/login              # Username/password login
POST /v1/auth/logout             # Logout and invalidate session
POST /v1/auth/refresh            # Refresh access token
GET  /v1/auth/me                 # Get current user

# BankID
POST /v1/auth/bankid/init        # Initiate BankID auth
POST /v1/auth/bankid/qr          # Get QR code data
POST /v1/auth/bankid/collect     # Poll for completion
POST /v1/auth/bankid/cancel      # Cancel BankID session

# OIDC
POST /v1/auth/oidc/init          # Start OIDC flow
POST /v1/auth/oidc/callback      # Handle OIDC callback
GET  /v1/auth/oidc/providers     # List OIDC providers
```

### 6.3 Entity Endpoints

```
GET    /entities                      # List entities (paginated)
POST   /entities                      # Create entity
GET    /entities/{id}                 # Get entity by ID
PATCH  /entities/{id}                 # Update entity
GET    /entities/{id}/relationships   # Get entity relationships
POST   /entities/relationships        # Create relationship
GET    /entities/by-personnummer/{pn} # Lookup by personnummer
GET    /entities/by-orgnr/{orgnr}     # Lookup by organisationsnummer
```

### 6.4 Alert Endpoints

```
GET  /alerts                    # List alerts (paginated, filtered)
GET  /alerts/{id}               # Get alert details
POST /alerts/{id}/acknowledge   # Acknowledge Tier 2 alert
POST /alerts/{id}/resolve       # Resolve alert
POST /alerts/{id}/dismiss       # Dismiss alert
POST /alerts/{id}/create-case   # Escalate to case
```

### 6.5 Intelligence Endpoints

```
# Anomaly Detection
GET /intelligence/anomaly/address/{id}  # Score address
GET /intelligence/anomaly/company/{id}  # Score company
GET /intelligence/anomaly/person/{id}   # Score person

# Pattern Detection
GET  /intelligence/patterns              # List patterns
GET  /intelligence/patterns/detect/{id}  # Detect patterns for entity
POST /intelligence/patterns/scan         # Scan all patterns

# Risk Prediction
GET  /intelligence/predict/{id}          # Predict risk
POST /intelligence/predict/batch         # Batch prediction
GET  /intelligence/predict/{id}/explain  # Explain prediction

# SAR Generation
POST /intelligence/sar/generate          # Generate SAR

# Konkurs Prediction
GET /intelligence/konkurs/{id}           # Predict bankruptcy
GET /intelligence/konkurs/{id}/contagion # Contagion analysis

# Evasion Detection
GET /intelligence/evasion/{id}           # Detect evasion

# Playbook Detection
GET /intelligence/playbooks              # List playbooks
GET /intelligence/playbooks/detect/{id}  # Match playbooks

# Network Risk
GET /intelligence/network-risk/{id}      # Network risk analysis
```

### 6.6 Graph Endpoints

```
GET /graph/entities/{id}          # Get entity with metrics
GET /graph/entities/{id}/neighbors # Get neighbors (configurable hops)
GET /graph/entities/{id}/network  # Get network for visualization
GET /graph/metrics/centrality     # Compute centrality metrics
GET /graph/metrics/components     # Find connected components
```

### 6.7 Dependency Injection

**File**: `halo/api/deps.py`

```python
# Type aliases for dependency injection
EntityRepo = Annotated[EntityRepository, Depends(get_entity_repo)]
AlertRepo = Annotated[AlertRepository, Depends(get_alert_repo)]
AuditRepo = Annotated[AuditRepository, Depends(get_audit_repo)]
User = Annotated[CurrentUser, Depends(get_current_user)]
```

---

## 7. User Interface

**Location**: `halo/ui/`

React frontend with TypeScript and Vite.

### 7.1 Page Components

| Page | Route | Purpose |
|------|-------|---------|
| `Dashboard.tsx` | `/` | Overview with stats and recent items |
| `Entities.tsx` | `/entities` | Entity list with search/filter |
| `EntityDetail.tsx` | `/entities/:id` | Entity details with graph |
| `Alerts.tsx` | `/alerts` | Alert list with review status |
| `AlertDetail.tsx` | `/alerts/:id` | Alert review workflow |
| `Cases.tsx` | `/cases` | Investigation cases |
| `CaseDetail.tsx` | `/cases/:id` | Case timeline and evidence |
| `Search.tsx` | `/search` | Advanced search |
| `Login.tsx` | `/login` | Authentication |

### 7.2 Core Components

#### NetworkGraph.tsx

Interactive force-directed graph visualization using D3.js.

```typescript
interface NetworkGraphProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  onNodeClick?: (node: GraphNode) => void
  highlightedNodes?: string[]
  width?: number
  height?: number
}
```

Features:
- Force simulation with collision detection
- Zoom and pan
- Node coloring by risk level
- Edge styling by relationship type
- Click handlers for drill-down

#### RiskIndicator.tsx

Risk level display components.

```typescript
// Risk badge
<RiskIndicator level="high" score={0.85} size="md" />

// Risk progress bar
<RiskProgress score={0.72} label="Fraud Probability" />

// Shell company indicator
<ShellIndicator score={0.65} signals={["no_employees", "virtual_address"]} />
```

#### DetectionResults.tsx

Display components for detection results.

```typescript
// Pattern match card
<PatternMatchCard match={patternMatch} onViewDetails={handleDetails} />

// Anomaly score card
<AnomalyScoreCard score={anomalyScore} />

// Fraud prediction card
<FraudPredictionCard prediction={prediction} onGenerateSAR={handleSAR} />

// Playbook match card
<PlaybookMatchCard match={playbookMatch} />
```

### 7.3 API Client

**File**: `halo/ui/src/services/api.ts`

Axios-based API client with authentication interceptors.

```typescript
// Auth interceptor (adds JWT token)
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor (token refresh)
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401 && !originalRequest._retry) {
      // Attempt token refresh
      const response = await api.post('/v1/auth/refresh', { refresh_token })
      // Retry original request
    }
  }
)
```

#### Service Objects

```typescript
// Entity operations
export const entitiesApi = {
  list: (params) => api.get('/entities', { params }),
  get: (id) => api.get(`/entities/${id}`),
  getRelationships: (id) => api.get(`/entities/${id}/relationships`),
}

// Graph operations
export const graphApi = {
  getEntity: (id, includeMetrics) => api.get(`/graph/entities/${id}`),
  getNeighbors: (id, hops) => api.get(`/graph/entities/${id}/neighbors`),
  getNetwork: (id, hops, maxNodes) => api.get(`/graph/entities/${id}/network`),
}

// Intelligence operations
export const intelligenceApi = {
  scoreAddress: (id) => api.get(`/intelligence/anomaly/address/${id}`),
  predictRisk: (entityId) => api.get(`/intelligence/predict/${entityId}`),
  detectPatterns: (entityId, entityType) => api.get(`/intelligence/patterns/detect/${entityId}`),
  generateSAR: (data) => api.post('/intelligence/sar/generate', data),
}
```

---

## 8. Security & Compliance

**Location**: `halo/security/`

### 8.1 Authentication Methods

| Method | File | Use Case |
|--------|------|----------|
| JWT | `auth.py` | API authentication |
| Sessions | `sessions.py` | Web sessions |
| BankID | `bankid.py` | Swedish citizens |
| OIDC | `oidc.py` | Enterprise SSO |
| SITHS | `siths.py` | Healthcare sector |

### 8.2 Authorization

#### Role-Based Access Control (RBAC)

```python
class UserRole(str, Enum):
    VIEWER = "viewer"           # Read-only access
    ANALYST = "analyst"         # Alert review, basic actions
    SENIOR_ANALYST = "senior"   # Tier 3 approval, case management
    ADMIN = "admin"             # Full system access
    SYSTEM = "system"           # Automated processes
```

#### Case-Level Access Control

```python
class CaseAccessLevel(str, Enum):
    READ = "read"       # View case
    WRITE = "write"     # Edit case
    OWNER = "owner"     # Full control
```

### 8.3 Encryption

**File**: `halo/security/encryption.py`

#### PII Field Encryption

```python
class EncryptedField(TypeDecorator):
    """SQLAlchemy type for encrypted PII fields."""

    impl = Text

    def process_bind_param(self, value, dialect):
        if value:
            return fernet.encrypt(value.encode()).decode()
        return value

    def process_result_value(self, value, dialect):
        if value:
            return fernet.decrypt(value.encode()).decode()
        return value
```

Encrypted fields:
- `personnummer`
- `organisationsnummer`
- `account_number`
- `email` (optional)

#### Blind Indexing

HMAC-based searchable encryption for sensitive lookups.

```python
def create_blind_index(value: str, salt: str) -> str:
    """Create searchable hash of sensitive value."""
    return hmac.new(
        settings.BLIND_INDEX_KEY.encode(),
        f"{salt}:{value}".encode(),
        hashlib.sha256
    ).hexdigest()
```

### 8.4 Middleware Stack

**File**: `halo/security/middleware.py`

```python
SECURITY_MIDDLEWARE = [
    RequestSizeLimitMiddleware(max_size=10_000_000),  # 10MB
    SecurityHeadersMiddleware(),
    RequestLoggingMiddleware(),
    RateLimitMiddleware(),
    SanitizationMiddleware(),
    CSRFMiddleware(),
]
```

#### Security Headers

```python
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; ...",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}
```

### 8.5 Compliance Features

#### Brottsdatalagen (Criminal Data Act)

- Three-tier alert system with human review
- Audit logging of all data access
- Export restrictions on unreviewed data

#### Säkerhetsskyddslagen (Security Protection Act)

- Need-to-know case access control
- Time-limited access grants
- Access revocation on role change

#### GDPR

- PII encryption at rest
- Data minimization in responses
- Audit trail for data subject access
- Right to erasure support

### 8.6 Account Security

**File**: `halo/security/lockout.py`

```python
LOCKOUT_CONFIG = {
    "max_failed_attempts": 5,
    "lockout_duration_minutes": 30,
    "reset_after_minutes": 60,
}
```

---

## 9. Database Schema

**Location**: `halo/db/`

### 9.1 Core Tables

#### Users and Sessions

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255),
    password_hash VARCHAR(255) NOT NULL,  -- Argon2id
    role user_role NOT NULL DEFAULT 'viewer',
    totp_secret VARCHAR(255),             -- MFA
    is_active BOOLEAN DEFAULT TRUE,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE user_sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    token_hash VARCHAR(255) NOT NULL,
    device_fingerprint VARCHAR(255),
    ip_address VARCHAR(45),
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Entities

```sql
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    entity_type entity_type NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    personnummer_encrypted TEXT,          -- Encrypted
    personnummer_blind_index VARCHAR(64), -- Searchable hash
    organisationsnummer_encrypted TEXT,   -- Encrypted
    organisationsnummer_blind_index VARCHAR(64),
    attributes JSONB DEFAULT '{}',
    sources TEXT[] DEFAULT '{}',
    risk_score FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE entity_relationships (
    id UUID PRIMARY KEY,
    from_entity_id UUID REFERENCES entities(id),
    to_entity_id UUID REFERENCES entities(id),
    relationship_type relationship_type NOT NULL,
    source VARCHAR(255) NOT NULL,
    attributes JSONB DEFAULT '{}',
    confidence FLOAT DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Alerts

```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    alert_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL,        -- low, medium, high, critical
    tier INTEGER NOT NULL DEFAULT 1,      -- 1, 2, or 3
    entity_id UUID REFERENCES entities(id),
    description TEXT,
    confidence FLOAT,
    evidence JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'open',    -- open, acknowledged, resolved, dismissed
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMP,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Audit Log

```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    user_name VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,          -- view, create, update, delete, export
    resource_type VARCHAR(50) NOT NULL,
    resource_id UUID,
    details JSONB DEFAULT '{}',
    entry_hash VARCHAR(64) NOT NULL,      -- HMAC of entry
    previous_hash VARCHAR(64),            -- Link to previous
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Cases

```sql
CREATE TABLE cases (
    id UUID PRIMARY KEY,
    case_number VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    case_type case_type NOT NULL,
    status case_status DEFAULT 'draft',
    priority case_priority DEFAULT 'medium',
    entity_ids UUID[] DEFAULT '{}',
    alert_ids UUID[] DEFAULT '{}',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE TABLE case_assignments (
    id UUID PRIMARY KEY,
    case_id UUID REFERENCES cases(id),
    user_id UUID REFERENCES users(id),
    access_level case_access_level NOT NULL,
    assigned_by UUID REFERENCES users(id),
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 9.2 Indexes

```sql
-- Entity lookups
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_pn_blind ON entities(personnummer_blind_index);
CREATE INDEX idx_entities_orgnr_blind ON entities(organisationsnummer_blind_index);
CREATE INDEX idx_entities_risk ON entities(risk_score DESC);

-- Alert queries
CREATE INDEX idx_alerts_status_tier ON alerts(status, tier);
CREATE INDEX idx_alerts_entity ON alerts(entity_id);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- Audit queries
CREATE INDEX idx_audit_user ON audit_log(user_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_hash ON audit_log(entry_hash);

-- Case queries
CREATE INDEX idx_cases_status ON cases(status);
CREATE INDEX idx_case_assignments_user ON case_assignments(user_id, access_level);
```

---

## 10. Component Interactions

### 10.1 Data Flow: Ingestion to Alert

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  External   │────▶│  Adapter    │────▶│  Entity     │
│  Source     │     │  (Ingest)   │     │  Resolution │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Alert      │◀────│  Detection  │◀────│  Graph      │
│  System     │     │  Engine     │     │  Database   │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Human      │────▶│  Case       │────▶│  SAR        │
│  Review     │     │  Management │     │  Export     │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 10.2 Authentication Flow

```
┌─────────┐  1. Login Request   ┌─────────┐
│  User   │────────────────────▶│  Auth   │
└─────────┘                     │  API    │
     ▲                          └────┬────┘
     │                               │
     │  5. JWT Token                 │ 2. Validate
     │                               ▼
     │                          ┌─────────┐
     │                          │  Auth   │
     │                          │Provider │
     │                          │(BankID/ │
     │                          │ OIDC)   │
     │                          └────┬────┘
     │                               │
     │                               │ 3. Identity
     │                               ▼
     │                          ┌─────────┐
     │                          │ Session │
     └──────────────────────────│ Manager │
                4. Create       └─────────┘
                Session
```

### 10.3 Alert Review Flow

```
Detection → Alert Created (Tier 1/2/3)
                   │
                   ├── Tier 1: Auto-logged
                   │
                   ├── Tier 2: Analyst acknowledges
                   │              │
                   │              └── Acknowledged → Reviewable
                   │
                   └── Tier 3: Senior analyst approves
                                  │
                                  ├── Approved → Exportable
                                  │
                                  └── Rejected → Archived
```

### 10.4 Graph Query Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐
│  API     │───▶│  Graph   │───▶│  Neo4j   │
│  Request │    │  Client  │    │  Backend │
└──────────┘    └──────────┘    └──────────┘
                     │
                     │ (or)
                     ▼
               ┌──────────┐
               │ NetworkX │
               │ Backend  │
               │  (Dev)   │
               └──────────┘
```

### 10.5 Intelligence Pipeline

```
Entity ID
    │
    ▼
┌────────────────────────────────────────────┐
│            LAYER 1: ANOMALY                 │
│  ┌─────────────┐                           │
│  │ Score Entity│──▶ Z-scores, Flags        │
│  └─────────────┘                           │
└────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────┐
│            LAYER 2: PATTERNS               │
│  ┌─────────────┐                           │
│  │ Match Cypher│──▶ Pattern Matches        │
│  │   Queries   │                           │
│  └─────────────┘                           │
└────────────────────────────────────────────┘
    │
    ▼
┌────────────────────────────────────────────┐
│            LAYER 3: PREDICTIVE             │
│  ┌─────────────┐                           │
│  │ ML Scoring  │──▶ Risk Prediction        │
│  └─────────────┘                           │
└────────────────────────────────────────────┘
    │
    ▼
Combined Detection Results
    │
    ├──▶ High Risk? ──▶ Generate Alert
    │
    └──▶ Critical? ──▶ Auto-escalate to Case
```

---

## Appendix A: Directory Structure

```
halo/
├── anomaly/                 # Transaction anomaly detection
│   ├── rules_engine.py
│   ├── scorer.py
│   └── transaction_patterns.py
├── api/                     # FastAPI REST API
│   ├── deps.py              # Dependency injection
│   └── routes/
│       ├── alerts.py
│       ├── audit.py
│       ├── auth.py
│       ├── cases.py
│       ├── documents.py
│       ├── entities.py
│       ├── graph.py
│       ├── intelligence.py
│       └── search.py
├── db/                      # Database layer
│   ├── models.py            # SQLAlchemy models
│   ├── repositories.py      # Data access
│   ├── types.py             # Custom types
│   └── migrations/
│       └── versions/
├── entities/                # Entity management
│   ├── graph.py
│   ├── models.py
│   ├── organisationsnummer.py
│   ├── relationships.py
│   ├── resolution.py
│   └── swedish_personnummer.py
├── fincrime/                # AML/Financial crime
│   ├── aml_patterns.py
│   ├── risk_scoring.py
│   ├── sar_generator.py
│   └── watchlist.py
├── graph/                   # Intelligence graph
│   ├── client.py            # Graph client
│   ├── edges.py             # Edge types
│   └── schema.py            # Node schemas
├── ingestion/               # Data adapters
│   ├── bank_transactions.py
│   ├── base_adapter.py
│   ├── bolagsverket_hvd.py
│   ├── document_upload.py
│   ├── graph_loader.py
│   ├── lantmateriet.py
│   ├── polisen_incidents.py
│   ├── rate_limiter.py
│   ├── scb_foretag.py
│   └── scb_pxweb.py
├── intelligence/            # Detection engine
│   ├── anomaly.py
│   ├── evasion.py
│   ├── formation_agent.py
│   ├── konkurs.py
│   ├── patterns.py
│   ├── predictive.py
│   ├── sar_generator.py
│   └── sequence_detector.py
├── investigation/           # Case management
│   ├── case_manager.py
│   ├── evidence.py
│   ├── timeline.py
│   └── workflow.py
├── nlp/                     # NLP pipeline
│   ├── models/
│   ├── ner.py
│   ├── pipeline.py
│   ├── sentiment.py
│   ├── threat_vocab.py
│   └── tokenizer.py
├── personal/                # Personal data
│   └── adapters/
│       ├── aggregator.py
│       ├── property.py
│       └── spar.py
├── review/                  # QA workflows
│   ├── stats.py
│   ├── validation.py
│   └── workflow.py
├── security/                # Security layer
│   ├── access.py
│   ├── auth.py
│   ├── bankid.py
│   ├── csrf.py
│   ├── encryption.py
│   ├── lockout.py
│   ├── middleware.py
│   ├── oidc.py
│   ├── ratelimit.py
│   ├── sessions.py
│   └── siths.py
├── tests/                   # Test suite
│   └── test_*.py
└── ui/                      # React frontend
    ├── src/
    │   ├── components/
    │   │   ├── DetectionResults.tsx
    │   │   ├── Layout.tsx
    │   │   ├── NetworkGraph.tsx
    │   │   └── RiskIndicator.tsx
    │   ├── pages/
    │   │   ├── Alerts.tsx
    │   │   ├── Cases.tsx
    │   │   ├── Dashboard.tsx
    │   │   ├── Entities.tsx
    │   │   └── Search.tsx
    │   ├── services/
    │   │   └── api.ts
    │   ├── App.tsx
    │   └── main.tsx
    ├── package.json
    ├── tailwind.config.js
    └── vite.config.ts
```

---

## Appendix B: Test Coverage

| Module | Test File | Tests |
|--------|-----------|-------|
| API | `test_api.py` | 25 |
| Ingestion | `test_ingestion.py` | 20 |
| Graph Schema | `test_graph_schema.py` | 18 |
| Graph Edges | `test_graph_edges.py` | 15 |
| Graph Client | `test_graph_client.py` | 22 |
| Anomaly | `test_intelligence_anomaly.py` | 20 |
| Patterns | `test_intelligence_patterns.py` | 18 |
| Predictive | `test_intelligence_predictive.py` | 17 |
| Sequence | `test_intelligence_sequence.py` | 12 |
| Evasion | `test_intelligence_evasion.py` | 10 |
| SAR | `test_intelligence_sar.py` | 12 |
| Konkurs | `test_intelligence_konkurs.py` | 15 |
| AML Patterns | `test_aml_patterns.py` | 18 |
| Risk Scoring | `test_risk_scoring.py` | 15 |
| Watchlist | `test_watchlist.py` | 14 |
| Investigation | `test_investigation.py` | 15 |
| **Total** | | **256** |

---

*Document generated: December 2024*
