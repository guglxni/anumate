"""Anumate core configuration utilities."""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class Settings:
    """Application settings."""
    
    # Database settings
    database_url: str = "postgresql://localhost/anumate"
    
    # Redis settings  
    redis_url: str = "redis://localhost:6379"
    
    # Portia settings
    portia_base_url: str = "http://localhost:8080"
    portia_timeout: int = 30
    
    # Security settings
    jwt_secret: str = "dev-secret-key"
    
    # Environment
    environment: str = "development"
    debug: bool = True
    
    def __post_init__(self):
        """Load settings from environment variables."""
        self.database_url = os.getenv("DATABASE_URL", self.database_url)
        self.redis_url = os.getenv("REDIS_URL", self.redis_url)
        self.portia_base_url = os.getenv("PORTIA_BASE_URL", self.portia_base_url)
        self.portia_timeout = int(os.getenv("PORTIA_TIMEOUT", str(self.portia_timeout)))
        self.jwt_secret = os.getenv("JWT_SECRET", self.jwt_secret)
        self.environment = os.getenv("ENVIRONMENT", self.environment)
        self.debug = os.getenv("DEBUG", "true").lower() == "true"

# Global settings instance
settings = Settings()