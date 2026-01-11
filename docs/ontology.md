# Archeron Ontology Architecture v2

## Overview

This document defines the ontology layer for Archeron's intelligence platform, starting from Halo's organized crime intelligence needs. All design decisions have been finalized for implementation.

---

## Design Principles

1. **Entity-Fact model**: Flexible enough for cross-domain intelligence, queryable enough for real-time operations
2. **Non-destructive operations**: Merges create same-as links, splits preserve originals, deletions anonymize
3. **Full provenance**: Every fact traces to source, extraction method, timestamp, and system version
4. **Day-level temporality**: All facts have valid_from/valid_to at day granularity
5. **Conservative accuracy**: >99.5% specificity, >90% sensitivity, 0.95 auto-match threshold

---

## Performance Targets

| Operation | Target |
|-----------|--------|
| Single entity lookup | <100ms |
| 2-hop graph traversal | <1s |
| Pattern matching (full graph) | <10s |
| Entity resolution batch | <1hr for 10K mentions |
| Nightly derived fact recomputation | <4hr |

---

## Core Data Model

### Entity

```sql
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL CHECK (entity_type IN ('PERSON', 'COMPANY', 'ADDRESS')),
    canonical_name TEXT NOT NULL,
    resolution_confidence FLOAT NOT NULL DEFAULT 1.0 CHECK (resolution_confidence BETWEEN 0 AND 1),
    
    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'MERGED', 'SPLIT', 'ANONYMIZED')),
    merged_into UUID REFERENCES entities(id),  -- For MERGED status
    split_from UUID REFERENCES entities(id),   -- For SPLIT status
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    anonymized_at TIMESTAMPTZ  -- For GDPR erasure
);

CREATE INDEX idx_entities_type ON entities(entity_type) WHERE status = 'ACTIVE';
CREATE INDEX idx_entities_merged ON entities(merged_into) WHERE merged_into IS NOT NULL;
```

### Entity Identifiers

Separated table for multiple identifiers per entity:

```sql
CREATE TABLE entity_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entities(id),
    identifier_type VARCHAR(30) NOT NULL CHECK (identifier_type IN (
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

CREATE INDEX idx_identifiers_lookup ON entity_identifiers(identifier_type, identifier_value);
CREATE INDEX idx_identifiers_entity ON entity_identifiers(entity_id);
```

### Person Entity Attributes

