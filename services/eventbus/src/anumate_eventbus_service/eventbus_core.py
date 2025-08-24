"""
A.28 Implementation: CloudEvents Event Bus Service
=================================================

Comprehensive event-driven architecture implementation using NATS with CloudEvents format.
Provides publishers, subscribers, routing, replay, and dead letter handling for all Anumate services.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, asdict
from enum import Enum

import nats
from nats.aio.client import Client as NATS
from nats.aio.msg import Msg
import aioredis
from pydantic import BaseModel, Field, validator
from fastapi import FastAPI, HTTPException, BackgroundTasks
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Standard CloudEvents event types for Anumate platform."""
    # Capsule Registry Events
    CAPSULE_CREATED = "com.anumate.capsule.created"
    CAPSULE_UPDATED = "com.anumate.capsule.updated"
    CAPSULE_DELETED = "com.anumate.capsule.deleted"
    CAPSULE_PUBLISHED = "com.anumate.capsule.published"
    
    # Policy Events
    POLICY_CREATED = "com.anumate.policy.created"
    POLICY_UPDATED = "com.anumate.policy.updated"
    POLICY_VIOLATED = "com.anumate.policy.violated"
    POLICY_ENFORCED = "com.anumate.policy.enforced"
    
    # Plan Compiler Events
    PLAN_COMPILED = "com.anumate.plan.compiled"
    PLAN_COMPILATION_FAILED = "com.anumate.plan.compilation.failed"
    PLAN_OPTIMIZED = "com.anumate.plan.optimized"
    
    # GhostRun Events
    PREFLIGHT_STARTED = "com.anumate.preflight.started"
    PREFLIGHT_COMPLETED = "com.anumate.preflight.completed"
    PREFLIGHT_FAILED = "com.anumate.preflight.failed"
    
    # Orchestrator Events
    EXECUTION_STARTED = "com.anumate.execution.started"
    EXECUTION_COMPLETED = "com.anumate.execution.completed"
    EXECUTION_FAILED = "com.anumate.execution.failed"
    EXECUTION_PAUSED = "com.anumate.execution.paused"
    EXECUTION_RESUMED = "com.anumate.execution.resumed"
    EXECUTION_CANCELLED = "com.anumate.execution.cancelled"
    
    # Approval Events
    APPROVAL_REQUESTED = "com.anumate.approval.requested"
    APPROVAL_GRANTED = "com.anumate.approval.granted"
    APPROVAL_REJECTED = "com.anumate.approval.rejected"
    APPROVAL_TIMEOUT = "com.anumate.approval.timeout"
    
    # Capability Token Events
    TOKEN_ISSUED = "com.anumate.token.issued"
    TOKEN_VERIFIED = "com.anumate.token.verified"
    TOKEN_EXPIRED = "com.anumate.token.expired"
    TOKEN_REVOKED = "com.anumate.token.revoked"
    
    # Receipt Events
    RECEIPT_CREATED = "com.anumate.receipt.created"
    RECEIPT_VERIFIED = "com.anumate.receipt.verified"
    RECEIPT_ARCHIVED = "com.anumate.receipt.archived"
    
    # Audit Events
    AUDIT_EVENT_CAPTURED = "com.anumate.audit.captured"
    AUDIT_EXPORT_REQUESTED = "com.anumate.audit.export.requested"
    AUDIT_EXPORT_COMPLETED = "com.anumate.audit.export.completed"


class CloudEvent(BaseModel):
    """
    CloudEvents v1.0 compliant event structure.
    https://github.com/cloudevents/spec/blob/v1.0/spec.md
    """
    # Required attributes
    specversion: str = Field(default="1.0", description="CloudEvents specification version")
    type: str = Field(..., description="Event type")
    source: str = Field(..., description="Event source URI")
    id: str = Field(..., description="Event ID")
    
    # Optional attributes
    time: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    datacontenttype: Optional[str] = Field(default="application/json")
    dataschema: Optional[str] = None
    subject: Optional[str] = None
    
    # Extension attributes
    tenantid: Optional[str] = Field(None, alias="tenantid")
    correlationid: Optional[str] = Field(None, alias="correlationid")
    tracecontext: Optional[str] = Field(None, alias="tracecontext")
    
    # Data payload
    data: Optional[Dict[str, Any]] = None
    
    @validator('id', pre=True, always=True)
    def generate_id_if_missing(cls, v):
        return v or str(uuid.uuid4())
        
    @validator('time', pre=True)
    def parse_time(cls, v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace('Z', '+00:00'))
        return v
        
    class Config:
        allow_population_by_field_name = True


