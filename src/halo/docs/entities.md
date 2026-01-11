# Halo Entity Resolution Documentation

## Overview

The Halo entity resolution module provides comprehensive Swedish entity management:

- **Swedish ID Validation** - Validate and parse personnummer and organisationsnummer
- **Entity Resolution** - Match and deduplicate entities using exact and fuzzy matching
- **Relationship Extraction** - Extract relationships from structured data and text
- **Graph Analysis** - Navigate and analyze entity relationship networks

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Entity Resolution Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Raw Data (Bolagsverket, SCB, Documents)                       │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────────────────────┐                              │
│   │  ID Validation               │  Validate Swedish IDs        │
│   │ - Personnummer (Luhn)        │  - Format normalization      │
│   │ - Organisationsnummer        │  - Checksum verification     │
│   │ - Coordination numbers       │  - Type detection            │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │    EntityResolver            │  Match to existing entities  │
│   │ - Exact ID matching          │  - Deduplication             │
│   │ - Fuzzy name matching        │  - Confidence scoring        │
│   │ - Swedish name normalization │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │  RelationshipExtractor       │  Extract relationships       │
│   │ - Bolagsverket (boards)      │  - NLP from text            │
│   │ - Ownership structures       │  - Transaction patterns      │
│   │ - Address co-location        │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │       EntityGraph            │  Graph operations            │
│   │ - Path finding               │  - Network analysis          │
│   │ - Subgraph extraction        │  - Cluster detection         │
│   │ - Common connections         │                              │
│   └──────────────────────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Swedish ID Validation

### Personnummer

Swedish personal identity numbers with Luhn checksum validation.

```python
from halo.entities import validate_personnummer, format_personnummer

# Validate a personnummer
info = validate_personnummer("198012151234")

print(f"Valid: {info.is_valid}")
print(f"Normalized: {info.normalized}")  # YYYYMMDDXXXX
print(f"Birth date: {info.birth_date}")
print(f"Gender: {info.gender}")  # 'M' or 'F'
print(f"Coordination number: {info.is_coordination}")

# Format for display
formatted = format_personnummer("198012151234")  # "19801215-1234"
```

#### Supported Formats

| Format | Example | Notes |
|--------|---------|-------|
| `YYMMDD-XXXX` | `801215-1234` | Standard short format |
| `YYMMDDXXXX` | `8012151234` | Without separator |
| `YYYYMMDD-XXXX` | `19801215-1234` | Full format |
| `YYYYMMDDXXXX` | `198012151234` | Full without separator |
| `YYMMDD+XXXX` | `201215+1234` | Person over 100 years old |

#### PersonnummerInfo Object

```python
@dataclass
class PersonnummerInfo:
    normalized: str      # 12-digit format: YYYYMMDDXXXX
    birth_date: date     # Extracted birth date
    gender: str          # 'M' or 'F'
    is_coordination: bool # True if samordningsnummer
    is_valid: bool       # Validation result
```

#### Coordination Numbers (Samordningsnummer)

Coordination numbers add 60 to the day component:

```python
# Born December 15 -> Day becomes 75
info = validate_personnummer("19801275-1234")
print(info.is_coordination)  # True
print(info.birth_date)       # 1980-12-15
```

#### Luhn Algorithm

The 10th digit is a Luhn checksum calculated on digits 3-11:

```python
def luhn_checksum(digits: str) -> int:
    """
    1. Double every second digit from the right
    2. If doubling results in > 9, subtract 9
    3. Sum all digits
    4. Checksum is (10 - (sum % 10)) % 10
    """
```

---

### Organisationsnummer

Swedish organization numbers with type detection.

```python
from halo.entities import validate_organisationsnummer, format_organisationsnummer

# Validate an organisationsnummer
info = validate_organisationsnummer("5561234567")

print(f"Valid: {info.is_valid}")
print(f"Normalized: {info.normalized}")
print(f"Type: {info.organization_type}")
print(f"Type code: {info.organization_type_code}")

# Format for display
formatted = format_organisationsnummer("5561234567")  # "556123-4567"

# With 16 prefix (Swedish Tax Authority format)
formatted_16 = format_with_prefix("5561234567")  # "16556123-4567"
```

