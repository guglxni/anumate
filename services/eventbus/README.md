# Anumate CloudEvents Event Bus Service

Enterprise-grade CloudEvents v1.0 compliant event bus service providing event-driven architecture foundation for the Anumate platform.

## Features

### Core Event Bus
- **CloudEvents v1.0 Compliance**: Full compliance with CloudEvents specification
- **NATS JetStream Backend**: Reliable, high-performance message streaming
- **Event Routing**: Flexible subject-based routing and filtering
- **Dead Letter Handling**: Automatic dead letter queue for failed events
- **Event Replay**: Replay events by time or sequence for recovery
- **Multi-tenant Support**: Tenant isolation and event filtering

### Publishers & Subscribers
- **Service-Specific Publishers**: Pre-configured publishers for all Anumate services
- **Flexible Subscription Model**: Queue groups, durable consumers, filtering
- **Automatic Retries**: Configurable retry policies with exponential backoff
- **Circuit Breaker**: Protection against cascading failures
- **Load Balancing**: Queue group-based load balancing for subscribers

### Monitoring & Operations  
- **Redis-backed Metrics**: Real-time event metrics and tracking
- **Health Checks**: Comprehensive health monitoring for all components
- **REST API**: Full REST API for event bus management and monitoring
- **Prometheus Integration**: Metrics export for monitoring dashboards
- **Distributed Tracing**: OpenTelemetry integration for request tracing

### Enterprise Features
- **High Availability**: Multi-node NATS cluster support
- **Disaster Recovery**: Event replay and backup capabilities  
- **Security**: TLS encryption and authentication
- **Compliance Logging**: Complete audit trail for all events
- **Rate Limiting**: Protection against event floods

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Anumate Services                         │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│   Registry  │   Policy    │ Orchestrator│   Approvals     │
│   Service   │   Service   │   Service   │   Service       │
└─────┬───────┴─────┬───────┴─────┬───────┴─────┬───────────┘
      │             │             │             │
      │ Publish     │ Subscribe   │ Publish     │ Subscribe
      │ Events      │ to Events   │ Events      │ to Events
      │             │             │             │
┌─────▼─────────────▼─────────────▼─────────────▼───────────┐
│                 Event Bus Service                         │
│ ┌─────────────────────────────────────────────────────┐   │
│ │              CloudEvent Router                      │   │
│ │   • Event Type Routing                             │   │
│ │   • Subject Pattern Matching                       │   │
│ │   • Tenant Filtering                               │   │
│ └─────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────┐   │
│ │              NATS JetStream                         │   │
│ │   • Event Streams                                  │   │
│ │   • Durable Consumers                              │   │
│ │   • Dead Letter Queue                              │   │
│ └─────────────────────────────────────────────────────┘   │
│ ┌─────────────────────────────────────────────────────┐   │
│ │              Redis Tracking                         │   │
│ │   • Event Metrics                                  │   │
│ │   • Processing Status                              │   │
│ │   • Performance Monitoring                         │   │
│ └─────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────┘
```

## Quick Start

### Installation

```bash
# Install the package
pip install anumate-eventbus-service

# Or for development
pip install -e ".[dev]"
```

### Basic Usage

```python
import asyncio
from anumate_eventbus_service import (
    EventBusService, EventBusConfig, CloudEvent, EventType
)

async def main():
    # Initialize event bus
    config = EventBusConfig()
    event_bus = EventBusService(config)
    await event_bus.start()
    
    # Publish an event
    event = CloudEvent(
        type=EventType.CAPSULE_CREATED,
        source="https://anumate.com/services/registry",
        data={
            "capsule_id": "cap-123",
            "name": "terraform-aws",
            "version": "1.0.0"
        }
    )
    
    event_id = await event_bus.publish_event(event)
    print(f"Published event: {event_id}")
    
    # Subscribe to events
    from anumate_eventbus_service import EventSubscription
    
    subscription = EventSubscription(
        event_types={EventType.CAPSULE_CREATED},
        queue_group="registry_processors",
        durable_name="registry_consumer"
    )
    
    async def handle_event(event: CloudEvent):
        print(f"Received: {event.type} - {event.data}")
    
    subscription_id = await event_bus.subscribe(
        subscription, handle_event, "registry_handler"
    )
    
    # Keep running
    await asyncio.sleep(60)
    
    # Cleanup
    await event_bus.unsubscribe(subscription_id)
    await event_bus.stop()

asyncio.run(main())
```

### Service Integration

```python
from anumate_eventbus_service import (
    EventPublisherFactory, EventSubscriberFactory, EventContext
)

