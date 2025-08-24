"""
FastAPI Application for Capsule Registry

A.4–A.6 Implementation: Main application with dependency injection,
middleware, error handling, and endpoint implementations.
"""

import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any, Annotated

import uvicorn
from fastapi import FastAPI, Request, Response, Depends, Query, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, text

# Observability
from anumate_logging import configure_logging, get_logger
from anumate_tracing import configure_tracing
from prometheus_fastapi_instrumentator import Instrumentator

# Core imports
from anumate_core_config import get_config_value
from anumate_errors import (
    AnumateError, ValidationError, SecurityError, StorageError, 
    ConcurrencyError, TenantError, NotFoundError
)
from anumate_events import configure_events
from anumate_tenancy import TenantResolver, TenantContext

# Service components
from .settings import RegistrySettings
from .models import (
    Base, Capsule, CapsuleVersion, 
    CapsuleCreateRequest, CapsuleUpdateRequest, CapsuleVersionRequest,
    CapsuleResponse, CapsuleVersionResponse, CapsuleListResponse, ValidationResult,
    ErrorResponse, HealthResponse
)
from .security import SecurityContext, OIDCHandler, get_security_context
from .service import CapsuleService, create_capsule_service
from .repo import CapsuleRepository
from .signing import CapsuleSigner
from .worm_store import create_worm_store
from .events import CapsuleEventPublisher


# Configure logging first
configure_logging()
logger = get_logger(__name__)


# Global dependencies (initialized at startup)
settings: Optional[RegistrySettings] = None
db_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
capsule_service: Optional[CapsuleService] = None
oidc_handler: Optional[OIDCHandler] = None
tenant_resolver: Optional[TenantResolver] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    
    global settings, db_session_factory, capsule_service, oidc_handler, tenant_resolver
    
    logger.info("Starting Capsule Registry service")
    
    # Load configuration
    settings = RegistrySettings()
    logger.info(f"Loaded configuration: {settings.service_name}")
    
    # Configure observability
    configure_tracing(settings.service_name)
    configure_events(settings.events)
    
    # Initialize database
    engine = create_async_engine(
        settings.database.url,
        echo=settings.database.echo,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_recycle=3600
    )
    
    db_session_factory = async_sessionmaker(
        engine, 
        class_=AsyncSession, 
        expire_on_commit=False
    )
    
    # Create tables (in production, use Alembic migrations)
    if settings.database.auto_migrate:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/updated")
    
    # Initialize OIDC
    oidc_handler = OIDCHandler(settings.oidc)
    
    # Initialize tenant resolver
    tenant_resolver = TenantResolver()
    
    # Initialize WORM storage
    worm_store = await create_worm_store(settings.worm)
    
    # Initialize signer
    signer = CapsuleSigner(settings.signing)
    
    # Initialize event publisher
    event_publisher = CapsuleEventPublisher(settings.events)
    
    # Initialize repository
    repo = CapsuleRepository(db_session_factory)
    
    # Initialize service
    capsule_service = create_capsule_service(
        settings, repo, signer, worm_store, event_publisher
    )
    
    logger.info("Capsule Registry service started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Capsule Registry service")
    if engine:
        await engine.dispose()


# Create FastAPI application
app = FastAPI(
    title="Capsule Registry",
    description="Production-grade registry for capsule definitions with WORM storage and multi-tenant support",
    version="1.0.0",
    lifespan=lifespan,
    openapi_url="/openapi.json" if get_config_value("REGISTRY_DEV_MODE", False) else None
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Prometheus instrumentation
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)


# Dependency providers
async def get_db_session() -> AsyncSession:
    """Provide database session."""
    if not db_session_factory:
        raise HTTPException(status_code=503, detail="Database not available")
    
    async with db_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_tenant_context(
    x_tenant_id: Annotated[str, Header(alias="x-tenant-id")]
) -> TenantContext:
    """Extract and validate tenant context."""
    if not tenant_resolver:
        raise HTTPException(status_code=503, detail="Tenant resolver not available")
    
    try:
        tenant_uuid = uuid.UUID(x_tenant_id)
        return await tenant_resolver.resolve_tenant(tenant_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    except TenantError as e:
        raise HTTPException(status_code=403, detail=str(e))


async def get_auth_context(
    request: Request,
    tenant_ctx: TenantContext = Depends(get_tenant_context)
) -> SecurityContext:
    """Extract and validate security context."""
    if not oidc_handler:
        raise HTTPException(status_code=503, detail="OIDC handler not available")
    
    # Extract bearer token
    authorization = request.headers.get("authorization")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, 
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        return await get_security_context(oidc_handler, token, tenant_ctx)
    except SecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))


