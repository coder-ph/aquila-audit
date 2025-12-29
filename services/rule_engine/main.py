#!/usr/bin/env python3
"""
Rule Engine Service - Evaluates rules against data and generates findings.
"""
from fastapi import FastAPI, HTTPException, status
from contextlib import asynccontextmanager
import time

from shared.utils.logging import logger
from shared.database.base import init_db
from shared.messaging.rabbitmq_client import rabbitmq_client
from services.rule_engine.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Rule Engine Service")
    
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
    
    yield
    
    # Shutdown
    logger.info("Shutting down Rule Engine Service")
    
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
    return {
        "status": "healthy",
        "service": config.api_title,
        "version": config.api_version,
        "timestamp": time.time()
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