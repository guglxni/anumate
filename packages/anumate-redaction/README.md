# Anumate Redaction

This package provides PII redaction utilities for the Anumate platform.

## Usage

To use this package, you can use the provided masking functions and redaction hooks:

```python
from anumate_redaction import get_redaction_hook, mask_email, mask_upi_vpa

# Mask email and UPI VPAs
masked_email = mask_email("test@example.com")
masked_upi = mask_upi_vpa("test@upi")

# Get a redaction hook based on the user's role
redaction_hook = get_redaction_hook("default")

data = {"email": "test@example.com", "upi": "test@upi"}
redacted_data = redaction_hook(data)
```
