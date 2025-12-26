import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, DateTime, String, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr

from shared.database.base import Base


class BaseModel(Base):
    """Base model with common fields and methods."""
    
    __abstract__ = True
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    
    @declared_attr
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower()
    
    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def update(self, **kwargs):
        """Update model attributes."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class TenantBaseModel(BaseModel):
    """Base model for tenant-isolated entities."""
    
    __abstract__ = True
    
    tenant_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="Tenant identifier for data isolation"
    )
    
    @classmethod
    def query_with_tenant(cls, session, tenant_id: uuid.UUID):
        """Query with automatic tenant filtering."""
        return session.query(cls).filter(cls.tenant_id == tenant_id)


# Event listener for automatic updated_at
@event.listens_for(BaseModel, 'before_update', propagate=True)
def update_timestamp(mapper, connection, target):
    """Update the updated_at timestamp before update."""
    target.updated_at = datetime.utcnow()