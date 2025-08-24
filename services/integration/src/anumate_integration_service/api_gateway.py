"""
Production-grade API Gateway

Provides external access to internal microservices with routing, authentication,
rate limiting, load balancing, and comprehensive monitoring.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urljoin, urlparse
from collections import defaultdict
import uuid

from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import httpx
from pydantic import BaseModel, Field
import structlog

from .service_registry import ServiceRegistry, ServiceInfo, ServiceCapability
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, get_circuit_breaker
from .load_balancer import LoadBalancer, LoadBalancerStrategy


logger = structlog.get_logger(__name__)


class RouteConfig(BaseModel):
    """Route configuration"""
    path: str = Field(..., description="Route path pattern")
    service_name: str = Field(..., description="Target service name")
    rewrite_path: Optional[str] = Field(None, description="Path rewrite pattern")
    strip_prefix: bool = Field(False, description="Strip route prefix")
    timeout: float = Field(30.0, description="Request timeout in seconds")
    retry_attempts: int = Field(3, description="Number of retry attempts")
    circuit_breaker: bool = Field(True, description="Enable circuit breaker")
    rate_limit: Optional[Dict[str, int]] = Field(None, description="Rate limiting config")
    auth_required: bool = Field(True, description="Require authentication")
    allowed_methods: List[str] = Field(["GET", "POST", "PUT", "DELETE", "PATCH"], description="Allowed HTTP methods")


class GatewayConfig(BaseModel):
    """API Gateway configuration"""
    service_name: str = "anumate-api-gateway"
    version: str = "1.0.0"
    title: str = "Anumate API Gateway"
    description: str = "Production API Gateway for Anumate Platform"
    
    # Network settings
    host: str = "0.0.0.0"
    port: int = 8080
    
    # Service discovery
    registry_url: str = "redis://localhost:6379"
    service_refresh_interval: int = 30
    
    # Security
    cors_origins: List[str] = ["*"]
    trusted_hosts: List[str] = ["*"]
    api_key_header: str = "X-API-Key"
    tenant_header: str = "X-Tenant-Id"
    
    # Rate limiting (requests per minute)
    default_rate_limit: int = 1000
    burst_rate_limit: int = 2000
    
    # Circuit breaker defaults
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    
    # Load balancing
    load_balancer_strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN
    
    # Monitoring
    enable_metrics: bool = True
    enable_tracing: bool = True
    log_requests: bool = True


class RequestMetrics:
    """Request metrics tracking"""
    
    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.total_duration = 0.0
        self.routes: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.status_codes: Dict[int, int] = defaultdict(int)
        self.response_times: List[float] = []
        
    def record_request(
        self,
        route: str,
        method: str,
        status_code: int,
        duration: float,
        error: bool = False
    ):
        """Record request metrics"""
        self.request_count += 1
        if error:
            self.error_count += 1
            
        self.total_duration += duration
        self.routes[route][method] += 1
        self.status_codes[status_code] += 1
        
        # Keep last 1000 response times for percentiles
        self.response_times.append(duration)
        if len(self.response_times) > 1000:
            self.response_times.pop(0)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive metrics"""
        avg_duration = self.total_duration / max(self.request_count, 1)
        error_rate = self.error_count / max(self.request_count, 1)
        
        # Calculate percentiles
        sorted_times = sorted(self.response_times)
        p50 = sorted_times[len(sorted_times) // 2] if sorted_times else 0
        p95 = sorted_times[int(len(sorted_times) * 0.95)] if sorted_times else 0
        p99 = sorted_times[int(len(sorted_times) * 0.99)] if sorted_times else 0
        
        return {
            'total_requests': self.request_count,
            'total_errors': self.error_count,
            'error_rate': error_rate,
            'avg_response_time': avg_duration,
            'response_time_p50': p50,
            'response_time_p95': p95,
            'response_time_p99': p99,
            'routes': dict(self.routes),
            'status_codes': dict(self.status_codes)
        }


class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, requests_per_minute: int, burst_capacity: int):
        self.rate = requests_per_minute / 60.0  # requests per second
        self.burst_capacity = burst_capacity
        self.tokens = burst_capacity
        self.last_refill = time.time()
        self.client_buckets: Dict[str, Dict[str, float]] = {}
    
    def _refill_bucket(self, bucket: Dict[str, float]):
        """Refill token bucket"""
        now = time.time()
        elapsed = now - bucket.get('last_refill', now)
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.rate
        bucket['tokens'] = min(self.burst_capacity, bucket.get('tokens', 0) + tokens_to_add)
        bucket['last_refill'] = now
    
    def is_allowed(self, client_id: str, tokens: int = 1) -> bool:
        """Check if request is allowed"""
        if client_id not in self.client_buckets:
            self.client_buckets[client_id] = {
                'tokens': self.burst_capacity,
                'last_refill': time.time()
            }
        
        bucket = self.client_buckets[client_id]
        self._refill_bucket(bucket)
        
        if bucket['tokens'] >= tokens:
            bucket['tokens'] -= tokens
            return True
        
        return False


