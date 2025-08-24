"""
Production-grade Circuit Breaker Implementation

Implements the circuit breaker pattern to prevent cascading failures in microservices.
Features configurable thresholds, multiple failure modes, and comprehensive monitoring.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union
from collections import deque
import threading

import structlog


logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Circuit breaker triggered
    HALF_OPEN = "half_open"  # Testing recovery


class FailureMode(Enum):
    """Types of failures that can trigger circuit breaker"""
    TIMEOUT = "timeout"
    EXCEPTION = "exception" 
    STATUS_CODE = "status_code"
    CUSTOM = "custom"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5          # Number of failures to trigger open
    success_threshold: int = 3          # Number of successes to close from half-open
    timeout_threshold: float = 30.0     # Timeout in seconds to trigger failure
    recovery_timeout: float = 60.0      # Time to wait before trying half-open
    window_size: int = 100             # Sliding window size for failure rate
    failure_rate_threshold: float = 0.5  # Failure rate to trigger open (50%)
    enable_metrics: bool = True         # Enable detailed metrics
    
    def __post_init__(self):
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.success_threshold <= 0:
            raise ValueError("success_threshold must be positive") 
        if self.timeout_threshold <= 0:
            raise ValueError("timeout_threshold must be positive")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be positive")
        if not 0 < self.failure_rate_threshold <= 1:
            raise ValueError("failure_rate_threshold must be between 0 and 1")


@dataclass
class CallResult:
    """Result of a circuit breaker call"""
    success: bool
    duration: float
    failure_mode: Optional[FailureMode] = None
    error: Optional[Exception] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    
    def __init__(self, message: str, circuit_name: str, state: CircuitState):
        super().__init__(message)
        self.circuit_name = circuit_name
        self.state = state


class CircuitBreakerMetrics:
    """Metrics tracking for circuit breaker"""
    
    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.calls: deque = deque(maxlen=window_size)
        self.lock = threading.RLock()
        
        # Counters
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.timeouts = 0
        self.circuit_opens = 0
        self.circuit_closes = 0
        
        # Timing
        self.total_duration = 0.0
        self.min_duration = float('inf')
        self.max_duration = 0.0
        
        # State tracking
        self.state_changes: deque = deque(maxlen=100)
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None
    
    def record_call(self, result: CallResult):
        """Record a call result"""
        with self.lock:
            self.calls.append(result)
            self.total_calls += 1
            
            if result.success:
                self.successful_calls += 1
                self.last_success_time = result.timestamp
            else:
                self.failed_calls += 1
                self.last_failure_time = result.timestamp
                
                if result.failure_mode == FailureMode.TIMEOUT:
                    self.timeouts += 1
            
            # Update timing metrics
            self.total_duration += result.duration
            self.min_duration = min(self.min_duration, result.duration)
            self.max_duration = max(self.max_duration, result.duration)
    
    def record_state_change(self, old_state: CircuitState, new_state: CircuitState):
        """Record circuit breaker state change"""
        with self.lock:
            self.state_changes.append({
                'timestamp': time.time(),
                'from_state': old_state.value,
                'to_state': new_state.value
            })
            
            if new_state == CircuitState.OPEN:
                self.circuit_opens += 1
            elif old_state == CircuitState.OPEN and new_state == CircuitState.CLOSED:
                self.circuit_closes += 1
    
    def get_failure_rate(self) -> float:
        """Get current failure rate in the window"""
        with self.lock:
            if not self.calls:
                return 0.0
            
            failed = sum(1 for call in self.calls if not call.success)
            return failed / len(self.calls)
    
    def get_average_duration(self) -> float:
        """Get average call duration"""
        with self.lock:
            if self.total_calls == 0:
                return 0.0
            return self.total_duration / self.total_calls
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        with self.lock:
            return {
                'total_calls': self.total_calls,
                'successful_calls': self.successful_calls,
                'failed_calls': self.failed_calls,
                'success_rate': self.successful_calls / max(self.total_calls, 1),
                'failure_rate': self.get_failure_rate(),
                'timeouts': self.timeouts,
                'circuit_opens': self.circuit_opens,
                'circuit_closes': self.circuit_closes,
                'avg_duration': self.get_average_duration(),
                'min_duration': self.min_duration if self.min_duration != float('inf') else 0,
                'max_duration': self.max_duration,
                'window_size': len(self.calls),
                'last_failure_time': self.last_failure_time,
                'last_success_time': self.last_success_time
            }


class CircuitBreaker:
    """
    Production-grade circuit breaker implementation
    
    Prevents cascading failures by monitoring call success/failure rates
    and temporarily blocking calls when failure thresholds are exceeded.
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        failure_detector: Optional[Callable[[Any], bool]] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.failure_detector = failure_detector or self._default_failure_detector
        
        # State management
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change = time.time()
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Metrics
        self.metrics = CircuitBreakerMetrics(self.config.window_size) if self.config.enable_metrics else None
        
        # Event listeners
        self.state_change_listeners = []
        self.call_listeners = []
        
        logger.info(f"Circuit breaker '{name}' initialized", 
                   state=self.state.value, config=self.config)
    
    def _default_failure_detector(self, result: Any) -> bool:
        """Default failure detection logic"""
        if isinstance(result, Exception):
            return True
        if hasattr(result, 'status_code') and result.status_code >= 500:
            return True
        return False
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function call through the circuit breaker
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: When circuit is open
        """
        # Check if circuit allows calls
        if not self._can_execute():
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is {self.state.value}",
                self.name,
                self.state
            )
        
        start_time = time.time()
        result = None
        error = None
        success = False
        failure_mode = None
        
        try:
            # Execute with timeout if configured
            if self.config.timeout_threshold > 0:
                result = await asyncio.wait_for(
                    self._execute_function(func, *args, **kwargs),
                    timeout=self.config.timeout_threshold
                )
            else:
                result = await self._execute_function(func, *args, **kwargs)
            
            # Check if result indicates failure
            if self.failure_detector(result):
                success = False
                failure_mode = FailureMode.CUSTOM
            else:
                success = True
                
        except asyncio.TimeoutError as e:
            error = e
            success = False
            failure_mode = FailureMode.TIMEOUT
            
        except Exception as e:
            error = e
            success = False
            failure_mode = FailureMode.EXCEPTION
        
        duration = time.time() - start_time
        
        # Record call result
        call_result = CallResult(
            success=success,
            duration=duration,
            failure_mode=failure_mode,
            error=error,
            timestamp=start_time
        )
        
        # Update circuit breaker state
        self._record_call_result(call_result)
        
        # Re-raise exception if call failed
        if error:
            raise error
            
        return result
    
    async def _execute_function(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function, handling both sync and async"""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run sync function in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)
    
    def _can_execute(self) -> bool:
        """Check if circuit allows execution"""
        with self.lock:
            current_time = time.time()
            
            if self.state == CircuitState.CLOSED:
                return True
                
            elif self.state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if (self.last_failure_time and 
                    current_time - self.last_failure_time >= self.config.recovery_timeout):
                    self._transition_to_half_open()
                    return True
                return False
                
            elif self.state == CircuitState.HALF_OPEN:
                return True
                
            return False
    
    def _record_call_result(self, result: CallResult):
        """Record call result and update circuit state"""
        with self.lock:
            # Record metrics
            if self.metrics:
                self.metrics.record_call(result)
            
            # Notify listeners
            for listener in self.call_listeners:
                try:
                    listener(self.name, result)
                except Exception as e:
                    logger.error(f"Call listener error: {e}")
            
            # Update state based on result
            if result.success:
                self._handle_successful_call()
            else:
                self._handle_failed_call(result)
            
            # Check if state transition is needed
            self._check_state_transition()
    
    def _handle_successful_call(self):
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
        else:
            # Reset failure count on success in closed state
            self.failure_count = 0
    
    def _handle_failed_call(self, result: CallResult):
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = result.timestamp
        
        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self._transition_to_open()
    
    def _check_state_transition(self):
        """Check if circuit breaker should change state"""
        if self.state == CircuitState.CLOSED:
            # Check failure count threshold
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
                return
            
            # Check failure rate threshold
            if self.metrics:
                failure_rate = self.metrics.get_failure_rate()
                if failure_rate >= self.config.failure_rate_threshold:
                    self._transition_to_open()
                    return
    
    def _transition_to_open(self):
        """Transition to open state"""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        
        self._notify_state_change(old_state, self.state)
        logger.warning(f"Circuit breaker '{self.name}' opened", 
                      failure_count=self.failure_count)
    
    def _transition_to_half_open(self):
        """Transition to half-open state"""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.last_state_change = time.time()
        self.success_count = 0
        
        self._notify_state_change(old_state, self.state)
        logger.info(f"Circuit breaker '{self.name}' half-opened")
    
    def _transition_to_closed(self):
        """Transition to closed state"""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.last_state_change = time.time()
        self.failure_count = 0
        self.success_count = 0
        
        self._notify_state_change(old_state, self.state)
        logger.info(f"Circuit breaker '{self.name}' closed")
    
    def _notify_state_change(self, old_state: CircuitState, new_state: CircuitState):
        """Notify state change to listeners and metrics"""
        if self.metrics:
            self.metrics.record_state_change(old_state, new_state)
        
        for listener in self.state_change_listeners:
            try:
                listener(self.name, old_state, new_state)
            except Exception as e:
                logger.error(f"State change listener error: {e}")
    
    def force_open(self):
        """Force circuit breaker to open state"""
        with self.lock:
            if self.state != CircuitState.OPEN:
                self._transition_to_open()
    
    def force_closed(self):
        """Force circuit breaker to closed state"""
        with self.lock:
            if self.state != CircuitState.CLOSED:
                self._transition_to_closed()
    
    def reset(self):
        """Reset circuit breaker to initial state"""
        with self.lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None
            self.last_state_change = time.time()
            
            if self.metrics:
                self.metrics = CircuitBreakerMetrics(self.config.window_size)
            
            self._notify_state_change(old_state, self.state)
            logger.info(f"Circuit breaker '{self.name}' reset")
    
    def add_state_change_listener(self, listener: Callable[[str, CircuitState, CircuitState], None]):
        """Add listener for state changes"""
        self.state_change_listeners.append(listener)
    
    def add_call_listener(self, listener: Callable[[str, CallResult], None]):
        """Add listener for call results"""
        self.call_listeners.append(listener)
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state"""
        return self.state
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        with self.lock:
            stats = {
                'name': self.name,
                'state': self.state.value,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'last_failure_time': self.last_failure_time,
                'last_state_change': self.last_state_change,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'success_threshold': self.config.success_threshold,
                    'timeout_threshold': self.config.timeout_threshold,
                    'recovery_timeout': self.config.recovery_timeout,
                    'failure_rate_threshold': self.config.failure_rate_threshold
                }
            }
            
            if self.metrics:
                stats['metrics'] = self.metrics.get_stats()
            
            return stats


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers"""
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.RLock()
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        failure_detector: Optional[Callable] = None
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create new one"""
        with self.lock:
            if name not in self.circuit_breakers:
                self.circuit_breakers[name] = CircuitBreaker(name, config, failure_detector)
            return self.circuit_breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name"""
        return self.circuit_breakers.get(name)
    
    def remove(self, name: str) -> bool:
        """Remove circuit breaker"""
        with self.lock:
            return self.circuit_breakers.pop(name, None) is not None
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all circuit breakers"""
        with self.lock:
            return {name: cb.get_stats() for name, cb in self.circuit_breakers.items()}
    
    def reset_all(self):
        """Reset all circuit breakers"""
        with self.lock:
            for cb in self.circuit_breakers.values():
                cb.reset()


# Global circuit breaker registry
_circuit_breaker_registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
    failure_detector: Optional[Callable] = None
) -> CircuitBreaker:
    """Get or create a circuit breaker"""
    return _circuit_breaker_registry.get_or_create(name, config, failure_detector)
