"""
Pydantic Schemas for Audit Service API
======================================

A.27 Implementation: Request/response models for the comprehensive audit logging service.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, validator


class EventTypeEnum(str, Enum):
    """Standard audit event types."""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    SYSTEM_CONFIGURATION = "system_configuration"
    USER_MANAGEMENT = "user_management"
    API_ACCESS = "api_access"
    FILE_ACCESS = "file_access"
    SECURITY_ALERT = "security_alert"
    COMPLIANCE_EVENT = "compliance_event"


class EventSeverityEnum(str, Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ExportFormatEnum(str, Enum):
    """Supported SIEM export formats."""
    JSON = "json"
    CSV = "csv"
    SYSLOG = "syslog"
    CEF = "cef"


class AuditEventCreate(BaseModel):
    """Request model for creating audit events."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    # Event identification
    tenant_id: UUID = Field(..., description="Tenant identifier")
    correlation_id: Optional[str] = Field(None, max_length=255, description="Cross-service correlation ID")
    parent_event_id: Optional[UUID] = Field(None, description="Parent event for event chains")
    
    # Event classification
    event_type: EventTypeEnum = Field(..., description="Type of audit event")
    event_category: str = Field(..., max_length=100, description="Event category")
    event_action: str = Field(..., max_length=255, description="Specific action performed")
    event_severity: EventSeverityEnum = Field(EventSeverityEnum.INFO, description="Event severity level")
    
    # Source information
    service_name: str = Field(..., max_length=100, description="Originating service name")
    service_version: Optional[str] = Field(None, max_length=50, description="Service version")
    endpoint: Optional[str] = Field(None, max_length=500, description="API endpoint or resource")
    method: Optional[str] = Field(None, max_length=10, description="HTTP method")
    
    # Actor information
    user_id: Optional[str] = Field(None, max_length=255, description="User identifier")
    user_type: Optional[str] = Field(None, max_length=50, description="Type of actor (human, service, system)")
    session_id: Optional[str] = Field(None, max_length=255, description="Session identifier")
    
    # Security context
    client_ip: Optional[str] = Field(None, max_length=45, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    authentication_method: Optional[str] = Field(None, max_length=100, description="Authentication method used")
    authorization_context: Optional[Dict[str, Any]] = Field(None, description="Authorization context data")
    
    # Event timing
    event_timestamp: Optional[datetime] = Field(None, description="Event timestamp (defaults to now)")
    processing_time_ms: Optional[int] = Field(None, ge=0, description="Processing time in milliseconds")
    
    # Request/Response data
    request_id: Optional[str] = Field(None, max_length=255, description="Request identifier")
    request_data: Optional[Dict[str, Any]] = Field(None, description="Request data (PII will be redacted)")
    response_code: Optional[int] = Field(None, description="Response code")
    response_data: Optional[Dict[str, Any]] = Field(None, description="Response data (PII will be redacted)")
    
    # Event details
    event_description: str = Field(..., description="Human-readable event description")
    event_data: Optional[Dict[str, Any]] = Field(None, description="Additional structured event data")
    tags: Optional[List[str]] = Field(None, description="Searchable tags")
    
    # Result information
    success: bool = Field(..., description="Whether the operation was successful")
    error_code: Optional[str] = Field(None, max_length=50, description="Error code if applicable")
    error_message: Optional[str] = Field(None, description="Error message if applicable")
    
    # Compliance and retention
    compliance_tags: Optional[Dict[str, Any]] = Field(None, description="Compliance metadata")
    source_system: Optional[str] = Field(None, max_length=100, description="Source system identifier")
    environment: Optional[str] = Field(None, max_length=50, description="Environment (prod, staging, dev)")


class AuditEventResponse(BaseModel):
    """Response model for audit events."""
    
    model_config = ConfigDict(from_attributes=True)
    
    event_id: UUID
    tenant_id: UUID
    correlation_id: Optional[str]
    parent_event_id: Optional[UUID]
    
    event_type: str
    event_category: str
    event_action: str
    event_severity: str
    
    service_name: str
    service_version: Optional[str]
    endpoint: Optional[str]
    method: Optional[str]
    
    user_id: Optional[str]
    user_type: Optional[str]
    session_id: Optional[str]
    
    client_ip: Optional[str]
    user_agent: Optional[str]
    authentication_method: Optional[str]
    authorization_context: Optional[Dict[str, Any]]
    
    event_timestamp: datetime
    processing_time_ms: Optional[int]
    
    request_id: Optional[str]
    request_data: Optional[Dict[str, Any]]
    response_code: Optional[int]
    response_data: Optional[Dict[str, Any]]
    
    event_description: str
    event_data: Optional[Dict[str, Any]]
    tags: Optional[List[str]]
    
    success: bool
    error_code: Optional[str]
    error_message: Optional[str]
    
    compliance_tags: Optional[Dict[str, Any]]
    retention_until: Optional[datetime]
    pii_redacted: bool
    
    created_at: datetime
    source_system: Optional[str]
    environment: Optional[str]


class AuditEventSearch(BaseModel):
    """Request model for searching audit events."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    # Pagination
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(100, ge=1, le=10000, description="Events per page")
    
    # Time filtering
    start_date: Optional[datetime] = Field(None, description="Search events after this timestamp")
    end_date: Optional[datetime] = Field(None, description="Search events before this timestamp")
    
    # Event filtering
    event_types: Optional[List[EventTypeEnum]] = Field(None, description="Filter by event types")
    event_categories: Optional[List[str]] = Field(None, description="Filter by event categories")
    event_actions: Optional[List[str]] = Field(None, description="Filter by event actions")
    severities: Optional[List[EventSeverityEnum]] = Field(None, description="Filter by severity levels")
    
    # Source filtering
    service_names: Optional[List[str]] = Field(None, description="Filter by service names")
    user_ids: Optional[List[str]] = Field(None, description="Filter by user IDs")
    client_ips: Optional[List[str]] = Field(None, description="Filter by client IP addresses")
    
    # Content filtering
    correlation_id: Optional[str] = Field(None, description="Find events with this correlation ID")
    search_text: Optional[str] = Field(None, description="Free text search in descriptions")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    
    # Result filtering
    success_only: Optional[bool] = Field(None, description="Filter by success/failure status")
    error_codes: Optional[List[str]] = Field(None, description="Filter by error codes")
    
    # Compliance filtering
    compliance_frameworks: Optional[List[str]] = Field(None, description="Filter by compliance frameworks")
    
    # Sorting
    sort_by: str = Field("event_timestamp", description="Sort field")
    sort_order: str = Field("desc", pattern="^(asc|desc)$", description="Sort order")


class AuditEventSearchResponse(BaseModel):
    """Response model for audit event searches."""
    
    events: List[AuditEventResponse]
    total_count: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    execution_time_ms: int


class RetentionPolicyCreate(BaseModel):
    """Request model for creating retention policies."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    tenant_id: UUID = Field(..., description="Tenant identifier")
    policy_name: str = Field(..., min_length=1, max_length=200, description="Policy name")
    policy_description: Optional[str] = Field(None, description="Policy description")
    
    event_types: List[str] = Field(..., min_items=1, description="Event types this policy applies to")
    retention_days: int = Field(..., gt=0, le=36500, description="Retention period in days")
    archive_after_days: Optional[int] = Field(None, gt=0, description="Archive to cold storage after days")
    
    compliance_framework: Optional[str] = Field(None, max_length=100, description="Compliance framework")
    regulatory_requirements: Optional[Dict[str, Any]] = Field(None, description="Regulatory requirements")
    legal_hold_exempt: bool = Field(False, description="Exempt from legal holds")
    
    conditions: Optional[Dict[str, Any]] = Field(None, description="Additional matching conditions")
    priority: int = Field(100, gt=0, le=1000, description="Policy priority (lower = higher priority)")
    
    effective_from: Optional[datetime] = Field(None, description="Policy effective start date")
    effective_until: Optional[datetime] = Field(None, description="Policy effective end date")


class RetentionPolicyResponse(BaseModel):
    """Response model for retention policies."""
    
    model_config = ConfigDict(from_attributes=True)
    
    policy_id: UUID
    tenant_id: UUID
    policy_name: str
    policy_description: Optional[str]
    policy_version: str
    
    event_types: List[str]
    retention_days: int
    archive_after_days: Optional[int]
    
    compliance_framework: Optional[str]
    regulatory_requirements: Optional[Dict[str, Any]]
    legal_hold_exempt: bool
    
    conditions: Optional[Dict[str, Any]]
    priority: int
    status: str
    
    effective_from: datetime
    effective_until: Optional[datetime]
    
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]


