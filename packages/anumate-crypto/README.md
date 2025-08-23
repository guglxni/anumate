# Anumate Crypto

This package provides cryptographic utilities for the Anumate platform.

## Usage

To use this package, you can use the provided functions for key loading, hashing, and serialization:

```python
from anumate_crypto import (
    canonical_json_serialize,
    load_ed25519_private_key_from_file,
    sha256_hash,
)

# Load a private key from a file
private_key = load_ed25519_private_key_from_file("my_key.pem")

# Hash data using SHA-256
hashed_data = sha256_hash(b"my data")

# Serialize a dictionary to canonical JSON
serialized_data = canonical_json_serialize({"b": 2, "a": 1})
```
