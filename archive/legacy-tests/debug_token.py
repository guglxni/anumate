#!/usr/bin/env python3
"""
Debug A.22 Token Issues
"""

import sys
import jwt

# Add the packages to Python path
sys.path.insert(0, '/Users/aaryanguglani/anumate/packages/anumate-capability-tokens')

from cryptography.hazmat.primitives.asymmetric import ed25519
from anumate_capability_tokens import (
    issue_capability_token, 
    verify_capability_token, 
    InMemoryReplayGuard
)

def debug_token():
    """Debug token creation and verification."""
    
    # Generate keys
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    replay_guard = InMemoryReplayGuard()
    
    # Issue token
    token = issue_capability_token(
        private_key=private_key,
        sub="debug-user",
        capabilities=["test"],
        ttl_secs=60,
        tenant_id="debug-tenant"
    )
    
    print(f"Token issued: {token.token}")
    
    # Try to decode without verification first
    try:
        unverified = jwt.decode(token.token, options={"verify_signature": False})
        print(f"Unverified payload: {unverified}")
    except Exception as e:
        print(f"Failed to decode unverified: {e}")
    
    # Try manual verification
    try:
        verified = jwt.decode(token.token, public_key, algorithms=["EdDSA"])
        print(f"Manual verification successful: {verified}")
    except Exception as e:
        print(f"Manual verification failed: {e}")
    
    # Try our function
    try:
        payload = verify_capability_token(public_key, token.token, replay_guard)
        print(f"Function verification successful: {payload}")
    except Exception as e:
        print(f"Function verification failed: {e}")

if __name__ == "__main__":
    debug_token()
