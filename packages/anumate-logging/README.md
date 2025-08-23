# Anumate Logging

This package provides structured JSON logging for the Anumate platform.

## Usage

To use this package, you can get a logger instance and use it to log messages:

```python
from anumate_logging import get_logger

logger = get_logger("my-service", tenant_id="my-tenant", plan_hash="my-hash", run_id="my-run")

logger.info("This is a test message with an email: test@example.com")
```

The logger will automatically format the log messages as JSON and mask PII data like emails and UPI addresses.
