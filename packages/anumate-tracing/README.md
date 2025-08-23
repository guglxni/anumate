# Anumate Tracing

This package provides OpenTelemetry tracing utilities for the Anumate platform.

## Usage

To use this package, you need to initialize the tracer in your application startup:

```python
from anumate_tracing import initialize_tracer, add_tracing_middleware
from fastapi import FastAPI

app = FastAPI()

initialize_tracer("my-service")
add_tracing_middleware(app, "my-service")
```

You can then get the current trace ID and inject/extract the trace context:

```python
from anumate_tracing import get_trace_id, inject_trace_context, extract_trace_context

trace_id = get_trace_id()

headers = {}
inject_trace_context(headers)

context = extract_trace_context(headers)
```