```sql
CREATE TABLE person_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id),
    
    -- Extracted/derived attributes
    birth_year INT,
    birth_date DATE,
    gender VARCHAR(10),
    
    -- Cached computations (updated nightly)
    company_count INT NOT NULL DEFAULT 0,
    active_directorship_count INT NOT NULL DEFAULT 0,
    network_cluster_id UUID,
    risk_score FLOAT NOT NULL DEFAULT 0.0 CHECK (risk_score BETWEEN 0 AND 1),
    risk_factors TEXT[],
    
    -- Activity tracking
    first_seen DATE NOT NULL,
    last_activity DATE NOT NULL,
    
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Company Entity Attributes

```sql
CREATE TABLE company_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id),
    
    -- Core info
    legal_form VARCHAR(20),  -- AB, HB, KB, EF, etc.
    status VARCHAR(30) NOT NULL,  -- ACTIVE, LIQUIDATION, DISSOLVED, BANKRUPTCY
    registration_date DATE,
    dissolution_date DATE,
    
    -- Industry
    sni_codes TEXT[],
    sni_primary VARCHAR(10),
    
    -- Financials (from annual reports)
    latest_revenue BIGINT,
    latest_employees INT,
    latest_assets BIGINT,
    financial_year_end DATE,
    
    -- Cached computations (updated nightly)
    director_count INT NOT NULL DEFAULT 0,
    director_change_velocity FLOAT NOT NULL DEFAULT 0.0,  -- Changes per year
    network_cluster_id UUID,
    risk_score FLOAT NOT NULL DEFAULT 0.0 CHECK (risk_score BETWEEN 0 AND 1),
    risk_factors TEXT[],
    shell_indicators TEXT[],
    ownership_opacity_score FLOAT NOT NULL DEFAULT 0.0,
    
    -- Activity tracking
    last_filing_date DATE,
    
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Include dissolved and liquidated companies
CREATE INDEX idx_company_status ON company_attributes(status);
CREATE INDEX idx_company_sni ON company_attributes(sni_primary);
CREATE INDEX idx_company_risk ON company_attributes(risk_score) WHERE risk_score > 0.5;
```

### Address Entity Attributes

```sql
CREATE TABLE address_attributes (
    entity_id UUID PRIMARY KEY REFERENCES entities(id),
    
    -- Normalized components
    street TEXT NOT NULL,
    street_number TEXT,
    postal_code VARCHAR(10) NOT NULL,
    city TEXT NOT NULL,
    municipality VARCHAR(50),
    
    -- Geocoded location
    coordinates GEOGRAPHY(POINT, 4326),
    geocode_confidence FLOAT,
    
    -- Zone classification
    vulnerable_area BOOLEAN NOT NULL DEFAULT FALSE,
    vulnerability_level VARCHAR(20),  -- PARTICULARLY, RISK, CONCERN
    
    -- Cached computations (updated nightly)
    company_count INT NOT NULL DEFAULT 0,
    person_count INT NOT NULL DEFAULT 0,
    is_registration_hub BOOLEAN NOT NULL DEFAULT FALSE,  -- Many companies, few people
    
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_address_postal ON address_attributes(postal_code);
CREATE INDEX idx_address_geo ON address_attributes USING GIST(coordinates);
CREATE INDEX idx_address_vulnerable ON address_attributes(vulnerable_area) WHERE vulnerable_area = TRUE;
```

---

## Facts and Relationships

### Fact Table

All assertions about entities and relationships:

```sql
CREATE TABLE facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_type VARCHAR(20) NOT NULL CHECK (fact_type IN ('ATTRIBUTE', 'RELATIONSHIP')),
    
    -- Subject (always required)
    subject_id UUID NOT NULL REFERENCES entities(id),
    
    -- Predicate
    predicate VARCHAR(50) NOT NULL,
    
    -- For ATTRIBUTE facts
    value_text TEXT,
    value_int BIGINT,
    value_float FLOAT,
    value_date DATE,
    value_bool BOOLEAN,
    value_json JSONB,
    
    -- For RELATIONSHIP facts
    object_id UUID REFERENCES entities(id),
    relationship_attributes JSONB,  -- ownership_percentage, role_title, etc.
    
    -- Temporality (day-level)
    valid_from DATE NOT NULL,
    valid_to DATE,  -- NULL = current
    
    -- Confidence and provenance
    confidence FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    provenance_id UUID NOT NULL REFERENCES provenances(id),
    
    -- Lifecycle
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_by UUID REFERENCES facts(id),
    superseded_at TIMESTAMPTZ,
    
    -- For derived facts
    is_derived BOOLEAN NOT NULL DEFAULT FALSE,
    derivation_rule TEXT,
    derived_from UUID[]  -- Source fact IDs
);

-- Primary query patterns
CREATE INDEX idx_facts_subject ON facts(subject_id, predicate) WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_object ON facts(object_id, predicate) WHERE superseded_by IS NULL AND object_id IS NOT NULL;
CREATE INDEX idx_facts_temporal ON facts(valid_from, valid_to) WHERE superseded_by IS NULL;
CREATE INDEX idx_facts_derived ON facts(is_derived, derivation_rule) WHERE is_derived = TRUE;
```

### Relationship Types (MVP)

```sql
-- Constrain to MVP relationship types
ALTER TABLE facts ADD CONSTRAINT valid_relationship_predicate CHECK (
    fact_type != 'RELATIONSHIP' OR predicate IN (
        'DIRECTOR_OF',
        'SHAREHOLDER_OF', 
        'REGISTERED_AT',
        'SAME_AS'  -- For entity merges
    )
);
```

### Same-As Links (Entity Merge)

```sql
-- View for resolved entity clusters
CREATE VIEW entity_clusters AS
WITH RECURSIVE cluster AS (
    -- Base: entities with same-as links
    SELECT 
        f.subject_id as entity_id,
        f.object_id as linked_to,
        f.subject_id as cluster_root
    FROM facts f
    WHERE f.predicate = 'SAME_AS'
    AND f.superseded_by IS NULL
    
    UNION
    
    -- Recursive: follow same-as chains
    SELECT 
        c.entity_id,
        f.object_id,
        c.cluster_root
    FROM cluster c
    JOIN facts f ON f.subject_id = c.linked_to
    WHERE f.predicate = 'SAME_AS'
    AND f.superseded_by IS NULL
)
SELECT DISTINCT entity_id, cluster_root FROM cluster;
```

---

## Provenance

### Provenance Table

```sql
CREATE TABLE provenances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Source identification
    source_type VARCHAR(30) NOT NULL CHECK (source_type IN (
        'BOLAGSVERKET_HVD',
        'BOLAGSVERKET_ANNUAL_REPORT',
        'ALLABOLAG_SCRAPE',
        'MANUAL_ENTRY',
        'DERIVED_COMPUTATION'
    )),
    source_id TEXT NOT NULL,  -- API response ID, document URL, etc.
    source_url TEXT,
    source_document_hash TEXT,  -- SHA-256
    
    -- Extraction details
    extraction_method TEXT NOT NULL,
    extraction_timestamp TIMESTAMPTZ NOT NULL,
    extraction_system_version TEXT NOT NULL,
    
    -- For derived facts
    derived_from UUID[],
    derivation_rule TEXT,
    
    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_provenance_source ON provenances(source_type, source_id);