def get_trace_id(request: Request) -> Optional[str]:
    """Extract trace ID from headers."""
    return request.headers.get("x-trace-id")


# Error handlers
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            type="https://docs.anumate.io/errors/validation",
            title="Validation Error",
            detail=str(exc),
            status=400,
            instance=str(request.url)
        ).model_dump()
    )


@app.exception_handler(SecurityError)
async def security_error_handler(request: Request, exc: SecurityError):
    """Handle security errors."""
    return JSONResponse(
        status_code=403,
        content=ErrorResponse(
            type="https://docs.anumate.io/errors/security",
            title="Security Error", 
            detail=str(exc),
            status=403,
            instance=str(request.url)
        ).model_dump()
    )


@app.exception_handler(NotFoundError)
async def not_found_error_handler(request: Request, exc: NotFoundError):
    """Handle not found errors."""
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            type="https://docs.anumate.io/errors/not-found",
            title="Not Found",
            detail=str(exc),
            status=404,
            instance=str(request.url)
        ).model_dump()
    )


@app.exception_handler(ConcurrencyError)
async def concurrency_error_handler(request: Request, exc: ConcurrencyError):
    """Handle concurrency errors."""
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(
            type="https://docs.anumate.io/errors/concurrency",
            title="Concurrency Error",
            detail=str(exc),
            status=409,
            instance=str(request.url)
        ).model_dump()
    )


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError):
    """Handle storage errors."""
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            type="https://docs.anumate.io/errors/storage",
            title="Storage Error",
            detail="Internal storage error occurred",  # Don't expose internal details
            status=500,
            instance=str(request.url)
        ).model_dump()
    )


# Health and readiness endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Basic health check."""
    if not capsule_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    health_data = await capsule_service.health_check()
    return HealthResponse(**health_data)


