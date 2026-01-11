# Bolagsverket HVD API - Exploration Findings

## Summary

**Conclusion: The HVD (Värdefulla Datamängder) API does NOT provide director/funktionär data.**

The free HVD API only provides basic company registration data. Director information must be obtained through:
1. Annual report PDF scraping (current approach)
2. Paid Bolagsverket APIs (not HVD)

## API Details

- **Base URL (Prod)**: `https://gw.api.bolagsverket.se/vardefulla-datamangder/v1`
- **Base URL (Test)**: `https://gw-accept2.api.bolagsverket.se/vardefulla-datamangder/v1`
- **Auth**: OAuth2 Client Credentials
- **Token URL**: `https://portal.api.bolagsverket.se/oauth2/token`
- **Rate Limit**: 60 requests/minute per user (1 req/sec)

## Available Endpoints (Confirmed Working)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/isalive` | GET | Health check |
| `/organisationer` | POST | Company data lookup by org number |
| `/dokumentlista` | POST | List annual reports for a company |
| `/dokument/{dokumentId}` | GET | Download annual report PDF |

## Tested Endpoints (All Returned 404)

The following endpoints were tested to find director/funktionär data:

- `/funktionarer` - 404
- `/funktionar` - 404
- `/person` - 404
- `/personer` - 404
- `/engagemang` - 404
- `/firmateckning` - 404
- `/styrelse` - 404
- `/ledning` - 404

## Data Returned by /organisationer

The `/organisationer` endpoint returns:
- Organisation identity (org number, type)
- Company name (firma)
- Legal form (juridisk form)
- Registration dates
- SNI industry codes
- Postal address
- Business description (verksamhetsbeskrivning)
- Active/inactive status

**NOT included:**
- Directors/board members (styrelseledamöter)
- CEO (VD)
- Signatories (firmatecknare)
- Auditors (revisorer)
- Beneficial owners

## Request/Response Examples

### POST /organisationer

Request:
```json
{
  "identitetsbeteckning": "5560001234"
}
```

Response (abbreviated):
```json
{
  "organisationer": [{
    "identitetsbeteckning": "5560001234",
    "organisationsnamn": "EXAMPLE AB",
    "juridiskForm": "AB",
    "registreringsdatum": "1990-01-15",
    "sniKoder": ["62010"],
    "postadress": {
      "utdelningsadress": "Box 123",
      "postnummer": "12345",
      "postort": "STOCKHOLM"
    }
  }]
}
```

### POST /dokumentlista

Request:
```json
{
  "identitetsbeteckning": "5560001234"
}
```

Response:
```json
{
  "dokument": [{
    "dokumentId": "abc123",
    "dokumentTyp": "Årsredovisning",
    "rakenskapsperiod": {
      "from": "2022-01-01",
      "tom": "2022-12-31"
    }
  }]
}
```

## Additional Parameters Tested

Tested with `/organisationer` - no additional data returned:

- `inkludera: ["funktionarer"]` - ignored, no extra data
- `omfattning: "fullstandig"` - ignored, no extra data
- `inkludera: ["styrelse", "firmatecknare"]` - ignored

## OpenAPI/Swagger Spec

- `/swagger.json` - 404
- `/openapi.json` - 404
- Portal documentation requires authentication

## Alternative Data Sources for Directors

1. **Annual Reports (Current Approach)**
   - Download PDFs via `/dokument/{id}`
   - Parse/scrape for director names
   - Pros: Free, available via HVD API
   - Cons: Requires PDF parsing, historical data only

2. **Paid Bolagsverket APIs**
   - May have separate subscription APIs with director data
   - Requires contacting Bolagsverket directly

3. **Other Data Providers**
   - Bisnode/Dun & Bradstreet
   - UC
   - Creditsafe
   - All paid services

## Recommendations

1. **Continue with annual report scraping** for director data
2. **Contact Bolagsverket** to inquire about paid APIs with funktionär endpoints
3. **Monitor HVD API updates** - they may add more endpoints in future

---
*Generated: 2025-12-29*
*Based on direct API testing against production endpoints*
