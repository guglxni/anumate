"""Backward compatibility layer for Portia client migration.

This module provides backward compatibility during the migration from custom
PortiaClient to the official Portia SDK Python for WeMakeDevs AgentHack 2025.
"""

import warnings
from .portia_sdk_client import PortiaSDKClient, PortiaSDKClientError

# Backward compatibility aliases
PortiaClient = PortiaSDKClient
PortiaClientError = PortiaSDKClientError

# Deprecation warning
def _warn_deprecated():
    """Issue deprecation warning for old imports."""
    warnings.warn(
        "Importing from portia_client is deprecated. "
        "Use portia_sdk_client instead for production-grade Portia SDK integration.",
        DeprecationWarning,
        stacklevel=3
    )

# Override __all__ to ensure proper exports
__all__ = ['PortiaClient', 'PortiaClientError']

# Issue warning when module is imported
_warn_deprecated()
