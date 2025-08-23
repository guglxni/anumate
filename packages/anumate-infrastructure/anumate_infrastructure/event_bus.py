"""Event bus using NATS JetStream with CloudEvents support."""

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

import nats
from nats.js import JetStreamContext
import structlog

from .tenant_context import get_current_tenant_id

logger = structlog.get_logger(__name__)


class CloudEvent:
    """CloudEvents specification implementation."""
    
    def __init__(
        self,
        event_type: str,
        source: str,
        data: Any,
        subject: Optional[str] = None,
        event_id: Optional[str] = None,
        time: Optional[datetime] = None,
        tenant_id: Optional[UUID] = None,
    ) -> None:
        """Initialize CloudEvent."""
        self.spec_version = "1.0"
        self.event_type = event_type
        self.source = source
        self.subject = subject
        self.event_id = event_id or str(uuid4())
        self.time = time or datetime.utcnow()
        self.data_content_type = "application/json"
        self.data = data
        self.tenant_id = tenant_id or get_current_tenant_id()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to CloudEvents dictionary format."""
        event_dict = {
            "specversion": self.spec_version,
            "type": self.event_type,
            "source": self.source,
            "id": self.event_id,
            "time": self.time.isoformat() + "Z",
            "datacontenttype": self.data_content_type,
            "data": self.data,
        }
        
        if self.subject:
            event_dict["subject"] = self.subject
        
        if self.tenant_id:
            event_dict["tenantid"] = str(self.tenant_id)
        
        return event_dict
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloudEvent":
        """Create CloudEvent from dictionary."""
        return cls(
            event_type=data["type"],
            source=data["source"],
            data=data["data"],
            subject=data.get("subject"),
            event_id=data["id"],
            time=datetime.fromisoformat(data["time"].rstrip("Z")),
            tenant_id=UUID(data["tenantid"]) if data.get("tenantid") else None,
        )


class EventBus:
    """NATS JetStream event bus with CloudEvents support."""
    
    def __init__(self, nats_url: Optional[str] = None) -> None:
        """Initialize event bus."""
        self.nats_url = nats_url or os.getenv(
            "NATS_URL", 
            "nats://anumate_app:app_password@localhost:4222"
        )
        self._nc: Optional[nats.NATS] = None
        self._js: Optional[JetStreamContext] = None
    
    async def connect(self) -> None:
        """Connect to NATS server."""
        if self._nc is None:
            self._nc = await nats.connect(
                self.nats_url,
                name="anumate-event-bus",
                max_reconnect_attempts=5,
                reconnect_time_wait=2,
            )
            self._js = self._nc.jetstream()
            logger.info("Connected to NATS JetStream")
    
    async def close(self) -> None:
        """Close NATS connection."""
        if self._nc is not None:
            await self._nc.close()
            self._nc = None
            self._js = None
            logger.info("NATS connection closed")
    
    async def publish(
        self,
        subject: str,
        data: Any,
        event_type: Optional[str] = None,
        source: str = "anumate-platform",
        event_subject: Optional[str] = None,
    ) -> str:
        """Publish CloudEvent to NATS JetStream."""
        await self.connect()
        
        # Create CloudEvent
        cloud_event = CloudEvent(
            event_type=event_type or subject,
            source=source,
            data=data,
            subject=event_subject,
        )
        
        # Publish to JetStream
        ack = await self._js.publish(
            subject,
            cloud_event.to_json().encode(),
            headers={
                "Ce-Specversion": cloud_event.spec_version,
                "Ce-Type": cloud_event.event_type,
                "Ce-Source": cloud_event.source,
                "Ce-Id": cloud_event.event_id,
                "Ce-Time": cloud_event.time.isoformat() + "Z",
                "Content-Type": "application/json",
            }
        )
        
        logger.info(
            "Published event",
            subject=subject,
            event_id=cloud_event.event_id,
            event_type=cloud_event.event_type,
            tenant_id=cloud_event.tenant_id,
        )
        
        return cloud_event.event_id
    
    async def subscribe(
        self,
        subject: str,
        callback,
        durable_name: Optional[str] = None,
        queue_group: Optional[str] = None,
    ) -> None:
        """Subscribe to events with callback."""
        await self.connect()
        
        async def message_handler(msg):
            try:
                # Parse CloudEvent
                event_data = json.loads(msg.data.decode())
                cloud_event = CloudEvent.from_dict(event_data)
                
                # Set tenant context if available
                if cloud_event.tenant_id:
                    from .tenant_context import TenantContext
                    async with TenantContext(cloud_event.tenant_id):
                        await callback(cloud_event, msg)
                else:
                    await callback(cloud_event, msg)
                
                # Acknowledge message
                await msg.ack()
                
            except Exception as e:
                logger.error(
                    "Error processing event",
                    subject=subject,
                    error=str(e),
                    exc_info=True
                )
                # Negative acknowledge to retry
                await msg.nak()
        
        if durable_name:
            # Durable consumer
            await self._js.subscribe(
                subject,
                cb=message_handler,
                durable=durable_name,
                queue=queue_group,
            )
        else:
            # Ephemeral consumer
            await self._js.subscribe(
                subject,
                cb=message_handler,
                queue=queue_group,
            )
        
        logger.info(
            "Subscribed to events",
            subject=subject,
            durable=durable_name,
            queue_group=queue_group,
        )
    
    async def pull_subscribe(
        self,
        subject: str,
        durable_name: str,
        batch_size: int = 10,
    ):
        """Create pull-based subscription for manual message processing."""
        await self.connect()
        
        psub = await self._js.pull_subscribe(
            subject,
            durable=durable_name,
        )
        
        logger.info(
            "Created pull subscription",
            subject=subject,
            durable=durable_name,
        )
        
        return EventSubscription(psub, batch_size)


class EventSubscription:
    """Pull-based event subscription wrapper."""
    
    def __init__(self, psub, batch_size: int = 10) -> None:
        """Initialize subscription."""
        self.psub = psub
        self.batch_size = batch_size
    
    async def fetch(self, timeout: float = 5.0):
        """Fetch messages from subscription."""
        msgs = await self.psub.fetch(self.batch_size, timeout=timeout)
        
        events = []
        for msg in msgs:
            try:
                event_data = json.loads(msg.data.decode())
                cloud_event = CloudEvent.from_dict(event_data)
                events.append((cloud_event, msg))
            except Exception as e:
                logger.error(
                    "Error parsing event",
                    error=str(e),
                    data=msg.data.decode()[:200],
                )
                await msg.nak()
        
        return events
    
    async def close(self) -> None:
        """Close subscription."""
        await self.psub.unsubscribe()