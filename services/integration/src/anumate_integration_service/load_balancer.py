"""
Production-grade Load Balancer

Implements various load balancing strategies for distributing requests
across service instances with health checking and failover capabilities.
"""

import random
import time
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging

import structlog

from .service_registry import ServiceInfo


logger = structlog.get_logger(__name__)


class LoadBalancerStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    RANDOM = "random"
    IP_HASH = "ip_hash"
    HEALTH_AWARE = "health_aware"


@dataclass
class ServiceInstance:
    """Service instance with load balancing metadata"""
    service_info: ServiceInfo
    weight: int = 1
    active_connections: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    last_health_check: float = 0.0
    health_score: float = 1.0
    
    def __post_init__(self):
        self.last_health_check = time.time()
    
    def record_request(self, success: bool, response_time: float):
        """Record request outcome"""
        self.total_requests += 1
        if not success:
            self.failed_requests += 1
        
        # Update average response time (exponential moving average)
        alpha = 0.1
        self.avg_response_time = (alpha * response_time + 
                                 (1 - alpha) * self.avg_response_time)
        
        # Update health score based on success rate and response time
        success_rate = 1.0 - (self.failed_requests / max(self.total_requests, 1))
        time_factor = max(0.1, 1.0 - (self.avg_response_time / 5.0))  # Penalize slow responses
        self.health_score = success_rate * time_factor
    
    def increment_connections(self):
        """Increment active connection count"""
        self.active_connections += 1
    
    def decrement_connections(self):
        """Decrement active connection count"""
        self.active_connections = max(0, self.active_connections - 1)


class LoadBalancingStrategy(ABC):
    """Abstract base class for load balancing strategies"""
    
    @abstractmethod
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        """Select a service instance"""
        pass
    
    @abstractmethod
    def reset(self):
        """Reset strategy state"""
        pass


class RoundRobinStrategy(LoadBalancingStrategy):
    """Round-robin load balancing"""
    
    def __init__(self):
        self.current_index = 0
        self.lock = threading.RLock()
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        with self.lock:
            # Filter healthy instances
            healthy_instances = [inst for inst in instances if inst.health_score > 0.5]
            if not healthy_instances:
                healthy_instances = instances  # Fallback to all instances
            
            selected = healthy_instances[self.current_index % len(healthy_instances)]
            self.current_index = (self.current_index + 1) % len(healthy_instances)
            
            return selected
    
    def reset(self):
        with self.lock:
            self.current_index = 0


class LeastConnectionsStrategy(LoadBalancingStrategy):
    """Least connections load balancing"""
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        # Filter healthy instances
        healthy_instances = [inst for inst in instances if inst.health_score > 0.5]
        if not healthy_instances:
            healthy_instances = instances
        
        # Select instance with least connections
        return min(healthy_instances, key=lambda x: x.active_connections)
    
    def reset(self):
        pass  # No state to reset


class WeightedRoundRobinStrategy(LoadBalancingStrategy):
    """Weighted round-robin load balancing"""
    
    def __init__(self):
        self.current_weights: Dict[str, int] = {}
        self.lock = threading.RLock()
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        with self.lock:
            # Filter healthy instances
            healthy_instances = [inst for inst in instances if inst.health_score > 0.5]
            if not healthy_instances:
                healthy_instances = instances
            
            # Initialize current weights if needed
            total_weight = 0
            max_current_weight = -1
            selected = None
            
            for instance in healthy_instances:
                instance_id = instance.service_info.instance_id
                
                if instance_id not in self.current_weights:
                    self.current_weights[instance_id] = 0
                
                # Increment current weight
                self.current_weights[instance_id] += instance.weight
                total_weight += instance.weight
                
                # Track instance with highest current weight
                if self.current_weights[instance_id] > max_current_weight:
                    max_current_weight = self.current_weights[instance_id]
                    selected = instance
            
            if selected:
                # Decrease selected instance's current weight by total weight
                selected_id = selected.service_info.instance_id
                self.current_weights[selected_id] -= total_weight
            
            return selected
    
    def reset(self):
        with self.lock:
            self.current_weights.clear()


