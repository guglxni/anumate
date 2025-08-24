"""Retry logic and idempotency handling for plan execution."""

import asyncio
import hashlib
import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Optional, TypeVar
from uuid import UUID

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    wait_random_exponential,
    retry_if_exception_type,
    RetryError,
)

try:
    from anumate_infrastructure import RedisManager
except ImportError:
    RedisManager = None

try:
    from anumate_tracing import trace_async
except ImportError:
    def trace_async(name):
        def decorator(func):
            return func
        return decorator

from models import ExecutionStatusEnum, IdempotencyKey, RetryPolicy

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryHandler:
    """Handles retry logic and idempotency for plan execution."""
    
    def __init__(self, redis_manager: Optional[RedisManager] = None):
        """Initialize retry handler.
        
        Args:
            redis_manager: Redis manager for idempotency storage
        """
        self.redis_manager = redis_manager
        self.default_retry_policy = RetryPolicy()
    
    @trace_async("retry_handler.execute_with_retry")
    async def execute_with_retry(
        self,
        func: Callable[..., T],
        retry_policy: Optional[RetryPolicy] = None,
        *args,
        **kwargs,
    ) -> T:
        """Execute a function with retry logic.
        
        Args:
            func: Function to execute
            retry_policy: Retry policy to use
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            RetryError: If all retry attempts fail
        """
        policy = retry_policy or self.default_retry_policy
        
        # Create retry decorator based on policy
        retry_decorator = self._create_retry_decorator(policy)
        
        # Wrap function with retry logic
        retryable_func = retry_decorator(func)
        
        try:
            return await retryable_func(*args, **kwargs)
        except RetryError as e:
            logger.error(f"All retry attempts failed: {e}")
            raise
    
    def _create_retry_decorator(self, policy: RetryPolicy):
        """Create tenacity retry decorator from policy."""
        wait_strategy = wait_exponential(
            multiplier=policy.initial_delay,
            max=policy.max_delay,
            exp_base=policy.exponential_base,
        )
        
        if policy.jitter:
            wait_strategy = wait_random_exponential(
                multiplier=policy.initial_delay,
                max=policy.max_delay,
            )
        
        return retry(
            stop=stop_after_attempt(policy.max_attempts),
            wait=wait_strategy,
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
    
    @trace_async("retry_handler.generate_idempotency_key")
    async def generate_idempotency_key(
        self,
        tenant_id: UUID,
        request_data: Dict[str, Any],
        ttl_hours: int = 24,
    ) -> IdempotencyKey:
        """Generate idempotency key for request.
        
        Args:
            tenant_id: Tenant ID
            request_data: Request data to hash
            ttl_hours: TTL for idempotency key in hours
            
        Returns:
            Idempotency key
        """
        # Create request hash
        request_hash = self._hash_request_data(request_data)
        
        # Generate key
        key = f"idempotency:{tenant_id}:{request_hash}"
        
        # Calculate expiry
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        
        return IdempotencyKey(
            key=key,
            tenant_id=tenant_id,
            request_hash=request_hash,
            expires_at=expires_at,
        )
    
    @trace_async("retry_handler.check_idempotency")
    async def check_idempotency(
        self,
        idempotency_key: IdempotencyKey,
    ) -> Optional[Dict[str, Any]]:
        """Check if request has been processed before.
        
        Args:
            idempotency_key: Idempotency key to check
            
        Returns:
            Cached response if found, None otherwise
        """
        if not self.redis_manager:
            logger.warning("No Redis manager configured, idempotency check skipped")
            return None
        
        try:
            async with self.redis_manager.get_client() as redis:
                cached_data = await redis.get(idempotency_key.key)
                
                if cached_data:
                    logger.info(f"Found cached response for idempotency key: {idempotency_key.key}")
                    return json.loads(cached_data)
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to check idempotency: {e}")
            return None
    
    @trace_async("retry_handler.store_idempotency_result")
    async def store_idempotency_result(
        self,
        idempotency_key: IdempotencyKey,
        result: Dict[str, Any],
    ) -> None:
        """Store result for idempotency.
        
        Args:
            idempotency_key: Idempotency key
            result: Result to cache
        """
        if not self.redis_manager:
            logger.warning("No Redis manager configured, idempotency storage skipped")
            return
        
        try:
            async with self.redis_manager.get_client() as redis:
                # Calculate TTL in seconds
                now = datetime.now(timezone.utc)
                ttl_seconds = int((idempotency_key.expires_at - now).total_seconds())
                
                if ttl_seconds > 0:
                    await redis.setex(
                        idempotency_key.key,
                        ttl_seconds,
                        json.dumps(result, default=str)
                    )
                    logger.info(f"Stored idempotency result for key: {idempotency_key.key}")
                
        except Exception as e:
            logger.error(f"Failed to store idempotency result: {e}")
    
    def _hash_request_data(self, data: Dict[str, Any]) -> str:
        """Create hash of request data for idempotency.
        
        Args:
            data: Request data to hash
            
        Returns:
            SHA-256 hash of data
        """
        # Remove non-deterministic fields
        hashable_data = {k: v for k, v in data.items() if k not in [
            'correlation_id', 'timestamp', 'request_id'
        ]}
        
        # Sort keys for consistent hashing
        json_str = json.dumps(hashable_data, sort_keys=True, default=str)
        
        return hashlib.sha256(json_str.encode()).hexdigest()
    
    @trace_async("retry_handler.cleanup_expired_keys")
    async def cleanup_expired_keys(self) -> int:
        """Clean up expired idempotency keys.
        
        Returns:
            Number of keys cleaned up
        """
        if not self.redis_manager:
            return 0
        
        try:
            async with self.redis_manager.get_client() as redis:
                # Find all idempotency keys
                pattern = "idempotency:*"
                keys = await redis.keys(pattern)
                
                if not keys:
                    return 0
                
                # Check TTL and remove expired keys
                cleaned_count = 0
                for key in keys:
                    ttl = await redis.ttl(key)
                    if ttl == -2:  # Key doesn't exist
                        continue
                    elif ttl == -1:  # Key exists but no TTL
                        await redis.delete(key)
                        cleaned_count += 1
                
                logger.info(f"Cleaned up {cleaned_count} expired idempotency keys")
                return cleaned_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired keys: {e}")
            return 0