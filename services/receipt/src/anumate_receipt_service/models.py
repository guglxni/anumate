"""
Database Models for Receipt Service
===================================

Production-grade SQLAlchemy models for tamper-evident receipts and audit logging.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

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
    """Mixin for automatic timestamp tracking."""
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class TenantMixin:
    """Mixin for multi-tenant isolation."""
    tenant_id = Column(UUID(as_uuid=True), nullable=False)


class Receipt(Base, TimestampMixin, TenantMixin):
    """
    Receipts table for tamper-evident receipt storage.
    
    Stores immutable receipts with cryptographic hashing and digital signatures
    for integrity verification and compliance.
    """
    
    __tablename__ = "receipts"
    
    receipt_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Receipt content and metadata
    receipt_type = Column(String(100), nullable=False)  # execution, approval, policy_evaluation, etc.
    subject = Column(String(255), nullable=False)  # What this receipt is for
    reference_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to related entity
    
    # Receipt data (immutable once created)
    receipt_data = Column(JSONB, nullable=False)  # The actual receipt content
    
    # Cryptographic integrity
    content_hash = Column(String(64), nullable=False)  # SHA-256 hash of receipt_data
    signature = Column(Text, nullable=False)  # Ed25519 signature for integrity
    signing_key_id = Column(String(100), nullable=False)  # Key identifier used for signing
    
    # WORM storage tracking
    worm_storage_path = Column(String(500), nullable=True)  # Path in WORM storage
    worm_written_at = Column(DateTime(timezone=True), nullable=True)  # When written to WORM
    worm_verified_at = Column(DateTime(timezone=True), nullable=True)  # Last verification
    
    # Audit and compliance
    retention_until = Column(DateTime(timezone=True), nullable=True)  # Retention policy
    compliance_tags = Column(JSONB, nullable=True)  # Compliance metadata
    
    # Status tracking
    is_verified = Column(Boolean, nullable=False, default=True)
    verification_failures = Column(Integer, nullable=False, default=0)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    audit_entries = relationship("ReceiptAuditLog", back_populates="receipt", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_receipts_tenant", "tenant_id"),
        Index("idx_receipts_type", "receipt_type"),
        Index("idx_receipts_subject", "subject"),
        Index("idx_receipts_reference", "reference_id"),
        Index("idx_receipts_hash", "content_hash"),
        Index("idx_receipts_created", "created_at"),
        Index("idx_receipts_retention", "retention_until"),
        Index("idx_receipts_verification", "is_verified", "last_verified_at"),
        UniqueConstraint("tenant_id", "content_hash", name="uq_receipts_tenant_hash"),
        CheckConstraint("verification_failures >= 0", name="ck_receipts_verification_failures"),
        CheckConstraint("LENGTH(content_hash) = 64", name="ck_receipts_content_hash_length"),
    )
    
    def __repr__(self) -> str:
        return f"<Receipt(type='{self.receipt_type}', subject='{self.subject}', hash='{self.content_hash[:8]}...')>"


class ReceiptAuditLog(Base, TimestampMixin, TenantMixin):
    """
    Receipt Audit Log table for comprehensive receipt access tracking.
    
    Tracks all access, verification, and modification attempts for receipts
    to provide comprehensive audit trails for compliance.
    """
    
    __tablename__ = "receipt_audit_logs"
    
    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("receipts.receipt_id"), nullable=False)
    
    # Audit event details
    event_type = Column(String(50), nullable=False)  # created, accessed, verified, exported, etc.
    event_source = Column(String(100), nullable=False)  # service that generated the event
    user_id = Column(String(255), nullable=True)  # User identifier if applicable
    
    # Request context
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    request_id = Column(String(100), nullable=True)  # Correlation ID
    
    # Event-specific data
    event_data = Column(JSONB, nullable=True)  # Additional event metadata
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Performance metrics
    processing_time_ms = Column(Integer, nullable=True)
    
    # Relationships
    receipt = relationship("Receipt", back_populates="audit_entries")
    
    __table_args__ = (
        Index("idx_receipt_audit_tenant", "tenant_id"),
        Index("idx_receipt_audit_receipt", "receipt_id"),
        Index("idx_receipt_audit_event", "event_type"),
        Index("idx_receipt_audit_created", "created_at"),
        Index("idx_receipt_audit_user", "user_id"),
        Index("idx_receipt_audit_source", "event_source"),
        Index("idx_receipt_audit_success", "success"),
    )
    
    def __repr__(self) -> str:
        return f"<ReceiptAuditLog(event='{self.event_type}', receipt_id='{self.receipt_id}')>"


class RetentionPolicy(Base, TimestampMixin, TenantMixin):
    """
    Retention Policy table for managing per-tenant receipt retention rules.
    
    Defines how long different types of receipts should be retained
    based on tenant requirements and compliance needs.
    """
    
    __tablename__ = "retention_policies"
    
    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Policy definition
    policy_name = Column(String(100), nullable=False)
    receipt_types = Column(JSONB, nullable=False)  # List of receipt types this applies to
    retention_days = Column(Integer, nullable=False)  # How long to retain in days
    
    # Policy configuration
    is_active = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)  # Lower = higher priority
    description = Column(Text, nullable=True)
    
    # Compliance metadata
    compliance_requirements = Column(JSONB, nullable=True)  # Regulatory requirements
    auto_delete = Column(Boolean, nullable=False, default=False)  # Auto-delete after retention
    
    __table_args__ = (
        Index("idx_retention_policies_tenant", "tenant_id"),
        Index("idx_retention_policies_active", "is_active"),
        Index("idx_retention_policies_priority", "priority"),
        UniqueConstraint("tenant_id", "policy_name", name="uq_retention_policies_tenant_name"),
        CheckConstraint("retention_days > 0", name="ck_retention_policies_days"),
        CheckConstraint("priority > 0", name="ck_retention_policies_priority"),
    )
    
    def __repr__(self) -> str:
        return f"<RetentionPolicy(name='{self.policy_name}', days={self.retention_days})>"


class WormStorageRecord(Base, TimestampMixin, TenantMixin):
    """
    WORM Storage Record table for tracking Write-Once-Read-Many storage operations.
    
    Tracks receipts written to immutable storage for compliance and audit purposes.
    """
    
    __tablename__ = "worm_storage_records"
    
    worm_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    receipt_id = Column(UUID(as_uuid=True), ForeignKey("receipts.receipt_id"), nullable=False)
    
    # Storage details
    storage_provider = Column(String(50), nullable=False)  # s3_glacier, azure_archive, etc.
    storage_path = Column(String(500), nullable=False)  # Full path in WORM storage
    storage_checksum = Column(String(64), nullable=False)  # Checksum in storage
    
    # Write operation
    written_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    written_by = Column(String(255), nullable=True)  # Service/user that wrote
    write_transaction_id = Column(String(100), nullable=True)  # Storage transaction ID
    
    # Verification tracking
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_count = Column(Integer, nullable=False, default=0)
    verification_failures = Column(Integer, nullable=False, default=0)
    
    # Status
    is_accessible = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    receipt = relationship("Receipt")
    
    __table_args__ = (
        Index("idx_worm_storage_tenant", "tenant_id"),
        Index("idx_worm_storage_receipt", "receipt_id"),
        Index("idx_worm_storage_provider", "storage_provider"),
        Index("idx_worm_storage_written", "written_at"),
        Index("idx_worm_storage_verified", "last_verified_at"),
        Index("idx_worm_storage_accessible", "is_accessible"),
        UniqueConstraint("storage_provider", "storage_path", name="uq_worm_storage_provider_path"),
        CheckConstraint("verification_count >= 0", name="ck_worm_storage_verification_count"),
        CheckConstraint("verification_failures >= 0", name="ck_worm_storage_verification_failures"),
    )
    
    def __repr__(self) -> str:
        return f"<WormStorageRecord(provider='{self.storage_provider}', path='{self.storage_path}')>"
