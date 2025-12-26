.PHONY: help setup dev test lint format clean db-migrate db-upgrade db-downgrade

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

setup:
	@echo "Setting up development environment..."
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	cp .env.example .env
	@echo "Please update .env with your configuration"

dev:
	docker-compose -f docker/docker-compose.yml -f docker/docker-compose.override.yml up --build

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