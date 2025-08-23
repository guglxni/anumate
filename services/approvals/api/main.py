"""FastAPI application for the Approvals service."""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .routes import router

try:
    from anumate_tenancy import add_tenant_middleware
    from anumate_logging import configure_logging
except ImportError:
    # Mock implementations for development
    def add_tenant_middleware(app):
        pass
    
    def configure_logging():
        logging.basicConfig(level=logging.INFO)


# Configure logging
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager."""
    logger.info("Starting Approvals service...")
    
    # Startup logic
    try:
        # Initialize database connections, event bus, etc.
        # This would be implemented when we have the actual dependencies
        pass
    except Exception as e:
        logger.error(f"Failed to initialize Approvals service: {e}")
        raise
    
    yield
    
    # Shutdown logic
    logger.info("Shutting down Approvals service...")
    try:
        # Clean up connections, background tasks, etc.
        pass
    except Exception as e:
        logger.error(f"Error during Approvals service shutdown: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="Anumate Approvals Service",
        description="Approval workflow and Clarifications bridge integration",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add tenant middleware
    add_tenant_middleware(app)
    
    # Include routes
    app.include_router(router, tags=["approvals"])
    
    return app


# Create the application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8004"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=os.getenv("ANUMATE_ENV", "development") == "development",
    )
