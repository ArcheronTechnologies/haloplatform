# Halo Financial Crime Documentation

## Overview

The Halo financial crime module provides comprehensive Anti-Money Laundering (AML) and Counter-Terrorist Financing (CTF) capabilities:

- **AML Pattern Detection** - Detect structuring, layering, rapid movement, round-tripping, and smurfing
- **Risk Scoring** - Multi-factor entity and transaction risk assessment
- **SAR Generation** - Create and submit Suspicious Activity Reports to Finanspolisen
- **Watchlist Screening** - Check entities against sanctions, PEP, and adverse media lists

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  Financial Crime Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Transactions/Entities                                          │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────────────────────┐                              │
│   │    AMLPatternDetector        │  Pattern detection           │
│   │ - Structuring                │  - Transaction analysis      │
│   │ - Layering                   │  - Graph analysis            │
│   │ - Rapid movement             │  - Window-based detection    │
│   │ - Round-tripping             │                              │
│   │ - Smurfing                   │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │      WatchlistChecker        │  Screen against lists        │
│   │ - Sanctions (EU, UN, OFAC)   │  - Fuzzy name matching       │
│   │ - PEP lists                  │  - Identifier matching       │
│   │ - Adverse media              │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │      RiskScorer              │  Calculate risk scores       │
│   │ - Entity scoring             │  - Geographic risk           │
│   │ - Transaction scoring        │  - Customer risk             │
│   │ - Relationship scoring       │  - Behavioral risk           │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │      SARGenerator            │  Report generation           │
│   │ - STR / CTR / SAR / TFAR     │  - Finanspolisen XML         │
│   │ - Narrative generation       │  - Validation                │
│   │ - Priority assignment        │                              │
│   └──────────────────────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### AMLPatternDetector

Orchestrates multiple AML pattern detection algorithms.

```python
from halo.fincrime import AMLPatternDetector

detector = AMLPatternDetector()
matches = detector.detect_all(transactions)

for match in matches:
    print(f"{match.pattern_type}: {match.description}")
    print(f"Severity: {match.severity}, Confidence: {match.confidence}")
    print(f"Amount: {match.total_amount} {match.currency}")
```

#### Pattern Types

| Pattern | Description | Key Indicators |
|---------|-------------|----------------|
| `structuring` | Breaking amounts to avoid thresholds | Multiple transactions 140k-150k SEK in 7 days |
| `layering` | Complex chains obscuring origin | 3+ hops within 72 hours |
| `rapid_movement` | Quick in-and-out of funds | Deposit and 80%+ withdrawal within 24 hours |
| `round_trip` | Funds returning through intermediaries | Circular flow with <15% loss |
| `smurfing` | Multiple depositors to single recipient | 3+ depositors, >150k SEK aggregate in 7 days |

#### PatternMatch Object

```python
@dataclass
class PatternMatch:
    pattern_type: str           # Type identifier
    severity: PatternSeverity   # low, medium, high, critical
    confidence: float           # 0.0 to 1.0
    description: str            # Human-readable description

    entity_ids: list[UUID]      # Entities involved
    transaction_ids: list[UUID] # Transactions involved

    total_amount: Decimal       # Total amount involved
    currency: str               # Currency (default: SEK)

    pattern_start: datetime     # When pattern began
    pattern_end: datetime       # When pattern ended
    details: dict               # Pattern-specific details
```

---

### StructuringDetector

Detects structuring (smurfing) patterns where large amounts are broken into smaller transactions to avoid reporting thresholds.

```python
from halo.fincrime import StructuringDetector

detector = StructuringDetector(
    threshold=Decimal("150000"),     # Swedish reporting threshold
    lookback_days=7,                  # Analysis window
    min_transactions=3,               # Minimum suspicious transactions
)

matches = detector.detect(transactions)
```

**Detection Logic:**
1. Find transactions just under threshold (95% to 100% of 150,000 SEK)
2. Check if they occur within lookback window (7 days)
3. Verify combined amounts would exceed threshold
4. Assign severity based on total amount and transaction count

