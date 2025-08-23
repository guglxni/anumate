"""
A.27 Audit Service Integration Middleware
========================================

Middleware components to integrate the Audit Service with other Anumate services.
Provides easy-to-use decorators and client libraries for automatic audit logging.
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Callable, Union
from contextlib import asynccontextmanager
from functools import wraps

import aiohttp
import logging
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AuditClient:
    """
    Asynchronous client for the Audit Service.
    
    Provides high-level methods for logging audit events from other services.
    """
    
    def __init__(
        self, 
        audit_service_url: str = "http://audit-service:8007",
        timeout: int = 5,
        retry_attempts: int = 3,
        buffer_size: int = 100
    ):
        self.audit_service_url = audit_service_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.retry_attempts = retry_attempts
        self.buffer_size = buffer_size
        self._session: Optional[aiohttp.ClientSession] = None
        self._event_buffer: List[Dict[str, Any]] = []
        self._buffer_lock = asyncio.Lock()
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
        
    async def close(self):
        """Close the HTTP session and flush any buffered events."""
        await self.flush_buffer()
        if self._session and not self._session.closed:
            await self._session.close()
            
    async def log_event(
        self,
        tenant_id: str,
        event_type: str,
        event_category: str,
        event_action: str,
        service_name: str,
        event_description: str,
        event_severity: str = "info",
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        success: bool = True,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None,
        request_id: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        event_data: Optional[Dict[str, Any]] = None,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        compliance_tags: Optional[List[str]] = None,
        buffered: bool = False
    ) -> Optional[str]:
        """
        Log an audit event.
        
        Args:
            buffered: If True, event will be buffered and sent in batches
            
        Returns:
            Event ID if sent immediately, None if buffered
        """
        event_data_dict = {
            "tenant_id": tenant_id,
            "event_type": event_type,
            "event_category": event_category,
            "event_action": event_action,
            "event_severity": event_severity,
            "service_name": service_name,
            "event_description": event_description,
            "success": success,
            "user_id": user_id,
            "client_ip": client_ip,
            "error_code": error_code,
            "error_message": error_message,
            "correlation_id": correlation_id,
            "request_id": request_id,
            "processing_time_ms": processing_time_ms,
            "event_data": event_data,
            "request_data": request_data,
            "response_data": response_data,
            "tags": tags or [],
            "compliance_tags": compliance_tags or []
        }
        
        # Remove None values
        event_data_dict = {k: v for k, v in event_data_dict.items() if v is not None}
        
        if buffered:
            await self._add_to_buffer(event_data_dict)
            return None
        else:
            return await self._send_event(event_data_dict)
            
    async def _send_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Send a single event to the audit service."""
        session = await self._get_session()
        url = f"{self.audit_service_url}/v1/audit/events"
        
        for attempt in range(self.retry_attempts):
            try:
                async with session.post(url, json=event_data) as response:
                    if response.status == 201:
                        result = await response.json()
                        return result.get("event_id")
                    else:
                        logger.warning(f"Audit service returned status {response.status}")
                        
            except Exception as e:
                logger.error(f"Failed to send audit event (attempt {attempt + 1}): {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                    
        return None
        
    async def _add_to_buffer(self, event_data: Dict[str, Any]):
        """Add event to buffer for batch processing."""
        async with self._buffer_lock:
            self._event_buffer.append(event_data)
            
            if len(self._event_buffer) >= self.buffer_size:
                await self._flush_buffer_unsafe()
                
    async def _flush_buffer_unsafe(self):
        """Flush buffer without acquiring lock (internal use)."""
        if not self._event_buffer:
            return
            
        events_to_send = self._event_buffer.copy()
        self._event_buffer.clear()
        
        # Send events in background to avoid blocking
        asyncio.create_task(self._send_buffered_events(events_to_send))
        
    async def flush_buffer(self):
        """Flush any buffered events immediately."""
        async with self._buffer_lock:
            await self._flush_buffer_unsafe()
            
    async def _send_buffered_events(self, events: List[Dict[str, Any]]):
        """Send multiple events to the audit service."""
        session = await self._get_session()
        url = f"{self.audit_service_url}/v1/audit/events/batch"
        
        try:
            async with session.post(url, json={"events": events}) as response:
                if response.status != 201:
                    logger.warning(f"Batch audit failed with status {response.status}")
        except Exception as e:
            logger.error(f"Failed to send batch audit events: {e}")
            
    async def log_authentication(
        self,
        tenant_id: str,
        service_name: str,
        user_id: str,
        success: bool,
        authentication_method: str = "unknown",
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        error_message: Optional[str] = None,
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Log authentication events."""
        return await self.log_event(
            tenant_id=tenant_id,
            event_type="user_authentication",
            event_category="security",
            event_action="login" if success else "login_failure",
            event_severity="info" if success else "warning",
            service_name=service_name,
            user_id=user_id,
            client_ip=client_ip,
            success=success,
            error_message=error_message,
            correlation_id=correlation_id,
            event_description=f"User authentication {'successful' if success else 'failed'}",
            event_data={
                "authentication_method": authentication_method,
                "user_agent": user_agent
            },
            compliance_tags=["authentication", "security"]
        )
        
    async def log_data_access(
        self,
        tenant_id: str,
        service_name: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        client_ip: Optional[str] = None,
        correlation_id: Optional[str] = None,
        sensitive_data: bool = False
    ) -> Optional[str]:
        """Log data access events."""
        return await self.log_event(
            tenant_id=tenant_id,
            event_type="data_access",
            event_category="data",
            event_action=action,
            event_severity="warning" if sensitive_data else "info",
            service_name=service_name,
            user_id=user_id,
            client_ip=client_ip,
            success=success,
            correlation_id=correlation_id,
            event_description=f"User {action} {resource_type}",
            event_data={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "sensitive_data": sensitive_data
            },
            compliance_tags=["data_access", "gdpr"] if sensitive_data else ["data_access"]
        )
        
    async def log_system_event(
        self,
        tenant_id: str,
        service_name: str,
        event_type: str,
        event_description: str,
        event_severity: str = "info",
        success: bool = True,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        correlation_id: Optional[str] = None
    ) -> Optional[str]:
        """Log system events."""
        return await self.log_event(
            tenant_id=tenant_id,
            event_type=event_type,
            event_category="system",
            event_action="system_operation",
            event_severity=event_severity,
            service_name=service_name,
            success=success,
            error_code=error_code,
            error_message=error_message,
            processing_time_ms=processing_time_ms,
            correlation_id=correlation_id,
            event_description=event_description
        )


class AuditMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic audit logging.
    
    Logs HTTP requests/responses automatically with configurable filters.
    """
    
    def __init__(
        self,
        app,
        audit_client: AuditClient,
        service_name: str,
        tenant_id_extractor: Callable[[Request], str] = None,
        user_id_extractor: Callable[[Request], Optional[str]] = None,
        skip_paths: List[str] = None,
        skip_methods: List[str] = None,
        log_request_body: bool = False,
        log_response_body: bool = False,
        sensitive_headers: List[str] = None
    ):
        super().__init__(app)
        self.audit_client = audit_client
        self.service_name = service_name
        self.tenant_id_extractor = tenant_id_extractor or self._default_tenant_extractor
        self.user_id_extractor = user_id_extractor or self._default_user_extractor
        self.skip_paths = set(skip_paths or ["/health", "/metrics", "/docs", "/openapi.json"])
        self.skip_methods = set(skip_methods or ["OPTIONS"])
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.sensitive_headers = set(h.lower() for h in (sensitive_headers or [
            "authorization", "x-api-key", "cookie", "x-auth-token"
        ]))
        
    def _default_tenant_extractor(self, request: Request) -> str:
        """Default tenant ID extraction from request."""
        # Try header first
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id:
            return tenant_id
            
        # Try path parameter
        if hasattr(request, "path_params") and "tenant_id" in request.path_params:
            return request.path_params["tenant_id"]
            
        # Try query parameter
        return request.query_params.get("tenant_id", "unknown")
        
    def _default_user_extractor(self, request: Request) -> Optional[str]:
        """Default user ID extraction from request."""
        # Try header first
        user_id = request.headers.get("x-user-id")
        if user_id:
            return user_id
            
        # Try to extract from JWT token (simplified)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # In a real implementation, you would decode the JWT
            # For now, just return a placeholder
            return "jwt_user"
            
        return None
        
    def _extract_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP from request."""
        # Check X-Forwarded-For header first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
            
        # Check X-Real-IP header
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
            
        # Fallback to client host
        if hasattr(request, "client") and request.client:
            return request.client.host
            
        return None
        
    def _filter_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Filter sensitive headers from logging."""
        filtered = {}
        for name, value in headers.items():
            if name.lower() in self.sensitive_headers:
                filtered[name] = "[REDACTED]"
            else:
                filtered[name] = value
        return filtered
        
    async def dispatch(self, request: Request, call_next):
        """Process request and response for audit logging."""
        # Skip certain paths and methods
        if (request.url.path in self.skip_paths or 
            request.method in self.skip_methods):
            return await call_next(request)
            
        # Extract context information
        tenant_id = self.tenant_id_extractor(request)
        user_id = self.user_id_extractor(request)
        client_ip = self._extract_client_ip(request)
        correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        
        # Capture request data
        request_start_time = time.time()
        request_data = {
            "method": request.method,
            "url": str(request.url),
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "headers": self._filter_headers(dict(request.headers))
        }
        
        # Capture request body if enabled
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    # Try to parse as JSON, fallback to string
                    try:
                        request_data["body"] = json.loads(body.decode())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        request_data["body"] = body.decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"Failed to capture request body: {e}")
                
        # Process request
        response = None
        success = True
        error_code = None
        error_message = None
        
        try:
            response = await call_next(request)
            success = 200 <= response.status_code < 400
            
            if not success:
                error_code = str(response.status_code)
                
        except HTTPException as e:
            success = False
            error_code = str(e.status_code)
            error_message = e.detail
            response = Response(status_code=e.status_code)
            
        except Exception as e:
            success = False
            error_code = "500"
            error_message = str(e)
            response = Response(status_code=500)
            
        # Calculate processing time
        processing_time_ms = int((time.time() - request_start_time) * 1000)
        
        # Capture response data
        response_data = {
            "status_code": response.status_code,
            "headers": self._filter_headers(dict(response.headers))
        }
        
        # Capture response body if enabled (for small responses)
        if (self.log_response_body and 
            hasattr(response, "body") and 
            len(getattr(response, "body", b"")) < 10000):  # Limit to 10KB
            try:
                response_data["body"] = response.body.decode("utf-8", errors="replace")
            except Exception:
                pass
                
        # Log audit event asynchronously
        asyncio.create_task(self._log_request_event(
            tenant_id=tenant_id,
            user_id=user_id,
            client_ip=client_ip,
            correlation_id=correlation_id,
            request_id=request_id,
            processing_time_ms=processing_time_ms,
            request_data=request_data,
            response_data=response_data,
            success=success,
            error_code=error_code,
            error_message=error_message
        ))
        
        return response
        
    async def _log_request_event(
        self,
        tenant_id: str,
        user_id: Optional[str],
        client_ip: Optional[str],
        correlation_id: str,
        request_id: str,
        processing_time_ms: int,
        request_data: Dict[str, Any],
        response_data: Dict[str, Any],
        success: bool,
        error_code: Optional[str],
        error_message: Optional[str]
    ):
        """Log the HTTP request as an audit event."""
        try:
            await self.audit_client.log_event(
                tenant_id=tenant_id,
                event_type="http_request",
                event_category="api",
                event_action=request_data["method"].lower(),
                event_severity="info" if success else "warning",
                service_name=self.service_name,
                user_id=user_id,
                client_ip=client_ip,
                success=success,
                error_code=error_code,
                error_message=error_message,
                correlation_id=correlation_id,
                request_id=request_id,
                processing_time_ms=processing_time_ms,
                event_description=f"{request_data['method']} {request_data['path']}",
                request_data=request_data,
                response_data=response_data,
                endpoint=request_data["path"],
                method=request_data["method"],
                response_code=response_data["status_code"],
                buffered=True  # Use buffering for high-volume API logs
            )
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")


def audit_operation(
    event_type: str,
    event_category: str = "business",
    event_action: str = "operation",
    event_severity: str = "info",
    extract_tenant_id: Callable = None,
    extract_user_id: Callable = None,
    log_args: bool = False,
    log_result: bool = False,
    sensitive_args: List[str] = None,
    compliance_tags: List[str] = None
):
    """
    Decorator for automatic audit logging of function calls.
    
    Args:
        event_type: Type of audit event
        event_category: Category of the event
        event_action: Action being performed
        event_severity: Severity level
        extract_tenant_id: Function to extract tenant ID from args/kwargs
        extract_user_id: Function to extract user ID from args/kwargs
        log_args: Whether to log function arguments
        log_result: Whether to log function result
        sensitive_args: List of argument names to redact
        compliance_tags: Compliance tags to add
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract context
            tenant_id = "unknown"
            user_id = None
            
            if extract_tenant_id:
                try:
                    tenant_id = extract_tenant_id(*args, **kwargs)
                except Exception:
                    pass
                    
            if extract_user_id:
                try:
                    user_id = extract_user_id(*args, **kwargs)
                except Exception:
                    pass
                    
            # Prepare event data
            event_data = {
                "function_name": func.__name__,
                "module": func.__module__
            }
            
            if log_args:
                # Filter sensitive arguments
                filtered_kwargs = kwargs.copy()
                if sensitive_args:
                    for sensitive_arg in sensitive_args:
                        if sensitive_arg in filtered_kwargs:
                            filtered_kwargs[sensitive_arg] = "[REDACTED]"
                            
                event_data["arguments"] = {
                    "args": list(args),
                    "kwargs": filtered_kwargs
                }
                
            # Execute function
            start_time = time.time()
            success = True
            error_message = None
            result = None
            
            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                success = False
                error_message = str(e)
                raise
            finally:
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                # Log result if requested and successful
                if log_result and success and result is not None:
                    event_data["result"] = result
                    
                # Get audit client from context (assumes it's available)
                audit_client = getattr(func, '_audit_client', None)
                if audit_client:
                    asyncio.create_task(audit_client.log_event(
                        tenant_id=tenant_id,
                        event_type=event_type,
                        event_category=event_category,
                        event_action=event_action,
                        event_severity=event_severity,
                        service_name=func.__module__.split('.')[0],
                        user_id=user_id,
                        success=success,
                        error_message=error_message,
                        processing_time_ms=processing_time_ms,
                        event_description=f"Function {func.__name__} {'completed' if success else 'failed'}",
                        event_data=event_data,
                        compliance_tags=compliance_tags or [],
                        buffered=True
                    ))
                    
            return result
            
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Similar logic for synchronous functions
            # Implementation would be similar but without async/await
            return func(*args, **kwargs)
            
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


# Context manager for audit session management
@asynccontextmanager
async def audit_session(
    service_name: str,
    audit_service_url: str = "http://audit-service:8007",
    buffer_events: bool = True
):
    """
    Context manager for audit client sessions.
    
    Usage:
        async with audit_session("my-service") as audit:
            await audit.log_authentication(...)
            await audit.log_data_access(...)
    """
    client = AuditClient(audit_service_url)
    try:
        yield client
    finally:
        await client.close()
