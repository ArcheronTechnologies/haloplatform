#!/bin/bash
#
# Redact Data Source Information
#
# This script redacts sensitive data source information from files
# before they are committed to GitHub, while preserving the originals locally.
#
# Usage: ./scripts/redact_data_sources.sh
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Data Source Redaction Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Files to redact (create .local versions)
SENSITIVE_FILES=(
    "src/halo/ingestion/API_COMPLIANCE.md"
    "src/halo/ingestion/SCB_DATA_PLAN.md"
    "docs/api_findings.md"
)

# Create backup directory
BACKUP_DIR=".data_sources_local"
mkdir -p "${BACKUP_DIR}"

echo -e "${YELLOW}Processing sensitive files...${NC}"
echo ""

redact_file() {
    local file="$1"
    local temp_file="${file}.tmp"

    # Copy to temp file
    cp "$file" "$temp_file"

    # Apply redactions using sed
    sed -i.bak \
        -e 's|https://api\.scb\.se[^[:space:]"'"'"']*|[REDACTED_API_ENDPOINT]|g' \
        -e 's|https://privateapi\.scb\.se[^[:space:]"'"'"']*|[REDACTED_PRIVATE_API]|g' \
        -e 's|https://[^[:space:]"'"'"']*bolagsverket\.se[^[:space:]"'"'"']*|[REDACTED_GOV_API]|g' \
        -e 's|https://[^[:space:]"'"'"']*allabolag\.se[^[:space:]"'"'"']*|[REDACTED_COMMERCIAL_API]|g' \
        -e 's|uyMBu2LtKfiY|[REDACTED_PASSWORD]|g' \
        -e 's|scb_cert\.pfx|[REDACTED_CERT]|g' \
        -e 's|JE - Juridiska enheter|[REDACTED_DATA_LAYOUT]|g' \
        -e 's|AE - Arbetsställe|[REDACTED_DATA_LAYOUT]|g' \
        -e 's|AnQ27kXW8z4sdOMJHJuFJGf5AFIa|[REDACTED_CLIENT_ID]|g' \
        -e 's|L4bi0Wh_pDiMZ7GrKb9PYd1274oa|[REDACTED_CLIENT_SECRET]|g' \
        -e 's|10 requests per 10 seconds|[REDACTED_RATE_LIMIT]|g' \
        -e 's|2,000 rows per request|[REDACTED_MAX_RESULTS]|g' \
        -e 's|Password: [^[:space:]<>]*|Password: [REDACTED]|g' \
        -e 's|BOLAGSVERKET_CLIENT_ID=[^[:space:]]*|BOLAGSVERKET_CLIENT_ID=[REDACTED]|g' \
        -e 's|BOLAGSVERKET_CLIENT_SECRET=[^[:space:]]*|BOLAGSVERKET_CLIENT_SECRET=[REDACTED]|g' \
        -e 's|SCB_CERT_PASSWORD=[^[:space:]]*|SCB_CERT_PASSWORD=[REDACTED]|g' \
        "$temp_file"

    rm "${temp_file}.bak"
    mv "$temp_file" "$file"
}

for file in "${SENSITIVE_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "Processing: ${YELLOW}$file${NC}"

        # Backup original to .local version
        local_file="${file%.md}.local.md"
        cp "$file" "$local_file"
        echo "  ✓ Backed up to: $local_file"

        # Backup to hidden directory
        backup_file="${BACKUP_DIR}/$(basename $file)"
        cp "$file" "$backup_file"
        echo "  ✓ Archived to: $backup_file"

        # Add redaction notice at top
        {
            echo "<!--"
            echo "  THIS IS A REDACTED VERSION FOR PUBLIC REPOSITORY"
            echo "  Original with full API details: $(basename $file .md).local.md"
            echo "  Redacted: API endpoints, credentials, rate limits, data layouts"
            echo "  For internal use, see: .data_sources_local/"
            echo "-->"
            echo ""
            cat "$file"
        } > "${file}.new"

        mv "${file}.new" "$file"

        # Apply redactions
        redact_file "$file"

        echo -e "  ${GREEN}✓ Redacted${NC}"
        echo ""
    else
        echo -e "${YELLOW}  ⚠ File not found: $file${NC}"
    fi
done

# Redact Python files
echo -e "${YELLOW}Processing Python files with credentials...${NC}"
echo ""

# Find all Python files that may contain credentials
PYTHON_PATTERNS=(
    "src/halo/ingestion/*.py"
    "src/halo/scripts/*.py"
    "src/halo/pipeline/*.py"
    "scripts/*.py"
)

# Collect all matching files
PYTHON_FILES=()
for pattern in "${PYTHON_PATTERNS[@]}"; do
    for file in $pattern; do
        if [ -f "$file" ] && [ "$(basename $file)" != "redact_data_sources.sh" ]; then
            PYTHON_FILES+=("$file")
        fi
    done
done

for file in "${PYTHON_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "Processing: ${YELLOW}$file${NC}"

        # Backup original
        local_file="${file%.py}.local.py"
        cp "$file" "$local_file"
        echo "  ✓ Backed up to: $local_file"

        # Redact URLs, credentials, and sensitive strings
        sed -i.bak \
            -e 's|https://[^ "]*scb\.se[^ "]*|[REDACTED_API_ENDPOINT]|g' \
            -e 's|https://[^ "]*bolagsverket\.se[^ "]*|[REDACTED_GOV_API]|g' \
            -e 's|https://[^ "]*allabolag\.se[^ "]*|[REDACTED_COMMERCIAL_API]|g' \
            -e 's|"uyMBu2LtKfiY"|"[REDACTED_PASSWORD]"|g' \
            -e "s|'uyMBu2LtKfiY'|'[REDACTED_PASSWORD]'|g" \
            -e 's|=uyMBu2LtKfiY|=[REDACTED_PASSWORD]|g' \
            -e 's|"AnQ27kXW8z4sdOMJHJuFJGf5AFIa"|"[REDACTED_CLIENT_ID]"|g' \
            -e "s|'AnQ27kXW8z4sdOMJHJuFJGf5AFIa'|'[REDACTED_CLIENT_ID]'|g" \
            -e 's|=AnQ27kXW8z4sdOMJHJuFJGf5AFIa|=[REDACTED_CLIENT_ID]|g' \
            -e 's|"L4bi0Wh_pDiMZ7GrKb9PYd1274oa"|"[REDACTED_CLIENT_SECRET]"|g' \
            -e "s|'L4bi0Wh_pDiMZ7GrKb9PYd1274oa'|'[REDACTED_CLIENT_SECRET]'|g" \
            -e 's|=L4bi0Wh_pDiMZ7GrKb9PYd1274oa|=[REDACTED_CLIENT_SECRET]|g' \
            -e 's|scb_cert\.pfx|[REDACTED_CERT]|g' \
            "$file"

        rm "${file}.bak"

        echo -e "  ${GREEN}✓ Redacted${NC}"
        echo ""
    fi
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Redaction Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Files backed up to:"
echo "  - *.local.md and *.local.py files"
echo "  - ${BACKUP_DIR}/ directory"
echo ""
echo -e "${YELLOW}⚠️  Important:${NC}"
echo "  - Commit the redacted versions to GitHub"
echo "  - Keep .local versions for internal use only"
echo "  - Never commit .local files or .data_sources_local/"
echo ""
