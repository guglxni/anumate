# Shared Libraries and Utilities Implementation

This document describes the implementation of task A.3: "Create shared libraries and utilities" from the Anumate Platform MVP specification.

## Overview

The task required implementing:
- Tenant context middleware
- OpenTelemetry tracing utilities  
- Structured logging with correlation IDs
- Common authentication/authorization helpers

## Implementation Summary

### 1. Enhanced Tenant Context Middleware

**Location**: `packages/anumate-infrastructure/anumate_infrastructure/tenant_context.py`

**Features Implemented**:
- ✅ Context variables for tenant ID and correlation ID
- ✅ `TenantContext` context manager for scoped tenant operations
- ✅ `TenantMiddleware` FastAPI middleware for automatic tenant extraction
- ✅ `CorrelationMiddleware` FastAPI middleware for correlation ID management
- ✅ Support for extracting tenant ID from headers, JWT tokens, or URL paths

**Key Functions**:
```python
# Context management
get_current_tenant_id() -> Optional[UUID]
set_current_tenant_id(tenant_id: UUID) -> None
get_current_correlation_id() -> Optional[str]
set_current_correlation_id(correlation_id: str) -> None

# Context manager
with TenantContext(tenant_id):
    # Operations within tenant context
    pass

# Middleware classes
TenantMiddleware(app)
CorrelationMiddleware(app)
```

### 2. Enhanced OpenTelemetry Tracing Utilities

**Location**: `packages/anumate-tracing/anumate_tracing/__init__.py`

**Features Implemented**:
- ✅ Enhanced tracer initialization with service metadata
- ✅ Automatic tenant and correlation context injection into spans
- ✅ Custom span creation with context awareness
- ✅ FastAPI instrumentation with health check exclusions

**Key Functions**:
```python
# Tracer setup
initialize_tracer(service_name: str, service_version: str = "1.0.0")
get_tracer(service_name: str) -> trace.Tracer

# Context-aware tracing
add_tenant_context_to_span()
create_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> trace.Span
add_span_attributes(attributes: Dict[str, Any])

# FastAPI integration
add_tracing_middleware(app, service_name: str)
```

### 3. Enhanced Structured Logging with Correlation IDs

**Location**: `packages/anumate-logging/anumate_logging/__init__.py`

**Features Implemented**:
- ✅ Enhanced PII filtering with multiple pattern types (email, SSN, credit cards, phone numbers)
- ✅ Dynamic context injection (tenant ID, correlation ID, trace ID)
- ✅ Structured JSON logging with consistent format
- ✅ `StructuredLogger` class for context-aware logging

**Key Features**:
```python
# Logger setup
get_logger(name: str, tenant_id=None, plan_hash=None, run_id=None, level: int = logging.INFO)
configure_root_logger(level: int = logging.INFO)

# Structured logging
logger = StructuredLogger("service_name", extra_context={"key": "value"})
logger.info("Message", custom_field="value")

# PII Protection
# Automatically redacts: emails, SSNs, credit cards, phone numbers, UPIs
```

### 4. Common Authentication/Authorization Helpers

**Location**: `packages/anumate-infrastructure/anumate_infrastructure/auth_utils.py`
**Location**: `packages/anumate-oidc/anumate_oidc/__init__.py`

**Features Implemented**:
- ✅ Permission and role constants
- ✅ Authentication decorators
- ✅ Authorization decorators (roles and permissions)
- ✅ Tenant access control decorators
- ✅ Security utilities (API key validation, token extraction)
- ✅ Enhanced OIDC service with FastAPI integration
- ✅ User model with role/permission checking

**Key Components**:

#### Permission Constants
```python
class Permission:
    CAPSULE_READ = "capsule:read"
    CAPSULE_WRITE = "capsule:write"
    PLAN_EXECUTE = "plan:execute"
    TENANT_ADMIN = "tenant:admin"
    # ... and more
```

