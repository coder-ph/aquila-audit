"""
Billing Service - Handles usage tracking, billing, and subscriptions.
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
from datetime import datetime

from shared.utils.logging import logger
from shared.database.base import init_db
from shared.messaging.rabbitmq_client import rabbitmq_client
from shared.messaging.message_formats import MessageType
from shared.models.billing_models import BillingPlan

from services.billing_service.config import config
from services.billing_service.tracking.usage_tracker import usage_tracker
from services.billing_service.tracking.cost_calculator import cost_calculator
from services.billing_service.tracking.budget_enforcer import budget_enforcer
from services.billing_service.alerts.alert_manager import alert_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Billing Service")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
        
        # Create default billing plans if they don't exist
        create_default_billing_plans()
        
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    
    # Connect to RabbitMQ
    try:
        rabbitmq_client.connect()
        logger.info("RabbitMQ connected")
        
        # Start listening for usage events
        setup_message_consumers()
        
    except Exception as e:
        logger.error(f"RabbitMQ connection failed: {str(e)}")
    
    # Start background tasks
    try:
        # Start usage aggregation
        usage_tracker.start_background_aggregation()
        
        # Start alert monitoring
        alert_manager.start_monitoring()
        
        # Start budget enforcement
        budget_enforcer.start_monitoring()
        
    except Exception as e:
        logger.error(f"Failed to start background tasks: {str(e)}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Billing Service")
    
    # Stop background tasks
    try:
        usage_tracker.stop_background_aggregation()
        alert_manager.stop_monitoring()
        budget_enforcer.stop_monitoring()
    except Exception as e:
        logger.error(f"Failed to stop background tasks: {str(e)}")
    
    # Disconnect from RabbitMQ
    try:
        rabbitmq_client.disconnect()
    except Exception as e:
        logger.error(f"RabbitMQ disconnection failed: {str(e)}")


def create_default_billing_plans():
    """Create default billing plans if they don't exist."""
    from shared.database.session import get_db
    from sqlalchemy.orm import Session
    
    db: Session = next(get_db())
    
    # Check if plans already exist
    existing_plans = db.query(BillingPlan).count()
    if existing_plans > 0:
        return
    
    default_plans = [
        {
            "name": "Free",
            "description": "Basic plan for small projects",
            "price_per_month": 0.00,
            "currency": "USD",
            "max_users": 1,
            "max_storage_gb": 1,
            "max_files_per_month": 100,
            "max_api_calls": 1000,
            "features": {
                "basic_auditing": True,
                "pdf_reports": True,
                "email_support": False,
                "api_access": True
            },
            "is_active": True,
            "is_default": True
        },
        {
            "name": "Pro",
            "description": "For growing teams and businesses",
            "price_per_month": 49.00,
            "currency": "USD",
            "max_users": 10,
            "max_storage_gb": 100,
            "max_files_per_month": 5000,
            "max_api_calls": 50000,
            "features": {
                "basic_auditing": True,
                "pdf_reports": True,
                "excel_reports": True,
                "html_reports": True,
                "ai_explanations": True,
                "priority_support": True,
                "api_access": True,
                "custom_rules": True
            },
            "is_active": True,
            "is_default": False
        },
        {
            "name": "Enterprise",
            "description": "For large organizations with custom needs",
            "price_per_month": 299.00,
            "currency": "USD",
            "max_users": 100,
            "max_storage_gb": 1000,
            "max_files_per_month": 50000,
            "max_api_calls": 500000,
            "features": {
                "basic_auditing": True,
                "pdf_reports": True,
                "excel_reports": True,
                "html_reports": True,
                "ai_explanations": True,
                "24/7_support": True,
                "api_access": True,
                "custom_rules": True,
                "sso_integration": True,
                "custom_branding": True,
                "audit_trail": True,
                "compliance_reports": True
            },
            "is_active": True,
            "is_default": False
        }
    ]
    
    for plan_data in default_plans:
        plan = BillingPlan(**plan_data)
        db.add(plan)
    
    db.commit()
    logger.info("Created default billing plans")


def setup_message_consumers():
    """Setup RabbitMQ message consumers for billing events."""
    from services.billing_service.consumers.billing_consumer import billing_consumer
    
    # Start consumer in background thread
    import threading
    consumer_thread = threading.Thread(
        target=billing_consumer.start_consuming,
        daemon=True
    )
    consumer_thread.start()
    logger.info("Billing consumer started")


# Create FastAPI application
app = FastAPI(
    title=config.api_title,
    description=config.api_description,
    version=config.api_version,
    docs_url=config.api_docs_url,
    redoc_url=config.api_redoc_url,
    lifespan=lifespan
)


# Add middleware
if config.enable_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Add request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add request processing time to headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log slow requests
    if process_time > 1.0:
        logger.warning(
            "Slow request",
            path=request.url.path,
            method=request.method,
            process_time=process_time
        )
    
    return response


# Health check endpoint
@app.get(config.health_check_path, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": config.api_title,
        "version": config.api_version,
        "timestamp": time.time(),
        "database_connected": True,
        "rabbitmq_connected": rabbitmq_client.connected
    }


# Include routers
from services.billing_service.routes import billing_routes, usage_routes, subscription_routes

app.include_router(
    billing_routes.router,
    prefix=f"{config.api_prefix}/billing",
    tags=["Billing"]
)

app.include_router(
    usage_routes.router,
    prefix=f"{config.api_prefix}/usage",
    tags=["Usage"]
)

app.include_router(
    subscription_routes.router,
    prefix=f"{config.api_prefix}/subscriptions",
    tags=["Subscriptions"]
)


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "service": config.api_title,
        "version": config.api_version,
        "docs": config.api_docs_url,
        "health": config.health_check_path
    }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting {config.api_title} v{config.api_version}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.port,
        reload=config.debug,
        log_config=None
    )