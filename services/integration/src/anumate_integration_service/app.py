"""
Production Integration Service Application

Main FastAPI application providing service integration patterns
for the Anumate platform with comprehensive monitoring and management.
"""

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import structlog
import uvicorn

from .service_registry import ServiceRegistry, ServiceInfo, ServiceCapability, ServiceStatus
from .circuit_breaker import get_circuit_breaker, CircuitBreakerConfig
from .api_gateway import APIGateway, GatewayConfig, RouteConfig
from .health_manager import HealthManager, HealthCheckConfig, HealthCheckType
from .discovery_client import create_discovery_client
from .load_balancer import LoadBalancer, LoadBalancerStrategy


logger = structlog.get_logger(__name__)


class IntegrationServiceConfig(BaseModel):
    """Integration service configuration"""
    service_name: str = "anumate-integration-service"
    version: str = "1.0.0"
    title: str = "Anumate Integration Service"
    description: str = "Production service integration patterns and infrastructure"
    
    # Network
    host: str = "0.0.0.0"
    port: int = 8090
    
    # Service registry
    redis_url: str = "redis://localhost:6379"
    
    # Gateway configuration
    gateway_enabled: bool = True
    gateway_port: int = 8080
    
    # Health manager
    health_manager_enabled: bool = True
    default_health_check_interval: int = 30
    
    # Circuit breaker defaults
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: float = 60.0
    
    # Load balancer
    load_balancer_strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN


# Request/Response models
class ServiceRegistrationRequest(BaseModel):
    """Service registration request"""
    name: str = Field(..., description="Service name")
    version: str = Field("1.0.0", description="Service version")
    instance_id: Optional[str] = Field(None, description="Instance ID")
    endpoints: Dict[str, Dict[str, Any]] = Field(..., description="Service endpoints")
    capabilities: List[str] = Field(default_factory=list, description="Service capabilities")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Service metadata")
    tags: List[str] = Field(default_factory=list, description="Service tags")


class RouteConfigRequest(BaseModel):
    """Route configuration request"""
    path: str = Field(..., description="Route path")
    service_name: str = Field(..., description="Target service name")
    rewrite_path: Optional[str] = Field(None, description="Path rewrite")
    strip_prefix: bool = Field(False, description="Strip route prefix")
    timeout: float = Field(30.0, description="Request timeout")
    circuit_breaker: bool = Field(True, description="Enable circuit breaker")
    auth_required: bool = Field(True, description="Require authentication")


class HealthCheckConfigRequest(BaseModel):
    """Health check configuration request"""
    service_name: str = Field(..., description="Service name")
    instance_id: str = Field(..., description="Instance ID")
    check_type: str = Field(..., description="Health check type")
    interval: int = Field(30, description="Check interval in seconds")
    timeout: int = Field(10, description="Check timeout in seconds")
    healthy_threshold: int = Field(2, description="Healthy threshold")
    unhealthy_threshold: int = Field(3, description="Unhealthy threshold")


