#!/bin/bash
#
# Generate Secure Production Keys for Halo Platform
#
# This script generates cryptographically secure keys for:
# - SECRET_KEY (JWT signing)
# - PII_ENCRYPTION_KEY (PII encryption)
# - Database passwords
# - Redis password
# - Neo4j password
#
# Usage: ./generate_production_keys.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Halo Platform - Production Key Generator${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Create output directory
OUTPUT_DIR="$(pwd)/production_keys"
mkdir -p "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}"

OUTPUT_FILE="${OUTPUT_DIR}/production_keys_$(date +%Y%m%d_%H%M%S).txt"

echo -e "${YELLOW}Generating secure keys...${NC}"
echo ""

# Generate SECRET_KEY (64 characters for JWT signing)
echo "Generating SECRET_KEY..."
SECRET_KEY=$(openssl rand -base64 48)

# Generate PII_ENCRYPTION_KEY (32 bytes for AES-256)
echo "Generating PII_ENCRYPTION_KEY..."
PII_ENCRYPTION_KEY=$(openssl rand -base64 32)

# Generate PostgreSQL password (32 characters)
echo "Generating PostgreSQL password..."
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

# Generate Redis password (32 characters)
echo "Generating Redis password..."
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

# Generate Neo4j password (32 characters)
echo "Generating Neo4j password..."
NEO4J_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

# Generate backup encryption key (32 characters)
echo "Generating backup encryption key..."
BACKUP_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)

# Generate JWT RSA key pair
echo "Generating JWT RSA key pair..."
JWT_DIR="${OUTPUT_DIR}/jwt_keys"
mkdir -p "${JWT_DIR}"
chmod 700 "${JWT_DIR}"

ssh-keygen -t rsa -b 4096 -m PEM -f "${JWT_DIR}/jwt_private.pem" -N "" -q
openssl rsa -in "${JWT_DIR}/jwt_private.pem" -pubout -outform PEM -out "${JWT_DIR}/jwt_public.pem" 2>/dev/null
chmod 400 "${JWT_DIR}/jwt_private.pem"
chmod 444 "${JWT_DIR}/jwt_public.pem"

echo ""
echo -e "${GREEN}✓ All keys generated successfully!${NC}"
echo ""

# Write keys to file
cat > "${OUTPUT_FILE}" << EOF
# ========================================
# HALO PLATFORM - PRODUCTION KEYS
# ========================================
# Generated: $(date)
#
# ⚠️  CRITICAL SECURITY WARNING ⚠️
# These keys provide full access to the Halo Platform.
# - Store this file in a secure password manager
# - Delete this file after copying the keys
# - Never commit this file to version control
# - Never share these keys via email or chat
# ========================================

# Application Security Keys
SECRET_KEY=${SECRET_KEY}
PII_ENCRYPTION_KEY=${PII_ENCRYPTION_KEY}

# Database Passwords
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
NEO4J_PASSWORD=${NEO4J_PASSWORD}

# Backup Encryption
BACKUP_ENCRYPTION_KEY=${BACKUP_ENCRYPTION_KEY}

# JWT Keys
# Private key location: ${JWT_DIR}/jwt_private.pem
# Public key location: ${JWT_DIR}/jwt_public.pem

# ========================================
# .env File Template
# ========================================
# Copy the section below to /opt/halo/.env

# Security
SECRET_KEY=${SECRET_KEY}
PII_ENCRYPTION_KEY=${PII_ENCRYPTION_KEY}
JWT_PRIVATE_KEY_PATH=/app/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/app/secrets/jwt_public.pem

# Database
DATABASE_URL=postgresql+asyncpg://halo:${POSTGRES_PASSWORD}@postgres:5432/halo_production

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}

# Backup
BACKUP_ENCRYPTION_KEY=${BACKUP_ENCRYPTION_KEY}

# ========================================
# docker-compose.prod.yml Environment Variables
# ========================================
# Add these to your docker-compose file:

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
NEO4J_PASSWORD=${NEO4J_PASSWORD}

# ========================================
# Next Steps
# ========================================
# 1. Copy the .env template above to /opt/halo/.env
# 2. Copy JWT keys to /opt/halo/secrets/:
#    cp ${JWT_DIR}/jwt_private.pem /opt/halo/secrets/
#    cp ${JWT_DIR}/jwt_public.pem /opt/halo/secrets/
# 3. Set file permissions:
#    chmod 400 /opt/halo/.env
#    chmod 400 /opt/halo/secrets/jwt_private.pem
#    chmod 444 /opt/halo/secrets/jwt_public.pem
# 4. Update docker-compose.prod.yml with passwords
# 5. **DELETE THIS FILE** after copying the keys:
#    shred -u ${OUTPUT_FILE}
# 6. Store keys in secure password manager (e.g., 1Password, Bitwarden)
# ========================================
EOF

