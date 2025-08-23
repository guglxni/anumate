"""Authentication and authorization utilities."""

from typing import Optional, List, Dict, Any, Callable
from uuid import UUID
import logging
from functools import wraps

from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)


class Permission:
    """Permission constants."""
    
    # Capsule permissions
    CAPSULE_READ = "capsule:read"
    CAPSULE_WRITE = "capsule:write"
    CAPSULE_DELETE = "capsule:delete"
    CAPSULE_EXECUTE = "capsule:execute"
    
    # Plan permissions
    PLAN_READ = "plan:read"
    PLAN_COMPILE = "plan:compile"
    PLAN_EXECUTE = "plan:execute"
    
    # Approval permissions
    APPROVAL_READ = "approval:read"
    APPROVAL_APPROVE = "approval:approve"
    APPROVAL_DELEGATE = "approval:delegate"
    
    # Admin permissions
    TENANT_ADMIN = "tenant:admin"
    USER_ADMIN = "user:admin"
    CONNECTOR_ADMIN = "connector:admin"
    
    # Audit permissions
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"


class Role:
    """Role constants."""
    
    TENANT_ADMIN = "tenant_admin"
    CAPSULE_AUTHOR = "capsule_author"
    PLAN_EXECUTOR = "plan_executor"
    APPROVER = "approver"
    AUDITOR = "auditor"
    VIEWER = "viewer"


def get_user_from_request(request: Request) -> Optional[Any]:
    """Extract user from request state."""
    return getattr(request.state, 'user', None)


def require_authentication(func: Callable) -> Callable:
    """Decorator to require authentication."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Look for request in args/kwargs
        request = None
        for arg in args:
            if hasattr(arg, 'state'):  # FastAPI Request object
                request = arg
                break
        
        if not request:
            for value in kwargs.values():
                if hasattr(value, 'state'):
                    request = value
                    break
        
        if not request:
            raise HTTPException(status_code=500, detail="Request object not found")
        
        user = get_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        return await func(*args, **kwargs)
    
    return wrapper


def require_roles(required_roles: List[str]) -> Callable:
    """Decorator to require specific roles."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Look for request in args/kwargs
            request = None
            for arg in args:
                if hasattr(arg, 'state'):
                    request = arg
                    break
            
            if not request:
                for value in kwargs.values():
                    if hasattr(value, 'state'):
                        request = value
                        break
            
            if not request:
                raise HTTPException(status_code=500, detail="Request object not found")
            
            user = get_user_from_request(request)
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            if not hasattr(user, 'has_any_role') or not user.has_any_role(required_roles):
                logger.warning(f"User {getattr(user, 'user_id', 'unknown')} lacks required roles: {required_roles}")
                raise HTTPException(status_code=403, detail="Insufficient permissions")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_permissions(required_permissions: List[str]) -> Callable:
    """Decorator to require specific permissions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Look for request in args/kwargs
            request = None
            for arg in args:
                if hasattr(arg, 'state'):
                    request = arg
                    break
            
            if not request:
                for value in kwargs.values():
                    if hasattr(value, 'state'):
                        request = value
                        break
            
            if not request:
                raise HTTPException(status_code=500, detail="Request object not found")
            
            user = get_user_from_request(request)
            if not user:
                raise HTTPException(status_code=401, detail="Authentication required")
            
            # Check if user has all required permissions
            if hasattr(user, 'has_permission'):
                missing_permissions = [perm for perm in required_permissions if not user.has_permission(perm)]
                if missing_permissions:
                    logger.warning(f"User {getattr(user, 'user_id', 'unknown')} lacks permissions: {missing_permissions}")
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
            else:
                logger.warning("User object does not support permission checking")
                raise HTTPException(status_code=403, detail="Permission system unavailable")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_tenant_access(func: Callable) -> Callable:
    """Decorator to ensure user can only access their tenant's resources."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Look for request in args/kwargs
        request = None
        for arg in args:
            if hasattr(arg, 'state'):
                request = arg
                break
        
        if not request:
            for value in kwargs.values():
                if hasattr(value, 'state'):
                    request = value
                    break
        
        if not request:
            raise HTTPException(status_code=500, detail="Request object not found")
        
        user = get_user_from_request(request)
        if not user:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Extract tenant_id from path parameters
        path_params = getattr(request, 'path_params', {})
        resource_tenant_id = path_params.get('tenant_id')
        
        if resource_tenant_id:
            try:
                resource_tenant_uuid = UUID(resource_tenant_id)
                user_tenant_uuid = getattr(user, 'tenant_id', None)
                
                if user_tenant_uuid != resource_tenant_uuid:
                    logger.warning(f"User {getattr(user, 'user_id', 'unknown')} attempted cross-tenant access")
                    raise HTTPException(status_code=403, detail="Cross-tenant access denied")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid tenant ID format")
        
        return await func(*args, **kwargs)
    
    return wrapper


class SecurityHeaders:
    """Security headers middleware."""
    
    @staticmethod
    def add_security_headers(response):
        """Add security headers to response."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


def validate_api_key(api_key: str, valid_keys: List[str]) -> bool:
    """Validate API key against list of valid keys."""
    return api_key in valid_keys


def extract_bearer_token(authorization: str) -> Optional[str]:
    """Extract bearer token from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.split(" ", 1)[1]


def create_error_response(status_code: int, error_code: str, message: str, correlation_id: Optional[str] = None) -> Dict[str, Any]:
    """Create standardized error response."""
    error_response = {
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": "2025-01-20T00:00:00Z"  # Would use actual timestamp
        }
    }
    
    if correlation_id:
        error_response["error"]["correlation_id"] = correlation_id
    
    return error_response