"""
Retention Policy Engine
======================

A.27 Implementation: Per-tenant retention policy enforcement with automated
cleanup, compliance tracking, and regulatory requirement handling.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import select, delete, and_, func, desc
from sqlalchemy.dialects.postgresql import insert

from .models import AuditEvent, RetentionPolicy, TenantAuditConfig

logger = logging.getLogger(__name__)


class RetentionEngine:
    """
    Manages audit event retention policies and automated cleanup.
    
    Features:
    - Per-tenant retention policy enforcement
    - Automated cleanup scheduling
    - Compliance framework integration
    - Legal hold support
    - Archive to cold storage
    """
    
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self.cleanup_task = None
        self.running = False
        
    async def start_cleanup_scheduler(self):
        """Start the automated cleanup scheduler."""
        if self.running:
            return
            
        self.running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_scheduler())
        logger.info("Retention cleanup scheduler started")
        
    async def stop_cleanup_scheduler(self):
        """Stop the cleanup scheduler."""
        self.running = False
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Retention cleanup scheduler stopped")
        
    async def _cleanup_scheduler(self):
        """Background scheduler for retention cleanup."""
        while self.running:
            try:
                await self.run_retention_cleanup()
                # Run cleanup every hour
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retention cleanup scheduler: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
                
    async def run_retention_cleanup(self):
        """
        Run retention policy cleanup across all tenants.
        
        Returns:
            Dict with cleanup statistics
        """
        logger.info("Starting retention cleanup process")
        start_time = datetime.now(timezone.utc)
        
        stats = {
            "tenants_processed": 0,
            "events_processed": 0,
            "events_archived": 0,
            "events_deleted": 0,
            "errors": 0
        }
        
        async with self.session_factory() as session:
            try:
                # Get all tenants with active retention policies
                tenants_query = select(RetentionPolicy.tenant_id).distinct().where(
                    RetentionPolicy.status == "active"
                )
                tenant_result = await session.execute(tenants_query)
                tenant_ids = [row[0] for row in tenant_result]
                
                for tenant_id in tenant_ids:
                    try:
                        tenant_stats = await self._process_tenant_retention(tenant_id, session)
                        stats["events_processed"] += tenant_stats["events_processed"]
                        stats["events_archived"] += tenant_stats["events_archived"]
                        stats["events_deleted"] += tenant_stats["events_deleted"]
                        stats["tenants_processed"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing retention for tenant {tenant_id}: {e}")
                        stats["errors"] += 1
                        
                await session.commit()
                
            except Exception as e:
                logger.error(f"Error in retention cleanup process: {e}")
                await session.rollback()
                stats["errors"] += 1
                
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"Retention cleanup completed in {execution_time:.2f}s: {stats}")
        
        return stats
        
    async def _process_tenant_retention(self, tenant_id: str, session: AsyncSession) -> Dict[str, int]:
        """Process retention policies for a specific tenant."""
        stats = {"events_processed": 0, "events_archived": 0, "events_deleted": 0}
        
        # Get tenant configuration
        config_query = select(TenantAuditConfig).where(TenantAuditConfig.tenant_id == tenant_id)
        config_result = await session.execute(config_query)
        config = config_result.scalar_one_or_none()
        
        # Skip if legal hold is active
        if config and config.enable_legal_hold:
            logger.info(f"Skipping retention cleanup for tenant {tenant_id} - legal hold active")
            return stats
            
        # Get active retention policies for tenant
        policies_query = select(RetentionPolicy).where(
            and_(
                RetentionPolicy.tenant_id == tenant_id,
                RetentionPolicy.status == "active",
                RetentionPolicy.effective_from <= datetime.now(timezone.utc)
            )
        ).order_by(desc(RetentionPolicy.priority))
        
        policies_result = await session.execute(policies_query)
        policies = policies_result.scalars().all()
        
        if not policies:
            logger.debug(f"No active retention policies for tenant {tenant_id}")
            return stats
            
        # Process each policy
        for policy in policies:
            try:
                policy_stats = await self._apply_retention_policy(policy, session)
                stats["events_processed"] += policy_stats["events_processed"]
                stats["events_archived"] += policy_stats["events_archived"]
                stats["events_deleted"] += policy_stats["events_deleted"]
                
            except Exception as e:
                logger.error(f"Error applying retention policy {policy.policy_id}: {e}")
                
        return stats
        
    async def _apply_retention_policy(self, policy: RetentionPolicy, session: AsyncSession) -> Dict[str, int]:
        """Apply a specific retention policy."""
        stats = {"events_processed": 0, "events_archived": 0, "events_deleted": 0}
        
        now = datetime.now(timezone.utc)
        retention_cutoff = now - timedelta(days=policy.retention_days)
        
        # Find events eligible for retention action
        events_query = select(AuditEvent).where(
            and_(
                AuditEvent.tenant_id == policy.tenant_id,
                AuditEvent.event_type.in_(policy.event_types),
                AuditEvent.event_timestamp <= retention_cutoff,
                AuditEvent.retention_until <= now
            )
        ).limit(1000)  # Process in batches
        
        events_result = await session.execute(events_query)
        events = events_result.scalars().all()
        
        if not events:
            return stats
            
        logger.info(f"Processing {len(events)} events for retention policy {policy.policy_name}")
        
        # Check if archiving is enabled
        if policy.archive_after_days:
            archive_cutoff = now - timedelta(days=policy.archive_after_days)
            
            # Archive older events
            archive_events = [e for e in events if e.event_timestamp <= archive_cutoff]
            if archive_events:
                archived_count = await self._archive_events(archive_events, session)
                stats["events_archived"] += archived_count
                
            # Delete remaining events
            delete_events = [e for e in events if e.event_timestamp > archive_cutoff]
        else:
            delete_events = events
            
        if delete_events:
            deleted_count = await self._delete_events(delete_events, session)
            stats["events_deleted"] += deleted_count
            
        stats["events_processed"] = len(events)
        return stats
        
    async def _archive_events(self, events: List[AuditEvent], session: AsyncSession) -> int:
        """Archive events to cold storage."""
        # In a real implementation, this would:
        # 1. Export events to cold storage (S3, Glacier, etc.)
        # 2. Verify successful transfer
        # 3. Mark events as archived or delete them
        
        archived_count = 0
        
        for event in events:
            try:
                # Placeholder: Export to cold storage
                await self._export_to_cold_storage(event)
                archived_count += 1
                
            except Exception as e:
                logger.error(f"Error archiving event {event.event_id}: {e}")
                
        # Delete archived events from primary storage
        if archived_count > 0:
            event_ids = [e.event_id for e in events[:archived_count]]
            delete_query = delete(AuditEvent).where(AuditEvent.event_id.in_(event_ids))
            await session.execute(delete_query)
            
        return archived_count
        
    async def _delete_events(self, events: List[AuditEvent], session: AsyncSession) -> int:
        """Delete events that have exceeded retention period."""
        if not events:
            return 0
            
        event_ids = [e.event_id for e in events]
        delete_query = delete(AuditEvent).where(AuditEvent.event_id.in_(event_ids))
        result = await session.execute(delete_query)
        
        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} events from primary storage")
        
        return deleted_count
        
    async def _export_to_cold_storage(self, event: AuditEvent):
        """Export single event to cold storage."""
        # Placeholder implementation
        # In production, this would integrate with:
        # - AWS S3/Glacier
        # - Azure Blob Storage
        # - Google Cloud Storage
        # - Tape backup systems
        
        logger.debug(f"Archiving event {event.event_id} to cold storage")
        
    async def calculate_retention_requirements(self, tenant_id: str) -> Dict[str, Any]:
        """
        Calculate current retention requirements for a tenant.
        
        Returns:
            Dictionary with retention analysis and recommendations
        """
        async with self.session_factory() as session:
            # Get tenant policies
            policies_query = select(RetentionPolicy).where(
                and_(
                    RetentionPolicy.tenant_id == tenant_id,
                    RetentionPolicy.status == "active"
                )
            )
            policies_result = await session.execute(policies_query)
            policies = policies_result.scalars().all()
            
            # Get event type distribution
            events_query = select(
                AuditEvent.event_type,
                func.count(),
                func.min(AuditEvent.event_timestamp),
                func.max(AuditEvent.event_timestamp)
            ).where(AuditEvent.tenant_id == tenant_id).group_by(AuditEvent.event_type)
            
            events_result = await session.execute(events_query)
            event_stats = events_result.all()
            
            # Calculate coverage
            covered_types = set()
            for policy in policies:
                covered_types.update(policy.event_types)
                
            all_types = {row[0] for row in event_stats}
            uncovered_types = all_types - covered_types
            
            # Calculate storage projections
            total_events = sum(row[1] for row in event_stats)
            oldest_event = min((row[2] for row in event_stats), default=None)
            newest_event = max((row[3] for row in event_stats), default=None)
            
            return {
                "tenant_id": tenant_id,
                "active_policies": len(policies),
                "event_types_covered": len(covered_types),
                "event_types_uncovered": len(uncovered_types),
                "uncovered_types": list(uncovered_types),
                "total_events": total_events,
                "oldest_event": oldest_event.isoformat() if oldest_event else None,
                "newest_event": newest_event.isoformat() if newest_event else None,
                "retention_compliance": len(uncovered_types) == 0,
                "policies": [
                    {
                        "name": p.policy_name,
                        "retention_days": p.retention_days,
                        "event_types": p.event_types,
                        "compliance_framework": p.compliance_framework
                    }
                    for p in policies
                ]
            }
            
    async def validate_retention_policy(self, policy: RetentionPolicy) -> Dict[str, Any]:
        """
        Validate a retention policy for compliance and effectiveness.
        
        Returns:
            Validation results with recommendations
        """
        issues = []
        recommendations = []
        
        # Validate retention period
        if policy.retention_days < 30:
            issues.append("Retention period less than 30 days may not meet compliance requirements")
        elif policy.retention_days > 3650:  # 10 years
            recommendations.append("Consider if retention period exceeds business requirements")
            
        # Validate compliance framework alignment
        if policy.compliance_framework:
            framework_requirements = {
                "SOX": {"min_days": 2555, "event_types": ["financial_transaction", "system_configuration"]},
                "HIPAA": {"min_days": 2190, "event_types": ["data_access", "data_modification"]},
                "GDPR": {"max_days": 1095, "event_types": ["data_access", "user_management"]},
                "PCI_DSS": {"min_days": 365, "event_types": ["authentication", "data_access"]}
            }
            
            if policy.compliance_framework in framework_requirements:
                req = framework_requirements[policy.compliance_framework]
                
                if "min_days" in req and policy.retention_days < req["min_days"]:
                    issues.append(f"{policy.compliance_framework} requires minimum {req['min_days']} days retention")
                    
                if "max_days" in req and policy.retention_days > req["max_days"]:
                    issues.append(f"{policy.compliance_framework} requires maximum {req['max_days']} days retention")
                    
                if "event_types" in req:
                    missing_types = set(req["event_types"]) - set(policy.event_types)
                    if missing_types:
                        recommendations.append(f"Consider adding {missing_types} for {policy.compliance_framework} compliance")
                        
        # Validate archive settings
        if policy.archive_after_days:
            if policy.archive_after_days >= policy.retention_days:
                issues.append("Archive period should be less than retention period")
                
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "recommendations": recommendations,
            "compliance_aligned": policy.compliance_framework and len(issues) == 0
        }
