"""
Cryptographic Signing Module

A.4–A.6 Implementation: Ed25519 digital signatures for capsule content integrity
with secure key management and verification capabilities.
"""

import base64
import binascii
from typing import Optional, Tuple, Dict, Any
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from anumate_crypto import Ed25519Signer, Ed25519Verifier, generate_ed25519_keypair
from anumate_errors import SecurityError, ConfigurationError
from .settings import RegistrySettings


class CapsuleSigner:
    """Ed25519 signer for capsule content integrity."""
    
    def __init__(self, settings: RegistrySettings):
        """Initialize signer with configuration."""
        self.settings = settings
        self.key_id = settings.signing_key_id
        self._private_key: Optional[Ed25519PrivateKey] = None
        self._public_key: Optional[Ed25519PublicKey] = None
        self._initialize_keys()
        
    def _initialize_keys(self) -> None:
        """Initialize signing keys from configuration."""
        try:
            if self.settings.ed25519_private_key:
                # Load private key from base64-encoded environment variable
                private_key_bytes = base64.b64decode(self.settings.ed25519_private_key)
                self._private_key = serialization.load_pem_private_key(
                    private_key_bytes, 
                    password=None
                )
                if not isinstance(self._private_key, Ed25519PrivateKey):
                    raise ConfigurationError("Configured key is not Ed25519")
                    
                self._public_key = self._private_key.public_key()
                
            else:
                # Generate ephemeral keypair for development
                if not self.settings.is_production:
                    self._private_key, self._public_key = generate_ed25519_keypair()
                else:
                    raise ConfigurationError(
                        "ED25519_PRIVATE_KEY must be configured in production"
                    )
                    
        except Exception as e:
            raise ConfigurationError(f"Failed to initialize signing keys: {e}")
    
    def get_public_key_pem(self) -> str:
        """Get public key in PEM format."""
        if not self._public_key:
            raise SecurityError("Public key not available")
            
        pem_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return pem_bytes.decode("utf-8")
    
    def get_public_key_fingerprint(self) -> str:
        """Get public key fingerprint for identification."""
        import hashlib
        pem = self.get_public_key_pem()
        return hashlib.sha256(pem.encode()).hexdigest()[:16]
    
    def sign_content_hash(self, content_hash: str) -> str:
        """Sign a content hash and return hex-encoded signature."""
        if not self._private_key:
            raise SecurityError("Private key not available for signing")
            
        if len(content_hash) != 64 or not all(c in "0123456789abcdef" for c in content_hash):
            raise ValueError("Content hash must be 64-character hex string")
        
        try:
            # Convert hash to bytes and sign
            hash_bytes = binascii.unhexlify(content_hash)
            signature = self._private_key.sign(hash_bytes)
            
            # Return hex-encoded signature
            return binascii.hexlify(signature).decode("ascii")
            
        except Exception as e:
            raise SecurityError(f"Failed to sign content hash: {e}")
    
    def verify_signature(self, content_hash: str, signature_hex: str, 
                        public_key_pem: Optional[str] = None) -> bool:
        """Verify signature against content hash."""
        try:
            # Use provided public key or own public key
            if public_key_pem:
                public_key = serialization.load_pem_public_key(public_key_pem.encode())
                if not isinstance(public_key, Ed25519PublicKey):
                    raise ValueError("Provided key is not Ed25519")
            else:
                public_key = self._public_key
                
            if not public_key:
                raise SecurityError("No public key available for verification")
            
            # Convert inputs to bytes
            hash_bytes = binascii.unhexlify(content_hash)
            signature_bytes = binascii.unhexlify(signature_hex)
            
            # Verify signature
            public_key.verify(signature_bytes, hash_bytes)
            return True
            
        except InvalidSignature:
            return False
        except Exception as e:
            raise SecurityError(f"Signature verification failed: {e}")
    
    def create_signature_metadata(self, content_hash: str) -> Dict[str, str]:
        """Create complete signature metadata for a content hash."""
        signature = self.sign_content_hash(content_hash)
        
        return {
            "content_hash": content_hash,
            "signature": signature,
            "pubkey_id": self.key_id,
            "pubkey_fingerprint": self.get_public_key_fingerprint(),
            "algorithm": "Ed25519"
        }
    
    def verify_signature_metadata(self, metadata: Dict[str, str], 
                                 public_key_pem: Optional[str] = None) -> bool:
        """Verify complete signature metadata."""
        required_fields = ["content_hash", "signature", "pubkey_id", "algorithm"]
        
        if not all(field in metadata for field in required_fields):
            raise ValueError(f"Signature metadata missing required fields: {required_fields}")
        
        if metadata["algorithm"] != "Ed25519":
            raise ValueError(f"Unsupported signature algorithm: {metadata['algorithm']}")
        
        return self.verify_signature(
            metadata["content_hash"],
            metadata["signature"], 
            public_key_pem
        )


class SignatureVerifier:
    """Standalone signature verifier for external verification."""
    
    @staticmethod
    def verify_with_public_key(content_hash: str, signature_hex: str, 
                              public_key_pem: str) -> bool:
        """Verify signature using provided public key."""
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            
            hash_bytes = binascii.unhexlify(content_hash)
            signature_bytes = binascii.unhexlify(signature_hex)
            
            public_key.verify(signature_bytes, hash_bytes)
            return True
            
        except (InvalidSignature, Exception):
            return False
    
    @staticmethod
    def extract_public_key_info(public_key_pem: str) -> Dict[str, str]:
        """Extract information from public key PEM."""
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            if not isinstance(public_key, Ed25519PublicKey):
                raise ValueError("Key is not Ed25519")
            
            # Generate fingerprint
            import hashlib
            fingerprint = hashlib.sha256(public_key_pem.encode()).hexdigest()[:16]
            
            return {
                "algorithm": "Ed25519",
                "fingerprint": fingerprint,
                "key_size": "256",  # Ed25519 is always 256-bit
                "format": "PEM"
            }
            
        except Exception as e:
            raise ValueError(f"Invalid public key: {e}")


def create_signer(settings: RegistrySettings) -> CapsuleSigner:
    """Factory function to create configured signer."""
    return CapsuleSigner(settings)


def verify_content_integrity(content_hash: str, signature_hex: str, 
                           public_key_pem: str) -> bool:
    """Utility function for standalone content integrity verification."""
    return SignatureVerifier.verify_with_public_key(
        content_hash, signature_hex, public_key_pem
    )
