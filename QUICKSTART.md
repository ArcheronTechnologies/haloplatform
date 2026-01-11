# Halo Platform - Quick Start Guide

Get the Halo platform running for testing in **5 minutes**, even while data ingestion is still ongoing.

---

## Prerequisites

- **Docker Desktop** installed and running
- **Node.js 20+** (for frontend)
- **Python 3.12+** (optional, for local development)

---

## Quick Start (Docker)

### 1. Start All Services

```bash
# Start infrastructure services (PostgreSQL, Redis, Elasticsearch, Neo4j)
docker-compose up -d postgres redis elasticsearch neo4j

# Wait for services to be healthy (about 30 seconds)
docker-compose ps
```

### 2. Initialize Database

```bash
# Create tables and load sample data from existing SQLite databases
docker-compose run --rm halo-api python /app/scripts/load_sample_data.py
```

This will:
- Create all database tables
- Load 100 sample companies from your existing data
- Set up indexes and relationships

### 3. Start the API Server

```bash
# Start the FastAPI backend
docker-compose up -d halo-api

# Check logs
docker-compose logs -f halo-api
```

### 4. Start the Frontend

```bash
# Install dependencies (first time only)
cd src/halo/ui
npm install

# Start development server
npm run dev
```

### 5. Access the Platform

- **Frontend**: http://localhost:5173
- **API Docs**: http://localhost:8000/docs
- **API Health**: http://localhost:8000/health
- **Neo4j Browser**: http://localhost:7474 (user: neo4j, password: halopassword)

---

## Testing the Platform

### Login Credentials (Development)

Default admin account:
- **Email**: admin@example.com
- **Password**: admin123

### Test Workflows

1. **Search Companies**
   - Go to "Search" page
   - Search for a company name or organization number
   - View company details and relationships

2. **View Graph**
   - Go to "Graph" page
   - Explore entity relationships
   - Visualize corporate structures

3. **Risk Scoring**
   - Go to "Risk Analysis" page
   - Search for a company
   - View risk score and factors

4. **Create SAR**
   - Go to "SARs" page
   - Click "Create New SAR"
   - Fill in suspicious activity details

5. **Audit Log**
   - Go to "Audit" page
   - View all user actions and searches

---

## Development Mode (Without Docker)

If you prefer running services locally:

### 1. Start Infrastructure Only

```bash
# Start just the infrastructure services
docker-compose up -d postgres redis elasticsearch neo4j
```

### 2. Run Backend Locally

```bash
# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
cd src/halo
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql+asyncpg://halo:halo@localhost:5432/halo"
export REDIS_URL="redis://localhost:6379"
export ELASTICSEARCH_URL="http://localhost:9200"
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="halopassword"
export SECRET_KEY="dev-secret-key-change-in-production"
export PII_ENCRYPTION_KEY="dev-encryption-key-32-chars!!"
export PYTHONPATH="${PWD}"

# Load sample data
cd ../..
python scripts/load_sample_data.py

# Run API server
cd src/halo
uvicorn halo.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run Frontend Locally

```bash
# In a new terminal
cd src/halo/ui
npm install
npm run dev
```

---

## Loading More Data

### Option 1: Load from Existing SQLite Databases

You already have these databases with data:
- `data/unified.db` (644MB)
- `data/allabolag.db` (3.7GB)
- `data/bolagsverket_bulk.db` (811MB)
- `data/scb_bulk.db` (304MB)
- `data/directors.db` (138MB)

To load more data from these:

```bash
# Modify the limit in scripts/load_sample_data.py
# Change: load_companies_from_sqlite(limit=100)
# To:     load_companies_from_sqlite(limit=1000)

