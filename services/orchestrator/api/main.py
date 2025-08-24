"""Main FastAPI application for orchestrator service."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
# Infrastructure imports - simplified for demo
import logging

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from routes.execution import router as execution_router
from routes.razorpay_webhook import router as razorpay_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.
    
    Args:
        app: FastAPI application
        
    Yields:
        None during application lifetime
    """
    # Startup
    logger.info("Starting Orchestrator API service...")
    
    # Import after path setup
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    
    try:
        # Initialize and validate Portia SDK client during startup
        logger.info("Initializing Portia SDK client...")
        from src.settings import Settings
        from src.portia_client import create_portia_client
        
        # Load settings
        settings = Settings()
        
        # Create Portia client with proper credentials
        portia_client = create_portia_client(
            api_key=settings.PORTIA_API_KEY
        )
        
        # Store client in app state for later use
        app.state.portia_client = portia_client
        
        logger.info("✅ Portia SDK validation passed - service ready")
        
    except Exception as e:
        logger.error(f"❌ Portia SDK initialization failed: {e}")
        logger.error("Service startup aborted - fix SDK configuration and restart")
        # Re-raise to crash the application
        raise RuntimeError(f"Startup failed: Portia SDK not ready: {e}") from e
    
    logger.info("Orchestrator API service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Orchestrator API service...")
    
    # Cleanup Portia client if available
    if hasattr(app.state, 'portia_client'):
        try:
            await app.state.portia_client.close()
        except Exception as e:
            logger.warning(f"Error closing Portia client: {e}")
    
    logger.info("Orchestrator API service shutdown complete")


def create_app() -> FastAPI:
    """Create FastAPI application.
    
    Returns:
        Configured FastAPI application
    """
    # Setup basic logging
    logging.basicConfig(level=logging.INFO)
    
    # Create FastAPI app
    app = FastAPI(
        title="Anumate Orchestrator API",
        description="ExecutablePlan execution orchestration via Portia Runtime",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(execution_router)
    app.include_router(razorpay_router)
    
    # Health check endpoint
    @app.get("/health", tags=["health"])
    async def health_check():
        """Health check endpoint - only healthy if Portia SDK probe passed."""
        # Check if Portia client is ready
        if hasattr(app.state, 'portia_client'):
            try:
                is_ready = app.state.portia_client.is_ready()
                if is_ready:
                    return {"status": "healthy", "service": "orchestrator-api", "portia": "ready"}
                else:
                    return {"status": "degraded", "service": "orchestrator-api", "reason": "portia_sdk_not_ready"}
            except Exception as e:
                return {"status": "degraded", "service": "orchestrator-api", "reason": f"portia_check_failed: {e}"}
        else:
            return {"status": "degraded", "service": "orchestrator-api", "reason": "portia_client_not_initialized"}
    
    # Readiness check endpoint
    @app.get("/readyz", tags=["health"])
    async def readiness_check():
        """Readiness check endpoint for production deployment."""
        # Import settings to check environment
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.settings import Settings
        
        settings = Settings()
        
        # Get Portia client status from app state
        portia_status = "not_initialized"
        if hasattr(app.state, 'portia_client'):
            try:
                is_ready = app.state.portia_client.is_ready()
                portia_status = "ready" if is_ready else "not_ready"
            except Exception as e:
                logger.warning(f"Error getting Portia health status: {e}")
                portia_status = "error"
        
        # Check required environment variables
        env_ready = all([
            settings.PORTIA_API_KEY,
            settings.OPENAI_API_KEY,
            settings.OPENAI_BASE_URL
        ])
        
        services_status = {
            "portia": portia_status,
            "openai": "ready" if settings.OPENAI_API_KEY else "missing_config",
            "approvals_service": "configured",
            "receipts_service": "configured"
        }
        
        overall_ready = (
            env_ready and 
            portia_status == "ready" and
            all(status in ["ready", "configured"] for status in services_status.values())
        )
        
        return {
            "ready": overall_ready,
            "service": "orchestrator-api",
            "version": "0.1.0",
            "environment": settings.ANUMATE_ENV,
            "mode": "sdk-only-hackathon",
            "services": services_status,
            "portia_mode": settings.PORTIA_MODE,
            "sdk_enforced": settings.ANUMATE_ENV in {"dev", "stage", "prod"}
        }
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler.
        
        Args:
            request: HTTP request
            exc: Exception that occurred
            
        Returns:
            JSON error response
        """
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "path": str(request.url.path),
            }
        )
    
    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )