# Anumate HTTP

This package provides a resilient HTTP client for the Anumate platform.

## Usage

To use this package, you can create an HTTP client and use it to make requests:

```python
from anumate_http import create_http_client

client = create_http_client(tenant_id="my-tenant", trace_id="my-trace-id")

response = client.get("https://example.com")
```

The client automatically adds the tenant ID and trace ID to the request headers, and it also provides retries with backoff for failed requests.
