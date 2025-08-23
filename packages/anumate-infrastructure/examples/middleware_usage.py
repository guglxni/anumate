"""Example usage of Anumate shared utilities and middleware."""

from fastapi import FastAPI, Request, Depends
from anumate_infrastructure import (
    TenantMiddleware,
    CorrelationMiddleware,
    require_authentication,
    require_roles,
    require_permissions,
    Permission,
    Role,
    SecurityHeaders
)
from anumate_oidc import AuthService, OIDCVerifier, AuthMiddleware
from anumate_logging import get_logger, configure_root_logger
from anumate_tracing import initialize_tracer, add_tracing_middleware

# Configure logging
configure_root_logger()
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Anumate Service Example")

# Initialize tracing
initialize_tracer("example-service", "1.0.0")

# Set up authentication
oidc_verifier = OIDCVerifier(
    issuer="https://your-oidc-provider.com",
    audience="anumate-api"
)
auth_service = AuthService(oidc_verifier)

# Add middleware in correct order (last added = first executed)
app.add_middleware(
    AuthMiddleware,
    auth_service=auth_service,
    excluded_paths=["/health", "/metrics", "/docs", "/openapi.json"]
)
app.add_middleware(TenantMiddleware)
app.add_middleware(CorrelationMiddleware)

# Add tracing middleware
add_tracing_middleware(app, "example-service")


@app.get("/health")
async def health_check():
    """Health check endpoint (no auth required)."""
    return {"status": "healthy"}


@app.get("/capsules")
@require_authentication
@require_permissions([Permission.CAPSULE_READ])
async def list_capsules(request: Request):
    """List capsules - requires authentication and capsule read permission."""
    logger.info("Listing capsules")
    
    # The middleware has already set tenant context and user in request.state
    user = request.state.user
    logger.info(f"User {user.user_id} listing capsules for tenant {user.tenant_id}")
    
    return {"capsules": []}


@app.post("/capsules")
@require_authentication
@require_roles([Role.CAPSULE_AUTHOR])
async def create_capsule(request: Request):
    """Create capsule - requires authentication and capsule author role."""
    logger.info("Creating capsule")
    
    user = request.state.user
    logger.info(f"User {user.user_id} creating capsule for tenant {user.tenant_id}")
    
    return {"message": "Capsule created"}


@app.get("/admin/users")
@require_authentication
@require_roles([Role.TENANT_ADMIN])
async def list_users(request: Request):
    """List users - requires tenant admin role."""
    logger.info("Listing users (admin endpoint)")
    
    user = request.state.user
    logger.info(f"Admin {user.user_id} listing users for tenant {user.tenant_id}")
    
    return {"users": []}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)
    return SecurityHeaders.add_security_headers(response)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)