```

### Source Authority Hierarchy

Each source is authoritative for specific fact types:

```sql
CREATE TABLE source_authority (
    source_type VARCHAR(30) NOT NULL,
    fact_predicate VARCHAR(50) NOT NULL,
    authority_level INT NOT NULL,  -- Lower = more authoritative
    PRIMARY KEY (source_type, fact_predicate)
);

-- Bolagsverket is authoritative for company registration data
INSERT INTO source_authority VALUES
    ('BOLAGSVERKET_HVD', 'DIRECTOR_OF', 1),
    ('BOLAGSVERKET_HVD', 'REGISTERED_AT', 1),
    ('BOLAGSVERKET_HVD', 'SHAREHOLDER_OF', 2),
    ('BOLAGSVERKET_ANNUAL_REPORT', 'SHAREHOLDER_OF', 1),
    ('ALLABOLAG_SCRAPE', 'DIRECTOR_OF', 2),
    ('ALLABOLAG_SCRAPE', 'SHAREHOLDER_OF', 3);
```

**Conflict Resolution Rule**: When facts conflict, the source with lowest authority_level wins. If equal, most recent extraction_timestamp wins.

---

## Mentions and Resolution

### Mention Table

Raw observations before entity resolution:

```sql
CREATE TABLE mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mention_type VARCHAR(20) NOT NULL CHECK (mention_type IN ('PERSON', 'COMPANY', 'ADDRESS')),
    
    -- What was observed
    surface_form TEXT NOT NULL,  -- Exact text as appeared
    normalized_form TEXT NOT NULL,  -- Cleaned version
    
    -- Extracted identifiers (if available)
    extracted_personnummer TEXT,
    extracted_orgnummer TEXT,
    
    -- Extracted attributes
    extracted_attributes JSONB NOT NULL DEFAULT '{}',
    
    -- Source
    provenance_id UUID NOT NULL REFERENCES provenances(id),
    document_location TEXT,  -- XPath, page number, etc.
    
    -- Resolution status
    resolution_status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (resolution_status IN (
        'PENDING', 'AUTO_MATCHED', 'HUMAN_MATCHED', 'AUTO_REJECTED', 'HUMAN_REJECTED'
    )),
    resolved_to UUID REFERENCES entities(id),
    resolution_confidence FLOAT,
    resolution_method TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,  -- 'system' or user ID
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_mentions_pending ON mentions(mention_type) WHERE resolution_status = 'PENDING';
CREATE INDEX idx_mentions_resolved ON mentions(resolved_to) WHERE resolved_to IS NOT NULL;
```

### Resolution Thresholds

```sql
CREATE TABLE resolution_config (
    mention_type VARCHAR(20) PRIMARY KEY,
    auto_match_threshold FLOAT NOT NULL,
    human_review_min FLOAT NOT NULL,
    auto_reject_threshold FLOAT NOT NULL
);

INSERT INTO resolution_config VALUES
    ('PERSON', 0.95, 0.60, 0.60),
    ('COMPANY', 0.95, 0.60, 0.60),
    ('ADDRESS', 0.90, 0.50, 0.50);
