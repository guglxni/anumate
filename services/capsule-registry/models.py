"""SQLAlchemy models for Capsule Registry."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    Column, String, Text, Integer, DateTime, Boolean, ForeignKey,
    Index, CheckConstraint, func, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression

Base = declarative_base()


class CapsuleStatus(str, Enum):
    """Capsule lifecycle status."""
    ACTIVE = "active"
    DELETED = "deleted"


class CapsuleVisibility(str, Enum):
    """Capsule visibility scope."""
    PRIVATE = "private"
    ORG = "org"


class AuditAction(str, Enum):
    """Audit action types."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    PUBLISH_VERSION = "publish_version"


class Capsule(Base):
    """Main Capsule entity with metadata and versioning."""
    
    __tablename__ = "capsules"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Core metadata
    name = Column(String(255), nullable=False)
    description = Column(Text)
    tags = Column(JSONB, default=list)  # Array of strings
    owner = Column(String(255), nullable=False)
    visibility = Column(String(20), nullable=False, default=CapsuleVisibility.PRIVATE.value)
    status = Column(String(20), nullable=False, default=CapsuleStatus.ACTIVE.value)
    
    # Versioning
    latest_version = Column(Integer, nullable=False, default=0)
    
    # Concurrency control
    etag = Column(String(64), nullable=False, server_default=text("gen_random_uuid()::text"))
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    versions = relationship("CapsuleVersion", back_populates="capsule", cascade="all, delete-orphan")
    audit_logs = relationship("CapsuleAudit", back_populates="capsule", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        Index("ix_capsules_tenant_name", "tenant_id", "name", unique=True),
        Index("ix_capsules_tenant_status", "tenant_id", "status"),
        Index("ix_capsules_tenant_updated", "tenant_id", "updated_at"),
        CheckConstraint("visibility IN ('private', 'org')", name="ck_capsules_visibility"),
        CheckConstraint("status IN ('active', 'deleted')", name="ck_capsules_status"),
        CheckConstraint("latest_version >= 0", name="ck_capsules_latest_version"),
    )
    
    def __repr__(self):
        return f"<Capsule(id={self.id}, name='{self.name}', version={self.latest_version})>"


class CapsuleVersion(Base):
    """Individual version of a Capsule with content hash and signature."""
    
    __tablename__ = "capsule_versions"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Parent relationship
    capsule_id = Column(UUID(as_uuid=True), ForeignKey("capsules.id"), nullable=False)
    
    # Version metadata
    version = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hex
    signature = Column(Text, nullable=False)  # Ed25519 signature (base64)
    pubkey_id = Column(String(100), nullable=False)
    uri = Column(Text, nullable=False)  # WORM storage URI
    
    # Audit info
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    capsule = relationship("Capsule", back_populates="versions")
    
    # Constraints
    __table_args__ = (
        Index("ix_capsule_versions_tenant_id", "tenant_id"),
        Index("ix_capsule_versions_capsule_version", "capsule_id", "version", unique=True),
        Index("ix_capsule_versions_content_hash", "tenant_id", "content_hash"),
        CheckConstraint("version > 0", name="ck_capsule_versions_version"),
    )
    
    def __repr__(self):
        return f"<CapsuleVersion(capsule_id={self.capsule_id}, version={self.version})>"


class CapsuleBlob(Base):
    """YAML content storage with deduplication by content hash."""
    
    __tablename__ = "capsule_blobs"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Content
    content_hash = Column(String(64), nullable=False)  # SHA-256 hex
    yaml_text = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Constraints
    __table_args__ = (
        Index("ix_capsule_blobs_tenant_hash", "tenant_id", "content_hash", unique=True),
        CheckConstraint("size_bytes > 0", name="ck_capsule_blobs_size"),
    )
    
    def __repr__(self):
        return f"<CapsuleBlob(content_hash={self.content_hash[:12]}..., size={self.size_bytes})>"


class CapsuleAudit(Base):
    """Audit log for Capsule operations."""
    
    __tablename__ = "capsule_audit"
    
    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Subject
    capsule_id = Column(UUID(as_uuid=True), ForeignKey("capsules.id"), nullable=False)
    version = Column(Integer)  # Null for capsule-level operations
    
    # Action
    actor = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False)
    details = Column(JSONB)  # Additional action-specific data
    
    # Timestamps
    occurred_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Tracing
    trace_id = Column(String(100))
    
    # Relationships
    capsule = relationship("Capsule", back_populates="audit_logs")
    
    # Constraints
    __table_args__ = (
        Index("ix_capsule_audit_tenant_capsule", "tenant_id", "capsule_id"),
        Index("ix_capsule_audit_tenant_occurred", "tenant_id", "occurred_at"),
        Index("ix_capsule_audit_trace_id", "trace_id"),
        CheckConstraint("action IN ('create', 'update', 'delete', 'restore', 'publish_version')", 
                       name="ck_capsule_audit_action"),
    )
    
    def __repr__(self):
        return f"<CapsuleAudit(capsule_id={self.capsule_id}, action='{self.action}')>"


# For SQLite compatibility in tests
def create_enums(engine):
    """Create enum types for PostgreSQL (no-op for SQLite)."""
    if engine.dialect.name == 'postgresql':
        from sqlalchemy import text
        
        # Create custom enum types
        enums_sql = [
            "CREATE TYPE capsule_status AS ENUM ('active', 'deleted');",
            "CREATE TYPE capsule_visibility AS ENUM ('private', 'org');",
            "CREATE TYPE audit_action AS ENUM ('create', 'update', 'delete', 'restore', 'publish_version');"
        ]
        
        with engine.connect() as conn:
            for sql in enums_sql:
                try:
                    conn.execute(text(sql))
                except Exception:
                    # Type might already exist
                    pass
