from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from shared.models.base import BaseModel, TenantBaseModel
from shared.database.base import Base


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
    tenants = relationship("Tenant", secondary="user_tenants", back_populates="users")
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
        
        # Remove sensitive fields unless requested
        if not include_sensitive:
            data.pop("hashed_password", None)
            data.pop("mfa_secret", None)
            data.pop("recovery_codes", None)
        
        # Convert datetime to ISO format
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
    
    # Configuration
    config = Column(Text, nullable=True)  # JSON configuration
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Billing
    billing_tier = Column(String(50), default="free", nullable=False)
    monthly_allowance = Column(Text, nullable=True)  # JSON allowance config
    
    # Relationships
    users = relationship("User", secondary="user_tenants", back_populates="tenants")
    files = relationship("File", back_populates="tenant")
    rules = relationship("Rule", back_populates="tenant")
    findings = relationship("Finding", back_populates="tenant")
    reports = relationship("Report", back_populates="tenant")
    
    def __repr__(self):
        return f"<Tenant {self.name}>"
    
    @property
    def user_count(self) -> int:
        """Get number of users in tenant."""
        return len(self.users) if self.users else 0


class UserTenant(Base):
    """User-Tenant association model."""
    
    __tablename__ = "user_tenants"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    
    # Role in this tenant
    role = Column(String(50), default="member", nullable=False)
    
    # Timestamps
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", backref="tenant_associations")
    tenant = relationship("Tenant", backref="user_associations")


class UserRole(TenantBaseModel):
    """User role within a tenant."""
    
    __tablename__ = "user_roles"
    
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), nullable=False)  # tenant_admin, auditor, analyst, viewer
    
    # Permissions (JSON string of permission list)
    permissions = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="roles")
    
    def __repr__(self):
        return f"<UserRole user={self.user_id} role={self.role} tenant={self.tenant_id}>"
    
    @property
    def permission_list(self) -> List[str]:
        """Get permissions as list."""
        import json
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
    action = Column(String(100), nullable=False)  # login, logout, create, update, delete
    resource_type = Column(String(100), nullable=True)  # user, file, rule, etc.
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Details
    details = Column(Text, nullable=True)  # JSON details
    ip_address = Column(String(45), nullable=True)  # Support IPv6
    user_agent = Column(Text, nullable=True)
    
    # Status
    status = Column(String(50), default="success", nullable=False)  # success, failed
    error_message = Column(Text, nullable=True)
    
    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id}>"
    
    def to_dict(self) -> dict:
        """Convert audit log to dictionary."""
        data = super().to_dict()
        
        # Parse details if they exist
        if data.get("details"):
            import json
            try:
                data["details"] = json.loads(data["details"])
            except json.JSONDecodeError:
                pass
        
        return data