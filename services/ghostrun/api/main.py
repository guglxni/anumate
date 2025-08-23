"""FastAPI application for GhostRun service."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.simulation import router as simulation_router

# Create FastAPI application
app = FastAPI(
    title="GhostRun Service",
    description="Dry-run simulation service for preflight validation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
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
app.include_router(simulation_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ghostrun"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "GhostRun",
        "description": "Dry-run simulation service for preflight validation",
        "version": "0.1.0",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)