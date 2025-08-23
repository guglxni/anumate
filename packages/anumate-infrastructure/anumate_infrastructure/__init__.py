"""Anumate infrastructure utilities."""

from .database import DatabaseManager
from .redis_manager import RedisManager
from .event_bus import EventBus
from .secrets import SecretsManager
from .tenant_context import (
    TenantContext, 
    get_current_tenant_id, 
    get_current_correlation_id,
    set_current_tenant_id,
    set_current_correlation_id,
    TenantMiddleware,
    CorrelationMiddleware
)
from .auth_utils import (
    Permission,
    Role,
    require_authentication,
    require_roles,
    require_permissions,
    require_tenant_access,
    SecurityHeaders,
    get_user_from_request,
    validate_api_key,
    extract_bearer_token,
    create_error_response
)

# Setup functions for compatibility
async def setup_database():
    """Setup database connection."""
    return DatabaseManager()

async def setup_redis():
    """Setup Redis connection."""
    return RedisManager()

async def setup_event_bus():
    """Setup event bus."""
    return EventBus()

__all__ = [
    "DatabaseManager",
    "RedisManager", 
    "EventBus",
    "SecretsManager",
    "TenantContext",
    "get_current_tenant_id",
    "get_current_correlation_id",
    "set_current_tenant_id", 
    "set_current_correlation_id",
    "TenantMiddleware",
    "CorrelationMiddleware",
    "Permission",
    "Role",
    "require_authentication",
    "require_roles",
    "require_permissions",
    "require_tenant_access",
    "SecurityHeaders",
    "get_user_from_request",
    "validate_api_key",
    "extract_bearer_token",
    "create_error_response",
    "setup_database",
    "setup_redis", 
    "setup_event_bus",
]