#### Organization Types

| Code | Type | Description |
|------|------|-------------|
| 1 | Dödsbo | Estate of deceased person |
| 2 | Stat, landsting, kommun | Government entity |
| 5 | Handelsbolag, kommanditbolag | Partnership |
| 6 | Kommanditbolag | Limited partnership |
| 7 | Ekonomisk förening, stiftelse | Foundation/Association |
| 8 | Ideell förening, stiftelse | Non-profit/Foundation |
| 9 | Utländskt företag | Foreign company |

#### Aktiebolag Detection

```python
from halo.entities import is_aktiebolag

# Check if org number is an Aktiebolag (AB)
is_ab = is_aktiebolag("5561234567")  # True if starts with 5, group 56-99
```

#### Format Rules

- 10 digits total
- Digits 3-4 must be >= 20 (distinguishes from personnummer)
- Last digit is Luhn checksum
- May include `16` prefix (stripped automatically)

---

## Entity Resolution

### EntityResolver

Main entry point for matching entities against existing records.

```python
from halo.entities import EntityResolver

resolver = EntityResolver(
    exact_match_threshold=1.0,    # Score for exact ID matches
    fuzzy_match_threshold=0.85,   # Minimum for fuzzy matches
    low_confidence_threshold=0.50, # Minimum for review
)

# Resolve an entity
result = resolver.resolve(
    entity_type="person",
    display_name="Johan Andersson",
    personnummer="19801215-1234",
    existing_entities=existing_list,
)

print(f"Match type: {result.match_type}")   # 'exact_id', 'fuzzy_name', 'no_match'
print(f"Score: {result.match_score}")
print(f"Entity ID: {result.entity_id}")
print(f"Is match: {result.is_match}")
```

#### MatchResult Object

```python
@dataclass
class MatchResult:
    entity_id: Optional[UUID]   # Matched entity ID (None if no match)
    match_score: float          # 0.0 to 1.0
    match_type: str             # Type of match
    matched_fields: list[str]   # Which fields matched

    @property
    def is_match(self) -> bool:
        return self.match_score >= 0.85
```

#### Match Types

| Type | Score | Description |
|------|-------|-------------|
| `exact_id` | 1.0 | Personnummer or organisationsnummer match |
| `exact_name` | 0.99+ | Exact name after normalization |
| `fuzzy_name` | 0.85-0.99 | Fuzzy name similarity |
| `no_match` | 0.0 | No match found |

---

### SwedishNameMatcher

Fuzzy matching for Swedish names with normalization.

```python
from halo.entities import SwedishNameMatcher

matcher = SwedishNameMatcher()

# Person name matching
score = matcher.match_person_names("Kalle Andersson", "Karl Andersson")
# Returns high score because "Kalle" is a nickname for "Karl"

# Company name matching
score = matcher.match_company_names("IKEA AB", "Ikea Aktiebolag")
# Returns 1.0 - identical after normalization
```

#### Swedish Character Normalization

```python
# Characters normalized for comparison
replacements = {
    "å": "a",
    "ä": "a",
    "ö": "o",
    "é": "e",
    "ü": "u",
}
```

#### Nickname Mappings

```python
# Common Swedish nicknames mapped to formal names
NICKNAME_MAP = {
    "kalle": "karl",
    "pelle": "per",
    "nansen": "göran",
    "benansen": "bengt",
    "oansen": "ola",
    "sansen": "sven",
}
```

#### Company Suffix Normalization

```python
# Suffixes removed for comparison
COMPANY_SUFFIXES = [
    " aktiebolag", " ab",
    " handelsbolag", " hb",
    " kommanditbolag", " kb",
    " ek. för.", " ekonomisk förening",
]
```

---

## Relationship Extraction

### StructuredRelationshipExtractor

Extract relationships from structured data sources.

```python
from halo.entities import StructuredRelationshipExtractor

extractor = StructuredRelationshipExtractor()

# From Bolagsverket company data
relationships = extractor.extract_from_bolagsverket(
    company_data=bolagsverket_response,
    company_entity_id=company_uuid,
)

# From address co-location
entities_at_address = [
    (uuid1, "company", "IKEA AB"),
    (uuid2, "person", "Johan Andersson"),
]
relationships = extractor.extract_address_colocation(entities_at_address)
```

