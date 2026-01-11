# Halo Intelligence Platform

# Archeron: Unified Intelligence Platform

## The Problem

Sweden's criminal economy generates 100-150B SEK annually. 67,500 individuals are connected to criminal networks. Gang violence has made Sweden Europe's leader in gun deaths. 30+ bombings occurred in Stockholm in January 2025 alone.

**The financial extraction is massive:**
- €325M+ confirmed welfare fraud by gang members (likely much higher)
- Welfare fraud profits estimated at 2x the drug trade
- Healthcare/personal assistance sector systematically infiltrated
- Invoice factories generating false deductions worth billions
- VAT carousel fraud exploiting EU trade mechanisms
- Serial bankruptcy fraud stripping assets from creditors

The criminals operate across silos. The defenders are blind.

- **Bolagsverket** sees company registrations but not the network topology
- **Lantmäteriet** sees property ownership but not the pattern of territorial control
- **Försäkringskassan** sees benefit claims but not the shell company extraction scheme
- **Skatteverket** sees tax returns but not the invoice factory network
- **Ekobrottsmyndigheten** investigates cases but lacks proactive detection
- **Polisen** sees incidents but not the corporate structures behind them
- **Housing companies** see disturbances but not the organized crime connection
- **Security firms** see patrol data but share nothing
- **Banks** see transactions but can't connect to criminal networks

Each agency, authority, and company sees their slice. Nobody sees the network.

**Archeron builds the system that sees across the silos.**

---

## The Vision

A sovereign Swedish intelligence platform that autonomously generates actionable insight by fusing data across corporate, property, welfare, financial, and physical domains.

Not a dashboard. Not a database. Not analyst-assisted exploration.

**Autonomous insight generation:**
- What is happening
- What will happen next
- How to interdict it
- Evidence package for action
- Referral package for prosecution

100x over Palantir because the system thinks, not just displays.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT LAYER                                        │
│  Interdiction recommendations, evidence packages, predictions, alerts, referrals│
├─────────────────────────────────────────────────────────────────────────────────┤
│                           INTELLIGENCE ENGINE                                    │
│  Entity resolution │ Graph analysis │ Pattern matching │ Prediction │ Autonomy  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                             FUSION LAYER                                         │
│  Cross-domain correlation │ Temporal sequencing │ Spatial clustering │ Flow     │
├───────────────┬───────────────┬───────────────┬───────────────┬─────────────────┤
│   CORPORATE   │   PROPERTY    │   WELFARE     │   FINANCIAL   │    PHYSICAL    │
│  Bolagsverket │ Lantmäteriet  │ Healthcare Co │  Transactions │  Argus sensors │
│  Annual rpts  │ Addresses     │ Benefit flows │  Kronofogden  │  Frontline cam │
│  Directors    │ Ownership     │ Employment    │  Tax records  │  Incidents     │
│  UBO chains   │ Territorial   │ Fraud signals │  Court cases  │  OSINT feeds   │
└───────────────┴───────────────┴───────────────┴───────────────┴─────────────────┘
```

---

## Data Layers

### Layer 1: Corporate Intelligence

**Sources:**
- Bolagsverket company registry (API + scraping)
- Annual reports (PDF extraction for director/auditor data)
- Ownership chains (Bolagsverket + manual UBO resolution)
- Kronofogden debt records (FOI/partnership)
- Court records (domstol.se)

**Ingestion Pipeline:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Bolagsverket│────▶│  PDF Parser  │────▶│   Entity     │
│  Annual Rpts │     │  (pypdf +    │     │  Extraction  │
│  (500K/year) │     │   regex)     │     │  (NER/rules) │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐     ┌──────────────┐            ▼
│  Company API │────▶│  Structured  │────▶┌──────────────┐
│  (real-time) │     │  Ingestion   │     │   Identity   │
└──────────────┘     └──────────────┘     │  Resolution  │
                                          └──────┬───────┘
                                                 │
                                                 ▼
                                          ┌──────────────┐
                                          │    Graph     │
                                          │   Storage    │
                                          └──────────────┘
```

**Entities Extracted:**
- Companies (org_nr, name, status, dates, address)
- Persons (name, personnummer where available, role, tenure)
- Relationships (director_of, owner_of, auditor_of, signatory_of)

**Patterns Detected:**
| Pattern | Indicators | Risk Level |
|---------|------------|------------|
| Målvaktsbolag (straw man) | Rapid director changes, nominee patterns, address clustering | High |
| Skalbolag (shell) | No employees, minimal revenue, asset stripping | High |
| Phoenix company | Serial bankruptcy, same directors, similar names | High |
| Invoice factory | High turnover, no assets, rapid formation/dissolution | Critical |
| VAT carousel | Cross-border chains, circular transactions | Critical |
| Healthcare infiltration | SNI 86/87/88, vulnerable area addresses, ownership opacity | High |

### Layer 2: Property Intelligence

**Sources:**
- Lantmäteriet property registry
- Address-to-company mapping (SCB, Bolagsverket)
- Municipal "vulnerable area" designations
- Housing company incident data (AEGIS customers)

**Ingestion Pipeline:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Lantmäteriet │────▶│   Address    │────▶│   Geocoding  │
│  Properties  │     │  Normalize   │     │   (PostGIS)  │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐                                  ▼
│  Company     │                           ┌──────────────┐
│  Addresses   │──────────────────────────▶│   Address    │
│ (Bolagsverket)                           │   Graph      │
└──────────────┘                           └──────┬───────┘
                                                  │
