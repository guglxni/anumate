"""
Simple crypto utilities for Receipt service
===========================================

Standalone crypto utilities to avoid import issues with the anumate_crypto package.
"""

import json
import hashlib

def canonical_json_serialize(data: dict) -> bytes:
    """Serialize dictionary to canonical JSON bytes."""
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode("utf-8")

def sha256_hash(data: bytes) -> bytes:
    """Calculate SHA-256 hash of data."""
    return hashlib.sha256(data).digest()
