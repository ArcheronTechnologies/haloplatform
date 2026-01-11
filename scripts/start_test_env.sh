#!/bin/bash
#
# Quick Start Script for Halo Platform Testing
#
# This script starts all services and loads sample data for testing
#

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}Halo Platform - Quick Start${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""

# Check if Docker is running
if ! docker ps >/dev/null 2>&1; then
    echo -e "${RED}✗ Docker is not running${NC}"
    echo ""
    echo "Please start Docker Desktop and try again."
    echo ""
    exit 1
fi

echo -e "${YELLOW}Step 1: Starting infrastructure services...${NC}"
docker-compose up -d postgres redis elasticsearch neo4j

echo ""
echo -e "${YELLOW}Step 2: Waiting for services to be healthy (30s)...${NC}"
sleep 5
for i in {1..5}; do
    echo -n "."
    sleep 5
done
echo ""

# Check service health
echo ""
echo -e "${YELLOW}Checking service status...${NC}"
docker-compose ps

echo ""
echo -e "${YELLOW}Step 3: Creating database tables and loading sample data...${NC}"
docker-compose run --rm halo-api python /app/scripts/load_sample_data.py

echo ""
echo -e "${YELLOW}Step 4: Starting API server...${NC}"
docker-compose up -d halo-api

echo ""
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}✓ Platform Started Successfully!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo "Services running:"
echo "  • PostgreSQL:     localhost:5432"
echo "  • Redis:          localhost:6379"
echo "  • Elasticsearch:  http://localhost:9200"
echo "  • Neo4j Browser:  http://localhost:7474"
echo "  • API Server:     http://localhost:8000"
echo "  • API Docs:       http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Start the frontend:"
echo "     cd src/halo/ui && npm install && npm run dev"
echo ""
echo "  2. Open the app:"
echo "     http://localhost:5173"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  • View API logs:  docker-compose logs -f halo-api"
echo "  • Stop platform:  docker-compose stop"
echo "  • Fresh restart:  docker-compose down -v && ./scripts/start_test_env.sh"
echo ""