async def integrate_with_service():
    # Initialize event bus
    event_bus = EventBusService(EventBusConfig())
    await event_bus.start()
    
    # Get service-specific publisher
    factory = EventPublisherFactory(event_bus)
    registry_publisher = factory.get_capsule_registry_publisher()
    
    # Publish service event
    context = EventContext(
        tenant_id="tenant-123",
        correlation_id="req-456"
    )
    
    await registry_publisher.publish_capsule_created(
        capsule_id="cap-789",
        capsule_name="terraform-aws",
        version="2.0.0", 
        author="user@anumate.com",
        context=context
    )
    
    # Create service subscriber
    subscriber_factory = EventSubscriberFactory(event_bus)
    policy_subscriber = subscriber_factory.create_policy_subscriber()
    
    await policy_subscriber.start()
```

### REST API Usage

```bash
# Start the API server
uvicorn anumate_eventbus_service.app:app --host 0.0.0.0 --port 8080

# Publish an event via API
curl -X POST "http://localhost:8080/events/publish?source=https://anumate.com/test" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "com.anumate.test.event",
    "data": {"message": "Hello World"},
    "tenant_id": "test-tenant"
  }'

# Get event bus metrics
curl "http://localhost:8080/metrics"

# Check health
curl "http://localhost:8080/health"
```

## Configuration

### Environment Variables

```bash
# NATS Configuration
NATS_URL=nats://localhost:4222
NATS_CLUSTER_ID=anumate-cluster

# Redis Configuration  
REDIS_URL=redis://localhost:6379

# Stream Configuration
STREAM_NAME=ANUMATE_EVENTS
MAX_MSGS=1000000
MAX_BYTES=1073741824
MAX_AGE=604800

# Dead Letter Configuration
DEAD_LETTER_STREAM=ANUMATE_DEAD_LETTERS
MAX_DELIVER_ATTEMPTS=5

# API Configuration
API_HOST=0.0.0.0
API_PORT=8080
```

### Advanced Configuration

```python
from anumate_eventbus_service import EventBusConfig

config = EventBusConfig(
    nats_url="nats://nats1:4222,nats2:4222,nats3:4222",
    nats_cluster_id="anumate-production",
    redis_url="redis://redis-cluster:6379",
    stream_name="ANUMATE_EVENTS_PROD",
    max_msgs=10000000,
    max_bytes=10 * 1024 * 1024 * 1024,  # 10GB
    max_age=30 * 24 * 3600,  # 30 days
    dead_letter_stream="ANUMATE_DEAD_LETTERS_PROD",
    max_deliver_attempts=3
)

event_bus = EventBusService(config)
```

## Event Types

The service provides standardized CloudEvents for all Anumate platform operations:

### Capsule Registry Events
- `com.anumate.capsule.created`
- `com.anumate.capsule.updated` 
- `com.anumate.capsule.deleted`
- `com.anumate.capsule.published`

### Policy Events
- `com.anumate.policy.created`
- `com.anumate.policy.updated`
- `com.anumate.policy.violated`
- `com.anumate.policy.enforced`

### Execution Events
- `com.anumate.execution.started`
- `com.anumate.execution.completed`
- `com.anumate.execution.failed`
- `com.anumate.execution.paused`

### Approval Events
- `com.anumate.approval.requested`
- `com.anumate.approval.granted` 
- `com.anumate.approval.rejected`

### And many more...

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .
RUN pip install .

EXPOSE 8080
CMD ["uvicorn", "anumate_eventbus_service.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eventbus-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: eventbus-service
  template:
    metadata:
      labels:
        app: eventbus-service
    spec:
      containers:
      - name: eventbus-service
        image: anumate/eventbus-service:1.0.0
        ports:
        - containerPort: 8080
        env:
        - name: NATS_URL
          value: "nats://nats:4222"
        - name: REDIS_URL
          value: "redis://redis:6379"
```

## Monitoring

### Metrics

The service exposes comprehensive metrics via the `/metrics` endpoint:

- Event publishing rates and success/failure ratios
- Subscription processing rates and latencies  
- Dead letter queue sizes and trends
- Consumer lag and throughput
- NATS and Redis connection health

### Health Checks

Health checks are available at `/health`:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-20T10:30:00Z",
  "details": {
    "nats_connected": true,
    "redis_connected": true,
    "running": true
  }
}
```

### Logging

Structured logging with correlation IDs and trace context:

```json
{
  "timestamp": "2024-01-20T10:30:00Z",
  "level": "INFO",
  "message": "Published event",
  "event_id": "evt-123",
  "event_type": "com.anumate.capsule.created",
  "tenant_id": "tenant-456",
  "correlation_id": "req-789"
}
```

## Development

### Setup

```bash
git clone https://github.com/anumate/eventbus-service.git
cd eventbus-service

# Install development dependencies
pip install -e ".[dev]"

# Start dependencies
docker-compose up -d nats redis

# Run tests
pytest

# Run linting
black src tests
ruff src tests
mypy src
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=anumate_eventbus_service

# Run integration tests
pytest -m integration

# Run performance tests
pytest -m performance
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`) 
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- Documentation: https://anumate.github.io/eventbus-service
- Issues: https://github.com/anumate/eventbus-service/issues
- Discussions: https://github.com/anumate/eventbus-service/discussions
