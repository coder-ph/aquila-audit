#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_ROOT="/home/pheli/development/aquila_audit"
COMPOSE_FILE="$PROJECT_ROOT/docker/docker-compose.yml"

echo -e "${YELLOW}Cleaning up old containers...${NC}"
docker rm -f aquila_postgres aquila_redis aquila_rabbitmq aquila_api_gateway 2>/dev/null

echo -e "${YELLOW}Starting services...${NC}"
docker compose -f "$COMPOSE_FILE" --project-directory "$PROJECT_ROOT" up -d

echo -e "${YELLOW}Waiting for PostgreSQL...${NC}"
for i in {1..30}; do
    if docker exec aquila_postgres pg_isready -U aquila > /dev/null 2>&1; then
        echo -e "${GREEN}PostgreSQL is ready!${NC}"
        break
    fi
    sleep 2
done

echo -e "${YELLOW}Waiting for api-gateway...${NC}"
for i in {1..30}; do
    STATUS=$(docker inspect -f '{{.State.Status}}' aquila_api_gateway 2>/dev/null)
    if [ "$STATUS" = "running" ]; then
        echo -e "${GREEN}api-gateway is running!${NC}"
        sleep 3 
        break
    fi
    sleep 2
done


echo -e "${YELLOW}Running database migrations...${NC}"
# We add -e PYTHONPATH=/app/aquila_audit so Python can find the 'shared' package
docker exec -e PYTHONPATH=/app/aquila_audit -w /app/aquila_audit/shared/database aquila_api_gateway alembic upgrade head

# 6. Create initial data
echo -e "${YELLOW}Creating initial data...${NC}"
docker exec -e PYTHONPATH=/app/aquila_audit aquila_api_gateway python /app/aquila_audit/scripts/seed_data.py

echo -e "${GREEN}Database setup completed successfully!${NC}"