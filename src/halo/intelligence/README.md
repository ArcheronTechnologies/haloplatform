# Halo Intelligence Module

The intelligence module implements a 3-layer proactive fraud detection framework for Swedish corporate entities.

## Architecture

```
intelligence/
├── __init__.py           # Module exports
├── anomaly.py            # Layer 1: Statistical anomaly detection
├── patterns.py           # Layer 2: Graph pattern matching (Cypher)
├── predictive.py         # Layer 3: ML-based risk prediction
├── formation_agent.py    # Formation agent tracking
├── sequence_detector.py  # Fraud playbook detection
├── evasion.py            # Evasion behavior detection
├── sar_generator.py      # SAR report generation
├── konkurs.py            # Bankruptcy prediction
└── README.md             # This file
```

## Layer 1: Anomaly Detection

Statistical deviation detection using z-scores against Swedish market baselines.

### Usage

```python
from halo.intelligence.anomaly import AnomalyDetector, BaselineStats
from halo.graph.client import GraphClient

# Create detector with custom baselines
baselines = BaselineStats(
    addr_density_mean=1.3,    # Companies per address
    director_roles_mean=1.2,  # Directorships per person
    company_lifespan_months_median=84.0
)

detector = AnomalyDetector(
    graph_client=GraphClient(),
    baselines=baselines
)

# Score entities
address_score = await detector.score_address("address-123")
company_score = await detector.score_company("company-123")
person_score = await detector.score_person("person-123")

# Check results
if address_score.is_anomalous:
    print(f"Anomaly detected: {address_score.severity}")
    for flag in address_score.flags:
        print(f"  - {flag['type']}: {flag['severity']}")
```

### Anomaly Types

| Type | Description | Threshold |
|------|-------------|-----------|
| `high_registration_density` | Many companies at same address | >5 companies |
| `high_directorship_count` | Person has many directorships | >5 roles |
| `shell_indicator_no_employees` | Company has zero employees | 0 |
| `shell_indicator_f_skatt_no_vat` | F-skatt without VAT registration | - |
| `shell_indicator_generic_sni` | Generic industry code (70100, 82110) | - |
| `shell_indicator_recently_formed` | Formed within last 180 days | - |

## Layer 2: Pattern Matching

Graph-based pattern detection using Cypher queries.

### Built-in Patterns

```python
from halo.intelligence.patterns import PatternMatcher, FRAUD_PATTERNS

matcher = PatternMatcher(GraphClient())

# List available patterns
for pattern_id, pattern in FRAUD_PATTERNS.items():
    print(f"{pattern_id}: {pattern.name} ({pattern.severity})")
```

| Pattern ID | Typology | Severity | Description |
|------------|----------|----------|-------------|
| `registration_mill` | shell_company_network | high | Address with 5+ companies, shared directors |
| `phoenix` | corporate_fraud | medium | Director reappears in new company after konkurs |
| `circular_ownership` | money_laundering | high | Ownership loops back to same entity |
| `invoice_factory` | invoice_trading | critical | Shell company selling fake invoices |
| `layered_ownership` | tax_fraud | high | 3+ ownership layers through foreign entities |
| `nominee_director` | shell_company_network | medium | Person directing 10+ companies |
| `rapid_succession` | phoenix | high | Director associated with 3+ short-lived companies |
| `address_hop` | evasion | medium | Company changed address 3+ times in 12 months |
| `paper_trail` | shell_company_network | high | Recent formation + virtual address + no activity |
| `supplier_concentration` | invoice_trading | medium | 80%+ transactions with single supplier |

### Custom Patterns

```python
from halo.intelligence.patterns import FraudPattern

custom_pattern = FraudPattern(
    id="custom_pattern",
    name="Custom Detection",
    description="Detects custom fraud scenario",
    severity="high",
    typology="custom",
    query="""
        MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
        WHERE a.is_virtual = true
        AND c.employees.count = 0
        RETURN c, a
    """,
    extractor=lambda row: {
        "company": row["c"],
        "address": row["a"]
    }
)

matcher.add_pattern(custom_pattern)
```

