from __future__ import annotations

from typing import Any, Optional, Dict
import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

logger = logging.getLogger(__name__)


def initialize_tracer(service_name: str, service_version: str = "1.0.0") -> None:
    """Initialize OpenTelemetry tracer with service information."""
    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: service_name,
        ResourceAttributes.SERVICE_VERSION: service_version,
    })
    
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    
    logger.info(f"Initialized tracer for service: {service_name}")


def get_tracer(service_name: str) -> trace.Tracer:
    return trace.get_tracer(service_name)


def get_trace_id() -> str | None:
    span = trace.get_current_span()
    if span is None:
        return None
    return f"{span.get_span_context().trace_id:032x}"


def inject_trace_context(headers: dict[str, Any]) -> None:
    TraceContextTextMapPropagator().inject(headers)


def extract_trace_context(headers: dict[str, Any]) -> trace.Context:
    return TraceContextTextMapPropagator().extract(headers)


def add_span_attributes(attributes: Dict[str, Any]) -> None:
    """Add attributes to the current span."""
    span = trace.get_current_span()
    if span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_tenant_context_to_span() -> None:
    """Add tenant and correlation context to current span."""
    try:
        from anumate_infrastructure import get_current_tenant_id, get_current_correlation_id
        
        span = trace.get_current_span()
        if span.is_recording():
            tenant_id = get_current_tenant_id()
            correlation_id = get_current_correlation_id()
            
            if tenant_id:
                span.set_attribute("tenant.id", str(tenant_id))
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)
    except ImportError:
        logger.warning("anumate_infrastructure not available for context injection")


def create_span(name: str, attributes: Optional[Dict[str, Any]] = None) -> trace.Span:
    """Create a new span with tenant context."""
    tracer = trace.get_tracer(__name__)
    span = tracer.start_span(name)
    
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    
    # Add tenant context
    add_tenant_context_to_span()
    
    return span


def add_tracing_middleware(app: Any, service_name: str) -> None:
    """Add FastAPI tracing instrumentation."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(
        app, 
        service_name=service_name,
        excluded_urls="health,metrics"  # Exclude health checks from tracing
    )