┌──────────────┐                                  ▼
│  Incident    │                           ┌──────────────┐
│  Reports     │──────────────────────────▶│  Territorial │
│  (geocoded)  │                           │   Analysis   │
└──────────────┘                           └──────────────┘
```

**Entities:**
- Properties (fastighet_id, coordinates, type, owner)
- Addresses (street, postal code, municipality, coordinates)
- Territorial zones (vulnerable area polygons, gang territory estimates)

**Analysis Capabilities:**
- Address clustering (how many companies at this address?)
- Territorial correlation (incidents near shell company addresses)
- Expansion detection (new registrations in previously clean areas)

### Layer 3: Welfare Intelligence

**Sources:**
- Healthcare company patterns (SNI codes 86, 87, 88 from Bolagsverket)
- Personal assistance provider registrations
- Employment patterns (anomalous headcount vs revenue)
- News/media monitoring for fraud cases

**Detection Focus:**

The welfare fraud vector is estimated at 2x drug trade profits. Criminal networks establish:
- Private healthcare clinics
- Personal assistance agencies
- Vaccination clinics
- Elderly care providers

**Indicators:**
- Company registered in vulnerable area
- Directors with criminal network connections
- Rapid employee count changes
- Revenue/employee ratio anomalies
- Ownership chains terminating in opaque structures

### Layer 4: Financial Intelligence

**Sources:**
- Bolagsverket financial statements (annual reports, revenue, assets)
- Skatteverket public records (employer registrations, VAT registrations)
- Kronofogden (debt enforcement, payment defaults, bankruptcies)
- Bank transaction patterns (via partnership or regulatory access)
- Ekobrottsmyndigheten case law (training data for patterns)
- domstol.se court records (fraud convictions, disputes)
- EU VAT Information Exchange System (VIES) for cross-border patterns
- Suspicious Activity Reports (FIU-Sverige, requires partnership)

**Ingestion Pipeline:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Annual      │────▶│  Financial   │────▶│   Anomaly    │
│  Reports     │     │  Extraction  │     │  Detection   │
│  (PDF/XBRL)  │     │  (revenue,   │     │  (ratios,    │
│              │     │   assets,    │     │   trends)    │
│              │     │   employees) │     │              │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐     ┌──────────────┐            ▼
│ Kronofogden  │────▶│   Distress   │────▶┌──────────────┐
│  Defaults    │     │   Signals    │     │   Risk       │
└──────────────┘     └──────────────┘     │   Scoring    │
                                          └──────┬───────┘
┌──────────────┐     ┌──────────────┐            │
│  Transaction │────▶│   Flow       │────────────┤
│  Data        │     │   Analysis   │            │
└──────────────┘     └──────────────┘            ▼
                                          ┌──────────────┐
                                          │   Fraud      │
                                          │   Patterns   │
                                          └──────────────┘
```

**Financial Crime Categories:**

| Category | Description | Annual Estimate |
|----------|-------------|-----------------|
| Welfare fraud | Healthcare infiltration, assistance fraud, benefit extraction | €325M+ confirmed, likely 2x drug trade |
| Tax fraud | VAT carousels, invoice factories, undeclared income | 100-150B SEK criminal economy largely untaxed |
| Money laundering | Cash businesses, real estate, trade-based | Flows through all other categories |
| Bankruptcy fraud | Asset stripping, phoenix companies, creditor evasion | Unknown, systematic |
| Procurement fraud | False invoicing to public sector, bid rigging | Unknown, likely significant |

**Detection Patterns:**

```python
financial_crime_patterns = {
    'invoice_factory': {
        'description': 'Company exists solely to generate false invoices for tax deduction',
        'indicators': [
            'High revenue relative to assets',
            'No physical premises',
            'Rapid formation/dissolution cycle',
            'Directors with multiple similar companies',
            'Customer concentration (few buyers, high volume)',
            'No employees despite significant revenue'
        ],
        'graph_query': '''
            MATCH (c:Company)
            WHERE c.revenue > 5000000
            AND c.employees < 2
            AND c.assets < 100000
            AND c.age_months < 24
            MATCH (p:Person)-[:DIRECTOR_OF]->(c)
            MATCH (p)-[:DIRECTOR_OF]->(c2:Company)
            WHERE c2.status = 'DISSOLVED'
            AND c2.dissolution_type = 'BANKRUPTCY'
            RETURN c, p, collect(c2) as prior_bankruptcies
        ''',
        'confidence_threshold': 0.80
    },
    
    'vat_carousel': {
        'description': 'Circular trading exploiting VAT refund mechanisms',
        'indicators': [
            'Cross-border transactions with EU companies',
            'Rapid inventory turnover with no physical handling',
            'Circular ownership or trading patterns',
            'Missing trader in chain',
            'Goods that exist only on paper'
        ],
        'graph_query': '''
            MATCH path = (c1:Company)-[:TRADES_WITH*2..5]->(c1)
            WHERE ALL(c IN nodes(path) WHERE c.country IN ['SE', 'DK', 'DE', 'PL', 'LT'])
            AND ANY(c IN nodes(path) WHERE c.vat_registered = false OR c.status = 'DISSOLVED')
            RETURN path, [c IN nodes(path) | c.vat_claimed] as vat_amounts
        ''',
        'confidence_threshold': 0.85
    },
    
    'money_laundering_front': {
        'description': 'Cash-intensive business used to integrate illicit funds',
        'indicators': [
            'Cash-heavy industry (restaurant, car wash, salon, kiosk)',
            'Revenue anomalous for location/size',
            'Owner network connects to known criminal entities',
            'Located in vulnerable area',
            'Multiple similar businesses under same control'
        ],
        'graph_query': '''
            MATCH (c:Company)-[:REGISTERED_AT]->(a:Address)
            MATCH (a)-[:IN_ZONE]->(z:Zone {type: 'vulnerable_area'})
            WHERE c.sni_code IN ['56.10', '45.20', '96.02', '47.11']  -- Restaurant, car repair, salon, kiosk
            AND c.cash_ratio > 0.7
            MATCH (p:Person)-[:DIRECTOR_OF]->(c)
            MATCH (p)-[:DIRECTOR_OF]->(c2:Company)
            WHERE c2.risk_score > 0.6
            RETURN c, p, collect(c2) as connected_risky_companies
        ''',
        'confidence_threshold': 0.70
    },
    
    'bankruptcy_fraud_chain': {
        'description': 'Serial bankruptcies to evade creditors while continuing operations',
        'indicators': [
            'Director appears in multiple bankruptcies',
            'New company formed shortly before/after bankruptcy',
            'Similar name, address, or business activity',
            'Assets transferred pre-bankruptcy',
            'Same customers/suppliers continue with new entity'
        ],
        'graph_query': '''
            MATCH (p:Person)-[:DIRECTOR_OF]->(c1:Company {status: 'BANKRUPT'})
            MATCH (p)-[:DIRECTOR_OF]->(c2:Company)
            WHERE c2.formed_date > c1.bankruptcy_date - duration('P90D')
            AND c2.formed_date < c1.bankruptcy_date + duration('P180D')
            AND (c2.sni_code = c1.sni_code OR 
                 levenshtein(c2.name, c1.name) < 5 OR
                 c2.address = c1.address)
            WITH p, collect(c1) as bankruptcies, collect(c2) as phoenix_companies
            WHERE size(bankruptcies) > 1
            RETURN p, bankruptcies, phoenix_companies
        ''',
        'confidence_threshold': 0.85
    },
    
    'procurement_fraud_network': {
        'description': 'Coordinated bidding or false invoicing to public sector',
        'indicators': [
            'Multiple companies bidding are connected via directors/owners',
            'Bid prices suspiciously close or follow pattern',
            'Winner subcontracts to losing bidders',
            'Invoices for services not rendered',
            'Shell companies in supply chain'
        ],
        'graph_query': '''
            MATCH (c1:Company)-[:BID_ON]->(tender:Tender)
            MATCH (c2:Company)-[:BID_ON]->(tender)
            WHERE c1 <> c2
            MATCH (p:Person)-[:DIRECTOR_OF]->(c1)
            MATCH (p)-[:DIRECTOR_OF]->(c2)
            RETURN tender, c1, c2, p
        ''',
        'requires_data': 'Public procurement records (Upphandlingsmyndigheten)',
        'confidence_threshold': 0.90
    },
    
    'welfare_extraction_scheme': {
        'description': 'Systematic extraction of public funds through fake services',
        'indicators': [
            'Healthcare/assistance company in vulnerable area',
            'Employee count doesn\'t match service volume',
            'Employees are also clients or family of directors',
            'Directors connected to criminal networks',
            'Rapid growth without infrastructure',
            'Multiple companies at same address doing same thing'
        ],
        'graph_query': '''
            MATCH (c:Company)
            WHERE c.sni_code STARTS WITH '86' OR c.sni_code STARTS WITH '87' OR c.sni_code STARTS WITH '88'
            MATCH (c)-[:REGISTERED_AT]->(a:Address)
            MATCH (c2:Company)-[:REGISTERED_AT]->(a)
            WHERE c2.sni_code STARTS WITH '86' OR c2.sni_code STARTS WITH '87' OR c2.sni_code STARTS WITH '88'
            AND c <> c2
            WITH a, collect(DISTINCT c) + collect(DISTINCT c2) as welfare_companies
            WHERE size(welfare_companies) > 2
            MATCH (p:Person)-[:DIRECTOR_OF]->(wc) WHERE wc IN welfare_companies
            WITH a, welfare_companies, collect(DISTINCT p) as shared_directors
            WHERE size(shared_directors) < size(welfare_companies)  -- Some director overlap but not 1:1
            RETURN a, welfare_companies, shared_directors
        ''',
        'confidence_threshold': 0.75
    }
}
```