```

### Resolution Decision Log

For audit trail and accuracy measurement:

```sql
CREATE TABLE resolution_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mention_id UUID NOT NULL REFERENCES mentions(id),
    candidate_entity_id UUID NOT NULL REFERENCES entities(id),
    
    -- Scores
    overall_score FLOAT NOT NULL,
    feature_scores JSONB NOT NULL,  -- Individual feature breakdown
    
    -- Decision
    decision VARCHAR(20) NOT NULL CHECK (decision IN (
        'AUTO_MATCH', 'AUTO_REJECT', 'HUMAN_MATCH', 'HUMAN_REJECT', 'PENDING_REVIEW'
    )),
    decision_reason TEXT,
    
    -- Human review (if applicable)
    reviewer_id TEXT,
    reviewed_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_resolution_pending ON resolution_decisions(decision) WHERE decision = 'PENDING_REVIEW';
```

---

## Entity Lifecycle Operations

### Merge (Same-As)

Non-destructive merge preserving both entities:

```python
def merge_entities(entity_a_id: UUID, entity_b_id: UUID, reason: str, confidence: float) -> UUID:
    """
    Create same-as relationship between two entities.
    Returns the canonical entity ID (lower created_at wins).
    """
    # Determine canonical (older entity)
    a = get_entity(entity_a_id)
    b = get_entity(entity_b_id)
    
    if a.created_at <= b.created_at:
        canonical, secondary = a, b
    else:
        canonical, secondary = b, a
    
    # Create same-as fact
    create_fact(
        fact_type='RELATIONSHIP',
        subject_id=secondary.id,
        predicate='SAME_AS',
        object_id=canonical.id,
        valid_from=date.today(),
        confidence=confidence,
        provenance=create_provenance(
            source_type='DERIVED_COMPUTATION',
            extraction_method='entity_merge',
            derivation_rule=reason
        )
    )
    
    # Update secondary status
    update_entity(secondary.id, status='MERGED', merged_into=canonical.id)
    
    # Log for audit
    log_audit_event('ENTITY_MERGE', {
        'canonical': canonical.id,
        'secondary': secondary.id,
        'reason': reason,
        'confidence': confidence
    })
    
    return canonical.id
```

### Split

Create new entity, reassign facts:

```python
def split_entity(original_id: UUID, fact_ids_for_new: List[UUID], reason: str) -> UUID:
    """
    Split entity by moving specified facts to new entity.
    Original entity preserved with remaining facts.
    """
    original = get_entity(original_id)
    
    # Create new entity
    new_entity = create_entity(
        entity_type=original.entity_type,
        canonical_name=f"Split from {original.canonical_name}",
        status='ACTIVE',
        split_from=original.id
    )
    
    # Reassign specified facts
    for fact_id in fact_ids_for_new:
        fact = get_fact(fact_id)
        
        # Supersede old fact
        update_fact(fact_id, superseded_by=new_fact_id, superseded_at=now())
        
        # Create new fact pointing to new entity
        new_fact = create_fact(
            **fact.copy(),
            id=gen_uuid(),
            subject_id=new_entity.id,
            provenance=create_provenance(
                source_type='DERIVED_COMPUTATION',
                extraction_method='entity_split',
                derived_from=[fact_id],
                derivation_rule=f"Split from entity {original_id}: {reason}"
            )
        )
    
    # Log for audit
    log_audit_event('ENTITY_SPLIT', {
        'original': original_id,
        'new_entity': new_entity.id,
        'facts_moved': fact_ids_for_new,
        'reason': reason
    })
    
    return new_entity.id
```

### Anonymize (GDPR Erasure)

```python
def anonymize_entity(entity_id: UUID, request_reference: str) -> None:
    """
    GDPR-compliant anonymization.
    Preserves structure, removes PII.
    """
    entity = get_entity(entity_id)
    
    # Generate anonymization hash
    anon_hash = sha256(f"{entity_id}:{request_reference}".encode()).hexdigest()[:16]
    
    # Anonymize entity
    update_entity(
        entity_id,
        canonical_name=f"ANONYMIZED_{anon_hash}",
        status='ANONYMIZED',
        anonymized_at=now()
    )
    
    # Clear identifiers
    delete_entity_identifiers(entity_id)
    
    # Clear PII from attributes
    if entity.entity_type == 'PERSON':
        clear_person_attributes(entity_id)
    
    # Preserve relationships (structure) but clear any PII in attributes
    anonymize_fact_values(entity_id)
    
    # Log for audit (separate retention)
    log_erasure_request(
        entity_id=entity_id,
        request_reference=request_reference,
        anonymized_at=now()
    )
