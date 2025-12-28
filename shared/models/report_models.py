from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Text, ForeignKey, Enum as SQLEnum, Table, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from shared.models.base import TenantBaseModel, Base
from shared.models.schemas import ReportFormat


# Association tables
report_files = Table(
    'report_files',
    Base.metadata,
    Column('report_id', UUID(as_uuid=True), ForeignKey('reports.id'), primary_key=True),
    Column('file_id', UUID(as_uuid=True), ForeignKey('files.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow, nullable=False)
)

report_findings = Table(
    'report_findings',
    Base.metadata,
    Column('report_id', UUID(as_uuid=True), ForeignKey('reports.id'), primary_key=True),
    Column('finding_id', UUID(as_uuid=True), ForeignKey('findings.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.utcnow, nullable=False)
)


class Report(TenantBaseModel):
    """Report model for generated audit reports."""
    
    __tablename__ = "reports"
    
    # Report information
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    report_format = Column(
        SQLEnum(ReportFormat),
        default=ReportFormat.PDF,
        nullable=False
    )
    
    # Status
    status = Column(String(50), default="pending", nullable=False)  # pending, generating, completed, failed
    file_path = Column(String(500), nullable=True)  # Path to generated report file
    error_message = Column(Text, nullable=True)
    
    # Parameters and configuration
    parameters = Column(JSONB, nullable=True)  # Report generation parameters
    config = Column(JSONB, nullable=True)  # Report configuration
    
    # Generation information
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    generated_at = Column(DateTime, nullable=True)
    
    # Relationships
    tenant = relationship("Tenant", back_populates="reports")
    files = relationship("File", secondary=report_files, back_populates="reports")
    findings = relationship("Finding", secondary=report_findings, back_populates="reports")
    
    def __repr__(self):
        return f"<Report {self.name} ({self.report_format})>"
    
    @property
    def is_completed(self) -> bool:
        """Check if report generation is completed."""
        return self.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        """Check if report generation failed."""
        return self.status == "failed"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        data = super().to_dict()
        
        # Add computed properties
        data["is_completed"] = self.is_completed
        data["is_failed"] = self.is_failed
        
        return data