#!/bin/bash

# Setup script for Week 9 Reporting Service features

echo "Setting up Week 9 Reporting Service features..."

# Create required directories
mkdir -p data/certificates
mkdir -p services/reporting_service/consumers
mkdir -p services/reporting_service/events
mkdir -p services/reporting_service/integrations

# Generate self-signed certificates for digital signatures
echo "Generating digital signature certificates..."
openssl req -x509 -newkey rsa:4096 -keyout data/certificates/private.key \
  -out data/certificates/signature.pem -days 365 -nodes -subj "/C=US/ST=State/L=City/O=Aquila/CN=aquila-audit.com"

# Set proper permissions
chmod 600 data/certificates/private.key
chmod 644 data/certificates/signature.pem

# Create RabbitMQ queues for reporting
echo "Setting up RabbitMQ queues for reporting..."
docker-compose -f docker/docker-compose.yml exec rabbitmq rabbitmqadmin declare queue name=report_generation_request durable=true
docker-compose -f docker/docker-compose.yml exec rabbitmq rabbitmqadmin declare queue name=report_generation_complete durable=true
docker-compose -f docker/docker-compose.yml declare queue name=report_generation_failed durable=true

# Declare exchanges
docker-compose -f docker/docker-compose.yml exec rabbitmq rabbitmqadmin declare exchange name=findings_events type=topic durable=true

# Setup queue bindings
docker-compose -f docker/docker-compose.yml exec rabbitmq rabbitmqadmin declare binding source=findings_events destination_type=queue destination=reporting_service_findings routing_key="findings.generated.*"

echo "Installing additional Python dependencies..."
pip install -r requirements-reporting.txt

echo "Running database migrations for reporting tables..."
alembic upgrade head

echo "Creating test data for reporting..."
python -c "
from shared.database.session import get_db
from shared.database.base import Base, engine
from shared.models.report_models import Report
import uuid

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Create a test report
db = next(get_db())
test_report = Report(
    id=uuid.uuid4(),
    tenant_id=uuid.uuid4(),
    user_id=uuid.uuid4(),
    report_type='pdf',
    status='test',
    parameters={'test': True}
)
db.add(test_report)
db.commit()
print('Test report created')
"

echo "Starting reporting service components..."
docker-compose -f docker/docker-compose.yml up -d reporting-worker reporting-consumer celery-beat

echo "Week 9 setup completed!"
echo ""
echo "Available reporting features:"
echo "1. Async report generation via Celery"
echo "2. RabbitMQ integration for event-driven reports"
echo "3. AI explanations via LLM integration"
echo "4. Event triggers from rule findings"
echo "5. Digital signatures for report authenticity"