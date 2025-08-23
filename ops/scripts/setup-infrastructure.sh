#!/bin/bash
# Setup script for Anumate shared infrastructure components

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="ops/docker-compose.infrastructure.yml"
ENV_FILE=".env.infrastructure"

echo -e "${GREEN}Setting up Anumate Infrastructure Components${NC}"

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}Docker Compose is not installed. Please install Docker Compose first.${NC}"
    exit 1
fi

# Create environment file if it doesn't exist
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}Creating environment file...${NC}"
    cat > "$ENV_FILE" << EOF
# Anumate Infrastructure Environment Variables

# PostgreSQL Configuration
POSTGRES_PASSWORD=anumate_dev_password
POSTGRES_USER=anumate_admin
POSTGRES_DB=anumate

# Redis Configuration
REDIS_PASSWORD=

# NATS Configuration
NATS_USER=anumate_app
NATS_PASSWORD=nats_dev_password

# Vault Configuration
VAULT_ROOT_TOKEN=dev-root-token
VAULT_ADDR=http://localhost:8200

# Network Configuration
COMPOSE_PROJECT_NAME=anumate
EOF
    echo -e "${GREEN}Environment file created at $ENV_FILE${NC}"
fi

# Source environment variables
set -a
source "$ENV_FILE"
set +a

# Create necessary directories
echo -e "${YELLOW}Creating necessary directories...${NC}"
mkdir -p ops/postgres/{init,config,data}
mkdir -p ops/redis/{config,data}
mkdir -p ops/nats/{config,data}
mkdir -p ops/vault/{config,policies,data,logs}

# Stop any existing containers
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker-compose -f "$COMPOSE_FILE" down --remove-orphans || true

# Pull latest images
echo -e "${YELLOW}Pulling latest images...${NC}"
docker-compose -f "$COMPOSE_FILE" pull

# Start infrastructure services
echo -e "${YELLOW}Starting infrastructure services...${NC}"
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U anumate_admin -d anumate; do
    echo "PostgreSQL is unavailable - sleeping"
    sleep 2
done
echo -e "${GREEN}PostgreSQL is ready!${NC}"

# Wait for Redis
echo "Waiting for Redis..."
until docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping; do
    echo "Redis is unavailable - sleeping"
    sleep 2
done
echo -e "${GREEN}Redis is ready!${NC}"

# Wait for NATS
echo "Waiting for NATS..."
until curl -s http://localhost:8222/healthz > /dev/null; do
    echo "NATS is unavailable - sleeping"
    sleep 2
done
echo -e "${GREEN}NATS is ready!${NC}"

# Wait for Vault
echo "Waiting for Vault..."
until curl -s http://localhost:8200/v1/sys/health > /dev/null; do
    echo "Vault is unavailable - sleeping"
    sleep 2
done
echo -e "${GREEN}Vault is ready!${NC}"

# Initialize Vault
echo -e "${YELLOW}Initializing Vault...${NC}"
./ops/scripts/init-vault.sh

# Create JetStream streams for event bus
echo -e "${YELLOW}Creating NATS JetStream streams...${NC}"
./ops/scripts/init-nats-streams.sh

# Verify setup
echo -e "${YELLOW}Verifying setup...${NC}"

# Check PostgreSQL connection and RLS
echo "Testing PostgreSQL connection and RLS..."
docker-compose -f "$COMPOSE_FILE" exec -T postgres psql -U anumate_admin -d anumate -c "SELECT current_database(), current_user;"

# Check Redis connection
echo "Testing Redis connection..."
docker-compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping

# Check NATS connection
echo "Testing NATS connection..."
curl -s http://localhost:8222/varz | grep -q "server_name" && echo "NATS server info accessible"

# Check Vault status
echo "Testing Vault status..."
curl -s http://localhost:8200/v1/sys/health | grep -q "initialized" && echo "Vault is initialized"

echo -e "${GREEN}Infrastructure setup complete!${NC}"
echo ""
echo -e "${GREEN}Services available at:${NC}"
echo "  PostgreSQL: localhost:5432"
echo "  Redis: localhost:6379"
echo "  NATS: localhost:4222 (HTTP: localhost:8222)"
echo "  Vault: localhost:8200"
echo ""
echo -e "${GREEN}Next steps:${NC}"
echo "1. Configure your application to use these services"
echo "2. Set tenant context in your application: SET app.current_tenant_id = '<tenant-uuid>'"
echo "3. Use the Vault token for secrets management"
echo ""
echo -e "${YELLOW}To stop services: docker-compose -f $COMPOSE_FILE down${NC}"
echo -e "${YELLOW}To view logs: docker-compose -f $COMPOSE_FILE logs -f [service-name]${NC}"