#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting Aquila Audit Services...${NC}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Start infrastructure services
echo -e "${YELLOW}Starting infrastructure services...${NC}"
docker-compose -f docker/docker-compose.yml up -d postgres redis rabbitmq

# Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"

# Wait for PostgreSQL
for i in {1..30}; do
    if docker-compose -f docker/docker-compose.yml exec -T postgres pg_isready -U aquila > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ PostgreSQL failed to start${NC}"
        exit 1
    fi
    echo -n "."
    sleep 2
done

# Wait for Redis
for i in {1..30}; do
    if docker-compose -f docker/docker-compose.yml exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ Redis failed to start${NC}"
        exit 1
    fi
    echo -n "."
    sleep 2
done

# Wait for RabbitMQ
for i in {1..30}; do
    if docker-compose -f docker/docker-compose.yml exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ RabbitMQ is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ RabbitMQ failed to start${NC}"
        exit 1
    fi
    echo -n "."
    sleep 2
done

## Run database migrations
echo -e "${YELLOW}Running database migrations...${NC}"
# Run via docker to ensure pathing and dependencies match the container
docker-compose -f docker/docker-compose.yml exec -T api-gateway alembic -c shared/database/alembic.ini upgrade head

# Seed initial data
echo -e "${YELLOW}Seeding initial data...${NC}"
# Run inside the container where the models and database connection are ready
docker-compose -f docker/docker-compose.yml exec -T api-gateway python scripts/seed_data.py

# Start API Gateway (it is already running migrations, but this ensures it's healthy)
echo -e "${YELLOW}Starting API Gateway...${NC}"
docker-compose -f docker/docker-compose.yml up -d api-gateway

# Start Admin Service (Fixed name to match your docker-compose file)
echo -e "${YELLOW}Starting Admin Service...${NC}"
# Note: If your docker-compose service is named 'admin-service', use that here
docker-compose -f docker/docker-compose.yml up -d admin-service 

# Start Worker Service
echo -e "${YELLOW}Starting Worker Service...${NC}"
docker-compose -f docker/docker-compose.yml up -d worker-service
# Show service status
echo -e "\n${YELLOW}Service Status:${NC}"
docker-compose -f docker/docker-compose.yml ps

echo -e "\n${GREEN}Services started successfully!${NC}"
echo -e "\n${YELLOW}Access URLs:${NC}"
echo -e "  API Gateway:      http://localhost:8000"
echo -e "  API Documentation: http://localhost:8000/docs"
echo -e "  Admin Service:    http://localhost:8001"
echo -e "  RabbitMQ Management: http://localhost:15672 (admin/admin)"
echo -e "\n${YELLOW}Development credentials are shown above.${NC}"