**Financial Anomaly Detection:**

```python
class FinancialAnomalyDetector:
    """
    Statistical detection of financial irregularities.
    """
    
    def __init__(self):
        self.industry_benchmarks = self.load_sni_benchmarks()
    
    def analyze_company(self, company_id):
        """
        Multi-dimensional financial health and fraud indicators.
        """
        financials = self.get_financial_history(company_id)
        industry = self.get_industry_peers(company_id)
        
        anomalies = []
        
        # Benford's Law analysis on revenue figures
        if self.benford_deviation(financials.revenues) > 0.25:
            anomalies.append({
                'type': 'benford_violation',
                'description': 'Revenue figures deviate from expected distribution',
                'severity': 'high',
                'indicator_of': ['accounting_fraud', 'fabricated_invoices']
            })
        
        # Revenue/employee ratio vs industry
        rev_per_employee = financials.revenue / max(financials.employees, 1)
        industry_median = industry.median_revenue_per_employee
        if rev_per_employee > industry_median * 3:
            anomalies.append({
                'type': 'revenue_employee_anomaly',
                'description': f'Revenue per employee {rev_per_employee/industry_median:.1f}x industry median',
                'severity': 'medium',
                'indicator_of': ['invoice_factory', 'undeclared_employees', 'money_laundering']
            })
        
        # Asset stripping detection (pre-bankruptcy pattern)
        if self.detect_asset_decline(financials):
            anomalies.append({
                'type': 'asset_stripping',
                'description': 'Rapid asset decline while liabilities stable',
                'severity': 'high',
                'indicator_of': ['bankruptcy_fraud', 'creditor_evasion']
            })
        
        # Circular transaction detection
        if self.detect_circular_flows(company_id):
            anomalies.append({
                'type': 'circular_transactions',
                'description': 'Money flowing in circles through related entities',
                'severity': 'critical',
                'indicator_of': ['vat_carousel', 'money_laundering', 'tax_fraud']
            })
        
        # Sudden activity spikes
        if self.detect_activity_spike(financials):
            anomalies.append({
                'type': 'activity_spike',
                'description': 'Dramatic increase in activity inconsistent with history',
                'severity': 'medium',
                'indicator_of': ['money_laundering', 'invoice_factory_activation']
            })
        
        return {
            'company_id': company_id,
            'anomalies': anomalies,
            'risk_score': self.compute_risk_score(anomalies),
            'recommended_investigation': self.prioritize_investigation(anomalies)
        }
    
    def benford_deviation(self, numbers):
        """
        Compare first-digit distribution to Benford's Law.
        Fabricated numbers often fail this test.
        """
        expected = {1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097, 
                    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046}
        observed = self.first_digit_distribution(numbers)
        
        # Chi-squared test
        chi_sq = sum((observed.get(d, 0) - expected[d])**2 / expected[d] 
                     for d in range(1, 10))
        return chi_sq
    
    def detect_circular_flows(self, company_id):
        """
        Find money returning to origin through intermediaries.
        """
        cycles = self.graph.query('''
            MATCH path = (c:Company {id: $company_id})-[:PAYS*2..6]->(c)
            WHERE ALL(r IN relationships(path) WHERE r.amount > 100000)
            RETURN path, 
                   reduce(total = 0, r IN relationships(path) | total + r.amount) as cycle_volume
        ''', company_id=company_id)
        
        return len(cycles) > 0
```

**Cross-Domain Financial Correlation:**

```python
class FinancialFusionEngine:
    """
    Correlates financial signals with other intelligence layers.
    """
    
    def correlate_financial_physical(self, company_id):
        """
        Does physical activity match reported financials?
        """
        company = self.get_company(company_id)
        address = company.registered_address
        
        # Get physical observation data
        foot_traffic = self.frontline.get_foot_traffic(address, days=90)
        vehicle_activity = self.argus.get_vehicle_detections(address, days=90)
        operating_hours = self.frontline.get_activity_hours(address, days=90)
        
        # Compare to reported financials
        discrepancies = []
        
        if company.sni_code == '56.10':  # Restaurant
            expected_traffic = self.model_expected_traffic(company.revenue)
            if foot_traffic.daily_average < expected_traffic * 0.3:
                discrepancies.append({
                    'type': 'activity_revenue_mismatch',
                    'description': f'Foot traffic {foot_traffic.daily_average} vs expected {expected_traffic} for reported revenue',
                    'implication': 'Possible money laundering or fabricated revenue'
                })
        
        if company.employees > 10:
            expected_vehicles = company.employees * 0.3  # Rough estimate
            if vehicle_activity.unique_daily < expected_vehicles * 0.2:
                discrepancies.append({
                    'type': 'employee_activity_mismatch',
                    'description': f'Vehicle activity suggests fewer actual employees than reported',
                    'implication': 'Possible ghost employees or welfare fraud'
                })
        
        return discrepancies
    
    def trace_money_flow(self, entity_id, depth=3):
        """
        Follow money through the network.
        """
        flows = self.graph.query('''
            MATCH path = (start:Entity {id: $entity_id})-[:PAYS|OWNS|CONTROLS*1..$depth]->(end:Entity)
            WHERE end.jurisdiction IN ['CY', 'MT', 'AE', 'PA', 'VG']  -- Tax havens
               OR end.type = 'SHELL_COMPANY'
               OR end.risk_score > 0.7
            RETURN path, 
                   [n IN nodes(path) | n.name] as entity_chain,
                   [r IN relationships(path) | {type: type(r), amount: r.amount}] as flow_details
        ''', entity_id=entity_id, depth=depth)
        
        return {
            'entity_id': entity_id,
            'suspicious_flows': flows,
            'total_value_to_high_risk': sum(f.amount for f in flows if f.end.risk_score > 0.7),
            'jurisdictions_touched': set(n.jurisdiction for path in flows for n in path.nodes)
        }
```

### Layer 5: Physical Intelligence

**Sources:**
- Argus acoustic sensors (gunshots, explosions, vehicles, drones)
- Frontline camera network (vehicle tracking, crowd analysis)
- Housing company incident reports (AEGIS)
- Security firm patrol data
- Police blotter / public incident reports
- OSINT (news, social media)

**Ingestion Pipeline:**
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    Argus     │────▶│    Edge      │────▶│   Central    │
│   Sensors    │     │  Inference   │     │   Fusion     │
│  (nRF5340)   │     │  (200KB model)    │   Engine     │
└──────────────┘     └──────────────┘     └──────┬───────┘
                                                  │
┌──────────────┐     ┌──────────────┐            │
│  Frontline   │────▶│   Video      │────────────┤
│   Cameras    │     │  Analysis    │            │
└──────────────┘     └──────────────┘            │
                                                  │
┌──────────────┐                                  │
│   Incident   │─────────────────────────────────┤
│   Reports    │                                  │
└──────────────┘                                  │
                                                  ▼
                                          ┌──────────────┐
                                          │   Event      │
                                          │   Store      │
                                          │ (TimescaleDB)│
                                          └──────────────┘
```

**Event Types:**
- IMPULSIVE (gunshot, explosion)
- VEHICLE (engine signature, anomalous pattern)
- DRONE (rotor acoustic signature)
- CROWD (assembly, dispersal, aggression)
- INCIDENT (reported disturbance, crime, property damage)

---

## Intelligence Engine

### Entity Resolution

The core capability. Connecting identities across data sources.

**Problem:** 
- "Johan Andersson" appears in 47 company registrations
- Which are the same person?
- Personnummer often unavailable in public records

**Approach:**
```python
class EntityResolver:
    """
    Probabilistic identity resolution across data sources.
    """
    
    def __init__(self):
        self.blocking_keys = [
            'exact_name',
            'phonetic_name',  # Soundex/Metaphone
            'birth_year',     # When available
            'address_cluster'
        ]
    
    def candidate_pairs(self, entity, corpus):
        """
        Blocking: reduce O(n²) to O(n) by only comparing
        entities that share at least one blocking key.
        """
        candidates = set()
        for key_type in self.blocking_keys:
            key = self.extract_key(entity, key_type)
            candidates.update(self.index[key_type].get(key, []))
        return candidates
    
    def similarity_score(self, e1, e2):
        """
        Weighted feature comparison.
        Returns probability these are the same entity.
        """
        features = {
            'name_jaro_winkler': 0.3,
            'address_overlap': 0.2,
            'temporal_overlap': 0.15,  # Were they active same years?
            'network_overlap': 0.25,   # Shared co-directors?
            'role_similarity': 0.1
        }
        
        score = 0
        for feature, weight in features.items():
            score += self.compute_feature(e1, e2, feature) * weight
        
        return score
    
    def resolve(self, threshold=0.85):
        """
        Cluster entities into resolved identities.
        """
        # Union-find with probabilistic edges
        pass
```

**Graph Storage:**

PostgreSQL with ltree + PostGIS for initial implementation. Migrate to dedicated graph DB (Neo4j/Apache AGE) when query complexity demands it.

```sql
-- Core entity tables
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    entity_type VARCHAR(50),  -- 'person', 'company', 'property', 'event'
    canonical_name TEXT,
    attributes JSONB,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- Relationships with provenance
CREATE TABLE relationships (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES entities(id),
    target_id UUID REFERENCES entities(id),
    relationship_type VARCHAR(50),  -- 'director_of', 'owner_of', 'located_at', 'incident_at'
    confidence FLOAT,
    valid_from DATE,
    valid_to DATE,
    provenance JSONB,  -- Source document, extraction method, timestamp
    created_at TIMESTAMPTZ
);

-- Spatial indexing
CREATE INDEX idx_entities_location ON entities USING GIST (
    (attributes->>'coordinates')::geometry
);