```

---

## Derived Facts

### Configuration

```sql
CREATE TABLE derivation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name TEXT NOT NULL UNIQUE,
    rule_type VARCHAR(30) NOT NULL CHECK (rule_type IN (
        'RISK_SCORE', 'NETWORK_CLUSTER', 'SHELL_INDICATOR', 'VELOCITY'
    )),
    rule_definition JSONB NOT NULL,  -- Parameters, thresholds
    version INT NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Recomputation

Nightly batch job:

```python
async def nightly_derivation_job():
    """
    Recompute all derived facts.
    Target: <4 hours for full graph.
    """
    job_start = now()
    
    # 1. Risk scores
    await compute_person_risk_scores()
    await compute_company_risk_scores()
    
    # 2. Network clusters
    await compute_network_clusters()
    
    # 3. Shell indicators
    await compute_shell_indicators()
    
    # 4. Director velocity
    await compute_director_velocity()
    
    # 5. Address statistics
    await compute_address_statistics()
    
    # 6. Validate derived facts match source facts
    await validate_derivation_consistency()
    
    job_end = now()
    log_audit_event('DERIVATION_JOB_COMPLETE', {
        'duration_seconds': (job_end - job_start).total_seconds(),
        'entities_processed': get_active_entity_count()
    })
```

Each derived fact stored with provenance:

```python
def store_derived_fact(entity_id: UUID, predicate: str, value: Any, rule_name: str, source_facts: List[UUID]):
    """
    Store derived fact with full lineage.
    """
    rule = get_derivation_rule(rule_name)
    
    # Supersede previous derivation if exists
    prev = get_current_derived_fact(entity_id, predicate, rule_name)
    if prev:
        supersede_fact(prev.id)
    
    create_fact(
        fact_type='ATTRIBUTE',
        subject_id=entity_id,
        predicate=predicate,
        value=value,
        valid_from=date.today(),
        confidence=1.0,  # Derived facts are deterministic
        is_derived=True,
        derivation_rule=rule_name,
        derived_from=source_facts,
        provenance=create_provenance(
            source_type='DERIVED_COMPUTATION',
            extraction_method=f'derivation_rule_{rule_name}_v{rule.version}',
            derived_from=source_facts,
            derivation_rule=rule_name
        )
    )
```

---

## Audit Logging

### Audit Log Table

Separate storage for tamper resistance:

```sql
-- In separate audit database/schema
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    
    -- Actor
    actor_type VARCHAR(20) NOT NULL CHECK (actor_type IN ('SYSTEM', 'USER', 'API')),
    actor_id TEXT,
    
    -- Target
    target_type VARCHAR(30),  -- 'ENTITY', 'FACT', 'MENTION', etc.
    target_id UUID,
    
    -- Event details
    event_data JSONB NOT NULL,
    
    -- Request context
    request_id UUID,
    ip_address INET,
    user_agent TEXT
);

-- Partition by month for retention management
CREATE INDEX idx_audit_timestamp ON audit_log(event_timestamp);
CREATE INDEX idx_audit_target ON audit_log(target_type, target_id);
CREATE INDEX idx_audit_actor ON audit_log(actor_type, actor_id);
```

### Retention Policy

```sql
-- Retention: 3 years for audit log
-- Implemented via pg_partman or manual partition management
CREATE OR REPLACE FUNCTION drop_old_audit_partitions()
RETURNS void AS $$
BEGIN
    -- Drop partitions older than 3 years
    -- Implementation depends on partitioning strategy
END;
$$ LANGUAGE plpgsql;
```

### What Gets Logged

| Event Type | Logged Data | Retention |
|------------|-------------|-----------|
| ENTITY_CREATE | entity_id, type, canonical_name | 3 years |
| ENTITY_MERGE | canonical_id, secondary_id, reason | 3 years |
| ENTITY_SPLIT | original_id, new_id, facts_moved | 3 years |
| ENTITY_ANONYMIZE | entity_id, request_reference | 3 years |
| FACT_CREATE | fact_id, subject_id, predicate | 3 years |
| FACT_SUPERSEDE | old_id, new_id, reason | 3 years |
| RESOLUTION_DECISION | mention_id, entity_id, decision, score | 3 years |
| HUMAN_REVIEW | mention_id, reviewer_id, decision | 3 years |
| PII_QUERY | user_id, query_type, entity_ids_returned | 6 months |
| PATTERN_MATCH | pattern_type, entities_matched | 3 years |
| EXPORT_EVIDENCE | entity_ids, requesting_user | 3 years |
| DERIVATION_JOB | entities_processed, duration | 1 year |

