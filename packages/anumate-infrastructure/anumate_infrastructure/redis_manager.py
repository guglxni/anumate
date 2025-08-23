"""Redis manager with tenant-aware caching and rate limiting."""

import json
import os
from typing import Any, Optional, Union
from uuid import UUID

import redis.asyncio as redis
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from .tenant_context import get_current_tenant_id

logger = structlog.get_logger(__name__)


class RedisManager:
    """Redis manager with automatic tenant prefixing."""
    
    def __init__(self, redis_url: Optional[str] = None) -> None:
        """Initialize Redis manager."""
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", 
            "redis://localhost:6379"
        )
        self._client: Optional[redis.Redis] = None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            await self._client.ping()
            logger.info("Redis client created and connected")
        return self._client
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.info("Redis client closed")
    
    def _get_tenant_key(self, key: str) -> str:
        """Get tenant-prefixed key."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise ValueError("No tenant context set. Use TenantContext manager.")
        return f"tenant:{tenant_id}:{key}"
    
    def _get_global_key(self, key: str) -> str:
        """Get global (non-tenant) key."""
        return f"global:{key}"
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ex: Optional[int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False,
        global_key: bool = False
    ) -> bool:
        """Set a key-value pair with optional expiration."""
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(key)
        else:
            full_key = self._get_tenant_key(key)
        
        # Serialize value if it's not a string
        if not isinstance(value, str):
            value = json.dumps(value)
        
        result = await client.set(
            full_key, 
            value, 
            ex=ex, 
            px=px, 
            nx=nx, 
            xx=xx
        )
        
        logger.debug("Set Redis key", key=full_key, ex=ex, px=px)
        return result
    
    async def get(self, key: str, global_key: bool = False) -> Optional[str]:
        """Get value by key."""
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(key)
        else:
            full_key = self._get_tenant_key(key)
        
        value = await client.get(full_key)
        logger.debug("Get Redis key", key=full_key, found=value is not None)
        return value
    
    async def get_json(self, key: str, global_key: bool = False) -> Optional[Any]:
        """Get and deserialize JSON value."""
        value = await self.get(key, global_key=global_key)
        if value is None:
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning("Failed to decode JSON value", key=key, value=value)
            return None
    
    async def delete(self, *keys: str, global_key: bool = False) -> int:
        """Delete one or more keys."""
        client = await self.get_client()
        
        if global_key:
            full_keys = [self._get_global_key(key) for key in keys]
        else:
            full_keys = [self._get_tenant_key(key) for key in keys]
        
        result = await client.delete(*full_keys)
        logger.debug("Deleted Redis keys", keys=full_keys, count=result)
        return result
    
    async def exists(self, key: str, global_key: bool = False) -> bool:
        """Check if key exists."""
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(key)
        else:
            full_key = self._get_tenant_key(key)
        
        result = await client.exists(full_key)
        return bool(result)
    
    async def expire(self, key: str, seconds: int, global_key: bool = False) -> bool:
        """Set expiration on key."""
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(key)
        else:
            full_key = self._get_tenant_key(key)
        
        result = await client.expire(full_key, seconds)
        logger.debug("Set expiration on Redis key", key=full_key, seconds=seconds)
        return result
    
    async def incr(self, key: str, amount: int = 1, global_key: bool = False) -> int:
        """Increment key value."""
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(key)
        else:
            full_key = self._get_tenant_key(key)
        
        result = await client.incrby(full_key, amount)
        logger.debug("Incremented Redis key", key=full_key, amount=amount, new_value=result)
        return result
    
    async def rate_limit(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int,
        global_key: bool = False
    ) -> tuple[bool, int, int]:
        """
        Rate limiting using sliding window.
        
        Returns:
            (allowed, current_count, reset_time)
        """
        client = await self.get_client()
        
        if global_key:
            full_key = self._get_global_key(f"rate_limit:{key}")
        else:
            full_key = self._get_tenant_key(f"rate_limit:{key}")
        
        # Use Lua script for atomic rate limiting
        lua_script = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        
        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
        
        -- Count current entries
        local current = redis.call('ZCARD', key)
        
        if current < limit then
            -- Add current request
            redis.call('ZADD', key, now, now)
            redis.call('EXPIRE', key, window)
            return {1, current + 1, now + window}
        else
            return {0, current, now + window}
        end
        """
        
        import time
        now = int(time.time())
        
        result = await client.eval(
            lua_script, 
            1, 
            full_key, 
            limit, 
            window_seconds, 
            now
        )
        
        allowed = bool(result[0])
        current_count = int(result[1])
        reset_time = int(result[2])
        
        logger.debug(
            "Rate limit check", 
            key=full_key, 
            allowed=allowed, 
            current=current_count, 
            limit=limit
        )
        
        return allowed, current_count, reset_time