class AuditExportCreate(BaseModel):
    """Request model for creating audit exports."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    tenant_id: UUID = Field(..., description="Tenant identifier")
    export_format: ExportFormatEnum = Field(..., description="Export format")
    
    start_date: datetime = Field(..., description="Export events from this date")
    end_date: datetime = Field(..., description="Export events until this date")
    
    event_types: Optional[List[EventTypeEnum]] = Field(None, description="Filter by event types")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional export filters")
    
    include_pii: bool = Field(False, description="Include PII data (requires special permissions)")
    compression: Optional[str] = Field(None, pattern="^(gzip|zip)$", description="Compression format")
    
    @validator('end_date')
    def validate_date_range(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v


class AuditExportResponse(BaseModel):
    """Response model for audit exports."""
    
    model_config = ConfigDict(from_attributes=True)
    
    export_id: UUID
    tenant_id: UUID
    export_format: str
    
    start_date: datetime
    end_date: datetime
    event_types: Optional[List[str]]
    filters: Optional[Dict[str, Any]]
    
    include_pii: bool
    compression: Optional[str]
    
    status: str
    total_records: Optional[int]
    exported_records: Optional[int]
    error_message: Optional[str]
    
    file_path: Optional[str]
    file_size_bytes: Optional[int]
    file_checksum: Optional[str]
    download_url: Optional[str]
    url_expires_at: Optional[datetime]
    
    requested_by: str
    requested_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


class AuditStatsResponse(BaseModel):
    """Response model for audit statistics."""
    
    tenant_id: UUID
    total_events: int
    events_by_type: Dict[str, int]
    events_by_severity: Dict[str, int]
    events_by_service: Dict[str, int]
    
    time_range_start: datetime
    time_range_end: datetime
    
    success_rate: float
    avg_processing_time_ms: Optional[float]
    
    retention_summary: Dict[str, Any]
    compliance_summary: Dict[str, Any]


class TenantAuditConfigCreate(BaseModel):
    """Request model for tenant audit configuration."""
    
    model_config = ConfigDict(str_strip_whitespace=True)
    
    tenant_id: UUID = Field(..., description="Tenant identifier")
    
    audit_enabled: bool = Field(True, description="Enable audit logging")
    audit_level: str = Field("standard", pattern="^(minimal|standard|detailed|comprehensive)$")
    auto_redact_pii: bool = Field(True, description="Automatically redact PII")
    
    default_retention_days: int = Field(2555, gt=0, le=36500, description="Default retention (7 years)")
    enable_legal_hold: bool = Field(False, description="Enable legal hold functionality")
    
    siem_endpoints: Optional[List[str]] = Field(None, description="SIEM webhook endpoints")
    real_time_streaming: bool = Field(False, description="Enable real-time audit streaming")
    export_formats: Optional[List[ExportFormatEnum]] = Field(None, description="Supported export formats")
    
    compliance_frameworks: Optional[List[str]] = Field(None, description="Applied compliance frameworks")
    data_classification: Optional[str] = Field(None, pattern="^(public|internal|confidential|restricted)$")
    
    batch_size: int = Field(1000, gt=0, le=10000, description="Batch processing size")
    async_processing: bool = Field(True, description="Enable asynchronous processing")
    compression_enabled: bool = Field(True, description="Enable data compression")


class TenantAuditConfigResponse(BaseModel):
    """Response model for tenant audit configuration."""
    
    model_config = ConfigDict(from_attributes=True)
    
    config_id: UUID
    tenant_id: UUID
    
    audit_enabled: bool
    audit_level: str
    auto_redact_pii: bool
    
    default_retention_days: int
    enable_legal_hold: bool
    
    siem_endpoints: Optional[List[str]]
    real_time_streaming: bool
    export_formats: Optional[List[str]]
    
    compliance_frameworks: Optional[List[str]]
    data_classification: Optional[str]
    
    batch_size: int
    async_processing: bool
    compression_enabled: bool
    
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]


class HealthResponse(BaseModel):
    """Response model for service health check."""
    
    service: str = "anumate-audit-service"
    version: str = "1.0.0"
    status: str = "operational"
    timestamp: datetime
    database_status: str
    features: List[str]
    
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime
    request_id: Optional[str] = None