-- Graph traversal optimization
CREATE INDEX idx_relationships_source ON relationships(source_id, relationship_type);
CREATE INDEX idx_relationships_target ON relationships(target_id, relationship_type);
```

### Pattern Library

Codified knowledge of Swedish organized crime modus operandi.

```python
class PatternLibrary:
    """
    Pattern definitions for organized crime detection.
    Each pattern has:
    - Graph structure (what relationships to look for)
    - Temporal signature (how it evolves over time)
    - Confidence thresholds
    - Evidence requirements for court-grade output
    """
    
    patterns = {
        'shell_company_network': {
            'description': 'Network of companies with shared directors, minimal operations',
            'graph_query': '''
                MATCH (p:Person)-[:DIRECTOR_OF]->(c1:Company)
                MATCH (p)-[:DIRECTOR_OF]->(c2:Company)
                WHERE c1 <> c2
                AND c1.employee_count < 2
                AND c2.employee_count < 2
                AND c1.revenue < 500000
                AND c2.revenue < 500000
                WITH p, collect(DISTINCT c1) + collect(DISTINCT c2) as companies
                WHERE size(companies) > 3
                RETURN p, companies
            ''',
            'temporal': 'Companies formed within 12 months of each other',
            'confidence_threshold': 0.75,
            'evidence_fields': ['director_name', 'company_names', 'formation_dates', 'addresses']
        },
        
        'territorial_extortion': {
            'description': 'Physical incidents clustered around business addresses',
            'graph_query': '''
                MATCH (e:Event {type: 'IMPULSIVE'})-[:LOCATED_AT]->(a:Address)
                MATCH (c:Company)-[:REGISTERED_AT]->(a)
                WHERE e.timestamp > datetime() - duration('P90D')
                WITH a, count(e) as incident_count, collect(c) as companies
                WHERE incident_count > 2
                RETURN a, incident_count, companies
            ''',
            'temporal': 'Escalating frequency over 30-90 days',
            'confidence_threshold': 0.80,
            'evidence_fields': ['incident_times', 'incident_types', 'address', 'company_names']
        },
        
        'healthcare_infiltration': {
            'description': 'Healthcare company with criminal network indicators',
            'graph_query': '''
                MATCH (c:Company)
                WHERE c.sni_code STARTS WITH '86' 
                   OR c.sni_code STARTS WITH '87'
                   OR c.sni_code STARTS WITH '88'
                MATCH (c)-[:REGISTERED_AT]->(a:Address)
                MATCH (a)-[:IN_ZONE]->(z:Zone {type: 'vulnerable_area'})
                MATCH (p:Person)-[:DIRECTOR_OF]->(c)
                MATCH (p)-[:DIRECTOR_OF]->(c2:Company)
                WHERE c2.risk_score > 0.7
                RETURN c, p, c2, a, z
            ''',
            'temporal': 'Company formed within 24 months',
            'confidence_threshold': 0.70,
            'evidence_fields': ['company_name', 'sni_code', 'directors', 'connected_companies', 'address', 'zone']
        }
    }
```

### Prediction Engine

Moving from detection to prediction.

```python
class PredictionEngine:
    """
    Temporal pattern analysis for predictive intelligence.
    """
    
    def __init__(self, graph_db, event_store):
        self.graph = graph_db
        self.events = event_store  # TimescaleDB
    
    def extortion_escalation_probability(self, address_id, horizon_days=30):
        """
        Given an address with recent incidents, what's the probability
        of escalation (bombing, arson) within the horizon?
        
        Based on observed patterns:
        1. Initial contact (threat, minor vandalism)
        2. Demonstration (small explosive, broken windows)
        3. Escalation (arson, significant explosive)
        4. Resolution (payment or destruction)
        """
        
        # Get incident history for this address
        incidents = self.events.query(f'''
            SELECT * FROM events 
            WHERE address_id = '{address_id}'
            AND timestamp > NOW() - INTERVAL '180 days'
            ORDER BY timestamp
        ''')
        
        if not incidents:
            return {'probability': 0.05, 'confidence': 'low', 'basis': 'no_history'}
        
        # Classify current stage
        stage = self.classify_extortion_stage(incidents)
        
        # Transition probabilities (from training data)
        transition_matrix = {
            'stage_1': {'escalate': 0.40, 'stable': 0.45, 'resolve': 0.15},
            'stage_2': {'escalate': 0.55, 'stable': 0.30, 'resolve': 0.15},
            'stage_3': {'escalate': 0.70, 'stable': 0.15, 'resolve': 0.15},
        }
        
        # Time-adjusted probability
        days_since_last = (datetime.now() - incidents[-1].timestamp).days
        time_factor = min(1.0, days_since_last / 14)  # Escalation more likely if recent
        
        base_prob = transition_matrix[stage]['escalate']
        adjusted_prob = base_prob * (1.5 - time_factor)  # Recent = higher risk
        
        return {
            'probability': min(0.95, adjusted_prob),
            'confidence': 'high' if len(incidents) > 3 else 'medium',
            'current_stage': stage,
            'days_since_last_incident': days_since_last,
            'recommended_action': self.recommend_action(stage, adjusted_prob)
        }
    
    def recommend_action(self, stage, probability):
        if probability > 0.7:
            return {
                'urgency': 'critical',
                'actions': [
                    'Notify property owner immediately',
                    'Increase physical security presence',
                    'Alert local police district',
                    'Document all business registrations at address'
                ]
            }
        elif probability > 0.4:
            return {
                'urgency': 'high',
                'actions': [
                    'Flag for monitoring',
                    'Review connected addresses for pattern',
                    'Prepare evidence package'
                ]
            }
        else:
            return {
                'urgency': 'monitor',
                'actions': ['Continue passive monitoring']
            }