class APIGateway:
    """
    Production-grade API Gateway
    
    Provides:
    - Dynamic service routing based on service discovery
    - Circuit breaker protection
    - Load balancing across service instances
    - Rate limiting and authentication
    - Request/response transformation
    - Comprehensive monitoring and metrics
    """
    
    def __init__(self, config: GatewayConfig):
        self.config = config
        self.app = FastAPI(
            title=config.title,
            description=config.description,
            version=config.version
        )
        
        # Core components
        self.service_registry = ServiceRegistry(config.registry_url)
        self.load_balancer = LoadBalancer(config.load_balancer_strategy)
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # Monitoring
        self.metrics = RequestMetrics() if config.enable_metrics else None
        
        # Rate limiting
        self.rate_limiter = RateLimiter(
            config.default_rate_limit,
            config.burst_rate_limit
        )
        
        # Route configuration
        self.routes: Dict[str, RouteConfig] = {}
        
        # Service cache
        self._service_cache: Dict[str, List[ServiceInfo]] = {}
        self._cache_refresh_task: Optional[asyncio.Task] = None
        
        self._setup_middleware()
        self._setup_routes()
    
    def _setup_middleware(self):
        """Setup FastAPI middleware"""
        # CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Trusted hosts
        if self.config.trusted_hosts != ["*"]:
            self.app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=self.config.trusted_hosts
            )
        
        # Request logging middleware
        @self.app.middleware("http")
        async def logging_middleware(request: Request, call_next):
            start_time = time.time()
            correlation_id = str(uuid.uuid4())
            
            # Add correlation ID to request state
            request.state.correlation_id = correlation_id
            
            # Log request
            if self.config.log_requests:
                logger.info("Gateway request started",
                           correlation_id=correlation_id,
                           method=request.method,
                           path=request.url.path,
                           client=request.client.host if request.client else "unknown")
            
            try:
                response = await call_next(request)
                duration = time.time() - start_time
                
                # Record metrics
                if self.metrics:
                    self.metrics.record_request(
                        route=request.url.path,
                        method=request.method,
                        status_code=response.status_code,
                        duration=duration,
                        error=response.status_code >= 400
                    )
                
                # Log response
                if self.config.log_requests:
                    logger.info("Gateway request completed",
                               correlation_id=correlation_id,
                               status_code=response.status_code,
                               duration=duration)
                
                return response
                
            except Exception as e:
                duration = time.time() - start_time
                
                # Record error metrics
                if self.metrics:
                    self.metrics.record_request(
                        route=request.url.path,
                        method=request.method,
                        status_code=500,
                        duration=duration,
                        error=True
                    )
                
                logger.error("Gateway request failed",
                            correlation_id=correlation_id,
                            error=str(e),
                            duration=duration)
                
                raise
    
    def _setup_routes(self):
        """Setup API Gateway routes"""
        
        @self.app.get("/")
        async def root():
            """Gateway health and info"""
            return {
                "service": self.config.service_name,
                "version": self.config.version,
                "status": "healthy",
                "timestamp": time.time()
            }
        
        @self.app.get("/health")
        async def health_check():
            """Detailed health check"""
            try:
                # Check service registry connection
                await self.service_registry.redis.ping()
                registry_healthy = True
            except:
                registry_healthy = False
            
            health = {
                "service": self.config.service_name,
                "status": "healthy" if registry_healthy else "degraded",
                "components": {
                    "service_registry": "healthy" if registry_healthy else "unhealthy",
                    "http_client": "healthy",
                    "rate_limiter": "healthy"
                },
                "timestamp": time.time()
            }
            
            status_code = 200 if registry_healthy else 503
            return JSONResponse(content=health, status_code=status_code)
        
        @self.app.get("/metrics")
        async def get_metrics():
            """Get gateway metrics"""
            if not self.metrics:
                raise HTTPException(status_code=404, detail="Metrics not enabled")
            
            return self.metrics.get_stats()
        
        @self.app.get("/routes")
        async def get_routes():
            """Get configured routes"""
            return {
                "routes": {path: route.dict() for path, route in self.routes.items()},
                "services": await self._get_service_summary()
            }
        
        # Catch-all route for service proxying
        @self.app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
        async def proxy_request(request: Request, path: str):
            """Proxy request to backend service"""
            return await self._proxy_request(request, path)
    
    async def _proxy_request(self, request: Request, path: str) -> Response:
        """Proxy request to backend service"""
        start_time = time.time()
        correlation_id = getattr(request.state, 'correlation_id', str(uuid.uuid4()))
        
        try:
            # Find matching route
            route_config = await self._find_route(path, request.method)
            if not route_config:
                raise HTTPException(status_code=404, detail=f"Route not found: {path}")
            
            # Authentication check
            if route_config.auth_required:
                await self._authenticate_request(request)
            
            # Rate limiting
            client_id = self._get_client_id(request)
            if not self.rate_limiter.is_allowed(client_id):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            
            # Service discovery
            service_instances = await self._discover_service_instances(route_config.service_name)
            if not service_instances:
                raise HTTPException(status_code=503, detail=f"Service {route_config.service_name} unavailable")
            
            # Load balancing
            target_service = self.load_balancer.select(service_instances)
            if not target_service:
                raise HTTPException(status_code=503, detail="No healthy service instances")
            
            # Build target URL
            target_url = await self._build_target_url(target_service, path, route_config)
            
            # Get circuit breaker
            circuit_breaker = None
            if route_config.circuit_breaker:
                cb_config = CircuitBreakerConfig(
                    failure_threshold=self.config.circuit_breaker_failure_threshold,
                    recovery_timeout=self.config.circuit_breaker_recovery_timeout,
                    timeout_threshold=route_config.timeout
                )
                circuit_breaker = get_circuit_breaker(
                    f"{route_config.service_name}-{target_service.instance_id}",
                    cb_config
                )
            
            # Proxy the request
            response = await self._execute_proxy_request(
                request, target_url, route_config, circuit_breaker, correlation_id
            )
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            duration = time.time() - start_time
            logger.error("Proxy request failed",
                        correlation_id=correlation_id,
                        path=path,
                        error=str(e),
                        duration=duration)
            
            raise HTTPException(status_code=502, detail="Gateway error")
    
    async def _find_route(self, path: str, method: str) -> Optional[RouteConfig]:
        """Find matching route configuration"""
        # First try exact matches
        if path in self.routes:
            route = self.routes[path]
            if method in route.allowed_methods:
                return route
        
        # Then try prefix matches (longest first)
        sorted_routes = sorted(self.routes.items(), key=lambda x: len(x[0]), reverse=True)
        for route_path, route_config in sorted_routes:
            if path.startswith(route_path) and method in route_config.allowed_methods:
                return route_config
        
        # Auto-route based on path segments
        path_segments = path.strip('/').split('/')
        if len(path_segments) >= 2 and path_segments[0] == 'v1':
            service_name = path_segments[1]
            
            # Check if service exists
            services = await self._discover_service_instances(service_name)
            if services:
                # Create dynamic route
                return RouteConfig(
                    path=f"/v1/{service_name}",
                    service_name=service_name,
                    strip_prefix=True,
                    timeout=30.0,
                    circuit_breaker=True,
                    auth_required=True
                )
        
        return None
    
    async def _authenticate_request(self, request: Request):
        """Authenticate request (placeholder - implement your auth logic)"""
        # Check API key
        api_key = request.headers.get(self.config.api_key_header)
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # TODO: Validate API key against auth service
        # For now, accept any non-empty key
        if not api_key.strip():
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting"""
        # Try different identification methods
        client_id = request.headers.get(self.config.api_key_header)
        if client_id:
            return f"api_key:{client_id}"
        
        if request.client:
            return f"ip:{request.client.host}"
        
        return "unknown"
    
    async def _discover_service_instances(self, service_name: str) -> List[ServiceInfo]:
        """Discover healthy service instances"""
        # Check cache first
        if service_name in self._service_cache:
            return self._service_cache[service_name]
        
        # Discover from registry
        services = await self.service_registry.discover_services(
            service_name=service_name,
            status=None  # Get all services, we'll filter by health
        )
        
        # Filter healthy services
        healthy_services = [s for s in services if s.status.value == "healthy"]
        
        # Update cache
        self._service_cache[service_name] = healthy_services
        
        return healthy_services
    
    async def _build_target_url(
        self,
        service: ServiceInfo,
        original_path: str,
        route_config: RouteConfig
    ) -> str:
        """Build target URL for service"""
        # Get primary endpoint
        endpoint = None
        if 'http' in service.endpoints:
            endpoint = service.endpoints['http']
        elif 'https' in service.endpoints:
            endpoint = service.endpoints['https']
        else:
            # Use first available endpoint
            endpoint = next(iter(service.endpoints.values()))
        
        if not endpoint:
            raise HTTPException(status_code=503, detail="No HTTP endpoint available")
        
        # Build base URL
        base_url = endpoint.url
        
        # Apply path transformations
        target_path = original_path
        
        if route_config.strip_prefix:
            # Remove route prefix from path
            if original_path.startswith(route_config.path):
                target_path = original_path[len(route_config.path):]
                if not target_path.startswith('/'):
                    target_path = '/' + target_path
        
        if route_config.rewrite_path:
            target_path = route_config.rewrite_path
        
        return urljoin(base_url, target_path.lstrip('/'))
    
    async def _execute_proxy_request(
        self,
        request: Request,
        target_url: str,
        route_config: RouteConfig,
        circuit_breaker: Optional[CircuitBreaker],
        correlation_id: str
    ) -> Response:
        """Execute proxied request with circuit breaker protection"""
        
        async def make_request():
            # Prepare headers
            headers = dict(request.headers)
            headers['X-Gateway-Correlation-ID'] = correlation_id
            
            # Remove hop-by-hop headers
            hop_by_hop_headers = {
                'connection', 'keep-alive', 'proxy-authenticate',
                'proxy-authorization', 'te', 'trailers', 'transfer-encoding', 'upgrade'
            }
            headers = {k: v for k, v in headers.items() if k.lower() not in hop_by_hop_headers}
            
            # Get request body
            body = None
            if request.method in ['POST', 'PUT', 'PATCH']:
                body = await request.body()
            
            # Make request
            response = await self.http_client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
                timeout=route_config.timeout
            )
            
            return response
        
        # Execute with or without circuit breaker
        if circuit_breaker:
            httpx_response = await circuit_breaker.call(make_request)
        else:
            httpx_response = await make_request()
        
        # Build response
        response_headers = dict(httpx_response.headers)
        
        # Remove hop-by-hop headers from response
        response_headers = {
            k: v for k, v in response_headers.items()
            if k.lower() not in {'connection', 'transfer-encoding'}
        }
        
        return Response(
            content=httpx_response.content,
            status_code=httpx_response.status_code,
            headers=response_headers
        )
    
    async def _get_service_summary(self) -> Dict[str, Any]:
        """Get summary of available services"""
        all_services = await self.service_registry.discover_services()
        
        summary = {}
        for service in all_services:
            if service.name not in summary:
                summary[service.name] = {
                    'instances': 0,
                    'healthy_instances': 0,
                    'capabilities': list(service.capabilities),
                    'endpoints': {}
                }
            
            summary[service.name]['instances'] += 1
            if service.status.value == 'healthy':
                summary[service.name]['healthy_instances'] += 1
            
            # Merge endpoints
            for name, endpoint in service.endpoints.items():
                if name not in summary[service.name]['endpoints']:
                    summary[service.name]['endpoints'][name] = []
                summary[service.name]['endpoints'][name].append(endpoint.url)
        
        return summary
    
    async def add_route(self, route_config: RouteConfig):
        """Add route configuration"""
        self.routes[route_config.path] = route_config
        logger.info(f"Added route {route_config.path} -> {route_config.service_name}")
    
    async def remove_route(self, path: str) -> bool:
        """Remove route configuration"""
        if path in self.routes:
            del self.routes[path]
            logger.info(f"Removed route {path}")
            return True
        return False
    
    async def start(self):
        """Start the API Gateway"""
        logger.info("Starting API Gateway", config=self.config)
        
        # Connect to service registry
        await self.service_registry.connect()
        
        # Start service cache refresh task
        self._cache_refresh_task = asyncio.create_task(self._refresh_service_cache())
        
        logger.info("API Gateway started successfully")
    
    async def stop(self):
        """Stop the API Gateway"""
        logger.info("Stopping API Gateway")
        
        # Stop cache refresh task
        if self._cache_refresh_task:
            self._cache_refresh_task.cancel()
        
        # Close HTTP client
        await self.http_client.aclose()
        
        # Disconnect from service registry
        await self.service_registry.disconnect()
        
        logger.info("API Gateway stopped")
    
    async def _refresh_service_cache(self):
        """Periodically refresh service cache"""
        while True:
            try:
                await asyncio.sleep(self.config.service_refresh_interval)
                
                # Clear cache to force refresh
                self._service_cache.clear()
                
                logger.debug("Service cache refreshed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Service cache refresh error: {e}")
