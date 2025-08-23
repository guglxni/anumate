"""Anumate error handling utilities."""

from typing import Optional, Dict, Any

class AnumateError(Exception):
    """Base exception for Anumate errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "ANUMATE_ERROR"
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details
        }

class ValidationError(AnumateError):
    """Validation error."""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, error_code="VALIDATION_ERROR", **kwargs)
        if field:
            self.details["field"] = field

class ConfigurationError(AnumateError):
    """Configuration error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="CONFIGURATION_ERROR", **kwargs)

class ExecutionError(AnumateError):
    """Execution error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="EXECUTION_ERROR", **kwargs)

class NetworkError(AnumateError):
    """Network error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, error_code="NETWORK_ERROR", **kwargs)


class ErrorCode:
    """Standard error codes."""
    
    # Generic errors
    ANUMATE_ERROR = "ANUMATE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    
    # Token errors
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    INSUFFICIENT_CAPABILITY = "INSUFFICIENT_CAPABILITY"
    
    # Service errors
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"