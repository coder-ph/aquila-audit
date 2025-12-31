"""
Update main.py to include reporting routes.
"""
#!/usr/bin/env python3
"""
Reporting Service - Generates audit reports in PDF, Excel, and HTML formats.
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
from pathlib import Path

from shared.utils.logging import logger
from shared.database.base import init_db
from shared.messaging.rabbitmq_client import rabbitmq_client
from services.reporting_service.config import config
from services.reporting_service.routes import reports_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Reporting Service")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
    
    # Connect to RabbitMQ
    try:
        rabbitmq_client.connect()
        logger.info("RabbitMQ connected")
    except Exception as e:
        logger.error(f"RabbitMQ connection failed: {str(e)}")
    
    # Ensure reports directory exists
    reports_dir = Path(config.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Ensure templates directory exists
    templates_dir = Path(config.templates_dir)
    templates_dir.mkdir(parents=True, exist_ok=True)
    
    # Create default templates if they don't exist
    from services.reporting_service.templates.template_manager import template_manager
    template_manager.ensure_default_templates()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Reporting Service")
    
    # Disconnect from RabbitMQ
    try:
        rabbitmq_client.disconnect()
    except Exception as e:
        logger.error(f"RabbitMQ disconnection failed: {str(e)}")


# Create FastAPI application
app = FastAPI(
    title=config.api_title,
    description=config.api_description,
    version=config.api_version,
    docs_url=config.api_docs_url,
    redoc_url=config.api_redoc_url,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(reports_routes.router)

# Health check endpoint
@app.get(config.health_check_path, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": config.api_title,
        "version": config.api_version,
        "timestamp": time.time(),
        "storage": {
            "reports_dir": config.reports_dir,
            "templates_dir": config.templates_dir
        }
    }


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
        host=config.host,
        port=config.port,
        reload=config.debug,
        log_config=None
    )