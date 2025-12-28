from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Text, ForeignKey, Enum as SQLEnum, Index, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import json

from shared.models.base import TenantBaseModel
from shared.models.schemas import FindingSeverity


class Finding(TenantBaseModel):
    """Finding model for audit findings."""
    
    __tablename__ = "findings"
    
    # Identification
    rule_id = Column(UUID(as_uuid=True), ForeignKey("rules.id"), nullable=False)
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    
    # Finding details
    severity = Column(
        SQLEnum(FindingSeverity),
        default=FindingSeverity.MEDIUM,
        nullable=False
    )
    description = Column(Text, nullable=False)
    
    # Data and context
    raw_data = Column(JSONB, nullable=False)  # Original data that triggered finding
    context = Column(JSONB, nullable=True)  # Additional context data
    location = Column(JSONB, nullable=True)  # Location in file (row, column, etc.)
    
    # Status
    status = Column(String(50), default="open", nullable=False)  # open, reviewing, resolved, false_positive
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    
    # AI explanations
    ai_explanation = Column(Text, nullable=True)
    ai_confidence = Column(JSONB, nullable=True)  # Confidence scores from AI
    
    # Relationships
    rule = relationship("Rule", back_populates="findings")
    file = relationship("File", back_populates="findings")
    tenant = relationship("Tenant", back_populates="findings")
    reports = relationship("Report", secondary="report_findings", back_populates="findings")
    
    # Indexes
    __table_args__ = (
        Index('ix_findings_severity', 'severity'),
        Index('ix_findings_status', 'status'),
        Index('ix_findings_rule_id', 'rule_id'),
        Index('ix_findings_file_id', 'file_id'),
        Index('ix_findings_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Finding {self.severity}: {self.description[:50]}...>"
    
    @property
    def is_resolved(self) -> bool:
        """Check if finding is resolved."""
        return self.status in ["resolved", "false_positive"]
    
    @property
    def needs_attention(self) -> bool:
        """Check if finding needs attention."""
        return self.severity in ["high", "critical"] and not self.is_resolved
    
    def to_dict(self, include_raw_data: bool = True) -> Dict[str, Any]:
        """Convert finding to dictionary."""
        data = super().to_dict()
        
        if not include_raw_data:
            data.pop("raw_data", None)
        
        # Add computed properties
        data["is_resolved"] = self.is_resolved
        data["needs_attention"] = self.needs_attention
        
        return data


class FindingComment(TenantBaseModel):
    """Comments on findings."""
    
    __tablename__ = "finding_comments"
    
    finding_id = Column(UUID(as_uuid=True), ForeignKey("findings.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    comment = Column(Text, nullable=False)
    
    # Status
    is_internal = Column(Boolean, default=False, nullable=False)  # Internal note vs user comment
    
    # Relationships
    finding = relationship("Finding", backref="comments")
    user = relationship("User", backref="finding_comments")
    
    def __repr__(self):
        return f"<FindingComment on finding {self.finding_id}>"