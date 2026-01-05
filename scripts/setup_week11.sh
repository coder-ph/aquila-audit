#!/bin/bash

# Setup script for Week 11 - Dashboard, Billing, and Monitoring

set -e

echo "Setting up Week 11 features..."

# Create necessary directories
echo "Creating dashboard directories..."
mkdir -p data/dashboards
mkdir -p data/billing
mkdir -p data/monitoring

# Create billing database tables
echo "Setting up billing database tables..."
python -c "
from shared.database.session import SessionLocal
from shared.models.billing_models import Base
from shared.database.base import engine

print('Creating billing tables...')
Base.metadata.create_all(bind=engine, tables=[
    Base.metadata.tables['subscriptions'],
    Base.metadata.tables['billing_cycles'],
    Base.metadata.tables['usage_records'],
    Base.metadata.tables['invoices']
])
print('Billing tables created successfully!')
"

# Create default dashboard configs
echo "Creating dashboard configurations..."
cat > data/dashboards/default_config.json << EOF
{
    "charts": {
        "usage_over_time": {
            "type": "line",
            "title": "API Usage Over Time",
            "refresh_interval": 300
        },
        "tenant_activity": {
            "type": "bar",
            "title": "Tenant Activity",
            "refresh_interval": 600
        },
        "cost_distribution": {
            "type": "pie",
            "title": "Cost Distribution",
            "refresh_interval": 900
        }
    },
    "widgets": ["usage_summary", "active_tenants", "revenue_today"],
    "refresh_rate": 30
}
EOF

# Setup billing queues
echo "Setting up billing message queues..."
python -c "
from shared.messaging.rabbitmq_client import rabbitmq_client
import time

print('Waiting for RabbitMQ...')
time.sleep(5)

rabbitmq_client.connect()

# Declare billing queues
queues = [
    'billing.usage_updates',
    'billing.alerts',
    'billing.invoices',
    'billing.payments'
]

for queue in queues:
    rabbitmq_client.channel.queue_declare(
        queue=queue,
        durable=True,
        arguments={'x-queue-type': 'quorum'}
    )
    print(f'Declared queue: {queue}')

print('Billing queues setup complete!')
rabbitmq_client.disconnect()
"

# Create billing service config
echo "Creating billing service environment..."
cat > .env.billing << EOF
# Billing Service Configuration
BILLING_SERVICE_PORT=8006
BILLING_REDIS_PREFIX=billing
BILLING_CURRENCY=USD
BILLING_TIMEZONE=UTC

# Alert Thresholds
ALERT_THRESHOLD_PERCENTAGE=80
ALERT_COOLDOWN_MINUTES=30

# Usage Tracking
USAGE_SAMPLE_INTERVAL=60
USAGE_RETENTION_DAYS=90

# Invoice Settings
INVOICE_DAYS_DUE=30
INVOICE_TAX_RATE=0.0

# Subscription Plans
PLAN_BASIC_PRICE=99.00
PLAN_PRO_PRICE=299.00
PLAN_ENTERPRISE_PRICE=999.00
EOF

# Update main .env file with billing variables
echo "Updating main .env file..."
if [ ! -f .env ]; then
    cp .env.example .env 2>/dev/null || touch .env
fi

# Add billing variables if not present
grep -q "^BILLING_" .env || cat .env.billing >> .env

echo "Creating test billing data..."
python -c "
from shared.database.session import SessionLocal
from shared.models.billing_models import Subscription, BillingCycle
from datetime import datetime, timedelta

db = SessionLocal()

# Create test subscriptions
subscriptions = [
    Subscription(
        tenant_id='tenant_001',
        plan_type='pro',
        monthly_price=299.00,
        status='active',
        billing_day=15,
        features={'api_calls': 10000, 'storage_gb': 100, 'users': 10}
    ),
    Subscription(
        tenant_id='tenant_002',
        plan_type='basic',
        monthly_price=99.00,
        status='active',
        billing_day=1,
        features={'api_calls': 1000, 'storage_gb': 10, 'users': 3}
    )
]

for sub in subscriptions:
    db.add(sub)

db.commit()

# Create current billing cycles
for sub in subscriptions:
    cycle = BillingCycle(
        subscription_id=sub.id,
        start_date=datetime.now().replace(day=sub.billing_day),
        end_date=(datetime.now().replace(day=sub.billing_day) + timedelta(days=30)),
        total_amount=sub.monthly_price,
        status='active'
    )
    db.add(cycle)

db.commit()
db.close()
print('Test billing data created!')
"

echo "Week 11 setup complete!"
echo ""
echo "To start the services, run:"
echo "docker-compose up -d"
echo ""
echo "Dashboard available at: http://localhost:8001/admin/dashboard"
echo "Billing API available at: http://localhost:8006/billing/docs"