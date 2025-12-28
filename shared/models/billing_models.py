from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, Numeric, Boolean, ForeignKey, Enum as SQLEnum, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from shared.models.base import TenantBaseModel


class BillingPlan(TenantBaseModel):
    """Billing plan model."""
    
    __tablename__ = "billing_plans"
    
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    
    # Pricing
    price_per_month = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    
    # Limits
    max_users = Column(Integer, nullable=True)
    max_storage_gb = Column(Integer, nullable=True)
    max_files_per_month = Column(Integer, nullable=True)
    max_api_calls = Column(Integer, nullable=True)
    
    
    features = Column(JSONB, nullable=True)  
    
    
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    
    def __repr__(self):
        return f"<BillingPlan {self.name}>"


class Subscription(TenantBaseModel):
    """Subscription model."""
    
    __tablename__ = "subscriptions"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    billing_plan_id = Column(UUID(as_uuid=True), ForeignKey("billing_plans.id"), nullable=False)
    
    # Subscription details
    status = Column(String(50), default="active", nullable=False)  # active, canceled, expired
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    
    # Billing information
    stripe_subscription_id = Column(String(100), nullable=True)
    stripe_customer_id = Column(String(100), nullable=True)
    
    # Trial information
    is_trial = Column(Boolean, default=False, nullable=False)
    trial_ends_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", backref="subscriptions")
    billing_plan = relationship("BillingPlan", backref="subscriptions")
    invoices = relationship("Invoice", back_populates="subscription")
    
    def __repr__(self):
        return f"<Subscription tenant={self.tenant_id} plan={self.billing_plan_id}>"
    
    @property
    def is_active(self) -> bool:
        """Check if subscription is active."""
        return self.status == "active" and datetime.utcnow() < self.current_period_end


class Invoice(TenantBaseModel):
    """Invoice model."""
    
    __tablename__ = "invoices"
    
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False)
    
    # Invoice details
    invoice_number = Column(String(100), unique=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=False)
    
    # Status
    status = Column(String(50), default="draft", nullable=False)  # draft, sent, paid, overdue, void
    paid_at = Column(DateTime, nullable=True)
    due_date = Column(DateTime, nullable=False)
    
    # Stripe integration
    stripe_invoice_id = Column(String(100), nullable=True)
    stripe_payment_intent_id = Column(String(100), nullable=True)
    
    # Relationships
    subscription = relationship("Subscription", back_populates="invoices")
    
    def __repr__(self):
        return f"<Invoice {self.invoice_number} ({self.status})>"


class UsageRecord(TenantBaseModel):
    """Usage record for billing."""
    
    __tablename__ = "usage_records"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    
    # Usage metrics
    metric_name = Column(String(100), nullable=False)  # file_uploads, api_calls, storage_bytes
    metric_value = Column(Integer, nullable=False)
    recorded_at = Column(DateTime, nullable=False)
    
    # Context
    context = Column(JSONB, nullable=True)  # Additional context (file_id, user_id, etc.)
    
    # Relationships
    tenant = relationship("Tenant", backref="usage_records")
    
    # Indexes
    __table_args__ = (
        Index('ix_usage_records_metric_name', 'metric_name'),
        Index('ix_usage_records_recorded_at', 'recorded_at'),
    )
    
    def __repr__(self):
        return f"<UsageRecord {self.metric_name}={self.metric_value}>"