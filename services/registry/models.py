"""
Database Models for Capsule Registry

A.4–A.6 Implementation: SQLAlchemy models with tenant isolation and audit trails.
Supports both SQLite (dev/testing) and PostgreSQL (production) with RLS templates.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum

from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Boolean, ForeignKey, 
    UniqueConstraint, Index, CheckConstraint, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from pydantic import BaseModel, Field, validator
import uuid as uuid_lib


Base = declarative_base()


class CapsuleStatus(str, Enum):
    """Capsule lifecycle status."""
    DRAFT = "draft"
    ACTIVE = "active" 
    DELETED = "deleted"


class CapsuleVisibility(str, Enum):
    """Capsule access visibility."""
    PRIVATE = "private"
    INTERNAL = "internal"
    PUBLIC = "public"


class CapsuleRole(str, Enum):
    """RBAC roles for capsule access."""
    VIEWER = "viewer"      # Read-only access
    EDITOR = "editor"      # Create, version, lint
    ADMIN = "admin"        # Delete, hard delete


# Database Models

class Capsule(Base):
    """Core capsule metadata table."""
    __tablename__ = "capsules"
    
    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    name = Column(String(255), nullable=False, index=True)
    owner = Column(String(255), nullable=False, index=True)  # OIDC subject
    
    # Status and visibility
    status = Column(String(20), nullable=False, default=CapsuleStatus.DRAFT.value, index=True)
    visibility = Column(String(20), nullable=False, default=CapsuleVisibility.PRIVATE.value)
    
    # Metadata
    description = Column(Text)
    tags = Column(JSON)  # List of string tags
    
    # Versioning
    latest_version = Column(Integer, default=0, nullable=False)
    etag = Column(String(64), nullable=False)  # For concurrency control
    
    # Multi-tenancy (required for all records)
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
    
    # Relationships
    versions = relationship("CapsuleVersion", back_populates="capsule", cascade="all, delete-orphan")
    audit_logs = relationship("CapsuleAuditLog", back_populates="capsule", cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_capsule_tenant_name"),
        Index("ix_capsule_tenant_status", "tenant_id", "status"),
        Index("ix_capsule_tenant_updated", "tenant_id", "updated_at"),
        CheckConstraint(
            "status IN ('draft', 'active', 'deleted')", 
            name="ck_capsule_status"
        ),
        CheckConstraint(
            "visibility IN ('private', 'internal', 'public')",
            name="ck_capsule_visibility"
        ),
        CheckConstraint("latest_version >= 0", name="ck_capsule_version_positive"),
    )
    
    @validates("name")
    def validate_name(self, key, name):
        """Validate capsule name format."""
        if not name or len(name) > 255:
            raise ValueError("Capsule name must be 1-255 characters")
        if not name.replace("-", "").replace("_", "").replace(".", "").isalnum():
            raise ValueError("Capsule name must be alphanumeric with -, _, . allowed")
        return name


class CapsuleVersion(Base):
    """Immutable capsule version records."""
    __tablename__ = "capsule_versions"
    
    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    capsule_id = Column(UUID(as_uuid=True), ForeignKey("capsules.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    
    # Content integrity
    content_hash = Column(String(64), nullable=False, index=True)  # SHA256 hex
    signature = Column(Text, nullable=False)  # Ed25519 signature (hex)
    pubkey_id = Column(String(255), nullable=False)  # Public key identifier
    
    # Storage reference
    uri = Column(String(512), nullable=False)  # WORM storage URI
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Audit metadata
    created_by = Column(String(255), nullable=False)  # OIDC subject
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Relationships
    capsule = relationship("Capsule", back_populates="versions")
    blob = relationship("CapsuleBlob", foreign_keys="CapsuleVersion.content_hash", 
                       primaryjoin="CapsuleVersion.content_hash == CapsuleBlob.content_hash")
    
    # Constraints
    __table_args__ = (
        UniqueConstraint("capsule_id", "version", name="uq_version_capsule_version"),
        UniqueConstraint("tenant_id", "content_hash", name="uq_version_tenant_hash"),
        Index("ix_version_tenant_capsule", "tenant_id", "capsule_id"),
        Index("ix_version_content_hash", "content_hash"),
        CheckConstraint("version > 0", name="ck_version_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="ck_content_hash_length"),
    )


class CapsuleBlob(Base):
    """WORM storage for capsule YAML content."""
    __tablename__ = "capsule_blobs"
    
    # Content identification (using hash as natural key)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    content_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # Content data
    yaml_text = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    
    # Multi-tenancy 
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Audit
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Constraints
    __table_args__ = (
        Index("ix_blob_tenant_hash", "tenant_id", "content_hash"),
        CheckConstraint("size_bytes > 0", name="ck_blob_size_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="ck_blob_hash_length"),
    )


class CapsuleAuditLog(Base):
    """Comprehensive audit trail for all capsule operations."""
    __tablename__ = "capsule_audit_logs"
    
    # Primary identification  
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_lib.uuid4)
    capsule_id = Column(UUID(as_uuid=True), ForeignKey("capsules.id", ondelete="CASCADE"))
    version = Column(Integer)  # Null for capsule-level operations
    
    # Operation details
    actor = Column(String(255), nullable=False)  # OIDC subject
    action = Column(String(50), nullable=False, index=True)  # create, version, delete, etc.
    
    # Context and details
    details = Column(JSONB if "postgresql" in str(Base.metadata.bind) else JSON)  # Structured context
    
    # Multi-tenancy
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Timing
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    
    # Relationships
    capsule = relationship("Capsule", back_populates="audit_logs")
    
    # Constraints
    __table_args__ = (
        Index("ix_audit_tenant_capsule", "tenant_id", "capsule_id"),
        Index("ix_audit_tenant_timestamp", "tenant_id", "timestamp"),
        Index("ix_audit_action_timestamp", "action", "timestamp"),
        CheckConstraint("version IS NULL OR version > 0", name="ck_audit_version_positive"),
    )


# Pydantic Models (API DTOs)

class CapsuleMetadataResponse(BaseModel):
    """Capsule metadata API response."""
    id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    owner: str
    status: CapsuleStatus
    visibility: CapsuleVisibility
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    latest_version: int = Field(..., ge=0)
    etag: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CapsuleCreateRequest(BaseModel):
    """Request to create new capsule."""
    name: str = Field(..., min_length=1, max_length=255, regex=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$")
    description: Optional[str] = Field(None, max_length=2048)
    tags: Optional[List[str]] = Field(None, max_items=20)
    visibility: CapsuleVisibility = CapsuleVisibility.PRIVATE
    
    @validator("tags")
    def validate_tags(cls, v):
        if v:
            for tag in v:
                if not tag or not tag.replace("-", "").replace("_", "").replace(".", "").isalnum():
                    raise ValueError("Tags must be alphanumeric with -, _, . allowed")
        return v


class CapsuleUpdateRequest(BaseModel):
    """Request to update capsule status."""
    status: CapsuleStatus


class CapsuleVersionResponse(BaseModel):
    """Capsule version API response."""
    id: uuid.UUID
    capsule_id: uuid.UUID  
    version: int = Field(..., gt=0)
    content_hash: str = Field(..., regex=r"^[a-f0-9]{64}$")
    signature: str
    pubkey_id: str
    uri: str
    created_by: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class CapsuleVersionRequest(BaseModel):
    """Request to create new capsule version."""
    yaml_content: str = Field(..., min_length=1)
    lint_only: bool = Field(default=False)
    
    @validator("yaml_content")
    def validate_yaml_length(cls, v):
        # Approximate size check (actual will be validated in business logic)
        if len(v.encode("utf-8")) > 50 * 1024 * 1024:  # 50MB limit
            raise ValueError("YAML content exceeds maximum size")
        return v


class ValidationResult(BaseModel):
    """Capsule validation result."""
    valid: bool
    content_hash: str = Field(..., regex=r"^[a-f0-9]{64}$")
    errors: Optional[List[Dict[str, str]]] = None
    warnings: Optional[List[str]] = None


class CapsuleListResponse(BaseModel):
    """Paginated capsule list response."""
    capsules: List[CapsuleMetadataResponse]
    pagination: Dict[str, int] = Field(
        ..., 
        description="Pagination info: page, page_size, total_count, total_pages"
    )


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = Field(..., regex="^(healthy|unhealthy)$")
    timestamp: datetime
    checks: Optional[Dict[str, str]] = None


class CapsuleVersionContentResponse(BaseModel):
    """Version content response with YAML."""
    version: CapsuleVersionResponse
    yaml_content: str  # Potentially redacted for security
