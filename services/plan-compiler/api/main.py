"""Plan Compiler API main application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from api.routes import compilation, plans, health
from api.dependencies import get_settings

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    settings = get_settings()
    
    app = FastAPI(
        title="Anumate Plan Compiler Service",
        description="Transforms Capsules to ExecutablePlans",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(compilation.router, prefix="/v1", tags=["compilation"])
    app.include_router(plans.router, prefix="/v1", tags=["plans"])
    
    @app.on_event("startup")
    async def startup_event():
        """Application startup event."""
        logger.info("Plan Compiler service starting up")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Application shutdown event."""
        logger.info("Plan Compiler service shutting down")
    
    return app


app = create_app()