**Severity Thresholds:**

| Severity | Criteria |
|----------|----------|
| CRITICAL | Total >= 5x threshold OR 10+ transactions |
| HIGH | Total >= 3x threshold OR 7+ transactions |
| MEDIUM | Total >= 2x threshold OR 5+ transactions |
| LOW | Default |

---

### LayeringDetector

Detects layering patterns where money moves through multiple entities to obscure origin.

```python
from halo.fincrime import LayeringDetector

detector = LayeringDetector(
    min_hops=3,                      # Minimum entities in chain
    max_hours=72,                    # Maximum timeframe
    min_amount=Decimal("50000"),     # Minimum amount to flag
)

matches = detector.detect(transactions)
```

**Detection Logic:**
1. Build transaction graph (entities as nodes, transactions as edges)
2. Find chains with 3+ hops completing within 72 hours
3. Verify amounts are similar (accounting for fees)
4. Calculate confidence based on chain length and timing

---

### RapidMovementDetector

Detects rapid in-and-out patterns where funds are deposited and withdrawn quickly.

```python
from halo.fincrime import RapidMovementDetector

detector = RapidMovementDetector(
    max_hours=24,                    # Maximum time between in and out
    min_amount=Decimal("100000"),    # Minimum amount to flag
    min_percentage=0.8,              # 80% of deposit withdrawn
)

matches = detector.detect(transactions)
```

**Severity Thresholds:**

| Severity | Criteria |
|----------|----------|
| CRITICAL | >= 1M SEK OR <= 2 hours |
| HIGH | >= 500k SEK OR <= 6 hours |
| MEDIUM | >= 200k SEK OR <= 12 hours |
| LOW | Default |

---

### RoundTripDetector

Detects round-trip transactions where funds return to origin through intermediaries.

```python
from halo.fincrime import RoundTripDetector

detector = RoundTripDetector(
    min_amount=Decimal("50000"),     # Minimum amount to flag
    max_days=30,                     # Maximum cycle duration
    max_loss_percentage=0.15,        # Maximum 15% loss (fees)
)

matches = detector.detect(transactions)
```

**Detection Logic:**
1. Find transaction paths that return to starting entity
2. Check amounts are similar (within 15% loss for fees)
3. Verify cycle completes within 30 days

---

### SmurfingDetector

Detects smurfing patterns where multiple depositors aggregate funds to a single recipient.

```python
from halo.fincrime import SmurfingDetector

detector = SmurfingDetector(
    min_depositors=3,                # Minimum unique depositors
    min_aggregate=Decimal("150000"), # Minimum total amount
    max_days=7,                      # Analysis window
)

matches = detector.detect(transactions)
```

---

## Risk Scoring

### EntityRiskScorer

Multi-factor risk scoring for entities (persons and companies).

```python
from halo.fincrime import EntityRiskScorer, EntityForScoring

scorer = EntityRiskScorer()
risk = scorer.score(entity, transactions, relationships, watchlist_hits)

print(f"Risk Level: {risk.risk_level}")      # low, medium, high, very_high
print(f"Overall Score: {risk.overall_score}") # 0.0 to 1.0
print(f"Recommendations: {risk.recommendations}")
```

#### Risk Factors

| Category | Factors |
|----------|---------|
| **Geographic** | High-risk countries (FATF blacklist), offshore jurisdictions |
| **Customer** | PEP status, sanctions matches, watchlist hits |
| **Industry** | High-risk SNI codes (gambling, money services, trusts) |
| **Ownership** | Shell company indicators, complex structures |
| **Transaction** | High volume, velocity, round amounts |
| **Relationship** | Connections to high-risk entities |

#### High-Risk Countries

```python
# FATF Blacklist
HIGH_RISK_COUNTRIES = {"IR", "KP", "SY", "MM", "PK", "NG", "YE", "HT"}

# Elevated Risk (offshore/sanctions)
MEDIUM_RISK_COUNTRIES = {"AE", "PA", "VG", "KY", "RU", "BY", "VE"}
```

