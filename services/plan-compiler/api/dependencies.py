"""API dependencies and configuration."""

from functools import lru_cache
from typing import List
from uuid import UUID

from fastapi import Depends, HTTPException, Header
from pydantic_settings import BaseSettings
import structlog

from src.compiler import PlanCompiler
from src.dependency_resolver import DependencyResolver
from src.optimizer import PlanOptimizer
from src.validator import PlanValidator

logger = structlog.get_logger(__name__)


class Settings(BaseSettings):
    """Application settings."""
    
    # API Configuration
    debug: bool = False
    allowed_origins: List[str] = ["*"]
    
    # Database Configuration
    database_url: str = "postgresql://user:pass@localhost/plancompiler"
    
    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    
    # Registry Service Configuration
    registry_service_url: str = "http://localhost:8001"
    
    # Compilation Configuration
    default_optimization_level: str = "standard"
    max_compilation_time: int = 300  # 5 minutes
    enable_plan_caching: bool = True
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


async def get_tenant_id(x_tenant_id: str = Header(...)) -> UUID:
    """Extract tenant ID from request headers."""
    try:
        return UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")


async def get_user_id(x_user_id: str = Header(...)) -> UUID:
    """Extract user ID from request headers."""
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid user ID format")


@lru_cache()
def get_dependency_resolver() -> DependencyResolver:
    """Get dependency resolver instance."""
    return DependencyResolver()


@lru_cache()
def get_plan_optimizer() -> PlanOptimizer:
    """Get plan optimizer instance."""
    return PlanOptimizer()


@lru_cache()
def get_plan_validator() -> PlanValidator:
    """Get plan validator instance."""
    return PlanValidator()


def get_plan_compiler(
    dependency_resolver: DependencyResolver = Depends(get_dependency_resolver),
    optimizer: PlanOptimizer = Depends(get_plan_optimizer),
    validator: PlanValidator = Depends(get_plan_validator)
) -> PlanCompiler:
    """Get plan compiler instance."""
    return PlanCompiler(
        dependency_resolver=dependency_resolver,
        optimizer=optimizer,
        validator=validator
    )