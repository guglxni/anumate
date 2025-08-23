"""
Ed25519/JWT Capability Token Generator

Implements A.22: Ed25519/JWT capability tokens with ≤5min expiry
Provides cryptographically secure short-lived capability tokens.
"""

import base64
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization
import jwt
from dataclasses import dataclass
import uuid


@dataclass
class CapabilityToken:
    """Represents a capability token with metadata."""
    token: str
    token_id: str
    capabilities: List[str]
    tenant_id: str
    subject: str
    issued_at: datetime
    expires_at: datetime
    

class TokenKeyManager:
    """Manages Ed25519 key pairs for token signing and verification."""
    
    def __init__(self):
        self._private_key: Optional[ed25519.Ed25519PrivateKey] = None
        self._public_key: Optional[ed25519.Ed25519PublicKey] = None
        self._key_id: Optional[str] = None
        
    def generate_key_pair(self) -> Tuple[str, str]:
        """
        Generate a new Ed25519 key pair.
        
        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        self._private_key = ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._key_id = str(uuid.uuid4())
        
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')
        
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        return private_pem, public_pem
    
    def load_private_key(self, private_key_pem: str, key_id: str):
        """Load private key from PEM format."""
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode('utf-8'),
            password=None
        )
        self._public_key = self._private_key.public_key()
        self._key_id = key_id
        
    def load_public_key(self, public_key_pem: str, key_id: str):
        """Load public key from PEM format."""
        self._public_key = serialization.load_pem_public_key(
            public_key_pem.encode('utf-8')
        )
        self._key_id = key_id
    
    @property
    def private_key(self) -> ed25519.Ed25519PrivateKey:
        """Get the private key."""
        if not self._private_key:
            raise ValueError("Private key not loaded")
        return self._private_key
    
    @property
    def public_key(self) -> ed25519.Ed25519PublicKey:
        """Get the public key."""
        if not self._public_key:
            raise ValueError("Public key not loaded")
        return self._public_key
    
    @property
    def key_id(self) -> str:
        """Get the key ID."""
        if not self._key_id:
            raise ValueError("Key ID not set")
        return self._key_id


class CapabilityTokenGenerator:
    """
    Generates and validates Ed25519/JWT capability tokens.
    
    Features:
    - Ed25519 cryptographic signing
    - ≤5 minute token expiry
    - Capability-based access control
    - Multi-tenant isolation
    - Token revocation support
    """
    
    def __init__(self, key_manager: TokenKeyManager):
        self.key_manager = key_manager
        self._revoked_tokens: set = set()  # In production, use Redis/database
        
    def generate_token(
        self,
        tenant_id: str,
        subject: str,
        capabilities: List[str],
        expires_in_seconds: int = 300  # 5 minutes default
    ) -> CapabilityToken:
        """
        Generate a capability token.
        
        Args:
            tenant_id: Tenant identifier
            subject: Subject (user/service) identifier  
            capabilities: List of capability strings
            expires_in_seconds: Token expiry (max 300s = 5min)
            
        Returns:
            CapabilityToken with JWT and metadata
        """
        if expires_in_seconds > 300:
            raise ValueError("Token expiry cannot exceed 5 minutes (300 seconds)")
            
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_seconds)
        token_id = str(uuid.uuid4())
        
        # JWT payload with capability claims
        payload = {
            "jti": token_id,  # JWT ID
            "iss": "anumate-captokens",  # Issuer
            "sub": subject,  # Subject
            "aud": f"tenant:{tenant_id}",  # Audience (tenant)
            "iat": int(now.timestamp()),  # Issued at
            "exp": int(expires_at.timestamp()),  # Expires at
            "cap": capabilities,  # Capabilities
            "tid": tenant_id,  # Tenant ID
        }
        
        # Sign with Ed25519
        token = jwt.encode(
            payload,
            self.key_manager.private_key,
            algorithm="EdDSA",
            headers={
                "kid": self.key_manager.key_id,
                "alg": "EdDSA"
            }
        )
        
        return CapabilityToken(
            token=token,
            token_id=token_id,
            capabilities=capabilities,
            tenant_id=tenant_id,
            subject=subject,
            issued_at=now,
            expires_at=expires_at
        )
    
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode a capability token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload
            
        Raises:
            jwt.InvalidTokenError: If token is invalid
            ValueError: If token is revoked
        """
        try:
            # Decode and verify signature
            payload = jwt.decode(
                token,
                self.key_manager.public_key,
                algorithms=["EdDSA"],
                options={"verify_exp": True}
            )
            
            # Check revocation
            token_id = payload.get("jti")
            if token_id in self._revoked_tokens:
                raise ValueError("Token has been revoked")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise jwt.InvalidTokenError("Token has expired")
        except jwt.InvalidSignatureError:
            raise jwt.InvalidTokenError("Invalid token signature")
        except jwt.InvalidTokenError:
            raise
    
    def check_capability(self, token: str, required_capability: str) -> bool:
        """
        Check if token has a specific capability.
        
        Args:
            token: JWT token string
            required_capability: Capability to check for
            
        Returns:
            True if token has capability, False otherwise
        """
        try:
            payload = self.verify_token(token)
            capabilities = payload.get("cap", [])
            return required_capability in capabilities
        except (jwt.InvalidTokenError, ValueError):
            return False
    
    def revoke_token(self, token_id: str):
        """Revoke a token by its ID."""
        self._revoked_tokens.add(token_id)
    
    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get token information without throwing exceptions.
        
        Args:
            token: JWT token string
            
        Returns:
            Token info dict or None if invalid
        """
        try:
            return self.verify_token(token)
        except (jwt.InvalidTokenError, ValueError):
            return None


class CapabilityTokenMiddleware:
    """
    Middleware for capability token validation.
    
    Validates tokens and injects capability context into requests.
    """
    
    def __init__(self, generator: CapabilityTokenGenerator):
        self.generator = generator
    
    def validate_request_capability(
        self, 
        authorization_header: Optional[str], 
        required_capability: str
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate a request's capability token.
        
        Args:
            authorization_header: HTTP Authorization header value
            required_capability: Required capability string
            
        Returns:
            Tuple of (is_valid, token_payload)
        """
        if not authorization_header:
            return False, None
            
        if not authorization_header.startswith("Bearer "):
            return False, None
        
        token = authorization_header[7:]  # Remove "Bearer "
        
        try:
            payload = self.generator.verify_token(token)
            has_capability = self.generator.check_capability(token, required_capability)
            
            if has_capability:
                return True, payload
            else:
                return False, payload
                
        except (jwt.InvalidTokenError, ValueError):
            return False, None