class RandomStrategy(LoadBalancingStrategy):
    """Random load balancing"""
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        # Filter healthy instances
        healthy_instances = [inst for inst in instances if inst.health_score > 0.5]
        if not healthy_instances:
            healthy_instances = instances
        
        return random.choice(healthy_instances)
    
    def reset(self):
        pass


class IPHashStrategy(LoadBalancingStrategy):
    """IP hash-based load balancing for session affinity"""
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        # Filter healthy instances
        healthy_instances = [inst for inst in instances if inst.health_score > 0.5]
        if not healthy_instances:
            healthy_instances = instances
        
        # Use client IP from context for consistent hashing
        client_ip = context.get('client_ip', '0.0.0.0') if context else '0.0.0.0'
        hash_value = hash(client_ip)
        index = hash_value % len(healthy_instances)
        
        return healthy_instances[index]
    
    def reset(self):
        pass


class HealthAwareStrategy(LoadBalancingStrategy):
    """Health-aware load balancing that considers health scores"""
    
    def select(self, instances: List[ServiceInstance], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInstance]:
        if not instances:
            return None
        
        # Filter instances with positive health scores
        healthy_instances = [inst for inst in instances if inst.health_score > 0]
        if not healthy_instances:
            return None  # No healthy instances
        
        # Weighted selection based on health scores
        total_health = sum(inst.health_score for inst in healthy_instances)
        if total_health <= 0:
            return random.choice(healthy_instances)
        
        # Weighted random selection
        rand_value = random.uniform(0, total_health)
        current_sum = 0
        
        for instance in healthy_instances:
            current_sum += instance.health_score
            if rand_value <= current_sum:
                return instance
        
        return healthy_instances[-1]  # Fallback
    
    def reset(self):
        pass


class LoadBalancer:
    """
    Production-grade load balancer with multiple strategies and health checking
    """
    
    def __init__(self, strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN):
        self.strategy_type = strategy
        self.strategy = self._create_strategy(strategy)
        self.instances: Dict[str, ServiceInstance] = {}
        self.lock = threading.RLock()
        
        # Metrics
        self.total_selections = 0
        self.failed_selections = 0
        self.strategy_switches = 0
        
        logger.info(f"Load balancer initialized with {strategy.value} strategy")
    
    def _create_strategy(self, strategy: LoadBalancerStrategy) -> LoadBalancingStrategy:
        """Create strategy instance"""
        strategy_map = {
            LoadBalancerStrategy.ROUND_ROBIN: RoundRobinStrategy,
            LoadBalancerStrategy.LEAST_CONNECTIONS: LeastConnectionsStrategy,
            LoadBalancerStrategy.WEIGHTED_ROUND_ROBIN: WeightedRoundRobinStrategy,
            LoadBalancerStrategy.RANDOM: RandomStrategy,
            LoadBalancerStrategy.IP_HASH: IPHashStrategy,
            LoadBalancerStrategy.HEALTH_AWARE: HealthAwareStrategy,
        }
        
        strategy_class = strategy_map.get(strategy, RoundRobinStrategy)
        return strategy_class()
    
    def update_instances(self, services: List[ServiceInfo]):
        """Update service instances"""
        with self.lock:
            new_instances = {}
            
            for service in services:
                instance_id = service.instance_id
                
                if instance_id in self.instances:
                    # Update existing instance
                    self.instances[instance_id].service_info = service
                    new_instances[instance_id] = self.instances[instance_id]
                else:
                    # Create new instance
                    new_instances[instance_id] = ServiceInstance(
                        service_info=service,
                        weight=int(service.metadata.get('weight', 1))
                    )
            
            self.instances = new_instances
            
            logger.debug(f"Updated load balancer with {len(self.instances)} instances")
    
    def select(self, services: List[ServiceInfo], context: Optional[Dict[str, Any]] = None) -> Optional[ServiceInfo]:
        """Select a service instance using the configured strategy"""
        with self.lock:
            self.total_selections += 1
            
            # Update instances if needed
            self.update_instances(services)
            
            # Get instances for selection
            instances = list(self.instances.values())
            if not instances:
                self.failed_selections += 1
                return None
            
            # Select using strategy
            selected_instance = self.strategy.select(instances, context)
            
            if not selected_instance:
                self.failed_selections += 1
                return None
            
            # Increment connection count
            selected_instance.increment_connections()
            
            logger.debug(f"Selected instance {selected_instance.service_info.instance_id} "
                        f"using {self.strategy_type.value} strategy")
            
            return selected_instance.service_info
    
    def record_request_result(
        self,
        instance_id: str,
        success: bool,
        response_time: float
    ):
        """Record request result for load balancing metrics"""
        with self.lock:
            if instance_id in self.instances:
                instance = self.instances[instance_id]
                instance.record_request(success, response_time)
                instance.decrement_connections()
                
                logger.debug(f"Recorded request for {instance_id}: "
                            f"success={success}, time={response_time:.3f}s")
    
    def set_strategy(self, strategy: LoadBalancerStrategy):
        """Change load balancing strategy"""
        with self.lock:
            if strategy != self.strategy_type:
                self.strategy_type = strategy
                self.strategy = self._create_strategy(strategy)
                self.strategy_switches += 1
                
                logger.info(f"Switched to {strategy.value} load balancing strategy")
    
    def get_instance_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all instances"""
        with self.lock:
            stats = {}
            
            for instance_id, instance in self.instances.items():
                stats[instance_id] = {
                    'service_name': instance.service_info.name,
                    'weight': instance.weight,
                    'active_connections': instance.active_connections,
                    'total_requests': instance.total_requests,
                    'failed_requests': instance.failed_requests,
                    'success_rate': 1.0 - (instance.failed_requests / max(instance.total_requests, 1)),
                    'avg_response_time': instance.avg_response_time,
                    'health_score': instance.health_score,
                    'endpoints': {name: endpoint.url for name, endpoint in instance.service_info.endpoints.items()}
                }
            
            return stats
    
    def get_load_balancer_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics"""
        with self.lock:
            return {
                'strategy': self.strategy_type.value,
                'total_selections': self.total_selections,
                'failed_selections': self.failed_selections,
                'success_rate': 1.0 - (self.failed_selections / max(self.total_selections, 1)),
                'strategy_switches': self.strategy_switches,
                'active_instances': len(self.instances),
                'total_connections': sum(inst.active_connections for inst in self.instances.values()),
                'instance_stats': self.get_instance_stats()
            }
    
    def reset_stats(self):
        """Reset load balancer statistics"""
        with self.lock:
            self.total_selections = 0
            self.failed_selections = 0
            self.strategy_switches = 0
            self.strategy.reset()
            
            # Reset instance stats
            for instance in self.instances.values():
                instance.active_connections = 0
                instance.total_requests = 0
                instance.failed_requests = 0
                instance.avg_response_time = 0.0
                instance.health_score = 1.0
            
            logger.info("Load balancer statistics reset")
    
    def remove_unhealthy_instances(self, health_threshold: float = 0.1):
        """Remove instances below health threshold"""
        with self.lock:
            initial_count = len(self.instances)
            
            self.instances = {
                instance_id: instance
                for instance_id, instance in self.instances.items()
                if instance.health_score >= health_threshold
            }
            
            removed_count = initial_count - len(self.instances)
            if removed_count > 0:
                logger.info(f"Removed {removed_count} unhealthy instances "
                           f"below threshold {health_threshold}")
    
    def get_healthy_instances(self, min_health: float = 0.5) -> List[ServiceInfo]:
        """Get list of healthy service instances"""
        with self.lock:
            healthy = [
                instance.service_info
                for instance in self.instances.values()
                if instance.health_score >= min_health
            ]
            
            return healthy
