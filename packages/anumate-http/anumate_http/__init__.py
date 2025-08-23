import httpx
from typing import Any, Callable
from anumate_tracing import get_trace_id, inject_trace_context
from anumate_tenancy import get_tenant_id

class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "closed"
        self.last_failure_time = 0

    def call(self, func: Callable[..., Any]) -> Any:
        if self.state == "open":
            if self.last_failure_time + self.recovery_timeout < time.time():
                self.state = "half-open"
            else:
                raise Exception("Circuit is open")

        try:
            result = func()
            self.failure_count = 0
            if self.state == "half-open":
                self.state = "closed"
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.last_failure_time = time.time()
            raise e

def create_http_client(
    tenant_id: str | None = None,
    trace_id: str | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> httpx.Client:
    def trace_id_hook(request):
        if trace_id:
            request.headers["X-Trace-ID"] = trace_id
        else:
            inject_trace_context(request.headers)

    def tenant_id_hook(request):
        if tenant_id:
            request.headers["X-Tenant-ID"] = tenant_id

    transport = httpx.HTTPTransport(retries=retries)
    client = httpx.Client(transport=transport, timeout=timeout)
    client.event_hooks["request"] = [trace_id_hook, tenant_id_hook]

    return client
