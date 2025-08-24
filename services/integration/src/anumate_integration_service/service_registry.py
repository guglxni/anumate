"""
Production-grade Service Registry

Redis-backed service registry with TTL, health status tracking, and service discovery.
Supports multi-tenant service isolation and advanced query capabilities.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import aioredis
from pydantic import BaseModel, Field, validator


logger = logging.getLogger(__name__)


class ServiceStatus(str, Enum):
    """Service health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy" 
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class ServiceCapability(str, Enum):
    """Service capability types"""
    HTTP_API = "http_api"
    GRPC_API = "grpc_api" 
    EVENT_PUBLISHER = "event_publisher"
    EVENT_SUBSCRIBER = "event_subscriber"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    AUDIT = "audit"


@dataclass
class ServiceEndpoint:
    """Service endpoint configuration"""
    protocol: str  # http, https, grpc, tcp
    host: str
    port: int
    path: Optional[str] = None
    
    @property
    def url(self) -> str:
        """Get full endpoint URL"""
        base = f"{self.protocol}://{self.host}:{self.port}"
        if self.path:
            base += self.path if self.path.startswith('/') else f"/{self.path}"
        return base
    
    def __post_init__(self):
        if not self.host:
            raise ValueError("Host cannot be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")


@dataclass 
class ServiceInfo:
    """Service registration information"""
    name: str
    instance_id: str
    version: str
    tenant_id: Optional[str] = None
    endpoints: Dict[str, ServiceEndpoint] = None
    capabilities: Set[ServiceCapability] = None
    metadata: Dict[str, str] = None
    status: ServiceStatus = ServiceStatus.STARTING
    health_check_url: Optional[str] = None
    tags: Set[str] = None
    registered_at: float = None
    last_heartbeat: float = None
    
    def __post_init__(self):
        if not self.endpoints:
            self.endpoints = {}
        if not self.capabilities:
            self.capabilities = set()
        if not self.metadata:
            self.metadata = {}
        if not self.tags:
            self.tags = set()
        if not self.registered_at:
            self.registered_at = time.time()
        if not self.last_heartbeat:
            self.last_heartbeat = time.time()
            
    def to_dict(self) -> Dict:
        """Convert to dictionary for Redis storage"""
        data = asdict(self)
        # Convert sets to lists for JSON serialization
        data['capabilities'] = list(self.capabilities)
        data['tags'] = list(self.tags)
        # Convert enum to string
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ServiceInfo':
        """Create from dictionary from Redis"""
        # Convert lists back to sets
        data['capabilities'] = set(ServiceCapability(cap) for cap in data.get('capabilities', []))
        data['tags'] = set(data.get('tags', []))
        # Convert string back to enum
        data['status'] = ServiceStatus(data.get('status', ServiceStatus.UNKNOWN.value))
        # Reconstruct endpoints
        endpoints_data = data.get('endpoints', {})
        endpoints = {}
        for name, endpoint_data in endpoints_data.items():
            endpoints[name] = ServiceEndpoint(**endpoint_data)
        data['endpoints'] = endpoints
        
        return cls(**data)