@dataclass
class EventSubscription:
    """Configuration for event subscription."""
    event_types: Set[str]
    subject_pattern: Optional[str] = None
    queue_group: Optional[str] = None
    durable_name: Optional[str] = None
    max_inflight: int = 100
    ack_wait: int = 30  # seconds
    max_deliver: int = 5
    replay_policy: str = "instant"  # instant, original, by_start_sequence, by_start_time


class EventBusConfig(BaseModel):
    """Event bus configuration."""
    nats_url: str = "nats://localhost:4222"
    nats_cluster_id: str = "anumate-cluster"
    redis_url: str = "redis://localhost:6379"
    
    # Stream configuration
    stream_name: str = "ANUMATE_EVENTS"
    max_msgs: int = 1000000
    max_bytes: int = 1024 * 1024 * 1024  # 1GB
    max_age: int = 7 * 24 * 3600  # 7 days in seconds
    
    # Dead letter configuration
    dead_letter_stream: str = "ANUMATE_DEAD_LETTERS"
    max_deliver_attempts: int = 5
    
    # Retry configuration
    retry_backoff_base: float = 1.0
    retry_backoff_max: float = 60.0
    retry_backoff_multiplier: float = 2.0


class EventBusService:
    """
    Comprehensive CloudEvents event bus implementation using NATS JetStream.
    
    Features:
    - CloudEvents v1.0 compliant event publishing
    - Durable event subscriptions with queue groups
    - Event replay and recovery
    - Dead letter handling for failed events
    - Event routing and filtering
    - Redis-backed event tracking and metrics
    """
    
    def __init__(self, config: EventBusConfig):
        self.config = config
        self.nats: Optional[NATS] = None
        self.jetstream = None
        self.redis: Optional[aioredis.Redis] = None
        self.subscribers: Dict[str, Callable] = {}
        self.running = False
        
    async def start(self):
        """Initialize and start the event bus service."""
        try:
            # Connect to NATS
            self.nats = await nats.connect(self.config.nats_url)
            self.jetstream = self.nats.jetstream()
            
            # Connect to Redis
            self.redis = await aioredis.from_url(self.config.redis_url)
            
            # Create or update streams
            await self._setup_streams()
            
            self.running = True
            logger.info("Event bus service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start event bus service: {e}")
            raise
            
    async def stop(self):
        """Stop the event bus service."""
        self.running = False
        
        if self.nats:
            await self.nats.close()
        if self.redis:
            await self.redis.close()
            
        logger.info("Event bus service stopped")
        
    async def _setup_streams(self):
        """Set up NATS JetStream streams."""
        try:
            # Main events stream
            stream_config = {
                "name": self.config.stream_name,
                "subjects": ["events.>"],
                "max_msgs": self.config.max_msgs,
                "max_bytes": self.config.max_bytes,
                "max_age": self.config.max_age,
                "storage": "file",
                "retention": "limits",
                "discard": "old"
            }
            
            try:
                await self.jetstream.stream_info(self.config.stream_name)
                await self.jetstream.update_stream(**stream_config)
                logger.info(f"Updated stream: {self.config.stream_name}")
            except:
                await self.jetstream.add_stream(**stream_config)
                logger.info(f"Created stream: {self.config.stream_name}")
                
            # Dead letter stream
            dl_stream_config = {
                "name": self.config.dead_letter_stream,
                "subjects": ["dead_letters.>"],
                "max_msgs": 100000,
                "max_bytes": 100 * 1024 * 1024,  # 100MB
                "max_age": 30 * 24 * 3600,  # 30 days
                "storage": "file",
                "retention": "limits"
            }
            
            try:
                await self.jetstream.stream_info(self.config.dead_letter_stream)
                await self.jetstream.update_stream(**dl_stream_config)
                logger.info(f"Updated dead letter stream: {self.config.dead_letter_stream}")
            except:
                await self.jetstream.add_stream(**dl_stream_config)
                logger.info(f"Created dead letter stream: {self.config.dead_letter_stream}")
                
        except Exception as e:
            logger.error(f"Failed to setup streams: {e}")
            raise
            
    async def publish_event(
        self, 
        event: CloudEvent,
        subject: Optional[str] = None
    ) -> str:
        """
        Publish a CloudEvent to the event bus.
        
        Args:
            event: CloudEvent to publish
            subject: Optional NATS subject override
            
        Returns:
            Event ID
        """
        if not self.running:
            raise RuntimeError("Event bus service is not running")
            
        try:
            # Generate subject from event type if not provided
            if not subject:
                subject = f"events.{event.type.replace('.', '_')}"
                
            # Serialize event
            event_data = event.json().encode()
            
            # Publish to JetStream
            ack = await self.jetstream.publish(subject, event_data)
            
            # Track event in Redis
            await self._track_event_published(event, ack.seq)
            
            logger.debug(f"Published event {event.id} to {subject} (seq={ack.seq})")
            return event.id
            
        except Exception as e:
            logger.error(f"Failed to publish event {event.id}: {e}")
            await self._track_event_failed(event, str(e))
            raise
            
    async def subscribe(
        self,
        subscription: EventSubscription,
        handler: Callable[[CloudEvent], None],
        consumer_name: str
    ) -> str:
        """
        Subscribe to events with a handler.
        
        Args:
            subscription: Subscription configuration
            handler: Event handler function
            consumer_name: Unique consumer name
            
        Returns:
            Subscription ID
        """
        if not self.running:
            raise RuntimeError("Event bus service is not running")
            
        try:
            # Build consumer configuration
            consumer_config = {
                "durable_name": subscription.durable_name or consumer_name,
                "deliver_policy": "all",  # Start from beginning
                "ack_policy": "explicit",
                "ack_wait": subscription.ack_wait,
                "max_deliver": subscription.max_deliver,
                "max_ack_pending": subscription.max_inflight,
                "replay_policy": subscription.replay_policy
            }
            
            # Add queue group if specified
            if subscription.queue_group:
                consumer_config["deliver_group"] = subscription.queue_group
                
            # Create subject filter
            if subscription.subject_pattern:
                subject_filter = subscription.subject_pattern
            else:
                # Build filter from event types
                if len(subscription.event_types) == 1:
                    event_type = list(subscription.event_types)[0]
                    subject_filter = f"events.{event_type.replace('.', '_')}"
                else:
                    subject_filter = "events.>"
                    
            consumer_config["filter_subject"] = subject_filter
            
            # Create consumer
            consumer = await self.jetstream.add_consumer(
                self.config.stream_name,
                **consumer_config
            )
            
            # Create subscription
            subscription_id = str(uuid.uuid4())
            
            # Subscribe with message handler
            async def message_handler(msg: Msg):
                try:
                    # Parse CloudEvent
                    event_data = json.loads(msg.data.decode())
                    event = CloudEvent.parse_obj(event_data)
                    
                    # Filter by event types if specified
                    if subscription.event_types and event.type not in subscription.event_types:
                        await msg.ack()
                        return
                        
                    # Track event processing
                    await self._track_event_processing(event, consumer_name)
                    
                    # Call handler
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                        
                    # Acknowledge message
                    await msg.ack()
                    
                    # Track successful processing
                    await self._track_event_processed(event, consumer_name)
                    
                except Exception as e:
                    logger.error(f"Error processing event in {consumer_name}: {e}")
                    
                    # Try to extract event ID for tracking
                    event_id = "unknown"
                    try:
                        event_data = json.loads(msg.data.decode())
                        event_id = event_data.get("id", "unknown")
                    except:
                        pass
                        
                    # Track failed processing
                    await self._track_event_processing_failed(event_id, consumer_name, str(e))
                    
                    # Check if we should send to dead letter queue
                    if msg.metadata.num_delivered >= subscription.max_deliver:
                        await self._send_to_dead_letter(msg, str(e))
                        await msg.ack()  # Acknowledge to remove from main stream
                    else:
                        await msg.nak()  # Negative acknowledge for retry
                        
            # Subscribe to messages
            psub = await consumer.subscribe(cb=message_handler)
            
            # Store subscription
            self.subscribers[subscription_id] = {
                "consumer": consumer,
                "subscription": psub,
                "config": subscription,
                "handler": handler
            }
            
            logger.info(f"Created subscription {subscription_id} for {consumer_name}")
            return subscription_id
            
        except Exception as e:
            logger.error(f"Failed to create subscription for {consumer_name}: {e}")
            raise
            
    async def unsubscribe(self, subscription_id: str):
        """Unsubscribe from events."""
        if subscription_id in self.subscribers:
            try:
                sub_info = self.subscribers[subscription_id]
                await sub_info["subscription"].unsubscribe()
                del self.subscribers[subscription_id]
                logger.info(f"Unsubscribed {subscription_id}")
            except Exception as e:
                logger.error(f"Error unsubscribing {subscription_id}: {e}")
                
    async def replay_events(
        self,
        consumer_name: str,
        start_time: Optional[datetime] = None,
        start_sequence: Optional[int] = None,
        event_types: Optional[Set[str]] = None
    ) -> int:
        """
        Replay events for a consumer.
        
        Args:
            consumer_name: Consumer to replay events for
            start_time: Start replaying from this time
            start_sequence: Start replaying from this sequence
            event_types: Filter by event types
            
        Returns:
            Number of events replayed
        """
        try:
            # Build replay consumer configuration
            replay_config = {
                "durable_name": f"{consumer_name}_replay_{uuid.uuid4().hex[:8]}",
                "ack_policy": "explicit"
            }
            
            if start_time:
                replay_config["opt_start_time"] = start_time
            elif start_sequence:
                replay_config["opt_start_seq"] = start_sequence
            else:
                replay_config["deliver_policy"] = "all"
                
            # Create replay consumer
            consumer = await self.jetstream.add_consumer(
                self.config.stream_name,
                **replay_config
            )
            
            events_replayed = 0
            
            # Process messages
            async def replay_handler(msg: Msg):
                nonlocal events_replayed
                
                try:
                    event_data = json.loads(msg.data.decode())
                    event = CloudEvent.parse_obj(event_data)
                    
                    # Filter by event types if specified
                    if event_types and event.type not in event_types:
                        await msg.ack()
                        return
                        
                    # Track replayed event
                    await self._track_event_replayed(event, consumer_name)
                    events_replayed += 1
                    
                    await msg.ack()
                    
                except Exception as e:
                    logger.error(f"Error during replay: {e}")
                    await msg.ack()
                    
            # Subscribe and process
            psub = await consumer.subscribe(cb=replay_handler)
            
            # Wait for replay to complete (simplified - in production, add timeout)
            await asyncio.sleep(1)  # Allow time for processing
            
            # Clean up
            await psub.unsubscribe()
            
            logger.info(f"Replayed {events_replayed} events for {consumer_name}")
            return events_replayed
            
        except Exception as e:
            logger.error(f"Failed to replay events for {consumer_name}: {e}")
            raise
            
    async def _send_to_dead_letter(self, msg: Msg, error: str):
        """Send failed message to dead letter queue."""
        try:
            # Build dead letter event
            dead_letter_data = {
                "original_subject": msg.subject,
                "original_data": msg.data.decode(),
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "attempts": msg.metadata.num_delivered,
                "stream": msg.metadata.stream,
                "consumer": msg.metadata.consumer,
                "sequence": msg.metadata.sequence.stream
            }
            
            # Publish to dead letter stream
            dead_letter_subject = f"dead_letters.{msg.subject}"
            await self.jetstream.publish(
                dead_letter_subject, 
                json.dumps(dead_letter_data).encode()
            )
            
            logger.warning(f"Sent message to dead letter queue: {dead_letter_subject}")
            
        except Exception as e:
            logger.error(f"Failed to send message to dead letter queue: {e}")
            
    async def _track_event_published(self, event: CloudEvent, sequence: int):
        """Track published event in Redis."""
        if not self.redis:
            return
            
        try:
            event_key = f"event:published:{event.id}"
            event_data = {
                "id": event.id,
                "type": event.type,
                "source": event.source,
                "published_at": datetime.now(timezone.utc).isoformat(),
                "sequence": sequence,
                "tenant_id": event.tenantid or "unknown"
            }
            
            await self.redis.hset(event_key, mapping=event_data)
            await self.redis.expire(event_key, 86400)  # 24 hours
            
            # Update metrics
            await self.redis.incr("events:published:total")
            await self.redis.incr(f"events:published:type:{event.type}")
            
        except Exception as e:
            logger.error(f"Failed to track published event: {e}")
            
    async def _track_event_processing(self, event: CloudEvent, consumer: str):
        """Track event processing start."""
        if not self.redis:
            return
            
        try:
            processing_key = f"event:processing:{event.id}:{consumer}"
            await self.redis.set(processing_key, datetime.now(timezone.utc).isoformat(), ex=3600)
            
            await self.redis.incr("events:processing:total")
            await self.redis.incr(f"events:processing:consumer:{consumer}")
            
        except Exception as e:
            logger.error(f"Failed to track event processing: {e}")
            
    async def _track_event_processed(self, event: CloudEvent, consumer: str):
        """Track successful event processing."""
        if not self.redis:
            return
            
        try:
            # Remove processing marker
            processing_key = f"event:processing:{event.id}:{consumer}"
            await self.redis.delete(processing_key)
            
            # Track completion
            completed_key = f"event:completed:{event.id}:{consumer}"
            await self.redis.set(completed_key, datetime.now(timezone.utc).isoformat(), ex=86400)
            
            await self.redis.incr("events:processed:total")
            await self.redis.incr(f"events:processed:consumer:{consumer}")
            
        except Exception as e:
            logger.error(f"Failed to track event processed: {e}")
            
    async def _track_event_processing_failed(self, event_id: str, consumer: str, error: str):
        """Track failed event processing."""
        if not self.redis:
            return
            
        try:
            failed_key = f"event:failed:{event_id}:{consumer}"
            failed_data = {
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.hset(failed_key, mapping=failed_data)
            await self.redis.expire(failed_key, 86400)
            
            await self.redis.incr("events:failed:total")
            await self.redis.incr(f"events:failed:consumer:{consumer}")
            
        except Exception as e:
            logger.error(f"Failed to track event processing failure: {e}")
            
    async def _track_event_failed(self, event: CloudEvent, error: str):
        """Track event publishing failure."""
        if not self.redis:
            return
            
        try:
            failed_key = f"event:publish_failed:{event.id}"
            failed_data = {
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat()
            }
            await self.redis.hset(failed_key, mapping=failed_data)
            await self.redis.expire(failed_key, 86400)
            
            await self.redis.incr("events:publish_failed:total")
            
        except Exception as e:
            logger.error(f"Failed to track event publish failure: {e}")
            
    async def _track_event_replayed(self, event: CloudEvent, consumer: str):
        """Track event replay."""
        if not self.redis:
            return
            
        try:
            await self.redis.incr("events:replayed:total")
            await self.redis.incr(f"events:replayed:consumer:{consumer}")
            
        except Exception as e:
            logger.error(f"Failed to track event replay: {e}")
            
    async def get_metrics(self) -> Dict[str, Any]:
        """Get event bus metrics."""
        if not self.redis:
            return {}
            
        try:
            metrics = {}
            
            # Get all metric keys
            keys = await self.redis.keys("events:*:total")
            
            for key in keys:
                metric_name = key.decode().replace(":", "_")
                value = await self.redis.get(key)
                metrics[metric_name] = int(value) if value else 0
                
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {}
            
    async def get_dead_letters(
        self, 
        limit: int = 100, 
        subject_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get dead letter messages."""
        try:
            dead_letters = []
            
            # Create consumer for dead letter stream
            consumer_config = {
                "deliver_policy": "all",
                "ack_policy": "explicit"
            }
            
            if subject_filter:
                consumer_config["filter_subject"] = f"dead_letters.{subject_filter}"
            else:
                consumer_config["filter_subject"] = "dead_letters.>"
                
            consumer = await self.jetstream.add_consumer(
                self.config.dead_letter_stream,
                durable_name=f"dead_letter_reader_{uuid.uuid4().hex[:8]}",
                **consumer_config
            )
            
            # Fetch messages
            messages = await consumer.fetch(limit)
            
            for msg in messages:
                try:
                    dead_letter_data = json.loads(msg.data.decode())
                    dead_letters.append(dead_letter_data)
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Error reading dead letter message: {e}")
                    await msg.ack()
                    
            return dead_letters
            
        except Exception as e:
            logger.error(f"Failed to get dead letters: {e}")
            return []
