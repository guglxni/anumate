# Anumate Capability Tokens

This package provides JWT-like capability tokens for the Anumate platform.

## Usage

To use this package, you can issue and verify tokens:

```python
from Crypto.PublicKey import Ed25519
from anumate_capability_tokens import (
    InMemoryReplayGuard,
    issue_token,
    verify_token,
)

private_key = Ed25519.generate()
public_key = private_key.public_key()
replay_guard = InMemoryReplayGuard()

token = issue_token(
    private_key,
    sub="my-sub",
    tool="my-tool",
    constraints={"amount_lte": 100},
    ttl_secs=60,
    tenant_id="my-tenant",
)

payload = verify_token(public_key, token, replay_guard)
```

The package provides an in-memory replay guard for testing purposes. For production use, you would use a Redis-based implementation.