#### Extracted Relationship Types (Bolagsverket)

| Relationship | Source Field | Description |
|--------------|--------------|-------------|
| `BOARD_MEMBER` | styrelse | Board member |
| `BOARD_CHAIR` | styrelse (ordförande) | Board chairman |
| `BOARD_DEPUTY` | styrelse (suppleant) | Deputy board member |
| `CEO` | styrelse (VD) | CEO/Managing Director |
| `OWNS` | ägare | Ownership stake |
| `SIGNATORY` | firmatecknare | Signatory rights |
| `AUDITOR` | revisor | Company auditor |

#### ExtractedRelationship Object

```python
@dataclass
class ExtractedRelationship:
    from_entity_id: Optional[UUID]
    to_entity_id: Optional[UUID]
    relationship_type: RelationshipType
    confidence: float
    source: RelationshipSource

    # For unresolved entities
    from_entity_ref: Optional[str]  # Personnummer/name
    to_entity_ref: Optional[str]    # Orgnummer/name

    attributes: dict
    evidence: str
    extracted_at: datetime
```

---

### NLPRelationshipExtractor

Extract relationships from unstructured Swedish text.

```python
from halo.entities import NLPRelationshipExtractor

extractor = NLPRelationshipExtractor()

text = "Johan Andersson är VD för IKEA AB sedan 2020."
relationships = extractor.extract_from_text(
    text=text,
    source_document_id=document_uuid,
)

for rel in relationships:
    print(f"{rel.from_entity_ref} -> {rel.to_entity_ref}")
    print(f"Type: {rel.relationship_type}, Confidence: {rel.confidence}")
```

#### Swedish Patterns Detected

| Relationship | Pattern Examples |
|--------------|------------------|
| CEO | "X är VD för Y", "VD:n X på Y" |
| BOARD_CHAIR | "X är ordförande i Y" |
| OWNS | "X äger Y", "X har förvärvat Y" |
| EMPLOYED_BY | "X arbetar på Y", "X är anställd hos Y" |
| ASSOCIATED | "X och Y samarbetar", "koppling mellan X och Y" |
| TRANSACTED_WITH | "X betalade till Y", "transaktion från X till Y" |
| FAMILY | "X är gift med Y", "X och Y är syskon" |

#### Confidence Scoring

```python
# NLP extraction confidence factors:
# - Longer entity names: +0.1 per entity > 10 chars
# - Multiple words (likely real name): +0.1 per entity
# - Maximum NLP confidence: 0.85 (always requires verification)
```

---

### TransactionRelationshipExtractor

Extract relationships from transaction patterns.

```python
from halo.entities import TransactionRelationshipExtractor

extractor = TransactionRelationshipExtractor(
    min_transactions=3,        # Minimum transactions for relationship
    min_total_amount=10000,    # Minimum SEK total
)

relationships = extractor.extract_from_transactions(transactions)
```

#### Confidence Formula

```python
confidence = min(
    0.9,
    0.5 + (transaction_count / 20) * 0.2 + (total_amount / 1000000) * 0.2
)
```

---

### RelationshipExtractor

Orchestrates all extraction methods.

```python
from halo.entities import RelationshipExtractor

extractor = RelationshipExtractor()

all_relationships = extractor.extract_all(
    company_data=[bolagsverket_data],
    texts=[(text_content, doc_id)],
    transactions=transaction_list,
    address_groups=[entities_at_same_address],
)
```

---

## Entity Graph

### EntityGraph

Graph operations on entity relationships.

```python
from halo.entities import EntityGraph

graph = EntityGraph(session=db_session)

# Get neighbors
neighbors = await graph.get_neighbors(
    entity_id=uuid,
    relationship_types=[RelationshipType.OWNS, RelationshipType.BOARD_MEMBER],
    direction="both",  # 'outgoing', 'incoming', 'both'
)

# Find path between entities
path = await graph.find_path(
    from_entity_id=entity_a,
    to_entity_id=entity_b,
    max_depth=4,
)

if path:
    print(f"Path length: {path.length}")
    print(f"Confidence: {path.total_confidence}")
```

