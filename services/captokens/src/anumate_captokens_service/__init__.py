"""
Anumate CapTokens Service
========================

Production-grade Ed25519/JWT capability token management service with REST API.

This service provides:
- Token issuance with Ed25519 signing
- Token verification and validation
- Multi-tenant capability management
- Database-backed audit trails
- Redis-based replay protection
- Background token cleanup
- Comprehensive monitoring and observability
"""

__version__ = "0.1.0"
__author__ = "Anumate Platform"
__email__ = "platform@anumate.ai"

from .app_production import create_app, app
from .models import *

__all__ = [
    "app",
    "create_app",
    "__version__",
    "__author__",
    "__email__",
]