#### High-Risk Industries (SNI Codes)

| SNI Code | Industry |
|----------|----------|
| 64.19 | Other monetary intermediation |
| 64.30 | Trusts, funds and similar |
| 66.19 | Other financial service activities |
| 92.00 | Gambling and betting |
| 96.09 | Other personal service activities |

#### Risk Levels

| Level | Score Range | Recommended Actions |
|-------|-------------|---------------------|
| LOW | 0.00 - 0.24 | Standard monitoring |
| MEDIUM | 0.25 - 0.49 | Heightened attention, annual review |
| HIGH | 0.50 - 0.74 | Enhanced monitoring, quarterly review |
| VERY_HIGH | 0.75 - 0.89 | Senior management approval required |
| PROHIBITED | 0.90 - 1.00 | Escalate to compliance, consider SAR |

---

### TransactionRiskScorer

Real-time risk scoring for individual transactions.

```python
from halo.fincrime import TransactionRiskScorer, TransactionForScoring

scorer = TransactionRiskScorer()
risk = scorer.score(transaction, sender_entity, receiver_entity, sender_history)

print(f"Risk Level: {risk.risk_level}")
print(f"Recommendations: {risk.recommendations}")
```

#### Amount Thresholds

| Level | Amount (SEK) |
|-------|--------------|
| Low | < 50,000 |
| Medium | 50,000 - 149,999 |
| High | 150,000 - 499,999 |
| Very High | 500,000 - 999,999 |
| Critical | >= 1,000,000 |

#### High-Risk Transaction Types

- `cash` - Cash transactions
- `crypto` - Cryptocurrency
- `wire_international` - International wire transfers
- `money_order` - Money orders

---

## SAR Generation

### SARGenerator

Generates Suspicious Activity Reports for Finanspolisen.

```python
from halo.fincrime import SARGenerator

generator = SARGenerator()
sar = generator.create_from_patterns(
    pattern_matches=matches,
    entities=entity_dict,
    transactions=transactions,
    case_id=case_id,
)

# Validate before submission
is_valid, errors = generator.validate_sar(sar)

# Approve and submit
if is_valid:
    generator.approve_sar(sar, reviewer_id)
    generator.submit_sar(sar)
```

#### SAR Types

| Type | Description | Use Case |
|------|-------------|----------|
| `STR` | Suspicious Transaction Report | Specific suspicious transactions |
| `CTR` | Currency Transaction Report | Cash > 150,000 SEK |
| `SAR` | Suspicious Activity Report | General suspicious patterns |
| `TFAR` | Terrorist Financing Activity Report | Terrorism-related |

#### SAR Priorities

| Priority | Criteria |
|----------|----------|
| URGENT | Critical severity OR >= 5M SEK |
| HIGH | High severity OR >= 1M SEK |
| MEDIUM | Medium severity OR >= 500k SEK |
| LOW | Default |

#### SAR Workflow

```
DRAFT → PENDING_REVIEW → APPROVED → SUBMITTED → ACKNOWLEDGED
                              ↓
                          REJECTED
```

#### SARReport Object

```python
@dataclass
class SARReport:
    id: UUID
    sar_type: SARType           # STR, CTR, SAR, TFAR
    status: SARStatus           # Workflow status
    priority: SARPriority       # Submission priority

    subjects: list[SARSubject]  # Persons/companies involved
    transactions: list[SARTransaction]

    summary: str                # Brief summary
    detailed_narrative: str     # Full narrative
    suspicion_grounds: list[str]

    total_amount: Decimal
    activity_start: datetime
    activity_end: datetime

    external_reference: str     # Finanspolisen reference
```

#### Currency Transaction Report (CTR)

```python
# Create CTR for large cash transaction
sar = generator.create_ctr(
    transaction=cash_transaction,
    entity=entity_data,
    created_by=analyst_id,
)
```

#### XML Export for Finanspolisen

```python
xml_content = sar.to_finanspolisen_xml()
```

