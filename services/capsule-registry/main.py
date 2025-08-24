"""Capsule Registry service FastAPI application."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Annotated
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Header, Query, Path
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from prometheus_fastapi_instrumentator import Instrumentator

from anumate_core_config import Settings
from anumate_tracing import setup_tracing, get_tracer
from anumate_logging import setup_logging, get_logger
from anumate_events import EventPublisher
from anumate_errors import ErrorCode, AnumateError, NotFoundError, ValidationError, ConflictError
from anumate_oidc import OIDCProvider
from anumate_redaction import RedactionProvider
from anumate_idempotency import IdempotencyProvider

from .settings import CapsuleRegistrySettings
from .models import CapsuleStatus, CapsuleVisibility, init_database
from .repo import CapsuleRepository
from .service import CapsuleRegistryService
from .validation import CapsuleValidator
from .signing import CapsuleSigningProvider
from .worm_store import WormStorageProvider
from .events import CapsuleEventPublisher
from .security import get_security_context, SecurityContext

# Pydantic models for API requests/responses
class CreateCapsuleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    capsule_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    tags: List[str] = Field(default_factory=list, max_length=50)
    owner: str = Field(..., min_length=1, max_length=255)
    visibility: CapsuleVisibility = CapsuleVisibility.ORG
    yaml: str = Field(..., min_length=1)

class PublishVersionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    
    yaml: str = Field(..., min_length=1)
    message: Optional[str] = Field(None, max_length=500)

class UpdateStatusRequest(BaseModel):
    status: CapsuleStatus

class LintRequest(BaseModel):
    yaml: str = Field(..., min_length=1)

class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details format."""
    type: str = Field(..., description="A URI reference that identifies the problem type")
    title: str = Field(..., description="A short, human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: Optional[str] = Field(None, description="Human-readable explanation")
    instance: Optional[str] = Field(None, description="URI reference for this occurrence")
    trace_id: Optional[str] = Field(None, description="Distributed trace ID")

# Global dependencies
logger = get_logger(__name__)
tracer = get_tracer(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting Capsule Registry service")
    
    # Initialize database
    settings = app.state.settings
    await init_database(settings.database_url)
    
    # Warm up connections
    async with app.state.db_engine.begin() as conn:
        await conn.execute("SELECT 1")
    
    logger.info("Capsule Registry service started")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Capsule Registry service")
    if hasattr(app.state, 'db_engine'):
        await app.state.db_engine.dispose()
    
    if hasattr(app.state, 'event_publisher'):
        await app.state.event_publisher.close()


def create_app(settings: Optional[CapsuleRegistrySettings] = None) -> FastAPI:
    """Create and configure FastAPI application."""
    if settings is None:
        settings = CapsuleRegistrySettings()
    
    app = FastAPI(
        title="Capsule Registry",
        description="Anumate Capsule Registry Service - Secure storage and versioning for execution Capsules",
        version="1.0.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    # Store settings
    app.state.settings = settings
    
    # Setup CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Setup metrics
    if settings.metrics_enabled:
        instrumentator = Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            should_instrument_requests_inprogress=True,
            excluded_handlers=["/health", "/metrics"],
        )
        instrumentator.instrument(app).expose(app)
    
    # Initialize services
    _initialize_services(app, settings)
    
    # Setup routes
    _setup_routes(app)
    
    # Exception handlers
    _setup_exception_handlers(app)
    
    return app


def _initialize_services(app: FastAPI, settings: CapsuleRegistrySettings):
    """Initialize all service dependencies."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    # Database
    app.state.db_engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=settings.debug
    )
    app.state.db_session_factory = sessionmaker(
        bind=app.state.db_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # OIDC Provider
    if settings.oidc_enabled:
        app.state.oidc_provider = OIDCProvider(
            issuer_url=settings.oidc_issuer_url,
            client_id=settings.oidc_client_id,
            audience=settings.oidc_audience
        )
    else:
        app.state.oidc_provider = None
    
    # Event Publisher
    if settings.events_enabled:
        app.state.event_publisher = EventPublisher(
            nats_url=settings.events_nats_url
        )
    else:
        app.state.event_publisher = None
    
    # Redaction Provider
    if settings.redaction_enabled:
        app.state.redaction_provider = RedactionProvider()
    else:
        app.state.redaction_provider = None
    
    # Core services
    app.state.repository = CapsuleRepository()
    app.state.validator = CapsuleValidator()
    app.state.signing_provider = CapsuleSigningProvider(
        private_key_pem=settings.signing_private_key,
        public_key_pem=settings.signing_public_key
    )
    app.state.worm_storage = WormStorageProvider(settings.worm_storage_path)
    app.state.capsule_event_publisher = CapsuleEventPublisher(app.state.event_publisher)
    
    # Main service
    app.state.service = CapsuleRegistryService(
        repository=app.state.repository,
        validator=app.state.validator,
        signing_provider=app.state.signing_provider,
        worm_storage=app.state.worm_storage,
        event_publisher=app.state.capsule_event_publisher,
        redaction_provider=app.state.redaction_provider,
        max_capsule_size=settings.max_capsule_size_bytes,
        max_versions_per_capsule=settings.max_versions_per_capsule
    )


def _setup_routes(app: FastAPI):
    """Setup all API routes."""
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "capsule-registry"}
    
    @app.post("/api/v1/capsules", status_code=201)
    async def create_capsule(
        request: CreateCapsuleRequest,
        x_idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Create new Capsule."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.create_capsule(
            security_context=security_context,
            capsule_id=request.capsule_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            owner=request.owner,
            visibility=request.visibility,
            yaml_content=request.yaml,
            idempotency_key=x_idempotency_key
        )
        
        return result
    
    @app.post("/api/v1/capsules/{capsule_id}/versions", status_code=201)
    async def publish_version(
        request: PublishVersionRequest,
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        x_idempotency_key: Annotated[str, Header(alias="X-Idempotency-Key")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Publish new Capsule version."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.publish_version(
            security_context=security_context,
            capsule_id=capsule_id,
            yaml_content=request.yaml,
            message=request.message,
            idempotency_key=x_idempotency_key
        )
        
        return result
    
    @app.get("/api/v1/capsules/{capsule_id}")
    async def get_capsule(
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Get Capsule metadata."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.get_capsule(security_context, capsule_id)
        return result
    
    @app.get("/api/v1/capsules")
    async def list_capsules(
        security_context: SecurityContext = Depends(get_security_context),
        q: Annotated[Optional[str], Query(description="Search query")] = None,
        status: Annotated[Optional[CapsuleStatus], Query(description="Filter by status")] = None,
        tool: Annotated[Optional[str], Query(description="Filter by tool")] = None,
        updated_since: Annotated[Optional[str], Query(description="Filter by update time (ISO format)")] = None,
        page: Annotated[int, Query(description="Page number", ge=1)] = 1,
        page_size: Annotated[int, Query(description="Items per page", ge=1, le=100)] = 20
    ):
        """List Capsules with filtering and pagination."""
        service: CapsuleRegistryService = app.state.service
        
        # Parse updated_since if provided
        updated_since_dt = None
        if updated_since:
            from datetime import datetime
            try:
                updated_since_dt = datetime.fromisoformat(updated_since.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid updated_since format. Use ISO 8601 format."
                )
        
        result = await service.list_capsules(
            security_context=security_context,
            query=q,
            status=status,
            tool=tool,
            updated_since=updated_since_dt,
            page=page,
            page_size=page_size
        )
        
        return result
    
    @app.get("/api/v1/capsules/{capsule_id}/versions")
    async def get_capsule_versions(
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Get all versions for a Capsule."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.get_capsule_versions(security_context, capsule_id)
        return {"versions": result}
    
    @app.get("/api/v1/capsules/{capsule_id}/versions/{version}")
    async def get_capsule_version(
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        version: Annotated[int, Path(description="Version number", ge=1)],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Get specific Capsule version with YAML content."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.get_capsule_version(security_context, capsule_id, version)
        return result
    
    @app.post("/api/v1/capsules/{capsule_id}/lint")
    async def lint_capsule(
        request: LintRequest,
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Validate Capsule YAML without publishing."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.lint_capsule(
            security_context=security_context,
            capsule_id=capsule_id,
            yaml_content=request.yaml
        )
        
        return result
    
    @app.put("/api/v1/capsules/{capsule_id}")
    async def update_capsule_status(
        request: UpdateStatusRequest,
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        if_match: Annotated[str, Header(alias="If-Match", description="Expected ETag")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Update Capsule status (soft delete/restore)."""
        service: CapsuleRegistryService = app.state.service
        
        result = await service.update_capsule_status(
            security_context=security_context,
            capsule_id=capsule_id,
            status=request.status,
            expected_etag=if_match
        )
        
        return result
    
    @app.delete("/api/v1/capsules/{capsule_id}")
    async def delete_capsule(
        capsule_id: Annotated[UUID, Path(description="Capsule ID")],
        security_context: SecurityContext = Depends(get_security_context)
    ):
        """Permanently delete Capsule (admin only)."""
        service: CapsuleRegistryService = app.state.service
        
        await service.delete_capsule(security_context, capsule_id)
        return {"message": "Capsule permanently deleted"}


def _setup_exception_handlers(app: FastAPI):
    """Setup exception handlers for consistent error responses."""
    
    @app.exception_handler(AnumateError)
    async def anumate_error_handler(request, exc: AnumateError):
        """Handle Anumate domain errors."""
        status_map = {
            ErrorCode.NOT_FOUND: 404,
            ErrorCode.VALIDATION_ERROR: 400,
            ErrorCode.CONFLICT: 409,
            ErrorCode.FORBIDDEN: 403,
            ErrorCode.UNAUTHORIZED: 401,
            ErrorCode.INTERNAL_ERROR: 500,
        }
        
        status_code = status_map.get(exc.error_code, 500)
        
        error_response = ErrorResponse(
            type=f"https://anumate.io/errors/{exc.error_code.value}",
            title=exc.error_code.value.replace('_', ' ').title(),
            status=status_code,
            detail=exc.message,
            instance=str(request.url),
            trace_id=getattr(request.state, 'trace_id', None)
        )
        
        return JSONResponse(
            status_code=status_code,
            content=error_response.model_dump(exclude_none=True)
        )
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        """Handle HTTP exceptions in RFC 7807 format."""
        error_response = ErrorResponse(
            type="https://tools.ietf.org/html/rfc7231#section-6",
            title="HTTP Error",
            status=exc.status_code,
            detail=exc.detail,
            instance=str(request.url),
            trace_id=getattr(request.state, 'trace_id', None)
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(exclude_none=True)
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.exception("Unexpected error occurred", exc_info=exc)
        
        error_response = ErrorResponse(
            type="https://anumate.io/errors/internal_error",
            title="Internal Server Error",
            status=500,
            detail="An unexpected error occurred",
            instance=str(request.url),
            trace_id=getattr(request.state, 'trace_id', None)
        )
        
        return JSONResponse(
            status_code=500,
            content=error_response.model_dump(exclude_none=True)
        )


def setup_dependencies():
    """Setup dependency injection for request context."""
    from sqlalchemy.ext.asyncio import AsyncSession
    
    async def get_db_session():
        """Get database session."""
        app = get_current_app()
        async with app.state.db_session_factory() as session:
            yield session
    
    async def get_current_service() -> CapsuleRegistryService:
        """Get current service instance."""
        app = get_current_app()
        return app.state.service
    
    def get_current_app() -> FastAPI:
        """Get current FastAPI app from context."""
        from contextvars import ContextVar
        import inspect
        
        # Find app in call stack
        frame = inspect.currentframe()
        while frame:
            if 'app' in frame.f_locals and isinstance(frame.f_locals['app'], FastAPI):
                return frame.f_locals['app']
            frame = frame.f_back
        
        raise RuntimeError("Could not find FastAPI app in context")


async def main():
    """Run the service."""
    # Setup logging and tracing
    setup_logging()
    setup_tracing("capsule-registry")
    
    settings = CapsuleRegistrySettings()
    app = create_app(settings)
    
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,  # Use our logging setup
        access_log=settings.debug
    )
    server = uvicorn.Server(config)
    
    logger.info(
        f"Starting Capsule Registry on {settings.host}:{settings.port}",
        extra={"host": settings.host, "port": settings.port}
    )
    
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
