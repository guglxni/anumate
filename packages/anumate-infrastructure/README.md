# Anumate Infrastructure

Shared infrastructure utilities for the Anumate platform, providing multi-tenant database access with RLS, Redis caching, NATS event bus, and HashiCorp Vault secrets management.

## Features

- **PostgreSQL with RLS**: Multi-tenant database access with Row Level Security
- **Redis**: Caching and rate limiting utilities
- **NATS JetStream**: Event bus with CloudEvents support
- **HashiCorp Vault**: Secrets management and per-tenant encryption
- **Tenant Context**: Automatic tenant isolation across all services

## Usage

```python
from anumate_infrastructure import (
    DatabaseManager,
    RedisManager,
    EventBus,
    SecretsManager,
    TenantContext
)

# Set tenant context
async with TenantContext("tenant-uuid"):
    # Database operations are automatically tenant-isolated
    db = DatabaseManager()
    users = await db.fetch("SELECT * FROM users")
    
    # Redis operations with tenant prefixing
    cache = RedisManager()
    await cache.set("key", "value")
    
    # Publish events with tenant context
    events = EventBus()
    await events.publish("events.user.created", {"user_id": "123"})
    
    # Access tenant-specific secrets
    secrets = SecretsManager()
    db_config = await secrets.get("database/config")
```

## Configuration

Set environment variables:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/anumate

# Redis
REDIS_URL=redis://localhost:6379

# NATS
NATS_URL=nats://localhost:4222

# Vault
VAULT_ADDR=http://localhost:8200
VAULT_TOKEN=your-vault-token
```