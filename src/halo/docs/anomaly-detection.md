# Halo Anomaly Detection Documentation

## Overview

The Halo anomaly detection module identifies suspicious patterns in financial transactions for AML (Anti-Money Laundering) compliance. It implements Swedish-specific detection rules and integrates with the human-in-loop review system required by Brottsdatalagen.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Anomaly Detection Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Transactions                                                   │
│       │                                                          │
│       ▼                                                          │
│   ┌──────────────────────────────┐                              │
│   │ TransactionPatternDetector   │  Detect suspicious patterns  │
│   │ - Structuring                │                              │
│   │ - Velocity spikes            │                              │
│   │ - Round amounts              │                              │
│   │ - Rapid in-out               │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │       RulesEngine            │  Custom detection rules      │
│   │ - Configurable conditions    │                              │
│   │ - Analyst-defined patterns   │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │       RiskScorer             │  Calculate risk scores       │
│   │ - Combine pattern signals    │                              │
│   │ - Assign review tier         │                              │
│   └──────────────┬───────────────┘                              │
│                  │                                               │
│                  ▼                                               │
│   ┌──────────────────────────────┐                              │
│   │         Alerts               │  Create alerts for review    │
│   │ - Tier 1: Informational      │                              │
│   │ - Tier 2: Acknowledgment     │                              │
│   │ - Tier 3: Approval required  │                              │
│   └──────────────────────────────┘                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### TransactionPatternDetector

Detects common money laundering patterns in transaction data.

```python
from halo.anomaly import TransactionPatternDetector

detector = TransactionPatternDetector()
matches = detector.detect_patterns(transactions)

for match in matches:
    print(f"{match.pattern_type}: {match.description}")
    print(f"Confidence: {match.confidence}, Severity: {match.severity}")
```

#### Pattern Types

| Pattern | Description | Trigger Conditions |
|---------|-------------|-------------------|
| `STRUCTURING` | Breaking amounts to avoid reporting thresholds | Multiple transactions just under 150,000 SEK |
| `VELOCITY_SPIKE` | Unusual increase in transaction frequency | 3x normal transaction rate |
| `ROUND_AMOUNTS` | Suspiciously round numbers | Amounts like 10,000, 50,000, 100,000 |
| `RAPID_IN_OUT` | Money moving through quickly | In and out within 24-48 hours |
| `UNUSUAL_TIME` | Transactions at odd hours | Late night/early morning activity |
| `NEW_COUNTERPARTY` | Sudden new transaction partners | First-time high-value transfers |
| `DORMANT_REACTIVATION` | Dormant account suddenly active | Activity after 6+ months dormant |

#### Structuring Detection

Structuring (smurfing) is when large amounts are broken into smaller transactions to avoid reporting thresholds.

```python
# Swedish reporting threshold
REPORTING_THRESHOLD_SEK = 150_000

# Structuring detection parameters
STRUCTURING_THRESHOLD_SEK = 140_000  # Just under limit
STRUCTURING_WINDOW = timedelta(days=7)  # Analysis window
STRUCTURING_MIN_TRANSACTIONS = 3  # Minimum suspicious transactions
```

**Detection Logic:**
1. Find transactions just under the reporting threshold (140,000-150,000 SEK)
2. Check if they occur within a short window (7 days)
3. Calculate if combined amounts would exceed the threshold
4. Assign confidence based on pattern strength

#### Velocity Spike Detection

Detects unusual increases in transaction frequency.

```python
# Default parameters
VELOCITY_WINDOW_HOURS = 24
VELOCITY_MULTIPLIER = 3.0  # 3x normal rate triggers alert

# Detection Logic
current_rate = count_transactions(current_window)
historical_rate = average_transactions(historical_windows)

if current_rate > historical_rate * VELOCITY_MULTIPLIER:
    trigger_alert()
```

#### Round Amount Detection

Flags transactions with suspiciously round amounts.

```python
ROUND_AMOUNT_THRESHOLD = 10_000  # Minimum to flag

# Amounts that trigger detection:
# - 10,000 SEK
# - 50,000 SEK
# - 100,000 SEK
# - 500,000 SEK
```

---

### RulesEngine

Configurable rules engine for custom detection patterns.

