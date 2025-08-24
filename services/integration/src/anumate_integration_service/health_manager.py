"""
Health Check Manager

Centralized health checking for all services in the platform
with configurable checks and monitoring.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
import aiohttp

import structlog

from .service_registry import ServiceRegistry, ServiceInfo, ServiceStatus


logger = structlog.get_logger(__name__)


class HealthCheckType(Enum):
    """Types of health checks"""
    HTTP = "http"
    TCP = "tcp"
    REDIS = "redis"
    DATABASE = "database"
    CUSTOM = "custom"


@dataclass
class HealthCheckConfig:
    """Health check configuration"""
    check_type: HealthCheckType
    interval: int = 30  # seconds
    timeout: int = 10   # seconds
    retries: int = 3
    healthy_threshold: int = 2  # consecutive successes to mark healthy
    unhealthy_threshold: int = 3  # consecutive failures to mark unhealthy
    
    # HTTP-specific
    http_method: str = "GET"
    expected_status: List[int] = None
    expected_body: Optional[str] = None
    
    # TCP-specific
    tcp_port: Optional[int] = None
    
    # Custom check
    custom_checker: Optional[Callable] = None
    
    def __post_init__(self):
        if self.expected_status is None:
            self.expected_status = [200]


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    service_name: str
    instance_id: str
    check_type: HealthCheckType
    success: bool
    response_time: float
    error_message: Optional[str] = None
    timestamp: float = None
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.details is None:
            self.details = {}


class HealthChecker:
    """Individual health checker for a service"""
    
    def __init__(
        self,
        service_info: ServiceInfo,
        config: HealthCheckConfig
    ):
        self.service_info = service_info
        self.config = config
        
        # State tracking
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self.current_status = ServiceStatus.UNKNOWN
        self.last_check_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
        self.last_failure_time: Optional[float] = None
        
        # Results history
        self.results_history: List[HealthCheckResult] = []
        self.max_history = 100
        
        # HTTP client for HTTP checks
        self.http_client: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize health checker resources"""
        if self.config.check_type == HealthCheckType.HTTP:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.http_client = aiohttp.ClientSession(timeout=timeout)
    
    async def cleanup(self):
        """Cleanup health checker resources"""
        if self.http_client:
            await self.http_client.close()
    
    async def check(self) -> HealthCheckResult:
        """Perform health check"""
        start_time = time.time()
        
        try:
            if self.config.check_type == HealthCheckType.HTTP:
                result = await self._check_http()
            elif self.config.check_type == HealthCheckType.TCP:
                result = await self._check_tcp()
            elif self.config.check_type == HealthCheckType.CUSTOM:
                result = await self._check_custom()
            else:
                raise ValueError(f"Unsupported check type: {self.config.check_type}")
            
            result.response_time = time.time() - start_time
            
            # Update state based on result
            self._update_state(result)
            
            # Add to history
            self.results_history.append(result)
            if len(self.results_history) > self.max_history:
                self.results_history.pop(0)
            
            return result
            
        except Exception as e:
            response_time = time.time() - start_time
            result = HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=self.config.check_type,
                success=False,
                response_time=response_time,
                error_message=str(e)
            )
            
            self._update_state(result)
            self.results_history.append(result)
            
            return result
    
    async def _check_http(self) -> HealthCheckResult:
        """Perform HTTP health check"""
        if not self.http_client:
            raise RuntimeError("HTTP client not initialized")
        
        # Get health check URL
        health_url = self.service_info.health_check_url
        if not health_url:
            # Try to build from HTTP endpoint
            if 'http' in self.service_info.endpoints:
                endpoint = self.service_info.endpoints['http']
                health_url = f"{endpoint.url}/health"
            else:
                raise ValueError("No health check URL available")
        
        # Make HTTP request
        async with self.http_client.request(
            method=self.config.http_method,
            url=health_url
        ) as response:
            
            # Check status code
            if response.status not in self.config.expected_status:
                return HealthCheckResult(
                    service_name=self.service_info.name,
                    instance_id=self.service_info.instance_id,
                    check_type=HealthCheckType.HTTP,
                    success=False,
                    response_time=0,  # Will be set by caller
                    error_message=f"Unexpected status code: {response.status}",
                    details={"status_code": response.status, "url": health_url}
                )
            
            # Check response body if configured
            if self.config.expected_body:
                body = await response.text()
                if self.config.expected_body not in body:
                    return HealthCheckResult(
                        service_name=self.service_info.name,
                        instance_id=self.service_info.instance_id,
                        check_type=HealthCheckType.HTTP,
                        success=False,
                        response_time=0,
                        error_message=f"Expected body content not found",
                        details={"status_code": response.status, "url": health_url}
                    )
            
            # Success
            return HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=HealthCheckType.HTTP,
                success=True,
                response_time=0,
                details={"status_code": response.status, "url": health_url}
            )
    
    async def _check_tcp(self) -> HealthCheckResult:
        """Perform TCP health check"""
        port = self.config.tcp_port
        if not port:
            # Try to get port from service endpoints
            if 'http' in self.service_info.endpoints:
                port = self.service_info.endpoints['http'].port
            else:
                raise ValueError("No TCP port specified")
        
        # Get host
        if 'http' in self.service_info.endpoints:
            host = self.service_info.endpoints['http'].host
        else:
            host = 'localhost'
        
        # Try to connect
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=self.config.timeout
            )
            writer.close()
            await writer.wait_closed()
            
            return HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=HealthCheckType.TCP,
                success=True,
                response_time=0,
                details={"host": host, "port": port}
            )
            
        except Exception as e:
            return HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=HealthCheckType.TCP,
                success=False,
                response_time=0,
                error_message=str(e),
                details={"host": host, "port": port}
            )
    
    async def _check_custom(self) -> HealthCheckResult:
        """Perform custom health check"""
        if not self.config.custom_checker:
            raise ValueError("No custom checker provided")
        
        try:
            if asyncio.iscoroutinefunction(self.config.custom_checker):
                result = await self.config.custom_checker(self.service_info)
            else:
                result = self.config.custom_checker(self.service_info)
            
            success = bool(result)
            details = result if isinstance(result, dict) else {}
            
            return HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=HealthCheckType.CUSTOM,
                success=success,
                response_time=0,
                details=details
            )
            
        except Exception as e:
            return HealthCheckResult(
                service_name=self.service_info.name,
                instance_id=self.service_info.instance_id,
                check_type=HealthCheckType.CUSTOM,
                success=False,
                response_time=0,
                error_message=str(e)
            )
    
    def _update_state(self, result: HealthCheckResult):
        """Update health checker state based on result"""
        self.last_check_time = result.timestamp
        
        if result.success:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.last_success_time = result.timestamp
            
            # Check if service should be marked healthy
            if (self.current_status != ServiceStatus.HEALTHY and
                self.consecutive_successes >= self.config.healthy_threshold):
                self.current_status = ServiceStatus.HEALTHY
                
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_failure_time = result.timestamp
            
            # Check if service should be marked unhealthy
            if (self.current_status != ServiceStatus.UNHEALTHY and
                self.consecutive_failures >= self.config.unhealthy_threshold):
                self.current_status = ServiceStatus.UNHEALTHY
    
    def get_stats(self) -> Dict[str, Any]:
        """Get health checker statistics"""
        total_checks = len(self.results_history)
        successful_checks = sum(1 for r in self.results_history if r.success)
        
        return {
            'service_name': self.service_info.name,
            'instance_id': self.service_info.instance_id,
            'current_status': self.current_status.value,
            'check_type': self.config.check_type.value,
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'total_checks': total_checks,
            'successful_checks': successful_checks,
            'success_rate': successful_checks / max(total_checks, 1),
            'last_check_time': self.last_check_time,
            'last_success_time': self.last_success_time,
            'last_failure_time': self.last_failure_time,
            'config': {
                'interval': self.config.interval,
                'timeout': self.config.timeout,
                'healthy_threshold': self.config.healthy_threshold,
                'unhealthy_threshold': self.config.unhealthy_threshold
            }
        }