---

## Watchlist Screening

### WatchlistChecker

Screen entities against sanctions, PEP, and other watchlists.

```python
from halo.fincrime import WatchlistChecker, WatchlistType

checker = WatchlistChecker(
    min_fuzzy_score=0.85,    # Fuzzy match threshold
    check_aliases=True,       # Check known aliases
)

# Check single entity
matches = checker.check_entity(
    name="Johan Andersson",
    identifier="19801215-1234",
    identifier_type="personnummer",
    date_of_birth="1980-12-15",
    nationality="SE",
)

# Quick checks
is_sanctioned = checker.is_sanctioned(name, identifier)
is_pep = checker.is_pep(name, identifier)
```

#### Watchlist Types

| Type | Description |
|------|-------------|
| `SANCTIONS_EU` | EU Consolidated Sanctions List |
| `SANCTIONS_UN` | UN Security Council Consolidated List |
| `SANCTIONS_OFAC` | US OFAC SDN List |
| `SANCTIONS_SE` | Swedish national sanctions |
| `PEP_DOMESTIC` | Swedish PEPs |
| `PEP_FOREIGN` | Foreign PEPs |
| `PEP_INTERNATIONAL_ORG` | International organization PEPs |
| `LAW_ENFORCEMENT` | Law enforcement lists |
| `ADVERSE_MEDIA` | Adverse media mentions |
| `INTERNAL` | Company's own watchlist |

#### Match Types

| Type | Score | Description |
|------|-------|-------------|
| `IDENTIFIER` | 1.0 | Exact identifier match (personnummer, passport) |
| `EXACT` | 1.0 | Exact name match |
| `ALIAS` | 0.95 | Match on known alias |
| `FUZZY` | 0.85+ | Fuzzy name similarity |

#### Batch Screening

```python
results = checker.check_batch(
    entities=[
        {"name": "Person A", "identifier": "..."},
        {"name": "Company B", "identifier": "..."},
    ],
    lists_to_check=[WatchlistType.SANCTIONS_EU, WatchlistType.PEP_DOMESTIC],
)

for entity_id, matches in results.items():
    if matches:
        print(f"{entity_id}: {len(matches)} matches found")
```

#### Fuzzy Matching Algorithm

The fuzzy matching combines:
1. **Token matching** - Jaccard similarity of name tokens (40% weight)
2. **Character similarity** - Levenshtein distance ratio (60% weight)
3. **DOB validation** - Reduces confidence if DOB mismatch

```python
# Example: "Johan Andersson" vs "Joahn Andersson" -> ~0.92 score
# Example: "Johan Andersson" vs "J. Andersson" -> ~0.70 score (alias match better)
```

---

## Swedish AML Context

### Reporting Requirements

| Threshold | Amount | Requirement |
|-----------|--------|-------------|
| Cash reporting | 150,000 SEK | Automatic CTR to Finanspolisen |
| Suspicion | Any amount | SAR if suspicious |
| Enhanced DD | 100,000 EUR | Additional verification |

### Penningtvättslagen Compliance

The financial crime module implements requirements from Penningtvättslagen (2017:630):

1. **Customer Due Diligence** - Entity risk scoring with KYC factors
2. **Transaction Monitoring** - AML pattern detection
3. **Suspicious Activity Reporting** - SAR generation and submission
4. **PEP Screening** - Watchlist checking for PEPs
5. **Sanctions Screening** - EU, UN, OFAC, Swedish lists

### Finanspolisen Integration

```python
from halo.fincrime import SARGenerator

generator = SARGenerator()
sar = generator.create_from_patterns(pattern_matches, entities)

# Generate XML for Finanspolisen submission
xml = sar.to_finanspolisen_xml()

# Submit (placeholder - actual integration required)
generator.submit_sar(sar)
# Returns external_reference: "FP-YYYYMMDD-XXXXXXXX"
```

---

## Usage Examples

### Full AML Pipeline

