# Anumate Idempotency

This package provides idempotency key helpers and storage for the Anumate platform.

## Usage

To use this package, you can use the `idempotent` decorator to make a function idempotent:

```python
from anumate_idempotency import InMemoryIdempotencyStorage, idempotent

storage = InMemoryIdempotencyStorage()

@idempotent(storage, key_func=lambda x: str(x))
def my_func(x):
    return x * 2

result1 = my_func(2)
result2 = my_func(2)  # This will not execute the function again
```

The package provides an in-memory storage for testing purposes. For production use, you would use a Redis-based implementation.