class ServiceRegistry:
    """
    Production-grade service registry with Redis backend
    
    Features:
    - Service registration with TTL
    - Health status tracking
    - Service discovery with filtering
    - Multi-tenant isolation
    - Event-driven updates
    - Metrics and monitoring
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        service_ttl: int = 60,  # Service TTL in seconds
        heartbeat_interval: int = 30,  # Heartbeat interval in seconds
        key_prefix: str = "anumate:services",
        enable_events: bool = True
    ):
        self.redis_url = redis_url
        self.service_ttl = service_ttl
        self.heartbeat_interval = heartbeat_interval
        self.key_prefix = key_prefix
        self.enable_events = enable_events
        
        self.redis: Optional[aioredis.Redis] = None
        self._services_cache: Dict[str, ServiceInfo] = {}
        self._cache_last_updated: float = 0
        self._cache_ttl: int = 10  # Cache TTL in seconds
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self._event_listeners: Dict[str, List] = {
            'service_registered': [],
            'service_deregistered': [],
            'service_health_changed': [],
        }
        
    async def connect(self):
        """Connect to Redis"""
        try:
            self.redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            logger.info("Connected to Redis service registry")
            
            if self.enable_events:
                await self._setup_event_streams()
                
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Redis and cleanup"""
        # Cancel all heartbeat tasks
        for task in self._heartbeat_tasks.values():
            task.cancel()
        
        if self.redis:
            await self.redis.close()
            self.redis = None
        
        logger.info("Disconnected from service registry")
    
    def _service_key(self, service_name: str, instance_id: str, tenant_id: Optional[str] = None) -> str:
        """Generate Redis key for service"""
        if tenant_id:
            return f"{self.key_prefix}:{tenant_id}:{service_name}:{instance_id}"
        return f"{self.key_prefix}:global:{service_name}:{instance_id}"
    
    def _services_pattern(self, tenant_id: Optional[str] = None) -> str:
        """Generate Redis pattern for listing services"""
        if tenant_id:
            return f"{self.key_prefix}:{tenant_id}:*"
        return f"{self.key_prefix}:*"
    
    async def register_service(
        self, 
        service_info: ServiceInfo,
        auto_heartbeat: bool = True
    ) -> bool:
        """
        Register a service in the registry
        
        Args:
            service_info: Service information
            auto_heartbeat: Enable automatic heartbeat
            
        Returns:
            True if registration successful
        """
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            # Update registration time
            service_info.registered_at = time.time()
            service_info.last_heartbeat = time.time()
            
            # Store in Redis with TTL
            key = self._service_key(
                service_info.name, 
                service_info.instance_id,
                service_info.tenant_id
            )
            
            await self.redis.setex(
                key,
                self.service_ttl,
                json.dumps(service_info.to_dict())
            )
            
            # Update local cache
            cache_key = f"{service_info.name}:{service_info.instance_id}"
            self._services_cache[cache_key] = service_info
            
            # Start heartbeat if requested
            if auto_heartbeat:
                await self._start_heartbeat(service_info)
            
            # Emit registration event
            await self._emit_event('service_registered', service_info.to_dict())
            
            logger.info(
                f"Registered service {service_info.name}:{service_info.instance_id} "
                f"with capabilities {service_info.capabilities}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to register service {service_info.name}: {e}")
            return False
    
    async def deregister_service(
        self,
        service_name: str,
        instance_id: str,
        tenant_id: Optional[str] = None
    ) -> bool:
        """
        Deregister a service from the registry
        
        Args:
            service_name: Name of the service
            instance_id: Instance identifier
            tenant_id: Tenant identifier
            
        Returns:
            True if deregistration successful
        """
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            # Remove from Redis
            key = self._service_key(service_name, instance_id, tenant_id)
            
            # Get service info before deletion for event
            service_data = await self.redis.get(key)
            
            deleted = await self.redis.delete(key)
            
            # Stop heartbeat
            heartbeat_key = f"{service_name}:{instance_id}"
            if heartbeat_key in self._heartbeat_tasks:
                self._heartbeat_tasks[heartbeat_key].cancel()
                del self._heartbeat_tasks[heartbeat_key]
            
            # Remove from cache
            cache_key = f"{service_name}:{instance_id}"
            self._services_cache.pop(cache_key, None)
            
            # Emit deregistration event
            if service_data:
                service_info = json.loads(service_data)
                await self._emit_event('service_deregistered', service_info)
            
            if deleted:
                logger.info(f"Deregistered service {service_name}:{instance_id}")
                return True
            else:
                logger.warning(f"Service {service_name}:{instance_id} not found for deregistration")
                return False
                
        except Exception as e:
            logger.error(f"Failed to deregister service {service_name}: {e}")
            return False
    
    async def update_service_health(
        self,
        service_name: str,
        instance_id: str,
        status: ServiceStatus,
        tenant_id: Optional[str] = None
    ) -> bool:
        """Update service health status"""
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            key = self._service_key(service_name, instance_id, tenant_id)
            service_data = await self.redis.get(key)
            
            if not service_data:
                logger.warning(f"Service {service_name}:{instance_id} not found for health update")
                return False
            
            service_info_dict = json.loads(service_data)
            old_status = service_info_dict.get('status')
            
            # Update status and heartbeat
            service_info_dict['status'] = status.value
            service_info_dict['last_heartbeat'] = time.time()
            
            # Store updated info
            await self.redis.setex(
                key,
                self.service_ttl,
                json.dumps(service_info_dict)
            )
            
            # Update cache
            service_info = ServiceInfo.from_dict(service_info_dict)
            cache_key = f"{service_name}:{instance_id}"
            self._services_cache[cache_key] = service_info
            
            # Emit health change event if status changed
            if old_status != status.value:
                event_data = {
                    'service_name': service_name,
                    'instance_id': instance_id,
                    'old_status': old_status,
                    'new_status': status.value,
                    'timestamp': time.time()
                }
                await self._emit_event('service_health_changed', event_data)
                
                logger.info(f"Updated {service_name}:{instance_id} health: {old_status} -> {status.value}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update service health: {e}")
            return False
    
    async def discover_services(
        self,
        service_name: Optional[str] = None,
        capabilities: Optional[List[ServiceCapability]] = None,
        tags: Optional[List[str]] = None,
        status: Optional[ServiceStatus] = ServiceStatus.HEALTHY,
        tenant_id: Optional[str] = None
    ) -> List[ServiceInfo]:
        """
        Discover services with optional filtering
        
        Args:
            service_name: Filter by service name
            capabilities: Filter by required capabilities
            tags: Filter by tags
            status: Filter by health status
            tenant_id: Filter by tenant
            
        Returns:
            List of matching services
        """
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            # Use cache if fresh
            if time.time() - self._cache_last_updated < self._cache_ttl:
                services = list(self._services_cache.values())
            else:
                # Refresh from Redis
                services = await self._load_services_from_redis(tenant_id)
                self._cache_last_updated = time.time()
            
            # Apply filters
            filtered_services = []
            
            for service in services:
                # Filter by name
                if service_name and service.name != service_name:
                    continue
                
                # Filter by status
                if status and service.status != status:
                    continue
                
                # Filter by tenant
                if tenant_id and service.tenant_id != tenant_id:
                    continue
                
                # Filter by capabilities
                if capabilities:
                    required_caps = set(capabilities)
                    if not required_caps.issubset(service.capabilities):
                        continue
                
                # Filter by tags
                if tags:
                    required_tags = set(tags)
                    if not required_tags.issubset(service.tags):
                        continue
                
                filtered_services.append(service)
            
            logger.debug(f"Discovered {len(filtered_services)} services with filters")
            return filtered_services
            
        except Exception as e:
            logger.error(f"Failed to discover services: {e}")
            return []
    
    async def get_service(
        self,
        service_name: str,
        instance_id: str,
        tenant_id: Optional[str] = None
    ) -> Optional[ServiceInfo]:
        """Get specific service instance"""
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            # Check cache first
            cache_key = f"{service_name}:{instance_id}"
            if cache_key in self._services_cache:
                cached_service = self._services_cache[cache_key]
                # Verify tenant matches
                if tenant_id is None or cached_service.tenant_id == tenant_id:
                    return cached_service
            
            # Load from Redis
            key = self._service_key(service_name, instance_id, tenant_id)
            service_data = await self.redis.get(key)
            
            if not service_data:
                return None
            
            service_info = ServiceInfo.from_dict(json.loads(service_data))
            
            # Update cache
            self._services_cache[cache_key] = service_info
            
            return service_info
            
        except Exception as e:
            logger.error(f"Failed to get service {service_name}:{instance_id}: {e}")
            return None
    
    async def _load_services_from_redis(self, tenant_id: Optional[str] = None) -> List[ServiceInfo]:
        """Load all services from Redis"""
        pattern = self._services_pattern(tenant_id)
        keys = await self.redis.keys(pattern)
        
        services = []
        
        if keys:
            # Get all service data in batch
            service_data_list = await self.redis.mget(keys)
            
            for service_data in service_data_list:
                if service_data:
                    try:
                        service_info = ServiceInfo.from_dict(json.loads(service_data))
                        services.append(service_info)
                        
                        # Update cache
                        cache_key = f"{service_info.name}:{service_info.instance_id}"
                        self._services_cache[cache_key] = service_info
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse service data: {e}")
        
        return services
    
    async def _start_heartbeat(self, service_info: ServiceInfo):
        """Start heartbeat task for a service"""
        heartbeat_key = f"{service_info.name}:{service_info.instance_id}"
        
        # Cancel existing heartbeat if any
        if heartbeat_key in self._heartbeat_tasks:
            self._heartbeat_tasks[heartbeat_key].cancel()
        
        # Start new heartbeat task
        task = asyncio.create_task(self._heartbeat_loop(service_info))
        self._heartbeat_tasks[heartbeat_key] = task
    
    async def _heartbeat_loop(self, service_info: ServiceInfo):
        """Heartbeat loop to keep service registration alive"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                # Extend TTL and update heartbeat time
                key = self._service_key(
                    service_info.name,
                    service_info.instance_id, 
                    service_info.tenant_id
                )
                
                # Check if service still exists
                exists = await self.redis.exists(key)
                if not exists:
                    logger.warning(f"Service {service_info.name}:{service_info.instance_id} expired from registry")
                    break
                
                # Update heartbeat time
                service_data = await self.redis.get(key)
                if service_data:
                    service_dict = json.loads(service_data)
                    service_dict['last_heartbeat'] = time.time()
                    
                    await self.redis.setex(
                        key,
                        self.service_ttl,
                        json.dumps(service_dict)
                    )
                
                logger.debug(f"Heartbeat sent for {service_info.name}:{service_info.instance_id}")
                
            except asyncio.CancelledError:
                logger.info(f"Heartbeat cancelled for {service_info.name}:{service_info.instance_id}")
                break
            except Exception as e:
                logger.error(f"Heartbeat error for {service_info.name}:{service_info.instance_id}: {e}")
                # Continue heartbeat despite errors
    
    async def _setup_event_streams(self):
        """Setup Redis streams for service events"""
        try:
            # Create event streams if they don't exist
            streams = [
                f"{self.key_prefix}:events:registered",
                f"{self.key_prefix}:events:deregistered", 
                f"{self.key_prefix}:events:health_changed"
            ]
            
            for stream in streams:
                try:
                    await self.redis.xgroup_create(stream, "integration_service", id="$", mkstream=True)
                except Exception:
                    # Group might already exist
                    pass
                    
            logger.info("Service registry event streams initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup event streams: {e}")
    
    async def _emit_event(self, event_type: str, data: Dict):
        """Emit service registry event"""
        if not self.enable_events or not self.redis:
            return
        
        try:
            stream_name = f"{self.key_prefix}:events:{event_type.replace('service_', '')}"
            
            event_data = {
                'type': event_type,
                'timestamp': str(time.time()),
                'data': json.dumps(data)
            }
            
            await self.redis.xadd(stream_name, event_data)
            
            # Notify local listeners
            if event_type in self._event_listeners:
                for listener in self._event_listeners[event_type]:
                    try:
                        await listener(data)
                    except Exception as e:
                        logger.error(f"Event listener error: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to emit event {event_type}: {e}")
    
    def add_event_listener(self, event_type: str, listener):
        """Add event listener for service registry events"""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(listener)
    
    def remove_event_listener(self, event_type: str, listener):
        """Remove event listener"""
        if event_type in self._event_listeners:
            try:
                self._event_listeners[event_type].remove(listener)
            except ValueError:
                pass
    
    async def get_registry_stats(self) -> Dict:
        """Get service registry statistics"""
        if not self.redis:
            raise RuntimeError("Registry not connected")
        
        try:
            # Count services by status
            services = await self._load_services_from_redis()
            
            stats = {
                'total_services': len(services),
                'services_by_status': {},
                'services_by_capability': {},
                'services_by_tenant': {},
                'registry_uptime': time.time() - getattr(self, '_start_time', time.time()),
                'cache_hit_rate': getattr(self, '_cache_hits', 0) / max(getattr(self, '_cache_requests', 1), 1),
                'active_heartbeats': len(self._heartbeat_tasks)
            }
            
            # Count by status
            for service in services:
                status = service.status.value
                stats['services_by_status'][status] = stats['services_by_status'].get(status, 0) + 1
            
            # Count by capabilities  
            for service in services:
                for capability in service.capabilities:
                    cap_name = capability.value
                    stats['services_by_capability'][cap_name] = stats['services_by_capability'].get(cap_name, 0) + 1
            
            # Count by tenant
            for service in services:
                tenant = service.tenant_id or 'global'
                stats['services_by_tenant'][tenant] = stats['services_by_tenant'].get(tenant, 0) + 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get registry stats: {e}")
            return {}