```

### Fusion Engine

The cross-domain correlation that creates 100x value.

```python
class FusionEngine:
    """
    Correlates intelligence across all five data layers.
    This is where insight emerges.
    """
    
    def __init__(self, graph_db, event_store, financial_analyzer):
        self.graph = graph_db
        self.events = event_store
        self.financial = financial_analyzer
    
    def correlate_incident(self, event):
        """
        When a physical event occurs, immediately enrich with
        corporate/property/welfare/financial intelligence.
        """
        
        # 1. Geocode and find address
        address = self.geo.reverse_geocode(event.coordinates)
        
        # 2. What companies are registered here?
        companies = self.graph.query('''
            MATCH (c:Company)-[:REGISTERED_AT]->(a:Address {id: $addr_id})
            RETURN c
        ''', addr_id=address.id)
        
        # 3. Who controls these companies?
        controllers = []
        for company in companies:
            network = self.graph.query('''
                MATCH (p:Person)-[:DIRECTOR_OF|OWNER_OF*1..3]->(c:Company {id: $company_id})
                RETURN p, relationships
            ''', company_id=company.id)
            controllers.extend(network)
        
        # 4. What other addresses do these controllers touch?
        related_addresses = self.graph.query('''
            MATCH (p:Person {id: $person_ids})-[:DIRECTOR_OF]->(c:Company)-[:REGISTERED_AT]->(a:Address)
            RETURN DISTINCT a
        ''', person_ids=[c.id for c in controllers])
        
        # 5. What incidents have occurred at related addresses?
        related_incidents = self.events.query('''
            SELECT * FROM events
            WHERE address_id = ANY($addr_ids)
            AND timestamp > NOW() - INTERVAL '180 days'
        ''', addr_ids=[a.id for a in related_addresses])
        
        # 6. Financial intelligence on all related companies
        financial_intel = []
        for company in companies:
            financial_intel.append(self.financial.analyze_company(company.id))
        
        # 7. Pattern match across all domains
        patterns_matched = self.pattern_library.match_all({
            'trigger_event': event,
            'address': address,
            'companies': companies,
            'controllers': controllers,
            'related_addresses': related_addresses,
            'related_incidents': related_incidents,
            'financial_anomalies': financial_intel
        })
        
        # 8. Generate insight
        return {
            'event': event,
            'enrichment': {
                'companies_at_address': len(companies),
                'controller_network_size': len(set(controllers)),
                'related_addresses': len(related_addresses),
                'related_incidents_180d': len(related_incidents),
                'financial_anomalies_detected': sum(len(f['anomalies']) for f in financial_intel)
            },
            'patterns': patterns_matched,
            'risk_score': self.compute_risk_score(patterns_matched),
            'predictions': self.prediction_engine.predict_all(address.id),
            'recommended_actions': self.generate_recommendations(patterns_matched),
            'referral_ready': self.check_referral_threshold(patterns_matched)
        }
    
    def proactive_financial_scan(self):
        """
        Continuous scanning for financial crime patterns.
        Runs without incident trigger.
        """
        
        # Invoice factories appearing
        new_invoice_factories = self.pattern_library.scan('invoice_factory', 
            since=self.last_scan_time)
        
        # VAT carousel indicators
        vat_patterns = self.pattern_library.scan('vat_carousel',
            since=self.last_scan_time)
        
        # Welfare extraction schemes
        welfare_schemes = self.pattern_library.scan('welfare_extraction_scheme',
            since=self.last_scan_time)
        
        # Bankruptcy fraud chains
        phoenix_companies = self.pattern_library.scan('bankruptcy_fraud_chain',
            since=self.last_scan_time)
        
        # Money laundering fronts
        ml_fronts = self.pattern_library.scan('money_laundering_front',
            since=self.last_scan_time)
        
        # Aggregate and prioritize
        all_detections = (new_invoice_factories + vat_patterns + 
                         welfare_schemes + phoenix_companies + ml_fronts)
        
        prioritized = sorted(all_detections, 
                            key=lambda x: x['estimated_value'] * x['confidence'],
                            reverse=True)
        
        # Generate autonomous alerts
        for detection in prioritized[:20]:  # Top 20 by impact
            if detection['confidence'] > 0.75:
                self.alert_engine.create_alert({
                    'type': 'proactive_financial_detection',
                    'pattern': detection['pattern_name'],
                    'entities': detection['entities'],
                    'estimated_value': detection['estimated_value'],
                    'confidence': detection['confidence'],
                    'evidence_package': self.evidence_generator.create(detection),
                    'recommended_action': self.recommend_referral(detection)
                })
        
        return prioritized
    
    def recommend_referral(self, detection):
        """
        Determine appropriate authority for referral.
        """
        referral_map = {
            'invoice_factory': 'Skatteverket',
            'vat_carousel': 'Skatteverket + Ekobrottsmyndigheten',
            'welfare_extraction_scheme': 'Försäkringskassan + Ekobrottsmyndigheten',
            'bankruptcy_fraud_chain': 'Ekobrottsmyndigheten',
            'money_laundering_front': 'FIU-Sverige + Polisen',
            'healthcare_infiltration': 'IVO + Ekobrottsmyndigheten',
            'territorial_extortion': 'Polisen'
        }
        
        return {
            'primary_authority': referral_map.get(detection['pattern_name'], 'Ekobrottsmyndigheten'),
            'evidence_ready': detection['confidence'] > 0.80,
            'estimated_recovery': detection['estimated_value'] * 0.3,  # Conservative
            'priority': 'critical' if detection['estimated_value'] > 10000000 else 'high'
        }
```

---

## Output Layer

### Evidence Packages

Court-grade documentation with full provenance chain.

```python
class EvidencePackage:
    """
    Generates documentation suitable for:
    - Police referral
    - Prosecutor briefing
    - Regulatory action
    - Insurance claim
    """
    
    def __init__(self, investigation_id):
        self.id = investigation_id
        self.entities = []
        self.relationships = []
        self.events = []
        self.documents = []  # Source PDFs, screenshots, etc.
        self.chain_of_custody = []
    
    def add_evidence(self, item, source, extraction_method, timestamp):
        """
        Every piece of evidence includes provenance.
        """
        self.chain_of_custody.append({
            'item_hash': hash(item),
            'source': source,  # 'bolagsverket_api', 'annual_report_pdf', 'argus_sensor'
            'extraction_method': extraction_method,
            'timestamp': timestamp,
            'system_version': self.get_system_version()
        })
    
    def export_pdf(self):
        """
        Generate formal evidence package.
        """
        pass
    
    def export_police_format(self):
        """
        Swedish police system compatible format.
        """
        pass
```

### Autonomous Alerts

Not waiting for analysts to query.

```python
class AlertEngine:
    """
    Proactive notification when patterns emerge.
    """
    
    alert_rules = [
        {
            'name': 'new_shell_at_monitored_address',
            'trigger': 'company_registered',
            'condition': lambda e: e.address_id in monitored_addresses 
                         and e.company.matches_shell_indicators(),
            'priority': 'high',
            'action': 'notify_property_owner'
        },
        {
            'name': 'extortion_escalation_imminent',
            'trigger': 'incident_created',
            'condition': lambda e: prediction_engine.extortion_probability(e.address_id) > 0.7,
            'priority': 'critical',
            'action': 'notify_all_stakeholders'
        },
        {
            'name': 'network_expansion_detected',
            'trigger': 'relationship_created',
            'condition': lambda e: e.source_entity.risk_score > 0.8 
                         and e.relationship_type == 'director_of',
            'priority': 'medium',
            'action': 'flag_for_review'
        }
    ]
