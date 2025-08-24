"""
CloudEvents Event Bus API Service
=================================

FastAPI application providing REST API for event bus management,
monitoring, and administrative operations.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .eventbus_core import EventBusService, EventBusConfig, CloudEvent, EventSubscription
from .publishers import EventPublisherFactory, EventContext
from .subscribers import EventSubscriberFactory

logger = logging.getLogger(__name__)

# Global event bus instance
event_bus: Optional[EventBusService] = None
publisher_factory: Optional[EventPublisherFactory] = None
subscriber_factory: Optional[EventSubscriberFactory] = None


# API Models

class EventPublishRequest(BaseModel):
    """Request model for publishing events."""
    event_type: str = Field(..., description="CloudEvent type")
    data: Dict[str, Any] = Field(..., description="Event data payload") 
    subject: Optional[str] = Field(None, description="Event subject")
    tenant_id: Optional[str] = Field(None, description="Tenant ID")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    trace_context: Optional[str] = Field(None, description="Trace context")


class EventPublishResponse(BaseModel):
    """Response model for published events."""
    event_id: str = Field(..., description="Published event ID")
    success: bool = Field(..., description="Publication success status")
    message: str = Field(..., description="Success or error message")


class SubscriptionRequest(BaseModel):
    """Request model for creating subscriptions."""
    event_types: List[str] = Field(..., description="Event types to subscribe to")
    consumer_name: str = Field(..., description="Consumer name")
    queue_group: Optional[str] = Field(None, description="Queue group for load balancing")
    durable_name: Optional[str] = Field(None, description="Durable consumer name")
    subject_pattern: Optional[str] = Field(None, description="Subject pattern filter")
    max_inflight: int = Field(default=50, description="Max in-flight messages")
    ack_wait: int = Field(default=30, description="Acknowledgment wait time in seconds")
    max_deliver: int = Field(default=3, description="Maximum delivery attempts")


class SubscriptionResponse(BaseModel):
    """Response model for subscription operations."""
    subscription_id: str = Field(..., description="Subscription ID")
    success: bool = Field(..., description="Operation success status")
    message: str = Field(..., description="Success or error message")


class ReplayRequest(BaseModel):
    """Request model for event replay."""
    consumer_name: str = Field(..., description="Consumer name")
    start_time: Optional[datetime] = Field(None, description="Start replay from this time")
    start_sequence: Optional[int] = Field(None, description="Start replay from this sequence")
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")


class ReplayResponse(BaseModel):
    """Response model for replay operations."""
    events_replayed: int = Field(..., description="Number of events replayed")
    success: bool = Field(..., description="Operation success status") 
    message: str = Field(..., description="Success or error message")


class MetricsResponse(BaseModel):
    """Response model for event bus metrics."""
    metrics: Dict[str, Any] = Field(..., description="Event bus metrics")
    timestamp: datetime = Field(..., description="Metrics timestamp")


class DeadLetterResponse(BaseModel):
    """Response model for dead letter messages."""
    dead_letters: List[Dict[str, Any]] = Field(..., description="Dead letter messages")
    count: int = Field(..., description="Number of dead letter messages")


class HealthResponse(BaseModel):
    """Response model for health checks."""
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Check timestamp")
    details: Dict[str, Any] = Field(..., description="Health check details")


# Lifecycle management

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global event_bus, publisher_factory, subscriber_factory
    
    try:
        # Initialize event bus
        config = EventBusConfig()
        event_bus = EventBusService(config)
        await event_bus.start()
        
        # Initialize factories
        publisher_factory = EventPublisherFactory(event_bus)
        subscriber_factory = EventSubscriberFactory(event_bus)
        
        logger.info("Event bus API service started")
        yield
        
    finally:
        # Cleanup
        if event_bus:
            await event_bus.stop()
        logger.info("Event bus API service stopped")


# FastAPI application

app = FastAPI(
    title="Anumate CloudEvents Event Bus API",
    description="REST API for CloudEvents event bus management and operations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependency injection

def get_event_bus() -> EventBusService:
    """Get event bus service dependency."""
    if not event_bus:
        raise HTTPException(status_code=503, detail="Event bus service not available")
    return event_bus


def get_publisher_factory() -> EventPublisherFactory:
    """Get publisher factory dependency."""
    if not publisher_factory:
        raise HTTPException(status_code=503, detail="Publisher factory not available")
    return publisher_factory


def get_subscriber_factory() -> EventSubscriberFactory:
    """Get subscriber factory dependency."""
    if not subscriber_factory:
        raise HTTPException(status_code=503, detail="Subscriber factory not available")
    return subscriber_factory


# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check(bus: EventBusService = Depends(get_event_bus)):
    """Check event bus health."""
    try:
        # Check NATS connection
        nats_healthy = bus.nats and bus.nats.is_connected
        
        # Check Redis connection
        redis_healthy = False
        if bus.redis:
            try:
                await bus.redis.ping()
                redis_healthy = True
            except:
                pass
                
        # Overall health
        healthy = nats_healthy and redis_healthy
        
        return HealthResponse(
            status="healthy" if healthy else "unhealthy",
            timestamp=datetime.now(timezone.utc),
            details={
                "nats_connected": nats_healthy,
                "redis_connected": redis_healthy,
                "running": bus.running
            }
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc),
            details={"error": str(e)}
        )


@app.post("/events/publish", response_model=EventPublishResponse)
async def publish_event(
    request: EventPublishRequest,
    source: str = Query(..., description="Event source URI"),
    bus: EventBusService = Depends(get_event_bus)
):
    """Publish a CloudEvent."""
    try:
        # Create event context
        context = EventContext(
            tenant_id=request.tenant_id,
            correlation_id=request.correlation_id,
            trace_context=request.trace_context
        )
        
        # Create CloudEvent
        event = CloudEvent(
            type=request.event_type,
            source=source,
            data=request.data,
            subject=request.subject,
            tenantid=context.tenant_id,
            correlationid=context.correlation_id,
            tracecontext=context.trace_context
        )
        
        # Publish event
        event_id = await bus.publish_event(event)
        
        return EventPublishResponse(
            event_id=event_id,
            success=True,
            message=f"Event published successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")
        return EventPublishResponse(
            event_id="",
            success=False,
            message=f"Failed to publish event: {str(e)}"
        )


@app.post("/subscriptions", response_model=SubscriptionResponse)
async def create_subscription(
    request: SubscriptionRequest,
    bus: EventBusService = Depends(get_event_bus)
):
    """Create an event subscription."""
    try:
        # Create subscription configuration
        subscription = EventSubscription(
            event_types=set(request.event_types),
            subject_pattern=request.subject_pattern,
            queue_group=request.queue_group,
            durable_name=request.durable_name,
            max_inflight=request.max_inflight,
            ack_wait=request.ack_wait,
            max_deliver=request.max_deliver
        )
        
        # Simple handler that logs events
        async def log_handler(event: CloudEvent):
            logger.info(f"Received event: {event.type} - {event.id}")
            
        # Create subscription
        subscription_id = await bus.subscribe(
            subscription,
            log_handler,
            request.consumer_name
        )
        
        return SubscriptionResponse(
            subscription_id=subscription_id,
            success=True,
            message="Subscription created successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        return SubscriptionResponse(
            subscription_id="",
            success=False,
            message=f"Failed to create subscription: {str(e)}"
        )


@app.delete("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def delete_subscription(
    subscription_id: str,
    bus: EventBusService = Depends(get_event_bus)
):
    """Delete an event subscription."""
    try:
        await bus.unsubscribe(subscription_id)
        
        return SubscriptionResponse(
            subscription_id=subscription_id,
            success=True,
            message="Subscription deleted successfully"
        )
        
    except Exception as e:
        logger.error(f"Failed to delete subscription {subscription_id}: {e}")
        return SubscriptionResponse(
            subscription_id=subscription_id,
            success=False,
            message=f"Failed to delete subscription: {str(e)}"
        )


@app.post("/events/replay", response_model=ReplayResponse)
async def replay_events(
    request: ReplayRequest,
    bus: EventBusService = Depends(get_event_bus)
):
    """Replay events for a consumer."""
    try:
        event_types = set(request.event_types) if request.event_types else None
        
        events_replayed = await bus.replay_events(
            consumer_name=request.consumer_name,
            start_time=request.start_time,
            start_sequence=request.start_sequence,
            event_types=event_types
        )
        
        return ReplayResponse(
            events_replayed=events_replayed,
            success=True,
            message=f"Successfully replayed {events_replayed} events"
        )
        
    except Exception as e:
        logger.error(f"Failed to replay events: {e}")
        return ReplayResponse(
            events_replayed=0,
            success=False,
            message=f"Failed to replay events: {str(e)}"
        )


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(bus: EventBusService = Depends(get_event_bus)):
    """Get event bus metrics."""
    try:
        metrics = await bus.get_metrics()
        
        return MetricsResponse(
            metrics=metrics,
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@app.get("/dead-letters", response_model=DeadLetterResponse)
async def get_dead_letters(
    limit: int = Query(default=100, description="Maximum number of dead letters to return"),
    subject_filter: Optional[str] = Query(default=None, description="Subject filter"),
    bus: EventBusService = Depends(get_event_bus)
):
    """Get dead letter messages."""
    try:
        dead_letters = await bus.get_dead_letters(limit, subject_filter)
        
        return DeadLetterResponse(
            dead_letters=dead_letters,
            count=len(dead_letters)
        )
        
    except Exception as e:
        logger.error(f"Failed to get dead letters: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dead letters: {str(e)}")


# Service-specific publisher endpoints

@app.get("/publishers/registry")
async def get_registry_publisher_info(factory: EventPublisherFactory = Depends(get_publisher_factory)):
    """Get information about the registry publisher."""
    return {
        "service": "registry",
        "supported_events": [
            "com.anumate.capsule.created",
            "com.anumate.capsule.updated", 
            "com.anumate.capsule.published"
        ]
    }


@app.get("/publishers/policy") 
async def get_policy_publisher_info(factory: EventPublisherFactory = Depends(get_publisher_factory)):
    """Get information about the policy publisher."""
    return {
        "service": "policy",
        "supported_events": [
            "com.anumate.policy.created",
            "com.anumate.policy.updated",
            "com.anumate.policy.violated",
            "com.anumate.policy.enforced"
        ]
    }


@app.get("/publishers/orchestrator")
async def get_orchestrator_publisher_info(factory: EventPublisherFactory = Depends(get_publisher_factory)):
    """Get information about the orchestrator publisher."""
    return {
        "service": "orchestrator", 
        "supported_events": [
            "com.anumate.execution.started",
            "com.anumate.execution.completed",
            "com.anumate.execution.failed",
            "com.anumate.execution.paused",
            "com.anumate.execution.resumed",
            "com.anumate.execution.cancelled"
        ]
    }


# Utility endpoints

@app.get("/")
async def root():
    """API root endpoint."""
    return {
        "service": "Anumate CloudEvents Event Bus API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoints": {
            "health": "/health",
            "publish": "/events/publish", 
            "subscribe": "/subscriptions",
            "replay": "/events/replay",
            "metrics": "/metrics",
            "dead_letters": "/dead-letters"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )
