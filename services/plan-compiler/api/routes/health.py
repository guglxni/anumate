"""Health check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service="plan-compiler",
        version="1.0.0"
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness_check():
    """Readiness check endpoint."""
    # In a real implementation, this would check dependencies
    return HealthResponse(
        status="ready",
        service="plan-compiler",
        version="1.0.0"
    )