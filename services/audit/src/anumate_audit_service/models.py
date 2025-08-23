"""
Database Models for Audit Service
=================================

A.27 Implementation: SQLAlchemy models for comprehensive audit logging.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, DateTime, Text, JSON, Boolean, Integer, 
    Index, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class EventType(str, Enum):
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


class EventSeverity(str, Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RetentionPolicyStatus(str, Enum):
    """Retention policy status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class AuditEvent(Base):
    """
    Central audit event table capturing all platform operations.
    
    Designed for high-performance insertion and querying with proper indexing.
    Supports multi-tenant isolation and comprehensive audit trails.
    """
    __tablename__ = "audit_events"
    
    # Primary identification
    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)
    parent_event_id = Column(UUID(as_uuid=True), ForeignKey('audit_events.event_id'), nullable=True)
    
    # Event classification
    event_type = Column(String(50), nullable=False, index=True)
    event_category = Column(String(100), nullable=False)
    event_action = Column(String(255), nullable=False)
    event_severity = Column(String(20), nullable=False, default=EventSeverity.INFO)
    
    # Source information
    service_name = Column(String(100), nullable=False, index=True)
    service_version = Column(String(50), nullable=True)
    endpoint = Column(String(500), nullable=True)
    method = Column(String(10), nullable=True)
    
    # Actor information
    user_id = Column(String(255), nullable=True, index=True)
    user_type = Column(String(50), nullable=True)  # human, service, system
    session_id = Column(String(255), nullable=True, index=True)
    
    # Security context
    client_ip = Column(String(45), nullable=True, index=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    authentication_method = Column(String(100), nullable=True)
    authorization_context = Column(JSON, nullable=True)
    
    # Event timing
    event_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    processing_time_ms = Column(Integer, nullable=True)
    
    # Request/Response data
    request_id = Column(String(255), nullable=True, index=True)
    request_data = Column(JSON, nullable=True)  # Redacted sensitive data
    response_code = Column(Integer, nullable=True)
    response_data = Column(JSON, nullable=True)
    
    # Event details
    event_description = Column(Text, nullable=False)
    event_data = Column(JSON, nullable=True)  # Additional structured data
    tags = Column(JSON, nullable=True)  # Search/categorization tags
    
    # Result information
    success = Column(Boolean, nullable=False)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Compliance and retention
    compliance_tags = Column(JSON, nullable=True)  # SOX, HIPAA, GDPR, etc.
    retention_until = Column(DateTime, nullable=True, index=True)
    pii_redacted = Column(Boolean, nullable=False, default=False)
    
    # System metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_system = Column(String(100), nullable=True)
    environment = Column(String(50), nullable=True)  # prod, staging, dev
    
    # Relationships
    child_events = relationship("AuditEvent", backref="parent_event", remote_side=[event_id])
    
    __table_args__ = (
        # Composite indexes for common queries
        Index('idx_tenant_timestamp', 'tenant_id', 'event_timestamp'),
        Index('idx_tenant_type_timestamp', 'tenant_id', 'event_type', 'event_timestamp'),
        Index('idx_service_timestamp', 'service_name', 'event_timestamp'),
        Index('idx_user_timestamp', 'user_id', 'event_timestamp'),
        Index('idx_correlation_timestamp', 'correlation_id', 'event_timestamp'),
        Index('idx_retention_cleanup', 'retention_until', 'tenant_id'),
        Index('idx_compliance_search', 'tenant_id', 'compliance_tags'),
        
        # Performance constraints
        CheckConstraint('event_timestamp <= NOW()', name='event_timestamp_not_future'),
        CheckConstraint('processing_time_ms >= 0', name='processing_time_positive'),
    )


class RetentionPolicy(Base):
    """
    Per-tenant audit event retention policies.
    
    Supports complex retention rules based on event types, compliance requirements,
    and regulatory frameworks.
    """
    __tablename__ = "retention_policies"
    
    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Policy identification
    policy_name = Column(String(200), nullable=False)
    policy_description = Column(Text, nullable=True)
    policy_version = Column(String(50), nullable=False, default="1.0")
    
    # Retention rules
    event_types = Column(JSON, nullable=False)  # List of event types this applies to
    retention_days = Column(Integer, nullable=False)
    archive_after_days = Column(Integer, nullable=True)  # Move to cold storage
    
    # Compliance requirements
    compliance_framework = Column(String(100), nullable=True)  # SOX, HIPAA, GDPR, etc.
    regulatory_requirements = Column(JSON, nullable=True)
    legal_hold_exempt = Column(Boolean, nullable=False, default=False)
    
    # Policy conditions
    conditions = Column(JSON, nullable=True)  # Additional matching conditions
    priority = Column(Integer, nullable=False, default=100)  # Lower = higher priority
    
    # Policy status
    status = Column(String(20), nullable=False, default=RetentionPolicyStatus.ACTIVE)
    effective_from = Column(DateTime, nullable=False, default=datetime.utcnow)
    effective_until = Column(DateTime, nullable=True)
    
    # System metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(String(255), nullable=True)
    
    __table_args__ = (
        Index('idx_tenant_retention', 'tenant_id', 'status', 'effective_from'),
        Index('idx_policy_priority', 'tenant_id', 'priority'),
        UniqueConstraint('tenant_id', 'policy_name', name='unique_tenant_policy_name'),
    )


class AuditExport(Base):
    """
    SIEM export job tracking and metadata.
    
    Tracks export requests for audit trail and provides download links.
    """
    __tablename__ = "audit_exports"
    
    export_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Export request details
    export_format = Column(String(20), nullable=False)  # json, csv, syslog, cef
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    event_types = Column(JSON, nullable=True)  # Filter by event types
    
    # Export filters
    filters = Column(JSON, nullable=True)  # Additional export filters
    include_pii = Column(Boolean, nullable=False, default=False)
    compression = Column(String(20), nullable=True)  # gzip, zip
    
    # Export status
    status = Column(String(20), nullable=False, default="pending")  # pending, processing, completed, failed
    total_records = Column(Integer, nullable=True)
    exported_records = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # File details
    file_path = Column(String(1000), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    file_checksum = Column(String(255), nullable=True)
    download_url = Column(String(1000), nullable=True)
    url_expires_at = Column(DateTime, nullable=True)
    
    # System metadata
    requested_by = Column(String(255), nullable=False)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_tenant_export_status', 'tenant_id', 'status'),
        Index('idx_export_cleanup', 'url_expires_at', 'status'),
    )


class AuditSearchQuery(Base):
    """
    Audit search query history for performance optimization and compliance.
    
    Tracks searches performed on audit data for security monitoring.
    """
    __tablename__ = "audit_search_queries"
    
    query_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Query details
    query_text = Column(Text, nullable=True)  # Free text search
    filters = Column(JSON, nullable=False)  # Structured query filters
    sort_order = Column(JSON, nullable=True)
    limit_count = Column(Integer, nullable=True)
    
    # Query performance
    execution_time_ms = Column(Integer, nullable=True)
    result_count = Column(Integer, nullable=True)
    cache_hit = Column(Boolean, nullable=False, default=False)
    
    # Query context
    user_id = Column(String(255), nullable=False)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(255), nullable=True)
    
    # System metadata
    executed_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index('idx_tenant_query_time', 'tenant_id', 'executed_at'),
        Index('idx_user_query_history', 'user_id', 'executed_at'),
    )


