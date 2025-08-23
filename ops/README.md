# Anumate Infrastructure Operations

This directory contains the infrastructure setup and configuration for the Anumate platform.

## Quick Start

1. **Copy environment file:**
   ```bash
   cp .env.infrastructure.example .env.infrastructure
   ```

2. **Start infrastructure services:**
   ```bash
   ./ops/scripts/setup-infrastructure.sh
   ```

3. **Verify services are running:**
   ```bash
   docker-compose -f ops/docker-compose.infrastructure.yml ps
   ```

## Services

### PostgreSQL (Port 5432)
- **Purpose**: Multi-tenant database with Row Level Security (RLS)
- **Features**: 
  - Automatic tenant isolation via RLS policies
  - Audit logging schema
  - Events schema for event sourcing
- **Access**: `postgresql://anumate_app:app_password@localhost:5432/anumate`

### Redis (Port 6379)
- **Purpose**: Caching and rate limiting
- **Features**:
  - Tenant-aware key prefixing
  - Rate limiting with sliding windows
  - Session storage
- **Access**: `redis://localhost:6379`

### NATS JetStream (Port 4222, HTTP 8222)
- **Purpose**: Event bus with CloudEvents support
- **Features**:
  - Persistent messaging with JetStream
  - CloudEvents specification compliance
  - Multi-tenant event isolation
- **Access**: `nats://anumate_app:app_password@localhost:4222`
- **Monitoring**: http://localhost:8222

### HashiCorp Vault (Port 8200)
- **Purpose**: Secrets management and encryption
- **Features**:
  - Per-tenant encryption keys
  - KV secrets storage
  - Transit encryption engine
- **Access**: http://localhost:8200
- **Token**: `dev-root-token` (development only)

## Database Schema

### Multi-Tenant Tables
All tables include `tenant_id` for isolation:
- `tenants` - Tenant definitions
- `users` - User accounts per tenant
- `teams` - Team hierarchy per tenant
- `roles` - RBAC roles per tenant
- `capsules` - Automation definitions
- `plans` - Compiled execution plans
- `runs` - Plan execution records
- `approvals` - Workflow approvals
- `capability_tokens` - Short-lived access tokens
- `connectors` - External integrations

### RLS Policies
Row Level Security automatically filters data by tenant:
```sql
-- Example: Set tenant context
SET app.current_tenant_id = '123e4567-e89b-12d3-a456-426614174000';

-- All queries now automatically filtered by tenant
SELECT * FROM users; -- Only returns users for current tenant
```

## Event Streams

### JetStream Streams
- `CAPSULE_EVENTS` - Capsule lifecycle events
- `PLAN_EVENTS` - Plan compilation events  
- `EXECUTION_EVENTS` - Plan execution events
- `APPROVAL_EVENTS` - Approval workflow events
- `AUDIT_EVENTS` - Audit trail events (long retention)
- `SYSTEM_EVENTS` - System-level events
- `WEBHOOK_DELIVERY` - Outbound webhook queue

### CloudEvents Format
All events follow CloudEvents specification:
```json
{
  "specversion": "1.0",
  "type": "com.anumate.capsule.created",
  "source": "anumate-registry",
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "time": "2024-01-01T12:00:00Z",
  "tenantid": "tenant-uuid",
  "data": { ... }
}
```

## Secrets Management

### Vault Paths
- `secret/anumate/config/*` - Global application config
- `secret/tenants/{tenant-id}/*` - Per-tenant secrets
- `transit/keys/anumate-*` - Global encryption keys
- `transit/keys/tenant-*` - Per-tenant encryption keys

### Usage Example
```python
from anumate_infrastructure import SecretsManager, TenantContext

async with TenantContext(tenant_id):
    secrets = SecretsManager()
    
    # Get tenant-specific database config
    db_config = await secrets.get("database/config")
    
    # Encrypt sensitive data with tenant key
    encrypted = await secrets.encrypt("sensitive data")
```

## Development Commands

### Start Services
```bash
./ops/scripts/setup-infrastructure.sh
```

### Stop Services
```bash
docker-compose -f ops/docker-compose.infrastructure.yml down
```

### View Logs
```bash
docker-compose -f ops/docker-compose.infrastructure.yml logs -f [service]
```

### Reset Everything
```bash
docker-compose -f ops/docker-compose.infrastructure.yml down -v
./ops/scripts/setup-infrastructure.sh
```

### Database Operations
```bash
# Connect to database
docker-compose -f ops/docker-compose.infrastructure.yml exec postgres psql -U anumate_admin -d anumate

# Run migrations (when available)
# python -m alembic upgrade head
```

### Vault Operations
```bash
# Access Vault CLI
docker-compose -f ops/docker-compose.infrastructure.yml exec vault vault status

# Create tenant encryption key
vault write -f transit/keys/tenant-{tenant-id}

# Store tenant secret
vault kv put secret/tenants/{tenant-id}/config key=value
```

### NATS Operations
```bash
# List streams
nats --server=nats://anumate_app:app_password@localhost:4222 stream ls

# Publish test event
nats --server=nats://anumate_app:app_password@localhost:4222 pub events.test '{"message": "hello"}'

# Subscribe to events
nats --server=nats://anumate_app:app_password@localhost:4222 sub events.*
```

## Production Considerations

### Security
- Enable TLS for all services
- Use proper authentication tokens (not dev tokens)
- Configure network security groups
- Enable audit logging
- Rotate encryption keys regularly

### High Availability
- Deploy PostgreSQL in HA mode with streaming replication
- Use Redis Cluster for cache HA
- Deploy NATS in cluster mode
- Use Vault HA with Consul backend

### Monitoring
- Enable Prometheus metrics for all services
- Configure health checks and alerting
- Set up log aggregation
- Monitor SLO compliance

### Backup & Recovery
- Automated PostgreSQL backups with point-in-time recovery
- Vault backup and disaster recovery procedures
- NATS JetStream backup strategies
- Test recovery procedures regularly

## Troubleshooting

### Common Issues

**Database connection refused:**
```bash
# Check if PostgreSQL is running
docker-compose -f ops/docker-compose.infrastructure.yml ps postgres

# Check logs
docker-compose -f ops/docker-compose.infrastructure.yml logs postgres
```

**Vault sealed:**
```bash
# Check Vault status
curl http://localhost:8200/v1/sys/health

# Unseal if needed (development)
vault operator unseal
```

**NATS connection issues:**
```bash
# Check NATS health
curl http://localhost:8222/healthz

# Test connection
nats --server=nats://localhost:4222 rtt
```

**RLS not working:**
```sql
-- Verify tenant context is set
SELECT current_setting('app.current_tenant_id', true);

-- Check RLS policies
SELECT * FROM pg_policies WHERE tablename = 'users';
```