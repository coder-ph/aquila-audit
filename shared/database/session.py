from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy.orm import Session

from shared.database.base import SessionLocal
from shared.utils.logging import logger


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic cleanup.
    
    Yields:
        Database session
    """
    session: Optional[Session] = None
    try:
        session = SessionLocal()
        yield session
        session.commit()
    except Exception as e:
        if session:
            session.rollback()
        logger.error("Database session error", error=str(e))
        raise
    finally:
        if session:
            session.close()


class DatabaseSessionManager:
    """Manager for database sessions with tenant isolation."""
    
    def __init__(self):
        self.session_factory = SessionLocal
    
    def __enter__(self) -> Session:
        self.session = self.session_factory()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.session_factory()
    
def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()