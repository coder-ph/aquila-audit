#!/usr/bin/env python3
"""
Worker service entry point.
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.utils.logging import logger
from services.worker_service.celery_app import celery_app


if __name__ == "__main__":
    logger.info("Starting Aquila Worker Service")
    
    # Start Celery worker
    argv = [
        "worker",
        "--loglevel=info",
        "--concurrency=4",
        "--hostname=worker@%h",
        "--queues=file_processing,rule_evaluation,report_generation"
    ]
    
    celery_app.start(argv)