### Running Detection

```python
# Detect all patterns
matches = await matcher.detect_all()

# Detect patterns for specific entity
entity_matches = await matcher.detect_for_entity(
    entity_id="company-123",
    entity_type="Company"
)

# Detect specific pattern
mill_matches = await matcher.detect_pattern("registration_mill")

# Convert to alerts
for match in matches:
    alert = match.to_alert()
    print(f"Alert: {alert['title']} - {alert['severity']}")
```

## Layer 3: Predictive Risk

ML-based risk prediction with explainability.

### Usage

```python
from halo.intelligence.predictive import RiskPredictor

predictor = RiskPredictor(graph_client=GraphClient())

# Single prediction
prediction = await predictor.predict("company-123")
print(f"Risk: {prediction.risk_level} ({prediction.probability:.2%})")
print(f"Confidence: {prediction.confidence:.2%}")
print(f"Signals: {prediction.construction_signals}")

# Batch prediction
predictions = await predictor.predict_batch(["c1", "c2", "c3"])

# Explain prediction
explanation = await predictor.explain_prediction("company-123", prediction)
print(f"Summary: {explanation['summary']}")
for action in explanation['recommended_actions']:
    print(f"  - {action}")
```

### Proxy Labels

Training labels derived from observable outcomes:

| Label | Weight | Description |
|-------|--------|-------------|
| `konkurs_within_24m` | +0.9 | Bankruptcy within 24 months |
| `ekobrottsmyndigheten` | +1.0 | Economic crime prosecution |
| `skatteverket_action` | +0.7 | Tax authority enforcement |
| `high_risk_indicators` | +0.6 | Multiple risk flags |
| `active_5y_with_employees` | -0.5 | Stable operation (survival signal) |

### Construction Signals

Early warning indicators of fraud infrastructure:

| Signal | Description |
|--------|-------------|
| `virtual_address` | Registered at known virtual office |
| `generic_sni` | Vague industry code (holding, consulting) |
| `no_arsredovisning` | Missing annual reports |
| `ownership_layering` | Complex ownership structure |
| `nominee_pattern` | Director pattern suggests nominee |
| `rapid_formation_agent` | Formed by high-volume agent |

### Network Risk Analysis

```python
from halo.intelligence.predictive import NetworkRiskAnalyzer

analyzer = NetworkRiskAnalyzer(GraphClient())

result = await analyzer.analyze_network_risk("company-123", hops=2)
print(f"Network size: {result['network_size']}")
print(f"High risk entities: {result['high_risk_entities']}")
print(f"Risk propagation: {result['risk_propagation']}")
```

## Advanced Features

### Formation Agent Tracking

Track company formation agents and their outcomes.

```python
from halo.intelligence.formation_agent import FormationAgentTracker

tracker = FormationAgentTracker(graph_client=GraphClient())

# Score a formation agent
score = await tracker.score_formation_agent("agent-123")
print(f"Companies formed: {score.companies_formed}")
print(f"Konkurs rate (2y): {score.konkurs_rate_2y:.2%}")
print(f"Suspicion level: {score.suspicion_level}")

# Find suspicious agents
suspicious = await tracker.find_suspicious_agents(min_companies=10)
```

### Fraud Sequence Detection

Detect entities following known fraud playbooks.

```python
from halo.intelligence.sequence_detector import FraudSequenceDetector, PLAYBOOKS

detector = FraudSequenceDetector(graph_client=GraphClient())

# Detect playbook matches
matches = await detector.detect_playbook("company-123")
for match in matches:
    print(f"Playbook: {match.playbook_name}")
    print(f"Stage: {match.current_stage}/{match.total_stages}")
    print(f"Next expected: {match.next_expected}")

# Predict next events
if matches:
    predictions = await detector.predict_next_events("company-123", matches[0])
```

#### Built-in Playbooks