class HealthManager:
    """
    Health check manager for all services
    
    Manages health checks for all registered services and provides
    centralized health monitoring and alerting.
    """
    
    def __init__(
        self,
        service_registry: ServiceRegistry,
        default_config: Optional[HealthCheckConfig] = None
    ):
        self.service_registry = service_registry
        self.default_config = default_config or HealthCheckConfig(
            check_type=HealthCheckType.HTTP,
            interval=30,
            timeout=10
        )
        
        # Health checkers by service instance
        self.health_checkers: Dict[str, HealthChecker] = {}
        
        # Background tasks
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._discovery_task: Optional[asyncio.Task] = None
        
        # Event callbacks
        self.health_change_callbacks: List[Callable] = []
        
        # State
        self._running = False
        
        logger.info("Health manager initialized")
    
    async def start(self):
        """Start health manager"""
        if self._running:
            return
        
        self._running = True
        
        # Start service discovery task
        self._discovery_task = asyncio.create_task(self._service_discovery_loop())
        
        logger.info("Health manager started")
    
    async def stop(self):
        """Stop health manager"""
        if not self._running:
            return
        
        self._running = False
        
        # Stop discovery task
        if self._discovery_task:
            self._discovery_task.cancel()
        
        # Stop all check tasks
        for task in self._check_tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        tasks = list(self._check_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cleanup health checkers
        for checker in self.health_checkers.values():
            await checker.cleanup()
        
        self.health_checkers.clear()
        self._check_tasks.clear()
        
        logger.info("Health manager stopped")
    
    def add_health_change_callback(self, callback: Callable[[str, str, ServiceStatus, ServiceStatus], None]):
        """Add callback for health status changes"""
        self.health_change_callbacks.append(callback)
    
    def configure_service_health_check(
        self,
        service_name: str,
        instance_id: str,
        config: HealthCheckConfig
    ):
        """Configure health check for specific service instance"""
        checker_key = f"{service_name}:{instance_id}"
        
        # If checker exists, update its configuration
        if checker_key in self.health_checkers:
            old_checker = self.health_checkers[checker_key]
            # Create new checker with updated config but preserve service info
            new_checker = HealthChecker(old_checker.service_info, config)
            self.health_checkers[checker_key] = new_checker
            
            # Restart check task
            if checker_key in self._check_tasks:
                self._check_tasks[checker_key].cancel()
                self._check_tasks[checker_key] = asyncio.create_task(
                    self._health_check_loop(new_checker)
                )
        
        logger.info(f"Configured health check for {service_name}:{instance_id}")
    
    async def _service_discovery_loop(self):
        """Discover services and manage health checkers"""
        while self._running:
            try:
                # Discover all services
                services = await self.service_registry.discover_services()
                
                # Track current service instances
                current_instances = set()
                
                for service in services:
                    checker_key = f"{service.name}:{service.instance_id}"
                    current_instances.add(checker_key)
                    
                    # Create health checker if not exists
                    if checker_key not in self.health_checkers:
                        await self._add_health_checker(service)
                    else:
                        # Update service info
                        self.health_checkers[checker_key].service_info = service
                
                # Remove health checkers for services that no longer exist
                to_remove = set(self.health_checkers.keys()) - current_instances
                for checker_key in to_remove:
                    await self._remove_health_checker(checker_key)
                
                await asyncio.sleep(60)  # Check for new services every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Service discovery loop error: {e}")
                await asyncio.sleep(30)
    
    async def _add_health_checker(self, service: ServiceInfo):
        """Add health checker for a service"""
        checker_key = f"{service.name}:{service.instance_id}"
        
        # Determine health check configuration
        config = self._get_health_check_config(service)
        
        # Create health checker
        checker = HealthChecker(service, config)
        await checker.initialize()
        
        self.health_checkers[checker_key] = checker
        
        # Start health check task
        self._check_tasks[checker_key] = asyncio.create_task(
            self._health_check_loop(checker)
        )
        
        logger.info(f"Added health checker for {service.name}:{service.instance_id}")
    
    async def _remove_health_checker(self, checker_key: str):
        """Remove health checker"""
        # Cancel check task
        if checker_key in self._check_tasks:
            self._check_tasks[checker_key].cancel()
            del self._check_tasks[checker_key]
        
        # Cleanup checker
        if checker_key in self.health_checkers:
            checker = self.health_checkers[checker_key]
            await checker.cleanup()
            del self.health_checkers[checker_key]
        
        logger.info(f"Removed health checker for {checker_key}")
    
    def _get_health_check_config(self, service: ServiceInfo) -> HealthCheckConfig:
        """Get health check configuration for a service"""
        # Check if service has custom health check configuration in metadata
        if 'health_check_type' in service.metadata:
            check_type = HealthCheckType(service.metadata['health_check_type'])
            
            config = HealthCheckConfig(
                check_type=check_type,
                interval=int(service.metadata.get('health_check_interval', 30)),
                timeout=int(service.metadata.get('health_check_timeout', 10))
            )
            
            return config
        
        # Use default configuration
        return self.default_config
    
    async def _health_check_loop(self, checker: HealthChecker):
        """Health check loop for a single service"""
        while self._running:
            try:
                # Perform health check
                result = await checker.check()
                
                # Update service registry if status changed
                old_status = checker.current_status
                new_status = (ServiceStatus.HEALTHY if result.success 
                             else ServiceStatus.UNHEALTHY)
                
                if old_status != new_status:
                    await self.service_registry.update_service_health(
                        checker.service_info.name,
                        checker.service_info.instance_id,
                        new_status,
                        checker.service_info.tenant_id
                    )
                    
                    # Notify callbacks
                    for callback in self.health_change_callbacks:
                        try:
                            callback(
                                checker.service_info.name,
                                checker.service_info.instance_id,
                                old_status,
                                new_status
                            )
                        except Exception as e:
                            logger.error(f"Health change callback error: {e}")
                
                # Wait for next check
                await asyncio.sleep(checker.config.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error for {checker.service_info.name}: {e}")
                await asyncio.sleep(30)  # Back off on errors
    
    def get_service_health_status(self, service_name: str, instance_id: str) -> Optional[ServiceStatus]:
        """Get current health status of a service"""
        checker_key = f"{service_name}:{instance_id}"
        if checker_key in self.health_checkers:
            return self.health_checkers[checker_key].current_status
        return None
    
    def get_all_health_stats(self) -> Dict[str, Any]:
        """Get health statistics for all services"""
        stats = {}
        
        for checker_key, checker in self.health_checkers.items():
            stats[checker_key] = checker.get_stats()
        
        return {
            'health_checkers': stats,
            'total_services': len(self.health_checkers),
            'healthy_services': sum(1 for c in self.health_checkers.values() 
                                   if c.current_status == ServiceStatus.HEALTHY),
            'unhealthy_services': sum(1 for c in self.health_checkers.values() 
                                     if c.current_status == ServiceStatus.UNHEALTHY),
            'manager_running': self._running
        }
