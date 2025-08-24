"""CloudEvents publishing for Capsule Registry operations."""

from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

from anumate_events import CloudEventPublisher, CloudEvent
from anumate_tracing import get_trace_id


class CapsuleEventPublisher:
    """Publisher for Capsule Registry CloudEvents."""
    
    def __init__(self, event_publisher: CloudEventPublisher, service_name: str = "capsule-registry"):
        self.publisher = event_publisher
        self.service_name = service_name
    
    async def publish_capsule_created(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        capsule_name: str,
        actor: str,
        trace_id: Optional[str] = None
    ):
        """Publish capsule.created event."""
        event = CloudEvent(
            type="io.anumate.capsule.created",
            source=f"urn:anumate:service:{self.service_name}",
            subject=f"capsule/{capsule_id}",
            data={
                "tenant_id": str(tenant_id),
                "capsule_id": str(capsule_id),
                "capsule_name": capsule_name,
                "actor": actor,
                "created_at": datetime.utcnow().isoformat()
            },
            trace_id=trace_id or get_trace_id()
        )
        
        await self.publisher.publish(event)
    
    async def publish_version_published(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        capsule_name: str,
        version: int,
        content_hash: str,
        signature: str,
        uri: str,
        actor: str,
        trace_id: Optional[str] = None
    ):
        """Publish capsule.version.published event."""
        event = CloudEvent(
            type="io.anumate.capsule.version.published",
            source=f"urn:anumate:service:{self.service_name}",
            subject=f"capsule/{capsule_id}/version/{version}",
            data={
                "tenant_id": str(tenant_id),
                "capsule_id": str(capsule_id),
                "capsule_name": capsule_name,
                "version": version,
                "content_hash": content_hash,
                "signature": signature,
                "uri": uri,
                "actor": actor,
                "published_at": datetime.utcnow().isoformat()
            },
            trace_id=trace_id or get_trace_id()
        )
        
        await self.publisher.publish(event)
    
    async def publish_capsule_deleted(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        capsule_name: str,
        actor: str,
        hard_delete: bool = False,
        trace_id: Optional[str] = None
    ):
        """Publish capsule.deleted event."""
        event_type = "io.anumate.capsule.hard_deleted" if hard_delete else "io.anumate.capsule.deleted"
        
        event = CloudEvent(
            type=event_type,
            source=f"urn:anumate:service:{self.service_name}",
            subject=f"capsule/{capsule_id}",
            data={
                "tenant_id": str(tenant_id),
                "capsule_id": str(capsule_id),
                "capsule_name": capsule_name,
                "actor": actor,
                "hard_delete": hard_delete,
                "deleted_at": datetime.utcnow().isoformat()
            },
            trace_id=trace_id or get_trace_id()
        )
        
        await self.publisher.publish(event)
    
    async def publish_capsule_restored(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        capsule_name: str,
        actor: str,
        trace_id: Optional[str] = None
    ):
        """Publish capsule.restored event."""
        event = CloudEvent(
            type="io.anumate.capsule.restored",
            source=f"urn:anumate:service:{self.service_name}",
            subject=f"capsule/{capsule_id}",
            data={
                "tenant_id": str(tenant_id),
                "capsule_id": str(capsule_id),
                "capsule_name": capsule_name,
                "actor": actor,
                "restored_at": datetime.utcnow().isoformat()
            },
            trace_id=trace_id or get_trace_id()
        )
        
        await self.publisher.publish(event)
    
    async def publish_capsule_linted(
        self,
        tenant_id: UUID,
        capsule_id: UUID,
        capsule_name: str,
        is_valid: bool,
        error_count: int,
        warning_count: int,
        content_hash: Optional[str],
        actor: str,
        trace_id: Optional[str] = None
    ):
        """Publish capsule.linted event."""
        event = CloudEvent(
            type="io.anumate.capsule.linted",
            source=f"urn:anumate:service:{self.service_name}",
            subject=f"capsule/{capsule_id}",
            data={
                "tenant_id": str(tenant_id),
                "capsule_id": str(capsule_id),
                "capsule_name": capsule_name,
                "is_valid": is_valid,
                "error_count": error_count,
                "warning_count": warning_count,
                "content_hash": content_hash,
                "actor": actor,
                "linted_at": datetime.utcnow().isoformat()
            },
            trace_id=trace_id or get_trace_id()
        )
        
        await self.publisher.publish(event)


def create_event_publisher(event_bus_url: Optional[str] = None) -> Optional[CapsuleEventPublisher]:
    """Factory function to create event publisher."""
    if not event_bus_url:
        # Return None if no event bus configured (events disabled)
        return None
    
    try:
        cloud_event_publisher = CloudEventPublisher(event_bus_url)
        return CapsuleEventPublisher(cloud_event_publisher)
    except Exception as e:
        # Log error but don't fail service startup
        import logging
        logging.warning(f"Failed to create event publisher: {e}")
        return None


class NoOpEventPublisher:
    """No-op event publisher for testing or when events are disabled."""
    
    async def publish_capsule_created(self, *args, **kwargs):
        pass
    
    async def publish_version_published(self, *args, **kwargs):
        pass
    
    async def publish_capsule_deleted(self, *args, **kwargs):
        pass
    
    async def publish_capsule_restored(self, *args, **kwargs):
        pass
    
    async def publish_capsule_linted(self, *args, **kwargs):
        pass
