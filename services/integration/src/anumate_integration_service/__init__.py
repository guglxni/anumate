"""
Anumate Integration Service

Production-grade service integration patterns for microservices architecture.
Provides service discovery, circuit breakers, API gateway, and service mesh configuration.
"""

__version__ = "0.1.0"
__author__ = "Anumate"
__email__ = "info@anumate.com"

from .service_registry import ServiceRegistry, ServiceInfo
from .circuit_breaker import CircuitBreaker, CircuitBreakerError
from .discovery_client import DiscoveryClient
from .api_gateway import APIGateway
from .health_manager import HealthManager
from .load_balancer import LoadBalancer, LoadBalancerStrategy

__all__ = [
    "ServiceRegistry",
    "ServiceInfo", 
    "CircuitBreaker",
    "CircuitBreakerError",
    "DiscoveryClient",
    "APIGateway",
    "HealthManager",
    "LoadBalancer",
    "LoadBalancerStrategy",
]
