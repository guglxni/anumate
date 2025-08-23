"""
Replay Protection Service for CapTokens
=======================================

Production-grade Redis-backed replay attack prevention service.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from ..models import ReplayProtection
from anumate_logging import get_logger

logger = get_logger(__name__)


class ReplayProtectionService:
    """
    Production-grade replay protection service using Redis and database.
    
    Features:
    - Redis-backed fast lookup
    - Database persistence for audit
    - Configurable TTL policies
    - Token nonce tracking
    - Performance optimized
    - High availability support
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        redis_client: Optional[redis.Redis] = None,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "anumate:replay:",
    ):
        self.db = db_session
        self.redis_client = redis_client or redis.from_url(redis_url, decode_responses=True)
        self.key_prefix = key_prefix
    
    def _get_redis_key(self, token_jti: str) -> str:
        """Generate Redis key for token JTI."""
        return f"{self.key_prefix}{token_jti}"
    
    def _get_token_hash(self, token: str) -> str:
        """Generate consistent hash for token."""
        return hashlib.sha256(token.encode()).hexdigest()
    
    async def check_and_record_token_use(
        self,
        token: str,
        token_jti: str,
        expires_at: datetime,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check if token has been used before and record this usage.
        
        Args:
            token: The JWT token
            token_jti: JWT ID claim (unique identifier)
            expires_at: Token expiration time
            client_ip: Client IP address
            user_agent: Client user agent
            
        Returns:
            Dictionary with replay check results
        """
        try:
            redis_key = self._get_redis_key(token_jti)
            token_hash = self._get_token_hash(token)
            
            # Check Redis first (fast path)
            redis_exists = await self.redis_client.exists(redis_key)
            
            if redis_exists:
                # Token has been used before - replay attack detected
                usage_data = await self.redis_client.hgetall(redis_key)
                
                # Update usage count
                new_count = int(usage_data.get('usage_count', 0)) + 1
                await self.redis_client.hset(
                    redis_key,
                    mapping={
                        'usage_count': str(new_count),
                        'last_used_at': datetime.utcnow().isoformat(),
                        'last_used_ip': client_ip or '',
                    }
                )
                
                # Update database record
                await self.db.execute(
                    self.db.query(ReplayProtection)
                    .filter(ReplayProtection.token_jti == token_jti)
                    .update({
                        ReplayProtection.usage_count: new_count,
                        ReplayProtection.last_used_at: datetime.utcnow(),
                    })
                )
                await self.db.commit()
                
                logger.warning(
                    "Replay attack detected",
                    extra={
                        "token_jti": token_jti,
                        "usage_count": new_count,
                        "first_seen_ip": usage_data.get('first_seen_ip'),
                        "current_ip": client_ip,
                        "token_hash": token_hash[:16] + "...",
                    }
                )
                
                return {
                    "is_replay": True,
                    "usage_count": new_count,
                    "first_seen_at": usage_data.get('first_seen_at'),
                    "first_seen_ip": usage_data.get('first_seen_ip'),
                    "message": "Token has been used before - potential replay attack"
                }
            
            # First time seeing this token - record it
            current_time = datetime.utcnow()
            ttl_seconds = int((expires_at - current_time).total_seconds())
            
            if ttl_seconds <= 0:
                # Token already expired
                return {
                    "is_replay": False,
                    "is_expired": True,
                    "message": "Token is already expired"
                }
            
            # Store in Redis with TTL
            token_data = {
                'token_hash': token_hash,
                'usage_count': '1',
                'first_seen_at': current_time.isoformat(),
                'first_seen_ip': client_ip or '',
                'first_seen_user_agent': user_agent or '',
                'last_used_at': current_time.isoformat(),
                'expires_at': expires_at.isoformat(),
            }
            
            await self.redis_client.hset(redis_key, mapping=token_data)
            await self.redis_client.expire(redis_key, ttl_seconds)
            
            # Store in database for audit persistence
            replay_record = ReplayProtection(
                token_jti=token_jti,
                token_hash=token_hash,
                expires_at=expires_at,
                first_seen_ip=client_ip,
                first_seen_user_agent=user_agent,
                usage_count=1,
                last_used_at=current_time,
            )
            
            self.db.add(replay_record)
            await self.db.commit()
            
            logger.info(
                "Token recorded for replay protection",
                extra={
                    "token_jti": token_jti,
                    "expires_at": expires_at.isoformat(),
                    "client_ip": client_ip,
                    "ttl_seconds": ttl_seconds,
                }
            )
            
            return {
                "is_replay": False,
                "usage_count": 1,
                "first_seen_at": current_time.isoformat(),
                "ttl_seconds": ttl_seconds,
                "message": "Token recorded successfully"
            }
            
        except redis.RedisError as e:
            logger.error(
                "Redis error in replay protection",
                extra={
                    "error": str(e),
                    "token_jti": token_jti,
                }
            )
            # Fallback to database-only check
            return await self._database_replay_check(token_jti, token_hash, expires_at, client_ip, user_agent)
            
        except Exception as e:
            logger.error(
                "Error in replay protection check",
                extra={
                    "error": str(e),
                    "token_jti": token_jti,
                }
            )
            raise
    
    async def _database_replay_check(
        self,
        token_jti: str,
        token_hash: str,
        expires_at: datetime,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fallback database-only replay protection check.
        
        Used when Redis is unavailable.
        """
        try:
            # Check if token exists in database
            query = select(ReplayProtection).where(ReplayProtection.token_jti == token_jti)
            result = await self.db.execute(query)
            existing_record = result.scalar_one_or_none()
            
            if existing_record:
                # Update usage count
                existing_record.usage_count += 1
                existing_record.last_used_at = datetime.utcnow()
                await self.db.commit()
                
                logger.warning(
                    "Replay attack detected (database fallback)",
                    extra={
                        "token_jti": token_jti,
                        "usage_count": existing_record.usage_count,
                    }
                )
                
                return {
                    "is_replay": True,
                    "usage_count": existing_record.usage_count,
                    "first_seen_at": existing_record.created_at.isoformat(),
                    "message": "Token has been used before - potential replay attack (database fallback)"
                }
            
            # First time seeing this token
            current_time = datetime.utcnow()
            replay_record = ReplayProtection(
                token_jti=token_jti,
                token_hash=token_hash,
                expires_at=expires_at,
                first_seen_ip=client_ip,
                first_seen_user_agent=user_agent,
                usage_count=1,
                last_used_at=current_time,
            )
            
            self.db.add(replay_record)
            await self.db.commit()
            
            logger.info(
                "Token recorded for replay protection (database fallback)",
                extra={"token_jti": token_jti}
            )
            
            return {
                "is_replay": False,
                "usage_count": 1,
                "first_seen_at": current_time.isoformat(),
                "message": "Token recorded successfully (database fallback)"
            }
            
        except Exception as e:
            logger.error(
                "Error in database replay protection fallback",
                extra={
                    "error": str(e),
                    "token_jti": token_jti,
                }
            )
            raise
    
    async def invalidate_token(self, token_jti: str) -> bool:
        """
        Immediately invalidate a token in both Redis and database.
        
        Args:
            token_jti: JWT ID claim
            
        Returns:
            True if invalidated, False if not found
        """
        try:
            redis_key = self._get_redis_key(token_jti)
            
            # Remove from Redis
            redis_deleted = await self.redis_client.delete(redis_key)
            
            # Remove from database
            db_result = await self.db.execute(
                delete(ReplayProtection).where(ReplayProtection.token_jti == token_jti)
            )
            db_deleted = db_result.rowcount
            
            await self.db.commit()
            
            success = redis_deleted > 0 or db_deleted > 0
            
            if success:
                logger.info(
                    "Token invalidated from replay protection",
                    extra={
                        "token_jti": token_jti,
                        "redis_deleted": redis_deleted > 0,
                        "db_deleted": db_deleted > 0,
                    }
                )
            
            return success
            
        except Exception as e:
            logger.error(
                "Error invalidating token",
                extra={
                    "error": str(e),
                    "token_jti": token_jti,
                }
            )
            raise
    
    async def get_token_usage_stats(self, token_jti: str) -> Optional[Dict[str, Any]]:
        """
        Get usage statistics for a specific token.
        
        Args:
            token_jti: JWT ID claim
            
        Returns:
            Token usage statistics or None if not found
        """
        try:
            redis_key = self._get_redis_key(token_jti)
            
            # Try Redis first
            redis_data = await self.redis_client.hgetall(redis_key)
            
            if redis_data:
                return {
                    "token_jti": token_jti,
                    "usage_count": int(redis_data.get('usage_count', 0)),
                    "first_seen_at": redis_data.get('first_seen_at'),
                    "first_seen_ip": redis_data.get('first_seen_ip'),
                    "last_used_at": redis_data.get('last_used_at'),
                    "expires_at": redis_data.get('expires_at'),
                    "source": "redis"
                }
            
            # Fallback to database
            query = select(ReplayProtection).where(ReplayProtection.token_jti == token_jti)
            result = await self.db.execute(query)
            record = result.scalar_one_or_none()
            
            if record:
                return {
                    "token_jti": token_jti,
                    "usage_count": record.usage_count,
                    "first_seen_at": record.created_at.isoformat(),
                    "first_seen_ip": record.first_seen_ip,
                    "last_used_at": record.last_used_at.isoformat(),
                    "expires_at": record.expires_at.isoformat(),
                    "source": "database"
                }
            
            return None
            
        except Exception as e:
            logger.error(
                "Error retrieving token usage stats",
                extra={
                    "error": str(e),
                    "token_jti": token_jti,
                }
            )
            raise
    
    async def cleanup_expired_records(self, batch_size: int = 1000) -> Dict[str, Any]:
        """
        Clean up expired replay protection records.
        
        Args:
            batch_size: Number of records to process per batch
            
        Returns:
            Cleanup results
        """
        try:
            current_time = datetime.utcnow()
            total_cleaned = 0
            
            # Clean up database records
            while True:
                delete_result = await self.db.execute(
                    delete(ReplayProtection)
                    .where(ReplayProtection.expires_at < current_time)
                    .limit(batch_size)
                )
                
                batch_cleaned = delete_result.rowcount
                total_cleaned += batch_cleaned
                
                await self.db.commit()
                
                if batch_cleaned == 0:
                    break
            
            # Note: Redis keys will expire automatically due to TTL
            
            logger.info(
                "Cleaned up expired replay protection records",
                extra={
                    "total_cleaned": total_cleaned,
                    "batch_size": batch_size,
                }
            )
            
            return {
                "total_cleaned": total_cleaned,
                "cleanup_time": current_time.isoformat(),
            }
            
        except Exception as e:
            logger.error(
                "Error cleaning up replay protection records",
                extra={"error": str(e)}
            )
            raise