@app.get("/ready", tags=["Health"])
async def readiness_check(db: AsyncSession = Depends(get_db_session)):
    """Readiness check with database connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


# Capsule endpoints
@app.post("/v1/capsules", response_model=CapsuleResponse, status_code=201, tags=["Capsules"])
async def create_capsule(
    request: CapsuleCreateRequest,
    security_ctx: SecurityContext = Depends(get_auth_context),
    trace_id: Optional[str] = Depends(get_trace_id),
    idempotency_key: Optional[str] = Header(None, alias="idempotency-key")
):
    """Create new capsule."""
    
    capsule = await capsule_service.create_capsule(
        security_ctx, request, trace_id, idempotency_key
    )
    return CapsuleResponse.from_model(capsule)


@app.get("/v1/capsules", response_model=CapsuleListResponse, tags=["Capsules"])
async def list_capsules(
    security_ctx: SecurityContext = Depends(get_auth_context),
    q: Optional[str] = Query(None, description="Search query"),
    status: Optional[str] = Query(None, description="Filter by status"),
    tool: Optional[str] = Query(None, description="Filter by tool"),
    updated_since: Optional[datetime] = Query(None, description="Filter by update time"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size")
):
    """List capsules with filtering and pagination."""
    
    # Convert status string to enum if provided
    status_enum = None
    if status:
        try:
            from .models import CapsuleStatus
            status_enum = CapsuleStatus(status)
        except ValueError:
            raise ValidationError(f"Invalid status: {status}")
    
    capsules, total = await capsule_service.list_capsules(
        security_ctx, q, status_enum, tool, updated_since, page, page_size
    )
    
    return CapsuleListResponse(
        data=[CapsuleResponse.from_model(c) for c in capsules],
        pagination={
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    )


@app.get("/v1/capsules/{capsule_id}", response_model=CapsuleResponse, tags=["Capsules"])
async def get_capsule(
    capsule_id: uuid.UUID,
    security_ctx: SecurityContext = Depends(get_auth_context)
):
    """Get capsule by ID."""
    
    capsule = await capsule_service.get_capsule(security_ctx, capsule_id)
    if not capsule:
        raise NotFoundError(f"Capsule not found: {capsule_id}")
    
    return CapsuleResponse.from_model(capsule)


@app.patch("/v1/capsules/{capsule_id}", response_model=CapsuleResponse, tags=["Capsules"])
async def update_capsule(
    capsule_id: uuid.UUID,
    request: CapsuleUpdateRequest,
    security_ctx: SecurityContext = Depends(get_auth_context),
    if_match: str = Header(..., alias="if-match"),
    trace_id: Optional[str] = Depends(get_trace_id)
):
    """Update capsule status."""
    
    capsule = await capsule_service.update_capsule_status(
        security_ctx, capsule_id, request, if_match, trace_id
    )
    return CapsuleResponse.from_model(capsule)


@app.delete("/v1/capsules/{capsule_id}", status_code=204, tags=["Capsules"])
async def delete_capsule(
    capsule_id: uuid.UUID,
    security_ctx: SecurityContext = Depends(get_auth_context),
    trace_id: Optional[str] = Depends(get_trace_id)
):
    """Hard delete capsule (admin only)."""
    
    # Check admin permissions
    if not security_ctx.has_admin_role():
        raise SecurityError("Admin role required for hard deletion")
    
    await capsule_service.delete_capsule(security_ctx, capsule_id, trace_id)


# Version endpoints
@app.post("/v1/capsules/{capsule_id}/versions", 
         response_model=CapsuleVersionResponse, 
         status_code=201, tags=["Versions"])
async def publish_version(
    capsule_id: uuid.UUID,
    request: CapsuleVersionRequest,
    security_ctx: SecurityContext = Depends(get_auth_context),
    trace_id: Optional[str] = Depends(get_trace_id),
    idempotency_key: Optional[str] = Header(None, alias="idempotency-key")
):
    """Publish new capsule version."""
    
    version = await capsule_service.publish_version(
        security_ctx, capsule_id, request, trace_id, idempotency_key
    )
    
    if not version:  # lint-only mode
        return Response(status_code=204)
    
    return CapsuleVersionResponse.from_model(version)


@app.get("/v1/capsules/{capsule_id}/versions", 
         response_model=List[CapsuleVersionResponse], tags=["Versions"])
async def list_versions(
    capsule_id: uuid.UUID,
    security_ctx: SecurityContext = Depends(get_auth_context)
):
    """List all versions for a capsule."""
    
    versions = await capsule_service.list_versions(security_ctx, capsule_id)
    return [CapsuleVersionResponse.from_model(v) for v in versions]


@app.get("/v1/capsules/{capsule_id}/versions/{version_number}",
         response_model=CapsuleVersionResponse, tags=["Versions"])
async def get_version(
    capsule_id: uuid.UUID,
    version_number: int,
    security_ctx: SecurityContext = Depends(get_auth_context)
):
    """Get specific version by number."""
    
    version = await capsule_service.get_version(security_ctx, capsule_id, version_number)
    if not version:
        raise NotFoundError(f"Version not found: {capsule_id}/v{version_number}")
    
    return CapsuleVersionResponse.from_model(version)


@app.get("/v1/capsules/{capsule_id}/versions/{version_number}/content", 
         response_class=Response, tags=["Versions"])
async def get_version_content(
    capsule_id: uuid.UUID,
    version_number: int,
    security_ctx: SecurityContext = Depends(get_auth_context)
):
    """Get version YAML content."""
    
    result = await capsule_service.get_version_content(
        security_ctx, capsule_id, version_number
    )
    if not result:
        raise NotFoundError(f"Version content not found: {capsule_id}/v{version_number}")
    
    version, yaml_content = result
    
    return Response(
        content=yaml_content,
        media_type="application/x-yaml",
        headers={
            "etag": f'"{version.id}"',
            "x-content-hash": version.content_hash,
            "x-signature": version.signature,
            "x-pubkey-id": version.pubkey_id
        }
    )


# Validation endpoints
@app.post("/v1/lint", response_model=ValidationResult, tags=["Validation"])
async def lint_content(
    request: CapsuleVersionRequest,
    security_ctx: SecurityContext = Depends(get_auth_context)
):
    """Validate capsule YAML content without storing."""
    
    validation_result = await capsule_service.validate_content(
        security_ctx, request.yaml_content
    )
    return validation_result


# Development/debug endpoints (only in dev mode)
if get_config_value("REGISTRY_DEV_MODE", False):
    @app.get("/debug/metrics", tags=["Debug"])
    async def get_metrics():
        """Get service metrics (dev only)."""
        return {"metrics": "placeholder"}


def create_app() -> FastAPI:
    """Factory function to create configured FastAPI app."""
    return app


if __name__ == "__main__":
    # Development server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_config=None  # Use our logging configuration
    )