```python
from halo.anomaly import RulesEngine, Rule, RuleCondition, RuleOperator

engine = RulesEngine()

# Add a custom rule
rule = Rule(
    name="High Risk Country",
    description="Transaction to high-risk jurisdiction",
    conditions=[
        RuleCondition(
            field="destination_country",
            operator=RuleOperator.IN,
            value=["AF", "KP", "IR", "SY"]  # High-risk countries
        ),
        RuleCondition(
            field="amount",
            operator=RuleOperator.GREATER_THAN,
            value=10000
        )
    ],
    severity="high",
    require_all=True  # Both conditions must match
)

engine.add_rule(rule)
```

#### Rule Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `EQUALS` | Exact match | `amount == 10000` |
| `NOT_EQUALS` | Not equal | `status != "blocked"` |
| `GREATER_THAN` | Greater than | `amount > 50000` |
| `GREATER_OR_EQUAL` | Greater or equal | `amount >= 50000` |
| `LESS_THAN` | Less than | `amount < 1000` |
| `LESS_OR_EQUAL` | Less or equal | `amount <= 1000` |
| `CONTAINS` | Contains string | `description contains "cash"` |
| `MATCHES` | Regex match | `reference matches r"^\d{10}$"` |
| `IN` | Value in list | `type in ["wire", "cash"]` |
| `NOT_IN` | Value not in list | `country not_in ["SE", "NO", "DK"]` |

#### Default Rules

The engine includes these default rules:

1. **High Value Cash** - Cash transactions over 50,000 SEK
2. **Cross-Border High Value** - International transfers over 100,000 SEK
3. **Rapid Multiple Transfers** - More than 5 transfers in 1 hour
4. **Round Amount Wire** - Wire transfers with round amounts

---

### RiskScorer

Calculates unified risk scores from detected patterns.

```python
from halo.anomaly import RiskScorer

scorer = RiskScorer()
risk = scorer.calculate_score(pattern_matches)

print(f"Risk Score: {risk.score}")
print(f"Tier: {risk.tier}")
print(f"Severity: {risk.severity}")
print(f"Factors: {risk.factors}")
```

#### RiskScore Object

```python
@dataclass
class RiskScore:
    score: float           # 0.0 to 1.0
    tier: int              # 1, 2, or 3
    factors: list[str]     # Contributing factors
    pattern_matches: list[PatternMatch]
    entity_id: Optional[UUID]
    calculated_at: datetime

    @property
    def severity(self) -> str:
        if self.score >= 0.85: return "critical"
        elif self.score >= 0.70: return "high"
        elif self.score >= 0.50: return "medium"
        else: return "low"

    @property
    def requires_review(self) -> bool:
        return self.tier >= 2
```

#### Pattern Weights

Different patterns contribute different weights to the final score:

| Pattern | Weight | Rationale |
|---------|--------|-----------|
| `STRUCTURING` | 1.0 | Most serious - intentional evasion |
| `RAPID_IN_OUT` | 0.8 | Strong indicator of layering |
| `VELOCITY_SPIKE` | 0.7 | Unusual but could be legitimate |
| `DORMANT_REACTIVATION` | 0.6 | Suspicious but contextual |
| `NEW_COUNTERPARTY` | 0.5 | Needs investigation |
| `ROUND_AMOUNTS` | 0.4 | Common but noteworthy |
| `UNUSUAL_TIME` | 0.3 | Weak signal alone |

#### Tier Assignment

```python
# Tier thresholds (configurable)
TIER_3_THRESHOLD = 0.85  # Requires approval
TIER_2_THRESHOLD = 0.50  # Requires acknowledgment

def assign_tier(score: float) -> int:
    if score >= TIER_3_THRESHOLD:
        return 3  # Approval required
    elif score >= TIER_2_THRESHOLD:
        return 2  # Acknowledgment required
    else:
        return 1  # Informational only
```

---

## Human-in-Loop Compliance

Halo implements tiered review to comply with Brottsdatalagen 2 kap. 19 §.

### Tier System

| Tier | Score Range | Requirement | Use Case |
|------|-------------|-------------|----------|
| 1 | 0.0 - 0.49 | None | Logging only |
| 2 | 0.50 - 0.84 | Acknowledgment | Moderate risk patterns |
| 3 | 0.85 - 1.00 | Approval + Justification | High-risk, affects individuals |

### Review Process

```python
# Tier 2: Acknowledgment
POST /api/v1/alerts/{id}/acknowledge
{
    "displayed_at": "2025-01-15T10:30:00Z"
}

# Tier 3: Approval with justification
POST /api/v1/alerts/{id}/approve
{
    "decision": "approved",
    "justification": "Pattern consistent with known AML typology...",
    "displayed_at": "2025-01-15T10:30:00Z"
}
```

### Rubber-Stamp Detection

The system detects perfunctory reviews:

```python
MIN_REVIEW_SECONDS = 2.0  # Minimum review time

if review_duration < MIN_REVIEW_SECONDS:
    alert.is_rubber_stamp = True
    # Log warning, may require re-review
```

---

## Configuration

### Environment Variables

```bash
# Tier thresholds
TIER_3_THRESHOLD=0.85
TIER_2_THRESHOLD=0.50

# Detection parameters
STRUCTURING_THRESHOLD=140000
VELOCITY_WINDOW_HOURS=24
VELOCITY_MULTIPLIER=3.0
ROUND_AMOUNT_THRESHOLD=10000

# Review parameters
MIN_REVIEW_SECONDS=2.0
```

### Pattern Detector Configuration

```python
detector = TransactionPatternDetector(
    structuring_threshold=140_000,
    velocity_window_hours=24,
    velocity_multiplier=3.0,
    round_amount_threshold=10_000,
)
```

---

## Usage Examples

### Full Detection Pipeline

```python
from halo.anomaly import (
    TransactionPatternDetector,
    RulesEngine,
    RiskScorer,
)
from halo.db.models import Transaction, Alert

async def analyze_transactions(transactions: list[Transaction]):
    # Detect patterns
    pattern_detector = TransactionPatternDetector()
    patterns = pattern_detector.detect_patterns(transactions)

    # Apply custom rules
    rules_engine = RulesEngine()
    rule_matches = rules_engine.evaluate(transactions)

    # Combine all matches
    all_patterns = patterns + [
        PatternMatch(
            pattern_type=PatternType.CUSTOM,
            confidence=match.rule.confidence,
            description=match.rule.description,
        )
        for match in rule_matches
    ]

    # Calculate risk scores
    scorer = RiskScorer()
    risk = scorer.calculate_score(all_patterns)

    # Create alert if needed
    if risk.requires_review:
        alert = Alert(
            alert_type="aml_pattern",
            severity=risk.severity,
            title=f"Suspicious pattern detected",
            description=format_alert_description(risk),
            confidence=risk.score,
            tier=risk.tier,
            affects_person=True,
            entity_ids=[t.from_entity_id for t in transactions if t.from_entity_id],
            transaction_ids=[t.id for t in transactions],
        )
        return alert

    return None
```

### Batch Processing

```python
from halo.anomaly import TransactionPatternDetector

async def batch_analyze(entity_id: UUID, date_range: tuple):
    # Load transactions
    transactions = await load_transactions(entity_id, date_range)

    # Load historical context
    historical = await load_historical_transactions(
        entity_id,
        before=date_range[0],
        limit=1000,
    )

    # Detect patterns with context
    detector = TransactionPatternDetector()
    patterns = detector.detect_patterns(
        transactions=transactions,
        historical_transactions=historical,
    )

    return patterns
```

### Custom Rule Example

```python
from halo.anomaly import RulesEngine, Rule, RuleCondition, RuleOperator

# Detect cryptocurrency-related transactions
crypto_rule = Rule(
    name="Cryptocurrency Exchange",
    description="Transaction to known cryptocurrency exchange",
    conditions=[
        RuleCondition(
            field="counterparty_name",
            operator=RuleOperator.MATCHES,
            value=r".*(coinbase|binance|kraken|bitstamp).*",
        ),
        RuleCondition(
            field="amount",
            operator=RuleOperator.GREATER_OR_EQUAL,
            value=25000,
        )
    ],
    severity="medium",
    confidence=0.7,
    category="crypto",
)

engine = RulesEngine()
engine.add_rule(crypto_rule)
```

---

## Swedish AML Context

### Reporting Thresholds

| Threshold | Amount | Requirement |
|-----------|--------|-------------|
| Reporting | 150,000 SEK | Must report to Finanspolisen |
| Suspicion | Any amount | Report if suspicious |
| Enhanced Due Diligence | 100,000 EUR | Additional verification |

### High-Risk Indicators (Swedish Context)

1. **Geographic:** Transactions to/from high-risk countries (FATF list)
2. **Sector:** Cash-intensive businesses, gambling, crypto
3. **Behavior:** Structuring, rapid movement, new counterparties
4. **Profile:** PEP (Politically Exposed Persons), sanctions lists

### Finanspolisen Integration

Alerts flagged for SAR (Suspicious Activity Report) can be exported:

```python
from halo.fincrime import SARGenerator

generator = SARGenerator()
sar = await generator.generate(alert)

# Export in Finanspolisen format
xml = sar.to_xml()
```
