"""Production-grade settings for Orchestrator service with fail-fast validation."""

import os
from typing import Literal, Optional

# Load .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, use environment variables directly
    pass


class Settings:
    """Orchestrator service configuration with strict validation."""
    
    def __init__(self):
        # Environment configuration - determines strictness level
        self.ANUMATE_ENV: Literal["dev", "stage", "prod", "test"] = os.getenv("ANUMATE_ENV", "dev")
        if self.ANUMATE_ENV not in ["dev", "stage", "prod", "test"]:
            raise ValueError(f"ANUMATE_ENV must be one of: dev, stage, prod, test. Got: {self.ANUMATE_ENV}")
        
        # Portia configuration - SDK-only for hackathon
        self.PORTIA_MODE: Literal["sdk", "http"] = os.getenv("PORTIA_MODE", "sdk")
        if self.PORTIA_MODE not in ["sdk", "http"]:
            raise ValueError(f"PORTIA_MODE must be 'sdk' or 'http'. Got: {self.PORTIA_MODE}")
        
        # HTTP fallback only allowed in test environment
        self.ALLOW_PORTIA_HTTP_FALLBACK: bool = os.getenv("ALLOW_PORTIA_HTTP_FALLBACK", "false").lower() == "true"
        
        # Validate hackathon constraints
        self._validate_hackathon_constraints()
        
        # Required Portia credentials - no dummy defaults
        self.PORTIA_API_KEY = self._get_required_env("PORTIA_API_KEY")
        # Note: PORTIA_BASE_URL removed - using StorageClass.CLOUD for proper cloud config
        self.PORTIA_WORKSPACE_ID = os.getenv("PORTIA_WORKSPACE_ID")
        self.PORTIA_TIMEOUT_SEC = int(os.getenv("PORTIA_TIMEOUT_SEC", "30"))
            
        # LLM configuration for Moonshot Kimi (OpenAI-compatible)
        self.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        self.OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
        self.OPENAI_MODEL = os.getenv("OPENAI_MODEL", "moonshot-v1-8k")
        
        # Service endpoints
        self.APPROVALS_BASE_URL = os.getenv("APPROVALS_BASE_URL", "http://localhost:8001")
        self.RECEIPTS_BASE_URL = os.getenv("RECEIPTS_BASE_URL", "http://localhost:8002")
        self.CAPTOKENS_BASE_URL = os.getenv("CAPTOKENS_BASE_URL", "http://localhost:8083")
        self.REGISTRY_BASE_URL = os.getenv("REGISTRY_BASE_URL", "http://localhost:8082")
        
        # Receipt service configuration
        self.RECEIPT_SIGNING_KEY = os.getenv("RECEIPT_SIGNING_KEY")
        
        # Database configuration
        self.DATABASE_HOST = os.getenv("DATABASE_HOST", "127.0.0.1")
        self.DATABASE_PORT = int(os.getenv("DATABASE_PORT", "5432"))
        self.DATABASE_USER = os.getenv("DATABASE_USER", "anumate_admin")
        self.DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "dev_password")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "anumate")
        
        # Razorpay MCP Configuration
        self.ENABLE_RAZORPAY_MCP: bool = os.getenv("ENABLE_RAZORPAY_MCP", "false").lower() == "true"
        self.RAZORPAY_MCP_MODE: Literal["remote", "stdio"] = os.getenv("RAZORPAY_MCP_MODE", "remote")
        self.RAZORPAY_MCP_SERVER_NAME: str = os.getenv("RAZORPAY_MCP_SERVER_NAME", "razorpay")
        self.RAZORPAY_MCP_URL: str | None = os.getenv("RAZORPAY_MCP_URL", "https://mcp.razorpay.com/mcp")
        self.RAZORPAY_MCP_AUTH: str | None = os.getenv("RAZORPAY_MCP_AUTH")
        self.RAZORPAY_KEY_ID: str | None = os.getenv("RAZORPAY_KEY_ID")
        self.RAZORPAY_KEY_SECRET: str | None = os.getenv("RAZORPAY_KEY_SECRET")
        
        # Additional validation for Razorpay MCP
        self._validate_razorpay_mcp()
    
    def _validate_hackathon_constraints(self):
        """Validate hackathon-specific constraints for SDK-only operation."""
        # Constraint 1: SDK-only mode enforced for dev/stage/prod
        if self.ANUMATE_ENV in {"dev", "stage", "prod"} and self.PORTIA_MODE != "sdk":
            raise ValueError(
                f"SDK-only mode enforced for {self.ANUMATE_ENV} environment. "
                f"PORTIA_MODE must be 'sdk', got '{self.PORTIA_MODE}'"
            )
        
        # Constraint 2: HTTP fallback allowed only in test environment
        if self.ALLOW_PORTIA_HTTP_FALLBACK and self.ANUMATE_ENV != "test":
            raise ValueError(
                f"HTTP fallback allowed only in test environment. "
                f"Got ANUMATE_ENV='{self.ANUMATE_ENV}' with ALLOW_PORTIA_HTTP_FALLBACK=True"
            )
    
    def _get_required_env(self, key: str) -> str:
        """Get required environment variable or raise ValueError."""
        value = os.getenv(key)
        if not value:
            raise ValueError(
                f"Required environment variable {key} is not set. "
                f"Set it in your environment or .env file. No dummy defaults allowed."
            )
        return value
    
    def _validate_razorpay_mcp(self):
        """Validate Razorpay MCP configuration (strict; never log secrets)"""
        if not self.ENABLE_RAZORPAY_MCP:
            return
        
        if self.RAZORPAY_MCP_MODE == "remote":
            if not self.RAZORPAY_MCP_URL:
                raise ValueError("RAZORPAY_MCP_URL required when RAZORPAY_MCP_MODE=remote")
            if not self.RAZORPAY_MCP_AUTH:
                raise ValueError("RAZORPAY_MCP_AUTH required when RAZORPAY_MCP_MODE=remote")
            
            # Log validation without secrets
            print(f"✅ Razorpay MCP Remote mode validated:")
            print(f"   Server: {self.RAZORPAY_MCP_SERVER_NAME}")
            print(f"   URL: {self.RAZORPAY_MCP_URL}")
            print(f"   Auth: {'Bearer ***' if self.RAZORPAY_MCP_AUTH.startswith('Bearer') else '***'}")
            
        elif self.RAZORPAY_MCP_MODE == "stdio":
            if not self.RAZORPAY_KEY_ID:
                raise ValueError("RAZORPAY_KEY_ID required when RAZORPAY_MCP_MODE=stdio")
            if not self.RAZORPAY_KEY_SECRET:
                raise ValueError("RAZORPAY_KEY_SECRET required when RAZORPAY_MCP_MODE=stdio")
            
            # Log validation without secrets
            print(f"✅ Razorpay MCP stdio mode validated:")
            print(f"   Server: {self.RAZORPAY_MCP_SERVER_NAME}")
            print(f"   Key ID: {self.RAZORPAY_KEY_ID[:8]}***")
            print(f"   Key Secret: ***")
        
        else:
            raise ValueError(f"Invalid RAZORPAY_MCP_MODE: {self.RAZORPAY_MCP_MODE}")


def get_settings() -> Settings:
    """Get a new settings instance."""
    return Settings()