#### GraphPath Object

```python
@dataclass
class GraphPath:
    nodes: list[UUID]        # Entity IDs in path
    edges: list[UUID]        # Relationship IDs
    total_confidence: float  # Product of edge confidences

    @property
    def length(self) -> int:
        return len(self.edges)
```

---

### Subgraph Extraction

Extract a network around an entity for investigation.

```python
subgraph = await graph.extract_subgraph(
    center_entity_id=target_uuid,
    depth=2,                # Hops from center
    max_nodes=100,          # Maximum nodes
    relationship_types=None, # All types
)

print(f"Nodes: {subgraph.node_count}")
print(f"Edges: {subgraph.edge_count}")

# Convert to NetworkX for advanced analysis
import networkx as nx
G = graph.to_networkx(subgraph)
```

#### Subgraph Object

```python
@dataclass
class Subgraph:
    nodes: dict[UUID, GraphNode]
    edges: list[GraphEdge]
    center_entity_id: Optional[UUID]

    @property
    def node_count(self) -> int: ...
    @property
    def edge_count(self) -> int: ...
```

---

### Network Analysis

```python
# Degree centrality (connectedness)
centrality = await graph.compute_degree_centrality(entity_ids)
for entity_id, score in centrality.items():
    print(f"{entity_id}: {score:.2f}")

# Find common connections between two entities
common = await graph.find_common_connections(entity_a, entity_b)
for entity in common:
    print(f"Common connection: {entity.display_name}")

# Detect clusters of connected entities
clusters = await graph.detect_clusters(
    min_cluster_size=3,
    relationship_types=None,
)
for i, cluster in enumerate(clusters):
    print(f"Cluster {i}: {len(cluster)} entities")
```

---

## Entity Models

### Pydantic Models

```python
from halo.entities import Entity, EntityCreate, EntityUpdate

# Create a new entity
new_entity = EntityCreate(
    entity_type="person",
    display_name="Johan Andersson",
    personnummer="19801215-1234",
    attributes={
        "first_name": "Johan",
        "last_name": "Andersson",
        "address": "Storgatan 1",
    },
    sources=["bolagsverket"],
)

# Full entity with ID
entity = Entity(
    id=uuid,
    entity_type="person",
    display_name="Johan Andersson",
    personnummer="19801215-1234",
    attributes={...},
    created_at=datetime.utcnow(),
    updated_at=datetime.utcnow(),
)
```

#### Entity Types

| Type | Primary ID | Description |
|------|------------|-------------|
| `person` | personnummer | Individual person |
| `company` | organisationsnummer | Company/organization |
| `property` | fastighetsbeteckning | Real estate |
| `vehicle` | registration_number | Vehicle |

#### Attribute Models

```python
# Person-specific attributes
class PersonAttributes(BaseModel):
    first_name: Optional[str]
    last_name: Optional[str]
    birth_date: Optional[date]
    gender: Optional[str]
    address: Optional[str]
    city: Optional[str]
    postal_code: Optional[str]
    country: str = "SE"
    is_coordination_number: bool = False

# Company-specific attributes
class CompanyAttributes(BaseModel):
    legal_name: str
    trade_name: Optional[str]
    legal_form: Optional[str]  # AB, HB, KB
    status: Optional[str]      # Aktivt, Avregistrerat
    registration_date: Optional[date]
    share_capital: Optional[float]
    sni_codes: list[str] = []
    employee_count: Optional[int]
```

---

## Relationship Types

```python
class RelationshipType(str, Enum):
    # Corporate relationships
    BOARD_MEMBER = "board_member"
    BOARD_CHAIR = "board_chair"
    BOARD_DEPUTY = "board_deputy"
    CEO = "ceo"
    OWNS = "owns"
    SIGNATORY = "signatory"
    AUDITOR = "auditor"
    EMPLOYED_BY = "employed_by"

    # Personal relationships
    FAMILY = "family"
    SPOUSE = "spouse"
    PARENT = "parent"
    CHILD = "child"
    SIBLING = "sibling"

    # Business relationships
    TRANSACTED_WITH = "transacted_with"
    ASSOCIATED = "associated"
    COLOCATED = "colocated"

    # Property relationships
    OWNS_PROPERTY = "owns_property"
    RESIDES_AT = "resides_at"
```

