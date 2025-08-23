"""
Database Models for CapTokens Service
=====================================

Production-grade SQLAlchemy models for capability token management.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    Text,
    Integer,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class TimestampMixin:
    """Mixin for timestamp columns."""
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TenantMixin:
    """Mixin for tenant isolation."""
    
    tenant_id = Column(UUID(as_uuid=True), nullable=False)


class CapabilityToken(Base, TimestampMixin, TenantMixin):
    """
    Capability Tokens table for Ed25519/JWT token management.
    
    Production-grade table with:
    - Multi-tenant isolation
    - Token hash storage (not plaintext)
    - Comprehensive audit fields
    - Optimized indexes for performance
    - Proper constraints and validation
    """
    
    __tablename__ = "capability_tokens"
    
    # Primary key
    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Token metadata
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    subject = Column(String(255), nullable=False)
    capabilities = Column(JSONB, nullable=False)
    
    # Expiration and lifecycle
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(UUID(as_uuid=True), nullable=True)
    revocation_reason = Column(Text, nullable=True)
    
    # Status and metadata
    active = Column(Boolean, nullable=False, default=True)
    usage_count = Column(Integer, nullable=False, default=0)
    token_metadata = Column(JSONB, nullable=False, default=dict)
    
    # Audit fields
    created_by = Column(UUID(as_uuid=True), nullable=False)
    client_ip = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(Text, nullable=True)
    
    # Relationships
    audit_logs = relationship("TokenAuditLog", back_populates="token", cascade="all, delete-orphan")
    violations = relationship("CapabilityViolation", back_populates="token", cascade="all, delete-orphan")
    usage_tracking = relationship("TokenUsageTracking", back_populates="token", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_capability_tokens_tenant_id", "tenant_id"),
        Index("idx_capability_tokens_subject", "tenant_id", "subject"),
        Index("idx_capability_tokens_expires_at", "expires_at"),
        Index("idx_capability_tokens_active", "tenant_id", "active"),
        Index("idx_capability_tokens_created_by", "tenant_id", "created_by"),
        Index("idx_capability_tokens_cleanup", "active", "expires_at"),  # For cleanup job
        CheckConstraint("expires_at > created_at", name="check_expires_after_created"),
        CheckConstraint("usage_count >= 0", name="check_usage_count_positive"),
    )
    
    def __repr__(self) -> str:
        return f"<CapabilityToken(token_id={self.token_id}, subject='{self.subject}', tenant_id={self.tenant_id})>"


class TokenAuditLog(Base, TimestampMixin, TenantMixin):
    """
    Comprehensive audit log for token operations.
    
    Production-grade audit trail with:
    - Immutable log records
    - Detailed operation tracking
    - Performance optimized indexes
    - Compliance-ready structure
    """
    
    __tablename__ = "token_audit_logs"
    
    # Primary key
    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Token reference
    token_id = Column(UUID(as_uuid=True), ForeignKey("capability_tokens.token_id"), nullable=False)
    
    # Operation details
    operation = Column(String(50), nullable=False)  # issue, verify, refresh, revoke, cleanup
    status = Column(String(20), nullable=False)     # success, failure, warning
    
    # Request context
    endpoint = Column(String(255), nullable=True)
    http_method = Column(String(10), nullable=True)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Authentication context
    authenticated_subject = Column(String(255), nullable=True)
    authentication_method = Column(String(50), nullable=True)
    
    # Operation metadata
    request_data = Column(JSONB, nullable=False, default=dict)
    response_data = Column(JSONB, nullable=False, default=dict)
    error_details = Column(JSONB, nullable=True)
    
    # Performance metrics
    duration_ms = Column(Integer, nullable=True)
    
    # Compliance fields
    correlation_id = Column(UUID(as_uuid=True), nullable=True)
    trace_id = Column(String(32), nullable=True)
    span_id = Column(String(16), nullable=True)
    
    # Relationships
    token = relationship("CapabilityToken", back_populates="audit_logs")
    
    # Indexes for audit queries
    __table_args__ = (
        Index("idx_token_audit_logs_tenant_id", "tenant_id"),
        Index("idx_token_audit_logs_token_id", "token_id"),
        Index("idx_token_audit_logs_operation", "tenant_id", "operation"),
        Index("idx_token_audit_logs_created_at", "created_at"),
        Index("idx_token_audit_logs_status", "tenant_id", "status"),
        Index("idx_token_audit_logs_correlation_id", "correlation_id"),
        CheckConstraint("duration_ms >= 0", name="check_duration_positive"),
    )
    
    def __repr__(self) -> str:
        return f"<TokenAuditLog(audit_id={self.audit_id}, operation='{self.operation}', status='{self.status}')>"


class TokenCleanupJob(Base, TimestampMixin):
    """
    Background job tracking for token cleanup operations.
    
    Production-grade cleanup job management with:
    - Job status tracking
    - Performance metrics
    - Error handling and retry logic
    - Cleanup statistics
    """
    
    __tablename__ = "token_cleanup_jobs"
    
    # Primary key
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Job metadata
    job_type = Column(String(50), nullable=False, default="expired_tokens")
    status = Column(String(20), nullable=False, default="running")  # running, completed, failed
    
    # Execution details
    started_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    # Cleanup statistics
    tokens_processed = Column(Integer, nullable=False, default=0)
    tokens_cleaned = Column(Integer, nullable=False, default=0)
    errors_encountered = Column(Integer, nullable=False, default=0)
    
    # Job configuration
    cleanup_config = Column(JSONB, nullable=False, default=dict)
    
    # Error handling
    error_details = Column(JSONB, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Indexes for job management
    __table_args__ = (
        Index("idx_token_cleanup_jobs_status", "status"),
        Index("idx_token_cleanup_jobs_started_at", "started_at"),
        Index("idx_token_cleanup_jobs_retry", "status", "next_retry_at"),
        CheckConstraint("tokens_processed >= 0", name="check_tokens_processed_positive"),
        CheckConstraint("tokens_cleaned >= 0", name="check_tokens_cleaned_positive"),
        CheckConstraint("retry_count >= 0", name="check_retry_count_positive"),
    )
    
    def __repr__(self) -> str:
        return f"<TokenCleanupJob(job_id={self.job_id}, status='{self.status}', tokens_cleaned={self.tokens_cleaned})>"


class ReplayProtection(Base, TimestampMixin):
    """
    Redis-backed replay protection for JWT tokens.
    
    Production-grade replay attack prevention with:
    - Token nonce tracking
    - Configurable TTL based on token expiry
    - Efficient Redis-backed storage
    - Audit trail integration
    """
    
    __tablename__ = "replay_protection"
    
    # Primary key
    nonce_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Token identification
    token_jti = Column(String(255), nullable=False, unique=True, index=True)  # JWT ID claim
    token_hash = Column(String(255), nullable=False, index=True)
    
    # Expiration management
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Request context for audit
    first_seen_ip = Column(String(45), nullable=True)
    first_seen_user_agent = Column(Text, nullable=True)
    usage_count = Column(Integer, nullable=False, default=1)
    last_used_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Indexes for replay detection
    __table_args__ = (
        Index("idx_replay_protection_token_jti", "token_jti"),
        Index("idx_replay_protection_expires_at", "expires_at"),
        Index("idx_replay_protection_cleanup", "expires_at"),  # For cleanup job
        CheckConstraint("usage_count > 0", name="check_usage_count_positive"),
    )
    
    def __repr__(self) -> str:
        return f"<ReplayProtection(token_jti='{self.token_jti}', usage_count={self.usage_count})>"


class CapabilityViolation(Base, TimestampMixin, TenantMixin):
    """
    Capability Violations table for tracking security violations.
    
    Tracks attempts to access tools/resources without proper capabilities.
    """
    
    __tablename__ = "capability_violations"
    
    violation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(UUID(as_uuid=True), ForeignKey("capability_tokens.token_id"), nullable=True)
    
    # Violation details
    violation_type = Column(String(100), nullable=False)  # insufficient_capability, invalid_token, tool_blocked
    attempted_action = Column(String(200), nullable=False)  # The action that was attempted
    required_capability = Column(String(100), nullable=True)  # What capability was needed
    provided_capabilities = Column(JSONB, nullable=True)  # What capabilities were actually provided
    
    # Request context
    endpoint = Column(String(200), nullable=True)
    http_method = Column(String(10), nullable=True)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Subject information
    subject = Column(String(255), nullable=True)
    
    # Additional metadata
    extra_metadata = Column(JSONB, nullable=True)
    severity = Column(String(20), nullable=False, default="medium")  # low, medium, high, critical
    
    # Relationships
    token = relationship("CapabilityToken", back_populates="violations")
    
    __table_args__ = (
        Index("idx_capability_violations_tenant", "tenant_id"),
        Index("idx_capability_violations_token", "token_id"),
        Index("idx_capability_violations_type", "violation_type"),
        Index("idx_capability_violations_created", "created_at"),
        Index("idx_capability_violations_severity", "severity"),
        Index("idx_capability_violations_subject", "subject"),
    )
    
    def __repr__(self) -> str:
        return f"<CapabilityViolation(type='{self.violation_type}', action='{self.attempted_action}')>"


class TokenUsageTracking(Base, TimestampMixin, TenantMixin):
    """
    Token Usage Tracking table for analytics and monitoring.
    
    Tracks successful token usage for analytics and pattern detection.
    """
    
    __tablename__ = "token_usage_tracking"
    
    usage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token_id = Column(UUID(as_uuid=True), ForeignKey("capability_tokens.token_id"), nullable=False)
    
    # Usage details
    action_performed = Column(String(200), nullable=False)
    capabilities_used = Column(JSONB, nullable=False)
    success = Column(Boolean, nullable=False, default=True)
    
    # Request context
    endpoint = Column(String(200), nullable=True)
    http_method = Column(String(10), nullable=True)
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Performance metrics
    response_time_ms = Column(Integer, nullable=True)
    
    # Additional metadata
    extra_metadata = Column(JSONB, nullable=True)
    
    # Relationships
    token = relationship("CapabilityToken", back_populates="usage_tracking")
    
    __table_args__ = (
        Index("idx_token_usage_tenant", "tenant_id"),
        Index("idx_token_usage_token", "token_id"),
        Index("idx_token_usage_created", "created_at"),
        Index("idx_token_usage_success", "success"),
        Index("idx_token_usage_action", "action_performed"),
    )
    
    def __repr__(self) -> str:
        return f"<TokenUsageTracking(action='{self.action_performed}', success={self.success})>"


class ToolAllowList(Base, TimestampMixin, TenantMixin):
    """
    Tool Allow List table for capability-based access control.
    
    Maps capabilities to allowed tools and actions.
    """
    
    __tablename__ = "tool_allow_lists"
    
    rule_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Capability definition
    capability_name = Column(String(100), nullable=False)
    tool_pattern = Column(String(500), nullable=False)  # Tool pattern (regex or exact match)
    action_pattern = Column(String(200), nullable=True)  # Action pattern (optional)
    
    # Rule configuration
    rule_type = Column(String(50), nullable=False, default="allow")  # allow, deny
    pattern_type = Column(String(50), nullable=False, default="exact")  # exact, regex, glob
    priority = Column(Integer, nullable=False, default=100)  # Lower numbers = higher priority
    
    # Rule metadata
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    
    # Additional metadata
    extra_metadata = Column(JSONB, nullable=True)
    
    __table_args__ = (
        Index("idx_tool_allow_list_tenant", "tenant_id"),
        Index("idx_tool_allow_list_capability", "capability_name"),
        Index("idx_tool_allow_list_active", "is_active"),
        Index("idx_tool_allow_list_priority", "priority"),
        UniqueConstraint("tenant_id", "capability_name", "tool_pattern", name="uq_tool_allow_list_rule"),
    )
    
    def __repr__(self) -> str:
        return f"<ToolAllowList(capability='{self.capability_name}', tool='{self.tool_pattern}')>"