# Then run:
docker-compose run --rm halo-api python /app/scripts/load_sample_data.py
```

### Option 2: Continue Data Ingestion

The data ingestion scripts continue running in the background:

```bash
# Check ingestion status
ls -lh data/*.db

# Monitor SCB pull
tail -f logs/scb_pull.log  # If logging to file

# Monitor extraction
ls -lh data/test_extraction/
```

### Option 3: Import Specific Dataset

```bash
# Example: Load ICIJ offshore leaks data
docker-compose run --rm halo-api python /app/src/halo/scripts/load_icij.py

# Example: Enrich with Bolagsverket data
docker-compose run --rm halo-api python /app/scripts/bolagsverket_full_enrich.py
```

---

## Troubleshooting

### Services Not Starting

```bash
# Check service status
docker-compose ps

# View logs for specific service
docker-compose logs postgres
docker-compose logs redis
docker-compose logs elasticsearch
docker-compose logs neo4j
docker-compose logs halo-api

# Restart all services
docker-compose down
docker-compose up -d
```

### Database Connection Issues

```bash
# Check if PostgreSQL is accepting connections
docker-compose exec postgres pg_isready -U halo

# Connect to database manually
docker-compose exec postgres psql -U halo -d halo

# Check tables
\dt
```

### API Not Responding

```bash
# Check API health
curl http://localhost:8000/health

# View API logs
docker-compose logs -f halo-api

# Restart API
docker-compose restart halo-api
```

### Frontend Build Errors

```bash
# Clear cache and reinstall
cd src/halo/ui
rm -rf node_modules package-lock.json
npm install

# Check for TypeScript errors
npx tsc --noEmit
```

### Elasticsearch Yellow/Red Status

```bash
# Check cluster health
curl http://localhost:9200/_cluster/health?pretty

# For single-node setup, yellow is normal (no replicas)
# Green is ideal, but yellow is acceptable for development
```

### Neo4j Connection Issues

```bash
# Check Neo4j is running
docker-compose logs neo4j

# Test connection
docker-compose exec neo4j cypher-shell -u neo4j -p halopassword "RETURN 1"

# Access Neo4j Browser
open http://localhost:7474
```

---

## Accessing Services Directly

### PostgreSQL

```bash
# Connect to database
docker-compose exec postgres psql -U halo -d halo

# List all companies
SELECT orgnr, name, status FROM companies LIMIT 10;

# Count records
SELECT COUNT(*) FROM companies;
```

### Redis

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# Check cached data
KEYS *
GET some_key
```

### Elasticsearch

```bash
# Check indices
curl http://localhost:9200/_cat/indices?v

# Search companies
curl -X GET "http://localhost:9200/companies/_search?pretty" -H 'Content-Type: application/json' -d'
{
  "query": {
    "match_all": {}
  },
  "size": 10
}'
```

### Neo4j

```bash
# Open Neo4j Browser
open http://localhost:7474

# Or use cypher-shell
docker-compose exec neo4j cypher-shell -u neo4j -p halopassword

# Sample query
MATCH (n) RETURN count(n);
```

---

## Stopping Services

```bash
# Stop all services (keeps data)
docker-compose stop

# Stop and remove containers (keeps data)
docker-compose down

# Stop and remove ALL data (fresh start)
docker-compose down -v
```

---

## Next Steps

Once you've tested the platform:

1. **Set up production environment**
   - See [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
   - Generate secure keys with `scripts/generate_production_keys.sh`

2. **Configure data sources**
   - Add your SCB certificate and credentials
   - Register for Bolagsverket API access
   - Set up scheduled ingestion

3. **Customize for your needs**
   - Configure risk scoring rules
   - Add custom entity types
   - Integrate with your existing systems

4. **Deploy to cloud**
   - AWS, Azure, or Google Cloud
   - Use Kubernetes for scaling
   - Set up monitoring and alerting

---

## Need Help?

- **Documentation**: See [docs/](docs/) directory
- **API Reference**: http://localhost:8000/docs (when running)
- **Issues**: https://github.com/ArcheronTechnologies/haloplatform/issues

---

**Last Updated**: 2026-01-11
