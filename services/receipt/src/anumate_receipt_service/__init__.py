"""
Anumate Receipt Service
======================

Production-grade tamper-evident receipt system with digital signatures,
immutable storage, and comprehensive audit logging.

Key Features:
- Tamper-evident receipts with cryptographic hashing
- Ed25519 digital signatures for integrity verification
- WORM (Write Once Read Many) storage integration
- Comprehensive audit logging with SIEM export
- Multi-tenant isolation with UUID-based tenancy
- High-performance async architecture

Architecture:
- FastAPI service with async/await patterns
- PostgreSQL database with RLS for multi-tenancy
- Ed25519 cryptographic signatures for integrity
- OpenTelemetry integration for observability
- CloudEvents for event-driven integration

Version: 1.0.0
"""

from .app_production import create_app, app

__version__ = "1.0.0"
__all__ = ["create_app", "app"]
