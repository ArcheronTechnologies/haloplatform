# Detection Methodology

## Overview

This document describes the methodology for fraud detection in Swedish companies:

1. **Shell Company Scoring** - Weighted multi-factor scoring for shell company probability
2. **Serial Entity Analysis** - Identifying enablers who repeatedly appear across companies
3. **Temporal Sequence Detection** - Detecting fraud playbooks from event sequences

**Last Updated:** 2025-12-26
**Calibration Source:** 8,200 active Swedish ABs from SCB → Bolagsverket extraction

---

## 1. Shell Company Scoring

### Concept

Shell companies exhibit multiple characteristic indicators. Rather than flagging on any single indicator (which causes high false positive rates), we use weighted scoring that requires multiple indicators to reach a suspicious threshold.

### Indicators and Weights

| Indicator | Weight | Prevalence | Rationale |
|-----------|--------|------------|-----------|
| `f_skatt_no_vat` | 0.25 | 1.3% | F-skatt (tax) without VAT suggests invoice generation without actual goods/services. **Strongest signal.** |
| `generic_sni` | 0.20 | 15.5% | SNI codes 64,66,68,70,82 (financial, consulting, real estate) are overrepresented in shell schemes |
| `no_employees` | 0.15 | 99.2% | Nearly universal in Bolagsverket data (they don't track employees for most companies) |
| `recently_formed` | 0.15 | 4.1% | Companies < 2 years old have higher fraud risk |
| `single_director` | 0.10 | 8.7% | Common in legitimate small businesses; low weight |
| `no_revenue` | 0.15 | N/A | When available and zero, meaningful combined with other indicators |

### Scoring

```
shell_score = sum(weight[indicator] for indicator in triggered_indicators)
```

### Severity Thresholds

| Severity | Threshold | Flag Rate | Action |
|----------|-----------|-----------|--------|
| **High** | >= 0.6 | 0.4% (30 companies) | Prioritize for manual review |
| **Medium** | >= 0.4 | 3.3% (268 companies) | Monitor |
| **Low** | < 0.4 | 96.4% | No action |

### Threshold Justification

- **0.6 threshold** requires 3+ strong indicators OR 4+ weak indicators
- **0.4% flag rate** is manageable for human review (30 out of 8,200)
- Avoids the 14%+ flag rate that would result from flagging single_director + generic_sni alone

### Results (2025-12-26)

Top shell score indicators:
- **Elias Grafström AB** (0.85): no_employees, generic_sni, recently_formed, f_skatt_no_vat, single_director
- Multiple companies at 0.70: no_employees, generic_sni, f_skatt_no_vat, single_director

---

## 2. Serial Entity Analysis

### Concept

Fraud schemes often involve "formation agents" - entities that repeatedly appear across multiple companies. This includes auditors, directors, and shared addresses.

### Entity Types Analyzed

#### 2.1 Auditing Companies (Revisorer)

**Rationale:** Auditors see company financials. An auditor with many high-risk clients warrants investigation.

**Detection method:**
```
For each auditor node:
  1. Count companies they audit
  2. Calculate average shell_score of those companies
  3. Count companies with shell_score > 0.6
  4. Flag if: high_shell_count > 3 OR (company_count > 10 AND avg_shell > 0.4)
```

#### 2.2 Serial Directors

**Rationale:** Most people direct 1 company (mean=1.12, p99=2). Someone directing 5+ companies is statistically unusual.

**Detection method:**
```
For each person with 3+ directorships:
  1. Apply exclusion list (audit firms, PE, law firms, banks, government)
  2. Calculate average shell_score of directed companies
  3. Flag if: companies >= 5 AND (high_shell > 2 OR avg_shell > 0.5)
```

#### 2.3 Address Clusters

**Rationale:** Multiple companies at the same address combined with shell indicators suggests a registration mill.

**Detection method:**
```
For each address with 2+ companies:
  1. Normalize address (see Address Normalization below)
  2. Count companies registered at address
  3. Calculate average shell_score
  4. Flag if: company_count >= 5 OR (company_count >= 3 AND avg_shell > 0.5)
```

### Address Normalization

Swedish addresses are normalized for clustering:
- Extract and remove c/o prefixes
- Identify PO Box addresses
- Expand street abbreviations (g. → gatan, v. → vägen)
- Normalize postal codes (NNN NN → NNNNN)
- Detect virtual office providers (Regus, Spaces, etc.)

**Cluster key format:**
- PO Box: `BOX-{number}-{postal_code}`
- Street: `{STREET}-{number}-{postal_code}`

---

## 3. Exclusion Lists

### Rationale

Certain entities legitimately appear across many companies and should not be flagged as suspicious:

| Category | Examples | Exclusion Reason |
|----------|----------|------------------|
| **Audit Firms** | E&Y, PWC, KPMG, Deloitte, Grant Thornton, BDO, RSM | Legitimate auditors of many companies |
| **PE/VC Firms** | EQT, Nordic Capital, Investor AB, Kinnevik | Portfolio company board seats |
| **Law Firms** | Mannheimer Swartling, Vinge, Setterwalls | Corporate law, M&A advisory |
| **Banks** | Handelsbanken, SEB, Nordea, Swedbank | Custody, trust services |
| **Government** | State agencies, municipal companies | Public sector entities |

### Implementation

See `halo/intelligence/exclusion_lists.py` for full patterns.

---

## 4. Temporal Sequence Detection

### Concept

Fraud has a playbook. The **order of events** is a signature.

### Event Types

| Event | Source | Description |
|-------|--------|-------------|
| `formed` | formation.date | Company registration |
| `f_skatt_registered` | f_skatt.from | Tax registration |
| `vat_registered` | moms.from | VAT registration |
| `employer_registered` | employer.from | Employer registration |
| `director_added/removed` | DirectsEdge | Director changes |
| `address_changed` | addresses | Address change |
| `konkurs` | status | Bankruptcy |

### Implemented Playbooks

| Playbook | Detection Logic | Severity |
|----------|-----------------|----------|
| `shell_company_indicators` | 3+ shell indicators simultaneously | High/Medium |
| `rapid_formation` | F-skatt within 30 days of formation | Medium |
| `dormant_activation` | Company > 5 years old with single director | Low |

### Future Playbooks (Require More Data)

| Playbook | Sequence | Severity |
|----------|----------|----------|
| `invoice_factory` | formed → f_skatt → NO vat → virtual_address | High |
| `phoenix` | director_removed(A) → formed(B) → konkurs(A) | High |
| `nominee_takeover` | director_removed → director_added → signatory_changed → address_changed | High |

---

## 5. Ground Truth & Validation

### The Problem

Without known fraud cases, we cannot measure precision/recall of our detection.

### Available Sources

| Source | Data | Accessibility |
|--------|------|--------------|
| Ekobrottsmyndigheten | Fraud convictions | Press releases only; no public org number list |
| Domstol.se | Court decisions | Searchable by case number, not company |
| Bolagsverket | Bankruptcies | Does not flag fraud-related bankruptcies |
| Media | Major fraud cases | Company names, need manual matching |

### Proxy Indicators

When conviction data is unavailable:

1. **Quick bankruptcies**: Konkurs within 2 years of formation
2. **Tax debt at bankruptcy**: Large unpaid taxes suggest evasion
3. **Director bans (näringsförbud)**: Post-fraud director prohibitions
4. **Audit disclaimers**: Auditor unable to verify financials

### Recommendation

Collect confirmed fraud cases from:
- Ekobrottsmyndigheten annual reports
- Court case research (mål.se)
- Journalistic investigations
- Academic research (BRÅ, university studies)

---

## 6. Calibration Data

### Current Baselines (2025-12-26, n=8,200)

| Metric | Value | Source |
|--------|-------|--------|
| Shell score high rate | 0.4% | Shell scoring |
| Shell score medium rate | 3.3% | Shell scoring |
| no_employees prevalence | 99.2% | Bolagsverket |
| generic_sni prevalence | 15.5% | Bolagsverket |
| single_director rate | 8.7% | Companies with director data |
| f_skatt_no_vat rate | 1.3% | Bolagsverket |
| recently_formed rate | 4.1% | Formation dates |
| Director roles mean | 1.12 | 2,367 persons |
| Director roles p99 | 2 | Bolagsverket XBRL |

### Coverage

| Data | Coverage | Impact |
|------|----------|--------|
| Director data | 14.9% | Serial director detection limited |
| Address data | 1.3% | Address cluster detection limited |
| Event history | Partial | Temporal playbooks limited |

### Recalibration Schedule

- **Monthly** until allabolag enrichment > 50%
- **Quarterly** once stable

---

## 7. Running Detection

```bash
# Step 1: Shell scoring (updates graph with shell_score)
python scripts/run_shell_scoring.py

# Step 2: Formation agent analysis (uses shell_scores)
python scripts/run_formation_agent_analysis.py

# Step 3: Sequence detection
python scripts/run_sequence_detection.py
```

### Output Files

- `data/shell_scoring_results.json` - Shell score distribution
- `data/formation_agent_analysis.json` - Serial entity analysis
- `data/sequence_detection.json` - Playbook matches
- `data/alerts.json` - Combined alerts for review

---

## 8. Key Files

| File | Purpose |
|------|---------|
| `halo/intelligence/anomaly.py` | Baseline stats, thresholds, scoring weights |
| `halo/intelligence/exclusion_lists.py` | PE, law firms, banks, etc. |
| `halo/intelligence/address_normalizer.py` | Swedish address normalization |
| `halo/intelligence/ground_truth.py` | Validation framework |
| `halo/intelligence/sequence_detector.py` | Playbook definitions |
| `scripts/run_shell_scoring.py` | Calculate shell_score for all companies |
| `scripts/run_formation_agent_analysis.py` | Analyze serial entities |
| `scripts/run_sequence_detection.py` | Detect temporal patterns |
