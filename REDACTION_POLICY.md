# Data Source Redaction Policy

**Classification**: INTERNAL USE ONLY
**Last Updated**: 2026-01-11

---

## Overview

The Halo Platform uses sensitive Swedish government and commercial data sources. To protect operational security while maintaining open source collaboration, we use **automatic redaction** of data source details in the public GitHub repository.

---

## What Is Redacted

### Sensitive Information

The following information is **automatically redacted** before committing to GitHub:

1. **API Endpoints**
   - SCB (Statistics Sweden) API URLs
   - Bolagsverket (Swedish Companies Registration Office) endpoints
   - Allabolag commercial API endpoints
   - Private government API endpoints

2. **Credentials**
   - API keys and client IDs
   - API secrets and passwords
   - Certificate passwords
   - OAuth tokens

3. **Operational Details**
   - Rate limits (requests per second)
   - Data layouts and schemas
   - Maximum result sizes
   - Internal data structure details

4. **Commercial Agreements**
   - Specific pricing information
   - Contract details
   - Service level agreements

### What Remains Public

The following **functional information** remains in the public repository:

- ✅ Data source **names** (SCB, Bolagsverket, ICIJ, Allabolag)
- ✅ **Purpose** of each data source
- ✅ **License information** (CC0, Creative Commons, etc.)
- ✅ **Compliance** notes (GDPR, Brottsdatalagen)
- ✅ **General architecture** of data ingestion
- ✅ **Code functionality** (algorithms, patterns, analysis)

---

## Redaction System

### Automatic Redaction

**Script**: `scripts/redact_data_sources.sh`

**What It Does**:
1. Creates `.local.md` and `.local.py` backup copies with full details
2. Archives originals to `.data_sources_local/` directory
3. Redacts sensitive patterns from public versions
4. Adds redaction notice to files

**Redacted Patterns**:
```bash
# API URLs
https://api.scb.se/*                    → [REDACTED_API_ENDPOINT]
https://privateapi.scb.se/*             → [REDACTED_PRIVATE_API]
https://*.bolagsverket.se/*             → [REDACTED_GOV_API]
https://*.allabolag.se/*                → [REDACTED_COMMERCIAL_API]

# Credentials
uyMBu2LtKfiY                           → [REDACTED_PASSWORD]
AnQ27kXW8z4sdOMJHJuFJGf5AFIa           → [REDACTED_CLIENT_ID]
L4bi0Wh_pDiMZ7GrKb9PYd1274oa           → [REDACTED_CLIENT_SECRET]

# Operational Details
"10 requests per 10 seconds"           → [REDACTED_RATE_LIMIT]
"2,000 rows per request"               → [REDACTED_MAX_RESULTS]
"JE - Juridiska enheter"               → [REDACTED_DATA_LAYOUT]
```

### CI/CD Enforcement

**Workflow**: `.github/workflows/check-secrets.yml`

**Automatic Checks** (runs on every push):
1. ✅ Scans for sensitive patterns
2. ✅ Blocks commits containing credentials
3. ✅ Verifies redaction notices exist
4. ✅ Prevents `.local` files from being committed
5. ✅ Ensures `.env` files are not committed

**Failure Actions**:
- ❌ CI pipeline fails if sensitive data detected
- 📋 Provides instructions to run redaction script
- 🔒 Blocks merge until fixed

---

## File Structure

### Public Repository (GitHub)

```
haloplatform/
├── src/halo/ingestion/
│   ├── API_COMPLIANCE.md          # ✅ Redacted version
│   ├── SCB_DATA_PLAN.md           # ✅ Redacted version
│   ├── scb_foretag.py             # ✅ Redacted URLs in comments
│   ├── scb_pxweb.py               # ✅ Redacted URLs in comments
│   ├── bolagsverket_hvd.py        # ✅ Redacted URLs in comments
│   └── allabolag_adapter.py       # ✅ Redacted URLs in comments
├── docs/
│   └── api_findings.md            # ✅ Redacted version
└── scripts/
    └── redact_data_sources.sh     # 🔧 Redaction tool
```

### Local Only (NOT in Git)

