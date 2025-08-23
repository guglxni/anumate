"""Plan caching service with advanced caching strategies."""

import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any
from uuid import UUID
import json
import hashlib

import structlog
from pydantic import BaseModel

from .models import ExecutablePlan, PlanCacheEntry

logger = structlog.get_logger(__name__)


class CacheStats(BaseModel):
    """Cache statistics."""
    
    total_entries: int
    hit_count: int
    miss_count: int
    eviction_count: int
    total_size_bytes: int
    hit_ratio: float
    average_access_time: float


class CacheConfig(BaseModel):
    """Cache configuration."""
    
    max_entries: int = 1000
    max_size_bytes: int = 100 * 1024 * 1024  # 100MB
    default_ttl_hours: int = 24
    cleanup_interval_minutes: int = 30
    enable_lru_eviction: bool = True
    enable_size_based_eviction: bool = True
    enable_metrics: bool = True


class PlanCacheService:
    """Advanced caching service for ExecutablePlans."""
    
    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        
        # Cache storage
        self._cache: Dict[str, PlanCacheEntry] = {}
        self._access_order: List[str] = []  # For LRU eviction
        
        # Cache statistics
        self._stats = {
            "hit_count": 0,
            "miss_count": 0,
            "eviction_count": 0,
            "total_access_time": 0.0,
            "access_count": 0
        }
        
        # Cache indexes for efficient lookups
        self._tenant_index: Dict[UUID, Set[str]] = {}
        self._tag_index: Dict[str, Set[str]] = {}
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
    
    async def get(self, plan_hash: str, tenant_id: UUID) -> Optional[ExecutablePlan]:
        """Get a plan from cache."""
        
        # Ensure cleanup task is running
        await self._ensure_cleanup_task_running()
        
        start_time = time.time()
        
        try:
            if plan_hash not in self._cache:
                self._stats["miss_count"] += 1
                logger.debug("Cache miss", plan_hash=plan_hash, tenant_id=str(tenant_id))
                return None
            
            cache_entry = self._cache[plan_hash]
            
            # Check tenant access
            if cache_entry.tenant_id != tenant_id:
                self._stats["miss_count"] += 1
                logger.warning(
                    "Cache access denied - tenant mismatch",
                    plan_hash=plan_hash,
                    cache_tenant_id=str(cache_entry.tenant_id),
                    requesting_tenant_id=str(tenant_id)
                )
                return None
            
            # Check expiration
            if cache_entry.expires_at and cache_entry.expires_at < datetime.now(timezone.utc):
                await self._evict(plan_hash)
                self._stats["miss_count"] += 1
                logger.debug("Cache miss - expired", plan_hash=plan_hash)
                return None
            
            # Update access metadata
            cache_entry.access_count += 1
            cache_entry.last_accessed = datetime.now(timezone.utc)
            
            # Update LRU order
            if plan_hash in self._access_order:
                self._access_order.remove(plan_hash)
            self._access_order.append(plan_hash)
            
            self._stats["hit_count"] += 1
            
            logger.debug(
                "Cache hit",
                plan_hash=plan_hash,
                tenant_id=str(tenant_id),
                access_count=cache_entry.access_count
            )
            
            return cache_entry.plan
            
        finally:
            access_time = time.time() - start_time
            self._stats["total_access_time"] += access_time
            self._stats["access_count"] += 1
    
    async def put(
        self,
        plan: ExecutablePlan,
        ttl_hours: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Put a plan in cache."""
        
        try:
            # Check if we need to evict entries first
            await self._ensure_capacity()
            
            # Calculate expiration
            ttl = ttl_hours or self.config.default_ttl_hours
            expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl)
            
            # Create cache entry
            cache_entry = PlanCacheEntry(
                plan_hash=plan.plan_hash,
                tenant_id=plan.tenant_id,
                plan=plan,
                expires_at=expires_at,
                tags=tags or []
            )
            
            # Store in cache
            self._cache[plan.plan_hash] = cache_entry
            
            # Update indexes
            if plan.tenant_id not in self._tenant_index:
                self._tenant_index[plan.tenant_id] = set()
            self._tenant_index[plan.tenant_id].add(plan.plan_hash)
            
            for tag in cache_entry.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(plan.plan_hash)
            
            # Update LRU order
            if plan.plan_hash in self._access_order:
                self._access_order.remove(plan.plan_hash)
            self._access_order.append(plan.plan_hash)
            
            logger.info(
                "Plan cached successfully",
                plan_hash=plan.plan_hash,
                tenant_id=str(plan.tenant_id),
                expires_at=expires_at.isoformat(),
                tags=tags
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "Failed to cache plan",
                plan_hash=plan.plan_hash,
                error=str(e)
            )
            return False
    
    async def invalidate(self, plan_hash: str) -> bool:
        """Invalidate a specific plan from cache."""
        
        if plan_hash in self._cache:
            await self._evict(plan_hash)
            logger.info("Plan invalidated from cache", plan_hash=plan_hash)
            return True
        
        return False
    
    async def invalidate_by_tenant(self, tenant_id: UUID) -> int:
        """Invalidate all plans for a tenant."""
        
        if tenant_id not in self._tenant_index:
            return 0
        
        plan_hashes = list(self._tenant_index[tenant_id])
        count = 0
        
        for plan_hash in plan_hashes:
            if await self.invalidate(plan_hash):
                count += 1
        
        logger.info(
            "Plans invalidated by tenant",
            tenant_id=str(tenant_id),
            count=count
        )
        
        return count
    
    async def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all plans with a specific tag."""
        
        if tag not in self._tag_index:
            return 0
        
        plan_hashes = list(self._tag_index[tag])
        count = 0
        
        for plan_hash in plan_hashes:
            if await self.invalidate(plan_hash):
                count += 1
        
        logger.info(
            "Plans invalidated by tag",
            tag=tag,
            count=count
        )
        
        return count
    
    async def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        
        total_entries = len(self._cache)
        total_size = sum(
            len(json.dumps(entry.plan.model_dump(), default=str))
            for entry in self._cache.values()
        )
        
        hit_ratio = 0.0
        if self._stats["hit_count"] + self._stats["miss_count"] > 0:
            hit_ratio = self._stats["hit_count"] / (self._stats["hit_count"] + self._stats["miss_count"])
        
        avg_access_time = 0.0
        if self._stats["access_count"] > 0:
            avg_access_time = self._stats["total_access_time"] / self._stats["access_count"]
        
        return CacheStats(
            total_entries=total_entries,
            hit_count=self._stats["hit_count"],
            miss_count=self._stats["miss_count"],
            eviction_count=self._stats["eviction_count"],
            total_size_bytes=total_size,
            hit_ratio=hit_ratio,
            average_access_time=avg_access_time
        )
    
    async def clear(self) -> int:
        """Clear all cache entries."""
        
        count = len(self._cache)
        self._cache.clear()
        self._access_order.clear()
        self._tenant_index.clear()
        self._tag_index.clear()
        
        logger.info("Cache cleared", entries_removed=count)
        return count
    
    async def _ensure_capacity(self):
        """Ensure cache has capacity for new entries."""
        
        # Check entry count limit
        if len(self._cache) >= self.config.max_entries:
            await self._evict_lru()
        
        # Check size limit
        if self.config.enable_size_based_eviction:
            current_size = sum(
                len(json.dumps(entry.plan.model_dump(), default=str))
                for entry in self._cache.values()
            )
            
            while current_size > self.config.max_size_bytes and self._cache:
                await self._evict_lru()
                current_size = sum(
                    len(json.dumps(entry.plan.model_dump(), default=str))
                    for entry in self._cache.values()
                )
    
    async def _evict_lru(self):
        """Evict least recently used entry."""
        
        if not self._access_order:
            return
        
        lru_hash = self._access_order[0]
        await self._evict(lru_hash)
    
    async def _evict(self, plan_hash: str):
        """Evict a specific entry from cache."""
        
        if plan_hash not in self._cache:
            return
        
        cache_entry = self._cache[plan_hash]
        
        # Remove from cache
        del self._cache[plan_hash]
        
        # Remove from access order
        if plan_hash in self._access_order:
            self._access_order.remove(plan_hash)
        
        # Remove from tenant index
        if cache_entry.tenant_id in self._tenant_index:
            self._tenant_index[cache_entry.tenant_id].discard(plan_hash)
            if not self._tenant_index[cache_entry.tenant_id]:
                del self._tenant_index[cache_entry.tenant_id]
        
        # Remove from tag indexes
        for tag in cache_entry.tags:
            if tag in self._tag_index:
                self._tag_index[tag].discard(plan_hash)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]
        
        self._stats["eviction_count"] += 1
        
        logger.debug(
            "Cache entry evicted",
            plan_hash=plan_hash,
            tenant_id=str(cache_entry.tenant_id)
        )
    
    def _start_cleanup_task(self):
        """Start background cleanup task."""
        
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(self.config.cleanup_interval_minutes * 60)
                    await self._cleanup_expired()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error("Cache cleanup error", error=str(e))
        
        try:
            # Only start cleanup task if there's a running event loop
            asyncio.get_running_loop()
            self._cleanup_task = asyncio.create_task(cleanup_loop())
        except RuntimeError:
            # No event loop running, cleanup task will be started later
            self._cleanup_task = None
    
    async def _cleanup_expired(self):
        """Clean up expired cache entries."""
        
        now = datetime.now(timezone.utc)
        expired_hashes = []
        
        for plan_hash, cache_entry in self._cache.items():
            if cache_entry.expires_at and cache_entry.expires_at < now:
                expired_hashes.append(plan_hash)
        
        for plan_hash in expired_hashes:
            await self._evict(plan_hash)
        
        if expired_hashes:
            logger.info(
                "Expired cache entries cleaned up",
                count=len(expired_hashes)
            )
    
    async def shutdown(self):
        """Shutdown the cache service."""
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Cache service shutdown")
    
    async def _ensure_cleanup_task_running(self):
        """Ensure the cleanup task is running."""
        
        if self._cleanup_task is None or self._cleanup_task.done():
            try:
                async def cleanup_loop():
                    while True:
                        try:
                            await asyncio.sleep(self.config.cleanup_interval_minutes * 60)
                            await self._cleanup_expired()
                        except asyncio.CancelledError:
                            break
                        except Exception as e:
                            logger.error("Cache cleanup error", error=str(e))
                
                self._cleanup_task = asyncio.create_task(cleanup_loop())
            except RuntimeError:
                # No event loop running
                pass


# Global cache instance
_cache_service: Optional[PlanCacheService] = None


def get_cache_service() -> PlanCacheService:
    """Get the global cache service instance."""
    
    global _cache_service
    if _cache_service is None:
        _cache_service = PlanCacheService()
    
    return _cache_service