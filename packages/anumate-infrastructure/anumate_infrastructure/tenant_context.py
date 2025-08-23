"""Tenant context management for multi-tenant operations."""

import contextvars
from typing import Optional, Callable, Awaitable
from uuid import UUID
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse

# Context variable to store current tenant ID
_tenant_context: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "tenant_id", default=None
)

# Context variable to store correlation ID
_correlation_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)

# Context variable to store current user ID
_user_context: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "user_id", default=None
)

logger = logging.getLogger(__name__)


def get_current_tenant_id() -> Optional[UUID]:
    """Get the current tenant ID from context."""
    return _tenant_context.get()


def set_current_tenant_id(tenant_id: UUID) -> None:
    """Set the current tenant ID in context."""
    _tenant_context.set(tenant_id)


def get_current_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context."""
    return _correlation_context.get()


def set_current_correlation_id(correlation_id: str) -> None:
    """Set the current correlation ID in context."""
    _correlation_context.set(correlation_id)


def get_current_user_id() -> Optional[UUID]:
    """Get the current user ID from context."""
    return _user_context.get()


def set_current_user_id(user_id: UUID) -> None:
    """Set the current user ID in context."""
    _user_context.set(user_id)


class TenantContext:
    """Context manager for setting tenant context."""
    
    def __init__(self, tenant_id: UUID) -> None:
        """Initialize with tenant ID."""
        self.tenant_id = tenant_id
        self.token: Optional[contextvars.Token] = None
    
    def __enter__(self) -> "TenantContext":
        """Enter the context and set tenant ID."""
        self.token = _tenant_context.set(self.tenant_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context and reset tenant ID."""
        if self.token is not None:
            _tenant_context.reset(self.token)
    
    async def __aenter__(self) -> "TenantContext":
        """Async context manager entry."""
        return self.__enter__()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        self.__exit__(exc_type, exc_val, exc_tb)


class TenantMiddleware:
    """FastAPI middleware for tenant context management."""
    
    def __init__(self, app) -> None:
        self.app = app
    
    async def __call__(self, scope, receive, send):
        """Process request and set tenant context."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
            
        # For demo purposes, skip tenant validation
        # In production, this would extract tenant from headers/JWT
        await self.app(scope, receive, send)
    
    async def _extract_tenant_id(self, request: Request) -> Optional[UUID]:
        """Extract tenant ID from request headers, JWT token, or path."""
        # Try X-Tenant-ID header first
        tenant_header = request.headers.get("X-Tenant-ID")
        if tenant_header:
            try:
                return UUID(tenant_header)
            except ValueError:
                logger.warning(f"Invalid tenant ID in header: {tenant_header}")
        
        # Try to extract from JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                # This would need JWT decoding - simplified for now
                # In real implementation, decode JWT and extract tenant_id claim
                pass
            except Exception:
                logger.warning("Failed to extract tenant from JWT")
        
        # Try to extract from path (e.g., /tenants/{tenant_id}/...)
        path_parts = request.url.path.strip("/").split("/")
        if len(path_parts) >= 2 and path_parts[0] == "tenants":
            try:
                return UUID(path_parts[1])
            except ValueError:
                logger.warning(f"Invalid tenant ID in path: {path_parts[1]}")
        
        return None


class CorrelationMiddleware:
    """FastAPI middleware for correlation ID management."""
    
    def __init__(self, app: Callable[[Request], Awaitable[Response]]) -> None:
        self.app = app
    
    async def __call__(self, request: Request) -> Response:
        """Process request and set correlation ID."""
        import uuid
        
        # Get correlation ID from header or generate new one
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        
        # Set correlation context
        set_current_correlation_id(correlation_id)
        
        try:
            response = await self.app(request)
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        except Exception as e:
            logger.error(f"Error processing request: {e}", extra={
                "correlation_id": correlation_id,
                "path": request.url.path,
                "method": request.method
            })
            raise