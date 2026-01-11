# Halo Platform - Production Deployment Guide

**Target Environment**: Swedish Law Enforcement / Government Infrastructure
**Classification**: **INTERNAL USE ONLY**
**Date**: 2026-01-11

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Security Requirements](#security-requirements)
3. [Infrastructure Setup](#infrastructure-setup)
4. [Environment Configuration](#environment-configuration)
5. [Database Setup](#database-setup)
6. [Application Deployment](#application-deployment)
7. [Post-Deployment Verification](#post-deployment-verification)
8. [Monitoring & Logging](#monitoring--logging)
9. [Backup & Recovery](#backup--recovery)
10. [Security Hardening](#security-hardening)

---

## Prerequisites

### System Requirements

**Backend Server**:
- OS: Ubuntu 22.04 LTS Server (or RHEL 9)
- CPU: 8+ cores (16+ cores recommended)
- RAM: 32GB minimum (64GB recommended)
- Storage: 500GB SSD (RAID 10 recommended)
- Network: Gigabit Ethernet, isolated VLAN

**Database Server**:
- OS: Ubuntu 22.04 LTS Server
- CPU: 8+ cores
- RAM: 64GB minimum
- Storage: 1TB NVMe SSD (RAID 10)
- Backup: 2TB+ for PostgreSQL backups

**Graph Database Server**:
- OS: Ubuntu 22.04 LTS Server
- CPU: 8+ cores
- RAM: 32GB minimum
- Storage: 500GB SSD

**Frontend Server** (optional, can run on backend):
- OS: Ubuntu 22.04 LTS Server
- CPU: 4+ cores
- RAM: 16GB
- Storage: 100GB SSD

### Software Requirements

- Docker 24.0+ & Docker Compose 2.20+
- Python 3.12+
- Node.js 20.x LTS
- PostgreSQL 15+
- Redis 7+
- Elasticsearch 8.11+
- Neo4j 5.x
- Nginx 1.24+
- Certbot (Let's Encrypt)

### Network Requirements

- Dedicated IP address
- Domain name (e.g., `halo.internal.gov.se`)
- SSL certificate (government-issued or Let's Encrypt)
- Firewall rules configured
- No public internet access (internal network only recommended)

---

## Security Requirements

### Access Control

**SSH Access**:
```bash
# Disable password authentication
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Only allow key-based auth
sudo sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Restart SSH
sudo systemctl restart sshd
```

**Firewall (UFW)**:
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp   # SSH (restrict to specific IPs)
sudo ufw allow 443/tcp  # HTTPS only
sudo ufw enable
```

**Fail2Ban**:
```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Compliance

- **Brottsdatalagen** (Swedish Criminal Data Act) - All data handling must be logged
- **GDPR** - PII encryption enabled
- **Säkerhetsskydd** - Government security classifications enforced
- **Audit logging** - All actions logged to immutable storage

---

## Infrastructure Setup

### 1. Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

### 2. Clone Repository

```bash
# Clone from GitHub (use SSH for better security)
git clone git@github.com:ArcheronTechnologies/haloplatform.git /opt/halo
cd /opt/halo

# Set proper ownership
sudo chown -R $USER:$USER /opt/halo
chmod 700 /opt/halo
```

### 3. Create Data Directories

```bash
sudo mkdir -p /var/lib/halo/{postgres,neo4j,elasticsearch,redis,logs,backups}
sudo chown -R $USER:$USER /var/lib/halo
chmod 700 /var/lib/halo
```

---

## Environment Configuration

### 1. Generate Secure Keys

```bash
# Generate SECRET_KEY (64 characters)
openssl rand -base64 48

# Generate PII_ENCRYPTION_KEY (32 bytes base64 encoded)
openssl rand -base64 32

# Generate JWT signing keys
ssh-keygen -t rsa -b 4096 -m PEM -f /opt/halo/secrets/jwt_private.pem
openssl rsa -in /opt/halo/secrets/jwt_private.pem -pubout -outform PEM -out /opt/halo/secrets/jwt_public.pem
chmod 400 /opt/halo/secrets/jwt_*.pem
```

### 2. Create Production .env File

```bash
cat > /opt/halo/.env << 'EOF'
# ===========================
# HALO PLATFORM - PRODUCTION
# ===========================

# Application
ENV=production
DEBUG=false
LOG_LEVEL=INFO
APP_NAME="Halo Platform"
DOMAIN=halo.internal.gov.se

# Security (CHANGE THESE!)
SECRET_KEY=<GENERATED_64_CHAR_KEY>
PII_ENCRYPTION_KEY=<GENERATED_32_BYTE_KEY>
JWT_ALGORITHM=RS256
JWT_PRIVATE_KEY_PATH=/app/secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=/app/secrets/jwt_public.pem
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# Database
DATABASE_URL=postgresql+asyncpg://halo:CHANGE_THIS_PASSWORD@postgres:5432/halo_production
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Redis
REDIS_URL=redis://:CHANGE_THIS_PASSWORD@redis:6379/0
REDIS_MAX_CONNECTIONS=50

# Elasticsearch
ELASTICSEARCH_URL=http://elasticsearch:9200
ELASTICSEARCH_INDEX_PREFIX=halo_prod

# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=CHANGE_THIS_PASSWORD

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

# External APIs (if applicable)
SCB_CERT_PATH=/app/secrets/scb_cert.pfx
SCB_CERT_PASSWORD=<FROM_SCB_EMAIL>
BOLAGSVERKET_CLIENT_ID=<FROM_BOLAGSVERKET>
BOLAGSVERKET_CLIENT_SECRET=<FROM_BOLAGSVERKET>

# Monitoring
SENTRY_DSN=<OPTIONAL_SENTRY_URL>
PROMETHEUS_ENABLED=true
METRICS_PORT=9090

# Backup
BACKUP_ENABLED=true
BACKUP_SCHEDULE="0 2 * * *"  # Daily at 2 AM
BACKUP_RETENTION_DAYS=90
BACKUP_ENCRYPTION_ENABLED=true
EOF

# Secure the .env file
chmod 400 /opt/halo/.env
```

### 3. Update docker-compose.yml for Production

```bash
cat > /opt/halo/docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: halo_production
      POSTGRES_USER: halo
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_INITDB_ARGS: "--encoding=UTF8 --lc-collate=sv_SE.UTF-8 --lc-ctype=sv_SE.UTF-8"
    volumes:
      - /var/lib/halo/postgres:/var/lib/postgresql/data
    networks:
      - halo-internal
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U halo"]
      interval: 10s
      timeout: 5s
      retries: 5
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # Redis Cache
  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 4gb --maxmemory-policy allkeys-lru
    volumes:
      - /var/lib/halo/redis:/data
    networks:
      - halo-internal
    healthcheck:
      test: ["CMD", "redis-cli", "--raw", "incr", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  # Elasticsearch
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    restart: always
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms8g -Xmx8g"
    volumes:
      - /var/lib/halo/elasticsearch:/usr/share/elasticsearch/data
    networks:
      - halo-internal
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:9200/_cluster/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5

  # Neo4j Graph Database
  neo4j:
    image: neo4j:5-community
    restart: always
    environment:
      NEO4J_AUTH: neo4j/${NEO4J_PASSWORD}
      NEO4J_dbms_memory_heap_max__size: 8G
      NEO4J_dbms_memory_pagecache_size: 4G
    volumes:
      - /var/lib/halo/neo4j:/data
    networks:
      - halo-internal
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:7474 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 5

  # Backend Application
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    env_file:
      - .env
    volumes:
      - ./secrets:/app/secrets:ro
      - /var/lib/halo/logs:/app/logs
    networks:
      - halo-internal
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G

  # Nginx Reverse Proxy
  nginx:
    image: nginx:1.24-alpine
    restart: always
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - ./src/halo/ui/dist:/usr/share/nginx/html:ro
    networks:
      - halo-internal
    depends_on:
      - backend
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  halo-internal:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16
EOF
```

---

## Database Setup

### 1. Initialize PostgreSQL

```bash
# Start PostgreSQL
docker-compose -f docker-compose.prod.yml up -d postgres

# Wait for PostgreSQL to be healthy
docker-compose -f docker-compose.prod.yml ps postgres

# Run migrations
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 2. Create Admin User

```bash
docker-compose -f docker-compose.prod.yml exec backend python -c "
from src.halo.db.repositories import UserRepository
from src.halo.security.auth import hash_password
import asyncio

async def create_admin():
    repo = UserRepository()
    await repo.create(
        username='admin',
        email='admin@internal.gov.se',
        password='CHANGE_THIS_ON_FIRST_LOGIN',
        full_name='System Administrator',
        role='admin'
    )
    print('Admin user created successfully')

asyncio.run(create_admin())
"
```

### 3. Initialize Neo4j

```bash
# Neo4j initializes automatically on first start
docker-compose -f docker-compose.prod.yml up -d neo4j

# Verify
docker-compose -f docker-compose.prod.yml exec neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} "RETURN 'Connection successful' AS status"
```

---

## Application Deployment

### 1. Build Frontend

```bash
cd /opt/halo/src/halo/ui

# Install dependencies
npm ci --production

# Build for production
VITE_API_URL=https://halo.internal.gov.se/api/v1 npm run build

# Verify build
ls -lh dist/
```

### 2. Configure Nginx

```bash
mkdir -p /opt/halo/nginx/ssl

# Copy SSL certificates (obtain from government CA or Let's Encrypt)
sudo cp /path/to/halo.internal.gov.se.crt /opt/halo/nginx/ssl/
sudo cp /path/to/halo.internal.gov.se.key /opt/halo/nginx/ssl/
sudo chmod 400 /opt/halo/nginx/ssl/*.key

cat > /opt/halo/nginx/nginx.conf << 'EOF'
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 2048;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logging
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';
    access_log /var/log/nginx/access.log main;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 50M;

    # Security headers
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self';" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/xml text/javascript application/x-javascript application/xml+rss application/json application/javascript;

    # HTTP -> HTTPS redirect
    server {
        listen 80;
        server_name halo.internal.gov.se;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name halo.internal.gov.se;

        # SSL configuration
        ssl_certificate /etc/nginx/ssl/halo.internal.gov.se.crt;
        ssl_certificate_key /etc/nginx/ssl/halo.internal.gov.se.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Root for frontend
        root /usr/share/nginx/html;
        index index.html;

        # API proxy
        location /api/ {
            proxy_pass http://backend:8000/api/;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
            proxy_read_timeout 300s;
            proxy_connect_timeout 300s;
        }

        # Health check endpoint
        location /health {
            proxy_pass http://backend:8000/health;
            access_log off;
        }

        # Frontend SPA routing
        location / {
            try_files $uri $uri/ /index.html;
            expires 1h;
            add_header Cache-Control "public, must-revalidate";
        }

        # Static assets caching
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
EOF
```

### 3. Start All Services

```bash
cd /opt/halo

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Watch logs
docker-compose -f docker-compose.prod.yml logs -f

# Verify all services are healthy
docker-compose -f docker-compose.prod.yml ps
```

---

## Post-Deployment Verification

### 1. Health Checks

```bash
# Backend API
curl -k https://halo.internal.gov.se/api/v1/health

# Expected response:
# {"status": "healthy", "version": "1.0.0"}

# Database connectivity
docker-compose -f docker-compose.prod.yml exec backend python -c "
from src.halo.db import get_db
import asyncio

async def test_db():
    async for db in get_db():
        result = await db.execute('SELECT 1')
        print('Database connected:', result.scalar())
        break

asyncio.run(test_db())
"
```

### 2. Run Test Suite

```bash
docker-compose -f docker-compose.prod.yml exec backend pytest tests/ -v --tb=short -x
```

### 3. Verify CI/CD Pipeline

Go to: https://github.com/ArcheronTechnologies/haloplatform/actions

Check that:
- ✅ All 394 tests pass
- ✅ TypeScript compilation successful
- ✅ Security scans pass
- ✅ Build artifacts created

---

## Monitoring & Logging

### 1. Set Up Prometheus

```bash
# Add Prometheus to docker-compose
docker-compose -f docker-compose.prod.yml exec backend pip install prometheus-client

# Metrics available at: http://backend:9090/metrics
```

### 2. Configure Log Aggregation

```bash
# Install Loki (optional)
mkdir -p /var/lib/halo/loki

# Or use syslog forwarding to central logging server
```

### 3. Set Up Alerts

```yaml
# /opt/halo/alerts/rules.yml
groups:
  - name: halo_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
```

---

## Backup & Recovery

### 1. Database Backup Script

```bash
cat > /opt/halo/scripts/backup_database.sh << 'EOF'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/lib/halo/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="halo_postgres_${TIMESTAMP}.sql.gz"

# Create backup
docker-compose -f /opt/halo/docker-compose.prod.yml exec -T postgres \
    pg_dump -U halo halo_production | gzip > "${BACKUP_DIR}/${BACKUP_FILE}"

# Encrypt backup
openssl enc -aes-256-cbc -salt -in "${BACKUP_DIR}/${BACKUP_FILE}" \
    -out "${BACKUP_DIR}/${BACKUP_FILE}.enc" -pass pass:${BACKUP_ENCRYPTION_KEY}

# Remove unencrypted backup
rm "${BACKUP_DIR}/${BACKUP_FILE}"

# Delete backups older than 90 days
find "${BACKUP_DIR}" -name "halo_postgres_*.sql.gz.enc" -mtime +90 -delete

echo "Backup completed: ${BACKUP_FILE}.enc"
EOF

chmod +x /opt/halo/scripts/backup_database.sh

# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/halo/scripts/backup_database.sh") | crontab -
```

### 2. Neo4j Backup

```bash
cat > /opt/halo/scripts/backup_neo4j.sh << 'EOF'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/var/lib/halo/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup Neo4j
docker-compose -f /opt/halo/docker-compose.prod.yml exec -T neo4j \
    neo4j-admin database backup neo4j --to-path=/var/lib/neo4j/backups/

# Compress and encrypt
tar -czf "${BACKUP_DIR}/halo_neo4j_${TIMESTAMP}.tar.gz" /var/lib/halo/neo4j/backups/
openssl enc -aes-256-cbc -salt -in "${BACKUP_DIR}/halo_neo4j_${TIMESTAMP}.tar.gz" \
    -out "${BACKUP_DIR}/halo_neo4j_${TIMESTAMP}.tar.gz.enc" -pass pass:${BACKUP_ENCRYPTION_KEY}
rm "${BACKUP_DIR}/halo_neo4j_${TIMESTAMP}.tar.gz"

echo "Neo4j backup completed"
EOF

chmod +x /opt/halo/scripts/backup_neo4j.sh
```

### 3. Recovery Procedure

```bash
# Restore PostgreSQL
BACKUP_FILE="/var/lib/halo/backups/halo_postgres_YYYYMMDD_HHMMSS.sql.gz.enc"

# Decrypt
openssl enc -aes-256-cbc -d -in "${BACKUP_FILE}" \
    -out "${BACKUP_FILE%.enc}" -pass pass:${BACKUP_ENCRYPTION_KEY}

# Restore
gunzip -c "${BACKUP_FILE%.enc}" | docker-compose -f /opt/halo/docker-compose.prod.yml exec -T postgres \
    psql -U halo halo_production
```

---

## Security Hardening

### 1. Enable AppArmor/SELinux

```bash
# Ubuntu (AppArmor)
sudo apt install apparmor-utils
sudo aa-enforce /etc/apparmor.d/*

# RHEL (SELinux)
sudo setenforce 1
sudo sed -i 's/SELINUX=permissive/SELINUX=enforcing/' /etc/selinux/config
```

### 2. Limit System Resources

```bash
# Add to /etc/security/limits.conf
echo "* soft nofile 65536" | sudo tee -a /etc/security/limits.conf
echo "* hard nofile 65536" | sudo tee -a /etc/security/limits.conf
```

### 3. Intrusion Detection

```bash
# Install AIDE (Advanced Intrusion Detection Environment)
sudo apt install aide
sudo aideinit
sudo mv /var/lib/aide/aide.db.new /var/lib/aide/aide.db

# Add daily check to cron
(crontab -l; echo "0 3 * * * /usr/bin/aide --check") | crontab -
```

### 4. Two-Factor Authentication (Optional)

```bash
# Enable 2FA for SSH
sudo apt install libpam-google-authenticator
google-authenticator
```

---

## Maintenance Checklist

### Daily
- [ ] Check application logs for errors
- [ ] Verify backups completed successfully
- [ ] Monitor disk space usage
- [ ] Review security alerts

### Weekly
- [ ] Review audit logs
- [ ] Check database performance metrics
- [ ] Verify all services are healthy
- [ ] Update security patches (if available)

### Monthly
- [ ] Test backup restoration
- [ ] Review user access logs
- [ ] Update dependencies (test in staging first)
- [ ] Security vulnerability scan

### Quarterly
- [ ] Full security audit
- [ ] Disaster recovery drill
- [ ] Review and update documentation
- [ ] Performance optimization review

---

## Troubleshooting

### Application Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs backend

# Check environment variables
docker-compose -f docker-compose.prod.yml exec backend env | grep -E "SECRET|DATABASE|REDIS"

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker-compose -f docker-compose.prod.yml ps postgres

# Test connection
docker-compose -f docker-compose.prod.yml exec postgres psql -U halo -d halo_production -c "SELECT version();"
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check database connections
docker-compose -f docker-compose.prod.yml exec postgres psql -U halo -d halo_production -c "SELECT count(*) FROM pg_stat_activity;"

# Check slow queries
docker-compose -f docker-compose.prod.yml exec postgres psql -U halo -d halo_production -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

---

## Support & Escalation

**Technical Issues**:
- GitHub Issues: https://github.com/ArcheronTechnologies/haloplatform/issues
- Email: support@archeron.tech

**Security Incidents**:
- Immediate escalation to security team
- Follow incident response plan
- Document all actions in audit log

**Critical Failures**:
1. Enable maintenance mode
2. Notify stakeholders
3. Activate disaster recovery plan
4. Restore from last known good backup

---

## Compliance Documentation

**Brottsdatalagen Requirements**:
- ✅ 7-year audit log retention configured
- ✅ Tier 3 approval with senior analyst requirement
- ✅ Human-in-loop enabled for high-risk decisions
- ✅ All PII encrypted at rest and in transit

**GDPR Requirements**:
- ✅ Data encryption enabled
- ✅ Right to deletion implemented
- ✅ Data minimization enforced
- ✅ Consent tracking available

---

**Document Version**: 1.0
**Last Updated**: 2026-01-11
**Next Review**: 2026-04-11
**Classification**: INTERNAL USE ONLY