class IntegrationService:
    """Main integration service"""
    
    def __init__(self, config: IntegrationServiceConfig):
        self.config = config
        
        # Core components
        self.service_registry = ServiceRegistry(config.redis_url)
        self.health_manager = HealthManager(self.service_registry) if config.health_manager_enabled else None
        self.api_gateway = None
        self.load_balancer = LoadBalancer(config.load_balancer_strategy)
        
        # Discovery client for self-registration
        self.discovery_client = create_discovery_client(
            service_name=config.service_name,
            service_version=config.version,
            http_port=config.port,
            capabilities=[ServiceCapability.HTTP_API, ServiceCapability.AUTHENTICATION],
            tags=["integration", "infrastructure", "gateway"],
            registry_url=config.redis_url
        )
        
        # Setup FastAPI app
        self.app = self._create_app()
    
    def _create_app(self) -> FastAPI:
        """Create FastAPI application"""
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Application lifespan"""
            # Startup
            await self.start()
            yield
            # Shutdown
            await self.stop()
        
        app = FastAPI(
            title=self.config.title,
            description=self.config.description,
            version=self.config.version,
            lifespan=lifespan
        )
        
        self._setup_routes(app)
        return app
    
    def _setup_routes(self, app: FastAPI):
        """Setup API routes"""
        
        @app.get("/")
        async def root():
            """Service information"""
            return {
                "service": self.config.service_name,
                "version": self.config.version,
                "status": "healthy",
                "timestamp": time.time(),
                "components": {
                    "service_registry": "enabled",
                    "health_manager": "enabled" if self.health_manager else "disabled",
                    "api_gateway": "enabled" if self.api_gateway else "disabled",
                    "load_balancer": "enabled"
                }
            }
        
        @app.get("/health")
        async def health_check():
            """Detailed health check"""
            try:
                await self.service_registry.redis.ping()
                registry_healthy = True
            except:
                registry_healthy = False
            
            health = {
                "service": self.config.service_name,
                "status": "healthy" if registry_healthy else "degraded",
                "components": {
                    "service_registry": "healthy" if registry_healthy else "unhealthy",
                    "health_manager": "healthy" if self.health_manager else "disabled",
                    "api_gateway": "healthy" if self.api_gateway else "disabled",
                    "load_balancer": "healthy"
                },
                "timestamp": time.time()
            }
            
            status_code = 200 if registry_healthy else 503
            return JSONResponse(content=health, status_code=status_code)
        
        # Service Registry endpoints
        @app.post("/v1/services/register")
        async def register_service(request: ServiceRegistrationRequest):
            """Register a service"""
            try:
                service_info = ServiceInfo(
                    name=request.name,
                    instance_id=request.instance_id or f"{request.name}-instance",
                    version=request.version,
                    endpoints={},  # Will be populated from request
                    capabilities=set(ServiceCapability(cap) for cap in request.capabilities),
                    metadata=request.metadata,
                    tags=set(request.tags)
                )
                
                success = await self.service_registry.register_service(service_info)
                
                if success:
                    return {"message": "Service registered successfully", "instance_id": service_info.instance_id}
                else:
                    raise HTTPException(status_code=500, detail="Service registration failed")
                    
            except Exception as e:
                logger.error(f"Service registration error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @app.delete("/v1/services/{service_name}/{instance_id}")
        async def deregister_service(service_name: str, instance_id: str):
            """Deregister a service"""
            try:
                success = await self.service_registry.deregister_service(service_name, instance_id)
                
                if success:
                    return {"message": "Service deregistered successfully"}
                else:
                    raise HTTPException(status_code=404, detail="Service not found")
                    
            except Exception as e:
                logger.error(f"Service deregistration error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @app.get("/v1/services")
        async def discover_services(
            service_name: Optional[str] = None,
            capability: Optional[str] = None,
            status: Optional[str] = None
        ):
            """Discover services"""
            try:
                capabilities = [ServiceCapability(capability)] if capability else None
                service_status = ServiceStatus(status) if status else None
                
                services = await self.service_registry.discover_services(
                    service_name=service_name,
                    capabilities=capabilities,
                    status=service_status
                )
                
                return {
                    "services": [service.to_dict() for service in services],
                    "count": len(services)
                }
                
            except Exception as e:
                logger.error(f"Service discovery error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @app.get("/v1/services/{service_name}")
        async def get_service_instances(service_name: str):
            """Get all instances of a service"""
            try:
                services = await self.service_registry.discover_services(service_name=service_name)
                
                if not services:
                    raise HTTPException(status_code=404, detail=f"Service {service_name} not found")
                
                return {
                    "service_name": service_name,
                    "instances": [service.to_dict() for service in services],
                    "count": len(services)
                }
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Get service instances error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        # Health Management endpoints
        if self.health_manager:
            @app.get("/v1/health/status")
            async def get_all_health_status():
                """Get health status for all services"""
                try:
                    stats = self.health_manager.get_all_health_stats()
                    return stats
                    
                except Exception as e:
                    logger.error(f"Get health status error: {e}")
                    raise HTTPException(status_code=500, detail=str(e))
            
            @app.post("/v1/health/configure")
            async def configure_health_check(request: HealthCheckConfigRequest):
                """Configure health check for a service"""
                try:
                    config = HealthCheckConfig(
                        check_type=HealthCheckType(request.check_type),
                        interval=request.interval,
                        timeout=request.timeout,
                        healthy_threshold=request.healthy_threshold,
                        unhealthy_threshold=request.unhealthy_threshold
                    )
                    
                    self.health_manager.configure_service_health_check(
                        request.service_name,
                        request.instance_id,
                        config
                    )
                    
                    return {"message": "Health check configured successfully"}
                    
                except Exception as e:
                    logger.error(f"Configure health check error: {e}")
                    raise HTTPException(status_code=400, detail=str(e))
        
        # Circuit Breaker endpoints
        @app.get("/v1/circuit-breakers")
        async def get_circuit_breaker_stats():
            """Get circuit breaker statistics"""
            try:
                from .circuit_breaker import _circuit_breaker_registry
                return _circuit_breaker_registry.get_all_stats()
                
            except Exception as e:
                logger.error(f"Get circuit breaker stats error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/v1/circuit-breakers/{name}/reset")
        async def reset_circuit_breaker(name: str):
            """Reset a circuit breaker"""
            try:
                from .circuit_breaker import _circuit_breaker_registry
                cb = _circuit_breaker_registry.get(name)
                
                if not cb:
                    raise HTTPException(status_code=404, detail="Circuit breaker not found")
                
                cb.reset()
                return {"message": f"Circuit breaker {name} reset successfully"}
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Reset circuit breaker error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        # Load Balancer endpoints
        @app.get("/v1/load-balancer/stats")
        async def get_load_balancer_stats():
            """Get load balancer statistics"""
            try:
                return self.load_balancer.get_load_balancer_stats()
                
            except Exception as e:
                logger.error(f"Get load balancer stats error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @app.post("/v1/load-balancer/strategy")
        async def set_load_balancer_strategy(strategy: str):
            """Set load balancer strategy"""
            try:
                strategy_enum = LoadBalancerStrategy(strategy)
                self.load_balancer.set_strategy(strategy_enum)
                
                return {"message": f"Load balancer strategy set to {strategy}"}
                
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid strategy: {strategy}")
            except Exception as e:
                logger.error(f"Set load balancer strategy error: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        # Gateway management endpoints (if gateway is enabled)
        if self.config.gateway_enabled:
            @app.post("/v1/gateway/routes")
            async def add_gateway_route(request: RouteConfigRequest):
                """Add gateway route"""
                try:
                    if not self.api_gateway:
                        raise HTTPException(status_code=503, detail="API Gateway not enabled")
                    
                    route_config = RouteConfig(
                        path=request.path,
                        service_name=request.service_name,
                        rewrite_path=request.rewrite_path,
                        strip_prefix=request.strip_prefix,
                        timeout=request.timeout,
                        circuit_breaker=request.circuit_breaker,
                        auth_required=request.auth_required
                    )
                    
                    await self.api_gateway.add_route(route_config)
                    
                    return {"message": "Route added successfully"}
                    
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Add gateway route error: {e}")
                    raise HTTPException(status_code=400, detail=str(e))
            
            @app.delete("/v1/gateway/routes/{path:path}")
            async def remove_gateway_route(path: str):
                """Remove gateway route"""
                try:
                    if not self.api_gateway:
                        raise HTTPException(status_code=503, detail="API Gateway not enabled")
                    
                    success = await self.api_gateway.remove_route(f"/{path}")
                    
                    if success:
                        return {"message": "Route removed successfully"}
                    else:
                        raise HTTPException(status_code=404, detail="Route not found")
                        
                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Remove gateway route error: {e}")
                    raise HTTPException(status_code=400, detail=str(e))
            
            @app.get("/v1/gateway/routes")
            async def get_gateway_routes():
                """Get gateway routes"""
                try:
                    if not self.api_gateway:
                        raise HTTPException(status_code=503, detail="API Gateway not enabled")
                    
                    # This would be implemented in the gateway
                    return {"routes": {}, "message": "Gateway routes endpoint"}
                    
                except Exception as e:
                    logger.error(f"Get gateway routes error: {e}")
                    raise HTTPException(status_code=500, detail=str(e))
        
        # Integration metrics and monitoring
        @app.get("/v1/metrics")
        async def get_integration_metrics():
            """Get comprehensive integration metrics"""
            try:
                metrics = {
                    "timestamp": time.time(),
                    "service_registry": await self.service_registry.get_registry_stats(),
                    "load_balancer": self.load_balancer.get_load_balancer_stats(),
                    "system": {
                        "uptime": time.time() - getattr(self, '_start_time', time.time()),
                        "version": self.config.version
                    }
                }
                
                if self.health_manager:
                    metrics["health_manager"] = self.health_manager.get_all_health_stats()
                
                if self.api_gateway and hasattr(self.api_gateway, 'metrics'):
                    metrics["api_gateway"] = self.api_gateway.metrics.get_stats()
                
                return metrics
                
            except Exception as e:
                logger.error(f"Get integration metrics error: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    async def start(self):
        """Start integration service"""
        logger.info("Starting integration service", config=self.config)
        
        self._start_time = time.time()
        
        # Connect to service registry
        await self.service_registry.connect()
        
        # Start health manager
        if self.health_manager:
            await self.health_manager.start()
        
        # Start API Gateway if enabled
        if self.config.gateway_enabled:
            gateway_config = GatewayConfig(
                port=self.config.gateway_port,
                registry_url=self.config.redis_url
            )
            self.api_gateway = APIGateway(gateway_config)
            await self.api_gateway.start()
        
        # Register this service
        await self.discovery_client.start()
        
        logger.info("Integration service started successfully")
    
    async def stop(self):
        """Stop integration service"""
        logger.info("Stopping integration service")
        
        # Stop discovery client
        await self.discovery_client.stop()
        
        # Stop API Gateway
        if self.api_gateway:
            await self.api_gateway.stop()
        
        # Stop health manager
        if self.health_manager:
            await self.health_manager.stop()
        
        # Disconnect from service registry
        await self.service_registry.disconnect()
        
        logger.info("Integration service stopped")


def create_app(config: Optional[IntegrationServiceConfig] = None) -> FastAPI:
    """Create integration service application"""
    if config is None:
        config = IntegrationServiceConfig()
    
    service = IntegrationService(config)
    return service.app


# For direct execution
if __name__ == "__main__":
    import sys
    
    # Setup logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Create and run app
    config = IntegrationServiceConfig()
    app = create_app(config)
    
    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run with uvicorn
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="info",
        access_log=True
    )
