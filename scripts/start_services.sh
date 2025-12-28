#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

COMPOSE_FILE="docker/docker-compose.yml"

echo -e "${YELLOW}Starting Aquila Audit Services...${NC}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Clean up orphan containers and ensure a fresh start
echo -e "${YELLOW}Cleaning up orphan containers...${NC}"
docker-compose -f $COMPOSE_FILE down --remove-orphans

# 1. Start core infrastructure
echo -e "${YELLOW}Starting infrastructure services...${NC}"
docker-compose -f $COMPOSE_FILE up -d postgres redis rabbitmq

# 2. Wait for services to be ready
echo -e "${YELLOW}Waiting for services to be ready...${NC}"

# PostgreSQL check
for i in {1..30}; do
    if docker-compose -f $COMPOSE_FILE exec -T postgres pg_isready -U aquila > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    [ $i -eq 30 ] && echo -e "${RED}✗ PostgreSQL failed${NC}" && exit 1
    echo -n "."
    sleep 2
done

# Redis check
for i in {1..30}; do
    if docker-compose -f $COMPOSE_FILE exec -T redis redis-cli ping | grep PONG > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Redis is ready${NC}"
        break
    fi
    [ $i -eq 30 ] && echo -e "${RED}✗ Redis failed${NC}" && exit 1
    echo -n "."
    sleep 2
done

# RabbitMQ check
for i in {1..30}; do
    if docker-compose -f $COMPOSE_FILE exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; then
        echo -e "${GREEN}✓ RabbitMQ is ready${NC}"
        break
    fi
    [ $i -eq 30 ] && echo -e "${RED}✗ RabbitMQ failed${NC}" && exit 1
    echo -n "."
    sleep 2
done

# 3. Start the API Gateway first so we can use it to run migrations/seeds
echo -e "${YELLOW}Starting API Gateway for migrations...${NC}"
docker-compose -f $COMPOSE_FILE up -d api-gateway

# 4. Run database migrations inside the container
echo -e "${YELLOW}Running database migrations...${NC}"
docker-compose -f $COMPOSE_FILE exec -T api-gateway alembic -c shared/database/alembic.ini upgrade head

# 5. Seed initial data inside the container
echo -e "${YELLOW}Seeding initial data...${NC}"
docker-compose -f $COMPOSE_FILE exec -T api-gateway python scripts/seed_data.py

# 6. Start all remaining services
echo -e "${YELLOW}Starting remaining services (Admin, Worker, Ingestion)...${NC}"
docker-compose -f $COMPOSE_FILE up -d admin-service worker-service ingestion-service

# Show service status
echo -e "\n${YELLOW}Service Status:${NC}"
docker-compose -f $COMPOSE_FILE ps

echo -e "\n${GREEN}Services started successfully!${NC}"
echo -e "\n${YELLOW}Access URLs:${NC}"
echo -e "  API Gateway:      http://localhost:8000"
echo -e "  API Documentation: http://localhost:8000/docs"
echo -e "  Admin Service:    http://localhost:8001"
echo -e "  RabbitMQ Management: http://localhost:15672 (aquila / aquila123)"

echo -e "\n${YELLOW}Development credentials:${NC}"
echo -e "  Super Admin: admin@aquila.com / AdminPass123!"
echo -e "  Test User:   user@example.com / UserPass123!"