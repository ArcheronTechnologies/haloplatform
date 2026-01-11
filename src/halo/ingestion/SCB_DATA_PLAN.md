<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: SCB_DATA_PLAN.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: SCB_DATA_PLAN.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: SCB_DATA_PLAN.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

# SCB Data Access Plan

Statistics Sweden (SCB) provides two main types of data access relevant to Halo:

## 1. SCB Företagsregistret (Business Register)

**Access:** Certificate-based authentication
**Registration:** Email scbforetag@scb.se
**Data:** Individual company records

### What You Get
- All 1.8M Swedish companies
- 1.4M workplaces (arbetsställen)
- Company details (name, address, legal form)
- SNI codes (industry classification)
- CFAR numbers (workplace identifiers)
- Status (active/inactive)
- Registration dates

### API Endpoints
```
Base: [REDACTED_API_ENDPOINT]
GET  /je/{orgnr}      - Fetch company by org number
GET  /ae/{cfar}       - Fetch workplace by CFAR
POST /je/search       - Search companies
```

### Use in Halo
- Entity resolution for companies
- Validate organisationsnummer
- Get industry classification for risk assessment
- Find related workplaces

---

## 2. SCB Statistical Database (PxWeb API)

**Access:** Open, no registration required
**Rate Limit:** [REDACTED_RATE_LIMIT], max 100K values per query
**Data:** Aggregate statistics (not individual records)

### API Versions
- **v1 (current):** `[REDACTED_API_ENDPOINT]
- **v2 (new, Oct 2025):** `https://statistikdatabasen.scb.se/api/v2/`

### Available Subject Areas

| Code | Area | Use in Halo |
|------|------|-------------|
| **NV** | Business activities | Industry benchmarks, company size norms |
| **BE** | Population | Demographics, migration patterns |
| **AM** | Labour market | Employment statistics, salary benchmarks |
| **BO** | Housing, construction | Property value context |
| **FM** | Financial markets | Economic indicators |
| **HA** | Trade | Import/export patterns |
| **HE** | Household finances | Income benchmarks, wealth patterns |
| **PR** | Prices & Consumption | Inflation context |
| **OE** | Public finances | Government spending |
| **TK** | Transport | Vehicle statistics |

### Key Tables for Halo

#### Business Intelligence (NV)
```
NV/NV0101 - Företagsstatistik (Business statistics)
  - Number of enterprises by industry
  - Revenue by industry
  - Employee counts

NV/NV0119 - Nystartade företag (New enterprises)
  - Startup rates by industry/region
  - Survival rates
```

**Use case:** Flag companies with unusual metrics vs industry norms

#### Population (BE)
```
BE/BE0101 - Befolkningsstatistik (Population statistics)
  - Population by region/age/sex
  - Migration flows

BE/BE0401 - Befolkningsframskrivningar (Population projections)
```

**Use case:** Validate demographic plausibility, detect synthetic identities

#### Labour Market (AM)
```
AM/AM0103 - Lönestrukturstatistik (Salary statistics)
  - Salary by industry/occupation
  - Regional variations

AM/AM0207 - Arbetslöshetsstatistik (Unemployment statistics)
```

**Use case:** Flag implausible income claims, lifestyle analysis

#### Household Finances (HE)
```
HE/HE0103 - Hushållens tillgångar (Household assets)
  - Average wealth by region/age

HE/HE0110 - Inkomster och skatter (Income and taxes)
```

**Use case:** Wealth plausibility checks, unexplained wealth detection

### Query Examples

#### Get Industry Benchmark
```python
# How many companies in restaurant industry (SNI 56.1)?
query = {
    "SNI2007": ["561"],  # Restaurants
    "Tid": ["2023"],
}
data = await adapter.query_table("NV/NV0101/...", query)
```

#### Get Regional Salary Data
```python
# Average salary in Stockholm for IT professionals
query = {
    "Region": ["01"],  # Stockholm
    "Yrke": ["251"],   # IT professionals
    "Tid": ["2023"],
}
```

---

## 3. Data Integration Strategy

### Phase 1: Business Register (Företagsregistret)
1. Register for API access (email scbforetag@scb.se)
2. Receive PFX certificate
3. Implement certificate-based auth
4. Sync all active companies
5. Set up incremental updates

### Phase 2: Statistical Benchmarks (PxWeb)
1. Query industry statistics for risk scoring
2. Build salary/income benchmarks
3. Create regional demographic profiles
4. Cache results (statistics change monthly, not daily)

### Phase 3: Cross-Reference
1. Flag companies with unusual employee/revenue ratios
2. Identify salary claims outside normal ranges
3. Detect geographic anomalies (population vs business density)

---

## 4. Implementation Priority

### High Priority (Core Functionality)
- [ ] SCB Företagsregistret company lookup
- [ ] Industry classification (SNI) normalization
- [ ] Business statistics benchmarks

### Medium Priority (Enhanced Analysis)
- [ ] Salary benchmarks by industry/region
- [ ] Income distribution data
- [ ] New company formation trends

### Lower Priority (Advanced Features)
- [ ] Population density analysis
- [ ] Migration pattern correlation
- [ ] Property value statistics

---

## 5. Rate Limiting Strategy

Both APIs have 10 req/10 sec limit. Strategy:

```python
# Use token bucket rate limiter
from halo.ingestion.rate_limiter import SCB_RATE_LIMITER

# Batch requests where possible
# Cache statistical data aggressively (TTL: 24 hours for stats)
# Use incremental sync for business register
```

---

## 6. Data Quality Notes

### Business Register
- Updated daily
- Very high quality (official register)
- May lag 1-2 days for recent changes

### Statistical Database
- Updated monthly/quarterly depending on table
- Aggregated data (no individual records)
- Good for benchmarking, not entity lookup

---

## 7. Compliance Notes

### CC0 License
- No attribution required
- Free for commercial use
- Can modify and redistribute

### Restrictions
- Cannot claim partnership with SCB
- Cannot use for spreading malware
- If you modify data, don't claim SCB as source

### Audit Trail
Log all API calls:
- Timestamp
- Query parameters
- Response size
- User who triggered query