---

## MVP Query Patterns

### Shell Company Network Detection

```sql
-- Find persons directing multiple low-activity companies
WITH director_companies AS (
    SELECT 
        f.subject_id as person_id,
        f.object_id as company_id
    FROM facts f
    WHERE f.predicate = 'DIRECTOR_OF'
    AND f.valid_to IS NULL
    AND f.superseded_by IS NULL
),
company_stats AS (
    SELECT 
        dc.person_id,
        dc.company_id,
        ca.status,
        ca.latest_employees,
        ca.latest_revenue
    FROM director_companies dc
    JOIN company_attributes ca ON ca.entity_id = dc.company_id
    WHERE ca.status = 'ACTIVE'
    AND (ca.latest_employees IS NULL OR ca.latest_employees < 2)
    AND (ca.latest_revenue IS NULL OR ca.latest_revenue < 500000)
)
SELECT 
    person_id,
    array_agg(company_id) as shell_companies,
    count(*) as shell_count
FROM company_stats
GROUP BY person_id
HAVING count(*) >= 3
ORDER BY count(*) DESC;
```

### Real-Time New Registration Alert

```sql
-- Trigger on new company registration
CREATE OR REPLACE FUNCTION check_new_registration_risk()
RETURNS TRIGGER AS $$
DECLARE
    director_risk FLOAT;
    address_risk FLOAT;
BEGIN
    -- Check if any directors have high-risk connections
    SELECT COALESCE(MAX(pa.risk_score), 0)
    INTO director_risk
    FROM facts f
    JOIN person_attributes pa ON pa.entity_id = f.subject_id
    WHERE f.object_id = NEW.entity_id
    AND f.predicate = 'DIRECTOR_OF'
    AND f.superseded_by IS NULL;
    
    -- Check if registered at high-risk address
    SELECT COALESCE(MAX(
        CASE WHEN aa.vulnerable_area THEN 0.5 ELSE 0 END +
        CASE WHEN aa.is_registration_hub THEN 0.3 ELSE 0 END
    ), 0)
    INTO address_risk
    FROM facts f
    JOIN address_attributes aa ON aa.entity_id = f.object_id
    WHERE f.subject_id = NEW.entity_id
    AND f.predicate = 'REGISTERED_AT'
    AND f.superseded_by IS NULL;
    
    -- Alert if combined risk exceeds threshold
    IF director_risk + address_risk > 0.7 THEN
        INSERT INTO alerts (alert_type, entity_id, risk_score, created_at)
        VALUES ('HIGH_RISK_REGISTRATION', NEW.entity_id, director_risk + address_risk, NOW());
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

## Validation Strategy

### Ground Truth Sources

1. **Personnummer exact matches**: Gold standard for person resolution
2. **Organisationsnummer exact matches**: Gold standard for company resolution
3. **Synthetic test data**: Generated duplicates with known variations
4. **Ekobrottsmyndigheten cases**: Confirmed connected entities from prosecuted cases

### Accuracy Measurement

```sql
CREATE TABLE validation_ground_truth (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ground_truth_type VARCHAR(30) NOT NULL CHECK (ground_truth_type IN (
        'PERSONNUMMER_MATCH', 'ORGNUMMER_MATCH', 'SYNTHETIC', 'EKOBROTTSMYNDIGHETEN'
    )),
    entity_a_id UUID REFERENCES entities(id),
    entity_b_id UUID REFERENCES entities(id),
    is_same_entity BOOLEAN NOT NULL,
    source_reference TEXT,  -- Case number, test ID, etc.
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Validation metrics view
CREATE VIEW resolution_accuracy AS
WITH predictions AS (
    SELECT 
        gt.id,
        gt.is_same_entity as actual,
        CASE 
            WHEN EXISTS (
                SELECT 1 FROM facts f 
                WHERE f.predicate = 'SAME_AS'
                AND ((f.subject_id = gt.entity_a_id AND f.object_id = gt.entity_b_id)
                  OR (f.subject_id = gt.entity_b_id AND f.object_id = gt.entity_a_id))
                AND f.superseded_by IS NULL
            ) THEN TRUE
            ELSE FALSE
        END as predicted
    FROM validation_ground_truth gt
)
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN actual AND predicted THEN 1 ELSE 0 END) as true_positives,
    SUM(CASE WHEN NOT actual AND predicted THEN 1 ELSE 0 END) as false_positives,
    SUM(CASE WHEN actual AND NOT predicted THEN 1 ELSE 0 END) as false_negatives,
    SUM(CASE WHEN NOT actual AND NOT predicted THEN 1 ELSE 0 END) as true_negatives,
    -- Specificity target: >99.5%
    SUM(CASE WHEN NOT actual AND NOT predicted THEN 1 ELSE 0 END)::FLOAT / 
        NULLIF(SUM(CASE WHEN NOT actual THEN 1 ELSE 0 END), 0) as specificity,
    -- Sensitivity target: >90%
    SUM(CASE WHEN actual AND predicted THEN 1 ELSE 0 END)::FLOAT /
        NULLIF(SUM(CASE WHEN actual THEN 1 ELSE 0 END), 0) as sensitivity
