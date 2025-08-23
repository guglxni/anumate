"""
CapTokens Service Classes
========================

Production-grade service classes for token management, auditing, and cleanup.
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.orm import selectinload

from .models import CapabilityToken, TokenAuditLog, ReplayProtection, TokenCleanupJob

# Import logging with fallback
try:
    from anumate_logging import get_logger
except ImportError:
    import logging
    def get_logger(name: str):
        return logging.getLogger(name)

logger = get_logger(__name__)


class DatabaseTokenService:
    """Service for capability token management."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the token service."""
        self.db = db_session

    def _hash_token(self, token: str) -> str:
        """Create a secure hash of the token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()

    async def store_token(
        self,
        token_id: UUID,
        tenant_id: UUID,
        token_hash: str,
        subject: str,
        capabilities: List[str],
        expires_at: datetime,
        created_by: UUID,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> CapabilityToken:
        """Store a new capability token in the database."""
        try:
            token_record = CapabilityToken(
                token_id=token_id,
                tenant_id=tenant_id,
                token_hash=token_hash,
                subject=subject,
                capabilities=capabilities,
                expires_at=expires_at,
                created_by=created_by,
                client_ip=client_ip,
                user_agent=user_agent,
            )
            
            self.db.add(token_record)
            await self.db.commit()
            await self.db.refresh(token_record)
            
            logger.info(f"Token stored successfully: {token_id}")
            return token_record

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to store token: {e}")
            raise

    async def get_token(self, token_id: UUID) -> Optional[CapabilityToken]:
        """Retrieve a token by ID."""
        try:
            result = await self.db.execute(
                select(CapabilityToken).where(CapabilityToken.token_id == token_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Failed to retrieve token {token_id}: {e}")
            raise

    async def revoke_token(self, token_id: UUID, revoked_by: UUID) -> bool:
        """Revoke a capability token."""
        try:
            result = await self.db.execute(
                update(CapabilityToken)
                .where(CapabilityToken.token_id == token_id)
                .values(revoked_at=datetime.utcnow(), revoked_by=revoked_by, active=False)
            )
            
            if result.rowcount > 0:
                await self.db.commit()
                logger.info(f"Token revoked successfully: {token_id}")
                return True
            else:
                logger.warning(f"Token not found for revocation: {token_id}")
                return False

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to revoke token {token_id}: {e}")
            raise

    async def cleanup_expired_tokens(self, batch_size: int = 1000) -> int:
        """Clean up expired tokens."""
        try:
            current_time = datetime.utcnow()
            
            # Delete expired tokens
            result = await self.db.execute(
                delete(CapabilityToken)
                .where(CapabilityToken.expires_at < current_time)
                .execution_options(synchronize_session=False)
            )
            
            deleted_count = result.rowcount
            await self.db.commit()
            
            logger.info(f"Cleaned up {deleted_count} expired tokens")
            return deleted_count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to cleanup expired tokens: {e}")
            raise


class AuditService:
    """Service for audit trail management."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the audit service."""
        self.db = db_session

    async def log_operation(
        self,
        tenant_id: UUID,
        token_id: UUID,
        operation: str,
        status: str,
        request_data: Optional[Dict[str, Any]] = None,
        response_data: Optional[Dict[str, Any]] = None,
        error_details: Optional[Dict[str, Any]] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> TokenAuditLog:
        """Log an audit trail entry."""
        try:
            audit_log = TokenAuditLog(
                tenant_id=tenant_id,
                token_id=token_id,
                operation=operation,
                status=status,
                request_data=request_data or {},
                response_data=response_data or {},
                error_details=error_details,
                endpoint=endpoint,
                http_method=http_method,
                client_ip=client_ip,
                user_agent=user_agent,
                duration_ms=duration_ms,
            )
            
            self.db.add(audit_log)
            await self.db.commit()
            
            return audit_log

        except Exception as e:
            # Don't rollback here since this might be called in background tasks
            logger.error(f"Failed to log audit trail: {e}")
            raise

    async def get_audit_trail(
        self,
        tenant_id: UUID,
        token_id: Optional[UUID] = None,
        operation: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Retrieve audit trail records."""
        try:
            query = select(TokenAuditLog).where(TokenAuditLog.tenant_id == tenant_id)
            
            if token_id:
                query = query.where(TokenAuditLog.token_id == token_id)
            
            if operation:
                query = query.where(TokenAuditLog.operation == operation)
            
            # Count total records
            count_query = select(func.count()).select_from(query.subquery())
            total_count = await self.db.scalar(count_query)
            
            # Get paginated results
            query = query.order_by(TokenAuditLog.created_at.desc()).limit(limit).offset(offset)
            result = await self.db.execute(query)
            records = result.scalars().all()
            
            return {
                "audit_records": [
                    {
                        "id": str(record.audit_id),
                        "tenant_id": str(record.tenant_id),
                        "token_id": str(record.token_id),
                        "operation": record.operation,
                        "status": record.status,
                        "request_data": record.request_data,
                        "response_data": record.response_data,
                        "error_details": record.error_details,
                        "endpoint": record.endpoint,
                        "http_method": record.http_method,
                        "client_ip": record.client_ip,
                        "user_agent": record.user_agent,
                        "duration_ms": record.duration_ms,
                        "created_at": record.created_at.isoformat(),
                    }
                    for record in records
                ],
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            }

        except Exception as e:
            logger.error(f"Failed to retrieve audit trail: {e}")
            raise


class ReplayProtectionService:
    """Service for replay attack protection."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the replay protection service."""
        self.db = db_session

    async def check_and_record_token_use(
        self,
        token: str,
        token_jti: str,
        expires_at: datetime,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check for replay attacks and record token usage."""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Check if token has been used before
            result = await self.db.execute(
                select(ReplayProtection).where(ReplayProtection.token_jti == token_jti)
            )
            existing_record = result.scalar_one_or_none()
            
            if existing_record:
                # Token has been used before - potential replay
                existing_record.usage_count += 1
                existing_record.last_used_at = datetime.utcnow()
                
                await self.db.commit()
                
                return {
                    "is_replay": True,
                    "usage_count": existing_record.usage_count,
                    "first_used_at": existing_record.created_at,
                    "last_used_at": existing_record.last_used_at,
                }
            else:
                # First time use - record it
                replay_record = ReplayProtection(
                    token_jti=token_jti,
                    token_hash=token_hash,
                    expires_at=expires_at,
                    first_seen_ip=client_ip,
                    first_seen_user_agent=user_agent,
                )
                
                self.db.add(replay_record)
                await self.db.commit()
                
                return {
                    "is_replay": False,
                    "usage_count": 1,
                    "first_used_at": replay_record.created_at,
                    "last_used_at": replay_record.last_used_at,
                }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to check replay protection: {e}")
            raise

    async def cleanup_expired_records(self, batch_size: int = 1000) -> int:
        """Clean up expired replay protection records."""
        try:
            current_time = datetime.utcnow()
            
            result = await self.db.execute(
                delete(ReplayProtection)
                .where(ReplayProtection.expires_at < current_time)
                .execution_options(synchronize_session=False)
            )
            
            deleted_count = result.rowcount
            await self.db.commit()
            
            logger.info(f"Cleaned up {deleted_count} expired replay protection records")
            return deleted_count

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to cleanup replay protection records: {e}")
            raise


class CleanupService:
    """Service for background cleanup operations."""

    def __init__(self, db_session: AsyncSession):
        """Initialize the cleanup service."""
        self.db = db_session

    async def run_cleanup_job(self, job_type: str, job_config: Optional[Dict[str, Any]] = None) -> UUID:
        """Run a cleanup job and track its progress."""
        try:
            job_id = uuid.uuid4()
            
            # Create job record
            job_record = TokenCleanupJob(
                job_id=job_id,
                job_type=job_type,
                status="running",
                cleanup_config=job_config or {},
            )
            
            self.db.add(job_record)
            await self.db.commit()
            
            total_deleted = 0
            
            try:
                if job_type == "expired_tokens":
                    token_service = DatabaseTokenService(self.db)
                    deleted_count = await token_service.cleanup_expired_tokens()
                    total_deleted += deleted_count
                    
                elif job_type == "expired_replay_records":
                    replay_service = ReplayProtectionService(self.db)
                    deleted_count = await replay_service.cleanup_expired_records()
                    total_deleted += deleted_count
                    
                elif job_type == "old_audit_logs":
                    # Clean up audit logs older than configured period
                    retention_days = job_config.get("retention_days", 90) if job_config else 90
                    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                    
                    result = await self.db.execute(
                        delete(TokenAuditLog)
                        .where(TokenAuditLog.created_at < cutoff_date)
                        .execution_options(synchronize_session=False)
                    )
                    
                    total_deleted = result.rowcount
                    await self.db.commit()
                    
                else:
                    raise ValueError(f"Unknown job type: {job_type}")
                
                # Update job as completed
                await self.db.execute(
                    update(TokenCleanupJob)
                    .where(TokenCleanupJob.job_id == job_id)
                    .values(
                        status="completed",
                        completed_at=datetime.utcnow(),
                        tokens_processed=total_deleted,
                        tokens_cleaned=total_deleted,
                    )
                )
                await self.db.commit()
                
                logger.info(f"Cleanup job {job_type} completed: {total_deleted} records deleted")
                
            except Exception as e:
                # Update job as failed
                await self.db.execute(
                    update(TokenCleanupJob)
                    .where(TokenCleanupJob.job_id == job_id)
                    .values(
                        status="failed",
                        completed_at=datetime.utcnow(),
                        error_details={"error": str(e)},
                    )
                )
                await self.db.commit()
                raise
            
            return job_id

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to run cleanup job {job_type}: {e}")
            raise

    async def get_job_status(self, job_id: UUID) -> Optional[Dict[str, Any]]:
        """Get the status of a cleanup job."""
        try:
            result = await self.db.execute(
                select(TokenCleanupJob).where(TokenCleanupJob.job_id == job_id)
            )
            job = result.scalar_one_or_none()
            
            if not job:
                return None
            
            return {
                "id": str(job.job_id),
                "job_type": job.job_type,
                "status": job.status,
                "started_at": job.started_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "tokens_processed": job.tokens_processed,
                "tokens_cleaned": job.tokens_cleaned,
                "error_details": job.error_details,
                "cleanup_config": job.cleanup_config,
            }

        except Exception as e:
            logger.error(f"Failed to get job status for {job_id}: {e}")
            raise