# Secure the output file
chmod 400 "${OUTPUT_FILE}"

# Display summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Keys Generated Successfully${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Output file: ${YELLOW}${OUTPUT_FILE}${NC}"
echo -e "JWT keys: ${YELLOW}${JWT_DIR}/${NC}"
echo ""
echo -e "${GREEN}Keys generated:${NC}"
echo "  ✓ SECRET_KEY (64 characters)"
echo "  ✓ PII_ENCRYPTION_KEY (32 bytes)"
echo "  ✓ POSTGRES_PASSWORD (32 characters)"
echo "  ✓ REDIS_PASSWORD (32 characters)"
echo "  ✓ NEO4J_PASSWORD (32 characters)"
echo "  ✓ BACKUP_ENCRYPTION_KEY (32 characters)"
echo "  ✓ JWT RSA 4096-bit key pair"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT SECURITY STEPS:${NC}"
echo ""
echo "1. Copy keys to secure password manager"
echo "2. Set up production .env file:"
echo -e "   ${YELLOW}cp ${OUTPUT_FILE} /opt/halo/.env${NC}"
echo ""
echo "3. Copy JWT keys to secrets directory:"
echo -e "   ${YELLOW}mkdir -p /opt/halo/secrets${NC}"
echo -e "   ${YELLOW}cp ${JWT_DIR}/jwt_*.pem /opt/halo/secrets/${NC}"
echo -e "   ${YELLOW}chmod 400 /opt/halo/secrets/jwt_private.pem${NC}"
echo ""
echo "4. **DELETE this file** after copying:"
echo -e "   ${YELLOW}shred -u ${OUTPUT_FILE}${NC}"
echo ""
echo -e "${RED}⚠️  NEVER commit these keys to version control!${NC}"
echo ""
echo -e "${GREEN}========================================${NC}"

# Create a .env.production template
ENV_TEMPLATE="${OUTPUT_DIR}/.env.production.template"
cat > "${ENV_TEMPLATE}" << EOF
# ===========================
# HALO PLATFORM - PRODUCTION
# ===========================
# Generated: $(date)

# Application
ENV=production
DEBUG=false
LOG_LEVEL=INFO
APP_NAME="Halo Platform"
DOMAIN=halo.internal.gov.se

# Security
SECRET_KEY=${SECRET_KEY}
PII_ENCRYPTION_KEY=${PII_ENCRYPTION_KEY}
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/app/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/app/secrets/jwt_public.pem
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Database
DATABASE_URL=postgresql+asyncpg://halo:${POSTGRES_PASSWORD}@postgres:5432/halo_production
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
REDIS_MAX_CONNECTIONS=50

# Elasticsearch
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_INDEX_PREFIX=halo_prod

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}

# CORS (internal network only)
CORS_ORIGINS=https://halo.internal.gov.se
CORS_ALLOW_CREDENTIALS=true

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# Session Management
SESSION_TIMEOUT_MINUTES=30
MAX_CONCURRENT_SESSIONS_PER_USER=3

# File Upload
MAX_FILE_SIZE_MB=50
ALLOWED_FILE_TYPES=pdf,doc,docx,xls,xlsx,csv,txt,eml,msg

# Audit Logging
AUDIT_LOG_ENABLED=true
AUDIT_LOG_RETENTION_DAYS=2555  # 7 years (Brottsdatalagen requirement)
AUDIT_LOG_IMMUTABLE=true

# Brottsdatalagen Compliance
TIER3_APPROVAL_REQUIRED=true
TIER3_MIN_ROLE=senior_analyst
HUMAN_IN_LOOP_ENABLED=true

# Backup
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
BACKUP_RETENTION_DAYS=90
BACKUP_ENCRYPTION_ENABLED=true
BACKUP_ENCRYPTION_KEY=${BACKUP_ENCRYPTION_KEY}

# Monitoring
PROMETHEUS_ENABLED=true
METRICS_PORT=9090
EOF

chmod 400 "${ENV_TEMPLATE}"

echo -e "${GREEN}Also created:${NC} ${ENV_TEMPLATE}"
echo -e "Copy to production server: ${YELLOW}cp ${ENV_TEMPLATE} /opt/halo/.env${NC}"
echo ""
