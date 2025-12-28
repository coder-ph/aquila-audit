from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import json

from shared.models.base import BaseModel, TenantBaseModel, Base

class UserTenant(Base):
    """User-Tenant association model (Declarative version)."""
    
    __tablename__ = "user_tenants"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    
    # Extra data on the relationship
    role = Column(String(50), default="member", nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="tenant_associations")
    tenant = relationship("Tenant", back_populates="user_associations")

class User(BaseModel):
    """User model."""
    
    __tablename__ = "users"
    
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    # MFA
    mfa_secret = Column(String(255), nullable=True)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    recovery_codes = Column(Text, nullable=True)  # JSON array as string
    
    # Timestamps
    last_login = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant_associations = relationship("UserTenant", back_populates="user", cascade="all, delete-orphan")
    tenants = relationship("Tenant", secondary="user_tenants", viewonly=True)
    roles = relationship("UserRole", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self.is_active and self.is_verified
    
    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convert user to dictionary."""
        data = super().to_dict()
        
        if not include_sensitive:
            data.pop("hashed_password", None)
            data.pop("mfa_secret", None)
            data.pop("recovery_codes", None)
        
        for field in ["last_login", "password_changed_at"]:
            if data.get(field):
                data[field] = data[field].isoformat()
        
        return data

class Tenant(BaseModel):
    """Tenant model."""
    
    __tablename__ = "tenants"
    
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)  # JSON configuration
    is_active = Column(Boolean, default=True, nullable=False)
    billing_tier = Column(String(50), default="free", nullable=False)
    monthly_allowance = Column(JSON, nullable=True)  # JSON allowance config

    # Relationships
    user_associations = relationship("UserTenant", back_populates="tenant", cascade="all, delete-orphan")
    users = relationship("User", secondary="user_tenants", viewonly=True)
    files = relationship("File", back_populates="tenant")
    rules = relationship("Rule", back_populates="tenant")
    findings = relationship("Finding", back_populates="tenant")
    reports = relationship("Report", back_populates="tenant")
    
    def __repr__(self):
        return f"<Tenant {self.name}>"
    
    @property
    def user_count(self) -> int:
        """Get number of users in tenant."""
        return len(self.user_associations) if self.user_associations else 0

class UserRole(TenantBaseModel):
    """User role within a tenant."""
    __tablename__ = "user_roles"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False)
    permissions = Column(Text, nullable=True)
    user = relationship("User", back_populates="roles")

    @property
    def permission_list(self) -> List[str]:
        if self.permissions:
            try:
                return json.loads(self.permissions)
            except json.JSONDecodeError:
                return []
        return []

class AuditLog(TenantBaseModel):
    """Audit log for tracking user actions."""
    __tablename__ = "audit_logs"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    status = Column(String(50), default="success", nullable=False)
    error_message = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        data = super().to_dict()
        if data.get("details"):
            try:
                data["details"] = json.loads(data["details"])
            except json.JSONDecodeError:
                pass
        return data