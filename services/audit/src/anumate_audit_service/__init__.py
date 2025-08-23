"""
Anumate Audit Service
====================

A.27 Implementation: Comprehensive audit logging system for the Anumate platform.

Features:
- Centralized audit event capture across all services
- Per-tenant retention policy enforcement
- SIEM export in multiple formats (JSON, CSV, Syslog, CEF)
- Audit trail correlation and advanced search
- Real-time audit streaming via event bus
- PII redaction and compliance controls
- High-performance async logging with database indexing

This service provides enterprise-grade audit logging capabilities that meet
regulatory compliance requirements and integrate with existing security tools.
"""

__version__ = "1.0.0"
__author__ = "Anumate Platform Team"
