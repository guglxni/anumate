"""Database models for the Approvals service."""

from __future__ import annotations

import enum
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Column, DateTime, Enum, String, Text, UUID as SQLAlchemyUUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class ApprovalStatus(str, enum.Enum):
    """Approval status enumeration."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ApprovalPriority(str, enum.Enum):
    """Approval priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(str, enum.Enum):
    """Notification channel types."""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


# Database Models
class Approval(Base):
    """Approval database model."""
    __tablename__ = "approvals"
    
    # Primary fields
    approval_id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    
    # Clarification context
    clarification_id = Column(String(255), nullable=False, index=True)
    run_id = Column(String(255), nullable=False, index=True)
    
    # Approval details
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Enum(ApprovalPriority), nullable=False, default=ApprovalPriority.MEDIUM)
    
    # Approval requirements
    required_approvers = Column(JSONB, nullable=False, default=list)
    approval_rules = Column(JSONB, nullable=False, default=list)
    requires_all_approvers = Column(Boolean, default=False)
    
    # Status and timing
    status = Column(Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Request context
    plan_context = Column(JSONB, nullable=False, default=dict)
    request_metadata = Column(JSONB, nullable=False, default=dict)
    
    # Approval/rejection details
    approved_by = Column(JSONB, nullable=False, default=list)  # List of approver IDs
    rejected_by = Column(String(255), nullable=True)  # Single rejector ID
    approval_reason = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ApprovalNotification(Base):
    """Approval notification tracking."""
    __tablename__ = "approval_notifications"
    
    notification_id = Column(SQLAlchemyUUID(as_uuid=True), primary_key=True, default=uuid4)
    approval_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    tenant_id = Column(SQLAlchemyUUID(as_uuid=True), nullable=False, index=True)
    
    # Notification details
    channel = Column(Enum(NotificationChannel), nullable=False)
    recipient = Column(String(255), nullable=False)  # email/slack ID/webhook URL
    notification_type = Column(String(100), nullable=False)  # requested, reminder, responded
    
    # Status
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    
    # Content
    subject = Column(String(500), nullable=True)
    message_content = Column(Text, nullable=True)
    notification_data = Column(JSONB, nullable=False, default=dict)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# Pydantic Models
class ApprovalBase(BaseModel):
    """Base approval model."""
    title: str = Field(..., description="Approval request title")
    description: Optional[str] = Field(None, description="Detailed description")
    priority: ApprovalPriority = Field(ApprovalPriority.MEDIUM, description="Priority level")
    required_approvers: List[str] = Field(..., description="Required approver IDs")
    approval_rules: List[str] = Field(default_factory=list, description="Approval rule references")
    requires_all_approvers: bool = Field(False, description="Whether all approvers must approve")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    plan_context: Dict[str, Any] = Field(default_factory=dict, description="Plan execution context")
    request_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ApprovalCreate(ApprovalBase):
    """Create approval request."""
    clarification_id: str = Field(..., description="Associated clarification ID")
    run_id: str = Field(..., description="Associated run ID")


class ApprovalUpdate(BaseModel):
    """Update approval request."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[ApprovalPriority] = None
    required_approvers: Optional[List[str]] = None
    expires_at: Optional[datetime] = None


class ApprovalResponse(BaseModel):
    """Approval response model."""
    approved: bool = Field(..., description="Whether approved or rejected")
    approver_id: str = Field(..., description="ID of the approver")
    reason: Optional[str] = Field(None, description="Reason for approval/rejection")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")


class ApprovalDetail(ApprovalBase):
    """Complete approval details."""
    approval_id: UUID = Field(..., description="Approval ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    clarification_id: str = Field(..., description="Associated clarification ID")
    run_id: str = Field(..., description="Associated run ID")
    
    # Status
    status: ApprovalStatus = Field(..., description="Current status")
    requested_at: datetime = Field(..., description="Request timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    
    # Response details
    approved_by: List[str] = Field(default_factory=list, description="Approver IDs")
    rejected_by: Optional[str] = Field(None, description="Rejector ID")
    approval_reason: Optional[str] = Field(None, description="Approval reason")
    rejection_reason: Optional[str] = Field(None, description="Rejection reason")
    
    # Audit
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    class Config:
        from_attributes = True


class ApprovalSummary(BaseModel):
    """Approval summary for listing."""
    approval_id: UUID = Field(..., description="Approval ID")
    title: str = Field(..., description="Approval title")
    priority: ApprovalPriority = Field(..., description="Priority level")
    status: ApprovalStatus = Field(..., description="Current status")
    required_approvers: List[str] = Field(..., description="Required approver IDs")
    approved_by: List[str] = Field(default_factory=list, description="Approver IDs")
    requested_at: datetime = Field(..., description="Request timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    
    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    """Create notification request."""
    channel: NotificationChannel = Field(..., description="Notification channel")
    recipient: str = Field(..., description="Notification recipient")
    notification_type: str = Field(..., description="Type of notification")
    subject: Optional[str] = Field(None, description="Notification subject")
    message_content: Optional[str] = Field(None, description="Message content")
    notification_data: Dict[str, Any] = Field(default_factory=dict, description="Additional data")


class NotificationDetail(BaseModel):
    """Notification details."""
    notification_id: UUID = Field(..., description="Notification ID")
    approval_id: UUID = Field(..., description="Associated approval ID")
    channel: NotificationChannel = Field(..., description="Notification channel")
    recipient: str = Field(..., description="Notification recipient")
    notification_type: str = Field(..., description="Type of notification")
    
    # Status
    sent_at: Optional[datetime] = Field(None, description="Send timestamp")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    failed_at: Optional[datetime] = Field(None, description="Failure timestamp")
    failure_reason: Optional[str] = Field(None, description="Failure reason")
    
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        from_attributes = True


# Event Models
class ApprovalRequestedEvent(BaseModel):
    """Approval requested event."""
    approval_id: UUID = Field(..., description="Approval ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    clarification_id: str = Field(..., description="Clarification ID")
    run_id: str = Field(..., description="Run ID")
    title: str = Field(..., description="Approval title")
    priority: ApprovalPriority = Field(..., description="Priority level")
    required_approvers: List[str] = Field(..., description="Required approvers")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    requested_at: datetime = Field(..., description="Request timestamp")


class ApprovalGrantedEvent(BaseModel):
    """Approval granted event."""
    approval_id: UUID = Field(..., description="Approval ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    clarification_id: str = Field(..., description="Clarification ID")
    run_id: str = Field(..., description="Run ID")
    approved_by: List[str] = Field(..., description="Approver IDs")
    approval_reason: Optional[str] = Field(None, description="Approval reason")
    granted_at: datetime = Field(..., description="Grant timestamp")


class ApprovalRejectedEvent(BaseModel):
    """Approval rejected event."""
    approval_id: UUID = Field(..., description="Approval ID")
    tenant_id: UUID = Field(..., description="Tenant ID")
    clarification_id: str = Field(..., description="Clarification ID")
    run_id: str = Field(..., description="Run ID")
    rejected_by: str = Field(..., description="Rejector ID")
    rejection_reason: Optional[str] = Field(None, description="Rejection reason")
    rejected_at: datetime = Field(..., description="Rejection timestamp")


# API Request/Response Models
class ClarificationRequest(BaseModel):
    """Request model for creating approval from clarification."""
    clarification_id: str = Field(..., description="Clarification ID")
    clarification: Dict[str, Any] = Field(..., description="Clarification details")
    requester_contacts: Dict[str, str] = Field(..., description="Requester contact info")


class ApprovalResponseRequest(BaseModel):
    """Request model for approval/rejection responses."""
    response: ApprovalResponseData = Field(..., description="Approval response data")
    requester_contacts: Dict[str, str] = Field(..., description="Requester contact info")


class DelegateApprovalRequest(BaseModel):
    """Request model for delegating approval."""
    delegate_to: str = Field(..., description="User ID to delegate approval to")


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error message")
    status_code: int = Field(..., description="HTTP status code")
    path: Optional[str] = Field(None, description="Request path")
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


# Database initialization
async def init_database(database=None):
    """Initialize database tables."""
    # For now, this is a placeholder
    # In real implementation, this would create tables using SQLAlchemy
    pass
