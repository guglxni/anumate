# Anumate Events

This package provides CloudEvents models and event bus interfaces for the Anumate platform.

## Usage

To use this package, you can create and publish events using an event bus implementation:

```python
from anumate_events import InMemoryEventBus, PlanCreated

event_bus = InMemoryEventBus()

def my_handler(event):
    print(f"Received event: {event}")

event_bus.subscribe("PlanCreated", my_handler)

event = PlanCreated(plan_hash="my-hash", tenant_id="my-tenant")
event_bus.publish(event)
```

The package provides an in-memory event bus for testing purposes. For production use, you would use a NATS-based implementation.