FROM predictions;
```

---

## Swedish Data Handling

### Personnummer Validation

```python
def validate_personnummer(pnr: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Swedish personnummer with Luhn checksum.
    Handles both 10-digit (YYMMDD-XXXX) and 12-digit (YYYYMMDD-XXXX) formats.
    Also validates samordningsnummer (day + 60).
    """
    # Normalize
    clean = re.sub(r'[-\s]', '', pnr)
    
    if len(clean) == 12:
        clean = clean[2:]  # Remove century for validation
    
    if len(clean) != 10:
        return False, "Invalid length"
    
    # Check if samordningsnummer (day > 60)
    day = int(clean[4:6])
    is_samordning = day > 60
    if is_samordning:
        day -= 60
    
    # Validate date
    try:
        year = int(clean[0:2])
        month = int(clean[2:4])
        # Year interpretation depends on context (handled elsewhere)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return False, "Invalid date"
    except ValueError:
        return False, "Non-numeric date"
    
    # Luhn checksum
    digits = [int(d) for d in clean[:9]]
    weights = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    weighted = [d * w for d, w in zip(digits, weights)]
    summed = sum(d // 10 + d % 10 for d in weighted)
    checksum = (10 - (summed % 10)) % 10
    
    if checksum != int(clean[9]):
        return False, "Invalid checksum"
    
    return True, "samordningsnummer" if is_samordning else "personnummer"
```

### Company Name Normalization

```python
def normalize_company_name(name: str) -> str:
    """
    Normalize Swedish company names for matching.
    """
    normalized = name.upper().strip()
    
    # Standard legal form normalization
    replacements = [
        (r'\bAKTIEBOLAG\b', 'AB'),
        (r'\bAB\b$', ''),  # Remove trailing AB
        (r'\bHANDELSBOLAG\b', 'HB'),
        (r'\bKOMMANDITBOLAG\b', 'KB'),
        (r'\bENSKILD FIRMA\b', 'EF'),
        (r'\bI LIKVIDATION\b', ''),
        (r'\bI KONKURS\b', ''),
        (r'\bUNDER REKONSTRUKTION\b', ''),
    ]
    
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    
    # Remove common noise
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized
```

### Address Normalization

```python
def normalize_swedish_address(address: str) -> dict:
    """
    Parse and normalize Swedish addresses.
    """
    # Common street type abbreviations
    street_types = {
        'GATAN': 'G',
        'VÄGEN': 'V',
        'ALLÉN': 'A',
        'STIGEN': 'ST',
        'PLAN': 'PL',
        'TORG': 'T',
    }
    
    # Extract postal code (5 digits, optional space after 3)
    postal_match = re.search(r'(\d{3})\s?(\d{2})', address)
    postal_code = f"{postal_match.group(1)} {postal_match.group(2)}" if postal_match else None
    
    # Extract street number
    number_match = re.search(r'(\d+)\s*([A-Z])?(?:\s|,|$)', address.upper())
    street_number = number_match.group(0).strip() if number_match else None
    
    # Remaining is street name
    street = address
    if postal_match:
        street = street[:postal_match.start()]
    if number_match:
        street = street[:number_match.start()]
    street = street.strip().rstrip(',')
    
    return {
        'street': street,
        'street_number': street_number,
        'postal_code': postal_code,
        'normalized': f"{street} {street_number or ''} {postal_code or ''}".strip()
    }
```

---

## API Contract

### Entity Lookup

```
GET /api/v1/entities/{id}
Response time: <100ms

Response:
{
    "id": "uuid",
    "entity_type": "PERSON|COMPANY|ADDRESS",
    "canonical_name": "string",
    "status": "ACTIVE|MERGED|SPLIT|ANONYMIZED",
    "resolution_confidence": 0.0-1.0,
    "identifiers": [...],
    "attributes": {...},
    "same_as": ["uuid", ...],  // Merged entities
    "created_at": "timestamp",
    "updated_at": "timestamp"
}
```

### Graph Traversal

```
GET /api/v1/entities/{id}/relationships?depth=2&predicates=DIRECTOR_OF,SHAREHOLDER_OF
Response time: <1s for depth=2

Response:
{
    "root": "uuid",
    "nodes": [...],
    "edges": [...],
    "truncated": false,
    "total_nodes": 42
}
```

### Pattern Match

```
POST /api/v1/patterns/shell-network
Response time: <10s

Request:
{
    "min_companies": 3,
    "max_employees": 2,
    "max_revenue": 500000
}

Response:
{
    "matches": [
        {
            "person_id": "uuid",
            "companies": ["uuid", ...],
            "risk_score": 0.85,
            "indicators": [...]
        }
    ],
    "execution_time_ms": 4523
}
```

---

## Implementation Checklist

**Last Updated**: 2026-01-08

### Phase 1: Core Model (Weeks 1-4)

- [x] PostgreSQL schema deployment (`onto_*` tables via Alembic)
- [x] Entity CRUD operations (`halo.models.entity`)
- [x] Fact CRUD with temporal handling (`halo.models.fact`)
- [x] Provenance tracking (`halo.models.provenance`)
- [x] Bolagsverket HVD ingestion (`halo.ingestion.bolagsverket`)
- [x] Exact-match resolution (`halo.resolution.exact_match`)

### Phase 2: Resolution Engine (Weeks 5-8)

- [x] Mention extraction pipeline (`halo.models.mention`)
- [x] Blocking index implementation (`halo.resolution.blocking`)
- [x] Feature extractors (`halo.resolution.comparison`)
- [x] Confidence scoring
- [x] Human review queue (`halo.review_workflow`)
- [x] Resolution decision logging (`halo.models.mention.ResolutionDecision`)

### Phase 3: Graph & Patterns (Weeks 9-12)

- [x] Apache AGE integration (`halo.db.age_backend`)
- [x] Shell network pattern query (`POST /api/v1/patterns/shell-network`)
- [x] Real-time alerting on new registrations (`halo.patterns.alerting`)
- [x] Network visualization export
- [x] Evidence package generation (`halo.evidence`)

### Phase 4: Derived Facts & Validation (Weeks 13-16)

- [x] Risk score computation (`halo.derivation.risk_score`)
- [x] Director velocity calculation (`halo.derivation.velocity`)
- [x] Nightly derivation job (`halo.derivation.scheduler`)
- [x] Ground truth dataset construction (`halo.models.validation`)
- [x] Accuracy measurement dashboard
- [x] Audit log implementation (`halo.models.audit`)

### Additional Implementation

- [x] EVENT entity type with `onto_event_attributes` migration
- [x] Entity lifecycle operations (`halo.lifecycle` - merge, split, anonymize)
- [x] Referral pipeline (`halo.referral`)
- [x] Impact tracking (`halo.impact`)
- [x] Fusion layer (`halo.fusion`)
- [x] Swedish utilities (`halo.swedish` - personnummer, orgnummer, address, company_name)
- [x] OntologyBase separation from legacy models
- [x] 110 unit tests passing

### Remaining Work

- [ ] CI/CD pipeline
- [ ] End-to-end integration tests
- [ ] Performance benchmarking
- [ ] API documentation
- [ ] Production deployment
- [ ] Monitoring setup

---

*This architecture has been implemented. See `src/halo/` for the codebase.*
