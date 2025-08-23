"""
Anumate Capability Tokens Package

A.22 Implementation: Ed25519/JWT capability tokens with ≤5min expiry.
Enhanced version that supports capability-based access control.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, List, Optional, Protocol
from dataclasses import dataclass
from datetime import datetime, timezone

import jwt
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


class ReplayGuard(Protocol):
    """Protocol for replay attack prevention."""
    def check_and_set(self, jti: str, ttl: int) -> bool:
        ...


class InMemoryReplayGuard:
    """In-memory implementation of replay guard."""
    def __init__(self) -> None:
        self.storage: Dict[str, float] = {}

    def check_and_set(self, jti: str, ttl: int) -> bool:
        # Clean expired entries
        current_time = time.time()
        expired_keys = [k for k, v in self.storage.items() if v <= current_time]
        for k in expired_keys:
            del self.storage[k]
            
        if jti in self.storage and self.storage[jti] > current_time:
            return False
        self.storage[jti] = current_time + ttl
        return True


@dataclass
class CapabilityToken:
    """Represents a capability token with metadata."""
    token: str
    token_id: str
    subject: str
    tenant_id: str
    capabilities: List[str]
    issued_at: datetime
    expires_at: datetime


# Global key management
_private_key: Optional[ed25519.Ed25519PrivateKey] = None
_public_key: Optional[ed25519.Ed25519PublicKey] = None
_replay_guard: Optional[ReplayGuard] = None


def initialize_keys(private_key_pem: Optional[str] = None, public_key_pem: Optional[str] = None) -> None:
    """Initialize global keys for the capability tokens system."""
    global _private_key, _public_key, _replay_guard
    
    if private_key_pem:
        _private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        _public_key = _private_key.public_key()
    elif public_key_pem:
        _public_key = serialization.load_pem_public_key(public_key_pem.encode())
    else:
        # Generate new keys for development
        _private_key = ed25519.Ed25519PrivateKey.generate()
        _public_key = _private_key.public_key()
    
    _replay_guard = InMemoryReplayGuard()


def get_keys() -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """Get the initialized keys."""
    if _private_key is None or _public_key is None:
        initialize_keys()
    return _private_key, _public_key


def get_replay_guard() -> ReplayGuard:
    """Get the replay guard instance."""
    if _replay_guard is None:
        initialize_keys()
    return _replay_guard


def issue_capability_token_raw(
    private_key: ed25519.Ed25519PrivateKey,
    sub: str,
    capabilities: List[str],
    ttl_secs: int,
    tenant_id: str,
) -> CapabilityToken:
    """
    Issue a capability token (A.22 implementation) with explicit keys.
    
    Args:
        private_key: Ed25519 private key for signing
        sub: Subject identifier (user/service)
        capabilities: List of capability strings
        ttl_secs: TTL in seconds (max 300 for ≤5min requirement)
        tenant_id: Tenant identifier
        
    Returns:
        CapabilityToken with JWT and metadata
        
    Raises:
        ValueError: If TTL exceeds 5 minutes
    """
    if ttl_secs > 300:  # A.22 requirement: ≤5 minutes
        raise ValueError("Token TTL cannot exceed 5 minutes (300 seconds)")
        
    jti = str(uuid.uuid4())
    now = int(time.time())
    expires_at = now + ttl_secs
    
    payload = {
        "sub": sub,
        "capabilities": capabilities,  # A.22: capability-based access control
        "exp": expires_at,
        "iat": now,
        "jti": jti,
        "tenant_id": tenant_id,
        "iss": "anumate-captokens",  # Issuer
        "aud": f"tenant:{tenant_id}",  # Audience
    }
    
    token = jwt.encode(payload, private_key, algorithm="EdDSA")
    
    return CapabilityToken(
        token=token,
        token_id=jti,
        subject=sub,
        tenant_id=tenant_id,
        capabilities=capabilities,
        issued_at=datetime.fromtimestamp(now, tz=timezone.utc),
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc)
    )


def issue_capability_token(
    subject: str,
    capabilities: List[str],
    ttl_seconds: int,
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Issue a capability token using global keys (convenience wrapper).
    
    Args:
        subject: Subject identifier (user/service)
        capabilities: List of capability strings
        ttl_seconds: TTL in seconds (max 300 for ≤5min requirement)
        tenant_id: Tenant identifier
        
    Returns:
        Dictionary with token data for API compatibility
    """
    private_key, _ = get_keys()
    token_obj = issue_capability_token_raw(
        private_key=private_key,
        sub=subject,
        capabilities=capabilities,
        ttl_secs=ttl_seconds,
        tenant_id=tenant_id,
    )
    
    return {
        "token": token_obj.token,
        "token_id": token_obj.token_id,
        "subject": token_obj.subject,
        "tenant_id": token_obj.tenant_id,
        "capabilities": token_obj.capabilities,
        "issued_at": token_obj.issued_at,
        "expires_at": token_obj.expires_at,
    }


