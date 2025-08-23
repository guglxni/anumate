# Anumate Errors

This package provides an error taxonomy and RFC7807 helpers for the Anumate platform.

## Usage

To use this package, you can raise the specific error classes in your code:

```python
from anumate_errors import BadRequest

raise BadRequest("Invalid input")
```

The package also provides a FastAPI exception handler that can be used to automatically convert these exceptions into RFC7807-compliant JSON responses.