```
haloplatform/
├── .gitignore                      # 🔒 Excludes files below
├── .data_sources_local/            # 🔒 Archived originals
│   ├── API_COMPLIANCE.md           # 📁 Full details
│   ├── SCB_DATA_PLAN.md            # 📁 Full details
│   └── api_findings.md             # 📁 Full details
├── src/halo/ingestion/
│   ├── API_COMPLIANCE.local.md     # 📁 Full API details
│   ├── SCB_DATA_PLAN.local.md      # 📁 Full data layouts
│   ├── scb_foretag.local.py        # 📁 Original URLs
│   ├── scb_pxweb.local.py          # 📁 Original URLs
│   ├── bolagsverket_hvd.local.py   # 📁 Original URLs
│   └── allabolag_adapter.local.py  # 📁 Original URLs
└── docs/
    └── api_findings.local.md       # 📁 Full findings
```

---

## Usage Instructions

### For Developers

#### Running Redaction Script

**Before committing changes to data source files**:

```bash
cd /Users/timothyaikenhead/Desktop/new-folder

# Run redaction script
./scripts/redact_data_sources.sh

# Verify redaction
git diff src/halo/ingestion/API_COMPLIANCE.md

# Commit redacted versions
git add src/halo/ingestion/*.md src/halo/ingestion/*.py docs/*.md
git commit -m "Update data source documentation (redacted)"
git push
```

#### Working with Full Details Locally

**To view full details** (local development):

```bash
# Read original files
cat src/halo/ingestion/API_COMPLIANCE.local.md
cat src/halo/ingestion/scb_foretag.local.py

# Or restore from archive
cp .data_sources_local/API_COMPLIANCE.md src/halo/ingestion/API_COMPLIANCE.md
```

**IMPORTANT**: Never commit `.local` files to GitHub!

#### Adding New Sensitive Files

1. Add file path to `SENSITIVE_FILES` or `PYTHON_FILES` array in `scripts/redact_data_sources.sh`
2. Run redaction script
3. Commit redacted version only

### For Administrators

#### Sharing Full Details Internally

**Secure Methods**:
- ✅ Encrypted email (PGP/S/MIME)
- ✅ Secure file sharing (government-approved system)
- ✅ VPN + internal file server
- ✅ Password manager (1Password, Bitwarden teams)

**Never**:
- ❌ Plain email
- ❌ Slack/Teams messages
- ❌ Public GitHub
- ❌ Unencrypted file shares

#### Recovering Full Details

If `.local` files are lost:

```bash
# Restore from archive
cp .data_sources_local/* src/halo/ingestion/

# Rename back to .local
cd src/halo/ingestion
for f in API_COMPLIANCE.md SCB_DATA_PLAN.md; do
    mv "$f" "${f%.md}.local.md"
done
```

---

## CI/CD Integration

### Automatic Checks

**Workflow**: `.github/workflows/check-secrets.yml`

**Runs On**:
- Every push to `main` or `develop`
- Every pull request

**Checks**:

1. **Sensitive Pattern Scan**
   ```bash
   # Scans for:
   - API passwords/keys
   - Private endpoints
   - Certificate references
   ```

2. **Local File Check**
   ```bash
   # Ensures no .local files committed:
   git ls-files | grep '\.local\.'
   ```

3. **Redaction Notice Verification**
   ```bash
   # Verifies redacted files have notice:
   grep "REDACTED VERSION FOR PUBLIC REPOSITORY"
   ```

### Failure Handling

**If CI/CD Fails**:

```bash
# 1. Check error message in GitHub Actions
#    https://github.com/ArcheronTechnologies/haloplatform/actions

# 2. Run redaction script locally
./scripts/redact_data_sources.sh

# 3. Remove any .local files from staging
git reset *.local.*
git checkout *.local.*

# 4. Re-commit
git add -A
git commit --amend --no-edit
git push --force-with-lease
```

---

## Security Best Practices

### Do's ✅

1. **Always run redaction script** before committing data source changes
2. **Keep `.local` files** for local reference
3. **Archive to `.data_sources_local/`** for backup
4. **Use `.gitignore`** to prevent accidental commits
5. **Review git diff** before pushing
6. **Share full details** only via secure channels
7. **Update redaction patterns** when adding new data sources