def verify_capability_token_raw(
    public_key: ed25519.Ed25519PublicKey,
    token: str,
    replay_guard: ReplayGuard,
) -> Dict[str, Any]:
    """
    Verify a capability token (A.22 implementation) with explicit keys.
    
    Args:
        public_key: Ed25519 public key for verification
        token: JWT token string
        replay_guard: Replay attack prevention
        
    Returns:
        Decoded token payload
        
    Raises:
        ValueError: If token is invalid, expired, or replayed
    """
    try:
        # Disable audience verification for now as we handle multi-tenant validation elsewhere
        payload = jwt.decode(
            token, 
            public_key, 
            algorithms=["EdDSA"],
            options={"verify_aud": False}
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

    ttl = payload["exp"] - int(time.time())
    if ttl <= 0:
        raise ValueError("Token has expired")
        
    if not replay_guard.check_and_set(payload["jti"], ttl):
        raise ValueError("Token has been replayed")

    return payload


def verify_capability_token(token: str, tenant_id: str) -> Dict[str, Any]:
    """
    Verify a capability token using global keys (convenience wrapper).
    
    Args:
        token: JWT token string
        tenant_id: Expected tenant identifier
        
    Returns:
        Dictionary with verification result for API compatibility
    """
    try:
        _, public_key = get_keys()
        replay_guard = get_replay_guard()
        
        payload = verify_capability_token_raw(public_key, token, replay_guard)
        
        # Check tenant isolation
        if payload.get("tenant_id") != tenant_id:
            return {
                "valid": False,
                "error": "Token tenant mismatch"
            }
        
        return {
            "valid": True,
            "payload": payload
        }
    except ValueError as e:
        return {
            "valid": False,
            "error": str(e)
        }


def check_capability(
    public_key: ed25519.Ed25519PublicKey,
    token: str,
    required_capability: str,
    replay_guard: ReplayGuard,
) -> bool:
    """
    Check if token has a specific capability.
    
    Args:
        public_key: Ed25519 public key for verification
        token: JWT token string
        required_capability: Capability string to check
        replay_guard: Replay attack prevention
        
    Returns:
        True if token has capability, False otherwise
    """
    try:
        payload = verify_capability_token_raw(public_key, token, replay_guard)
        capabilities = payload.get("capabilities", [])
        return required_capability in capabilities
    except ValueError:
        return False


def issue_token(
    private_key: ed25519.Ed25519PrivateKey,
    sub: str,
    tool: str,
    constraints: Dict[str, Any],
    ttl_secs: int,
    tenant_id: str,
) -> str:
    """
    Legacy token issuer (pre-A.22).
    
    Use issue_capability_token() for A.22 implementation.
    """
    jti = str(uuid.uuid4())
    payload = {
        "sub": sub,
        "tool": tool,
        "constraints": constraints,
        "exp": int(time.time()) + ttl_secs,
        "iat": int(time.time()),
        "jti": jti,
        "tenant_id": tenant_id,
    }
    
    return jwt.encode(payload, private_key, algorithm="EdDSA")


def verify_token(
    public_key: ed25519.Ed25519PublicKey,
    token: str,
    replay_guard: ReplayGuard,
) -> Dict[str, Any]:
    """
    Legacy token verifier (pre-A.22).
    
    Use verify_capability_token() for A.22 implementation.
    """
    try:
        payload = jwt.decode(
            token, 
            public_key, 
            algorithms=["EdDSA"],
            options={"verify_aud": False}
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

    if not replay_guard.check_and_set(payload["jti"], payload["exp"] - int(time.time())):
        raise ValueError("Token has been replayed")

    return payload
