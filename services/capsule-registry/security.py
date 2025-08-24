"""Security middleware for authentication, authorization, and tenancy."""

from typing import Optional, List, Dict, Any
from uuid import UUID
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.requests import Request

from anumate_oidc import OIDCValidator, TokenValidationResult
from anumate_tenancy import TenantContext, extract_tenant_context
from anumate_errors import AuthenticationError, AuthorizationError, ErrorCode


# RBAC Roles
class Role:
    VIEWER = "viewer"      # Read access
    EDITOR = "editor"      # Create, update, version operations
    ADMIN = "admin"        # All operations including hard delete


class Permission:
    READ_CAPSULES = "capsules:read"
    CREATE_CAPSULES = "capsules:create"
    UPDATE_CAPSULES = "capsules:update"
    DELETE_CAPSULES = "capsules:delete"
    PUBLISH_VERSIONS = "capsules:publish"
    LINT_CAPSULES = "capsules:lint"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[str, List[str]] = {
    Role.VIEWER: [
        Permission.READ_CAPSULES,
    ],
    Role.EDITOR: [
        Permission.READ_CAPSULES,
        Permission.CREATE_CAPSULES,
        Permission.UPDATE_CAPSULES,
        Permission.PUBLISH_VERSIONS,
        Permission.LINT_CAPSULES,
    ],
    Role.ADMIN: [
        Permission.READ_CAPSULES,
        Permission.CREATE_CAPSULES,
        Permission.UPDATE_CAPSULES,
        Permission.DELETE_CAPSULES,
        Permission.PUBLISH_VERSIONS,
        Permission.LINT_CAPSULES,
    ]
}


class SecurityContext:
    """Security context for authenticated requests."""
    
    def __init__(
        self,
        user_id: str,
        tenant_id: UUID,
        roles: List[str],
        permissions: List[str],
        token_claims: Dict[str, Any]
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.roles = roles
        self.permissions = permissions
        self.token_claims = token_claims
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission."""
        return permission in self.permissions
    
    def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return role in self.roles
    
    def has_any_role(self, roles: List[str]) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)


class CapsuleRegistrySecurity:
    """Security handler for Capsule Registry service."""
    
    def __init__(self, oidc_validator: OIDCValidator):
        self.oidc_validator = oidc_validator
        self.bearer_scheme = HTTPBearer(auto_error=False)
    
    async def authenticate_request(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = None
    ) -> SecurityContext:
        """
        Authenticate and authorize request.
        
        Args:
            request: FastAPI request object
            credentials: Bearer token credentials
            
        Returns:
            SecurityContext with user info and permissions
            
        Raises:
            HTTPException: For authentication/authorization failures
        """
        # Extract bearer token
        if not credentials or not credentials.credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Validate OIDC token
        try:
            validation_result = await self.oidc_validator.validate_token(credentials.credentials)
            
            if not validation_result.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Invalid token: {validation_result.error}",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Extract tenant context
        try:
            tenant_context = extract_tenant_context(request)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tenant context: {str(e)}"
            )
        
        # Extract user info from token claims
        claims = validation_result.claims
        user_id = claims.get('sub')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject claim"
            )
        
        # Extract roles from token claims (customize based on your OIDC setup)
        roles = self._extract_roles(claims, tenant_context.tenant_id)
        
        # Calculate permissions
        permissions = self._calculate_permissions(roles)
        
        return SecurityContext(
            user_id=user_id,
            tenant_id=tenant_context.tenant_id,
            roles=roles,
            permissions=permissions,
            token_claims=claims
        )
    
    def _extract_roles(self, claims: Dict[str, Any], tenant_id: UUID) -> List[str]:
        """Extract roles from OIDC token claims."""
        # Default implementation - customize based on your OIDC provider
        roles = []
        
        # Check for realm roles
        if 'realm_access' in claims and 'roles' in claims['realm_access']:
            realm_roles = claims['realm_access']['roles']
            # Map OIDC roles to service roles
            role_mapping = {
                'anumate-admin': Role.ADMIN,
                'anumate-editor': Role.EDITOR,
                'anumate-viewer': Role.VIEWER,
            }
            for realm_role in realm_roles:
                if realm_role in role_mapping:
                    roles.append(role_mapping[realm_role])
        
        # Check for resource access (tenant-specific roles)
        resource_access = claims.get('resource_access', {})
        tenant_resource = f"anumate-{tenant_id}"
        if tenant_resource in resource_access:
            tenant_roles = resource_access[tenant_resource].get('roles', [])
            for tenant_role in tenant_roles:
                if tenant_role in [Role.ADMIN, Role.EDITOR, Role.VIEWER]:
                    roles.append(tenant_role)
        
        # Default role if none specified
        if not roles:
            roles.append(Role.VIEWER)
        
        return list(set(roles))  # Remove duplicates
    
    def _calculate_permissions(self, roles: List[str]) -> List[str]:
        """Calculate permissions based on roles."""
        permissions = set()
        
        for role in roles:
            if role in ROLE_PERMISSIONS:
                permissions.update(ROLE_PERMISSIONS[role])
        
        return list(permissions)


# FastAPI dependency functions
def get_security_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    security_handler: CapsuleRegistrySecurity = Depends()
) -> SecurityContext:
    """FastAPI dependency to get security context."""
    import asyncio
    if asyncio.iscoroutine(security_handler.authenticate_request(request, credentials)):
        # For async handling
        return asyncio.run(security_handler.authenticate_request(request, credentials))
    else:
        return security_handler.authenticate_request(request, credentials)


def require_permission(permission: str):
    """Decorator factory for permission-based access control."""
    def permission_checker(security_context: SecurityContext = Depends(get_security_context)):
        if not security_context.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        return security_context
    
    return permission_checker


def require_role(role: str):
    """Decorator factory for role-based access control."""
    def role_checker(security_context: SecurityContext = Depends(get_security_context)):
        if not security_context.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {role}"
            )
        return security_context
    
    return role_checker


def require_any_role(roles: List[str]):
    """Decorator factory for multi-role access control."""
    def role_checker(security_context: SecurityContext = Depends(get_security_context)):
        if not security_context.has_any_role(roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles required: {', '.join(roles)}"
            )
        return security_context
    
    return role_checker


# Convenience dependency functions for common access patterns
def require_read_access():
    """Require read access to Capsules."""
    return require_permission(Permission.READ_CAPSULES)


def require_write_access():
    """Require write access to Capsules."""
    return require_permission(Permission.CREATE_CAPSULES)


def require_admin_access():
    """Require admin access (for hard delete operations)."""
    return require_role(Role.ADMIN)


# Utility functions
def create_security_handler(oidc_issuer: str, oidc_audience: str, jwks_url: Optional[str] = None) -> CapsuleRegistrySecurity:
    """Factory function to create security handler."""
    oidc_validator = OIDCValidator(
        issuer=oidc_issuer,
        audience=oidc_audience,
        jwks_url=jwks_url
    )
    return CapsuleRegistrySecurity(oidc_validator)


def get_actor_id(security_context: SecurityContext) -> str:
    """Get actor ID for audit logging."""
    return security_context.user_id


def get_tenant_id(security_context: SecurityContext) -> UUID:
    """Get tenant ID from security context."""
    return security_context.tenant_id
