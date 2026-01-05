.PHONY: help setup dev test lint format clean db-migrate db-upgrade db-downgrade health down logs

help:
	@echo "Available commands:"
	@echo "  make setup      - Setup development environment"
	@echo "  make dev        - Start development services"
	@echo "  make test       - Run tests"
	@echo "  make lint       - Run linters"
	@echo "  make format     - Format code"
	@echo "  make clean      - Clean up temporary files"
	@echo "  make db-migrate - Create new migration"
	@echo "  make db-upgrade - Upgrade database to latest"
	@echo "  make db-downgrade - Downgrade database by one version"
	@echo "  make health     - Check service health"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View service logs"

setup:
	@echo "Setting up development environment..."
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	cp .env.example .env
	@echo "Please update .env with your configuration"

dev:
	@echo "Starting development services..."
	./scripts/start_services.sh

test:
	pytest tests/ -v --cov=services --cov=shared --cov-report=term-missing

lint:
	black --check services/ shared/ tests/
	isort --check-only services/ shared/ tests/
	flake8 services/ shared/ tests/
	mypy services/ shared/

format:
	black services/ shared/ tests/
	isort services/ shared/ tests/

clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

db-migrate:
	@read -p "Enter migration message: " message; \
	cd shared/database && alembic revision --autogenerate -m "$$message"

db-upgrade:
	cd shared/database && alembic upgrade head

db-downgrade:
	cd shared/database && alembic downgrade -1

health:
	@echo "Checking service health..."
	python3 scripts/health_check.py

down:
	@echo "Stopping all services..."
	docker-compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml down

logs:
	@echo "Showing service logs..."
	docker-compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml logs -f

# Week 11 Targets
setup-week11:
	@echo "Setting up Week 11 features..."
	@chmod +x scripts/setup_week11.sh
	@./scripts/setup_week11.sh

setup-dashboard:
	@echo "Setting up dashboard..."
	@python scripts/setup_dashboard.py

test-dashboard:
	@echo "Testing dashboard features..."
	@python scripts/test_dashboard.py

test-week11:
	@echo "Running Week 11 integration tests..."
	@python scripts/test_week11_integration.py

start-week11:
	@echo "Starting Week 11 services..."
	@docker-compose up -d admin-service billing-service
	@echo "Services started. Dashboard available at: http://localhost:8001/admin/dashboard"

stop-week11:
	@echo "Stopping Week 11 services..."
	@docker-compose stop admin-service billing-service

logs-week11:
	@echo "Showing Week 11 service logs..."
	@docker-compose logs -f admin-service billing-service

# Combined targets
week11-all: setup-week11 setup-dashboard start-week11
	@echo "Week 11 setup complete!"

week11-test: test-dashboard test-week11
	@echo "Week 11 tests complete!"

# Update existing test target
test: test-dashboard test-week11
	@echo "All tests completed!"