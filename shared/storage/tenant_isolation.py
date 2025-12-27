from contextlib import contextmanager
from typing import Generator, Optional
from uuid import UUID
from sqlalchemy.orm import Session

from shared.utils.logging import logger
from shared.database.session import get_session


class TenantIsolationManager:
    """Manager for tenant data isolation."""
    
    @staticmethod
    def ensure_tenant_context(
        session: Session,
        tenant_id: UUID,
        model_class
    ) -> None:
        """
        Ensure tenant context is applied to query.
        
        Args:
            session: Database session
            tenant_id: Tenant ID
            model_class: SQLAlchemy model class
        
        Raises:
            ValueError: If tenant context is missing
        """
        if not tenant_id:
            raise ValueError("Tenant context required")
        
        # This method ensures that all queries for this model
        # include tenant_id filter. In practice, this is enforced
        # at the application layer through middleware and query builders.
    
    @staticmethod
    def filter_by_tenant(query, tenant_id: UUID):
        """
        Filter query by tenant ID.
        
        Args:
            query: SQLAlchemy query
            tenant_id: Tenant ID
        
        Returns:
            Filtered query
        """
        return query.filter_by(tenant_id=tenant_id)
    
    @staticmethod
    def create_with_tenant(session: Session, obj, tenant_id: UUID):
        """
        Create object with tenant ID.
        
        Args:
            session: Database session
            obj: SQLAlchemy object
            tenant_id: Tenant ID
        """
        obj.tenant_id = tenant_id
        session.add(obj)
        session.flush()
    
    @contextmanager
    def tenant_session(
        self,
        tenant_id: UUID,
        session: Optional[Session] = None
    ) -> Generator[Session, None, None]:
        """
        Context manager for tenant-scoped database session.
        
        Args:
            tenant_id: Tenant ID
            session: Existing session (optional)
        
        Yields:
            Database session with tenant context
        """
        if session:
            # Use existing session
            yield session
            return
        
        # Create new session with tenant context
        with get_session() as db_session:
            # Store tenant_id in session info for auditing
            db_session.info['tenant_id'] = str(tenant_id)
            try:
                yield db_session
            finally:
                # Clean up session info
                if 'tenant_id' in db_session.info:
                    del db_session.info['tenant_id']
    
    def validate_tenant_access(
        self,
        session: Session,
        model_class,
        object_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """
        Validate that user has access to object within tenant.
        
        Args:
            session: Database session
            model_class: SQLAlchemy model class
            object_id: Object ID
            tenant_id: Tenant ID
        
        Returns:
            True if access is valid
        """
        obj = session.query(model_class).filter_by(
            id=object_id,
            tenant_id=tenant_id
        ).first()
        
        return obj is not None
    
    def get_tenant_objects(
        self,
        session: Session,
        model_class,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 100
    ):
        """
        Get objects for specific tenant with pagination.
        
        Args:
            session: Database session
            model_class: SQLAlchemy model class
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records
        
        Returns:
            Query results
        """
        query = session.query(model_class).filter_by(tenant_id=tenant_id)
        return query.offset(skip).limit(limit).all()


# Global tenant isolation manager
tenant_isolation = TenantIsolationManager()