```

---

## Referral Pipeline

### Autonomous Case Generation

The system doesn't just detect — it builds prosecution-ready cases.

```python
class ReferralPipeline:
    """
    Generates referral packages for Swedish authorities.
    Each authority has specific requirements and thresholds.
    """
    
    authority_specs = {
        'Ekobrottsmyndigheten': {
            'jurisdiction': ['invoice_factory', 'vat_carousel', 'bankruptcy_fraud', 
                           'money_laundering', 'accounting_fraud'],
            'threshold_sek': 500000,
            'evidence_requirements': [
                'company_chain_documentation',
                'director_network_analysis',
                'financial_flow_diagram',
                'timeline_of_events',
                'source_document_references'
            ],
            'format': 'EBM_REFERRAL_2024'
        },
        
        'Skatteverket': {
            'jurisdiction': ['vat_fraud', 'invoice_factory', 'undeclared_income',
                           'false_deductions'],
            'threshold_sek': 100000,
            'evidence_requirements': [
                'vat_analysis',
                'transaction_summary',
                'company_structure',
                'anomaly_documentation'
            ],
            'format': 'SKV_KONTROLLUPPGIFT'
        },
        
        'Försäkringskassan': {
            'jurisdiction': ['welfare_fraud', 'assistance_fraud', 'benefit_extraction'],
            'threshold_sek': 50000,
            'evidence_requirements': [
                'company_beneficiary_analysis',
                'employment_verification_gaps',
                'address_clustering',
                'director_network'
            ],
            'format': 'FK_MISSTANKE'
        },
        
        'FIU_Sverige': {
            'jurisdiction': ['money_laundering', 'terrorist_financing', 
                           'suspicious_transactions'],
            'threshold_sek': 0,  # No threshold for SAR
            'evidence_requirements': [
                'transaction_pattern_analysis',
                'beneficial_owner_chain',
                'risk_indicators',
                'source_of_funds_analysis'
            ],
            'format': 'GOAML_SAR'
        },
        
        'IVO': {
            'jurisdiction': ['healthcare_fraud', 'care_quality_violations',
                           'unlicensed_practice'],
            'threshold_sek': 0,
            'evidence_requirements': [
                'license_verification',
                'staff_qualification_analysis',
                'patient_safety_indicators',
                'billing_anomalies'
            ],
            'format': 'IVO_ANMALAN'
        },
        
        'Polisen': {
            'jurisdiction': ['extortion', 'violence', 'organized_crime',
                           'drug_trafficking'],
            'threshold_sek': 0,
            'evidence_requirements': [
                'incident_timeline',
                'network_visualization',
                'territorial_analysis',
                'threat_assessment'
            ],
            'format': 'POLISEN_UNDERRATTELSE'
        }
    }
    
    def generate_referral(self, detection):
        """
        Create authority-specific referral package.
        """
        # Determine appropriate authority
        authority = self.select_authority(detection)
        spec = self.authority_specs[authority]
        
        # Check threshold
        if detection['estimated_value'] < spec['threshold_sek']:
            return {'status': 'below_threshold', 'authority': authority}
        
        # Compile evidence package
        evidence = self.compile_evidence(detection, spec['evidence_requirements'])
        
        # Generate formatted referral
        referral = {
            'id': uuid4(),
            'authority': authority,
            'format': spec['format'],
            'created_at': datetime.now(),
            'detection_id': detection['id'],
            'pattern_type': detection['pattern_name'],
            'confidence': detection['confidence'],
            'estimated_value': detection['estimated_value'],
            'entities': self.extract_entity_summary(detection),
            'evidence_package': evidence,
            'provenance_chain': self.build_provenance(detection),
            'recommended_priority': self.assess_priority(detection)
        }
        
        # Validate completeness
        if self.validate_referral(referral, spec):
            referral['status'] = 'ready_for_submission'
        else:
            referral['status'] = 'needs_review'
            referral['missing_elements'] = self.identify_gaps(referral, spec)
        
        return referral
    
    def build_provenance(self, detection):
        """
        Full chain of custody for evidence.
        Critical for court admissibility.
        """
        provenance = []
        
        for evidence_item in detection['evidence']:
            provenance.append({
                'item_id': evidence_item['id'],
                'source': evidence_item['source'],
                'retrieval_timestamp': evidence_item['retrieved_at'],
                'retrieval_method': evidence_item['method'],
                'hash': sha256(evidence_item['content']),
                'system_version': self.system_version,
                'transformation_log': evidence_item.get('transformations', [])
            })
        
        return provenance
    
    def priority_queue(self):
        """
        Ranked list of pending referrals by impact.
        """
        pending = self.get_pending_referrals()
        
        # Score by: value * confidence * urgency_factor
        def score(r):
            urgency = 2.0 if r['pattern_type'] in ['extortion', 'violence'] else 1.0
            return r['estimated_value'] * r['confidence'] * urgency
        
        return sorted(pending, key=score, reverse=True)
```

### Impact Tracking

```python
class ImpactTracker:
    """
    Measures system effectiveness against organized crime.
    """
    
    def track_referral_outcome(self, referral_id, outcome):
        """
        Record what happened after referral.
        """
        outcomes = {
            'investigation_opened': 1.0,
            'charges_filed': 2.0,
            'conviction': 3.0,
            'assets_seized': 'variable',
            'declined': 0.0,
            'merged_with_existing': 0.5
        }
        
        self.db.update_referral(referral_id, {
            'outcome': outcome['type'],
            'outcome_date': outcome['date'],
            'value_recovered': outcome.get('assets_seized', 0),
            'sentences': outcome.get('sentences', []),
            'feedback': outcome.get('authority_feedback')
        })
    
    def generate_impact_report(self, period='quarter'):
        """
        Aggregate impact metrics.
        """
        referrals = self.get_referrals_for_period(period)
        
        return {
            'period': period,
            'referrals_generated': len(referrals),
            'referrals_accepted': len([r for r in referrals if r['outcome'] != 'declined']),
            'investigations_opened': len([r for r in referrals if r['outcome'] == 'investigation_opened']),
            'charges_filed': len([r for r in referrals if r['outcome'] == 'charges_filed']),
            'convictions': len([r for r in referrals if r['outcome'] == 'conviction']),
            'total_value_detected': sum(r['estimated_value'] for r in referrals),
            'total_value_recovered': sum(r.get('value_recovered', 0) for r in referrals),
            'patterns_by_frequency': self.count_by_pattern(referrals),
            'authorities_by_volume': self.count_by_authority(referrals),
            'average_confidence': sum(r['confidence'] for r in referrals) / len(referrals),
            'time_to_detection_avg': self.avg_detection_time(referrals)
        }
