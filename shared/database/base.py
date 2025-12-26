from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import QueuePool

from shared.utils.config import settings
from shared.utils.logging import logger


# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    str(settings.database_url),
    poolclass=QueuePool,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,
    echo=settings.debug,
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create scoped session for thread safety
ScopedSession = scoped_session(SessionLocal)

# Create declarative base
Base = declarative_base()

# Metadata for alembic
metadata = Base.metadata


def get_db():
    """
    Get database session.
    
    Yields:
        Database session
    """
    db = ScopedSession()
    try:
        yield db
    except Exception as e:
        logger.error("Database session error", error=str(e))
        db.rollback()
        raise
    finally:
        ScopedSession.remove()


def init_db():
    """
    Initialize database tables.
    """
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error("Failed to create database tables", error=str(e))
        raise