"""
Pydantic Models for Receipt Service API
=======================================

Request/Response models for the Receipt service REST API.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ReceiptCreateRequest(BaseModel):
    """Request model for creating new receipts."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    receipt_type: str = Field(..., min_length=1, max_length=100, description="Type of receipt")
    subject: str = Field(..., min_length=1, max_length=255, description="What this receipt is for")
    reference_id: Optional[UUID] = Field(None, description="Reference to related entity")
    receipt_data: Dict[str, Any] = Field(..., description="The actual receipt content")
    compliance_tags: Optional[Dict[str, Any]] = Field(None, description="Compliance metadata")
    retention_days: Optional[int] = Field(None, gt=0, le=36500, description="Custom retention period in days")


class ReceiptResponse(BaseModel):
    """Response model for receipt operations."""
    
    model_config = ConfigDict(from_attributes=True)
    
    receipt_id: UUID
    tenant_id: UUID
    receipt_type: str
    subject: str
    reference_id: Optional[UUID]
    receipt_data: Dict[str, Any]
    content_hash: str
    signature: str
    signing_key_id: str
    worm_storage_path: Optional[str]
    worm_written_at: Optional[datetime]
    retention_until: Optional[datetime]
    compliance_tags: Optional[Dict[str, Any]]
    is_verified: bool
    verification_failures: int
    last_verified_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ReceiptVerifyRequest(BaseModel):
    """Request model for verifying receipt integrity."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    verify_signature: bool = Field(True, description="Verify Ed25519 signature")
    verify_worm_storage: bool = Field(False, description="Verify WORM storage integrity")
    update_verification_timestamp: bool = Field(True, description="Update last verified timestamp")


class ReceiptVerifyResponse(BaseModel):
    """Response model for receipt verification."""
    
    receipt_id: UUID
    is_valid: bool
    content_hash_valid: bool
    signature_valid: bool
    worm_storage_valid: Optional[bool]
    verification_errors: List[str]
    verified_at: datetime


class AuditLogEntry(BaseModel):
    """Response model for audit log entries."""
    
    model_config = ConfigDict(from_attributes=True)
    
    audit_id: UUID
    receipt_id: UUID
    event_type: str
    event_source: str
    user_id: Optional[str]
    client_ip: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    event_data: Optional[Dict[str, Any]]
    success: bool
    error_message: Optional[str]
    processing_time_ms: Optional[int]
    created_at: datetime


class AuditExportRequest(BaseModel):
    """Request model for audit log export."""
    
    start_date: Optional[datetime] = Field(None, description="Start date for export (inclusive)")
    end_date: Optional[datetime] = Field(None, description="End date for export (inclusive)")
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")
    receipt_types: Optional[List[str]] = Field(None, description="Filter by receipt types")
    format: str = Field("json", pattern="^(json|csv|syslog)$", description="Export format")
    include_receipt_data: bool = Field(False, description="Include full receipt data in export")


class AuditExportResponse(BaseModel):
    """Response model for audit export."""
    
    export_id: UUID
    total_records: int
    export_format: str
    export_url: Optional[str] = Field(None, description="Download URL if available")
    expires_at: Optional[datetime] = Field(None, description="Export URL expiration")
    created_at: datetime


class RetentionPolicyRequest(BaseModel):
    """Request model for creating retention policies."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    policy_name: str = Field(..., min_length=1, max_length=100, description="Policy name")
    receipt_types: List[str] = Field(..., min_items=1, description="Receipt types this policy applies to")
    retention_days: int = Field(..., gt=0, le=36500, description="Retention period in days")
    description: Optional[str] = Field(None, max_length=1000, description="Policy description")
    compliance_requirements: Optional[Dict[str, Any]] = Field(None, description="Regulatory requirements")
    auto_delete: bool = Field(False, description="Auto-delete after retention period")
    priority: int = Field(100, gt=0, le=1000, description="Policy priority (lower = higher priority)")


class RetentionPolicyResponse(BaseModel):
    """Response model for retention policies."""
    
    model_config = ConfigDict(from_attributes=True)
    
    policy_id: UUID
    tenant_id: UUID
    policy_name: str
    receipt_types: List[str]
    retention_days: int
    is_active: bool
    priority: int
    description: Optional[str]
    compliance_requirements: Optional[Dict[str, Any]]
    auto_delete: bool
    created_at: datetime
    updated_at: datetime


class WormStorageRequest(BaseModel):
    """Request model for WORM storage operations."""
    
    storage_provider: str = Field(..., min_length=1, max_length=50, description="WORM storage provider")
    force_rewrite: bool = Field(False, description="Force rewrite if already exists")


class WormStorageResponse(BaseModel):
    """Response model for WORM storage operations."""
    
    model_config = ConfigDict(from_attributes=True)
    
    worm_id: UUID
    receipt_id: UUID
    storage_provider: str
    storage_path: str
    storage_checksum: str
    written_at: datetime
    written_by: Optional[str]
    write_transaction_id: Optional[str]
    is_accessible: bool


class HealthResponse(BaseModel):
    """Response model for health check."""
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})
    
    status: str
    timestamp: datetime
    version: str
    database_status: str
    worm_storage_status: str
    checks: Dict[str, Any]


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