```python
from halo.fincrime import (
    AMLPatternDetector,
    EntityRiskScorer,
    WatchlistChecker,
    SARGenerator,
)

async def analyze_entity(entity: dict, transactions: list[dict]):
    # 1. Screen against watchlists
    checker = WatchlistChecker()
    watchlist_hits = checker.check_entity(
        name=entity["name"],
        identifier=entity.get("personnummer") or entity.get("orgnr"),
    )

    # 2. Calculate entity risk
    scorer = EntityRiskScorer()
    entity_risk = scorer.score_entity(
        entity=entity,
        transactions=transactions,
        watchlist_hits=[h.to_dict() for h in watchlist_hits],
    )

    # 3. Detect AML patterns
    detector = AMLPatternDetector()
    pattern_matches = detector.detect_all(
        transactions=transactions,
        entity_id=entity["id"],
    )

    # 4. Generate SAR if needed
    if entity_risk.risk_level in ["high", "very_high"] or pattern_matches:
        generator = SARGenerator()
        sar = generator.create_from_patterns(
            pattern_matches=[m.to_dict() for m in pattern_matches],
            entities={entity["id"]: entity},
            transactions=transactions,
        )
        return sar

    return None
```

### Transaction Monitoring

```python
from halo.fincrime import TransactionRiskScorer

async def monitor_transaction(transaction: dict, sender: dict):
    scorer = TransactionRiskScorer()

    # Load sender's transaction history
    history = await load_transaction_history(sender["id"], days=90)

    # Score the transaction
    risk = scorer.score_transaction(
        transaction=transaction,
        sender_entity=sender,
        sender_history=history,
    )

    if risk.risk_level in ["high", "very_high"]:
        # Hold for manual review
        await create_alert(
            transaction_id=transaction["id"],
            risk_score=risk.overall_score,
            factors=[f.to_dict() for f in risk.factors],
        )
        return "HOLD"

    return "APPROVED"
```

### Batch Watchlist Screening

```python
from halo.fincrime import WatchlistChecker, WatchlistType

async def screen_customers_daily(customers: list[dict]):
    checker = WatchlistChecker()

    # Load latest watchlist data
    await refresh_watchlists(checker)

    # Screen all customers
    results = checker.check_batch(
        entities=customers,
        lists_to_check=[
            WatchlistType.SANCTIONS_EU,
            WatchlistType.SANCTIONS_UN,
            WatchlistType.SANCTIONS_OFAC,
            WatchlistType.PEP_DOMESTIC,
            WatchlistType.PEP_FOREIGN,
        ],
    )

    # Flag new matches
    for customer_id, matches in results.items():
        for match in matches:
            if match.match_score >= 0.9:
                await flag_customer_for_review(
                    customer_id=customer_id,
                    watchlist_match=match.to_dict(),
                )
```

---

## Configuration

### Environment Variables

```bash
# Risk thresholds
RISK_LOW_THRESHOLD=0.25
RISK_MEDIUM_THRESHOLD=0.50
RISK_HIGH_THRESHOLD=0.75
RISK_VERY_HIGH_THRESHOLD=0.90

# Pattern detection
STRUCTURING_THRESHOLD=150000
STRUCTURING_LOOKBACK_DAYS=7
LAYERING_MIN_HOPS=3
LAYERING_MAX_HOURS=72
RAPID_MOVEMENT_MAX_HOURS=24

# Watchlist matching
WATCHLIST_MIN_FUZZY_SCORE=0.85
WATCHLIST_CHECK_ALIASES=true
```

### Pattern Detector Configuration

```python
from halo.fincrime import (
    AMLPatternDetector,
    StructuringDetector,
    LayeringDetector,
)

# Custom configuration
detector = AMLPatternDetector(detectors=[
    StructuringDetector(
        threshold=Decimal("150000"),
        lookback_days=7,
        min_transactions=3,
    ),
    LayeringDetector(
        min_hops=3,
        max_hours=72,
        min_amount=Decimal("50000"),
    ),
    # Add custom detectors...
])
```