class TenantAuditConfig(Base):
    """
    Per-tenant audit configuration settings.
    
    Customizes audit behavior per tenant including PII handling, retention defaults,
    and integration settings.
    """
    __tablename__ = "tenant_audit_configs"
    
    config_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    
    # Audit behavior settings
    audit_enabled = Column(Boolean, nullable=False, default=True)
    audit_level = Column(String(20), nullable=False, default="standard")  # minimal, standard, detailed, comprehensive
    auto_redact_pii = Column(Boolean, nullable=False, default=True)
    
    # Default retention settings
    default_retention_days = Column(Integer, nullable=False, default=2555)  # 7 years
    enable_legal_hold = Column(Boolean, nullable=False, default=False)
    
    # SIEM integration
    siem_endpoints = Column(JSON, nullable=True)  # SIEM webhook endpoints
    real_time_streaming = Column(Boolean, nullable=False, default=False)
    export_formats = Column(JSON, nullable=True)  # Supported export formats
    
    # Compliance settings
    compliance_frameworks = Column(JSON, nullable=True)  # Applied compliance frameworks
    data_classification = Column(String(50), nullable=True)  # public, internal, confidential, restricted
    
    # Performance settings
    batch_size = Column(Integer, nullable=False, default=1000)
    async_processing = Column(Boolean, nullable=False, default=True)
    compression_enabled = Column(Boolean, nullable=False, default=True)
    
    # System metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_by = Column(String(255), nullable=True)