#### Role Constants
```python
class Role:
    TENANT_ADMIN = "tenant_admin"
    CAPSULE_AUTHOR = "capsule_author"
    PLAN_EXECUTOR = "plan_executor"
    # ... and more
```

#### Decorators
```python
@require_authentication
@require_roles([Role.CAPSULE_AUTHOR])
@require_permissions([Permission.CAPSULE_WRITE])
@require_tenant_access
async def create_capsule(request: Request):
    pass
```

#### OIDC Integration
```python
# Enhanced OIDC service
auth_service = AuthService(oidc_verifier)
user = await auth_service.get_current_user(credentials)

# User model with capabilities
user.has_role("tenant_admin")
user.has_permission("capsule:read")
```

## Usage Example

**Location**: `packages/anumate-infrastructure/examples/middleware_usage.py`

Complete FastAPI application example showing:
- Middleware setup in correct order
- Authentication and authorization decorators
- Structured logging with context
- OpenTelemetry tracing integration
- Security headers

```python
from fastapi import FastAPI
from anumate_infrastructure import TenantMiddleware, CorrelationMiddleware
from anumate_oidc import AuthService, AuthMiddleware
from anumate_logging import configure_root_logger
from anumate_tracing import initialize_tracer, add_tracing_middleware

app = FastAPI()

# Configure observability
configure_root_logger()
initialize_tracer("service-name")

# Add middleware
app.add_middleware(AuthMiddleware, auth_service=auth_service)
app.add_middleware(TenantMiddleware)
app.add_middleware(CorrelationMiddleware)
add_tracing_middleware(app, "service-name")

@app.get("/capsules")
@require_authentication
@require_permissions([Permission.CAPSULE_READ])
async def list_capsules(request: Request):
    # Automatic tenant context and correlation ID available
    # Structured logging with context
    # Distributed tracing with tenant/correlation context
    pass
```

## Security Features

### Multi-Tenant Isolation
- Automatic tenant context extraction from headers, JWT, or URL paths
- Tenant boundary enforcement in decorators
- Cross-tenant access prevention

### PII Protection
- Automatic PII redaction in logs (emails, SSNs, credit cards, phone numbers)
- Configurable redaction patterns
- Safe structured logging

### Authentication & Authorization
- JWT token validation with OIDC
- Role-based access control (RBAC)
- Permission-based access control
- Capability-based security model

### Security Headers
- Automatic security header injection
- CSRF protection headers
- Content security policy
- XSS protection

## Observability Features

### Distributed Tracing
- OpenTelemetry integration
- Automatic tenant and correlation context in spans
- Service-to-service trace propagation
- Performance monitoring

### Structured Logging
- JSON formatted logs
- Correlation ID tracking
- Tenant context in all logs
- PII-safe logging

### Metrics & Monitoring
- Request correlation tracking
- Error tracking with context
- Performance metrics
- Security event logging

## Testing

**Location**: `packages/anumate-infrastructure/tests/test_auth_utils.py`

Comprehensive test suite covering:
- Authentication decorator behavior
- Authorization enforcement
- Tenant access control
- Utility functions
- Error handling

## Requirements Satisfied

✅ **Tenant context middleware**: Implemented with automatic extraction and context management
✅ **OpenTelemetry tracing utilities**: Enhanced with tenant/correlation context injection  
✅ **Structured logging with correlation IDs**: JSON logging with PII protection and context
✅ **Common authentication/authorization helpers**: Complete RBAC system with decorators

## Dependencies Added

- `fastapi>=0.104.0` (for middleware and authentication)
- Enhanced existing packages with new functionality
- Maintained backward compatibility

## Next Steps

These shared utilities provide the foundation for:
1. **Service Implementation**: All core services can use these utilities
2. **Security Enforcement**: Consistent auth/authz across all services  
3. **Observability**: Unified logging, tracing, and monitoring
4. **Multi-Tenancy**: Proper tenant isolation and context management

The implementation satisfies all requirements from the task and provides a robust foundation for the Anumate platform's observability and security needs.