```

---

## Market Entry: AEGIS

### Why Housing Companies First

| Factor | Rationale |
|--------|-----------|
| Acute pain | Extortion, property damage, tenant safety |
| Data access | They have incident logs, we aggregate |
| Decision speed | Property manager, not committee |
| Network effects | Each customer's data improves detection |
| Expansion path | → Commercial RE → Insurance → Municipalities → Police |

### AEGIS MVP

**Input:** Customer uploads property addresses + incident history (CSV/API)

**Processing:**
1. Geocode and normalize addresses
2. Enrich with corporate layer (companies registered at their addresses)
3. Cross-reference with other AEGIS customers (anonymized patterns)
4. Match against pattern library
5. Score each property

**Output:**
- Dashboard: "8 of your 234 properties have organized crime indicators"
- Per-property: risk score, companies registered, network visualization
- Alerts: "New company registered at Storgatan 15 matches shell pattern"
- Weekly digest: changes, emerging patterns, predictions

**Pricing:** 2-5 SEK/apartment/month

**Target customers:**
- Stockholm "big three" (Stockholmshem, Svenska Bostäder, Familjebostäder)
- Sveriges Allmännytta network (300+ members)

---

## Implementation Phases

### Phase 1: Foundation (Months 1-3)

**Data Infrastructure:**
- [ ] PostgreSQL + PostGIS + TimescaleDB deployment (Scaleway)
- [ ] Bolagsverket API integration (company basics)
- [ ] Annual report scraping pipeline (director extraction)
- [ ] Entity resolution v1 (exact + phonetic matching)
- [ ] Basic graph queries
- [ ] Financial data extraction (revenue, employees, assets from annual reports)

**Deliverable:** Can ingest company data, resolve directors, build person→company graph, extract basic financials

### Phase 2: AEGIS MVP (Months 4-6)

**Product:**
- [ ] Address ingestion API
- [ ] Corporate enrichment for addresses
- [ ] Shell company detection (rule-based)
- [ ] Basic dashboard (property list, risk scores)
- [ ] Alert system (email)

**Deliverable:** Deployable to first housing company customer

### Phase 3: Financial Intelligence (Months 7-9)

**Capabilities:**
- [ ] Kronofogden integration (debt/bankruptcy data)
- [ ] Financial anomaly detection (Benford's law, ratio analysis)
- [ ] Invoice factory pattern detection
- [ ] Bankruptcy fraud chain detection
- [ ] Money laundering front indicators
- [ ] Welfare extraction scheme detection

**Deliverable:** Proactive financial crime scanning operational

### Phase 4: Intelligence Engine (Months 10-12)

**Capabilities:**
- [ ] Full pattern library (10+ organized crime patterns)
- [ ] Temporal analysis (trend detection)
- [ ] Prediction engine v1 (escalation probability)
- [ ] Evidence package generation
- [ ] Fusion across corporate + financial + incident data
- [ ] Referral pipeline v1 (Ekobrottsmyndigheten, Skatteverket formats)

**Deliverable:** System generates autonomous insights and prosecution-ready referrals

### Phase 5: Physical Layer Integration (Months 12-18)

**Sensors:**
- [ ] Argus acoustic integration
- [ ] Frontline camera integration
- [ ] Real-time event ingestion
- [ ] Cross-domain fusion (physical + financial + corporate)
- [ ] Activity/financial correlation (does foot traffic match revenue?)

**Deliverable:** Physical events automatically enriched with corporate/financial intelligence

### Phase 6: Law Enforcement Capability (Months 18-24)

**ZION:**
- [ ] Police system integration (requires partnership)
- [ ] Full investigation workflow
- [ ] Expanded data sources (court records, FIU access)
- [ ] Prosecutor-grade evidence packages
- [ ] Impact tracking (referral outcomes)
- [ ] Multi-authority referral routing

**Deliverable:** Platform capable of supporting criminal investigations with measurable conviction impact

---

## Technical Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Primary DB | PostgreSQL 16 + PostGIS + TimescaleDB | Proven, spatial + temporal, scales to 100M entities |
| Graph queries | Apache AGE (PostgreSQL extension) | Graph without separate DB, migrate to Neo4j if needed |
| API | FastAPI | Async, typed, fast |
| ML inference | Python + ONNX | Portable models, edge deployment |
| Edge (Argus) | nRF5340 + TensorFlow Lite | 200KB model budget, BLE mesh |
| Cloud | Scaleway (Paris) | EU sovereign, GDPR, not US CLOUD Act |
| Frontend | React + Mapbox GL | Standard, good geo visualization |

---

## Cost Estimate

### Development (24 months)

| Item | Monthly | Total |
|------|---------|-------|
| Engineering (3 FTE equivalent) | €30,000 | €720,000 |
| Infrastructure | €2,000 | €48,000 |
| Data costs (APIs, storage) | €1,000 | €24,000 |
| Legal/compliance | €2,000 | €48,000 |
| **Total** | | **€840,000** |

### Revenue Target (Month 24)

| Segment | Customers | Apartments | Price | MRR |
|---------|-----------|------------|-------|-----|
| Housing companies | 15 | 150,000 | 3 SEK | 450,000 SEK |
| Commercial RE | 5 | - | 50,000 SEK/mo | 250,000 SEK |
| **Total MRR** | | | | **700,000 SEK** |

---

## The 100x Test

**Palantir (10x over manual):**
- Surfaces connections for analysts to explore
- Requires trained operators
- Expensive implementation (€1M+)
- US-controlled
- Reactive to queries

**Archeron (100x over Palantir):**
- Generates insight autonomously
- Operates without analyst intervention for routine detection
- Swedish sovereign, no CLOUD Act exposure
- Proprietary Swedish data (housing incidents, local sensors) that Palantir can't access
- Physical-world sensors feeding ground truth (Argus/Frontline)
- Prediction, not just detection
- Proactive financial crime scanning without human trigger
- Court-ready evidence packages with full provenance
- Direct referral pathways to Swedish authorities

The 100x comes from:
1. **Fusion** — Corporate + Property + Welfare + Financial + Physical in one engine
2. **Autonomy** — System thinks, doesn't just display
3. **Prediction** — What will happen, not just what happened
4. **Action** — Interdiction recommendations, not just intelligence
5. **Prosecution** — Evidence packages ready for Ekobrottsmyndigheten, Skatteverket, FIU
6. **Sovereignty** — Swedish control of Swedish security
7. **Proactivity** — Continuous scanning finds crime before incidents occur

**Measurable 100x:**

| Metric | Manual/Palantir | Archeron |
|--------|-----------------|----------|
| Time to detect invoice factory | Months (if ever) | Hours after formation |
| Analyst hours per investigation | 40-200 | 2-4 (review only) |
| False positive rate | High (analyst fatigue) | <10% (multi-signal validation) |
| Prediction accuracy | None | 70%+ escalation prediction |
| Evidence compilation | Days | Instant |
| Cross-domain correlation | Manual, rare | Automatic, every entity |
| Coverage | Sample-based | Comprehensive (all entities) |

---

## Open Questions

1. **Data partnerships:** Which housing companies will share incident data first?
2. **Police relationship:** How to build bridge to law enforcement without being captured?
3. **Financial authority access:** Path to Ekobrottsmyndigheten/Skatteverket collaboration?
4. **Bank data:** Can transaction data be accessed via regulatory partnership or API?
5. **FIU relationship:** How to feed intelligence into money laundering detection?
6. **Legal structure:** Archeron AB or separate entity for platform?
7. **Funding:** Pre-seed sufficient for Phase 1-3? When to raise?
8. **Team:** Who else is needed beyond Tim + Fredrik? (Financial crime analyst? Former EBM?)
9. **Regulatory status:** Does proactive detection require any licensing?
10. **Evidence admissibility:** What standards ensure court acceptance?

---

*"The criminals are already using the system against itself. We're building the tool to see them doing it — and to generate the evidence packages that put them away."*