"""OpenTelemetry tracing setup for Sentinel Node Orchestrator.

Configures OpenTelemetry SDK with OTLP exporter and provides span decorators
for instrumenting critical paths.
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from functools import wraps
import logging
from typing import Callable, Any, Optional
from .config import settings

logger = logging.getLogger(__name__)

# Global tracer instance
_tracer: Optional[trace.Tracer] = None


def setup_tracing(service_name: str = "sentinel-orchestrator", service_version: str = "1.0.0") -> None:
    """Initialize OpenTelemetry tracing with OTLP exporter.
    
    Args:
        service_name: Name of the service for tracing
        service_version: Version of the service
    """
    global _tracer
    
    # Create resource with service info
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })
    
    # Configure tracer provider
    provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter (gRPC by default, pointing to localhost:4317)
    # Can be overridden with OTEL_EXPORTER_OTLP_ENDPOINT environment variable
    otlp_exporter = OTLPSpanExporter()
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    # Set global tracer provider
    trace.set_tracer_provider(provider)
    
    # Get tracer for this module
    _tracer = trace.get_tracer(__name__)
    
    # Auto-instrument FastAPI (will be called when app is passed)
    # Auto-instrument Redis
    RedisInstrumentor().instrument()
    
    logger.info(f"OpenTelemetry tracing initialized for {service_name} v{service_version}")


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance.
    
    Returns:
        Tracer instance
    
    Raises:
        RuntimeError: If tracing not initialized
    """
    if _tracer is None:
        raise RuntimeError("Tracing not initialized. Call setup_tracing() first.")
    return _tracer


def instrument_fastapi(app: Any) -> None:
    """Instrument a FastAPI application with OpenTelemetry.
    
    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI instrumented with OpenTelemetry")


def trace_async(span_name: str, **span_attributes):
    """Decorator for async functions to create tracing spans.
    
    Args:
        span_name: Name of the span
        **span_attributes: Additional attributes to add to the span
        
    Example:
        @trace_async("execute_task", task_type="graph")
        async def my_task():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                for key, value in span_attributes.items():
                    span.set_attribute(key, value)
                
                # Execute function
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def trace_sync(span_name: str, **span_attributes):
    """Decorator for sync functions to create tracing spans.
    
    Args:
        span_name: Name of the span
        **span_attributes: Additional attributes to add to the span
        
    Example:
        @trace_sync("validate_config", config_type="agent")
        def validate():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Add custom attributes
                for key, value in span_attributes.items():
                    span.set_attribute(key, value)
                
                # Execute function
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("success", True)
                    return result
                except Exception as e:
                    span.set_attribute("success", False)
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


def add_span_attributes(**attributes):
    """Add attributes to the current active span.
    
    Args:
        **attributes: Key-value pairs to add as span attributes
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[dict] = None):
    """Add an event to the current active span.
    
    Args:
        name: Event name
        attributes: Optional event attributes
    """
    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes=attributes or {})