---

## Usage Examples

### Full Entity Resolution Pipeline

```python
from halo.entities import (
    validate_personnummer,
    validate_organisationsnummer,
    EntityResolver,
    RelationshipExtractor,
    EntityGraph,
)

async def process_new_data(raw_data: dict, db_session):
    # 1. Validate Swedish IDs
    if "personnummer" in raw_data:
        pnr_info = validate_personnummer(raw_data["personnummer"])
        if not pnr_info.is_valid:
            raise ValueError(f"Invalid personnummer")
        raw_data["personnummer"] = pnr_info.normalized

    if "organisationsnummer" in raw_data:
        org_info = validate_organisationsnummer(raw_data["organisationsnummer"])
        if not org_info.is_valid:
            raise ValueError(f"Invalid organisationsnummer")
        raw_data["organisationsnummer"] = org_info.normalized

    # 2. Resolve against existing entities
    resolver = EntityResolver()
    existing_entities = await load_existing_entities(db_session)

    result = resolver.resolve(
        entity_type=raw_data["entity_type"],
        display_name=raw_data["name"],
        personnummer=raw_data.get("personnummer"),
        organisationsnummer=raw_data.get("organisationsnummer"),
        existing_entities=existing_entities,
    )

    if result.is_match:
        # Update existing entity
        entity_id = result.entity_id
        await update_entity(db_session, entity_id, raw_data)
    else:
        # Create new entity
        entity_id = await create_entity(db_session, raw_data)

    # 3. Extract relationships
    extractor = RelationshipExtractor()
    relationships = extractor.extract_all(
        company_data=[raw_data] if raw_data["entity_type"] == "company" else None,
    )

    # Save relationships
    for rel in relationships:
        await save_relationship(db_session, rel)

    return entity_id
```

### Investigation Subgraph

```python
async def investigate_entity(entity_id: UUID, db_session):
    graph = EntityGraph(session=db_session)

    # Extract 2-hop network
    subgraph = await graph.extract_subgraph(
        center_entity_id=entity_id,
        depth=2,
        max_nodes=50,
    )

    # Analyze centrality
    centrality = await graph.compute_degree_centrality(
        list(subgraph.nodes.keys())
    )

    # Find clusters
    clusters = await graph.detect_clusters(min_cluster_size=3)

    # Export to NetworkX for visualization
    G = graph.to_networkx(subgraph)

    return {
        "subgraph": subgraph,
        "centrality": centrality,
        "clusters": clusters,
        "networkx_graph": G,
    }
```

### Batch Entity Matching

```python
async def match_batch(records: list[dict], db_session):
    resolver = EntityResolver()
    existing_entities = await load_existing_entities(db_session)

    results = []
    for record in records:
        result = resolver.resolve(
            entity_type=record["type"],
            display_name=record["name"],
            personnummer=record.get("personnummer"),
            organisationsnummer=record.get("orgnr"),
            existing_entities=existing_entities,
        )

        results.append({
            "input": record,
            "match_type": result.match_type,
            "match_score": result.match_score,
            "entity_id": result.entity_id,
            "needs_review": not result.is_match and result.match_score > 0.5,
        })

    return results
```

---

## Configuration

### Environment Variables

```bash
# Entity resolution thresholds
ENTITY_EXACT_MATCH_THRESHOLD=1.0
ENTITY_FUZZY_MATCH_THRESHOLD=0.85
ENTITY_LOW_CONFIDENCE_THRESHOLD=0.50

# Graph analysis
GRAPH_MAX_PATH_DEPTH=4
GRAPH_MAX_SUBGRAPH_NODES=100
GRAPH_MIN_CLUSTER_SIZE=3

# Relationship extraction
RELATIONSHIP_MIN_TRANSACTIONS=3
RELATIONSHIP_MIN_AMOUNT=10000
```

### EntityResolver Configuration

```python
resolver = EntityResolver(
    exact_match_threshold=1.0,     # Score for exact ID matches
    fuzzy_match_threshold=0.85,    # Minimum for automatic match
    low_confidence_threshold=0.50, # Minimum to flag for review
)
```
