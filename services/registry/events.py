"""
Event Publishing Module

A.4–A.6 Implementation: CloudEvents publishing for capsule lifecycle events
with structured metadata and observability integration.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from dataclasses import dataclass

from anumate_events import EventPublisher, CloudEvent, EventAttributes
from anumate_logging import get_logger
from .settings import RegistrySettings


logger = get_logger(__name__)


@dataclass
class CapsuleEventContext:
    """Context information for capsule events."""
    tenant_id: uuid.UUID
    capsule_id: uuid.UUID
    actor: str  # OIDC subject
    trace_id: Optional[str] = None
    version: Optional[int] = None
    content_hash: Optional[str] = None
    signature: Optional[str] = None


class CapsuleEventPublisher:
    """Event publisher for capsule lifecycle events."""
    
    def __init__(self, settings: RegistrySettings):
        self.settings = settings
        self.publisher = EventPublisher(
            service_name="capsule-registry",
            version="1.0.0"
        )
    
    async def publish_capsule_created(self, context: CapsuleEventContext, 
                                    capsule_data: Dict[str, Any]) -> None:
        """Publish capsule.created event."""
        event = CloudEvent(
            type="dev.anumate.registry.capsule.created",
            source=f"capsule-registry/{context.tenant_id}",
            subject=f"capsule/{context.capsule_id}",
            data={
                "capsule_id": str(context.capsule_id),
                "name": capsule_data.get("name"),
                "owner": capsule_data.get("owner"),
                "visibility": capsule_data.get("visibility"),
                "status": capsule_data.get("status"),
                "description": capsule_data.get("description"),
                "tags": capsule_data.get("tags"),
                "tenant_id": str(context.tenant_id),
                "actor": context.actor,
                "created_at": datetime.now(timezone.utc).isoformat()
            },
            attributes=EventAttributes(
                tenant_id=str(context.tenant_id),
                trace_id=context.trace_id,
                actor=context.actor,
                capsule_id=str(context.capsule_id)
            )
        )
        
        await self._publish_event(event, "capsule_created")
    
    async def publish_version_published(self, context: CapsuleEventContext,
                                      version_data: Dict[str, Any]) -> None:
        """Publish capsule.version.published event."""
        event = CloudEvent(
            type="dev.anumate.registry.capsule.version.published",
            source=f"capsule-registry/{context.tenant_id}",
            subject=f"capsule/{context.capsule_id}/version/{context.version}",
            data={
                "capsule_id": str(context.capsule_id),
                "version": context.version,
                "content_hash": context.content_hash,
                "signature": context.signature,
                "uri": version_data.get("uri"),
                "created_by": version_data.get("created_by"),
                "pubkey_id": version_data.get("pubkey_id"),
                "tenant_id": str(context.tenant_id),
                "actor": context.actor,
                "published_at": datetime.now(timezone.utc).isoformat()
            },
            attributes=EventAttributes(
                tenant_id=str(context.tenant_id),
                trace_id=context.trace_id,
                actor=context.actor,
                capsule_id=str(context.capsule_id),
                version=str(context.version) if context.version else None,
                content_hash=context.content_hash,
                signature=context.signature
            )
        )
        
        await self._publish_event(event, "version_published")
    
    async def publish_capsule_deleted(self, context: CapsuleEventContext,
                                    deletion_data: Dict[str, Any]) -> None:
        """Publish capsule.deleted event."""
        event = CloudEvent(
            type="dev.anumate.registry.capsule.deleted",
            source=f"capsule-registry/{context.tenant_id}",
            subject=f"capsule/{context.capsule_id}",
            data={
                "capsule_id": str(context.capsule_id),
                "name": deletion_data.get("name"),
                "soft_delete": deletion_data.get("soft_delete", True),
                "latest_version": deletion_data.get("latest_version"),
                "tenant_id": str(context.tenant_id),
                "actor": context.actor,
                "deleted_at": datetime.now(timezone.utc).isoformat()
            },
            attributes=EventAttributes(
                tenant_id=str(context.tenant_id),
                trace_id=context.trace_id,
                actor=context.actor,
                capsule_id=str(context.capsule_id)
            )
        )
        
        await self._publish_event(event, "capsule_deleted")
    
    async def publish_capsule_restored(self, context: CapsuleEventContext,
                                     restore_data: Dict[str, Any]) -> None:
        """Publish capsule.restored event."""
        event = CloudEvent(
            type="dev.anumate.registry.capsule.restored",
            source=f"capsule-registry/{context.tenant_id}",
            subject=f"capsule/{context.capsule_id}",
            data={
                "capsule_id": str(context.capsule_id),
                "name": restore_data.get("name"),
                "latest_version": restore_data.get("latest_version"),
                "tenant_id": str(context.tenant_id),
                "actor": context.actor,
                "restored_at": datetime.now(timezone.utc).isoformat()
            },
            attributes=EventAttributes(
                tenant_id=str(context.tenant_id),
                trace_id=context.trace_id,
                actor=context.actor,
                capsule_id=str(context.capsule_id)
            )
        )
        
        await self._publish_event(event, "capsule_restored")
    
    async def publish_validation_failed(self, context: CapsuleEventContext,
                                      validation_errors: Dict[str, Any]) -> None:
        """Publish capsule.validation.failed event."""
        event = CloudEvent(
            type="dev.anumate.registry.capsule.validation.failed",
            source=f"capsule-registry/{context.tenant_id}",
            subject=f"capsule/{context.capsule_id}",
            data={
                "capsule_id": str(context.capsule_id),
                "errors": validation_errors.get("errors", []),
                "warnings": validation_errors.get("warnings", []),
                "tenant_id": str(context.tenant_id),
                "actor": context.actor,
                "failed_at": datetime.now(timezone.utc).isoformat()
            },
            attributes=EventAttributes(
                tenant_id=str(context.tenant_id),
                trace_id=context.trace_id,
                actor=context.actor,
                capsule_id=str(context.capsule_id)
            )
        )
        
        await self._publish_event(event, "validation_failed")
    
    async def _publish_event(self, event: CloudEvent, event_type: str) -> None:
        """Publish event with error handling and logging."""
        try:
            await self.publisher.publish(event)
            
            logger.info(
                "Published capsule event",
                extra={
                    "event_type": event_type,
                    "capsule_id": event.attributes.get("capsule_id"),
                    "tenant_id": event.attributes.get("tenant_id"),
                    "trace_id": event.attributes.get("trace_id")
                }
            )
            
        except Exception as e:
            logger.error(
                "Failed to publish capsule event",
                extra={
                    "event_type": event_type,
                    "error": str(e),
                    "capsule_id": event.attributes.get("capsule_id"),
                    "tenant_id": event.attributes.get("tenant_id"),
                    "trace_id": event.attributes.get("trace_id")
                }
            )
            # Don't re-raise - event publishing failures shouldn't block operations


class EventContextBuilder:
    """Helper to build event contexts from request data."""
    
    @staticmethod
    def from_security_context(security_ctx, capsule_id: uuid.UUID, 
                            trace_id: Optional[str] = None,
                            version: Optional[int] = None,
                            content_hash: Optional[str] = None,
                            signature: Optional[str] = None) -> CapsuleEventContext:
        """Build event context from security context."""
        return CapsuleEventContext(
            tenant_id=security_ctx.tenant_id,
            capsule_id=capsule_id,
            actor=security_ctx.actor,
            trace_id=trace_id,
            version=version,
            content_hash=content_hash,
            signature=signature
        )
    
    @staticmethod 
    def from_capsule_version(capsule_version, security_ctx,
                           trace_id: Optional[str] = None) -> CapsuleEventContext:
        """Build event context from capsule version data."""
        return CapsuleEventContext(
            tenant_id=security_ctx.tenant_id,
            capsule_id=capsule_version.capsule_id,
            actor=security_ctx.actor,
            trace_id=trace_id,
            version=capsule_version.version,
            content_hash=capsule_version.content_hash,
            signature=capsule_version.signature
        )


def create_event_publisher(settings: RegistrySettings) -> CapsuleEventPublisher:
    """Factory function to create configured event publisher."""
    return CapsuleEventPublisher(settings)
