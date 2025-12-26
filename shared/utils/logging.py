import logging
import sys
from pathlib import Path
from typing import Optional
import structlog

from shared.utils.config import settings


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    service_name: str = "aquila"
) -> structlog.BoundLogger:
    """
    Setup structured logging for the application.
    
    Args:
        log_level: Logging level
        log_file: Optional file to write logs to
        service_name: Name of the service for logging
    
    Returns:
        Configured logger
    """
    # Create logs directory if it doesn't exist
    logs_dir = Path(settings.logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper()),
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # Add file handler if log_file is specified
    if log_file:
        file_handler = logging.FileHandler(
            logs_dir / f"{service_name}.log",
            encoding="utf-8"
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        logging.getLogger().addHandler(file_handler)
    
    return structlog.get_logger(service_name)


# Global logger instance
logger = setup_logging(
    log_level=settings.log_level,
    service_name="aquila"
)