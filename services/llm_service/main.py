#!/usr/bin/env python3
"""
LLM Service - AI-powered explanations and analysis using Large Language Models.
"""
from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
import time

from shared.utils.logging import logger
from shared.database.base import init_db
from shared.messaging.rabbitmq_client import rabbitmq_client
from services.llm_service.config import config
from services.llm_service.budget.budget_manager import budget_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting LLM Service")
    
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
    
    # Initialize budget manager
    try:
        budget_manager.load_budgets()
        logger.info("Budget manager initialized")
    except Exception as e:
        logger.error(f"Budget manager initialization failed: {str(e)}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down LLM Service")
    
    # Save budgets
    try:
        budget_manager.save_budgets()
    except Exception as e:
        logger.error(f"Budget save failed: {str(e)}")
    
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


# Health check endpoint
@app.get(config.health_check_path, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    from services.llm_service.clients.openai_client import openai_client
    
    health_status = {
        "status": "healthy",
        "service": config.api_title,
        "version": config.api_version,
        "timestamp": time.time(),
        "openai_status": openai_client.get_status(),
        "budget_status": budget_manager.get_total_usage()
    }
    
    return health_status


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