| Playbook | Stages | Description |
|----------|--------|-------------|
| `invoice_factory` | 4 | Shell company setup for fake invoices |
| `phoenix` | 5 | Bankruptcy followed by new company |
| `ownership_layering` | 4 | Progressive ownership obfuscation |
| `money_laundering` | 5 | Classic money laundering pattern |
| `tax_fraud` | 4 | Tax evasion preparation |

### Evasion Detection

Detect attempts to avoid detection.

```python
from halo.intelligence.evasion import EvasionDetector

detector = EvasionDetector(graph_client=GraphClient())

score = await detector.analyze("company-123")
print(f"Evasion probability: {score.evasion_probability:.2%}")
print(f"Isolation score: {score.isolation_score:.2%}")
print(f"Synthetic compliance: {score.synthetic_compliance}")
print(f"Structuring detected: {score.structuring_detected}")
```

### SAR Generation

Generate Suspicious Activity Reports.

```python
from halo.intelligence.sar_generator import SARGenerator

generator = SARGenerator(graph_client=GraphClient())

sar = await generator.generate_sar(
    entity_id="company-123",
    trigger_reason="Pattern match: Registration Mill",
    alert_ids=["alert-1", "alert-2"],
    created_by="analyst@bank.se"
)

print(f"SAR ID: {sar.id}")
print(f"Priority: {sar.priority}")
print(f"Summary: {sar.summary}")

# Export
sar_data = sar.to_dict()
```

### Konkurs Prediction

Predict bankruptcy probability.

```python
from halo.intelligence.konkurs import KonkursPredictor

predictor = KonkursPredictor(graph_client=GraphClient())

prediction = await predictor.predict("company-123")
print(f"Konkurs probability: {prediction.konkurs_probability:.2%}")
print(f"Risk level: {prediction.risk_level}")
print(f"Network contagion risk: {prediction.network_contagion_risk:.2%}")
print(f"Distress signals: {prediction.distress_signals}")
print(f"Survival signals: {prediction.survival_signals}")

# Analyze contagion risk
contagion = await predictor.analyze_contagion_risk("company-123")
print(f"Affected entities: {contagion['affected_entities']}")
```

#### Konkurs Features

| Category | Features |
|----------|----------|
| Network | Counterparty distress %, average counterparty risk |
| Director | Previous konkurser, recent changes, shared with distressed |
| Trajectory | Employee trend, revenue trend, report delays |
| Industry | Sector failure rates |
| Lifecycle | Company age, initial capital, ownership changes |

## Testing

```bash
# Run all intelligence tests
python -m pytest halo/tests/test_intelligence_*.py -v

# Run specific module tests
python -m pytest halo/tests/test_intelligence_anomaly.py -v
python -m pytest halo/tests/test_intelligence_patterns.py -v
python -m pytest halo/tests/test_intelligence_predictive.py -v
python -m pytest halo/tests/test_intelligence_advanced.py -v
python -m pytest halo/tests/test_intelligence_sar_konkurs.py -v
```

## Integration Example

```python
from halo.graph.client import GraphClient
from halo.intelligence.anomaly import AnomalyDetector
from halo.intelligence.patterns import PatternMatcher
from halo.intelligence.predictive import RiskPredictor
from halo.intelligence.sar_generator import SARGenerator

async def analyze_entity(entity_id: str):
    client = GraphClient()

    async with client:
        # Layer 1: Anomaly detection
        anomaly_detector = AnomalyDetector(graph_client=client)
        anomaly_score = await anomaly_detector.score_company(entity_id)

        # Layer 2: Pattern matching
        matcher = PatternMatcher(client)
        pattern_matches = await matcher.detect_for_entity(entity_id, "Company")

        # Layer 3: Risk prediction
        predictor = RiskPredictor(graph_client=client)
        prediction = await predictor.predict(entity_id)

        # Generate SAR if high risk
        if prediction.risk_level in ["high", "critical"]:
            generator = SARGenerator(graph_client=client)
            sar = await generator.generate_sar(
                entity_id=entity_id,
                trigger_reason=f"Risk level: {prediction.risk_level}"
            )
            return sar

        return {
            "anomaly": anomaly_score,
            "patterns": pattern_matches,
            "prediction": prediction
        }
```
