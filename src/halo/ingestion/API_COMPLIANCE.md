<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: API_COMPLIANCE.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: API_COMPLIANCE.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: API_COMPLIANCE.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: API_COMPLIANCE.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

<!--
  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY
  Original with full API details: API_COMPLIANCE.local.md
  Redacted: API endpoints, credentials, rate limits, data layouts
  For internal use, see: .data_sources_local/
-->

# Swedish Government API Compliance Notes

This document summarizes the terms of use for Swedish government APIs used by Halo.

## Statistics Sweden (SCB) API

**Portal:** https://www.scb.se/en/services/open-data-api/

### License
- **CC0 (Creative Commons Zero)** - No attribution required
- License changed from CC-BY to CC0 on July 1, 2021
- Applies to all statistical data in the Statistical Database and open geospatial data

### Rate Limits
- **Maximum [REDACTED_RATE_LIMIT]** per IP address
- Maximum 100,000 values per table
- HTTP 403 response indicates limit exceeded

### Terms of Use
- Free to use without registration
- May NOT present service as "official cooperation" or "partnership" with SCB
- May NOT use API to spread malicious code
- If you process/modify the data, do NOT claim SCB as source
- API provided "as is" with no guarantees

### Implementation Notes
```python
# Respect rate limiting
RATE_LIMIT = 10  # requests
RATE_WINDOW = 10  # seconds
```

---

## Bolagsverket (Swedish Companies Registration Office) API

**Developer Portal:** [REDACTED_GOV_API]

### Registration Required
- Registration through the developer portal is required
- API key must be obtained before use

### Available APIs
- Company information retrieval API (updated April 2025)
- Annual report submission API
- Public company events API

### Terms
- Must register for API access
- Check developer portal for current terms
- Some data may be considered public records, others may have restrictions

### Implementation Notes
```python
# API key required
BOLAGSVERKET_API_KEY = os.getenv("BOLAGSVERKET_API_KEY")
```

---

## Lantmäteriet Open Data API

**Portal:** https://opendata.lantmateriet.se/

### License
- **CC0 (Creative Commons Zero)** for most open datasets
- Attribution appreciated but not required
- Some datasets (Topografi 10) use CC-BY 4.0

### Registration
- User account required to get API key
- Free registration at opendata.lantmateriet.se

### Available Data (CC0)
- Addresses (belägenhetadress)
- Buildings (byggnad)
- Property boundaries (fastighet)
- Topographic maps (Topografi 50, 100, 250)
- Aerial imagery

### Terms of Use
- May use, distribute, modify in commercial contexts
- No restrictions on CC0 data
- Historic maps (>70 years) and aerial photos (>50 years) are public domain

### Implementation Notes
```python
# API key required even for open data
LANTMATERIET_API_KEY = os.getenv("LANTMATERIET_API_KEY")
```

---

## Summary of Requirements

| API | Registration | License | Rate Limits | Attribution |
|-----|-------------|---------|-------------|-------------|
| SCB | None | CC0 | 10/10sec | Not required |
| Bolagsverket | Required | Varies | Check portal | Check portal |
| Lantmäteriet | Required | CC0/CC-BY | Check portal | Optional |

## Implementation Checklist

- [ ] Register for Bolagsverket developer portal
- [ ] Create Lantmäteriet account for API key
- [ ] Implement rate limiting for SCB (10 req/10 sec)
- [ ] Store API keys securely (use environment variables)
- [ ] Do not claim partnership/official status with any agency
- [ ] Document data sources in audit logs

## Legal Considerations

For law enforcement and financial compliance use cases:

1. **Brottsdatalagen** - Processing of personal data must comply with criminal data law
2. **GDPR** - Even public data may have GDPR implications for processing
3. **Säkerhetsskyddslagen** - Security classification may apply to aggregated intelligence
4. **Bank Secrecy** - Transaction data has additional restrictions beyond API terms

Consult legal counsel before deploying in production.
