"""
Cleanup Service for CapTokens
=============================

Production-grade background cleanup service for expired and revoked tokens.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, func, update
from sqlalchemy.sql import text

from ..models import CapabilityToken, TokenAuditLog, TokenCleanupJob, ReplayProtection
from anumate_logging import get_logger

logger = get_logger(__name__)


class CleanupService:
    """
    Production-grade cleanup service for token lifecycle management.
    
    Features:
    - Automatic expired token cleanup
    - Revoked token cleanup
    - Replay protection cleanup
    - Job tracking and monitoring
    - Configurable cleanup policies
    - Error handling and retry logic
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
    
    async def cleanup_expired_tokens(
        self,
        batch_size: int = 1000,
        max_age_days: int = 30,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Clean up expired tokens and their associated data.
        
        Args:
            batch_size: Number of tokens to process per batch
            max_age_days: Maximum age for expired tokens before cleanup
            dry_run: If True, only count tokens without deleting
            
        Returns:
            Cleanup results and statistics
        """
        job_id = uuid.uuid4()
        cleanup_config = {
            "batch_size": batch_size,
            "max_age_days": max_age_days,
            "dry_run": dry_run,
            "cleanup_type": "expired_tokens"
        }
        
        # Create cleanup job record
        job = TokenCleanupJob(
            job_id=job_id,
            job_type="expired_tokens",
            cleanup_config=cleanup_config,
        )
        
        try:
            self.db.add(job)
            await self.db.commit()
            
            logger.info(
                "Starting expired token cleanup",
                extra={
                    "job_id": str(job_id),
                    "batch_size": batch_size,
                    "max_age_days": max_age_days,
                    "dry_run": dry_run,
                }
            )
            
            cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
            total_processed = 0
            total_cleaned = 0
            errors = 0
            
            while True:
                # Find expired tokens
                query = select(CapabilityToken).where(
                    and_(
                        CapabilityToken.expires_at < cutoff_date,
                        CapabilityToken.active == False
                    )
                ).limit(batch_size)
                
                result = await self.db.execute(query)
                expired_tokens = result.scalars().all()
                
                if not expired_tokens:
                    break
                
                token_ids = [token.token_id for token in expired_tokens]
                batch_processed = len(expired_tokens)
                total_processed += batch_processed
                
                if not dry_run:
                    try:
                        # Delete audit logs first (foreign key constraint)
                        await self.db.execute(
                            delete(TokenAuditLog).where(
                                TokenAuditLog.token_id.in_(token_ids)
                            )
                        )
                        
                        # Delete replay protection records
                        token_hashes = [token.token_hash for token in expired_tokens]
                        await self.db.execute(
                            delete(ReplayProtection).where(
                                ReplayProtection.token_hash.in_(token_hashes)
                            )
                        )
                        
                        # Delete tokens
                        deleted_result = await self.db.execute(
                            delete(CapabilityToken).where(
                                CapabilityToken.token_id.in_(token_ids)
                            )
                        )
                        
                        batch_cleaned = deleted_result.rowcount
                        total_cleaned += batch_cleaned
                        
                        await self.db.commit()
                        
                        logger.debug(
                            "Cleaned up expired tokens batch",
                            extra={
                                "job_id": str(job_id),
                                "batch_processed": batch_processed,
                                "batch_cleaned": batch_cleaned,
                            }
                        )
                        
                    except Exception as e:
                        logger.error(
                            "Error cleaning up tokens batch",
                            extra={
                                "job_id": str(job_id),
                                "error": str(e),
                                "batch_size": batch_processed,
                            }
                        )
                        await self.db.rollback()
                        errors += 1
                        
                        if errors > 5:  # Max errors before stopping
                            break
                else:
                    # Dry run - just count
                    total_cleaned += batch_processed
                
                # Small delay to avoid overwhelming the database
                await asyncio.sleep(0.1)
            
            # Update job with results
            completion_time = datetime.utcnow()
            duration = int((completion_time - job.started_at).total_seconds())
            
            await self.db.execute(
                update(TokenCleanupJob)
                .where(TokenCleanupJob.job_id == job_id)
                .values(
                    status="completed",
                    completed_at=completion_time,
                    duration_seconds=duration,
                    tokens_processed=total_processed,
                    tokens_cleaned=total_cleaned,
                    errors_encountered=errors,
                )
            )
            await self.db.commit()
            
            results = {
                "job_id": str(job_id),
                "status": "completed",
                "tokens_processed": total_processed,
                "tokens_cleaned": total_cleaned,
                "errors_encountered": errors,
                "duration_seconds": duration,
                "dry_run": dry_run,
            }
            
            logger.info(
                "Completed expired token cleanup",
                extra=results
            )
            
            return results
            
        except Exception as e:
            # Update job with error
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
            
            logger.error(
                "Failed expired token cleanup",
                extra={
                    "job_id": str(job_id),
                    "error": str(e),
                }
            )
            raise
    
    async def cleanup_replay_protection(
        self,
        batch_size: int = 5000,
    ) -> Dict[str, Any]:
        """
        Clean up expired replay protection records.
        
        Args:
            batch_size: Number of records to process per batch
            
        Returns:
            Cleanup results and statistics
        """
        job_id = uuid.uuid4()
        cleanup_config = {
            "batch_size": batch_size,
            "cleanup_type": "replay_protection"
        }
        
        job = TokenCleanupJob(
            job_id=job_id,
            job_type="replay_protection",
            cleanup_config=cleanup_config,
        )
        
        try:
            self.db.add(job)
            await self.db.commit()
            
            logger.info(
                "Starting replay protection cleanup",
                extra={
                    "job_id": str(job_id),
                    "batch_size": batch_size,
                }
            )
            
            current_time = datetime.utcnow()
            total_cleaned = 0
            
            while True:
                # Delete expired replay protection records
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
                
                logger.debug(
                    "Cleaned up replay protection batch",
                    extra={
                        "job_id": str(job_id),
                        "batch_cleaned": batch_cleaned,
                    }
                )
                
                # Small delay
                await asyncio.sleep(0.05)
            
            # Update job with results
            completion_time = datetime.utcnow()
            duration = int((completion_time - job.started_at).total_seconds())
            
            await self.db.execute(
                update(TokenCleanupJob)
                .where(TokenCleanupJob.job_id == job_id)
                .values(
                    status="completed",
                    completed_at=completion_time,
                    duration_seconds=duration,
                    tokens_processed=total_cleaned,
                    tokens_cleaned=total_cleaned,
                )
            )
            await self.db.commit()
            
            results = {
                "job_id": str(job_id),
                "status": "completed",
                "records_cleaned": total_cleaned,
                "duration_seconds": duration,
            }
            
            logger.info(
                "Completed replay protection cleanup",
                extra=results
            )
            
            return results
            
        except Exception as e:
            # Update job with error
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
            
            logger.error(
                "Failed replay protection cleanup",
                extra={
                    "job_id": str(job_id),
                    "error": str(e),
                }
            )
            raise
    
    async def get_cleanup_statistics(
        self,
        days: int = 7,
    ) -> Dict[str, Any]:
        """
        Get cleanup job statistics for monitoring.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Cleanup statistics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get recent jobs
            query = select(TokenCleanupJob).where(
                TokenCleanupJob.created_at >= cutoff_date
            ).order_by(TokenCleanupJob.created_at.desc())
            
            result = await self.db.execute(query)
            jobs = result.scalars().all()
            
            # Calculate statistics
            total_jobs = len(jobs)
            completed_jobs = len([j for j in jobs if j.status == "completed"])
            failed_jobs = len([j for j in jobs if j.status == "failed"])
            total_tokens_cleaned = sum(j.tokens_cleaned for j in jobs)
            
            # Get success rate
            success_rate = (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
            
            # Get average duration for completed jobs
            completed_durations = [j.duration_seconds for j in jobs if j.status == "completed" and j.duration_seconds]
            avg_duration = sum(completed_durations) / len(completed_durations) if completed_durations else 0
            
            statistics = {
                "period_days": days,
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "success_rate_percent": round(success_rate, 2),
                "total_tokens_cleaned": total_tokens_cleaned,
                "average_duration_seconds": round(avg_duration, 2),
                "recent_jobs": [
                    {
                        "job_id": str(job.job_id),
                        "job_type": job.job_type,
                        "status": job.status,
                        "tokens_cleaned": job.tokens_cleaned,
                        "duration_seconds": job.duration_seconds,
                        "created_at": job.created_at.isoformat(),
                    }
                    for job in jobs[:10]  # Last 10 jobs
                ]
            }
            
            logger.info(
                "Retrieved cleanup statistics",
                extra={
                    "period_days": days,
                    "total_jobs": total_jobs,
                    "success_rate": success_rate,
                }
            )
            
            return statistics
            
        except Exception as e:
            logger.error(
                "Failed to retrieve cleanup statistics",
                extra={"error": str(e), "days": days}
            )
            raise
