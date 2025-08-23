"""FastAPI application for Policy Service."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False

from anumate_infrastructure.database import DatabaseManager
from anumate_infrastructure.tenant_context import TenantMiddleware

from .routes import policies
from .dependencies import get_database_manager

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting Policy Service")
    
    # Initialize database connection
    db_manager = DatabaseManager()
    await db_manager.initialize()
    app.state.db_manager = db_manager
    
    logger.info("Policy Service started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Policy Service")
    await db_manager.close()
    logger.info("Policy Service shutdown complete")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Anumate Policy Service",
        description="API for managing and evaluating policies in the Anumate platform",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add tenant context middleware
    app.add_middleware(TenantMiddleware)
    
    # Include routers
    app.include_router(
        policies.router,
        prefix="/v1/policies",
        tags=["policies"]
    )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "service": "policy"}
    
    # Add OpenTelemetry instrumentation if available
    if OTEL_AVAILABLE:
        FastAPIInstrumentor.instrument_app(app)
    
    return app


# Create the application instance
app = create_app()