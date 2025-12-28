from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum


# Enums
class FileStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class RuleType(str, Enum):
    VALIDATION = "validation"
    COMPLIANCE = "compliance"
    ANOMALY = "anomaly"


class FindingSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReportFormat(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"


# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    company: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @validator('password')
    def validate_password(cls, v):
        from shared.auth.password import validate_password_strength
        is_valid, errors = validate_password_strength(v)
        if not is_valid:
            raise ValueError(f"Password validation failed: {', '.join(errors)}")
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    is_verified: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Tenant Schemas
class TenantBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class TenantCreate(TenantBase):
    pass


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantBase):
    id: UUID
    is_active: bool
    billing_tier: str
    created_at: datetime
    updated_at: datetime
    user_count: Optional[int] = None
    
    class Config:
        from_attributes = True


# File Schemas
class FileBase(BaseModel):
    filename: str
    file_type: str
    file_size: int


class FileCreate(FileBase):
    original_filename: str
    storage_path: str


class FileUpdate(BaseModel):
    status: Optional[FileStatus] = None
    metadata: Optional[Dict[str, Any]] = None
    processing_result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class FileResponse(FileBase):
    id: UUID
    tenant_id: UUID
    status: FileStatus
    original_filename: str
    storage_path: str
    metadata: Optional[Dict[str, Any]] = None
    processing_result: Optional[Dict[str, Any]] = None
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Rule Schemas
class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    rule_type: RuleType
    rule_expression: str
    severity: FindingSeverity = FindingSeverity.MEDIUM
    is_active: bool = True


class RuleCreate(RuleBase):
    pass


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rule_type: Optional[RuleType] = None
    rule_expression: Optional[str] = None
    severity: Optional[FindingSeverity] = None
    is_active: Optional[bool] = None


class RuleResponse(RuleBase):
    id: UUID
    tenant_id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Finding Schemas
class FindingBase(BaseModel):
    rule_id: UUID
    file_id: UUID
    severity: FindingSeverity
    description: str
    raw_data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


class FindingCreate(FindingBase):
    pass


class FindingResponse(FindingBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Report Schemas
class ReportBase(BaseModel):
    name: str
    description: Optional[str] = None
    report_format: ReportFormat
    parameters: Dict[str, Any]


class ReportCreate(ReportBase):
    pass


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None


class ReportResponse(ReportBase):
    id: UUID
    tenant_id: UUID
    status: str
    file_path: Optional[str] = None
    generated_by: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# Pagination Schemas
class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


# Token Schemas
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    scope: Optional[str] = None


# Health Check
class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
    service: str
    version: str


# Error Response
class ErrorResponse(BaseModel):
    detail: str
    errors: Optional[List[Dict[str, Any]]] = None
    request_id: Optional[str] = None