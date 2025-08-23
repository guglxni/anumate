# Anumate Core Config

This package provides a layered configuration loader for the Anumate platform.

## Usage

To use this package, import the `settings` object from the `anumate_core_config` module:

```python
from anumate_core_config import settings

print(settings.ANUMATE_ENV)
```

The settings are loaded from environment variables, `.env` files, and command-line flags.
