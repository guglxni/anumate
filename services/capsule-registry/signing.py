"""Content signing and verification for Capsules."""

import base64
import hashlib
from typing import Tuple, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.exceptions import InvalidSignature

from anumate_crypto import CryptoProvider
from anumate_errors import CryptoError, ErrorCode


class CapsuleSigningProvider:
    """Handles Capsule content hashing and Ed25519 signing."""
    
    def __init__(self, private_key_pem: str, public_key_id: str = "default"):
        """
        Initialize with Ed25519 private key.
        
        Args:
            private_key_pem: Base64-encoded PEM private key
            public_key_id: Identifier for the public key
        """
        self.public_key_id = public_key_id
        self._private_key = self._load_private_key(private_key_pem)
        self._public_key = self._private_key.public_key()
    
    def _load_private_key(self, private_key_pem: str) -> Ed25519PrivateKey:
        """Load Ed25519 private key from base64-encoded PEM."""
        try:
            # Decode base64 if needed
            if not private_key_pem.startswith('-----BEGIN'):
                pem_data = base64.b64decode(private_key_pem.encode('ascii'))
            else:
                pem_data = private_key_pem.encode('ascii')
            
            # Load the private key
            private_key = serialization.load_pem_private_key(
                pem_data, 
                password=None
            )
            
            if not isinstance(private_key, Ed25519PrivateKey):
                raise CryptoError(
                    error_code=ErrorCode.CRYPTO_ERROR,
                    message="Provided key is not an Ed25519 private key"
                )
            
            return private_key
            
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to load private key: {str(e)}"
            )
    
    def compute_content_hash(self, canonical_json: str) -> str:
        """
        Compute SHA-256 hash of canonical JSON content.
        
        Args:
            canonical_json: Canonical JSON representation of Capsule
            
        Returns:
            Hex-encoded SHA-256 hash
        """
        try:
            content_bytes = canonical_json.encode('utf-8')
            hash_digest = hashlib.sha256(content_bytes).hexdigest()
            return hash_digest
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to compute content hash: {str(e)}"
            )
    
    def sign_content(self, content_hash: str) -> str:
        """
        Sign content hash with Ed25519 private key.
        
        Args:
            content_hash: Hex-encoded SHA-256 hash to sign
            
        Returns:
            Base64-encoded Ed25519 signature
        """
        try:
            # Convert hash to bytes
            hash_bytes = bytes.fromhex(content_hash)
            
            # Sign the hash
            signature_bytes = self._private_key.sign(hash_bytes)
            
            # Return base64-encoded signature
            return base64.b64encode(signature_bytes).decode('ascii')
            
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to sign content: {str(e)}"
            )
    
    def verify_signature(self, content_hash: str, signature: str, public_key_pem: Optional[str] = None) -> bool:
        """
        Verify Ed25519 signature against content hash.
        
        Args:
            content_hash: Hex-encoded SHA-256 hash
            signature: Base64-encoded Ed25519 signature
            public_key_pem: Optional public key PEM (uses instance key if None)
            
        Returns:
            True if signature is valid
        """
        try:
            # Get public key to use
            if public_key_pem:
                public_key = self._load_public_key(public_key_pem)
            else:
                public_key = self._public_key
            
            # Convert inputs to bytes
            hash_bytes = bytes.fromhex(content_hash)
            signature_bytes = base64.b64decode(signature.encode('ascii'))
            
            # Verify signature
            public_key.verify(signature_bytes, hash_bytes)
            return True
            
        except InvalidSignature:
            return False
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to verify signature: {str(e)}"
            )
    
    def _load_public_key(self, public_key_pem: str) -> Ed25519PublicKey:
        """Load Ed25519 public key from PEM."""
        try:
            pem_data = public_key_pem.encode('ascii')
            public_key = serialization.load_pem_public_key(pem_data)
            
            if not isinstance(public_key, Ed25519PublicKey):
                raise CryptoError(
                    error_code=ErrorCode.CRYPTO_ERROR,
                    message="Provided key is not an Ed25519 public key"
                )
            
            return public_key
            
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to load public key: {str(e)}"
            )
    
    def get_public_key_pem(self) -> str:
        """Get public key in PEM format."""
        try:
            public_key_bytes = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return public_key_bytes.decode('ascii')
        except Exception as e:
            raise CryptoError(
                error_code=ErrorCode.CRYPTO_ERROR,
                message=f"Failed to export public key: {str(e)}"
            )
    
    def sign_and_hash_content(self, canonical_json: str) -> Tuple[str, str]:
        """
        Convenience method to hash and sign content in one call.
        
        Args:
            canonical_json: Canonical JSON representation of Capsule
            
        Returns:
            Tuple of (content_hash, signature)
        """
        content_hash = self.compute_content_hash(canonical_json)
        signature = self.sign_content(content_hash)
        return content_hash, signature


def create_signing_provider(private_key_pem: str, public_key_id: str = "default") -> CapsuleSigningProvider:
    """Factory function to create a signing provider."""
    return CapsuleSigningProvider(private_key_pem, public_key_id)


# Utility functions for testing
def generate_test_keypair() -> Tuple[str, str]:
    """
    Generate a test Ed25519 keypair for development/testing.
    
    Returns:
        Tuple of (private_key_pem, public_key_pem)
    """
    private_key = Ed25519PrivateKey.generate()
    
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('ascii')
    
    public_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('ascii')
    
    return private_key_pem, public_key_pem