### Don'ts ❌

1. **Never commit `.local` files** to GitHub
2. **Never commit `.data_sources_local/` directory**
3. **Never share credentials** in chat or email
4. **Never bypass CI/CD checks**
5. **Never commit `.env` files**
6. **Never push without running redaction script**
7. **Never disable secret scanning**

---

## Redaction Maintenance

### Adding New Patterns

**To redact additional sensitive data**:

1. Edit `scripts/redact_data_sources.sh`
2. Add new sed pattern to `redact_file()` function:
   ```bash
   -e 's|NEW_PATTERN|[REDACTED_LABEL]|g' \
   ```

3. Update CI/CD check in `.github/workflows/check-secrets.yml`:
   ```yaml
   SENSITIVE_PATTERNS=(
     "NEW_PATTERN"              # Description
   )
   ```

4. Re-run redaction script:
   ```bash
   ./scripts/redact_data_sources.sh
   ```

### Testing Redaction

**Verify redaction works**:

```bash
# 1. Run redaction
./scripts/redact_data_sources.sh

# 2. Check for sensitive patterns
grep -r "uyMBu2LtKfiY" src/halo/ingestion/*.md
# Should return nothing

# 3. Verify local files still have data
grep "uyMBu2LtKfiY" src/halo/ingestion/*.local.md
# Should find matches

# 4. Check CI/CD locally (requires act)
act -j scan-secrets
```

---

## Compliance Notes

### Why Redaction Is Important

1. **Operational Security**
   - Prevents adversaries from knowing data sources
   - Protects API rate limits from abuse
   - Reduces attack surface

2. **Contract Compliance**
   - Some data sources prohibit public disclosure of API details
   - Commercial agreements may have confidentiality clauses
   - Government APIs may have usage restrictions

3. **GDPR**
   - Even metadata about data sources can reveal PII processing
   - Data flow documentation may need protection

4. **Brottsdatalagen** (Swedish Criminal Data Act)
   - Law enforcement data sources must not be publicly disclosed
   - Operational methods should remain confidential

### Legal Considerations

**Before publicly disclosing** any data source information:
1. Review API terms of service
2. Check commercial contract confidentiality clauses
3. Consult legal counsel
4. Verify GDPR compliance
5. Check Säkerhetsskydd (government security) classifications

---

## Emergency Procedures

### Accidental Credential Exposure

**If credentials are committed to GitHub**:

```bash
# 1. IMMEDIATELY revoke exposed credentials
#    - Change API keys
#    - Rotate passwords
#    - Revoke certificates

# 2. Remove from git history
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch FILE_WITH_CRED" \
  --prune-empty --tag-name-filter cat -- --all

# 3. Force push
git push --force --all
git push --force --tags

# 4. Notify team
#    - Email security team
#    - Document incident
#    - Update audit log

# 5. Verify removal
git log --all -- FILE_WITH_CRED
# Should show file is gone

# 6. Update credentials everywhere
#    - Production servers
#    - Staging environments
#    - Developer machines
```

### Lost Local Files

**If `.local` files are deleted**:

```bash
# 1. Check archive
ls .data_sources_local/

# 2. Restore from archive
cp .data_sources_local/*.md src/halo/ingestion/
# Rename as needed

# 3. If archive also lost, check git history
git log --all --full-history -- "*.local.md"
git checkout <commit> -- src/halo/ingestion/API_COMPLIANCE.local.md

# 4. Last resort: Request from data source providers
#    - Contact SCB for API documentation
#    - Contact Bolagsverket for credentials
```

---

## Support

### Questions

**Data Source Access**:
- SCB: https://www.scb.se/en/services/open-data-api/
- Bolagsverket: https://bolagsverket.se/
- Contact data provider directly

**Redaction Issues**:
- GitHub Issues: https://github.com/ArcheronTechnologies/haloplatform/issues
- Email: support@archeron.tech

**Security Incidents**:
- Immediate escalation to security team
- Document in audit log
- Follow incident response plan

---

**Document Version**: 1.0
**Last Updated**: 2026-01-11
**Classification**: INTERNAL USE ONLY
**Review Schedule**: Quarterly
