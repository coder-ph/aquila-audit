from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, Text, ForeignKey, Enum as SQLEnum, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import json

from shared.models.base import TenantBaseModel, Base
from shared.models.schemas import FileStatus


class File(TenantBaseModel):
    """File model for uploaded files."""
    
    __tablename__ = "files"
    
    # File information
    filename = Column(String(255), nullable=False)  # Unique filename in storage
    original_filename = Column(String(255), nullable=False)  # Original uploaded filename
    file_type = Column(String(50), nullable=False)  # csv, excel, json
    file_size = Column(Integer, nullable=False)  # Size in bytes
    storage_path = Column(String(500), nullable=False)  # Path in storage
    
    # Processing status
    status = Column(
        SQLEnum(FileStatus),
        default=FileStatus.UPLOADED,
        nullable=False
    )
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    
    # Metadata
    file_metadata = Column(JSONB, nullable=True)  # File metadata (columns, row count, etc.)
    processing_result = Column(JSONB, nullable=True)  # Processing results
    error_message = Column(Text, nullable=True)
    
    # Upload information
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Relationships - simplified to avoid circular references
    tenant = relationship("Tenant", back_populates="files")
    findings = relationship("Finding", back_populates="file")
    reports = relationship("Report", secondary="report_files", back_populates="files")
    # Indexes
    __table_args__ = (
        Index('ix_files_status', 'status'),
        Index('ix_files_uploaded_by', 'uploaded_by'),
        Index('ix_files_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<File {self.original_filename} ({self.status})>"
    
    @property
    def is_processed(self) -> bool:
        """Check if file is processed."""
        return self.status == FileStatus.PROCESSED
    
    @property
    def processing_duration(self) -> Optional[float]:
        """Get processing duration in seconds."""
        if self.processing_started_at and self.processing_completed_at:
            return (self.processing_completed_at - self.processing_started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert file to dictionary."""
        data = super().to_dict()
        
        # Convert JSONB fields
        for field in ["metadata", "processing_result"]:
            if data.get(field):
                if isinstance(data[field], dict):
                    # Already a dict
                    pass
                else:
                    # Try to parse as JSON
                    try:
                        data[field] = json.loads(data[field])
                    except (json.JSONDecodeError, TypeError):
                        data[field] = None
        
        # Add computed properties
        data["is_processed"] = self.is_processed
        data["processing_duration"] = self.processing_duration
        
        return data


class FileChunk(TenantBaseModel):
    """File chunk model for large file uploads."""
    
    __tablename__ = "file_chunks"
    
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    chunk_number = Column(Integer, nullable=False)
    chunk_size = Column(Integer, nullable=False)
    total_chunks = Column(Integer, nullable=False)
    chunk_data = Column(Text, nullable=False)  # Base64 encoded chunk data
    
    # Status
    is_uploaded = Column(Boolean, default=False, nullable=False)
    uploaded_at = Column(DateTime, nullable=True)
    
    # Relationships
    file = relationship("File", backref="chunks")
    
    # Unique constraint
    __table_args__ = (
        UniqueConstraint('file_id', 'chunk_number', name='uq_file_chunk'),
    )
    
    def __repr__(self):
        return f"<FileChunk {self.chunk_number}/{self.total_chunks} for file {self.file_id}>"


class FileValidation(TenantBaseModel):
    """File validation results."""
    
    __tablename__ = "file_validations"
    
    file_id = Column(UUID(as_uuid=True), ForeignKey("files.id"), nullable=False)
    validation_type = Column(String(100), nullable=False)  # schema, format, size, etc.
    is_valid = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)
    
    # Relationships
    file = relationship("File", backref="validations")
    
    def __repr__(self):
        status = "valid" if self.is_valid else "invalid"
        return f"<FileValidation {self.validation_type} ({status})>"