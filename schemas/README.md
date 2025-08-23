# Shared Schemas Package

This package contains shared data models, API contracts, and validation schemas used across all Anumate services.

## Structure

- `openapi/` - OpenAPI specifications for all services
- `events/` - CloudEvents schemas and definitions
- `models/` - Shared Pydantic models
- `validation/` - JSON Schema validation files
- `proto/` - Protocol Buffer definitions (if needed)

## Usage

Services import shared schemas to ensure consistency across the platform:

```python
from schemas.models import Capsule, ExecutablePlan
from schemas.events import CapsuleCreatedEvent
```

## Versioning

Schemas are versioned to support backward compatibility during service updates.