"""
Service Discovery Client

Client library for services to register with the service registry
and discover other services in the platform.
"""

import asyncio
import logging
import socket
import time
from typing import Dict, List, Optional, Set, Callable
import uuid

import structlog

from .service_registry import (
    ServiceRegistry, ServiceInfo, ServiceEndpoint, 
    ServiceCapability, ServiceStatus
)


logger = structlog.get_logger(__name__)


class DiscoveryClient:
    """
    Service discovery client for microservices
    
    Provides easy registration and discovery of services with automatic
    health checking and heartbeat management.
    """
    
    def __init__(
        self,
        service_name: str,
        service_version: str = "1.0.0",
        registry_url: str = "redis://localhost:6379",
        tenant_id: Optional[str] = None,
        instance_id: Optional[str] = None,
        heartbeat_interval: int = 30,
        health_check_endpoint: str = "/health",
        auto_register: bool = True
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.tenant_id = tenant_id
        self.instance_id = instance_id or self._generate_instance_id()
        self.heartbeat_interval = heartbeat_interval
        self.health_check_endpoint = health_check_endpoint
        self.auto_register = auto_register
        
        # Service registry connection
        self.registry = ServiceRegistry(
            redis_url=registry_url,
            heartbeat_interval=heartbeat_interval
        )
        
        # Service configuration
        self.endpoints: Dict[str, ServiceEndpoint] = {}
        self.capabilities: Set[ServiceCapability] = set()
        self.metadata: Dict[str, str] = {}
        self.tags: Set[str] = set()
        
        # State management
        self.is_registered = False
        self.is_healthy = True
        self._health_check_callbacks: List[Callable[[], bool]] = []
        self._shutdown_callbacks: List[Callable[[], None]] = []
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        
        logger.info(f"Discovery client initialized for {service_name}:{self.instance_id}")
    
    def _generate_instance_id(self) -> str:
        """Generate unique instance ID"""
        hostname = socket.gethostname()
        process_id = str(uuid.uuid4())[:8]
        return f"{hostname}-{process_id}"
    
    async def start(self):
        """Start the discovery client"""
        try:
            # Connect to service registry
            await self.registry.connect()
            
            # Auto-register if enabled
            if self.auto_register:
                await self.register()
            
            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            logger.info(f"Discovery client started for {self.service_name}:{self.instance_id}")
            
        except Exception as e:
            logger.error(f"Failed to start discovery client: {e}")
            raise
    
    async def stop(self):
        """Stop the discovery client"""
        try:
            # Stop health check task
            if self._health_check_task:
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Deregister service
            if self.is_registered:
                await self.deregister()
            
            # Run shutdown callbacks
            for callback in self._shutdown_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.error(f"Shutdown callback error: {e}")
            
            # Disconnect from registry
            await self.registry.disconnect()
            
            logger.info(f"Discovery client stopped for {self.service_name}:{self.instance_id}")
            
        except Exception as e:
            logger.error(f"Error stopping discovery client: {e}")
    
    def add_endpoint(
        self,
        name: str,
        protocol: str,
        host: str,
        port: int,
        path: Optional[str] = None
    ):
        """Add service endpoint"""
        endpoint = ServiceEndpoint(
            protocol=protocol,
            host=host,
            port=port,
            path=path
        )
        self.endpoints[name] = endpoint
        
        logger.debug(f"Added endpoint {name}: {endpoint.url}")
    
    def add_http_endpoint(self, host: str = "0.0.0.0", port: int = 8000, path: Optional[str] = None):
        """Add HTTP endpoint (convenience method)"""
        self.add_endpoint("http", "http", host, port, path)
    
    def add_grpc_endpoint(self, host: str = "0.0.0.0", port: int = 9000):
        """Add gRPC endpoint (convenience method)"""
        self.add_endpoint("grpc", "grpc", host, port)
    
    def add_capability(self, capability: ServiceCapability):
        """Add service capability"""
        self.capabilities.add(capability)
        logger.debug(f"Added capability: {capability.value}")
    
    def add_capabilities(self, capabilities: List[ServiceCapability]):
        """Add multiple capabilities"""
        for capability in capabilities:
            self.add_capability(capability)
    
    def set_metadata(self, key: str, value: str):
        """Set service metadata"""
        self.metadata[key] = value
    
    def add_tag(self, tag: str):
        """Add service tag"""
        self.tags.add(tag)
    
    def add_health_check_callback(self, callback: Callable[[], bool]):
        """Add health check callback"""
        self._health_check_callbacks.append(callback)
    
    def add_shutdown_callback(self, callback: Callable[[], None]):
        """Add shutdown callback"""
        self._shutdown_callbacks.append(callback)
    
    async def register(self) -> bool:
        """Register service with the registry"""
        try:
            # Build health check URL
            health_check_url = None
            if 'http' in self.endpoints and self.health_check_endpoint:
                http_endpoint = self.endpoints['http']
                health_check_url = f"{http_endpoint.url.rstrip('/')}{self.health_check_endpoint}"
            
            # Create service info
            service_info = ServiceInfo(
                name=self.service_name,
                instance_id=self.instance_id,
                version=self.service_version,
                tenant_id=self.tenant_id,
                endpoints=self.endpoints.copy(),
                capabilities=self.capabilities.copy(),
                metadata=self.metadata.copy(),
                status=ServiceStatus.HEALTHY if self.is_healthy else ServiceStatus.UNHEALTHY,
                health_check_url=health_check_url,
                tags=self.tags.copy()
            )
            
            # Register with auto-heartbeat
            success = await self.registry.register_service(service_info, auto_heartbeat=True)
            
            if success:
                self.is_registered = True
                logger.info(f"Successfully registered {self.service_name}:{self.instance_id}")
            else:
                logger.error(f"Failed to register {self.service_name}:{self.instance_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Service registration failed: {e}")
            return False
    
    async def deregister(self) -> bool:
        """Deregister service from the registry"""
        try:
            success = await self.registry.deregister_service(
                self.service_name,
                self.instance_id,
                self.tenant_id
            )
            
            if success:
                self.is_registered = False
                logger.info(f"Successfully deregistered {self.service_name}:{self.instance_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Service deregistration failed: {e}")
            return False
    
    async def update_health_status(self, status: ServiceStatus) -> bool:
        """Update service health status"""
        try:
            success = await self.registry.update_service_health(
                self.service_name,
                self.instance_id,
                status,
                self.tenant_id
            )
            
            if success:
                self.is_healthy = (status == ServiceStatus.HEALTHY)
                logger.debug(f"Updated health status to {status.value}")
            
            return success
            
        except Exception as e:
            logger.error(f"Health status update failed: {e}")
            return False
    
    async def discover_services(
        self,
        service_name: Optional[str] = None,
        capabilities: Optional[List[ServiceCapability]] = None,
        tags: Optional[List[str]] = None,
        healthy_only: bool = True
    ) -> List[ServiceInfo]:
        """Discover services"""
        try:
            status = ServiceStatus.HEALTHY if healthy_only else None
            
            services = await self.registry.discover_services(
                service_name=service_name,
                capabilities=capabilities,
                tags=tags,
                status=status,
                tenant_id=self.tenant_id
            )
            
            logger.debug(f"Discovered {len(services)} services")
            return services
            
        except Exception as e:
            logger.error(f"Service discovery failed: {e}")
            return []
    
    async def get_service_instances(self, service_name: str) -> List[ServiceInfo]:
        """Get all instances of a specific service"""
        return await self.discover_services(service_name=service_name)
    
    async def get_service_by_capability(self, capability: ServiceCapability) -> List[ServiceInfo]:
        """Get services by capability"""
        return await self.discover_services(capabilities=[capability])
    
    async def _health_check_loop(self):
        """Background health check loop"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Run health check callbacks
                health_status = await self._check_service_health()
                
                # Update health status if registered
                if self.is_registered:
                    status = ServiceStatus.HEALTHY if health_status else ServiceStatus.UNHEALTHY
                    await self.update_health_status(status)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
    
    async def _check_service_health(self) -> bool:
        """Check service health using callbacks"""
        if not self._health_check_callbacks:
            return True  # Assume healthy if no callbacks
        
        try:
            # Run all health check callbacks
            for callback in self._health_check_callbacks:
                if asyncio.iscoroutinefunction(callback):
                    result = await callback()
                else:
                    result = callback()
                
                if not result:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Health check callback failed: {e}")
            return False
    
    async def wait_for_service(
        self,
        service_name: str,
        timeout: float = 60.0,
        poll_interval: float = 5.0
    ) -> Optional[ServiceInfo]:
        """Wait for a service to become available"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            services = await self.discover_services(service_name=service_name)
            if services:
                logger.info(f"Service {service_name} is now available")
                return services[0]  # Return first instance
            
            logger.debug(f"Waiting for service {service_name}...")
            await asyncio.sleep(poll_interval)
        
        logger.warning(f"Timeout waiting for service {service_name}")
        return None
    
    def get_service_info(self) -> ServiceInfo:
        """Get current service information"""
        health_check_url = None
        if 'http' in self.endpoints and self.health_check_endpoint:
            http_endpoint = self.endpoints['http']
            health_check_url = f"{http_endpoint.url.rstrip('/')}{self.health_check_endpoint}"
        
        return ServiceInfo(
            name=self.service_name,
            instance_id=self.instance_id,
            version=self.service_version,
            tenant_id=self.tenant_id,
            endpoints=self.endpoints.copy(),
            capabilities=self.capabilities.copy(),
            metadata=self.metadata.copy(),
            status=ServiceStatus.HEALTHY if self.is_healthy else ServiceStatus.UNHEALTHY,
            health_check_url=health_check_url,
            tags=self.tags.copy()
        )


def create_discovery_client(
    service_name: str,
    service_version: str = "1.0.0",
    http_port: Optional[int] = None,
    grpc_port: Optional[int] = None,
    capabilities: Optional[List[ServiceCapability]] = None,
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, str]] = None,
    **kwargs
) -> DiscoveryClient:
    """
    Convenience function to create and configure a discovery client
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        http_port: HTTP port if service provides HTTP API
        grpc_port: gRPC port if service provides gRPC API
        capabilities: Service capabilities
        tags: Service tags
        metadata: Service metadata
        **kwargs: Additional DiscoveryClient arguments
    
    Returns:
        Configured DiscoveryClient
    """
    client = DiscoveryClient(
        service_name=service_name,
        service_version=service_version,
        **kwargs
    )
    
    # Add endpoints
    if http_port:
        client.add_http_endpoint(port=http_port)
        client.add_capability(ServiceCapability.HTTP_API)
    
    if grpc_port:
        client.add_grpc_endpoint(port=grpc_port)
        client.add_capability(ServiceCapability.GRPC_API)
    
    # Add capabilities
    if capabilities:
        client.add_capabilities(capabilities)
    
    # Add tags
    if tags:
        for tag in tags:
            client.add_tag(tag)
    
    # Add metadata
    if metadata:
        for key, value in metadata.items():
            client.set_metadata(key, value)
    
    return client
